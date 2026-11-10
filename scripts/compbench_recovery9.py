#!/usr/bin/env python3
"""Explicitly authorized nine-request CompBench repair and re-generation."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    for key in ("parent", "control", "results-root", "selection"):
        p.add_argument("--" + key, required=True)
    p = commands.add_parser("worker")
    for key in ("control", "output"):
        p.add_argument("--" + key, required=True)
    p.add_argument("--stage", choices=("tokens", "edit"), required=True)
    p.add_argument("--case-ids", nargs="+", required=True)
    p = commands.add_parser("score")
    for key in ("control", "run", "output"):
        p.add_argument("--" + key, required=True)
    p.add_argument("--case-ids", nargs="+", required=True)
    p = commands.add_parser("report")
    for key in ("control", "parent-report", "output"):
        p.add_argument("--" + key, required=True)
    p = commands.add_parser("preview")
    for key in ("control", "parent-report", "merged-report", "output"):
        p.add_argument("--" + key, required=True)
    args = vars(parser.parse_args())
    command = args.pop("command")
    if command == "prepare":
        from samtok_benchmark.external_compbench.recovery9.plan import prepare

        result = prepare(**args)
        print(json.dumps({"plan_digest": result["digest"], "cases": len(result["case_ids"])}))
    elif command == "preview":
        from samtok_benchmark.external_compbench.recovery9.preview import render

        print(render(**args))
    elif command == "report":
        from samtok_benchmark.external_compbench.recovery9.report import report

        result = report(**args)
        print(json.dumps({"models": result["models"], "post_hoc": result["post_hoc"]}))
    else:
        from samtok_benchmark.external_compbench.recovery9.worker import run, score

        result = (run if command == "worker" else score)(**args)
        print(json.dumps(result))
        if isinstance(result, dict) and any(
            result.get(k) for k in ("fatal", "unknown", "missing_previous", "stopped")
        ):
            raise SystemExit(2)


if __name__ == "__main__":
    main()
