from __future__ import annotations

import sys
import types
from argparse import Namespace
from pathlib import Path

import numpy as np
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "evaluation"))

from common import (  # noqa: E402
    annotated_prompt,
    official_output_size,
    paste_back,
    render_annotation,
    settings_for_model,
    summarize_records,
    token_prompt,
)
from run_inference import generate, input_and_prompt  # noqa: E402


def test_protocol_has_fifteen_result_settings_and_two_derived_rows():
    settings = [
        *settings_for_model("qwen"),
        *settings_for_model("flux2"),
        *settings_for_model("samtok_edit"),
    ]
    assert len(settings) == 15
    assert sum(setting.pasteback for setting in settings) == 2


def test_prompts_preserve_region_order():
    template = "Replace {region_1} and remove {region_2}."
    rendered = annotated_prompt(template, 2, "box")
    assert "R1 in red" in rendered
    assert "R2 in green" in rendered
    assert rendered.index("R1") < rendered.index("R2")
    assert "do not preserve, reproduce, or draw them" in rendered
    tokenized = token_prompt(template, ["SPAN_A", "SPAN_B"])
    assert tokenized == "Replace SPAN_A and remove SPAN_B."


def test_single_region_prompt_and_rendering_do_not_add_an_r1_label(tmp_path):
    prompt = annotated_prompt("Remove {region_1}.", 1, "mask")
    assert "area highlighted in red" in prompt
    assert "R1" not in prompt
    source = Image.new("RGB", (64, 64), (100, 100, 100))
    mask = np.zeros((64, 64), dtype=np.uint8)
    mask[16:48, 16:48] = 255
    Image.fromarray(mask).save(tmp_path / "mask.png")
    rendered = render_annotation(
        source,
        [{"mask": "mask.png", "box": [16, 16, 48, 48], "point": [32, 32]}],
        tmp_path,
        "mask",
    )
    # No text label is drawn above the mask's top edge for a single target.
    assert np.all(np.asarray(rendered)[4:12, 16:48] == 100)


def test_pasteback_changes_only_inside_binary_mask():
    source = Image.fromarray(np.zeros((8, 10, 3), dtype=np.uint8))
    generated = Image.fromarray(np.full((8, 10, 3), 255, dtype=np.uint8))
    mask_array = np.zeros((8, 10), dtype=np.uint8)
    mask_array[2:6, 3:8] = 255
    output = np.asarray(paste_back(source, generated, Image.fromarray(mask_array)))
    assert np.all(output[2:6, 3:8] == 255)
    outside = mask_array == 0
    assert np.all(output[outside] == 0)


def test_official_output_size_is_aligned_and_near_one_megapixel():
    width, height = official_output_size(Image.new("RGB", (640, 480)))
    assert width % 32 == height % 32 == 0
    assert abs(width * height - 1024 * 1024) / (1024 * 1024) < 0.06
    assert abs(width / height - 4 / 3) < 0.05


def test_mask_annotation_is_translucent(tmp_path):
    source = Image.new("RGB", (64, 64), (100, 100, 100))
    mask = np.zeros((64, 64), dtype=np.uint8)
    mask[8:56, 8:56] = 255
    Image.fromarray(mask).save(tmp_path / "mask.png")
    rendered = np.asarray(
        render_annotation(
            source,
            [{"mask": "mask.png", "box": [8, 8, 56, 56], "point": [32, 32]}],
            tmp_path,
            "mask",
        )
    )
    center = rendered[40, 40]
    assert 100 < int(center[0]) < 235
    assert int(center[1]) < 100


def test_samtok_umt_prompt_does_not_consume_target_fields(tmp_path):
    Image.new("RGB", (16, 16)).save(tmp_path / "source.png")
    row = {
        "source_image": "source.png",
        "instruction": {
            "with_location_reference": "remove the left cup",
            "region_only": "Remove {region_1}.",
        },
        "regions": [{"mask": "unused.png", "box": [0, 0, 1, 1], "point": [0, 0]}],
        "target": {"expected_local_content": "DO_NOT_LEAK"},
        "prepared": {
            "samtok_prompts": {
                "mask_umt": "Remove MASK_SPAN.",
                "box_sam2_umt": "Remove BOX_SPAN.",
                "point_sam2_umt": "Remove POINT_SPAN.",
            }
        },
    }
    setting = next(x for x in settings_for_model("samtok_edit") if x.key == "mask_umt")
    _, _, prompt, mt_cot = input_and_prompt(row, setting, tmp_path, tmp_path)
    assert prompt == "Remove MASK_SPAN."
    assert "DO_NOT_LEAK" not in prompt
    assert mt_cot is None


