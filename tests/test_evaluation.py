from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

import numpy as np
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "evaluation"))

from common import (  # noqa: E402
    official_output_size,
    render_annotation,
    settings_for_model,
    two_image_locator_prompt,
)
from run_inference import generate, input_and_prompt  # noqa: E402


def test_protocol_has_four_settings_for_each_baseline():
    expected = ["text_only", "mask_annotation", "box_annotation", "point_annotation"]
    assert [setting.key for setting in settings_for_model("qwen")] == expected
    assert [setting.key for setting in settings_for_model("flux2")] == expected


def test_two_region_prompt_preserves_region_order():
    prompt = two_image_locator_prompt(
        "Replace {region_1} and remove {region_2}.", 2, "box"
    )
    assert "R1 (red box) in Image 2" in prompt
    assert "R2 (green box) in Image 2" in prompt
    assert prompt.index("R1") < prompt.index("R2")
    assert "without any markers from Image 2" in prompt


def test_single_region_prompt_and_rendering_do_not_add_r1_label(tmp_path):
    prompt = two_image_locator_prompt("Remove {region_1}.", 1, "mask")
    assert "red mask in Image 2" in prompt
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
    assert np.all(np.asarray(rendered)[4:12, 16:48] == 100)


def test_each_prompt_explains_reference_roles_and_modality():
    phrases = {
        "mask": "red mask in Image 2",
        "box": "red box in Image 2",
        "point": "red point in Image 2",
    }
    for modality, phrase in phrases.items():
        prompt = two_image_locator_prompt(
            "Replace {region_1} with a blue cup.", 1, modality
        )
        assert prompt.startswith("Edit Image 1.")
        assert phrase in prompt
        assert "Keep everything else unchanged." in prompt
        assert "without any markers from Image 2" in prompt


def test_point_marker_is_clear_and_centered(tmp_path):
    source = Image.new("RGB", (128, 128), (100, 100, 100))
    rendered = np.asarray(
        render_annotation(
            source,
            [{"mask": "unused.png", "box": [32, 32, 96, 96], "point": [64, 64]}],
            tmp_path,
            "point",
        )
    )
    assert rendered[64, 64, 0] > rendered[64, 64, 1]
    changed = np.any(rendered[40:89, 40:89] != 100, axis=2)
    assert int(changed.sum()) > 250


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


def test_official_output_size_is_aligned_and_near_one_megapixel():
    width, height = official_output_size(Image.new("RGB", (640, 480)))
    assert width % 32 == height % 32 == 0
    assert abs(width * height - 1024 * 1024) / (1024 * 1024) < 0.06
    assert abs(width / height - 4 / 3) < 0.05


def test_inference_uses_frozen_ordered_image_list(tmp_path):
    source_path = tmp_path / "source.png"
    locator_path = tmp_path / "locator.png"
    Image.new("RGB", (16, 16), "black").save(source_path)
    Image.new("RGB", (16, 16), "red").save(locator_path)
    row = {
        "prepared": {
            "baseline_inputs": {
                "point_annotation": {
                    "images": [str(source_path), str(locator_path)],
                    "image_roles": ["clean_source_to_edit", "point_locator_only"],
                    "prompt": "FROZEN PROMPT",
                }
            }
        }
    }
    setting = next(
        item for item in settings_for_model("qwen") if item.key == "point_annotation"
    )
    images, paths, roles, prompt = input_and_prompt(
        row, setting, tmp_path, tmp_path
    )
    assert paths == [source_path, locator_path]
    assert roles == ["clean_source_to_edit", "point_locator_only"]
    assert images[0].getpixel((0, 0)) == (0, 0, 0)
    assert images[1].getpixel((0, 0)) == (255, 0, 0)
    assert prompt == "FROZEN PROMPT"


class RecordingPipeline:
    def __init__(self):
        self.calls = []

    def __call__(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return Image.new("RGB", (kwargs["width"], kwargs["height"]))


def test_qwen_adapter_uses_official_arguments_and_preserves_image_order():
    pipe = RecordingPipeline()
    source = Image.new("RGB", (64, 48), "black")
    locator = Image.new("RGB", (64, 48), "red")
    output, telemetry = generate(
        pipe,
        Namespace(model="qwen", qwen_steps=40, qwen_cfg_scale=4.0),
        [source, locator],
        "edit prompt",
        0,
        (128, 96),
        "cuda:3",
    )
    prompt, call = pipe.calls[0]
    assert prompt == "edit prompt"
    assert call == {
        "edit_image": [source, locator],
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


def test_flux_adapter_uses_official_arguments_and_preserves_image_order():
    pipe = RecordingPipeline()
    source = Image.new("RGB", (64, 48), "black")
    locator = Image.new("RGB", (64, 48), "red")
    _, telemetry = generate(
        pipe,
        Namespace(model="flux2", flux_steps=4),
        [source, locator],
        "edit prompt",
        0,
        (128, 96),
        "cuda:5",
    )
    _, call = pipe.calls[0]
    assert call == {
        "edit_image": [source, locator],
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
