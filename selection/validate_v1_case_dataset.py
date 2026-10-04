#!/usr/bin/env python3
"""Validate the instruction-free v1 case catalog and copied assets."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from PIL import Image


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        return image.size


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = root / "benchmark/benchmark.jsonl"
    rows = read_jsonl(manifest)
    ids: set[str] = set()
    source_hashes: set[str] = set()
    source_datasets = Counter()
    releases = Counter()
    edit_types = Counter()
    region_counts = Counter()
    checked_assets = 0

    for index, row in enumerate(rows):
        expected = {
            "id", "original_id", "source_release", "source_dataset", "edit_type",
            "difficulty", "source_image", "evaluation_mask", "regions",
        }
        if set(row) != expected:
            raise ValueError(f"row {index}: schema mismatch {set(row)}")
        if row["id"] in ids:
            raise ValueError(f"row {index}: duplicate id {row['id']}")
        ids.add(row["id"])
        if "instruction" in row or "target" in row:
            raise ValueError(f"row {index}: instruction/target must be omitted")

        source = root / row["source_image"]
        evaluation = root / row["evaluation_mask"]
        source_size = size(source)
        if size(evaluation) != source_size:
            raise ValueError(f"row {index}: evaluation mask geometry mismatch")
        source_hashes.add(sha256(source))
        checked_assets += 2
        for region_index, region in enumerate(row["regions"]):
            if set(region) != {"mask", "box", "point"}:
                raise ValueError(f"row {index} region {region_index}: schema mismatch")
            region_path = root / region["mask"]
            if size(region_path) != source_size:
                raise ValueError(f"row {index} region {region_index}: geometry mismatch")
            checked_assets += 1
        releases[row["source_release"]] += 1
        source_datasets[row["source_dataset"]] += 1
        edit_types[row["edit_type"]] += 1
        region_counts[len(row["regions"])] += 1

    report = {
        "status": "passed",
        "manifest": str(manifest),
        "rows": len(rows),
        "unique_ids": len(ids),
        "unique_source_images": len(source_hashes),
        "checked_assets": checked_assets,
        "source_release_counts": dict(releases),
        "source_dataset_counts": dict(sorted(source_datasets.items())),
        "edit_type_counts": dict(sorted(edit_types.items())),
        "region_count_distribution": dict(sorted(region_counts.items())),
    }
    out = root / "benchmark/validation_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
