"""Verify and summarize the fixed-cohort comparison; CPU only, no new scoring calls."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from samtok_benchmark.external_compare.report import run

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--control", required=True)
    p.add_argument("--attempt", required=True)
    run(**vars(p.parse_args()))
