#!/usr/bin/env python3
"""Validate the selected manifest and optional review-sheet index."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image

from select_candidates import QUOTAS


BASE = Path("/opt/tiger/tanyue/finegrained_edit_benchmark_selection/output")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=BASE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = args.output / "selected_500.jsonl"
    records = [json.loads(line) for line in manifest.read_text().splitlines() if line.strip()]
    errors: list[str] = []
    if len(records) != 500:
        errors.append(f"expected 500 records, found {len(records)}")
    ids = [x["candidate_id"] for x in records]
    if len(ids) != len(set(ids)):
        errors.append("candidate_id values are not unique")
    if [x["selection_index"] for x in records] != list(range(len(records))):
        errors.append("selection_index is not contiguous")
    groups = Counter((x["source_dataset"], x["edit_type"]) for x in records)
    if groups != Counter(QUOTAS):
        errors.append(f"quota mismatch: {groups}")
    small = sum(0.003 <= x["mask_area_ratio"] < 0.02 for x in records)
    if small < 125:
        errors.append(f"small target quota missed: {small}/125")
    multi_target = sum(x["multi_target"] for x in records)
    if not 60 <= multi_target <= 100:
        errors.append(f"multi-target share outside expected range: {multi_target}/500")
    same_class_proxy = sum(x["same_class_multi_instance_proxy"] for x in records)
    if same_class_proxy < 250:
        errors.append(f"same-class proxy quota missed: {same_class_proxy}/250")
    for record in records:
        if record["source_dataset"] in {"CompBench", "HumanEdit"}:
            if not record["strict_eligible"] or record["review_flags"]:
                errors.append(f"GT-backed candidate is not strict: {record['candidate_id']}")
            if record["changed_pixel_inside_ratio"] < 0.80:
                errors.append(f"changed-pixel locality failed: {record['candidate_id']}")
            if record["diff_mass_inside_ratio"] < 0.40:
                errors.append(f"difference-mass locality failed: {record['candidate_id']}")
        if record["source_dataset"] == "HumanEdit" and record["mask_flag"] != 1:
            errors.append(f"HumanEdit MASK != 1: {record['candidate_id']}")
        shard = Path(record["source_shard"])
        if not shard.is_file():
            errors.append(f"missing source shard: {shard}")
        elif shard.suffix == ".parquet":
            rows = pq.ParquetFile(shard).metadata.num_rows
            if not 0 <= int(record["source_row"]) < rows:
                errors.append(f"source row out of range: {record['candidate_id']}")
        if record["source_dataset"] == "ReShapeBench":
            if not Path(record["source_image_path"]).is_file() or not Path(record["source_mask_path"]).is_file():
                errors.append(f"missing ReShape asset: {record['candidate_id']}")
    csv_rows = list(csv.DictReader((args.output / "selected_500.csv").open(encoding="utf-8")))
    if len(csv_rows) != len(records):
        errors.append(f"CSV row mismatch: {len(csv_rows)}")
    elif [x["candidate_id"] for x in csv_rows] != ids:
        errors.append("CSV candidate order/content does not match JSONL")
    review_rows = list(csv.DictReader((args.output / "human_review_template.csv").open(encoding="utf-8")))
    if [x["candidate_id"] for x in review_rows] != ids:
        errors.append("human review template does not match JSONL")
    review_index = args.output / "review_sheets" / "review_sheet_index.csv"
    if review_index.is_file():
        index_rows = list(csv.DictReader(review_index.open(encoding="utf-8")))
        if Counter(x["candidate_id"] for x in index_rows) != Counter(ids):
            errors.append("review sheet index does not cover selected manifest exactly once")
        for filename in {x["sheet"] for x in index_rows}:
            sheet = review_index.parent / filename
            if not sheet.is_file():
                errors.append(f"missing review sheet: {filename}")
            else:
                with Image.open(sheet) as image:
                    image.verify()
    if errors:
        print(json.dumps({"status": "failed", "errors": errors}, indent=2, ensure_ascii=False))
        raise SystemExit(1)
    report = {
        "status": "passed", "records": len(records), "small_targets": small,
        "strict_gt_backed": sum(x["strict_eligible"] for x in records if x["has_gt_image"]),
        "review_required": sum(bool(x["review_flags"]) for x in records),
        "unique_source_images": len({x["source_group_id"] for x in records}),
        "unique_scene_groups": len({x["scene_group_id"] for x in records}),
        "multi_target": multi_target, "same_class_proxy": same_class_proxy,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
