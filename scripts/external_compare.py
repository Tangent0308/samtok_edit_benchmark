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
    q.add_argument("--execution")
    q = sub.add_parser("execution")
    for key in ("control", "output", "reason"):
        q.add_argument("--" + key, required=True)
    q.add_argument("--gpus", nargs="+", required=True)
    args = vars(p.parse_args())
    action = args.pop("action")
    if action == "prepare":
        from samtok_benchmark.external_compare.plan import prepare

        result = prepare(**args)
        print(
            json.dumps(
                {"digest": result["digest"], "new_requests": result["new_generation_requests"]}
            )
        )
    elif action == "execution":
        from samtok_benchmark.external_compare.execution import prepare

        result = prepare(**args)
        print(json.dumps({"execution_digest": result["digest"], "gpus": result["gpus"]}))
    else:
        from samtok_benchmark.external_compare.runner import run

        gpus = (
            json.loads(Path(args["execution"]).read_text())["gpus"]
            if args["execution"]
            else list(map(str, range(8)))
        )
        run(**args, gpus=gpus)


if __name__ == "__main__":
    main()
