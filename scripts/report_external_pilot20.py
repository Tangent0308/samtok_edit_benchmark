"""Verify and merge the initial and additional pilot results without changing either."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from samtok_benchmark.external_pilot.extension_report import report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("benchmark", "root", "previews", "old-config", "new-config"):
        parser.add_argument("--"+name, required=True)
    parser.add_argument("--doc")
    report(**vars(parser.parse_args()))
