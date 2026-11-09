"""Wait for final paired reports, then render all effect plots without using a GPU."""

import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from plot_external_pair import run as plot
from samtok_benchmark.external_full.coordination import read_retry
from samtok_benchmark.external_full.data import immutable
from samtok_benchmark.io import sha256_file


def main(control):
    control = Path(control)
    evidence = control / "plots"
    evidence.mkdir(exist_ok=False)
    immutable(evidence / "OWNER.json", {"pid": os.getpid(), "script_sha256": sha256_file(__file__)})
    try:
        while True:
            failure = control / "analysis/local001-v2/FAILED.json"
            if failure.exists():
                raise RuntimeError("Paired statistics stopped; inspect before plotting")
            summary = read_retry(control / "SUMMARY.json")
            if summary:
                break
            time.sleep(30)
        outputs = []
        for item in summary["reports"]:
            if sha256_file(item["path"]) != item["sha256"]:
                raise ValueError("Final report changed")
            output = (
                Path("/opt/tiger/tanyue/visualization_tmp/ExternalValidation_20261109")
                / item["benchmark"]
            )
            plot(item["path"], output)
            outputs.append(str(output / "PAIRED_EFFECTS.png"))
        immutable(
            evidence / "DONE.json",
            {"summary_sha256": sha256_file(control / "SUMMARY.json"), "plots": outputs},
        )
        print(json.dumps({"completed_plots": outputs}), flush=True)
    except BaseException as error:
        immutable(evidence / "FAILED.json", {"error": repr(error)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", required=True)
    main(**vars(parser.parse_args()))
