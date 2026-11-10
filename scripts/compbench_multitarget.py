#!/usr/bin/env python3
"""Prepare/run the isolated SITEdit multi-target correction; no paid API calls."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    for key in ("package", "control", "results-root"):
        p.add_argument("--" + key, required=True)
    p = sub.add_parser("run")
    for key in ("control", "attempt", "scratch-root"):
        p.add_argument("--" + key, required=True)
    p.add_argument("--gpus", nargs="+", default=["4", "5", "6", "7"])
    for stage in ("tokens", "edit", "score"):
        p = sub.add_parser(stage)
        for key in ("control", "output"):
            p.add_argument("--" + key, required=True)
        p.add_argument("--case-ids", nargs="+", required=True)
        if stage == "score":
            p.add_argument("--run", required=True)
    p = sub.add_parser("report")
    for key in ("control", "results-root", "output"):
        p.add_argument("--" + key, required=True)
    args = vars(parser.parse_args())
    command = args.pop("command")
    if command == "prepare":
        from samtok_benchmark.external_compbench.multitarget.plan import prepare

        result = prepare(**args)
        print(json.dumps({"plan_digest": result["digest"], "cases": len(result["case_ids"])}))
    elif command == "run":
        from samtok_benchmark.external_compbench.multitarget.runner import run

        print(json.dumps(run(**args)))
    elif command in ("tokens", "edit"):
        from samtok_benchmark.external_compbench.multitarget.worker import run

        result = run(stage=command, **args)
        print(json.dumps(result), flush=True)
        raise SystemExit(
            2
            if any(result.get(k) for k in ("fatal", "unknown", "missing_previous", "stopped"))
            else 0
        )
    elif command == "score":
        from samtok_benchmark.external_compbench.multitarget.worker import score

        score(**args)
    else:
        from samtok_benchmark.external_compbench.multitarget.report import report

        result = report(**args)
        print(
            json.dumps({"models": result["models"], "replaced": len(result["replaced_case_ids"])})
        )


if __name__ == "__main__":
    main()
