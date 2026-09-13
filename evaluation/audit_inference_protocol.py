#!/usr/bin/env python3
"""Audit frozen inference records without computing quality metrics or calling judges."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from common import (
    DEFAULT_DATASET_ROOT,
    DEFAULT_DIT_LORA,
    DEFAULT_EXPERIMENT_ROOT,
    DEFAULT_PREPARED_MANIFEST,
    DEFAULT_QWEN_2511,
    DEFAULT_SAMTOK_REPO,
    DEFAULT_TE_LORA,
    SAMTOK_SPAN_RE,
    annotated_prompt,
    atomic_write_json,
    official_output_size,
    output_paths,
    read_jsonl,
    resolve_path,
    settings_for_model,
    sha256_file,
)


EXPECTED_TE_LORA_SHA256 = (
    "9ce0ad749df5b8602d9b741d4fb95b3081cdd86cd1dbba4a590b210f171aa119"
)
EXPECTED_DIT_LORA_SHA256 = (
    "b37743956d44704f0294d045d34b22217c8c17e294afba2de97693a98524d2b4"
)


def git_revision(path: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def expected_input_and_prompt(
    row: dict,
    setting,
    dataset_root: Path,
    prepared_root: Path,
) -> tuple[Path, str, str | None]:
    prepared = row["prepared"]
    source_path = resolve_path(row["source_image"], dataset_root)
    input_path = (
        source_path
        if setting.input_mode == "source"
        else resolve_path(prepared[setting.input_mode], prepared_root)
    )
    if setting.samtok_mode == "umt_mask":
        prompt = prepared["samtok_prompts"]["mask_umt"]
    elif setting.samtok_mode == "umt_box_sam2":
        prompt = prepared["samtok_prompts"]["box_sam2_umt"]
    elif setting.samtok_mode == "umt_point_sam2":
        prompt = prepared["samtok_prompts"]["point_sam2_umt"]
    elif setting.prompt_mode == "with_location_reference":
        prompt = row["instruction"]["with_location_reference"]
    else:
        prompt = annotated_prompt(
            row["instruction"]["region_only"],
            len(row["regions"]),
            setting.input_mode.removesuffix("_annotation"),
        )
    mt_cot = prepared["mask_mt_cot"] if setting.samtok_mode == "mt_mask" else None
    return input_path.resolve(), prompt, mt_cot


def check_run_config(
    model: str,
    config: dict,
    prepared_manifest: Path,
    expected_prepared_sha256: str,
    expected_seed: int,
) -> list[str]:
    errors = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(f"{model}/run_config: {message}")

    require(config.get("protocol") == "samtok_finegrained_edit_benchmark_inference_v1", "bad protocol")
    require(config.get("model") == model, "bad model identity")
    require(config.get("data", {}).get("prepared_manifest") == str(prepared_manifest.resolve()), "prepared manifest path mismatch")
    require(config.get("data", {}).get("prepared_manifest_sha256") == expected_prepared_sha256, "prepared manifest hash mismatch")
    require(config.get("data", {}).get("rows") == 500, "prepared row count is not 500")
    require(config.get("selection", {}).get("count") == 500, "selected row count is not 500")
    require(config.get("parallelism", {}).get("world_size") == 8, "world size is not 8")
    require(config.get("generation", {}).get("seed_rule") == f"constant seed={expected_seed} for every case and setting", "seed rule mismatch")
    require(config.get("fairness", {}).get("target_fields_used_as_model_input") is False, "target fields were not declared evaluator-only")
    require(config.get("fairness", {}).get("evaluation_mask_used_during_generation") is False, "evaluation mask generation flag is not false")
    expected_settings = [setting.__dict__ for setting in settings_for_model(model)]
    require(config.get("settings") == expected_settings, "setting definitions mismatch current frozen protocol")

    generation = config.get("generation", {})
    artifacts = config.get("model_artifacts", {})
    if model == "qwen":
        require(artifacts.get("name") == "Qwen-Image-Edit-2511", "wrong checkpoint name")
        require(artifacts.get("diffsynth_pipeline") == "QwenImagePipeline", "wrong DiffSynth pipeline")
        require(generation.get("num_inference_steps") == 40, "steps are not 40")
        require(generation.get("cfg_scale") == 4.0, "CFG is not 4")
        require(generation.get("zero_cond_t") is True, "zero_cond_t is not enabled")
    elif model == "flux2":
        require(artifacts.get("name") == "black-forest-labs/FLUX.2-klein-4B", "wrong checkpoint name")
        require(artifacts.get("diffsynth_pipeline") == "Flux2ImagePipeline", "wrong DiffSynth pipeline")
        require(generation.get("num_inference_steps") == 4, "steps are not 4")
        require(generation.get("cfg_scale") == 1.0, "CFG is not 1")
        require(generation.get("embedded_guidance") == 4.0, "embedded guidance is not 4")
    else:
        require(artifacts.get("name") == "SAMTokEdit refined four-node", "wrong method identity")
        require(artifacts.get("diffsynth_pipeline") == "QwenImageSamtokPipeline", "wrong method pipeline")
        require(artifacts.get("stage1_te_lora_sha256") == EXPECTED_TE_LORA_SHA256, "wrong Stage-1 TE LoRA hash")
        require(artifacts.get("stage2_dit_lora_sha256") == EXPECTED_DIT_LORA_SHA256, "wrong Stage-2 DiT LoRA hash")
        require(generation.get("num_inference_steps") == 40, "steps are not 40")
        require(generation.get("cfg_scale") == 4.0, "CFG is not 4")
        require(generation.get("zero_cond_t") is True, "zero_cond_t is not enabled")
        require(generation.get("samtok_max_new_tokens") == 128, "pass-1 token budget is not 128")
    return errors


def exact_pasteback_check(job: tuple[dict, dict]) -> str | None:
    source_record, paste_record = job
    with Image.open(source_record["output"]) as image:
        generated = np.asarray(image.convert("RGB"))
    with Image.open(paste_record["source_image"]) as image:
        source = np.asarray(image.convert("RGB"))
    with Image.open(paste_record["evaluation_mask"]) as image:
        mask = np.asarray(image.convert("L")) > 0
    with Image.open(paste_record["output"]) as image:
        actual = np.asarray(image.convert("RGB"))
    if generated.shape != source.shape or actual.shape != source.shape or mask.shape != source.shape[:2]:
        return f"{paste_record['model']}/{paste_record['eval_index']:04d}: paste-back shape mismatch"
    expected = np.where(mask[..., None], generated, source)
    if not np.array_equal(expected, actual):
        return f"{paste_record['model']}/{paste_record['eval_index']:04d}: paste-back pixel mismatch"
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment_root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--prepared_manifest", type=Path, default=DEFAULT_PREPARED_MANIFEST)
    parser.add_argument("--prepared_root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--dataset_root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--samtok_repo", type=Path, default=DEFAULT_SAMTOK_REPO)
    parser.add_argument("--qwen_2511", type=Path, default=DEFAULT_QWEN_2511)
    parser.add_argument("--te_lora", type=Path, default=DEFAULT_TE_LORA)
    parser.add_argument("--dit_lora", type=Path, default=DEFAULT_DIT_LORA)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--pasteback_workers", type=int, default=16)
    parser.add_argument("--skip_pasteback_pixels", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.pasteback_workers <= 0:
        raise ValueError("--pasteback_workers must be positive")
    output_path = args.output or args.experiment_root / "reports/inference_protocol_audit.json"
    rows = read_jsonl(args.prepared_manifest)
    errors: list[str] = []
    if len(rows) != 500 or [row.get("eval_index") for row in rows] != list(range(500)):
        errors.append("prepared manifest does not contain contiguous eval_index 0..499")
    prepared_sha = sha256_file(args.prepared_manifest)
    source_sizes = {}
    native_sizes = {}
    for row in rows:
        with Image.open(resolve_path(row["source_image"], args.dataset_root)) as image:
            source_sizes[row["eval_index"]] = image.size
            native_sizes[row["eval_index"]] = official_output_size(image)

    counts = Counter()
    telemetry = Counter()
    pasteback_jobs = []
    source_records: dict[tuple[str, int], dict] = {}
    results_jsonl = {}

    for model in ("qwen", "flux2", "samtok_edit"):
        model_root = args.experiment_root / "inference" / model
        config_path = model_root / "run_config.json"
        if not config_path.is_file():
            errors.append(f"missing run config: {config_path}")
            continue
        config = json.loads(config_path.read_text(encoding="utf-8"))
        errors.extend(
            check_run_config(model, config, args.prepared_manifest, prepared_sha, args.seed)
        )
        world_size = int(config.get("parallelism", {}).get("world_size", -1))
        for setting in settings_for_model(model):
            result_path = model_root / setting.key / "results.jsonl"
            result_rows = read_jsonl(result_path) if result_path.is_file() else []
            results_jsonl[f"{model}/{setting.key}"] = {
                "count": len(result_rows),
                "contiguous_indices": [record.get("eval_index") for record in result_rows]
                == list(range(500)),
            }
            if len(result_rows) != 500:
                errors.append(f"{model}/{setting.key}: results.jsonl count={len(result_rows)}")
            result_by_index = {record.get("eval_index"): record for record in result_rows}
            for row in rows:
                index = row["eval_index"]
                image_path, sidecar_path = output_paths(
                    args.experiment_root, model, setting.key, index
                )
                if not image_path.is_file() or not sidecar_path.is_file():
                    errors.append(f"{model}/{setting.key}/{index:04d}: missing image or sidecar")
                    continue
                record = json.loads(sidecar_path.read_text(encoding="utf-8"))
                if result_by_index.get(index) != record:
                    errors.append(f"{model}/{setting.key}/{index:04d}: results.jsonl differs from sidecar")
                input_path, prompt, mt_cot = expected_input_and_prompt(
                    row, setting, args.dataset_root, args.prepared_root
                )
                target_ref = row["target"]["reference_image"]
                expected_target = (
                    str(resolve_path(target_ref, args.dataset_root).resolve())
                    if target_ref
                    else None
                )
                expected_values = {
                    "eval_index": index,
                    "case_id": row["id"],
                    "model": model,
                    "setting": setting.key,
                    "source_dataset": row["source_dataset"],
                    "edit_type": row["edit_type"],
                    "region_count": len(row["regions"]),
                    "source_image": str(resolve_path(row["source_image"], args.dataset_root).resolve()),
                    "model_input_image": str(input_path),
                    "target_reference_image": expected_target,
                    "evaluation_mask": str(resolve_path(row["evaluation_mask"], args.dataset_root).resolve()),
                    "output": str(image_path.resolve()),
                    "with_location_instruction": row["instruction"]["with_location_reference"],
                    "region_only_instruction": row["instruction"]["region_only"],
                    "conditioned_prompt": prompt,
                    "seed": args.seed,
                    "native_generation_size": list(native_sizes[index]),
                    "saved_source_size": list(source_sizes[index]),
                    "world_size": world_size,
                    "worker_rank": index % world_size,
                }
                for key, expected in expected_values.items():
                    if record.get(key) != expected:
                        errors.append(
                            f"{model}/{setting.key}/{index:04d}: {key} mismatch"
                        )
                if setting.samtok_mode == "online":
                    predicted_spans = SAMTOK_SPAN_RE.findall(
                        record.get("conditioned_mt_cot") or ""
                    )
                    telemetry["online_records"] += 1
                    telemetry[f"online_parse/{record.get('parse_layer')}"] += 1
                    telemetry[f"online_span_count/{len(predicted_spans)}"] += 1
                    telemetry[
                        f"online_region_span_count/{len(row['regions'])}->{len(predicted_spans)}"
                    ] += 1
                    if not predicted_spans or not record.get("pass1_raw"):
                        errors.append(f"{model}/{setting.key}/{index:04d}: empty online CoT telemetry")
                elif setting.samtok_mode and setting.samtok_mode.startswith("umt_"):
                    spans = [match.group(0) for match in SAMTOK_SPAN_RE.finditer(prompt)]
                    audit = record.get("user_mask_audit") or {}
                    telemetry[f"{setting.key}_records"] += 1
                    if not (
                        len(spans) == len(row["regions"])
                        and record.get("conditioned_mt_cot") is None
                        and record.get("pass1_raw") is None
                        and record.get("parse_layer") is None
                        and audit.get("user_mask_span_count") == len(spans)
                        and audit.get("user_mask_spans_atomic") is True
                        and audit.get("user_mask_spans_in_template") is True
                        and all(len(ids) == 4 for ids in audit.get("user_mask_span_token_ids", []))
                    ):
                        errors.append(f"{model}/{setting.key}/{index:04d}: invalid UMT telemetry")
                    else:
                        telemetry[f"{setting.key}_token_audit_passed"] += 1
                elif setting.samtok_mode == "mt_mask":
                    telemetry["mask_mt_records"] += 1
                    if not (
                        record.get("conditioned_mt_cot") == mt_cot
                        and record.get("pass1_raw") is None
                        and record.get("parse_layer") == "provided:strict"
                    ):
                        errors.append(f"{model}/{setting.key}/{index:04d}: invalid explicit MT telemetry")
                    else:
                        telemetry["mask_mt_exact_cot_passed"] += 1
                if setting.key == "mask_annotation":
                    source_records[(model, index)] = record
                if setting.pasteback:
                    expected_derived, _ = output_paths(
                        args.experiment_root, model, setting.derived_from, index
                    )
                    if record.get("derived_from_output") != str(expected_derived.resolve()):
                        errors.append(f"{model}/{setting.key}/{index:04d}: paste-back provenance mismatch")
                    pasteback_jobs.append((source_records[(model, index)], record))
                counts[f"{model}/{setting.key}"] += 1

    pasteback_errors = []
    if not args.skip_pasteback_pixels:
        with ThreadPoolExecutor(max_workers=args.pasteback_workers) as pool:
            pasteback_errors = [error for error in pool.map(exact_pasteback_check, pasteback_jobs) if error]
        errors.extend(pasteback_errors)

    full_report_path = args.experiment_root / "reports/full_inference_report.json"
    full_report = json.loads(full_report_path.read_text(encoding="utf-8"))
    if full_report.get("status") != "passed" or full_report.get("total_result_images") != 7500:
        errors.append("full output validation report is not passed/7500")

    te_lora_sha256 = sha256_file(args.te_lora)
    dit_lora_sha256 = sha256_file(args.dit_lora)
    report = {
        "status": "passed" if not errors else "failed",
        "scope": "inference protocol and provenance only; no quality metrics and no judge calls",
        "reference_implementations": {
            "samtok_repo": str(args.samtok_repo.resolve()),
            "samtok_repo_current_git_commit": git_revision(args.samtok_repo),
            "qwen_and_flux_diffsynth": str((args.samtok_repo / "DiffSynth-Studio").resolve()),
            "samtok_pipeline": str((args.samtok_repo / "scripts/inference/infer_samtok_edit.py").resolve()),
        },
        "frozen_inputs": {
            "prepared_manifest": str(args.prepared_manifest.resolve()),
            "prepared_manifest_sha256": prepared_sha,
            "rows": len(rows),
        },
        "model_artifact_checks": {
            "qwen_2511_model_index_sha256": sha256_file(args.qwen_2511 / "model_index.json"),
            "stage1_te_lora_sha256": te_lora_sha256,
            "stage1_te_lora_matches_expected": te_lora_sha256 == EXPECTED_TE_LORA_SHA256,
            "stage2_dit_lora_sha256": dit_lora_sha256,
            "stage2_dit_lora_matches_expected": dit_lora_sha256 == EXPECTED_DIT_LORA_SHA256,
        },
        "records": {
            "sidecars_checked": sum(counts.values()),
            "counts": dict(sorted(counts.items())),
            "results_jsonl": results_jsonl,
            "telemetry": dict(sorted(telemetry.items())),
        },
        "pasteback_pixel_audit": {
            "enabled": not args.skip_pasteback_pixels,
            "checked": 0 if args.skip_pasteback_pixels else len(pasteback_jobs),
            "passed": 0 if args.skip_pasteback_pixels else len(pasteback_jobs) - len(pasteback_errors),
            "failed": len(pasteback_errors),
        },
        "full_output_validation": {
            "path": str(full_report_path.resolve()),
            "sha256": sha256_file(full_report_path),
            "status": full_report.get("status"),
            "result_images": full_report.get("total_result_images"),
            "missing": full_report.get("missing_count"),
        },
        "error_count": len(errors),
        "first_errors": errors[:100],
    }
    atomic_write_json(output_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
