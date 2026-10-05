"""Load and verify the current release; geometry never depends on model outputs."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from samtok_benchmark.io import asset_path, read_jsonl, sha256_file, write_json

FIELDS = {
    "schema_version",
    "id",
    "original_id",
    "source_release",
    "source_dataset",
    "source_image",
    "regions",
    "evaluation_mask",
    "difficulty",
    "instruction",
    "region_instruction",
    "edit_type",
    "instruction_source",
    "instruction_revision",
}
OPERATIONS = {"attribute", "add", "remove", "replace", "mixed", "action", "text", "composite"}


def load_cases(manifest: Path, expected_cases: int | None = None) -> list[dict]:
    rows = read_jsonl(manifest)
    if not rows or (expected_cases is not None and len(rows) != expected_cases):
        raise ValueError(f"unexpected case count: {len(rows)}; expected {expected_cases}")
    ids = set()
    for row in rows:
        if set(row) != FIELDS or row["schema_version"] != "1.0":
            raise ValueError(f"invalid v1 schema: {row.get('id')}")
        if not isinstance(row["id"], str) or not row["id"] or row["id"] in ids:
            raise ValueError(f"invalid/duplicate case id: {row['id']}")
        ids.add(row["id"])
        if row["edit_type"] not in OPERATIONS:
            raise ValueError(f"invalid edit type: {row['id']}")
        for key in ("instruction", "region_instruction", "instruction_revision"):
            if not isinstance(row[key], str) or not row[key].strip():
                raise ValueError(f"empty {key}: {row['id']}")
        if len(row["regions"]) not in (1, 2):
            raise ValueError(f"expected one or two regions: {row['id']}")
        placeholders = re.findall(r"\{region_(\d+)\}", row["region_instruction"])
        if placeholders and placeholders != [str(i + 1) for i in range(len(row["regions"]))]:
            raise ValueError(f"region placeholder mismatch: {row['id']}")
        for region in row["regions"]:
            if set(region) != {"mask", "box", "point"}:
                raise ValueError(f"invalid region schema: {row['id']}")
            if len(region["box"]) != 4 or len(region["point"]) != 2:
                raise ValueError(f"invalid region geometry: {row['id']}")
    return rows


def _binary_mask(path: Path, size: tuple[int, int]) -> np.ndarray:
    with Image.open(path) as im:
        im.load()
        if im.size != size:
            raise ValueError(f"mask size mismatch: {path}")
        pixels = np.asarray(im.convert("L"))
    if not set(np.unique(pixels)).issubset({0, 1, 255}) or not pixels.any():
        raise ValueError(f"mask must be binary and nonempty: {path}")
    return pixels > 0


def validate(
    manifest: Path,
    root: Path,
    asset_manifest: Path | None = None,
    expected_cases: int | None = None,
    output: Path | None = None,
) -> dict:
    cases = load_cases(manifest, expected_cases)
    expected = {}
    if asset_manifest:
        for a in read_jsonl(asset_manifest):
            if a["local_path"] in expected:
                raise ValueError(f"duplicate asset record: {a['local_path']}")
            expected[a["local_path"]] = a
    hashes = {}
    source_hashes = set()
    for row in cases:
        source = asset_path(root, row["source_image"])
        with Image.open(source) as im:
            im.load()
            size = im.size
        union = np.zeros((size[1], size[0]), dtype=bool)
        refs = [row["source_image"], row["evaluation_mask"]]
        for region in row["regions"]:
            mask = _binary_mask(asset_path(root, region["mask"]), size)
            union |= mask
            x1, y1, x2, y2 = region["box"]
            px, py = region["point"]
            if not all(type(v) is int for v in [x1, y1, x2, y2, px, py]):
                raise ValueError(f"geometry must use integer pixels: {row['id']}")
            if not (0 <= x1 < x2 <= size[0] and 0 <= y1 < y2 <= size[1]):
                raise ValueError(f"invalid half-open box: {row['id']}")
            if not (0 <= px < size[0] and 0 <= py < size[1] and mask[py, px]):
                raise ValueError(f"point is outside the mask: {row['id']}")
            ys, xs = np.nonzero(mask)
            if not (x1 <= xs.min() <= xs.max() < x2 and y1 <= ys.min() <= ys.max() < y2):
                raise ValueError(f"box does not contain the mask: {row['id']}")
            refs.append(region["mask"])
        evaluation = _binary_mask(asset_path(root, row["evaluation_mask"]), size)
        if np.any(union & ~evaluation):
            raise ValueError(f"legacy evaluation mask does not cover regions: {row['id']}")
        for ref in refs:
            h = sha256_file(asset_path(root, ref))
            hashes[ref] = h
            if asset_manifest and (ref not in expected or expected[ref]["sha256"] != h):
                raise ValueError(f"asset hash mismatch: {ref}")
        source_hashes.add(hashes[row["source_image"]])
    if len(source_hashes) != len(cases):
        raise ValueError("duplicate source image content")
    report = {
        "status": "passed",
        "manifest_sha256": sha256_file(manifest),
        "cases": len(cases),
        "unique_source_images": len(source_hashes),
        "region_masks": sum(len(c["regions"]) for c in cases),
        "checked_assets": len(hashes),
        "asset_hashes_verified": bool(asset_manifest),
        "source_dataset_counts": dict(sorted(Counter(c["source_dataset"] for c in cases).items())),
        "edit_type_counts": dict(sorted(Counter(c["edit_type"] for c in cases).items())),
        "region_count_distribution": dict(
            sorted(Counter(len(c["regions"]) for c in cases).items())
        ),
    }
    if output:
        write_json(output, report)
    return report
