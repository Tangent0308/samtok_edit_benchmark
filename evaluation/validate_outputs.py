#!/usr/bin/env python3
"""Validate and summarize the complete 15-setting inference output tree."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from common import (
    DEFAULT_DATASET_ROOT,
    DEFAULT_EXPERIMENT_ROOT,
    DEFAULT_PREPARED_MANIFEST,
    atomic_write_json,
    completed_record,
    load_prepared_manifest,
    resolve_path,
    settings_for_model,
    verify_image,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment_root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--prepared_manifest", type=Path, default=DEFAULT_PREPARED_MANIFEST)
    parser.add_argument("--prepared_root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--dataset_root", type=Path, default=DEFAULT_DATASET_ROOT)
    args = parser.parse_args()

    rows, prepared_report = load_prepared_manifest(
        args.prepared_manifest, args.prepared_root
    )
    model_reports = {}
    missing = []
    seeds = Counter()
    total = 0
    source_sizes = {
        row["eval_index"]: verify_image(
            resolve_path(row["source_image"], args.dataset_root)
        )
        for row in rows
    }
    for model in ("qwen", "flux2", "samtok_edit"):
        settings = settings_for_model(model)
        setting_counts = {}
        for setting in settings:
            count = 0
            for row in rows:
                record = completed_record(
                    args.experiment_root,
                    model,
                    setting.key,
                    row["eval_index"],
                    row["id"],
                    source_sizes[row["eval_index"]],
                )
                if record is None:
                    missing.append(f"{model}/{setting.key}/{row['eval_index']:04d}")
                    continue
                seeds[int(record["seed"])] += 1
                count += 1
            setting_counts[setting.key] = count
            total += count
        run_config = args.experiment_root / "inference" / model / "run_config.json"
        report = args.experiment_root / "inference" / model / "report.json"
        if not run_config.is_file() or not report.is_file():
            missing.append(f"{model}/run_config_or_report")
        model_reports[model] = {"settings": setting_counts, "count": sum(setting_counts.values())}

    report = {
        "status": "passed" if not missing and total == 7500 else "failed",
        "protocol": "samtok_finegrained_edit_benchmark_full_output_validation_v1",
        "prepared_data": prepared_report,
        "models": model_reports,
        "total_result_images": total,
        "expected_result_images": 7500,
        "actual_stochastic_generations": 6500,
        "pasteback_derivations": 1000,
        "seed_counts": dict(sorted(seeds.items())),
        "missing_count": len(missing),
        "missing_first_100": missing[:100],
    }
    atomic_write_json(args.experiment_root / "reports/full_inference_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
