"""Full-run entry; preparation is CPU-only and parsers can run under python -I."""

import argparse
import json
import os
import subprocess

from . import MODELS
from .data import load_bundle


def gpu_guard(remote=False):
    gpu = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if not gpu.isdigit() or (not remote and gpu not in {"4", "5", "6", "7"}):
        raise RuntimeError("Exactly one authorized GPU is required (local: 4–7)")
    if remote and (os.environ.get("ARNOLD_WORKER_NUM") != "1" or os.environ.get("ARNOLD_ID") != "0"):
        raise RuntimeError("Remote execution requires a single-worker ARNOLD job")
    used, total = map(int, subprocess.check_output([
        "nvidia-smi", "--id=" + gpu, "--query-gpu=memory.used,memory.total",
        "--format=csv,noheader,nounits"], text=True).strip().split(","))
    if (not remote and used > 2300) or total - used < 70000:
        raise RuntimeError(f"GPU {gpu} is occupied ({used} MiB); no model started")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    for k in ("existing", "dataset", "bundle"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--workers", type=int, default=4)
    p = sub.add_parser("worker")
    for k in ("config", "bundle", "output"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--model", choices=MODELS, required=True)
    p.add_argument("--stage", choices=("tokens", "plan", "edit"), required=True)
    p.add_argument("--case-ids", nargs="+")
    p.add_argument("--remote", action="store_true")
    p = sub.add_parser("run")
    for k in ("config", "bundle", "output", "attempt"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--gpus", nargs="+", required=True)
    p.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS))
    p.add_argument("--case-ids", nargs="+")
    p.add_argument("--remote", action="store_true")
    p.add_argument("--smoke", action="store_true")
    p = sub.add_parser("score")
    for k in ("config", "bundle", "run", "output"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS))
    p.add_argument("--case-ids", nargs="+")
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=1)
    p = sub.add_parser("judge")
    for k in ("config", "bundle", "run", "output", "key-file"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS))
    p.add_argument("--case-ids", nargs="+")
    p.add_argument("--workers", type=int, default=4)
    p = sub.add_parser("report")
    for k in ("bundle", "run", "scores", "output"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS))
    p.add_argument("--case-ids", nargs="+")
    args = vars(parser.parse_args())
    command = args.pop("command")
    if command == "prepare":
        from .data import prepare
        result = prepare(**args)
        print(json.dumps({"cases": len(result["cases"]), "digest": result["digest"]}))
    elif command == "worker":
        from .worker import run
        gpu_guard(args.pop("remote"))
        args["config_path"] = args.pop("config")
        args["case_ids"] = args["case_ids"] or [x["case_id"] for x in load_bundle(args["bundle"])["cases"]]
        result = run(**args)
        print(json.dumps(result), flush=True)
        # Model failures are terminal data. Infrastructure/unknown states stop the schedule.
        raise SystemExit(2 if any(result.get(k) for k in ("fatal", "unknown", "missing_previous")) else 0)
    elif command == "run":
        from .launch import launch
        raise SystemExit(launch(**args))
    elif command == "score":
        from .score import score
        score(**args)
    elif command == "judge":
        from .judge import judge
        judge(**args)
    else:
        from .report import report
        report(**args)


if __name__ == "__main__":
    main()
