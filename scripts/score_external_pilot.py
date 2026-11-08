"""Isolated entrypoint for the unchanged branch-specific official scorer."""
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
if len(sys.argv) < 2 or sys.argv[1] not in {
    "gie", "compbench", "complexbench_edit", "interedit", "complex_edit", "gedit", "omni_iie", "gide"
}:
    raise SystemExit("First argument must name the benchmark")
benchmark = sys.argv.pop(1)
runpy.run_module("samtok_benchmark.external_" + benchmark + ".score", run_name="__main__")
