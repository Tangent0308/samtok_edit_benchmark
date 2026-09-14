#!/usr/bin/env python3
"""Verify that every materialized region union equals its released source mask."""

from __future__ import annotations

import argparse
import io
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from PIL import Image

from build_unified_benchmark import DEFAULT_OUTPUT, DEFAULT_SELECTION, atomic_text, read_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--benchmark-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "benchmark/source_mask_verification.json",
    )
    return parser.parse_args()


def decode_source_mask(cell: dict, dataset: str) -> np.ndarray:
    with Image.open(io.BytesIO(cell["bytes"])) as image:
        if dataset == "CompBench":
            return np.asarray(image.convert("L")) >= 128
        return np.asarray(image.convert("RGBA").getchannel("A")) < 128


def load_binary_mask(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L")) == 255


def main() -> None:
    args = parse_args()
    selected = read_jsonl(args.selection)
    benchmark = {
        row["id"]: row for row in read_jsonl(args.benchmark_root / "benchmark.jsonl")
    }
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in selected:
        groups[(row["source_dataset"], row["source_shard"])].append(row)

    mismatches = []
    checked = 0
    for (dataset, shard), rows in sorted(groups.items()):
        column = "mask" if dataset == "CompBench" else "MASK_IMG"
        table = pq.read_table(shard, columns=[column])
        for selected_row in rows:
            case_id = selected_row["candidate_id"]
            source = decode_source_mask(
                table[column][int(selected_row["source_row"])].as_py(), dataset
            )
            regions = benchmark[case_id]["regions"]
            materialized = np.logical_or.reduce(
                [
                    load_binary_mask(args.benchmark_root / region["mask"])
                    for region in regions
                ]
            )
            difference = int(np.logical_xor(source, materialized).sum())
            if difference:
                mismatches.append({"id": case_id, "different_pixels": difference})
            checked += 1

    report = {
        "status": "passed" if not mismatches and checked == len(selected) else "failed",
        "checked_cases": checked,
        "expected_cases": len(selected),
        "exact_union_matches": checked - len(mismatches),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "definition": "union(regions[].mask) is pixel-identical to the released parquet mask",
    }
    atomic_text(args.output, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
