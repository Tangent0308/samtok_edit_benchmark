#!/usr/bin/env python3
"""User-authorized GPU 0..7 gate override; immutable inference/scorer module stays unchanged."""

import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from samtok_benchmark.postprocessing import magicbrush_mirage_recovery as recovery


def authorized_gpu_gate():
    value = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if value not in {str(i) for i in range(8)}:
        raise ValueError("Worker must see exactly one local GPU 0..7")
    fields = (
        subprocess.check_output(
            [
                "nvidia-smi",
                "-i",
                value,
                "--query-gpu=memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            text=True,
        )
        .strip()
        .split(",")
    )
    used, free = map(int, fields)
    if used > 2300 or free < 70000:
        raise RuntimeError(f"GPU {value} occupied: {used} MiB; do not stop other processes")


if __name__ == "__main__":
    # Scheduling-only exception authorized 2026-11-11; no model/input/metric mutation.
    recovery.gpu_gate = authorized_gpu_gate
    recovery.main()
