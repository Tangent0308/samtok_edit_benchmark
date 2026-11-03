"""Meaningful CPU checks for the post-hoc analysis, without models or API calls."""
import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

SPEC = importlib.util.spec_from_file_location(
    "mira_analysis", Path(__file__).resolve().parents[1] / "scripts/analyze_mira_results.py")
ANALYSIS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYSIS)


def test_paired_components_align_source_ids_and_count_ties():
    baseline = {"001": [3, 6, 8], "002": [4, 6, 8], "003": [5, 6, 8]}
    ours = {"003": [5, 7, 7], "002": [3, 7, 7], "001": [4, 7, 7]}
    report = ANALYSIS.components({"sitedit": ours, "qwen21": baseline},
                                 ["003", "001", "002"], replicates=500)
    pf = report["metrics"]["prompt_following"]
    assert report["source_ids"] == ["001", "002", "003"]
    assert pf["paired_mean_difference"] == 0
    assert (pf["sitedit_lower_count"], pf["tie_count"], pf["sitedit_higher_count"]) == (1, 1, 1)
    assert report["metrics"]["perceptual_quality"]["difference_ci95"] == [-1, -1]
    assert report["metrics"]["consistency"]["difference_ci95"] == [1, 1]


def test_components_refuse_missing_sources_and_invalid_scores():
    values = {"sitedit": {"001": [1, 2, 3]}, "qwen21": {"001": [1, 2, 3]}}
    with pytest.raises(ValueError, match="Missing"):
        ANALYSIS.components(values, ["001", "002"])
    with pytest.raises(ValueError, match="Unique"):
        ANALYSIS.components(values, ["001", "001"])
    values["sitedit"]["001"][2] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        ANALYSIS.components(values, ["001"])


def test_region_iou_removes_letterbox_before_restoring_source_coordinates():
    # Padding is deliberately foreground too: a whole-canvas resize would give the wrong IoU.
    pixels = np.full((8, 8), 255, dtype="uint8")
    pixels[2:6, 2:6] = 0
    pixels[2:6, 2:4] = 255
    geometry = {"canvas_size": [8, 8], "content_box": [2, 2, 6, 6], "source_size": [4, 4]}
    mask = Image.fromarray(pixels)
    target = [[0, 0, 1, 0, 1, 3, 0, 3]]
    assert ANALYSIS.region_iou(mask, target, geometry) == 1
    assert ANALYSIS.region_iou(mask, [2, 0, 3, 0, 3, 3, 2, 3], geometry) == 0
    with pytest.raises(ValueError, match="canvas"):
        ANALYSIS.region_iou(mask.resize((4, 4)), target, geometry)
    with pytest.raises(ValueError, match="coordinates"):
        ANALYSIS.polygon_mask([0, 0, 1], [4, 4])


def test_saved_token_must_belong_to_the_corresponding_instruction():
    token = "<|mt_start|><|mt_0080|><|mt_0300|><|mt_end|>"
    tokens = {"native": {"units": [{"id": "U1", "token": token}]}}
    call = {"prompt": f"U1: Paint the target {token} blue\nU2: Remove the other object"}
    assert ANALYSIS.bound_token(tokens, call, "U1").startswith("U1:")
    call["prompt"] = f"U1: Paint the target blue\nU2: Remove {token}"
    with pytest.raises(ValueError, match="corresponding"):
        ANALYSIS.bound_token(tokens, call, "U1")


def test_evidence_tampering_and_formal_output_paths_are_rejected(tmp_path):
    evidence = tmp_path / "record.json"
    evidence.write_text("original")
    receipt = ANALYSIS.checked_file(evidence)
    evidence.write_text("changed")
    with pytest.raises(ValueError, match="hash"):
        ANALYSIS.checked_file(evidence, receipt["sha256"])
    formal = tmp_path / "formal"
    with pytest.raises(ValueError, match="formal"):
        ANALYSIS.fresh_destination(formal / "diagnostics", formal)
    with pytest.raises(ValueError, match="Preserve"):
        ANALYSIS.fresh_destination(evidence, formal)
    assert ANALYSIS.fresh_destination(tmp_path / "new", formal) == tmp_path / "new"
