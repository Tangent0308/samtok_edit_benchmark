"""External protocol regressions; no model downloads or GPU inference."""

import copy
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from samtok_benchmark.io import digest, sha256_file
from samtok_benchmark.external_mira.data import immutable, split_instruction, verify_public
from samtok_benchmark.external_mira.adapters import native_request, token_prompt
from samtok_benchmark.external_mira.score import overall, aggregate, judge
from samtok_benchmark.external_mira.cli import report


TEXT = ("Change the left umbrella to red, and Add a ribbon to the middle umbrella, and "
        "Replace the right umbrella with a flower. and Remove the left handle, and "
        "Wrap a red ribbon around the rightmost tree trunk")


@pytest.fixture
def public(tmp_path):
    path = tmp_path / "source.png"
    Image.new("RGB", (64, 64), "gray").save(path)
    obj = {"schema": "mira.public.v1", "case_id": "001",
           "source": {"path": str(path), "sha256": sha256_file(path), "size": [64, 64]},
           "original_instruction": TEXT,
           "units": [{"id": f"U{i}", "has_ref": True, "locator": "none", **part}
                     for i, part in enumerate(split_instruction(TEXT), 1)]}
    obj["input_digest"] = digest(obj)
    return obj


@pytest.fixture
def config():
    return json.loads((Path(__file__).parents[1] / "configs/external/mira.json").read_text())


def resign(value):
    value.pop("input_digest", None)
    value["input_digest"] = digest(value)
    return value


def test_public_split_handles_period_and_preserves_source_text(public):
    verify_public(public)
    for unit in public["units"]:
        start, end = unit["text_span"]
        assert TEXT[start:end] == unit["instruction"]
    assert public["units"][-1]["operation"] == "add"


@pytest.mark.parametrize("location", ["top", "unit", "source"])
def test_private_mask_or_source_metadata_cannot_enter_public(public, location):
    target = public if location == "top" else public["units"][0] if location == "unit" else public["source"]
    target["mask"] = "private/evaluation-mask.png"
    with pytest.raises(ValueError):
        verify_public(resign(public))


def test_missing_unit_is_not_silently_truncated(public):
    public["units"].pop()
    with pytest.raises(ValueError):
        verify_public(resign(public))


def test_mirage_receives_one_whole_composite_instruction(public, config):
    call = native_request("mirage", public, config)
    assert call["parser_inputs"] == [TEXT]
    assert call["global_original_prompt"] == TEXT
    assert call["grounding_image"] == call["edit_image"] == public["source"]["path"]
    assert not any("mask" in key for key in call)


def test_replan_filters_planner_metadata_from_diffusion_kwargs(public, config):
    call = native_request("replan", public, config)
    assert "native_planner_max_new_tokens" not in call["parameters"]
    assert "seed" not in call["parameters"]
    assert call["parameters"]["num_inference_steps"] == 40
    assert call["planner_image"] == call["editor_image"]


def test_qwen_native_canvas_and_sampling_are_preserved(public, config):
    for model, cfg in [("qwen21", 1.0), ("qwen2511", 4.0)]:
        call = native_request(model, public, config)
        assert call["images"] == [public["source"]["path"]]
        assert call["prompt"] == TEXT
        assert call["parameters"]["width"] == 64
        assert call["parameters"]["true_cfg_scale"] == cfg


def test_sit_tokens_remain_bound_to_public_units_and_fallback_keeps_text(public):
    pytest.importorskip("samtok_edit21")
    tokens = {"units": [{"id": u["id"], "token": f"<|mt_start|><|mt_000{i}|><|mt_0257|><|mt_end|>"}
                        for i, u in enumerate(public["units"], 1)]}
    tokens["units"][2]["token"] = None
    prompt, guided = token_prompt(public, tokens)
    assert guided
    assert prompt.count("<|mt_start|>") == 4
    assert "U3: Replace the right umbrella with a flower" in prompt
    assert "tree trunk <|mt_start|><|mt_0005|>" in prompt
    assert "left umbrella <|mt_start|><|mt_0001|>" in prompt


def test_input_receipts_reject_changed_content(tmp_path):
    immutable(tmp_path / "record.json", {"value": 1})
    immutable(tmp_path / "record.json", {"value": 1})
    with pytest.raises(ValueError):
        immutable(tmp_path / "record.json", {"value": 2})


def test_official_aggregation_is_not_average_per_image_overall():
    values = [[10, 0, 10], [0, 10, 10]]
    assert overall(values) == pytest.approx(np.sqrt(50))


def test_score_coverage_keeps_missing_and_omits_population_ci(tmp_path):
    for model in ["qwen21", "sitedit"]:
        root = tmp_path / model
        immutable(root / "JOB.json", {"total": 200, "valid_outputs": 1,
                                       "unscorable": [{"case_id": "002", "status": "missing"}],
                                       "bindings": [{"image": "001.jpg"}]})
        (root / "scores").mkdir()
        (root / "scores/per_image_results.jsonl").write_text(json.dumps({"image": "001.jpg",
            "prompt_following": 5, "consistency": 7, "perceptual_quality": 8}) + "\n")
    result = aggregate(tmp_path, ["qwen21", "sitedit"])
    assert result["rows"][0]["scored"] == 1
    assert result["rows"][0]["total"] == 200
    assert not result["rows"][0]["complete"]
    assert result["paired_sitedit_minus_baseline_CI95"] == {}
    assert "Overall_CI95" not in result["rows"][0]


def test_input_pixels_are_bound(public):
    original = copy.deepcopy(public)
    Image.new("RGB", (64, 64), "red").save(public["source"]["path"])
    with pytest.raises(ValueError, match="changed"):
        verify_public(original)


def test_changed_judge_annotation_is_rejected_before_api_use(tmp_path):
    annotations = tmp_path / "annotations.jsonl"
    annotations.write_text("original\n")
    immutable(tmp_path / "JOB.json", {"export": str(tmp_path), "evaluator": {},
              "annotation_sha256": {annotations.name: sha256_file(annotations)}})
    annotations.write_text("different target\n")
    with pytest.raises(ValueError, match="annotations changed"):
        judge(tmp_path / "JOB.json")


def test_generation_report_distinguishes_failed_plan_and_unknown_admission(tmp_path):
    immutable(tmp_path / "RUN.json", {"models": ["replan"], "scope": "smoke",
                                       "case_ids": ["001", "002", "003"]})
    immutable(tmp_path / "replan/plan/001/result.json", {"status": "failed", "error": "bad plan"})
    immutable(tmp_path / "replan/plan/002/ADMITTED.json", {"admitted": True})
    row = report(tmp_path)["rows"][0]
    assert [r["status"] for r in row["cases"]] == ["failed", "unknown", "pending"]
    assert row["failed"] == 1 and row["unknown"] == 1 and row["total"] == 3
