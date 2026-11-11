#!/usr/bin/env python3
# ruff: noqa: E402 - isolated CLI explicitly adds the repository source path.
"""Resume the approved 200-source MICE completion with frozen MIRA judging."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from samtok_benchmark.external_mira.data import immutable, read
from samtok_benchmark.external_mira.score import ensure_evaluator, export, judge, overall
from samtok_benchmark.io import write_json

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
CONTROL = NAS / ".ifbench-tmp/external_additions_20261111/mira_mice"
ROOT = NAS / "experiments2/SAMTokEdit/external_mira/mice_20261111"
PYTHON = "/tmp/ifbench/fairness-dev20-runtime-20261030/generation/env/bin/python"
KEY = NAS / ".ifbench-tmp/external_bench_20261102/secrets/gpt54.key"


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge-job")
    args = parser.parse_args()
    if args.judge_job:
        return judge(args.judge_job)
    import fcntl

    lock = (CONTROL / "judge.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if not KEY.is_file():
        raise RuntimeError("Existing approved GPT credential file is missing")
    plan = read(ROOT / "run/RUN.json")
    cfg = read(CONTROL / "CONFIG.json")
    jc = read(CONTROL / "JUDGE_CONFIG.json")
    evaluator = ensure_evaluator(jc["source"])
    batches = {f"batch{i // 10:02d}": plan["case_ids"][i : i + 10] for i in range(0, 200, 10)}
    logs = CONTROL / "judge_logs"
    logs.mkdir(exist_ok=True)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="", MIRA_API_KEY_FILE=str(KEY), OMP_NUM_THREADS="4")

    def one(name, ids):
        view = CONTROL / "judge_views" / name
        immutable(view / "RUN.json", dict(plan, case_ids=ids))
        link = view / "mice"
        target = ROOT / "run/mice"
        if not link.exists():
            link.symlink_to(target, target_is_directory=True)
        if link.resolve() != target.resolve():
            raise ValueError("Unexpected generation view")
        while any(not (target / "edit" / c / "result.json").exists() for c in ids):
            if all((CONTROL / "formal" / f"shard-{s}-DONE.json").exists() for s in range(4)):
                raise RuntimeError("Generation ended without complete terminal coverage")
            time.sleep(15)
        directory = ROOT / "scores_gpt54" / name / "mice"
        job = export(plan["bundle"], view, directory, "mice", cfg, evaluator, jc)
        if not job["valid_outputs"]:
            return {"batch": name, "status": "no_valid_outputs"}
        attempt = 0
        while True:
            attempt += 1
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            path = logs / f"{name}-{stamp}.log"
            with path.open("x") as log:
                rc = subprocess.run(
                    [
                        PYTHON,
                        "-u",
                        "-I",
                        str(Path(__file__).resolve()),
                        "--judge-job",
                        str(directory / "JOB.json"),
                    ],
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                ).returncode
            immutable(
                logs / f"{name}-{stamp}.json",
                {
                    "returncode": rc,
                    "finished": now(),
                    "log": str(path),
                    "attempt_this_session": attempt,
                },
            )
            if rc == 0:
                print(f"{now()} {name}: scored {job['valid_outputs']}", flush=True)
                return {"batch": name, "status": "complete"}
            text = path.read_text()
            transient = any(
                x in text
                for x in (
                    "RateLimitError",
                    "APIConnectionError",
                    "APITimeoutError",
                    "InternalServerError",
                    "RemoteProtocolError",
                    "ConnectionResetError",
                    "Resource exhausted",
                    "insufficient capacity",
                )
            )
            if not transient:
                raise RuntimeError(f"Non-transient Judge error; inspect {path}")
            print(f"{now()} {name}: temporary API error; preserve answers and resume", flush=True)
            time.sleep(min(60, 10 * attempt))

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(lambda x: one(*x), batches.items()))
    rows = []
    for name in batches:
        file = ROOT / "scores_gpt54" / name / "mice/scores/per_image_results.jsonl"
        if file.exists():
            rows.extend(json.loads(s) for s in file.read_text().splitlines() if s.strip())
    import numpy as np

    if len({r["image"] for r in rows}) != len(rows):
        raise ValueError("Duplicate Judge image")
    values = [
        [r[k] for k in ("prompt_following", "consistency", "perceptual_quality")] for r in rows
    ]
    report = {
        "model": "mice",
        "total": 200,
        "scored": len(rows),
        "complete": len(rows) == 200,
        "judge_config": jc,
        "outcomes": outcomes,
        "per_image": rows,
    }
    if values:
        report.update(zip(("PF", "Cons", "PQ"), np.asarray(values).mean(axis=0).tolist()))
        report["Overall"] = overall(values)
    immutable(ROOT / "REPORT.json", report)
    write_json(
        CONTROL / "JUDGE_STATUS.json",
        {
            "status": "complete" if len(rows) == 200 else "incomplete",
            "scored": len(rows),
            "finished": now(),
        },
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ("per_image", "judge_config", "outcomes")}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
