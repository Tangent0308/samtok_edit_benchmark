#!/usr/bin/env python3
"""Entry for the isolated IF-Bench inference cost experiment."""

from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    for key in ("bundle", "sit-run", "method-source", "destination"):
        prepare.add_argument("--" + key, required=True)
    control = sub.add_parser("control")
    for key in ("plan", "output", "runtime", "attempt"):
        control.add_argument("--" + key, required=True)
    control.add_argument("--validate-only", action="store_true")
    control.add_argument("--smoke-only", action="store_true")
    worker = sub.add_parser("worker")
    for key in ("plan", "output", "phase-root", "model", "stage", "setting"):
        worker.add_argument("--" + key, required=True)
    worker.add_argument("--shard", type=int, required=True)
    worker.add_argument("--smoke", action="store_true")
    report = sub.add_parser("report")
    report.add_argument("--plan", required=True)
    report.add_argument("--output", required=True)
    a = p.parse_args()
    options = vars(a)
    command = options.pop("command")
    if command == "prepare":
        from samtok_benchmark.inference_cost.prepare import prepare

        result = prepare(**options)
        print(result["digest"])
    elif command == "worker":
        from samtok_benchmark.inference_cost.worker import run

        run(**options)
    elif command == "control":
        from samtok_benchmark.inference_cost.control import run

        run(**options)
    else:
        from samtok_benchmark.inference_cost.report import report

        report(**options)


if __name__ == "__main__":
    main()
