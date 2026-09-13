#!/usr/bin/env python3
"""Freeze visual prompts, SAM2 interaction masks, and SAMTok spans."""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from common import (
    DEFAULT_DATASET_ROOT,
    DEFAULT_EXPERIMENT_ROOT,
    DEFAULT_MANIFEST,
    DEFAULT_PREPARED_MANIFEST,
    DEFAULT_SAMTOK_REPO,
    DEFAULT_SAMTOK_TE,
    SAM2_MODEL_ID,
    SAM2_REVISION,
    atomic_write_json,
    atomic_write_jsonl,
    load_benchmark,
    relative_to_root,
    render_annotation,
    resolve_path,
    sha256_file,
    token_prompt,
    verify_image,
)


DEFAULT_MODEL_CACHE = Path("/mnt/bn/strategy-mllm-train/user/tanyue/datasets/model_cache")


def binary_mask(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L")) > 0


def save_binary_mask(path: Path, mask: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.png")
    Image.fromarray((np.asarray(mask, dtype=np.uint8) * 255), "L").save(temporary)
    temporary.replace(path)


def mask_iou(first: np.ndarray, second: np.ndarray) -> float:
    intersection = np.logical_and(first, second).sum()
    union = np.logical_or(first, second).sum()
    return float(intersection / union) if union else 1.0


def fallback_mask(row: dict, region_index: int, modality: str, size: tuple[int, int]) -> np.ndarray:
    width, height = size
    mask = np.zeros((height, width), dtype=bool)
    region = row["regions"][region_index]
    if modality == "box":
        x1, y1, x2, y2 = region["box"]
        mask[y1:y2, x1:x2] = True
    else:
        x, y = region["point"]
        radius = max(3, round(min(size) * 0.015))
        yy, xx = np.ogrid[:height, :width]
        mask[(xx - x) ** 2 + (yy - y) ** 2 <= radius**2] = True
    return mask


class Sam2InteractiveSegmenter:
    def __init__(self, device: str, cache_dir: Path):
        from transformers import Sam2Model, Sam2Processor

        self.device = device
        self.processor = Sam2Processor.from_pretrained(
            SAM2_MODEL_ID,
            revision=SAM2_REVISION,
            cache_dir=cache_dir,
            local_files_only=True,
        )
        self.model = Sam2Model.from_pretrained(
            SAM2_MODEL_ID,
            revision=SAM2_REVISION,
            cache_dir=cache_dir,
            dtype=torch.float32,
            local_files_only=True,
        ).to(device).eval()

    @torch.inference_mode()
    def segment(self, image: Image.Image, row: dict, modality: str) -> tuple[list[np.ndarray], list[dict]]:
        if modality == "box":
            kwargs = {"input_boxes": [[region["box"] for region in row["regions"]]]}
        elif modality == "point":
            # [image, object, point, xy]; one positive click for each object.
            kwargs = {
                "input_points": [
                    [[list(region["point"])] for region in row["regions"]]
                ],
                "input_labels": [
                    [[1] for _ in row["regions"]]
                ],
            }
        else:
            raise ValueError(modality)
        inputs = self.processor(images=image, return_tensors="pt", **kwargs).to(self.device)
        outputs = self.model(**inputs, multimask_output=True)
        predictions = self.processor.post_process_masks(
            outputs.pred_masks.detach().cpu(), inputs["original_sizes"].detach().cpu()
        )[0].numpy().astype(bool)
        scores = outputs.iou_scores[0].detach().cpu().numpy()
        if predictions.shape[0] != len(row["regions"]):
            raise RuntimeError(
                f"SAM2 returned {predictions.shape[0]} objects for {len(row['regions'])} prompts"
            )
        selected, diagnostics = [], []
        for region_index, (candidates, candidate_scores) in enumerate(zip(predictions, scores)):
            best = int(np.argmax(candidate_scores))
            mask = candidates[best]
            method = "sam2"
            if not mask.any():
                mask = fallback_mask(row, region_index, modality, image.size)
                method = f"{modality}_geometry_fallback_after_empty_sam2"
            reference = binary_mask(
                resolve_path(row["regions"][region_index]["mask"], self.dataset_root)
            )
            selected.append(mask)
            diagnostics.append(
                {
                    "method": method,
                    "selected_candidate": best,
                    "predicted_iou_scores": [round(float(value), 7) for value in candidate_scores],
                    "input_mask_iou": round(mask_iou(mask, reference), 7),
                    "mask_area_ratio": round(float(mask.mean()), 7),
                }
            )
        return selected, diagnostics


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
) -> None:
    def render_one(row: dict) -> int:
        cache = load_case_cache(experiment_root, row)
        source_path = resolve_path(row["source_image"], dataset_root)
        with Image.open(source_path) as image:
            source = image.convert("RGB")
        for modality in ("mask", "box", "point"):
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
        completed = pool.map(render_one, rows)
        for position, _ in enumerate(completed, 1):
            if position % 25 == 0 or position == len(rows):
                print(f"[render] {position}/{len(rows)}", flush=True)


def prepare_sam2_masks(
    rows: list[dict],
    dataset_root: Path,
    experiment_root: Path,
    device: str,
    model_cache: Path,
    resume: bool,
) -> None:
    segmenter = Sam2InteractiveSegmenter(device, model_cache)
    segmenter.dataset_root = dataset_root
    for position, row in enumerate(rows, 1):
        cache = load_case_cache(experiment_root, row)
        source_path = resolve_path(row["source_image"], dataset_root)
        with Image.open(source_path) as image:
            source = image.convert("RGB")
        for modality in ("box", "point"):
            mask_key = f"{modality}_sam2_masks"
            diagnostic_key = f"{modality}_sam2_diagnostics"
            paths = [
                experiment_root / "inputs" / mask_key / f"{row['eval_index']:04d}_r{i + 1}.png"
                for i in range(len(row["regions"]))
            ]
            cached_paths = cache["prepared"].get(mask_key)
            cached_diagnostics = cache["prepared"].get(diagnostic_key)
            valid = (
                resume
                and cached_paths
                and cached_diagnostics
                and len(cached_paths) == len(paths)
                and all(path.is_file() and verify_image(path) == source.size for path in paths)
            )
            if valid:
                continue
            masks, diagnostics = segmenter.segment(source, row, modality)
            for path, mask in zip(paths, masks):
                save_binary_mask(path, mask)
            cache["prepared"][mask_key] = [
                relative_to_root(path, experiment_root) for path in paths
            ]
            cache["prepared"][diagnostic_key] = diagnostics
            write_case_cache(experiment_root, row["eval_index"], cache)
        if position % 10 == 0 or position == len(rows):
            print(f"[sam2] {position}/{len(rows)}", flush=True)
    del segmenter
    gc.collect()
    torch.cuda.empty_cache()


def token_cache_path(experiment_root: Path, modality: str, index: int, region_index: int) -> Path:
    return experiment_root / "prepared/token_spans" / modality / f"{index:04d}_r{region_index + 1}.json"


def prepare_samtok_spans(
    rows: list[dict],
    dataset_root: Path,
    experiment_root: Path,
    samtok_repo: Path,
    samtok_te: Path,
    device: str,
    batch_size: int,
    resume: bool,
) -> None:
    for path in (samtok_repo, samtok_repo / "DiffSynth-Studio", samtok_repo / "scripts/data"):
        sys.path.insert(0, str(path))
    from samtok_codec import SamtokCodec

    codec = SamtokCodec(
        samtok_te / "sam2.1_hiera_large.pt",
        samtok_te / "mask_tokenizer_256x2.pth",
        device=device,
        dtype=torch.float32,
    )
    tasks: list[tuple[int, str, int, Path, Path]] = []
    for row in rows:
        cache = load_case_cache(experiment_root, row)
        modality_paths = {
            "mask": [resolve_path(region["mask"], dataset_root) for region in row["regions"]],
            "box_sam2": [resolve_path(path, experiment_root) for path in cache["prepared"]["box_sam2_masks"]],
            "point_sam2": [resolve_path(path, experiment_root) for path in cache["prepared"]["point_sam2_masks"]],
        }
        for modality, paths in modality_paths.items():
            for region_index, mask_path in enumerate(paths):
                token_path = token_cache_path(
                    experiment_root, modality, row["eval_index"], region_index
                )
                if resume and token_path.is_file():
                    continue
                tasks.append(
                    (
                        row["eval_index"], modality, region_index,
                        resolve_path(row["source_image"], dataset_root), mask_path,
                    )
                )
    print(f"[samtok] encoding {len(tasks)} uncached region/modality pairs", flush=True)
    for start in range(0, len(tasks), batch_size):
        batch = tasks[start : start + batch_size]
        pairs = []
        for _, _, _, image_path, mask_path in batch:
            with Image.open(image_path) as image:
                source = image.convert("RGB")
            pairs.append((source, binary_mask(mask_path)))
        spans = codec.encode_single_batch(pairs)
        for (index, modality, region_index, _, _), span in zip(batch, spans):
            atomic_write_json(
                token_cache_path(experiment_root, modality, index, region_index),
                {"eval_index": index, "region_index": region_index, "modality": modality, "span": span},
            )
        done = min(start + len(batch), len(tasks))
        print(f"[samtok] {done}/{len(tasks)}", flush=True)
    del codec
    gc.collect()
    torch.cuda.empty_cache()


def assemble_prepared_manifest(
    rows: list[dict],
    dataset_root: Path,
    experiment_root: Path,
    output_manifest: Path,
    samtok_repo: Path,
    samtok_te: Path,
) -> tuple[list[dict], dict]:
    for path in (samtok_repo / "DiffSynth-Studio",):
        sys.path.insert(0, str(path))
    from diffsynth.core.data.samtok_dataset import to_cot

    prepared_rows = []
    ious: dict[tuple[str, str], list[float]] = defaultdict(list)
    token_collision_cases = defaultdict(list)
    for row in rows:
        cache = load_case_cache(experiment_root, row)
        prepared = cache["prepared"]
        spans_by_modality = {}
        for modality in ("mask", "box_sam2", "point_sam2"):
            spans = []
            for region_index in range(len(row["regions"])):
                path = token_cache_path(
                    experiment_root, modality, row["eval_index"], region_index
                )
                if not path.is_file():
                    raise FileNotFoundError(f"Missing SAMTok span cache: {path}")
                item = json.loads(path.read_text(encoding="utf-8"))
                spans.append(item["span"])
            spans_by_modality[modality] = spans
        prepared["samtok_spans"] = spans_by_modality
        for modality, spans in spans_by_modality.items():
            if len(spans) != len(set(spans)):
                token_collision_cases[modality].append(row["id"])
        prepared["samtok_prompts"] = {
            "mask_umt": token_prompt(row["instruction"]["region_only"], spans_by_modality["mask"]),
            "box_sam2_umt": token_prompt(row["instruction"]["region_only"], spans_by_modality["box_sam2"]),
            "point_sam2_umt": token_prompt(row["instruction"]["region_only"], spans_by_modality["point_sam2"]),
        }
        # Labels are deliberately generic. target.expected_* is evaluator-only and
        # must never leak into a model input, including an explicit assistant CoT.
        prepared["mask_mt_cot"] = to_cot(
            [(span, f"region {index + 1}") for index, span in enumerate(spans_by_modality["mask"])]
        )
        output = dict(row)
        output["prepared"] = prepared
        prepared_rows.append(output)
        for modality in ("box", "point"):
            for diagnostic in prepared[f"{modality}_sam2_diagnostics"]:
                ious[(modality, row["edit_type"])].append(diagnostic["input_mask_iou"])
    atomic_write_jsonl(output_manifest, prepared_rows)
    diagnostic_summary = {}
    for (modality, edit_type), values in sorted(ious.items()):
        diagnostic_summary[f"{modality}/{edit_type}"] = {
            "count": len(values),
            "mean_input_mask_iou": round(float(np.mean(values)), 6),
            "median_input_mask_iou": round(float(np.median(values)), 6),
        }
    report = {
        "status": "complete",
        "protocol": "samtok_finegrained_edit_input_preparation_v1",
        "benchmark_manifest": str((dataset_root / "benchmark.jsonl").resolve()),
        "benchmark_manifest_sha256": sha256_file(dataset_root / "benchmark.jsonl"),
        "prepared_manifest": str(output_manifest.resolve()),
        "prepared_manifest_sha256": sha256_file(output_manifest),
        "rows": len(prepared_rows),
        "visual_prompt_rendering": {
            "region_colors": ["red", "green", "blue"],
            "labels": "single-region inputs are unnumbered; multi-region inputs use R1, R2, ...",
            "mask_fill_alpha": 70,
            "mask_outline_relative_width": "max(3 px, 0.6% short side)",
            "point_radius": "max(7 px, 1.4% short side)",
            "vector_antialiasing": "4x supersampling",
        },
        "sam2": {
            "model_id": SAM2_MODEL_ID,
            "revision": SAM2_REVISION,
            "selection": "highest predicted-IoU candidate per independent box/positive-point prompt",
            "diagnostic_iou_against_benchmark_input_mask": diagnostic_summary,
        },
        "samtok": {
            "source_checkpoint": str(samtok_te.resolve()),
            "input_modalities": ["benchmark mask", "box-prompted SAM2 mask", "point-prompted SAM2 mask"],
            "multi_region_order": "benchmark regions array order; no codec sorting",
            "mask_mt_labels": "generic region N labels; target evaluator fields are never consumed",
            "within_case_duplicate_span_counts": {
                modality: len(token_collision_cases.get(modality, []))
                for modality in ("mask", "box_sam2", "point_sam2")
            },
            "within_case_duplicate_span_ids": dict(sorted(token_collision_cases.items())),
        },
    }
    atomic_write_json(experiment_root / "prepared/preparation_report.json", report)
    return prepared_rows, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dataset_root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--experiment_root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--output_manifest", type=Path, default=DEFAULT_PREPARED_MANIFEST)
    parser.add_argument("--samtok_repo", type=Path, default=DEFAULT_SAMTOK_REPO)
    parser.add_argument("--samtok_te", type=Path, default=DEFAULT_SAMTOK_TE)
    parser.add_argument("--model_cache", type=Path, default=DEFAULT_MODEL_CACHE)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--codec_batch_size", type=int, default=32)
    parser.add_argument("--render_workers", type=int, default=16)
    parser.add_argument(
        "--stages", nargs="+", choices=("render", "sam2", "samtok", "assemble"),
        default=["render", "sam2", "samtok", "assemble"],
    )
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.codec_batch_size <= 0 or args.render_workers <= 0:
        raise ValueError("batch size and worker count must be positive")
    rows, data_report = load_benchmark(args.manifest, args.dataset_root, verify_assets=True)
    args.experiment_root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(args.experiment_root / "prepared/benchmark_validation.json", data_report)
    started = time.perf_counter()
    if "render" in args.stages:
        render_inputs(
            rows, args.dataset_root, args.experiment_root, args.resume, args.render_workers
        )
    if "sam2" in args.stages:
        prepare_sam2_masks(
            rows, args.dataset_root, args.experiment_root, args.device, args.model_cache, args.resume
        )
    if "samtok" in args.stages:
        prepare_samtok_spans(
            rows, args.dataset_root, args.experiment_root, args.samtok_repo,
            args.samtok_te, args.device, args.codec_batch_size, args.resume,
        )
    if "assemble" in args.stages:
        _, report = assemble_prepared_manifest(
            rows,
            args.dataset_root,
            args.experiment_root,
            args.output_manifest,
            args.samtok_repo,
            args.samtok_te,
        )
        report["elapsed_seconds"] = time.perf_counter() - started
        atomic_write_json(args.experiment_root / "prepared/preparation_report.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
