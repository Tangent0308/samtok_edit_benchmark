#!/usr/bin/env python3
"""Create a 500-case v1 selection emphasizing precise multi-instance edits.

The policy is intentionally explicit and deterministic:

1. Include every strictly eligible CompBench multi-object add/remove case.
2. Remove HumanEdit counting cases that cannot be expressed with region-only input.
3. Remove one redundant ReShapeBench target variant for every repeated source/region.
4. Remove the largest remaining single-target regions until the total returns to 500.

The released-source feature manifest is immutable; this script writes a new v1
selection and a complete add/remove audit report.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_FEATURES = REPO_ROOT / "output" / "all_preselection_features.jsonl"
DEFAULT_V0_SELECTION = REPO_ROOT / "output" / "selected_500.jsonl"
DEFAULT_V0_BENCHMARK = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v0"
)
DEFAULT_V1_BENCHMARK = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v1"
)
DEFAULT_OUTPUT = REPO_ROOT / "output" / "selected_500_multi_instance_v1.jsonl"
DEFAULT_REPORT = REPO_ROOT / "output" / "multi_instance_rebalance_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--v0-selection", type=Path, default=DEFAULT_V0_SELECTION)
    parser.add_argument("--v0-benchmark", type=Path, default=DEFAULT_V0_BENCHMARK)
    parser.add_argument("--v1-benchmark", type=Path, default=DEFAULT_V1_BENCHMARK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    temp.replace(path)


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fields = [
        "selection_index",
        "candidate_id",
        "source_dataset",
        "source_split",
        "edit_type",
        "source_record_id",
        "instruction_original",
        "local_caption",
        "mask_area_ratio",
        "mask_components",
        "diff_mass_inside_ratio",
        "changed_pixel_inside_ratio",
        "small_target",
        "multi_target",
        "multi_object_scene",
        "same_class_multi_instance_proxy",
        "strict_eligible",
        "review_flags",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = dict(record)
            row["review_flags"] = "|".join(row["review_flags"])
            writer.writerow(row)


def final_mask_areas(benchmark_root: Path) -> dict[str, float]:
    areas: dict[str, float] = {}
    for record in read_jsonl(benchmark_root / "benchmark.jsonl"):
        masks = [
            np.asarray(Image.open(benchmark_root / region["mask"]).convert("L")) > 0
            for region in record["regions"]
        ]
        areas[record["id"]] = float(np.logical_or.reduce(masks).mean())
    return areas


def raw_group_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter((x["source_dataset"], x["edit_type"]) for x in records)
    return {f"{dataset}/{edit_type}": count for (dataset, edit_type), count in sorted(counts.items())}


def normalized_edit_type(record: dict[str, Any]) -> str:
    if record["edit_type"] == "multi_object_add":
        return "add"
    if record["edit_type"] == "multi_object_remove":
        return "remove"
    if record["source_dataset"] == "ReShapeBench":
        return "replace"
    return record["edit_type"]


def summary(records: list[dict[str, Any]], areas: dict[str, float]) -> dict[str, Any]:
    values = np.asarray([areas[x["candidate_id"]] for x in records], dtype=np.float64)
    return {
        "records": len(records),
        "counts_by_dataset": dict(sorted(Counter(x["source_dataset"] for x in records).items())),
        "counts_by_source_group": raw_group_counts(records),
        "counts_by_normalized_edit_type": dict(
            sorted(Counter(normalized_edit_type(x) for x in records).items())
        ),
        "strict_eligible": sum(bool(x["strict_eligible"]) for x in records),
        "unique_source_images": len({x["source_group_id"] for x in records}),
        "explicit_multi_instance_cases": sum(
            x["source_dataset"] == "CompBench" and x["edit_type"].startswith("multi_object")
            for x in records
        ),
        "explicit_multi_instance_fraction": sum(
            x["source_dataset"] == "CompBench" and x["edit_type"].startswith("multi_object")
            for x in records
        )
        / len(records),
        "small_target_count_final_mask_lt_2pct": int((values < 0.02).sum()),
        "small_target_fraction_final_mask_lt_2pct": float((values < 0.02).mean()),
        "region_area_le_10pct_count": int((values <= 0.10).sum()),
        "region_area_gt_20pct_count": int((values > 0.20).sum()),
        "region_area_quantiles": {
            str(q): float(np.quantile(values, q)) for q in (0.0, 0.25, 0.5, 0.75, 0.9, 1.0)
        },
    }


def main() -> None:
    args = parse_args()
    features = read_jsonl(args.features)
    selected_v0 = read_jsonl(args.v0_selection)
    if len(selected_v0) != 500:
        raise ValueError(f"expected 500 v0 cases, found {len(selected_v0)}")
    areas_v0 = final_mask_areas(args.v0_benchmark)
    if set(areas_v0) != {x["candidate_id"] for x in selected_v0}:
        raise ValueError("v0 compact benchmark and construction selection IDs differ")

    selected_ids = {x["candidate_id"] for x in selected_v0}
    additions = [
        x
        for x in features
        if x["candidate_id"] not in selected_ids
        and x["source_dataset"] == "CompBench"
        and x["edit_type"] in {"multi_object_add", "multi_object_remove"}
        and x["strict_eligible"]
    ]
    additions.sort(key=lambda x: x["candidate_id"])
    if len(additions) != 56:
        raise ValueError(f"expected 56 strict multi-instance additions, found {len(additions)}")

    removal_reason: dict[str, str] = {}
    for record in selected_v0:
        if record["source_dataset"] == "HumanEdit" and record["edit_type"] == "counting":
            removal_reason[record["candidate_id"]] = "non_local_counting_without_region_only_instruction"

    reshape_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in selected_v0:
        if record["source_dataset"] == "ReShapeBench":
            reshape_groups[record["source_group_id"]].append(record)
    for group in reshape_groups.values():
        if len(group) <= 1:
            continue
        # The variants have the same source and region. Keep the more concise target,
        # which is generally easier to score consistently with text-based metrics.
        ranked = sorted(group, key=lambda x: (len(x["local_caption"]), x["candidate_id"]))
        for record in ranked[1:]:
            removal_reason[record["candidate_id"]] = "redundant_reshape_source_region_variant"

    remaining_needed = len(additions) - len(removal_reason)
    if remaining_needed < 0:
        raise ValueError("mandatory removals exceed the number of additions")
    coarse_pool = [
        x
        for x in selected_v0
        if x["candidate_id"] not in removal_reason
        and not (
            x["source_dataset"] == "CompBench"
            and x["edit_type"] in {"multi_object_add", "multi_object_remove"}
        )
    ]
    coarse_pool.sort(key=lambda x: (-areas_v0[x["candidate_id"]], x["candidate_id"]))
    for record in coarse_pool[:remaining_needed]:
        removal_reason[record["candidate_id"]] = "largest_remaining_single_target_region"

    if len(removal_reason) != len(additions):
        raise ValueError(f"replacement mismatch: remove={len(removal_reason)} add={len(additions)}")

    retained = [x for x in selected_v0 if x["candidate_id"] not in removal_reason]
    selected_v1 = retained + additions
    selected_v1.sort(key=lambda x: (x["source_dataset"], x["edit_type"], x["candidate_id"]))
    for index, record in enumerate(selected_v1):
        record["selection_index"] = index
        record["selection_version"] = "multi-instance-v1-20260907"
        record["human_review_status"] = "pending"
        record["sam2_status"] = (
            "pending" if record["source_dataset"] == "ReShapeBench" else "not_required"
        )
    if len(selected_v1) != 500 or len({x["candidate_id"] for x in selected_v1}) != 500:
        raise ValueError("v1 selection is not exactly 500 unique cases")
    explicit_multi = [
        x
        for x in selected_v1
        if x["source_dataset"] == "CompBench"
        and x["edit_type"] in {"multi_object_add", "multi_object_remove"}
    ]
    if len(explicit_multi) != 116 or not all(x["strict_eligible"] for x in explicit_multi):
        raise ValueError("v1 does not contain all 116 strict CompBench multi-instance cases")

    areas_v1 = {
        **{case_id: area for case_id, area in areas_v0.items() if case_id not in removal_reason},
        **{x["candidate_id"]: float(x["mask_area_ratio"]) for x in additions},
    }
    report = {
        "policy_version": "multi-instance-v1-20260907",
        "selection_input": str(args.v0_selection),
        "feature_input": str(args.features),
        "added_count": len(additions),
        "removed_count": len(removal_reason),
        "added_ids": [x["candidate_id"] for x in additions],
        "removed": [
            {
                "id": x["candidate_id"],
                "reason": removal_reason[x["candidate_id"]],
                "source_dataset": x["source_dataset"],
                "edit_type": x["edit_type"],
                "final_region_area_ratio": areas_v0[x["candidate_id"]],
            }
            for x in selected_v0
            if x["candidate_id"] in removal_reason
        ],
        "removal_reason_counts": dict(sorted(Counter(removal_reason.values()).items())),
        "before": summary(selected_v0, areas_v0),
        "after_projected": summary(selected_v1, areas_v1),
        "notes": [
            "Projected v1 areas use released CompBench union masks for new cases; these are the final union areas.",
            "Small target means the union of input regions occupies less than 2% of the source image.",
            "ReShape duplicate removals preserve one target instruction for every retained source/region.",
        ],
    }
    if (args.v1_benchmark / "benchmark.jsonl").is_file():
        areas_v1_actual = final_mask_areas(args.v1_benchmark)
        if set(areas_v1_actual) != {x["candidate_id"] for x in selected_v1}:
            raise ValueError("v1 compact benchmark and rebalanced selection IDs differ")
        report["after_actual"] = summary(selected_v1, areas_v1_actual)

    write_jsonl(args.output, selected_v1)
    write_csv(args.output.with_suffix(".csv"), selected_v1)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report.get("after_actual", report["after_projected"]), indent=2, ensure_ascii=False))
    print(f"selection: {args.output}")
    print(f"report: {args.report}")


if __name__ == "__main__":
    main()
