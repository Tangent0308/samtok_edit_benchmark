"""Validate independent physical targets, public interactions and immutable assets."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from samtok_benchmark.io import asset_path, read_jsonl, sha256_file, write_json
from samtok_benchmark.v2 import OPERATIONS, SCHEMA_VERSION


def interaction_name(unit):
    interaction = unit["interaction"]
    return ("ref" if interaction["has_ref"] else "noref") + "+" + interaction["locator"]


def load_cases(manifest: Path) -> list[dict]:
    cases = read_jsonl(manifest)
    if not cases:
        raise ValueError("empty v2 manifest")
    ids, families = set(), set()
    for case in cases:
        if case.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("expected v2 schema")
        if not case.get("id") or case["id"] in ids:
            raise ValueError("duplicate/empty case ID")
        ids.add(case["id"])
        source = case["source"]
        if source["family_id"] in families:
            raise ValueError("release cases must use distinct source families")
        families.add(source["family_id"])
        units = case["units"]
        if not 2 <= len(units) <= 4:
            raise ValueError("v2 release requires two to four independent units")
        unit_ids, parents = set(), set()
        for unit in units:
            if not unit.get("id") or unit["id"] in unit_ids:
                raise ValueError("duplicate/empty unit ID")
            unit_ids.add(unit["id"])
            if unit["operation"] not in OPERATIONS:
                raise ValueError("invalid unit operation")
            target = unit["target"]
            parent = target["parent_instance_id"]
            if not parent or parent in parents:
                raise ValueError("units must identify different physical parent objects")
            parents.add(parent)
            interaction = unit["interaction"]
            if type(interaction.get("has_ref")) is not bool:
                raise ValueError("has_ref must be boolean")
            if interaction.get("locator") not in {"none", "mask", "box", "point"}:
                raise ValueError("invalid per-unit locator")
            if not interaction["has_ref"] and interaction["locator"] == "none":
                raise ValueError("no-ref unit requires a locator")
            for field in ("instruction_ref", "instruction_noref", "completion_requirement"):
                if not isinstance(unit.get(field), str) or not unit[field].strip():
                    raise ValueError(f"empty unit field: {field}")
            if not isinstance(unit.get("preserve"), list) or not unit["preserve"]:
                raise ValueError("unit must specify protected neighboring content")
        if len({interaction_name(u) for u in units}) < 2:
            raise ValueError("primary v2 case requires mixed per-unit interactions")
        review = case["review"]
        if review.get("decision") != "accept" or not review.get("evidence"):
            raise ValueError("release requires a recorded admission decision and evidence")
        if review.get("kind") not in {"ai_direct_visual", "human"}:
            raise ValueError("review provenance must name its actual kind")
        if not case["difficulty"].get("mechanisms"):
            raise ValueError("missing fine-grained difficulty evidence")
    return cases


def validate(manifest: Path, root: Path, minimum_cases=0, output: Path | None = None):
    cases = load_cases(manifest)
    if len(cases) < minimum_cases:
        raise ValueError(f"expected at least {minimum_cases} cases; found {len(cases)}")
    source_hashes = set()
    asset_count = 0
    for case in cases:
        source = case["source"]
        path = asset_path(root, source["image"])
        h = sha256_file(path)
        if h != source["sha256"] or h in source_hashes:
            raise ValueError("source content changed or duplicated")
        source_hashes.add(h)
        with Image.open(path) as im:
            im.load()
            width, height = im.size
        if [width, height] != source["size"]:
            raise ValueError("source geometry changed")
        asset_count += 1
        card = asset_path(root, case["review"]["card"])
        if sha256_file(card) != case["review"]["card_sha256"]:
            raise ValueError("review evidence image changed")
        asset_count += 1
        masks = []
        for unit in case["units"]:
            target = unit["target"]
            path = asset_path(root, target["mask"])
            if sha256_file(path) != target["mask_sha256"]:
                raise ValueError("target mask content changed")
            with Image.open(path) as im:
                if im.size != (width, height):
                    raise ValueError("mask/source size mismatch")
                a = np.array(im.convert("L"))
            if not set(np.unique(a)).issubset({0, 255}) or not a.any():
                raise ValueError("mask must be nonempty binary 0/255")
            mask = a > 0
            x1, y1, x2, y2 = target["box"]
            px, py = target["point"]
            if not all(type(v) is int for v in [x1, y1, x2, y2, px, py]):
                raise ValueError("geometry requires integer pixels")
            if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                raise ValueError("invalid half-open box")
            if not (0 <= px < width and 0 <= py < height and mask[py, px]):
                raise ValueError("point must lie in target")
            yy, xx = np.where(mask)
            if not (x1 <= xx.min() and xx.max() < x2 and y1 <= yy.min() and yy.max() < y2):
                raise ValueError("box must contain target mask")
            for previous in masks:
                if (mask & previous).sum() / min(mask.sum(), previous.sum()) > 0.04:
                    raise ValueError("independent visible targets have substantial overlap")
            masks.append(mask)
            asset_count += 1
    inventory_path = manifest.parent / "asset_manifest.jsonl"
    inventory_count = 0
    if inventory_path.exists():
        inventory = read_jsonl(inventory_path)
        required = {c["source"]["image"] for c in cases}
        required |= {c["review"]["card"] for c in cases}
        required |= {u["target"]["mask"] for c in cases for u in c["units"]}
        if (
            len({r["path"] for r in inventory}) != len(inventory)
            or {r["path"] for r in inventory} != required
        ):
            raise ValueError("release asset inventory differs from manifest")
        for item in inventory:
            path = asset_path(root, item["path"])
            if sha256_file(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
                raise ValueError("release asset inventory checksum/size mismatch")
        inventory_count = len(inventory)
    report = {
        "status": "passed",
        "manifest_sha256": sha256_file(manifest),
        "cases": len(cases),
        "unique_sources": len(source_hashes),
        "units": sum(len(c["units"]) for c in cases),
        "checked_assets": asset_count,
        "inventory_checked": inventory_count,
        "unit_counts": dict(Counter(len(c["units"]) for c in cases)),
        "source_counts": dict(Counter(c["source"]["dataset"] for c in cases)),
        "unit_operations": dict(Counter(u["operation"] for c in cases for u in c["units"])),
        "unit_interactions": dict(Counter(interaction_name(u) for c in cases for u in c["units"])),
        "review_kinds": dict(Counter(c["review"]["kind"] for c in cases)),
    }
    if output:
        write_json(output, report)
    return report
