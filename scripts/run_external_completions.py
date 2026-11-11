#!/usr/bin/env python3
# ruff: noqa: E402 - isolated CLI explicitly adds the repository source path.
"""Four local GPU lanes, automatic objective scoring, and durable progress.

Run only after independent smoke generation and metric validation. Resume
finished immutable receipts; never resample a failed or unknown admission.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from samtok_benchmark.io import write_json
from samtok_benchmark.external_refedit.data import read, immutable

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
CONTROL = NAS / ".ifbench-tmp/external_additions_20261111/compbench"
ENTRY = REPO / "scripts/complete_external_baselines.py"
SCRATCH = Path("/tmp/ifbench/external_additions_20261111")
PYTHONS = {
    "generation": "/tmp/ifbench/fairness-dev20-runtime-20261030/generation/env/bin/python",
    "tokens": "/tmp/ifbench/external_bench_20261102/env_pass1/bin/python",
    "sitedit": "/tmp/ifbench/external_bench_20261102/env_v4/bin/python",
    "metrics": "/tmp/ifbench/external_pilots_20261107/env_metrics/bin/python",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    global CONTROL, ENTRY
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parsed", action="store_true")
    args = parser.parse_args()
    smoke_control = CONTROL
    if args.parsed:
        CONTROL = CONTROL / "syntax_recovery"
        ENTRY = REPO / "scripts/complete_external_parsed.py"
    locks = []
    for p in (
        CONTROL / "controller.lock",
        Path("/tmp/claude_gpu_4_5.lock"),
        Path("/tmp/claude_gpu_6_7.lock"),
    ):
        handle = p.open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locks.append(handle)
    immutable(
        CONTROL / "SCHEDULING.json",
        {
            "gpus": [4, 5, 6, 7],
            "order": ([] if args.parsed else ["sitedit_tokens"])
            + [
                "sitedit_edit",
                "mirage_plan_turn01",
                "mirage_edit_turn01",
                "mirage_plan_turn2",
                "mirage_edit_turn2",
            ],
            "objective_scoring": "CPU FP32, four shards; no CompBench GPT requests",
            "resume": "immutable identity-checked terminal records only; no automatic failed/unknown retries",
        },
    )
    plans = {m: read(CONTROL / m / "PLAN.json") for m in ("sitedit", "mirage")}
    for model, plan in plans.items():
        smoke = smoke_control / model / "smoke"
        for cid in plan["smoke"]:
            r = read(smoke / "run" / model / "edit" / cid / "result.json")
            if r["status"] != "completed":
                raise RuntimeError(f"{model}: smoke has a non-completed output")
            metric = read(smoke / "scores" / model / cid / "local.json")
            if metric["status"] != "completed":
                raise RuntimeError(f"{model}: smoke metric failed")
    if args.parsed:
        for cid in plans["sitedit"]["case_ids"]:
            record = read(
                Path(plans["sitedit"]["results_root"]) / "run/sitedit/tokens" / cid / "result.json"
            )
            if record["native"]["fallback_units"] or len(record["native"]["units"]) != 2:
                raise RuntimeError("Derived grounding must contain both native target codes")
    logs = CONTROL / "logs"
    logs.mkdir(exist_ok=True)
    children, mutex, stopping = {}, threading.Lock(), threading.Event()
    state = {
        "status": "running",
        "started": now(),
        "controller_pid": os.getpid(),
        "active": {},
        "completed_phases": [],
    }

    def save():
        write_json(CONTROL / "STATUS.json", dict(state, updated=now()))

    def stop(signum, _frame):
        stopping.set()
        with mutex:
            state["status"] = "stopping_after_current_requests"
            for process in children.values():
                if process.poll() is None:
                    process.send_signal(signal.SIGUSR1)
            save()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def execute(model, command, stage, shard, cohort=0):
        if stopping.is_set():
            raise RuntimeError("Controller was stopped; no further requests admitted")
        gpu = 4 + shard
        runtime = (
            "metrics"
            if command != "run"
            else "tokens"
            if stage == "tokens"
            else "sitedit"
            if model == "sitedit"
            else "generation"
        )
        argv = [
            PYTHONS[runtime],
            "-u",
            "-I",
            str(ENTRY),
            command,
            "--model",
            model,
            "--shard",
            str(shard),
            "--shards",
            "4",
        ]
        if stage:
            argv += ["--stage", stage]
        if cohort:
            argv += ["--cohort", str(cohort)]
        env = dict(
            os.environ,
            CUDA_VISIBLE_DEVICES=str(gpu) if command == "run" else "",
            OMP_NUM_THREADS="4",
            MKL_NUM_THREADS="4",
            TOKENIZERS_PARALLELISM="false",
            MASTER_PORT=str(44400 + gpu),
            PYTHONDONTWRITEBYTECODE="1",
            TORCHINDUCTOR_CACHE_DIR=str(SCRATCH / f"gpu{gpu}/inductor"),
            TRITON_CACHE_DIR=str(SCRATCH / f"gpu{gpu}/triton"),
        )
        env.pop("IFBENCH_NATIVE_SOURCES", None)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        name = f"{model}-{command}-{stage}-{cohort}-{shard}"
        logfile = logs / f"{name}-{stamp}.log"
        with logfile.open("x") as log:
            p = subprocess.Popen(argv, env=env, stdout=log, stderr=subprocess.STDOUT)
            with mutex:
                children[p.pid] = p
                state["active"][name] = {
                    "pid": p.pid,
                    "started": now(),
                    "log": str(logfile),
                    "gpu": gpu if command == "run" else None,
                }
                save()
            rc = p.wait()
        with mutex:
            children.pop(p.pid)
            entry = state["active"].pop(name)
            entry.update(finished=now(), returncode=rc, name=name)
            state["completed_phases"].append(entry)
            save()
        if rc:
            raise RuntimeError(f"{name} exited {rc}; inspect {logfile}")
        return entry

    def phase(model, stage, cohort=0):
        print(f"{now()} {model}: {stage}, cohort={cohort}", flush=True)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda s: execute(model, "run", stage, s, cohort), range(4)))

    def scoring(model):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda s: execute(model, "score", None, s), range(4)))
        execute(model, "report", None, 0)
        if model == "sitedit":
            logpath = logs / (
                "sitedit-full-merge-"
                + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                + ".log"
            )
            with logpath.open("x") as log:
                subprocess.run(
                    [
                        PYTHONS["metrics"],
                        "-u",
                        "-I",
                        str(REPO / "scripts/summarize_external_completions.py"),
                        "--merge-sitedit",
                    ]
                    + (["--parsed"] if args.parsed else []),
                    check=True,
                    env=dict(os.environ, CUDA_VISIBLE_DEVICES=""),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
        print(f"{now()} {model}: objective report written", flush=True)

    def progress():
        # Log only counts, and scan at most once a minute. Immutable result records
        # are authoritative; no output is ever rewritten by this monitor.
        while not stopping.wait(60):
            summary = {}
            for model, plan in plans.items():
                root = Path(plan["results_root"])
                summary[model] = {
                    stage: len(list((root / "run" / model / stage).glob("*/result.json")))
                    for stage in (("tokens", "edit") if model == "sitedit" else ("plan", "edit"))
                }
                summary[model]["scores"] = len(list((root / "scores" / model).glob("*/local.json")))
            write_json(CONTROL / "PROGRESS.json", {"updated": now(), "counts": summary})
            print(f"{now()} progress {json.dumps(summary)}", flush=True)

    threading.Thread(target=progress, daemon=True).start()
    try:
        with ThreadPoolExecutor(max_workers=1) as score_pool:
            if not args.parsed:
                phase("sitedit", "tokens")
            phase("sitedit", "edit")
            sitedit_scores = score_pool.submit(scoring, "sitedit")
            phase("mirage", "plan", 1)
            phase("mirage", "edit", 1)
            phase("mirage", "plan", 2)
            phase("mirage", "edit", 2)
            sitedit_scores.result()
            scoring("mirage")
        with mutex:
            state["status"] = "complete"
            state["finished"] = now()
            save()
    except BaseException as exc:
        with mutex:
            state["status"] = "error"
            state["error"] = repr(exc)
            save()
        raise
    finally:
        stopping.set()


if __name__ == "__main__":
    main()
