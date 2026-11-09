"""Local eight-GPU authorization boundary around the unchanged scientific worker."""

import argparse
import json
import os
import subprocess

from samtok_benchmark.external_full.worker import run
from . import MODELS


def guard():
    gpu = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if gpu not in tuple(map(str, range(8))):
        raise RuntimeError("Exactly one locally authorized GPU 0–7 is required")
    used, total = map(
        int,
        subprocess.check_output(
            [
                "nvidia-smi",
                "--id=" + gpu,
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
        )
        .strip()
        .split(","),
    )
    if used > 2300 or total - used < 70000:
        raise RuntimeError(
            f"GPU {gpu} is occupied ({used} MiB); existing processes will not be touched"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("bundle", "config-path", "output"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--stage", choices=("tokens", "edit"), required=True)
    parser.add_argument("--case-ids", nargs="+", required=True)
    args = vars(parser.parse_args())
    guard()
    result = run(**args)
    print(json.dumps(result), flush=True)
    raise SystemExit(
        2 if any(result.get(k) for k in ("fatal", "unknown", "missing_previous", "stopped")) else 0
    )


if __name__ == "__main__":
    main()
