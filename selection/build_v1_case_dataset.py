#!/usr/bin/env python3
"""Materialize the instruction-free v1 case catalog and its source/mask assets.

The v1 catalog is a staging benchmark: it contains source images, evaluation
masks, region masks, boxes, points, and provenance, but deliberately omits
editing instructions and target references.  The two inputs are the filtered
150-case subset of the frozen v0 benchmark and the separately reviewed
300-case external-source release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image


DEFAULT_DATASETS_ROOT = Path("/mnt/bn/strategy-mllm-train/user/tanyue/datasets")
DEFAULT_OUTPUT = DEFAULT_DATASETS_ROOT / "samtok_edit_benchmark_v1"
DEFAULT_V0_MANIFEST = (
    DEFAULT_DATASETS_ROOT
    / "PACO_benchmark_candidates/original_656_hard_relevant_v1/benchmark/benchmark.jsonl"
)
DEFAULT_V0_ROOT = DEFAULT_DATASETS_ROOT / "samtok_edit_benchmark"
DEFAULT_GOAL1K_MANIFEST = (
    DEFAULT_DATASETS_ROOT
    / "PACO_benchmark_candidates/goal_1k/benchmark_goal1k_v1_300/benchmark.jsonl"
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def image_size(path: Path) -> list[int]:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        return [image.width, image.height]


def resolve_ref(ref: str, dataset_root: Path | None) -> Path:
    path = Path(ref)
    if path.is_absolute():
        return path
    if dataset_root is None:
        raise ValueError(f"Relative asset reference without dataset root: {ref}")
    return (dataset_root / path).resolve()


def copy_asset(source: Path, destination: Path) -> dict[str, Any]:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {
        "sha256": sha256(destination),
        "size_wh": image_size(destination),
        "bytes": destination.stat().st_size,
    }


def relative_to_output(path: Path, output: Path) -> str:
    return path.relative_to(output).as_posix()


def build(
    v0_manifest: Path,
    v0_root: Path,
    goal1k_manifest: Path,
    output: Path,
    overwrite: bool,
) -> dict[str, Any]:
    if output.exists():
        if any(output.iterdir()) and not overwrite:
            raise FileExistsError(
                f"Output is non-empty: {output}; pass --overwrite to rebuild it"
            )
        if overwrite:
            shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    specs = [
        {
            "release": "v0_hard_relevant_150",
            "manifest": v0_manifest,
            "dataset_root": v0_root,
            "source_manifest_label": "original_656_hard_relevant_v1/benchmark/benchmark.jsonl",
        },
        {
            "release": "goal1k_v1_300",
            "manifest": goal1k_manifest,
            "dataset_root": None,
            "source_manifest_label": "goal_1k/benchmark_goal1k_v1_300/benchmark.jsonl",
        },
    ]

    cases: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    source_hashes: dict[str, list[str]] = {}
    original_ids: set[str] = set()
    combined_ids: set[str] = set()
    source_counts = Counter()
    release_counts = Counter()
    edit_counts = Counter()
    region_counts = Counter()
    asset_records: list[dict[str, Any]] = []

    for spec in specs:
        rows = read_jsonl(spec["manifest"])
        for local_index, row in enumerate(rows):
            original_id = row["id"]
            if original_id in original_ids:
                raise ValueError(f"Duplicate original id across inputs: {original_id}")
            original_ids.add(original_id)
            combined_id = f"v1-{spec['release']}-{local_index:04d}-{original_id}"
            if combined_id in combined_ids:
                raise ValueError(f"Duplicate combined id: {combined_id}")
            combined_ids.add(combined_id)

            source = resolve_ref(row["source_image"], spec["dataset_root"])
            evaluation = resolve_ref(row["evaluation_mask"], spec["dataset_root"])
            suffix = source.suffix.lower() or ".img"
            asset_prefix = f"assets/{spec['release']}/{local_index:04d}"
            source_dest = output / f"{asset_prefix}/source{suffix}"
            evaluation_dest = output / f"{asset_prefix}/evaluation_mask.png"
            source_record = copy_asset(source, source_dest)
            evaluation_record = copy_asset(evaluation, evaluation_dest)
            source_hashes.setdefault(source_record["sha256"], []).append(combined_id)

            regions: list[dict[str, Any]] = []
            for region_index, region in enumerate(row["regions"], 1):
                region_source = resolve_ref(region["mask"], spec["dataset_root"])
                region_dest = output / f"{asset_prefix}/region_{region_index}.png"
                region_record = copy_asset(region_source, region_dest)
                regions.append(
                    {
                        "mask": relative_to_output(region_dest, output),
                        "box": region["box"],
                        "point": region["point"],
                    }
                )
                asset_records.append(
                    {
                        "case_id": combined_id,
                        "asset_type": f"region_{region_index}",
                        "original_path": str(region_source),
                        "local_path": relative_to_output(region_dest, output),
                        "sha256": region_record["sha256"],
                        "size_wh": region_record["size_wh"],
                    }
                )

            cases.append(
                {
                    "id": combined_id,
                    "original_id": original_id,
                    "source_release": spec["release"],
                    "source_dataset": row["source_dataset"],
                    "edit_type": row["edit_type"],
                    "difficulty": row["difficulty"],
                    "source_image": relative_to_output(source_dest, output),
                    "evaluation_mask": relative_to_output(evaluation_dest, output),
                    "regions": regions,
                }
            )
            audits.append(
                {
                    "id": combined_id,
                    "original_id": original_id,
                    "source_release": spec["release"],
                    "source_manifest": spec["source_manifest_label"],
                    "source_manifest_path": str(spec["manifest"].resolve()),
                    "source_image_original": str(source),
                    "evaluation_mask_original": str(evaluation),
                    "source_image_sha256": source_record["sha256"],
                    "evaluation_mask_sha256": evaluation_record["sha256"],
                    "region_count": len(regions),
                }
            )
            asset_records.extend(
                [
                    {
                        "case_id": combined_id,
                        "asset_type": "source_image",
                        "original_path": str(source),
                        "local_path": relative_to_output(source_dest, output),
                        "sha256": source_record["sha256"],
                        "size_wh": source_record["size_wh"],
                    },
                    {
                        "case_id": combined_id,
                        "asset_type": "evaluation_mask",
                        "original_path": str(evaluation),
                        "local_path": relative_to_output(evaluation_dest, output),
                        "sha256": evaluation_record["sha256"],
                        "size_wh": evaluation_record["size_wh"],
                    },
                ]
            )
            source_counts[row["source_dataset"]] += 1
            release_counts[spec["release"]] += 1
            edit_counts[row["edit_type"]] += 1
            region_counts[len(regions)] += 1

    duplicate_source_hashes = {
        value: ids for value, ids in source_hashes.items() if len(ids) > 1
    }
    if duplicate_source_hashes:
        raise ValueError(f"Source image content duplicates found: {duplicate_source_hashes}")

    benchmark_dir = output / "benchmark"
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    for name, records in (
        ("benchmark.jsonl", cases),
        ("case_audit.jsonl", audits),
        ("asset_manifest.jsonl", asset_records),
    ):
        (benchmark_dir / name).write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
            encoding="utf-8",
        )

    summary = {
        "version": "samtok_edit_benchmark_v1_cases",
        "status": "staging_without_instructions",
        "case_count": len(cases),
        "source_image_count": len(source_hashes),
        "region_count_total": sum(region_counts.values()),
        "source_release_counts": dict(release_counts),
        "source_dataset_counts": dict(sorted(source_counts.items())),
        "edit_type_counts": dict(sorted(edit_counts.items())),
        "region_count_distribution": dict(sorted(region_counts.items())),
        "source_manifests": [str(spec["manifest"].resolve()) for spec in specs],
        "asset_policy": "source images and masks copied into this dataset; no external asset reference is required by benchmark.jsonl",
        "instruction_policy": "instruction field intentionally omitted; this catalog is not evaluator-ready until instructions are authored",
        "target_policy": "target field intentionally omitted; no target/reference image is part of this staging catalog",
        "id_policy": "new IDs preserve source release and local row index; original_id records the input ID",
    }
    (output / "dataset_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "README.md").write_text(
        "# SAMTok Edit Benchmark v1 case catalog\n\n"
        "This directory contains the combined 150-case v0 hard-relevant subset and "
        "the separately reviewed 300-case external-source release. It intentionally "
        "contains source images, masks, boxes, and points only; instructions and "
        "target references are omitted for the current construction stage. See the "
        "repository document `docs/BENCHMARK_V1_CASE_CATALOG.md` for provenance and "
        "selection details.\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v0-manifest", type=Path, default=DEFAULT_V0_MANIFEST)
    parser.add_argument("--v0-root", type=Path, default=DEFAULT_V0_ROOT)
    parser.add_argument("--goal1k-manifest", type=Path, default=DEFAULT_GOAL1K_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    summary = build(
        args.v0_manifest.resolve(),
        args.v0_root.resolve(),
        args.goal1k_manifest.resolve(),
        args.output.resolve(),
        args.overwrite,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
