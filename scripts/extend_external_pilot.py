"""Isolated, reproducible expansion of an existing pilot to about twenty cases."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from samtok_benchmark.external_pilot.extension import COUNTS, build

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=sorted(COUNTS), required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--dataset-output", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.benchmark, args.config, args.root, args.dataset_output), ensure_ascii=False))
