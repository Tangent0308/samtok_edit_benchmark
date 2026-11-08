"""Isolated entry for eight-method external full evaluation."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from samtok_benchmark.external_full.cli import main

if __name__ == "__main__":
    main()
