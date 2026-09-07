#!/usr/bin/env python3
"""Build a reproducible 500-case candidate manifest for the regional edit benchmark.

This is an automatic pre-selection pass. It never mutates the downloaded datasets.
CompBench and HumanEdit are filtered with their ground-truth edit locality; ReShapeBench
has no GT image, so its released box masks are ranked and explicitly flagged for SAM2
refinement and human review.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
import pyarrow.parquet as pq
from PIL import Image


ROOT = Path("/mnt/bn/strategy-mllm-train/user/tanyue/datasets")
DEFAULT_OUTPUT = Path("/opt/tiger/tanyue/finegrained_edit_benchmark_selection/output")
HUMANEDIT_CODE = Path("/opt/tiger/tanyue/HumanEdit")

QUOTAS = {
    ("CompBench", "add"): 50,
    ("CompBench", "remove"): 60,
    ("CompBench", "replace"): 50,
    ("CompBench", "multi_object_add"): 30,
    ("CompBench", "multi_object_remove"): 30,
    ("HumanEdit", "add"): 42,
    ("HumanEdit", "remove"): 60,
    ("HumanEdit", "replace"): 60,
    ("HumanEdit", "counting"): 18,
    ("ReShapeBench", "single_object"): 30,
    ("ReShapeBench", "multi_object"): 70,
}

POSITIONAL_RE = re.compile(
    r"\b(left|right|upper|lower|top|bottom|middle|center|front|behind|back|"
    r"leftmost|rightmost|nearest|farthest|biggest|smallest|first|second|third|"
    r"another|other|between|among|one of|one on|one in|one at)\b",
    re.IGNORECASE,
)
PLURAL_OR_COUNT_RE = re.compile(
    r"\b(two|three|2|3|both|pair|couple|several|multiple)\b", re.IGNORECASE
)
GLOBAL_EDIT_RE = re.compile(
    r"\b(style|stylize|viewpoint|camera angle|background|entire image|whole image|"
    r"make it (?:a |an )?(?:painting|drawing|sketch|cartoon))\b",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--diff-threshold", type=float, default=12.0 / 255.0)
    parser.add_argument("--seed", type=int, default=20260907)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--reuse-features",
        action="store_true",
        help="reuse output/all_preselection_features.jsonl and only rerun deterministic selection",
    )
    return parser.parse_args()


def decode(cell: dict[str, Any], mode: str) -> Image.Image:
    payload = cell.get("bytes") if isinstance(cell, dict) else None
    if not isinstance(payload, bytes):
        raise ValueError("embedded image cell has no bytes")
    with Image.open(io.BytesIO(payload)) as image:
        return image.convert(mode).copy()


def source_digest(cell: dict[str, Any]) -> str:
    return hashlib.sha256(cell["bytes"]).hexdigest()[:20]


def deterministic_tie(candidate_id: str, seed: int) -> float:
    value = hashlib.sha256(f"{seed}:{candidate_id}".encode()).digest()[:8]
    return int.from_bytes(value, "big") / float(2**64)


def comp_scene_id(source_record_id: str) -> str:
    # Local cases use <video>/<track>/<frame>; multi-object cases use <video>_<frame>.
    prefix = source_record_id.split("/", 1)[0]
    if "/" not in source_record_id:
        prefix = prefix.split("_", 1)[0]
    return f"cb-scene-{prefix}"


def binary_mask(mask: Image.Image, size: tuple[int, int] | None = None) -> np.ndarray:
    if size is not None and mask.size != size:
        mask = mask.resize(size, Image.Resampling.NEAREST)
    return np.asarray(mask.convert("L")) >= 128


def component_stats(mask: np.ndarray) -> tuple[int, list[int], list[list[int]]]:
    # A tiny-area cutoff suppresses encoding speckles without merging true instances.
    m = mask.astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    minimum = max(16, int(math.ceil(mask.size * 0.00005)))
    entries = []
    for row in stats[1:n]:
        x, y, w, h, area = map(int, row)
        if area >= minimum:
            entries.append((area, [x, y, x + w, y + h]))
    entries.sort(reverse=True)
    return len(entries), [x[0] for x in entries], [x[1] for x in entries]


def mask_metrics(mask: np.ndarray) -> dict[str, Any]:
    components, component_areas, boxes = component_stats(mask)
    ys, xs = np.nonzero(mask)
    bbox = None if not len(xs) else [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
    return {
        "mask_area_ratio": float(mask.mean()),
        "mask_components": components,
        "component_area_ratios": [float(x / mask.size) for x in component_areas],
        "component_boxes": boxes,
        "mask_bbox": bbox,
    }


def dilate_two_percent(mask: np.ndarray) -> np.ndarray:
    radius = max(1, round(min(mask.shape) * 0.02))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    return cv2.dilate(mask.astype(np.uint8), kernel, iterations=1).astype(bool)


def locality_metrics(
    source: Image.Image, target: Image.Image, mask: np.ndarray, diff_threshold: float
) -> dict[str, Any]:
    size = (mask.shape[1], mask.shape[0])
    if source.size != size:
        source = source.resize(size, Image.Resampling.BICUBIC)
    if target.size != size:
        target = target.resize(size, Image.Resampling.BICUBIC)
    src = np.asarray(source.convert("RGB"), dtype=np.float32) / 255.0
    tgt = np.asarray(target.convert("RGB"), dtype=np.float32) / 255.0
    delta = np.abs(src - tgt).mean(axis=2)
    region = dilate_two_percent(mask)
    total_mass = float(delta.sum())
    changed = delta >= diff_threshold
    changed_count = int(changed.sum())
    return {
        "diff_mass_inside_ratio": float(delta[region].sum() / total_mass) if total_mass else 1.0,
        "changed_pixel_inside_ratio": float((changed & region).sum() / changed_count) if changed_count else 1.0,
        "mean_change_inside": float(delta[mask].mean()) if mask.any() else 0.0,
        "mean_change_outside": float(delta[~mask].mean()) if (~mask).any() else 0.0,
        "changed_pixel_ratio": float(changed.mean()),
    }


def estimated_target_count(instruction: str, edit_type: str) -> int | None:
    text = instruction.lower()
    mapping = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
    if edit_type == "counting":
        matches = re.findall(r"\b(?:to|becomes?|became|into|left)\s+(?:just\s+)?(\d+|one|two|three|four|five|six)\b", text)
        if matches:
            return int(matches[-1]) if matches[-1].isdigit() else mapping[matches[-1]]
    if re.search(r"\b(two|both|pair)\b", text):
        return 2
    if re.search(r"\b(three|3)\b", text):
        return 3
    return 1


def common_flags(record: dict[str, Any], max_components: int, max_area: float) -> list[str]:
    flags = []
    area = record["mask_area_ratio"]
    if area < 0.003:
        flags.append("mask_area_below_0.3pct")
    if area > max_area:
        flags.append("mask_area_above_limit")
    if record["mask_components"] > max_components:
        flags.append("too_many_mask_components")
    if GLOBAL_EDIT_RE.search(record["instruction_original"]):
        flags.append("possible_global_edit")
    count = record.get("estimated_target_count")
    if count is not None and count > 3:
        flags.append("estimated_target_count_above_3")
    return flags


def _compbench_shard_records(shard: Path, diff_threshold: float) -> tuple[int, list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    allowed = {"add", "remove", "replace", "multi_object_add", "multi_object_remove"}
    columns = ["task", "image_path", "input_image", "edited_image", "instruction", "caption", "mask"]
    parquet = pq.ParquetFile(shard)
    row_number = 0
    for batch in parquet.iter_batches(batch_size=16, columns=columns):
        for row in batch.to_pylist():
            task = row["task"]
            current = row_number
            row_number += 1
            if task not in allowed or row["mask"] is None:
                continue
            mask_image = decode(row["mask"], "L")
            mask = binary_mask(mask_image)
            source = decode(row["input_image"], "RGB")
            target = decode(row["edited_image"], "RGB")
            metrics = mask_metrics(mask)
            candidate_id = f"cb_{shard.stem}_{current:04d}"
            record = {
                    "candidate_id": candidate_id,
                    "source_dataset": "CompBench",
                    "source_split": "train",
                    "source_shard": str(shard),
                    "source_row": current,
                    "source_record_id": row["image_path"],
                    "source_group_id": f"cb-src-{source_digest(row['input_image'])}",
                    "scene_group_id": comp_scene_id(row["image_path"]),
                    "instruction_original": row["instruction"].strip(),
                    "local_caption": (row["caption"] or "").strip(),
                    "target_prompt": None,
                    "edit_type": task,
                    "region_source": "instance_mask_union" if task.startswith("multi_object") else "instance_mask",
                    "has_gt_image": True,
                    "mask_flag": None,
                    "core": None,
                    "num_scene_objects": None,
                    "estimated_target_count": 2 if task.startswith("multi_object") else estimated_target_count(row["instruction"], task),
                    "multi_target": task.startswith("multi_object"),
                    "multi_object_scene": True,
                    "requires_ref_instruction": False,
                    "same_class_multi_instance_proxy": bool(POSITIONAL_RE.search(row["instruction"]) or task.startswith("multi_object")),
                    **metrics,
                    **locality_metrics(source, target, mask, diff_threshold),
            }
            limit = 0.50 if task.startswith("multi_object") else 0.40
            max_components = 6 if task.startswith("multi_object") else 2
            flags = common_flags(record, max_components=max_components, max_area=limit)
            if record["changed_pixel_inside_ratio"] < 0.80:
                flags.append("gt_changed_pixels_inside_below_80pct")
            if record["diff_mass_inside_ratio"] < 0.40:
                flags.append("gt_diff_mass_inside_below_40pct")
            component_ratios = record["component_area_ratios"]
            if task.startswith("multi_object") and any(x > 0.40 for x in component_ratios):
                flags.append("component_area_above_40pct")
            record["review_flags"] = sorted(set(flags))
            record["strict_eligible"] = not flags
            records.append(record)
    return row_number, records


def compbench_records(dataset_root: Path, diff_threshold: float, workers: int) -> list[dict[str, Any]]:
    records = []
    shards = sorted((dataset_root / "CompBench" / "data").glob("train-*.parquet"))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_compbench_shard_records, shard, diff_threshold): shard for shard in shards}
        for future in as_completed(futures):
            shard = futures[future]
            row_count, shard_records = future.result()
            records.extend(shard_records)
            print(f"CompBench {shard.name}: scanned={row_count} shard_candidates={len(shard_records)}", flush=True)
    return records


def load_humanedit_alignment():
    sys.path.insert(0, str(HUMANEDIT_CODE))
    from humanedit_converter.geometry import align_source, classify_geometry
    config = json.loads((HUMANEDIT_CODE / "configs" / "canonical_v1.json").read_text())
    return align_source, classify_geometry, config


def _humanedit_shard_records(
    shard: Path, diff_threshold: float, align_source: Any, classify_geometry: Any, config: dict[str, Any]
) -> tuple[int, list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    allowed = {"Add", "Remove", "Replace", "Counting"}
    columns = [
        "IMAGE_ID", "EDITING_TYPE", "CORE", "MASK", "EDITING_INSTRUCTION",
        "OUTPUT_DESCRIPTION", "INPUT_CAPTION_BY_LLAMA", "OUTPUT_CAPTION_BY_LLAMA",
        "INPUT_IMG", "MASK_IMG", "OUTPUT_IMG",
    ]
    parquet = pq.ParquetFile(shard)
    row_number = 0
    for batch in parquet.iter_batches(batch_size=8, columns=columns):
        for row in batch.to_pylist():
            current = row_number
            row_number += 1
            if row["EDITING_TYPE"] not in allowed or int(row["MASK"]) != 1:
                continue
            canvas = decode(row["MASK_IMG"], "RGBA")
            if canvas.mode != "RGBA":
                continue
            alpha = np.asarray(canvas.getchannel("A"))
            mask = alpha < int(config["alpha_threshold"])
            source_native = decode(row["INPUT_IMG"], "RGB")
            target = decode(row["OUTPUT_IMG"], "RGB")
            source, alignment = align_source(source_native, canvas, config)
            if target.size != canvas.size:
                target = target.resize(canvas.size, Image.Resampling.BICUBIC)
            metrics = mask_metrics(mask)
            edit_type = row["EDITING_TYPE"].lower()
            candidate_id = f"he_{row['IMAGE_ID']}"
            instruction = row["EDITING_INSTRUCTION"].strip()
            record = {
                    "candidate_id": candidate_id,
                    "source_dataset": "HumanEdit",
                    "source_split": "train",
                    "source_shard": str(shard),
                    "source_row": current,
                    "source_record_id": row["IMAGE_ID"],
                    "source_group_id": f"he-src-{source_digest(row['INPUT_IMG'])}",
                    "scene_group_id": f"he-src-{source_digest(row['INPUT_IMG'])}",
                    "instruction_original": instruction,
                    "local_caption": (row["OUTPUT_DESCRIPTION"] or row["OUTPUT_CAPTION_BY_LLAMA"] or "").strip(),
                    "target_prompt": (row["OUTPUT_CAPTION_BY_LLAMA"] or row["OUTPUT_DESCRIPTION"] or "").strip(),
                    "input_caption": (row["INPUT_CAPTION_BY_LLAMA"] or "").strip(),
                    "edit_type": edit_type,
                    "region_source": "human_brush_alpha",
                    "has_gt_image": True,
                    "mask_flag": int(row["MASK"]),
                    "core": int(row["CORE"]),
                    "num_scene_objects": None,
                    "estimated_target_count": estimated_target_count(instruction, edit_type),
                    "multi_target": bool(PLURAL_OR_COUNT_RE.search(instruction)),
                    "multi_object_scene": bool(PLURAL_OR_COUNT_RE.search(instruction)),
                    "requires_ref_instruction": edit_type == "counting",
                    "same_class_multi_instance_proxy": bool(edit_type == "counting" or POSITIONAL_RE.search(instruction)),
                    "alignment_transform": alignment.transform,
                    "alignment_status": alignment.status,
                    "alignment_ambiguous": alignment.ambiguous,
                    "geometry": classify_geometry(canvas.size, source_native.size, tuple(config["canonical_size"]), int(config["proportional_tolerance_px"])),
                    **metrics,
                    **locality_metrics(source, target, mask, diff_threshold),
            }
            flags = common_flags(record, max_components=3, max_area=0.40)
            if not mask.any():
                flags.append("empty_alpha_mask")
            if alignment.status == "poor":
                flags.append("source_alignment_poor")
            if record["changed_pixel_inside_ratio"] < 0.80:
                flags.append("gt_changed_pixels_inside_below_80pct")
            if record["diff_mass_inside_ratio"] < 0.40:
                flags.append("gt_diff_mass_inside_below_40pct")
            record["review_flags"] = sorted(set(flags))
            record["strict_eligible"] = not flags
            records.append(record)
    return row_number, records


def humanedit_records(dataset_root: Path, diff_threshold: float, workers: int) -> list[dict[str, Any]]:
    align_source, classify_geometry, config = load_humanedit_alignment()
    records = []
    shards = sorted((dataset_root / "HumanEdit" / "data").glob("*.parquet"))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _humanedit_shard_records, shard, diff_threshold, align_source, classify_geometry, config
            ): shard
            for shard in shards
        }
        for future in as_completed(futures):
            shard = futures[future]
            row_count, shard_records = future.result()
            records.extend(shard_records)
            print(f"HumanEdit {shard.name}: scanned={row_count} shard_candidates={len(shard_records)}", flush=True)
    return records


def reshapebench_records(dataset_root: Path) -> list[dict[str, Any]]:
    base = dataset_root / "ReShapeBench"
    records = []
    for subset in ("single_object", "multi_object"):
        metadata = base / subset / "metadata.jsonl"
        for line_number, line in enumerate(metadata.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            source_path = base / subset / row["file_name"]
            mask_path = base / subset / row["mask"]
            with Image.open(mask_path) as image:
                mask = binary_mask(image.convert("L"))
            metrics = mask_metrics(mask)
            instruction = row["instruction"].strip()
            candidate_id = f"rs_{row['id']}"
            record = {
                "candidate_id": candidate_id,
                "source_dataset": "ReShapeBench",
                "source_split": subset,
                "source_shard": str(metadata),
                "source_row": line_number - 1,
                "source_record_id": row["id"],
                "source_group_id": f"rs-src-{Path(row['file_name']).stem}",
                "scene_group_id": f"rs-src-{Path(row['file_name']).stem}",
                "source_image_path": str(source_path),
                "source_mask_path": str(mask_path),
                "instruction_original": instruction,
                "local_caption": row["foreground_target"],
                "target_prompt": row["target_prompt"],
                "source_prompt": row["source_prompt"],
                "foreground": row["foreground"],
                "foreground_target": row["foreground_target"],
                "background": row["background"],
                "edit_type": subset,
                "region_source": "released_box_mask_needs_sam2",
                "has_gt_image": False,
                "mask_flag": None,
                "core": None,
                "num_scene_objects": int(row["num_objects"]),
                "estimated_target_count": 1,
                "multi_target": False,
                "multi_object_scene": subset == "multi_object",
                "requires_ref_instruction": False,
                "same_class_multi_instance_proxy": subset == "multi_object",
                "diff_mass_inside_ratio": None,
                "changed_pixel_inside_ratio": None,
                "mean_change_inside": None,
                "mean_change_outside": None,
                "changed_pixel_ratio": None,
                **metrics,
            }
            strict_flags = common_flags(record, max_components=2, max_area=0.40)
            record["strict_eligible"] = not strict_flags
            # Every released ReShape box must go through the planned SAM2 + human check.
            record["review_flags"] = sorted(set(strict_flags + ["needs_sam2_mask_refinement", "no_gt_image"]))
            records.append(record)
        print(f"ReShapeBench {subset}: candidates={sum(x['edit_type'] == subset for x in records)}", flush=True)
    return records


def record_score(record: dict[str, Any], seed: int) -> float:
    area = record["mask_area_ratio"]
    # Peak around 8%; retain a smaller bonus for genuinely small targets.
    area_score = max(0.0, 1.0 - abs(math.log(max(area, 1e-5) / 0.08)) / 4.0)
    score = 2.5 * area_score
    if area < 0.02:
        score += 1.8
    if record.get("same_class_multi_instance_proxy"):
        score += 1.4
    if record.get("core") == 1:
        score += 0.8
    inside = record.get("diff_mass_inside_ratio")
    if inside is not None:
        score += 4.0 * inside
    if record.get("strict_eligible"):
        score += 5.0
    score -= 1.5 * len(record.get("review_flags", []))
    score += deterministic_tie(record["candidate_id"], seed) * 1e-3
    return score


def diverse_rank(
    pool: list[dict[str, Any]], seed: int, previously_used_scenes: set[str] | None = None
) -> list[dict[str, Any]]:
    for record in pool:
        record["selection_score"] = record_score(record, seed)
    ranked = sorted(pool, key=lambda x: (-x["selection_score"], x["candidate_id"]))
    # Prefer a new video/scene, then a new exact source within an already represented
    # scene, and only then an alternative target for an already used source.
    seen_scenes = set(previously_used_scenes or ())
    seen_sources = set()
    new_scene, new_source, repeated_source = [], [], []
    for record in ranked:
        scene = record["scene_group_id"]
        source = record["source_group_id"]
        if scene not in seen_scenes:
            new_scene.append(record)
            seen_scenes.add(scene)
            seen_sources.add(source)
        elif source not in seen_sources:
            new_source.append(record)
            seen_sources.add(source)
        else:
            repeated_source.append(record)
    return new_scene + new_source + repeated_source


def select_group(
    pool: list[dict[str, Any]], quota: int, seed: int, previously_used_scenes: set[str]
) -> list[dict[str, Any]]:
    strict = diverse_rank(
        [x for x in pool if x["strict_eligible"]], seed, previously_used_scenes
    )
    selected = strict[:quota]
    if len(selected) < quota:
        used = previously_used_scenes | {x["scene_group_id"] for x in selected}
        relaxed = diverse_rank(
            [x for x in pool if not x["strict_eligible"]], seed, used
        )
        selected.extend(relaxed[: quota - len(selected)])
    if len(selected) != quota:
        raise ValueError(f"quota {quota} cannot be met from pool of {len(pool)}")
    return selected


def improve_global_quotas(selected: list[dict[str, Any]], pools: dict[tuple[str, str], list[dict[str, Any]]], seed: int) -> None:
    """Swap within fixed source/type quotas to reach the small-target goal when feasible."""
    target_small = math.ceil(len(selected) * 0.25)
    current_ids = {x["candidate_id"] for x in selected}
    while sum(x["mask_area_ratio"] < 0.02 for x in selected) < target_small:
        best_swap = None
        scene_counts = Counter(x["scene_group_id"] for x in selected)
        source_counts = Counter(x["source_group_id"] for x in selected)
        for index, old in enumerate(selected):
            if old["mask_area_ratio"] < 0.02:
                continue
            key = (old["source_dataset"], old["edit_type"])
            alternatives = [
                x for x in pools[key]
                if x["candidate_id"] not in current_ids and x["mask_area_ratio"] < 0.02 and x["strict_eligible"]
            ]
            if not alternatives:
                continue
            def swap_cost(new: dict[str, Any]) -> float:
                quality_loss = record_score(old, seed) - record_score(new, seed)
                scene_loss = int(scene_counts[new["scene_group_id"]] > 0) - int(scene_counts[old["scene_group_id"]] > 1)
                source_loss = int(source_counts[new["source_group_id"]] > 0) - int(source_counts[old["source_group_id"]] > 1)
                return quality_loss + 8.0 * scene_loss + 3.0 * source_loss
            new = min(alternatives, key=swap_cost)
            loss = swap_cost(new)
            if best_swap is None or loss < best_swap[0]:
                best_swap = (loss, index, old, new)
        if best_swap is None:
            break
        _, index, old, new = best_swap
        selected[index] = new
        new["selection_score"] = record_score(new, seed)
        current_ids.remove(old["candidate_id"])
        current_ids.add(new["candidate_id"])


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    temp.replace(path)


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fields = [
        "candidate_id", "source_dataset", "source_split", "edit_type", "source_record_id",
        "source_shard", "source_row", "instruction_original", "local_caption", "target_prompt",
        "region_source", "mask_area_ratio", "mask_components", "diff_mass_inside_ratio",
        "changed_pixel_inside_ratio", "small_target", "multi_target", "multi_object_scene",
        "same_class_multi_instance_proxy", "requires_ref_instruction", "strict_eligible",
        "selection_score", "review_flags",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = dict(record)
            row["review_flags"] = "|".join(row["review_flags"])
            writer.writerow(row)


def write_review_template(path: Path, records: list[dict[str, Any]]) -> None:
    fields = [
        "selection_index", "candidate_id", "source_dataset", "edit_type",
        "instruction_original", "strict_eligible", "review_flags",
        "region_correct_y_n", "instruction_unambiguous_y_n", "local_edit_y_n",
        "gt_correct_y_n_or_na", "multi_target_mapping_y_n_or_na",
        "final_decision_keep_drop_rewrite", "reviewer", "review_notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = dict(record)
            row["review_flags"] = "|".join(row["review_flags"])
            for field in fields[7:]:
                row[field] = ""
            writer.writerow(row)


def summarize(all_records: list[dict[str, Any]], selected: list[dict[str, Any]]) -> dict[str, Any]:
    by_group = Counter((x["source_dataset"], x["edit_type"]) for x in selected)
    strict_by_source = Counter(x["source_dataset"] for x in selected if x["strict_eligible"])
    source_count = Counter(x["source_dataset"] for x in selected)
    flags = Counter(flag for x in selected for flag in x["review_flags"])
    area_values = np.asarray([x["mask_area_ratio"] for x in selected], dtype=np.float64)
    locality_values = np.asarray(
        [x["changed_pixel_inside_ratio"] for x in selected if x["has_gt_image"]], dtype=np.float64
    )
    return {
        "target_total": sum(QUOTAS.values()),
        "selected_total": len(selected),
        "all_preselection_records": len(all_records),
        "selected_by_source": dict(sorted(source_count.items())),
        "selected_by_group": {f"{k[0]}/{k[1]}": v for k, v in sorted(by_group.items())},
        "strict_selected_by_source": dict(sorted(strict_by_source.items())),
        "strict_selected_total": sum(x["strict_eligible"] for x in selected),
        "unique_source_images": len({x["source_group_id"] for x in selected}),
        "unique_scene_groups": len({x["scene_group_id"] for x in selected}),
        "small_target_count": sum(x["mask_area_ratio"] < 0.02 for x in selected),
        "small_target_fraction": sum(x["mask_area_ratio"] < 0.02 for x in selected) / len(selected),
        "multi_target_count": sum(x["multi_target"] for x in selected),
        "multi_target_fraction": sum(x["multi_target"] for x in selected) / len(selected),
        "multi_object_scene_count": sum(x["multi_object_scene"] for x in selected),
        "same_class_multi_instance_proxy_count": sum(x["same_class_multi_instance_proxy"] for x in selected),
        "requires_ref_instruction_count": sum(x["requires_ref_instruction"] for x in selected),
        "mask_area_quantiles": {
            str(q): float(np.quantile(area_values, q)) for q in (0.0, 0.25, 0.5, 0.75, 1.0)
        },
        "gt_changed_pixel_inside_min": float(locality_values.min()),
        "gt_changed_pixel_inside_median": float(np.median(locality_values)),
        "selected_review_flags": dict(sorted(flags.items())),
        "quota_config": {f"{k[0]}/{k[1]}": v for k, v in QUOTAS.items()},
        "notes": [
            "This is an automatic pre-selection for human review, not a frozen benchmark.",
            "GT locality requires >=80% of thresholded changed pixels inside a 2%-dilated region.",
            "A secondary guard requires >=40% of absolute RGB difference mass inside that region.",
            "HumanEdit masks use RGBA alpha < 128, not black RGB pixels.",
            "ReShapeBench has no GT image; released boxes require SAM2 refinement and manual validation.",
            "same_class_multi_instance_proxy is lexical/subset-based and must be verified visually.",
        ],
    }


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cv2.setNumThreads(1)
    feature_path = args.output / "all_preselection_features.jsonl"
    if args.reuse_features:
        if not feature_path.is_file():
            raise FileNotFoundError(f"cannot reuse missing feature manifest: {feature_path}")
        all_records = [json.loads(line) for line in feature_path.read_text().splitlines() if line.strip()]
        upgraded_features = False
        for record in all_records:
            if "scene_group_id" not in record:
                record["scene_group_id"] = (
                    comp_scene_id(record["source_record_id"])
                    if record["source_dataset"] == "CompBench"
                    else record["source_group_id"]
                )
                upgraded_features = True
        if upgraded_features:
            write_jsonl(feature_path, all_records)
            print("upgraded cached features with scene_group_id", flush=True)
        print(f"reused preselection features: {len(all_records)}", flush=True)
    else:
        comp = compbench_records(args.dataset_root, args.diff_threshold, args.workers)
        human = humanedit_records(args.dataset_root, args.diff_threshold, args.workers)
        reshape = reshapebench_records(args.dataset_root)
        all_records = comp + human + reshape
    pools: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in all_records:
        record["small_target"] = record["mask_area_ratio"] < 0.02
        pools[(record["source_dataset"], record["edit_type"])].append(record)
    selected = []
    used_scenes: set[str] = set()
    for key, quota in QUOTAS.items():
        group = select_group(pools[key], quota, args.seed, used_scenes)
        selected.extend(group)
        used_scenes.update(x["scene_group_id"] for x in group)
        print(f"selected {key[0]}/{key[1]}: {len(group)} (strict={sum(x['strict_eligible'] for x in group)})", flush=True)
    improve_global_quotas(selected, pools, args.seed)
    for record in selected:
        record["selection_score"] = record_score(record, args.seed)
    selected.sort(key=lambda x: (x["source_dataset"], x["edit_type"], x["candidate_id"]))
    for index, record in enumerate(selected):
        record["selection_index"] = index
        record["selection_version"] = "auto-v0-20260907"
        record["human_review_status"] = "pending"
        record["sam2_status"] = "pending" if record["source_dataset"] == "ReShapeBench" else "not_required"
    if not args.reuse_features:
        write_jsonl(feature_path, all_records)
    write_jsonl(args.output / "selected_500.jsonl", selected)
    write_csv(args.output / "selected_500.csv", selected)
    write_review_template(args.output / "human_review_template.csv", selected)
    report = summarize(all_records, selected)
    (args.output / "selection_stats.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
