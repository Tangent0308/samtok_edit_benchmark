"""Run one adapter over prepared jobs on several GPUs, then merge the per-shard registries.

Each shard is an ordinary, resumable `samtok-benchmark-v2 run-editor` call on a subset of the
jobs, so outputs keep the benchmark's content and run-key binding. Example:

  python run_sharded.py --jobs INPUTS/jobs.jsonl --output RUNS/qwen_image_edit_2511 \
      --model qwen_image_edit_2511 --gpus 0,1,2,3,4,5,6,7 [--case-ids ids.txt]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from adapters import default_config
from samtok_benchmark.io import read_jsonl, write_json, write_jsonl

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--model",
        required=True,
        choices=("qwen_image_edit_2511", "qwen_image_21", "flux2_dev", "flux2_klein_4b", "flux3_klein"),
    )
    parser.add_argument("--gpus", required=True, help="comma-separated CUDA device ids")
    parser.add_argument("--case-ids", type=Path, help="optional file with one case id per line")
    parser.add_argument("--seed", type=int, default=0)
    a = parser.parse_args()

    jobs = read_jsonl(a.jobs)
    if a.case_ids:
        wanted = [line.strip() for line in a.case_ids.read_text().splitlines() if line.strip()]
        by_case = {j["case_id"]: j for j in jobs}
        jobs = [by_case[c] for c in wanted]
    gpus = [g.strip() for g in a.gpus.split(",") if g.strip()]
    config = default_config(a.model)
    a.output.mkdir(parents=True, exist_ok=True)
    config_path = a.output / "config.json"
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        raise SystemExit(f"{config_path} differs from the current config; use a new output directory")
    write_json(config_path, config)

    procs = []
    for rank, gpu in enumerate(gpus):
        shard = jobs[rank :: len(gpus)]
        if not shard:
            continue
        shard_dir = a.output / "shards" / f"shard{rank:02d}"
        shard_dir.mkdir(parents=True, exist_ok=True)
        # Rewrite the shard's job list only on first launch; reruns resume against it.
        jobs_file = shard_dir / "jobs.jsonl"
        if not jobs_file.exists():
            write_jsonl(jobs_file, shard)
        elif [j["job_id"] for j in read_jsonl(jobs_file)] != [j["job_id"] for j in shard]:
            raise SystemExit(f"{jobs_file} holds a different job split; use a new output directory")
        env = {
            **os.environ,
            "CUDA_VISIBLE_DEVICES": gpu,
            "PYTHONPATH": str(HERE.parent.parent) + os.pathsep + os.environ.get("PYTHONPATH", ""),
        }
        command = [
            sys.executable, "-m", "samtok_benchmark.v2.cli", "run-editor",
            "--inputs", str(jobs_file), "--output", str(shard_dir),
            "--adapter", "adapters:edit", "--method", a.model,
            "--seed", str(a.seed), "--config", str(config_path),
        ]
        log = (shard_dir / "run.log").open("a")
        procs.append((rank, subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)))
        print(f"shard{rank:02d}: GPU {gpu}, {len(shard)} jobs", flush=True)

    failed = [rank for rank, p in procs if p.wait() != 0]
    rows = []
    for rank, _ in procs:
        registry = a.output / "shards" / f"shard{rank:02d}" / "outputs.jsonl"
        if registry.exists():
            rows.extend(read_jsonl(registry))
    write_jsonl(a.output / "outputs.jsonl", sorted(rows, key=lambda r: r["job_id"]))
    ok = sum(r["status"] == "ok" for r in rows)
    print(json.dumps({"jobs": len(jobs), "ok": ok, "failed_shards": failed}), flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
