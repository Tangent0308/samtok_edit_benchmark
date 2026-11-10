#!/usr/bin/env python3
"""Apply the authorized CPU-only CompBench Judge syntax-recovery overlay."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("bundle", "original-root", "source-report", "output"):
        parser.add_argument("--" + key, required=True)
    from samtok_benchmark.external_compbench.epq_repair.run import run

    print(json.dumps(run(**vars(parser.parse_args())), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
