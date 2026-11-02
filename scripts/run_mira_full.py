#!/usr/bin/env python3
"""Foreground MIRA generation, bounded concurrent judging, and final coverage-aware table."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


def now():
    return datetime.now(timezone.utc).isoformat()


def write_table(root, scores):
    rows = scores["rows"]
    columns = ["model", "PF", "Cons", "PQ", "Overall", "Overall_CI95", "scored", "total", "complete"]
    with (root / "TABLE.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: row.get(key) for key in columns} for row in rows)
    lines = ["# MIRA / GPT-5.4", "", "All metrics use the same GPT-5.4 judge and pinned MIRA scoring rules.", "",
             "| Method | PF | Cons | PQ | Overall | 95% CI | Scored/total |",
             "|---|---:|---:|---:|---:|---|---:|"]
    for row in rows:
        cells = [f"{row[key]:.3f}" if key in row else "missing" for key in ("PF", "Cons", "PQ", "Overall")]
        ci = row.get("Overall_CI95")
        lines.append("| " + " | ".join([row["model"], *cells,
            f"[{ci[0]:.3f}, {ci[1]:.3f}]" if ci else "not available",
            f"{row['scored']}/{row['total']}"]) + " |")
    if not all(r["complete"] for r in rows):
        lines += ["", "INCOMPLETE: means above use the scored subset. Missing cases are not zero or silently dropped."]
    lines += ["", "Paired Overall difference intervals, SITEdit minus baseline:", "",
              "```json", json.dumps(scores["paired_sitedit_minus_baseline_CI95"], indent=2), "```", "",
              "Data overlap audit must be reported separately before making an external-generalization claim.",
              "Generation errors and unavailable scores remain in the 200-source denominators."]
    (root / "TABLE.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--protocol-audit", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--gpus", default="0,1,2,3,4")
    parser.add_argument("--judge-workers", type=int, default=3)
    args = parser.parse_args()
    from samtok_benchmark.io import sha256_file, write_json
    from samtok_benchmark.external_mira import MODELS
    from samtok_benchmark.external_mira.data import read, immutable, load_bundle
    from samtok_benchmark.external_mira.score import export, aggregate, ensure_evaluator
    from samtok_benchmark.external_mira.worker import verify_config
    if not 1 <= args.judge_workers <= 5:
        raise ValueError("Judge concurrency must be between one and five")
    config = read(REPO / "configs/external/mira.json")
    judge_config = read(REPO / "configs/external/mira_judge_gpt54.json")
    verify_config(config)
    index = load_bundle(args.bundle)
    audit = read(args.protocol_audit / "PROTOCOL.json")
    replay = read(args.protocol_audit / "REPLAY.json")
    if audit["bundle_digest"] != index["digest"] or not replay["pixel_equal"]:
        raise ValueError("The native parity and scoring-input audit has not passed")
    args.root = args.root.resolve()
    if not args.root.is_relative_to(Path(config["formal_results_root"]).resolve()):
        raise ValueError("Formal results must use the designated root")
    if args.scratch.resolve().is_relative_to(args.root):
        raise ValueError("Temporary compiler caches and scratch must stay outside formal results")
    args.root.mkdir(parents=True, exist_ok=True)
    args.scratch.mkdir(parents=True, exist_ok=True)
    lock = (args.root / ".pipeline.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    run, scores = args.root / "run_001", args.root / "scores_gpt54_001"
    run.mkdir(exist_ok=True)
    # The existing launcher puts caches under output/cache; route that path to temporary storage.
    cache = args.scratch.resolve() / "cache"
    cache.mkdir(exist_ok=True)
    if not (run / "cache").exists():
        (run / "cache").symlink_to(cache, target_is_directory=True)
    if (run / "cache").resolve() != cache:
        raise ValueError("Unexpected cache location")
    immutable(args.root / "PIPELINE.json", {"schema": "mira.full.pipeline.v1", "gpus": args.gpus,
        "models": list(MODELS), "cases": 200, "bundle_digest": index["digest"],
        "generation_config": config, "judge_config": judge_config, "judge_workers": args.judge_workers,
        "launcher_sha256": sha256_file(__file__), "protocol_audit": str(args.protocol_audit),
        "protocol_sha256": sha256_file(args.protocol_audit / "PROTOCOL.json"),
        "replay_sha256": sha256_file(args.protocol_audit / "REPLAY.json"),
        "authorization": "User approved protocol audit, full 200x5 generation, GPT-5.4 scoring, and overlap audit."})
    immutable(args.root / "GENERATION_CONFIG.json", config)
    immutable(args.root / "JUDGE_CONFIG.json", judge_config)
    source = args.root / "run_mira_full.py"
    if not source.exists():
        with source.open("xb") as stream:
            stream.write(Path(__file__).read_bytes())
    if sha256_file(source) != sha256_file(__file__):
        raise ValueError("Pipeline source snapshot changed")
    evaluator = ensure_evaluator(judge_config["source"])
    env = dict(os.environ, PYTHONPATH=str(REPO / "src"), PYTHONDONTWRITEBYTECODE="1")
    python = config["runtime"]["generation"]
    command = [python, "-u", "-m", "samtok_benchmark.external_mira", "run",
               "--bundle", str(args.bundle.resolve()), "--config", str(args.root / "GENERATION_CONFIG.json"),
               "--output", str(run), "--gpus", args.gpus]
    subprocess_log = (args.root / "generation.log").open("a")
    process = subprocess.Popen(command, cwd=REPO, env=env, stdout=subprocess_log, stderr=subprocess.STDOUT)
    write_json(args.root / "STATUS.json", {"status": "running", "generation_pid": process.pid,
                                           "pipeline_pid": os.getpid(), "started_at": now()})
    print(f"Started formal generation PID {process.pid}: {run}", flush=True)

    def judge_model(model):
        directory = scores / model
        job = export(args.bundle, run, directory, model, config, evaluator, judge_config)
        if not job["valid_outputs"]:
            return {"model": model, "status": "no-valid-outputs", "attempts": []}
        attempts = []
        command = [python, "-u", "-m", "samtok_benchmark.external_mira", "judge",
                   "--job", str(directory / "JOB.json")]
        for attempt in range(1, 4):
            logfile = directory / f"judge_attempt_{attempt:02d}.log"
            with logfile.open("a") as log:
                offset = log.tell()
                started = now()
                code = subprocess.run(command, env=dict(env, CUDA_VISIBLE_DEVICES=""),
                                      stdout=log, stderr=subprocess.STDOUT).returncode
            with logfile.open() as stream:
                stream.seek(offset)
                text = stream.read()
            attempts.append({"attempt": attempt, "started_at": started, "finished_at": now(), "exit_code": code})
            write_json(directory / "ATTEMPTS.json", attempts)
            if code == 0:
                print(f"Judge complete: {model}", flush=True)
                return {"model": model, "status": "finished", "attempts": attempts}
            temporary = any(name in text for name in ("RateLimitError", "APIConnectionError",
                "APITimeoutError", "InternalServerError", "RemoteProtocolError", "ConnectionResetError"))
            if not temporary or attempt == 3:
                break
            print(f"Transient Judge failure: {model}; preserving receipts and resuming after 30 s", flush=True)
            time.sleep(30)
        return {"model": model, "status": "judge-failed", "attempts": attempts}

    futures = {}
    with ThreadPoolExecutor(max_workers=args.judge_workers) as pool:
        while True:
            for model in MODELS:
                if model in futures:
                    continue
                terminals = list((run / model / "edit").glob("*/result.json"))
                if len(terminals) == 200:
                    print(f"All 200 generation receipts present: {model}; scheduling Judge", flush=True)
                    futures[model] = pool.submit(judge_model, model)
            if process.poll() is not None:
                break
            time.sleep(15)
        for model in MODELS:
            if model not in futures:
                futures[model] = pool.submit(judge_model, model)
        outcomes = {model: future.result() for model, future in futures.items()}
    subprocess_log.close()
    report = aggregate(scores, list(MODELS))
    write_table(args.root, report)
    complete = all(r["complete"] for r in report["rows"])
    write_json(args.root / "STATUS.json", {"status": "complete" if complete else "finished_with_missing",
        "generation_exit_code": process.returncode, "judge": outcomes, "finished_at": now(),
        "scored": {r["model"]: r["scored"] for r in report["rows"]}})
    print(f"Formal pipeline finished; complete={complete}; table={args.root / 'TABLE.md'}", flush=True)
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
