#!/usr/bin/env python3
"""Render and freeze the two-reference inputs for Qwen and FLUX.2."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from common import (
    BASELINE_VISUAL_PROTOCOL,
    DEFAULT_DATASET_ROOT,
    DEFAULT_EXPERIMENT_ROOT,
    DEFAULT_MANIFEST,
    atomic_write_json,
    atomic_write_jsonl,
    load_benchmark,
    relative_to_root,
    render_annotation,
    resolve_path,
    sha256_file,
    two_image_locator_prompt,
    verify_image,
)


def case_cache_path(experiment_root: Path, index: int) -> Path:
    return experiment_root / "prepared/cases" / f"{index:04d}.json"


def load_case_cache(experiment_root: Path, row: dict) -> dict:
    path = case_cache_path(experiment_root, row["eval_index"])
    if not path.is_file():
        return {"case_id": row["id"], "prepared": {}}
    cached = json.loads(path.read_text(encoding="utf-8"))
    if cached.get("case_id") != row["id"]:
        raise ValueError(f"Prepared cache identity mismatch: {path}")
    return cached


def write_case_cache(experiment_root: Path, index: int, value: dict) -> None:
    atomic_write_json(case_cache_path(experiment_root, index), value)


def render_inputs(
    rows: list[dict],
    dataset_root: Path,
    experiment_root: Path,
    resume: bool,
    workers: int,
    modalities: tuple[str, ...],
) -> None:
    def render_one(row: dict) -> int:
        cache = load_case_cache(experiment_root, row)
        source_path = resolve_path(row["source_image"], dataset_root)
        with Image.open(source_path) as image:
            source = image.convert("RGB")
        for modality in modalities:
            key = f"{modality}_annotation"
            path = experiment_root / "inputs" / key / f"{row['eval_index']:04d}.png"
            if not (resume and path.is_file() and verify_image(path) == source.size):
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(f".{path.name}.tmp.png")
                render_annotation(source, row["regions"], dataset_root, modality).save(temporary)
                temporary.replace(path)
            cache["prepared"][key] = relative_to_root(path, experiment_root)
        write_case_cache(experiment_root, row["eval_index"], cache)
        return row["eval_index"]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for position, _ in enumerate(pool.map(render_one, rows), 1):
            if position % 25 == 0 or position == len(rows):
                print(f"[render] {position}/{len(rows)}", flush=True)


def assemble_manifest(
    rows: list[dict], dataset_root: Path, experiment_root: Path
) -> dict:
    """Freeze the exact ordered image lists and prompts consumed at inference."""

    manifest_path = experiment_root / "prepared/baseline_inputs.jsonl"
    inference_manifest_path = (
        experiment_root / "prepared/benchmark_baseline_eval_inputs.jsonl"
    )
    manifest_rows = []
    inference_rows = []
    for row in rows:
        prepared = load_case_cache(experiment_root, row)["prepared"]
        source_path = resolve_path(row["source_image"], dataset_root).resolve()
        settings = {
            "text_only": {
                "images": [str(source_path)],
                "image_roles": ["clean_source_to_edit"],
                "prompt": row["instruction"]["with_location_reference"],
            }
        }
        for modality in ("mask", "box", "point"):
            key = f"{modality}_annotation"
            if key not in prepared:
                raise FileNotFoundError(f"Missing rendered input for {row['id']}: {key}")
            locator_path = resolve_path(prepared[key], experiment_root).resolve()
            settings[key] = {
                "images": [str(source_path), str(locator_path)],
                "image_roles": ["clean_source_to_edit", f"{modality}_locator_only"],
                "prompt": two_image_locator_prompt(
                    row["instruction"]["region_only"], len(row["regions"]), modality
                ),
            }
        manifest_rows.append(
            {
                "eval_index": row["eval_index"],
                "case_id": row["id"],
                "source_dataset": row["source_dataset"],
                "edit_type": row["edit_type"],
                "settings": settings,
            }
        )
        inference_row = dict(row)
        inference_row["prepared"] = {
            key: prepared[key]
            for key in ("mask_annotation", "box_annotation", "point_annotation")
        }
        inference_row["prepared"]["baseline_visual_protocol"] = BASELINE_VISUAL_PROTOCOL
        inference_row["prepared"]["baseline_inputs"] = settings
        inference_rows.append(inference_row)

    atomic_write_jsonl(manifest_path, manifest_rows)
    atomic_write_jsonl(inference_manifest_path, inference_rows)
    report = {
        "status": "complete",
        "protocol": BASELINE_VISUAL_PROTOCOL,
        "rows": len(rows),
        "settings_per_row": [
            "text_only", "mask_annotation", "box_annotation", "point_annotation"
        ],
        "manifest": str(manifest_path.resolve()),
        "manifest_sha256": sha256_file(manifest_path),
        "baseline_prepared_manifest": str(inference_manifest_path.resolve()),
        "baseline_prepared_manifest_sha256": sha256_file(inference_manifest_path),
        "target_fields_used": False,
        "reference_image_policy": {
            "text_only": ["clean_source_to_edit"],
            "mask_box_point": ["clean_source_to_edit", "annotated_locator_only"],
            "ordering_is_semantic": True,
            "target_reference_is_never_included": True,
        },
        "visual_markers": (
            "mask/box/point are rendered into locator-only copies of the source image; "
            "the clean source remains the first reference and points use a moderately "
            "sized colored dot with a thin white outline"
        ),
        "prompt_policy": (
            "each prompt names the first image as the clean source to edit and the second "
            "as locator-only, identifies the marker and exact point center, and asks the "
            "model to output the edited first image without reproducing locator markers"
        ),
    }
    atomic_write_json(experiment_root / "prepared/baseline_input_report.json", report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dataset_root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--experiment_root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--render_workers", type=int, default=16)
    parser.add_argument(
        "--render_modalities",
        nargs="+",
        choices=("mask", "box", "point"),
        default=["mask", "box", "point"],
    )
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.render_workers <= 0:
        raise ValueError("--render_workers must be positive")
    rows, data_report = load_benchmark(args.manifest, args.dataset_root, verify_assets=True)
    args.experiment_root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(args.experiment_root / "prepared/benchmark_validation.json", data_report)
    render_inputs(
        rows,
        args.dataset_root,
        args.experiment_root,
        args.resume,
        args.render_workers,
        tuple(args.render_modalities),
    )
    report = assemble_manifest(rows, args.dataset_root, args.experiment_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
