#!/usr/bin/env python3
"""Structurally validate baseline inference outputs without quality metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import (
    BASELINE_VISUAL_PROTOCOL,
    DEFAULT_BASELINE_PREPARED_MANIFEST,
    DEFAULT_DATASET_ROOT,
    DEFAULT_EXPERIMENT_ROOT,
    completed_record,
    load_prepared_manifest,
    parse_settings,
    resolve_path,
    sha256_file,
    verify_image,
)


MODELS = ("qwen", "flux2")
SETTING_KEYS = ("text_only", "mask_annotation", "box_annotation", "point_annotation")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment_root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument(
        "--prepared_manifest", type=Path, default=DEFAULT_BASELINE_PREPARED_MANIFEST
    )
    parser.add_argument("--prepared_root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--dataset_root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument(
        "--eval_indices",
        nargs="+",
        type=int,
        default=None,
        help="Validate only these exact benchmark eval indices.",
    )
    parser.add_argument("--expected_world_size", type=int, default=8)
    args = parser.parse_args()

    all_rows, prepared_report = load_prepared_manifest(
        args.prepared_manifest, args.prepared_root
    )
    if args.eval_indices is None:
        selected_indices = [row["eval_index"] for row in all_rows]
    else:
        if len(set(args.eval_indices)) != len(args.eval_indices):
            raise ValueError("--eval_indices contains duplicates")
        invalid = [index for index in args.eval_indices if not 0 <= index < len(all_rows)]
        if invalid:
            raise ValueError(f"Invalid --eval_indices: {invalid}")
        selected_indices = args.eval_indices
    rows = [all_rows[index] for index in selected_indices]
    expected_hash = sha256_file(args.prepared_manifest)
    source_sizes = {
        row["eval_index"]: verify_image(resolve_path(row["source_image"], args.dataset_root))
        for row in rows
    }
    errors: list[str] = []
    counts: dict[str, dict[str, int]] = {}
    for model in MODELS:
        counts[model] = {}
        config_path = args.experiment_root / "inference" / model / "run_config.json"
        report_path = args.experiment_root / "inference" / model / "report.json"
        if not config_path.is_file():
            errors.append(f"missing run config: {config_path}")
            continue
        config = json.loads(config_path.read_text(encoding="utf-8"))
        expected_settings = [
            setting.__dict__ for setting in parse_settings(model, list(SETTING_KEYS))
        ]
        selection = config.get("selection", {})
        selection_matches = selection.get("eval_indices") == selected_indices
        if not selection_matches and selected_indices == list(
            range(selected_indices[0], selected_indices[-1] + 1)
        ):
            # Accept run configs written before exact non-contiguous selections
            # were added to the inference runner.
            selection_matches = (
                selection.get("eval_index_start") == selected_indices[0]
                and selection.get("eval_index_stop_inclusive") == selected_indices[-1]
            )
        checks = {
            "protocol": config.get("protocol")
            == "samtok_finegrained_edit_benchmark_inference_v2",
            "model": config.get("model") == model,
            "world_size": config.get("parallelism", {}).get("world_size")
            == args.expected_world_size,
            "selection": selection_matches,
            "settings": config.get("settings") == expected_settings,
            "prepared_manifest": config.get("data", {}).get("prepared_manifest")
            == str(args.prepared_manifest.resolve()),
            "prepared_hash": config.get("data", {}).get("prepared_manifest_sha256")
            == expected_hash,
            "target_not_input": config.get("fairness", {}).get(
                "target_fields_used_as_model_input"
            )
            is False,
            "evaluation_mask_not_generation_input": config.get("fairness", {}).get(
                "evaluation_mask_used_during_generation"
            )
            is False,
            "two_image_locator_policy": config.get("reference_image_policy")
            == {
                "text_only": ["clean_source_to_edit"],
                "mask_box_point": ["clean_source_to_edit", "annotated_locator_only"],
                "ordered_edit_image_list": True,
            },
            "prepared_visual_protocol": prepared_report.get("baseline_visual_protocol")
            == BASELINE_VISUAL_PROTOCOL,
        }
        errors.extend(f"{model}/run_config: failed {key}" for key, ok in checks.items() if not ok)
        if not report_path.is_file():
            errors.append(f"missing model report: {report_path}")
        for setting in SETTING_KEYS:
            count = 0
            for row in rows:
                record = completed_record(
                    args.experiment_root,
                    model,
                    setting,
                    row["eval_index"],
                    row["id"],
                    source_sizes[row["eval_index"]],
                )
                if record is None:
                    errors.append(f"{model}/{setting}/{row['eval_index']:04d}: missing or invalid")
                else:
                    frozen = row["prepared"]["baseline_inputs"][setting]
                    expected_images = [str(Path(path).resolve()) for path in frozen["images"]]
                    if record.get("model_input_images") != expected_images:
                        errors.append(
                            f"{model}/{setting}/{row['eval_index']:04d}: input-image list mismatch"
                        )
                    if record.get("model_input_roles") != frozen["image_roles"]:
                        errors.append(
                            f"{model}/{setting}/{row['eval_index']:04d}: input-role list mismatch"
                        )
                    if record.get("conditioned_prompt") != frozen["prompt"]:
                        errors.append(
                            f"{model}/{setting}/{row['eval_index']:04d}: prompt mismatch"
                        )
                    count += 1
            counts[model][setting] = count
    expected = len(rows) * len(MODELS) * len(SETTING_KEYS)
    actual = sum(value for model in counts.values() for value in model.values())
    result = {
        "status": "passed" if not errors and actual == expected else "failed",
        "validation_only": True,
        "quality_metrics_computed": False,
        "judge_called": False,
        "selected_indices": selected_indices,
        "expected_world_size": args.expected_world_size,
        "prepared_data": prepared_report,
        "models": counts,
        "result_images": actual,
        "expected_result_images": expected,
        "errors": errors[:200],
        "error_count": len(errors),
    }
    output = args.experiment_root / "reports/baseline_inference_validation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
