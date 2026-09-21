"""Run judge shards on an eight-device pool, using free memory only, never killing other jobs."""
from __future__ import annotations

import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def memory():
    out = subprocess.check_output(["nvidia-smi", "--query-gpu=index,memory.free", "--format=csv,noheader,nounits"], text=True)
    return {int(a): int(b) for a, b in (line.split(",") for line in out.splitlines())}


def log(event, **kwargs):
    print(json.dumps({"time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      "event": event, **kwargs}), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--devices", default="0,1,2,3,4,5,6,7")
    p.add_argument("--variants", nargs="+", required=True)
    p.add_argument("--split", default="dev", choices=["dev", "holdout", "all"])
    p.add_argument("--max-tokens", type=int, default=4096)
    p.add_argument("--max-pixels", type=int, default=1048576)
    p.add_argument("--gallery", action="store_true", help="Render every sample; omit for large full runs")
    args = p.parse_args()
    root = args.run_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    with (root / "launcher.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        code = root / "code"
        if not code.exists():
            (code / "evaluation").mkdir(parents=True)
            package = Path(__file__).resolve().parent.parent
            for filename in ("__init__.py", "common.py"):
                shutil.copy2(package / filename, code / "evaluation" / filename)
            shutil.copytree(package / "metrics", code / "evaluation/metrics", ignore=shutil.ignore_patterns("__pycache__"))
        devices = [int(d) for d in args.devices.split(",")]
        if len(set(devices)) != len(devices):
            raise ValueError("duplicate devices")
        pending = list(range(len(devices)))
        running = {}
        failed = []
        log("start", device_pool=devices, shards=len(pending), policy="free_memory_only_no_process_termination")
        while pending or running:
            for device, (proc, rank, handle) in list(running.items()):
                rc = proc.poll()
                if rc is not None:
                    handle.close()
                    log("shard_done", rank=rank, device=device, exit_code=rc)
                    if rc:
                        failed.append(rank)
                    del running[device]
            free = memory()
            for device in devices:
                if not pending or device in running or free.get(device, 0) < 70000:
                    continue
                rank = pending.pop(0)
                handle = (root / "logs" / f"rank{rank}.gpu{device}.log").open("a")
                command = [sys.executable, "-u", "-m", "evaluation.metrics.runner",
                           "--manifest", str(args.manifest.resolve()), "--output", str(root / args.split),
                           "--rank", str(rank), "--world-size", str(len(devices)), "--split", args.split,
                           "--max-tokens", str(args.max_tokens), "--max-pixels", str(args.max_pixels),
                           "--variants", *args.variants]
                env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(device), OMP_NUM_THREADS="2")
                proc = subprocess.Popen(command, cwd=code, env=env, stdout=handle, stderr=subprocess.STDOUT)
                running[device] = (proc, rank, handle)
                log("shard_started", rank=rank, device=device, pid=proc.pid, free_mib=free[device])
            if pending or running:
                log("progress", pending=pending, active={d: r for d, (_, r, _) in running.items()}, free_mib=free)
                time.sleep(15)
        result = subprocess.run([sys.executable, "-m", "evaluation.metrics.report",
                                 "--manifest", str(args.manifest.resolve()), "--run", str(root / args.split),
                                 "--output", str(root / args.split / "report")]
                                + (["--gallery"] if args.gallery else []), cwd=code)
        log("complete", failed_shards=failed, report_exit=result.returncode)
        sys.exit(1 if failed or result.returncode else 0)


if __name__ == "__main__":
    main()
