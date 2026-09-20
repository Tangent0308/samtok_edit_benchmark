#!/usr/bin/env python3
"""Check structure and provenance of all RePlan SAMTok generations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__:
    from .runner import MANIFEST, OUTPUT_ROOT, SETTINGS, image_size, sha256, write_json
else:
    from runner import MANIFEST, OUTPUT_ROOT, SETTINGS, image_size, sha256, write_json


MODELS = ("qwen2511", "flux2_klein4b")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS))
    parser.add_argument("--settings", nargs="+", choices=SETTINGS, default=list(SETTINGS))
    parser.add_argument("--indices", nargs="+", type=int)
    parser.add_argument("--expected-world-size", type=int, default=8)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line]
    if args.indices is not None:
        if len(args.indices) != len(set(args.indices)):
            parser.error("--indices contains duplicates")
        known_indices = {row["eval_index"] for row in rows}
        if any(index not in known_indices for index in args.indices):
            parser.error("--indices contains an unknown eval_index")
        requested = set(args.indices)
        rows = [row for row in rows if row["eval_index"] in requested]
    digest = sha256(args.manifest)
    selected_indices = [row["eval_index"] for row in rows]
    errors = []
    counts = {}
    source_sizes = {
        row["eval_index"]: image_size(Path(row["prepared"]["baseline_inputs"]["text_only"]["images"][0]))
        for row in rows
    }
    for model in args.models:
        counts[model] = {}
        config_path = args.output_root / "inference" / model / "run_config.json"
        if not config_path.is_file():
            errors.append(f"Missing {config_path}")
        else:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            configured_indices = config.get("eval_indices")
            indices_match = (
                configured_indices == selected_indices if args.indices is None
                else isinstance(configured_indices, list)
                and set(selected_indices).issubset(configured_indices)
            )
            configured_settings = config.get("settings")
            settings_match = (
                configured_settings == args.settings if args.settings == list(SETTINGS)
                else isinstance(configured_settings, list)
                and all(setting in configured_settings for setting in args.settings)
            )
            if (
                config.get("model") != model
                or config.get("manifest_sha256") != digest
                or config.get("world_size") != args.expected_world_size
                or not indices_match
                or not settings_match
            ):
                errors.append(f"Wrong manifest, selection, settings or world size: {config_path}")
        for setting in args.settings:
            counts[model][setting] = 0
            for row in rows:
                index = row["eval_index"]
                prefix = args.output_root / "inference" / model / setting / f"{index:04d}"
                image_path = prefix.with_suffix(".png")
                json_path = prefix.with_suffix(".json")
                if not image_path.is_file() or not json_path.is_file():
                    errors.append(f"Missing {prefix} PNG or JSON")
                    continue
                try:
                    record = json.loads(json_path.read_text(encoding="utf-8"))
                    frozen = row["prepared"]["baseline_inputs"][setting]
                    expected_size = source_sizes[index]
                    if record["case_id"] != row["id"] or record["eval_index"] != index:
                        raise ValueError("case ID/index mismatch")
                    if record["model"] != model or record["setting"] != setting:
                        raise ValueError("model/setting mismatch")
                    if record["manifest_sha256"] != digest:
                        raise ValueError("manifest hash mismatch")
                    if record["planner_input_images"] != frozen["images"]:
                        raise ValueError("planner input image order mismatch")
                    if record["planner_image_roles"] != frozen["image_roles"]:
                        raise ValueError("planner image roles mismatch")
                    if record["planner_prompt"] != frozen["prompt"]:
                        raise ValueError("planner prompt mismatch")
                    if record["edit_input_image"] != frozen["images"][0]:
                        raise ValueError("editor did not use clean source")
                    if image_size(image_path) != expected_size or record["saved_size"] != list(expected_size):
                        raise ValueError("saved dimensions mismatch")
                    if record.get("source_size") != list(expected_size):
                        raise ValueError("source dimensions mismatch")
                    if record.get("output_image") != str(image_path):
                        raise ValueError("output path mismatch")
                    counts[model][setting] += 1
                except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                    errors.append(f"{prefix}: {exc}")
    report = {"status": "passed" if not errors else "failed", "error_count": len(errors),
              "errors": errors[:100], "counts": counts, "manifest_sha256": digest}
    path = args.output_root / "reports/validation.json"
    write_json(path, report)
    print(json.dumps(report, indent=2)[:10000])
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
