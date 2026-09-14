#!/usr/bin/env python3
"""Report live progress for the two-model, four-input baseline inference run."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from common import DEFAULT_EXPERIMENT_ROOT, atomic_write_json


MODELS = ("qwen", "flux2")
SETTINGS = ("text_only", "mask_annotation", "box_annotation", "point_annotation")
EXPECTED_PER_SETTING = 556


def numeric_sidecars(path: Path) -> list[Path]:
    return [item for item in path.glob("*.json") if item.stem.isdigit()]


def snapshot(experiment_root: Path) -> dict:
    counts: dict[str, dict[str, int]] = {}
    latest_path: Path | None = None
    for model in MODELS:
        counts[model] = {}
        for setting in SETTINGS:
            files = numeric_sidecars(experiment_root / "inference" / model / setting)
            counts[model][setting] = len(files)
            candidate = max(files, key=lambda path: path.stat().st_mtime, default=None)
            if candidate is not None and (
                latest_path is None or candidate.stat().st_mtime > latest_path.stat().st_mtime
            ):
                latest_path = candidate
    completed = sum(value for model in counts.values() for value in model.values())
    total = len(MODELS) * len(SETTINGS) * EXPECTED_PER_SETTING
    latest = None
    if latest_path is not None:
        record = json.loads(latest_path.read_text(encoding="utf-8"))
        latest = {
            "model": record["model"],
            "setting": record["setting"],
            "eval_index": record["eval_index"],
            "case_id": record["case_id"],
            "worker_rank": record["worker_rank"],
            "elapsed_seconds": record["elapsed_seconds"],
            "updated_at": datetime.fromtimestamp(
                latest_path.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
        }
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "completed": completed,
        "total": total,
        "percent": round(100 * completed / total, 2),
        "counts": counts,
        "latest": latest,
    }


def format_snapshot(item: dict) -> str:
    latest = item["latest"]
    active = (
        "none"
        if latest is None
        else (
            f"{latest['model']}/{latest['setting']} eval_index={latest['eval_index']:04d} "
            f"rank={latest['worker_rank']}"
        )
    )
    model_parts = []
    for model in MODELS:
        settings = " ".join(
            f"{setting}={item['counts'][model][setting]}/{EXPECTED_PER_SETTING}"
            for setting in SETTINGS
        )
        model_parts.append(f"{model}: {settings}")
    return (
        f"[progress] {item['timestamp']} total={item['completed']}/{item['total']} "
        f"({item['percent']:.2f}%) active={active}\n  " + "\n  ".join(model_parts)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment_root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--watch", type=float, default=None, metavar="SECONDS")
    parser.add_argument("--log", type=Path, default=None)
    args = parser.parse_args()
    if args.watch is not None and args.watch < 5:
        raise ValueError("--watch interval must be at least 5 seconds")
    while True:
        item = snapshot(args.experiment_root)
        message = format_snapshot(item)
        print(message, flush=True)
        atomic_write_json(
            args.experiment_root / "logs/baseline_progress_latest.json", item
        )
        if args.log is not None:
            args.log.parent.mkdir(parents=True, exist_ok=True)
            with args.log.open("a", encoding="utf-8") as handle:
                handle.write(message + "\n")
        if args.watch is None or item["completed"] >= item["total"]:
            return
        time.sleep(args.watch)


if __name__ == "__main__":
    main()
