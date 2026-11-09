"""Explicitly authorized local paired validation; no changes to published cluster packages."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("prepare")
    a.add_argument("--benchmark", required=True)
    a.add_argument("--repo", required=True)
    a.add_argument("--control")
    a = sub.add_parser("freeze")
    a.add_argument("--repo", required=True)
    a.add_argument("--control", required=True)
    a = sub.add_parser("run")
    a.add_argument("--control", required=True)
    a.add_argument("--attempt", required=True)
    a.add_argument("--gpus", nargs=8, default=list(map(str, range(8))))
    args = vars(p.parse_args())
    command = args.pop("command")
    if command == "prepare":
        from samtok_benchmark.external_pair.selection import prepare

        if args["control"] is None:
            args.pop("control")
        prepare(**args)
    elif command == "freeze":
        from samtok_benchmark.external_pair.selection import freeze_plan

        freeze_plan(**args)
    else:
        from samtok_benchmark.external_pair.runner import run

        run(**args)
