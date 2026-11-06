#!/usr/bin/env python3
"""CPU-only post-processing of the final frozen MagicBrush report; use python -I."""

from pathlib import Path
import sys

if not sys.flags.isolated:
    raise SystemExit("Use python -I scripts/magicbrush_failure_report.py ...")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from samtok_benchmark.postprocessing.magicbrush_failures import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
