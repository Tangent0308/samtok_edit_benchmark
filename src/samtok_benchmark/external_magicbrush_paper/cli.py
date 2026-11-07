"""CPU preparation, bounded smoke, native generation, frozen scoring and full reporting."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for command in ("prepare", "worker", "launch", "supervise", "score", "estimate", "report"):
        item = sub.add_parser(command)
        item.add_argument("--output", type=Path, required=True)
        if command == "prepare":
            item.add_argument("--smoke", action="store_true")
        if command in ("worker", "score"):
            item.add_argument("--shard", type=int, default=0)
            item.add_argument("--shards", type=int, default=1)
        if command == "worker":
            item.add_argument("--model", choices=("instructpix2pix_magicbrush",), required=True)
        if command in ("launch", "supervise"):
            item.add_argument("--gpus", required=True)
            item.add_argument("--attempt", required=True)
        if command == "launch":
            item.add_argument("--estimate", type=Path)
        if command == "score":
            item.add_argument("--cache", type=Path, required=True)
            item.add_argument("--device", default="cuda")
    args = parser.parse_args()
    if args.action == "prepare":
        from .common import prepare

        result = prepare(args.output, smoke=args.smoke)
        result = {
            "scope": result["scope"],
            "models": result["models"],
            "requests_per_method": result["requests_per_method"],
        }
    elif args.action == "worker":
        from .run import worker

        result = worker(args.output, args.model, args.shard, args.shards)
    elif args.action == "launch":
        from .run import launch

        result = launch(
            args.output,
            [int(x) for x in args.gpus.split(",")],
            args.attempt,
            estimate_path=args.estimate,
        )
    elif args.action == "supervise":
        from .supervise import supervise

        result = supervise(args.output, [int(x) for x in args.gpus.split(",")], args.attempt)
    elif args.action == "score":
        from .common import load_run
        from samtok_benchmark.external_magicbrush.scoring import score

        load_run(args.output)
        # Frozen scorer visits both track keys; only the authorized mask-free keys have generations.
        result = score(
            args.output,
            args.output / "CONFIG.json",
            args.cache,
            args.device,
            args.shard,
            args.shards,
        )
    else:
        from .report import estimate, report

        result = estimate(args.output) if args.action == "estimate" else report(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
