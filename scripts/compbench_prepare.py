"""Isolated data entrypoint: python -I scripts/compbench_prepare.py ..."""

from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
runpy.run_module("samtok_benchmark.external_compbench.data", run_name="__main__")
