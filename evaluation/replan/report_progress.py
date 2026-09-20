#!/usr/bin/env python3
"""Summarize RePlan SAMTok output counts while eight workers are running."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from .runner import OUTPUT_ROOT, SETTINGS, write_json
else:
    from runner import OUTPUT_ROOT, SETTINGS, write_json


MODELS = ("qwen2511", "flux2_klein4b")


def snapshot(root: Path) -> dict:
    counts = {}
    latest_path = None
    for model in MODELS:
        counts[model] = {}
        for setting in SETTINGS:
            files = list((root / "inference" / model / setting).glob("[0-9][0-9][0-9][0-9].json"))
            counts[model][setting] = len(files)
            candidate = max(files, key=lambda p: p.stat().st_mtime, default=None)
            if candidate and (latest_path is None or candidate.stat().st_mtime > latest_path.stat().st_mtime):
                latest_path = candidate
    completed = sum(sum(settings.values()) for settings in counts.values())
    latest = None
    if latest_path:
        record = json.loads(latest_path.read_text(encoding="utf-8"))
        latest = {key: record[key] for key in ("model", "setting", "eval_index", "worker_rank")}
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "completed": completed,
        "total": 656 * len(SETTINGS) * len(MODELS),
        "counts": counts,
        "latest": latest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--watch", type=float)
    args = parser.parse_args()
    while True:
        progress = snapshot(args.output_root)
        percent = 100 * progress["completed"] / progress["total"]
        print(f"[progress] {progress['timestamp']} {progress['completed']}/{progress['total']} "
              f"({percent:.2f}%) latest={progress['latest']}", flush=True)
        for model, settings in progress["counts"].items():
            print("  " + model + ": " + " ".join(f"{key}={value}/656" for key, value in settings.items()), flush=True)
        write_json(args.output_root / "logs/progress_latest.json", progress)
        if args.watch is None or progress["completed"] == progress["total"]:
            break
        time.sleep(args.watch)


if __name__ == "__main__":
    main()
