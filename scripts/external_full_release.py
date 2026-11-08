"""Explicit coordination release after the operator confirms all four workers stopped."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from samtok_benchmark.external_full.coordination import release_stopped

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    p.add_argument("--attempt", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--confirm-all-workers-stopped", action="store_true")
    a = p.parse_args()
    print(release_stopped(a.output, a.attempt, a.reason, a.confirm_all_workers_stopped))
