#!/usr/bin/env python3
"""Find cases where every evaluated method struggles across input settings.

This script creates candidates for manual review. Judge scores are not treated as
human ground truth, so its output deliberately keeps several nested thresholds.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from evaluation.common import atomic_write_json


METHODS = ("qwen", "flux", "qwen21", "replan_qwen", "replan_flux")
SETTINGS = ("text_only", "mask_annotation", "box_annotation", "point_annotation")
AXES = ("edit", "preservation", "quality")


def is_strict_success(record: dict) -> bool:
    scores = record.get("scores", {})
    return (
        scores.get("edit") == 4
        and scores.get("preservation") is not None
        and scores["preservation"] >= 3
        and scores.get("quality") is not None
        and scores["quality"] >= 3
    )


def summarize_case(records: list[dict]) -> dict:
    sample = records[0]["sample"]
    usable = [
        record for record in records
        if record.get("status") == "ok"
        and all(record.get("scores", {}).get(axis) is not None for axis in AXES)
    ]
    edits = [record["scores"]["edit"] for record in usable]
    method_best_edit = {}
    for method in METHODS:
        values = [
            record["scores"]["edit"] for record in usable
            if record["sample"]["method"] == method
        ]
        method_best_edit[method] = max(values) if values else None
    method_strict_successes = {
        method: sum(
            is_strict_success(record) for record in usable
            if record["sample"]["method"] == method
        )
        for method in METHODS
    }
    setting_best_edit = {}
    for setting in SETTINGS:
        values = [
            record["scores"]["edit"] for record in usable
            if record["sample"]["setting"] == setting
        ]
        setting_best_edit[setting] = max(values) if values else None
    strict_outputs = [
        {
            "method": record["sample"]["method"],
            "setting": record["sample"]["setting"],
            "scores": {axis: record["scores"][axis] for axis in AXES},
        }
        for record in usable
        if is_strict_success(record)
    ]
    strict_outputs.sort(key=lambda item: (
        METHODS.index(item["method"]), SETTINGS.index(item["setting"])
    ))
    return {
        "eval_index": sample["eval_index"],
        "case_id": sample["case_id"],
        "source_dataset": sample["source_dataset"],
        "edit_type": sample["edit_type"],
        "region_count": len(sample["regions"]),
        "instruction": sample["instruction"],
        "records": len(records),
        "usable_records": len(usable),
        "status": dict(Counter(record["status"] for record in records)),
        "edit_mean": sum(edits) / len(edits) if edits else None,
        "edit_max": max(edits) if edits else None,
        "edit_successes": sum(score == 4 for score in edits),
        "strict_successes": sum(is_strict_success(record) for record in usable),
        "method_best_edit": method_best_edit,
        "method_strict_successes": method_strict_successes,
        "setting_best_edit": setting_best_edit,
        "strict_outputs": strict_outputs,
    }


def select(rows: list[dict]) -> dict[str, object]:
    valid = [row for row in rows if row["usable_records"] == len(METHODS) * len(SETTINGS)]
    concentrated_methods = [
        row["eval_index"] for row in valid
        if row["strict_successes"] >= 5
        and sum(value > 0 for value in row["method_strict_successes"].values()) <= 2
    ]
    concentrated_setting = [
        row["eval_index"] for row in valid
        if row["strict_successes"] >= 5
        and len({item["setting"] for item in row["strict_outputs"]}) == 1
    ]
    return {
        "all_20_edit_at_most_1": [
            row["eval_index"] for row in valid if row["edit_max"] <= 1
        ],
        "all_20_edit_at_most_2": [
            row["eval_index"] for row in valid if row["edit_max"] <= 2
        ],
        "no_edit_success": [
            row["eval_index"] for row in valid if row["edit_successes"] == 0
        ],
        "no_strict_success": [
            row["eval_index"] for row in valid if row["strict_successes"] == 0
        ],
        "at_most_1_strict_success": [
            row["eval_index"] for row in valid if row["strict_successes"] <= 1
        ],
        "at_most_2_strict_successes": [
            row["eval_index"] for row in valid if row["strict_successes"] <= 2
        ],
        "at_most_3_strict_successes": [
            row["eval_index"] for row in valid if row["strict_successes"] <= 3
        ],
        "at_most_4_strict_successes": [
            row["eval_index"] for row in valid if row["strict_successes"] <= 4
        ],
        "strict_at_least_5_in_at_most_2_methods": concentrated_methods,
        "strict_at_least_5_in_one_setting": concentrated_setting,
        "high_risk_concentrated_strict_success": sorted(set(
            concentrated_methods + concentrated_setting
        )),
        "shared_setting_edit_at_most_1": {
            setting: [
                row["eval_index"] for row in valid
                if row["setting_best_edit"][setting] <= 1
            ]
            for setting in SETTINGS
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    config = json.loads((args.run / "config.rank0.json").read_text())
    paths = sorted((args.run / "records").glob("*.json"))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        loaded = pool.map(lambda path: json.loads(path.read_text()), paths)
        records = []
        for record in loaded:
            if record["run_id"] == config["run_id"] and record["variant"] == "pair_v2":
                records.append(record)
    expected = set(config["selected_sample_ids"])
    actual = {record["sample_id"] for record in records}
    if actual != expected or len(actual) != len(records):
        raise ValueError("Common-failure audit requires complete, unique judge records")
    grouped = defaultdict(list)
    for record in records:
        grouped[record["sample"]["eval_index"]].append(record)
    rows = [summarize_case(grouped[index]) for index in sorted(grouped)]
    result = {
        "run_id": config["run_id"],
        "definitions": {
            "edit_success": "E=4",
            "strict_success": "E=4 and P>=3 and Q>=3",
            "candidate_warning": "Candidates require manual image review; judge scores are not human ground truth.",
        },
        "coverage": {
            "cases": len(rows),
            "records": len(records),
            "methods": list(METHODS),
            "settings": list(SETTINGS),
            "strict_success_distribution": dict(sorted(Counter(
                row["strict_successes"] for row in rows
            ).items())),
        },
        "candidates": select(rows),
        "cases": rows,
    }
    atomic_write_json(args.output, result)
    print(json.dumps({
        "coverage": result["coverage"],
        "candidate_counts": {
            key: ({name: len(values) for name, values in value.items()}
                  if isinstance(value, dict) else len(value))
            for key, value in result["candidates"].items()
        },
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
