#!/usr/bin/env python3
"""Isolated entry for the authorized MagicBrush paper-checkpoint addition."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from samtok_benchmark.external_magicbrush_paper.cli import main

if __name__ == "__main__":
    main()
