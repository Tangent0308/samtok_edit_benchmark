from pathlib import Path
import sys
import runpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
runpy.run_module("samtok_benchmark.external_gide.data",run_name="__main__")
