#!/usr/bin/env python3
"""Prepare, validate and run the isolated CompBench whole-instruction Judge."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--bundle", required=True)
    p.add_argument("--results-root", required=True)
    p = sub.add_parser("publish")
    p.add_argument("--bundle", required=True)
    p.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    p = sub.add_parser("run")
    for key in ("bundle", "output", "attempt"):
        p.add_argument("--" + key, required=True)
    p.add_argument("--model")
    p.add_argument("--smoke", action="store_true")
    p = sub.add_parser("report")
    for key in ("bundle", "output", "destination"):
        p.add_argument("--" + key, required=True)
    p = sub.add_parser("launch")
    p.add_argument("--bundle", required=True)
    p.add_argument("--attempt", required=True)
    p.add_argument("--work", default="/tmp/ifbench/compbench-epq-20261110")
    p.add_argument("--validate-only", action="store_true")
    args = vars(parser.parse_args())
    command = args.pop("command")
    if command in ("prepare", "publish"):
        from samtok_benchmark.external_compbench.vlm_judge import bundle

        result = getattr(bundle, command)(**args)
        if command == "publish":
            result = {k: v for k, v in result.items() if k != "files"}
    elif command == "run":
        from samtok_benchmark.external_compbench.vlm_judge.worker import run

        result = run(**args)
        print(json.dumps(result), flush=True)
        return 0 if result["stage"] == "completed" else 2
    elif command == "report":
        from samtok_benchmark.external_compbench.vlm_judge.report import report

        result = report(**args)
    else:
        from samtok_benchmark.external_compbench.vlm_judge.launch import launch

        return launch(**args)
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
