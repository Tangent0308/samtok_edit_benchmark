#!/usr/bin/env python3
"""Isolated entry for the two authorized classic MagicBrush additions."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from samtok_benchmark.external_magicbrush_classic.cli import main

if __name__ == "__main__":
    main()
