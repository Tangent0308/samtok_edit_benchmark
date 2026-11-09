"""Freeze/run additional baselines on the unchanged 20261109 validation cohort."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    q = sub.add_parser("prepare")
    q.add_argument("--parent", required=True)
    q.add_argument("--control", required=True)
    q = sub.add_parser("run")
    q.add_argument("--control", required=True)
    q.add_argument("--attempt", required=True)
    args = vars(p.parse_args())
    if args.pop("action") == "prepare":
        from samtok_benchmark.external_compare.plan import prepare

        result = prepare(**args)
        print(
            json.dumps(
                {"digest": result["digest"], "new_requests": result["new_generation_requests"]}
            )
        )
    else:
        from samtok_benchmark.external_compare.runner import run

        run(**args, gpus=list(map(str, range(8))))


if __name__ == "__main__":
    main()
