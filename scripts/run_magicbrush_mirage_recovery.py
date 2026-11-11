#!/usr/bin/env python3
"""Foreground supervisor; only its own children, no changes to frozen scientific runs."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--logs", required=True, type=Path)
    parser.add_argument("--gpus", default="4,5,6,7")
    parser.add_argument("--authorized-all-eight", action="store_true")
    parser.add_argument("--stages", nargs="+", default=["plan", "edit", "score"])
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    cards = [int(c) for c in args.gpus.split(",")]
    allowed = set(range(8)) if args.authorized_all_eight else {4, 5, 6, 7}
    if not cards or len(cards) != len(set(cards)) or not set(cards) <= allowed:
        raise ValueError("Use distinct authorized GPUs only")
    if not set(args.stages) <= {"plan", "edit", "score"}:
        raise ValueError("Invalid stages")
    args.logs.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[1]
    script = (
        repo
        / "scripts"
        / (
            "magicbrush_mirage_recovery_8gpu.py"
            if args.authorized_all_eight
            else "magicbrush_mirage_recovery.py"
        )
    )
    generation = "/tmp/ifbench/fairness-dev20-runtime-20261030/generation/env/bin/python"
    scoring = "/tmp/ifbench/external_bench_20261102/env_v4/bin/python"
    children, stop = [], []

    def stopped(*_):
        stop.append(True)
        for child in children:
            if child.poll() is None:
                child.send_signal(signal.SIGUSR1)

    signal.signal(signal.SIGUSR1, stopped)
    signal.signal(signal.SIGTERM, stopped)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for stage in args.stages:
        if stop:
            return
        children, handles = [], []
        for shard, card in enumerate(cards):
            handle = (args.logs / f"{stamp}-{stage}-gpu{card}.log").open("x")
            handles.append(handle)
            env = dict(
                os.environ,
                CUDA_VISIBLE_DEVICES=str(card),
                TOKENIZERS_PARALLELISM="false",
                OMP_NUM_THREADS="4",
                HF_HUB_OFFLINE="1",
                TRANSFORMERS_OFFLINE="1",
                HF_HUB_DISABLE_PROGRESS_BARS="1",
            )
            env.pop("IFBENCH_NATIVE_SOURCES", None)
            command = [
                scoring if stage == "score" else generation,
                "-I",
                str(script),
                stage,
                "--root",
                str(args.root),
                "--shard",
                str(shard),
                "--shards",
                str(len(cards)),
                "--cache",
                str(args.logs / "metric-cache"),
            ]
            children.append(
                subprocess.Popen(
                    command, stdout=handle, stderr=subprocess.STDOUT, cwd=repo, env=env
                )
            )
        print(
            json.dumps({"stage": stage, "pids": [p.pid for p in children], "gpus": cards}),
            flush=True,
        )
        last = 0
        while any(p.poll() is None for p in children):
            if time.monotonic() - last > 50:
                counts = {}
                for path in (args.root / stage).glob("*/result.json"):
                    row = json.loads(path.read_text())
                    counts[row["status"]] = counts.get(row["status"], 0) + 1
                print(
                    json.dumps(
                        {
                            "stage": stage,
                            "counts": counts,
                            "active": sum(p.poll() is None for p in children),
                        }
                    ),
                    flush=True,
                )
                last = time.monotonic()
            time.sleep(1)
        for handle in handles:
            handle.close()
        if any(p.returncode for p in children):
            raise RuntimeError(f"{stage} worker exit codes: {[p.returncode for p in children]}")
    if args.report and not stop:
        subprocess.run(
            [scoring, "-I", str(script), "report", "--root", str(args.root)], cwd=repo, check=True
        )


if __name__ == "__main__":
    main()
