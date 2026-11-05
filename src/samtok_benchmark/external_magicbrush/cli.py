"""MagicBrush data preparation and evaluation command line."""

import argparse
import json
import os
from pathlib import Path
import sys

from . import MODELS


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ["download", "extract"]:
        p = sub.add_parser(command)
        p.add_argument("--dataset", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--dataset", required=True)
    p.add_argument("--output", required=True)
    p = sub.add_parser("audit")
    p.add_argument("--dataset", required=True)
    p.add_argument("--training-root", required=True)
    p.add_argument("--output", required=True)
    p = sub.add_parser("download-metrics")
    p.add_argument("--config", required=True)
    for command in ["run", "worker"]:
        p = sub.add_parser(command)
        for key in ["bundle", "config", "output"]:
            p.add_argument("--" + key, required=True)
        p.add_argument("--smoke", action="store_true")
        if command == "run":
            p.add_argument("--gpus", required=True)
            p.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS))
            p.add_argument("--attempt", required=True)
            p.add_argument("--cache-dir")
            p.add_argument("--estimate")
        else:
            p.add_argument("--model", choices=MODELS, required=True)
            p.add_argument("--stage", choices=["tokens", "plan", "edit"], required=True)
            p.add_argument("--wave", choices=[-1, 0, 2, 3], type=int, required=True)
            p.add_argument("--sessions", nargs="+", required=True)
    p = sub.add_parser("score")
    for key in ["output", "config", "cache"]:
        p.add_argument("--" + key, required=True)
    p.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=1)
    for command in ["report", "estimate", "preview"]:
        p = sub.add_parser(command)
        p.add_argument("--output", required=True)
        p.add_argument("--destination", required=True)
        if command == "report":
            p.add_argument("--overlap", required=True)
    args = parser.parse_args(argv)
    from .data import download, extract, read

    if args.command in ["download", "extract"]:
        result = download(args.dataset) if args.command == "download" else extract(args.dataset)
    elif args.command == "prepare":
        from .bundle import prepare

        result = prepare(args.dataset, args.output)
    elif args.command == "audit":
        from .overlap import audit

        result = audit(args.dataset, args.training_root, args.output)
    elif args.command == "download-metrics":
        from .metrics import download_weights

        result = download_weights(read(args.config))
    elif args.command == "run":
        from .launch import launch

        result = launch(args)
    elif args.command == "worker":
        if args.model == "sitedit":
            source = Path(read(args.config)["paths"]["sitedit_source"])
            for relative in ["third_party", "third_party/diffsynth", "src"]:
                sys.path.insert(0, str(source / relative))
        # Native code gets no dataset import path or PYTHONPATH inherited from a job shell.
        os.environ.pop("PYTHONPATH", None)
        from .worker import run_stage

        result = run_stage(
            args.bundle,
            args.config,
            args.output,
            args.model,
            args.stage,
            args.sessions,
            args.wave,
            args.smoke,
        )
    elif args.command == "score":
        from .scoring import score

        result = score(args.output, args.config, args.cache, args.device, args.shard, args.shards)
    elif args.command == "report":
        from .report import report

        result = report(args.output, args.overlap, args.destination)
    elif args.command == "estimate":
        from .report import estimate

        result = estimate(args.output, args.destination)
    else:
        from .preview import preview

        result = preview(args.output, args.destination)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return (
        2
        if result.get("fatal")
        or result.get("failed_processes")
        or result.get("unknown")
        or result.get("pending_dependency")
        else 0
    )