def test_summary_counts_only_positive_span_umt_audits():
    common = {
        "edit_type": "replace",
        "source_dataset": "compbench",
        "derived_from_output": None,
        "elapsed_seconds": 1.0,
        "parse_layer": None,
        "conditioned_mt_cot": None,
    }
    no_user_span = {
        **common,
        "user_mask_audit": {
            "user_mask_span_count": 0,
            "user_mask_spans_atomic": True,
            "user_mask_spans_in_template": True,
        },
    }
    assert "umt_tokenizer_audits" not in summarize_records([no_user_span])
    with_user_span = {
        **common,
        "user_mask_audit": {
            "user_mask_span_count": 1,
            "user_mask_spans_atomic": True,
            "user_mask_spans_in_template": True,
        },
    }
    assert summarize_records([with_user_span])["umt_tokenizer_audits"] == {
        "count": 1,
        "passed": 1,
    }


class RecordingPipeline:
    def __init__(self):
        self.calls = []

    def __call__(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return Image.new("RGB", (kwargs["width"], kwargs["height"]))


def test_qwen_adapter_uses_official_2511_edit_arguments():
    pipe = RecordingPipeline()
    setting = next(x for x in settings_for_model("qwen") if x.key == "text_only")
    source = Image.new("RGB", (64, 48))
    output, telemetry = generate(
        pipe,
        Namespace(model="qwen", qwen_steps=40, qwen_cfg_scale=4.0),
        setting,
        source,
        "edit prompt",
        None,
        0,
        (128, 96),
        "cuda:3",
    )
    prompt, call = pipe.calls[0]
    assert prompt == "edit prompt"
    assert call == {
        "edit_image": [source],
        "seed": 0,
        "num_inference_steps": 40,
        "cfg_scale": 4.0,
        "height": 96,
        "width": 128,
        "edit_image_auto_resize": True,
        "zero_cond_t": True,
    }
    assert output.size == (128, 96)
    assert telemetry == {}


def test_flux_adapter_uses_official_klein_edit_arguments():
    pipe = RecordingPipeline()
    setting = next(x for x in settings_for_model("flux2") if x.key == "text_only")
    source = Image.new("RGB", (64, 48))
    _, telemetry = generate(
        pipe,
        Namespace(model="flux2", flux_steps=4),
        setting,
        source,
        "edit prompt",
        None,
        0,
        (128, 96),
        "cuda:5",
    )
    _, call = pipe.calls[0]
    assert call == {
        "edit_image": [source],
        "seed": 0,
        "rand_device": "cuda:5",
        "num_inference_steps": 4,
        "cfg_scale": 1.0,
        "embedded_guidance": 4.0,
        "height": 96,
        "width": 128,
        "edit_image_auto_resize": True,
    }
    assert telemetry == {}


def test_samtok_adapter_delegates_to_method_run_edit(monkeypatch):
    calls = []

    def fake_run_edit(pipe, source, prompt, **kwargs):
        calls.append((pipe, source, prompt, kwargs))
        pipe.last_mt_cot = "predicted"
        pipe.last_pass1_raw = "raw"
        pipe.last_parse_layer = "strict"
        pipe.last_user_mask_audit = None
        return Image.new("RGB", (kwargs["output_width"], kwargs["output_height"]))

    monkeypatch.setitem(sys.modules, "infer_samtok_edit", types.SimpleNamespace(run_edit=fake_run_edit))
    pipe = types.SimpleNamespace()
    source = Image.new("RGB", (64, 48))
    setting = next(x for x in settings_for_model("samtok_edit") if x.key == "online_cot")
    _, telemetry = generate(
        pipe,
        Namespace(
            model="samtok_edit",
            qwen_steps=40,
            qwen_cfg_scale=4.0,
            samtok_max_new_tokens=128,
        ),
        setting,
        source,
        "edit prompt",
        None,
        0,
        (128, 96),
        "cuda:7",
    )
    assert calls[0][0:3] == (pipe, source, "edit prompt")
    assert calls[0][3] == {
        "seed": 0,
        "num_inference_steps": 40,
        "cfg_scale": 4.0,
        "mt_cot": None,
        "enable_samtok_cot": True,
        "samtok_max_new_tokens": 128,
        "output_height": 96,
        "output_width": 128,
    }
    assert telemetry == {
        "conditioned_mt_cot": "predicted",
        "pass1_raw": "raw",
        "parse_layer": "strict",
        "user_mask_audit": None,
    }
