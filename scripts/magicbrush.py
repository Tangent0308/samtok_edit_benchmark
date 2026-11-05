#!/usr/bin/env python3
"""Isolated entry. Use python -I; only explicitly trusted source roots are added."""

from pathlib import Path
import sys

if not sys.flags.isolated:
    raise SystemExit("Use python -I scripts/magicbrush.py ...")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from samtok_benchmark.external_magicbrush.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
