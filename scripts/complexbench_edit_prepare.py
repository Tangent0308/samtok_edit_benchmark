"""Isolated official data parser: python -I scripts/complexbench_edit_prepare.py."""
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
runpy.run_module("samtok_benchmark.external_complexbench_edit.data", run_name="__main__")
