"""Regression checks for the moved RePlan adapter and completed run."""

import json
from argparse import Namespace
from pathlib import Path

import pytest

from evaluation.replan import runner
from evaluation.replan.audit_planner import audit


def test_existing_replan_runs_resume_only_with_the_same_semantics():
    for model in runner.BACKBONES:
        config_path = runner.OUTPUT_ROOT / "inference" / model / "run_config.json"
        if not config_path.is_file():
            pytest.skip("Existing RePlan run is not mounted")
        old = json.loads(config_path.read_text(encoding="utf-8"))
        args = Namespace(
            model=model,
            planner=Path(old["planner_checkpoint"]),
            backbone=Path(old["backbone_checkpoint"]),
            manifest=Path(old["manifest"]),
            dataset_root=Path(old["dataset_root"]),
            prepared_root=Path(old["prepared_root"]),
            replan_repo=runner.REPLAN_REPO,
            settings=old["settings"],
            world=old["world_size"],
            seed=old["seed"],
            expand_value=old["expand_value"],
            attention_switch_step=old["attention_switch_step"],
            stage_offload=old["stage_offload"],
        )
        rows = [{"eval_index": index} for index in old["eval_indices"]]
        current = runner.make_config(args, rows, runner.sha256(args.manifest))
        assert runner.configs_match(old, current)
        changed_seed = {**current, "seed": current["seed"] + 1}
        assert not runner.configs_match(old, changed_seed)
        changed_method = {**current, "replan_pipeline_sha256": "0" * 64}
        assert not runner.configs_match(old, changed_method)


def test_replan_uses_frozen_baseline_images_and_never_sends_locator_to_editor():
    if not runner.MANIFEST.is_file():
        pytest.skip("Frozen benchmark input manifest is not mounted")
    rows = [json.loads(line) for line in runner.MANIFEST.read_text().splitlines() if line]
    assert len(rows) == 656
    for row in rows:
        frozen = row["prepared"]["baseline_inputs"]
        clean = frozen["text_only"]["images"][0]
        assert frozen["text_only"]["images"] == [clean]
        for setting in runner.SETTINGS[1:]:
            images = frozen[setting]["images"]
            assert len(images) == 2 and images[0] == clean
            assert images[1] != clean
            assert row["target"]["reference_image"] not in images
            assert row["evaluation_mask"] not in images


def test_planner_template_audit_identifies_reused_example_box(tmp_path):
    root = tmp_path / "inference/qwen2511/mask_annotation"
    root.mkdir(parents=True)
    (root / "0575.json").write_text(json.dumps({
        "model": "qwen2511", "setting": "mask_annotation", "eval_index": 575,
        "predicted_boxes": [
            {"bbox_2d": [10, 150, 150, 210], "hint": "change collar"},
            {"bbox_2d": [300, 300, 400, 400], "hint": "keep dog"},
        ],
    }))
    result = audit(tmp_path)
    assert result["total_sidecars_scanned"] == 1
    assert result["distinct_cases"] == 1
    assert result["output_records"] == 1
    assert result["records"][0]["boxes"] == [[10, 150, 150, 210]]
