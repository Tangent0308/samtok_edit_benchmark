#!/usr/bin/env python3
"""Run with python -I: repository imports are explicit; downloaded files are only data."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from samtok_benchmark.external_compbench.full.cli import main

if __name__ == "__main__":
    main()
