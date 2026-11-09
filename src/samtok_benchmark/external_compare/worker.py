"""Authorized local wrapper; native inputs, calls and immutable receipts remain frozen."""

import argparse
import json
from pathlib import Path

from samtok_benchmark.external_full.worker import run
from samtok_benchmark.external_pair.worker import guard
from . import MODELS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("bundle", "config-path", "output"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--stage", choices=("plan", "edit"), required=True)
    parser.add_argument("--case-ids", nargs="+", required=True)
    args = vars(parser.parse_args())
    if any(
        not (Path(args["output"]) / args["model"] / args["stage"] / cid / "result.json").exists()
        for cid in args["case_ids"]
    ):
        guard()
    result = run(**args)
    print(json.dumps(result), flush=True)
    raise SystemExit(
        2 if any(result.get(k) for k in ("fatal", "unknown", "missing_previous", "stopped")) else 0
    )


if __name__ == "__main__":
    main()
