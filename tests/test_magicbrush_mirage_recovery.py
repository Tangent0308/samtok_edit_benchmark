import math

import pytest

from samtok_benchmark.postprocessing.magicbrush_mirage_recovery import decode, validate_regions


def answer(box=None):
    return {
        "regions": [
            {
                "refer_object": "table",
                "new_instruction": "Add a glass of water",
                "bbox_2d": [100, 200, 300, 400] if box is None else box,
            }
        ]
    }


def test_complete_pairs_only():
    assert validate_regions(answer())[0]["new_instruction"] == "Add a glass of water"
    with pytest.raises(ValueError):
        validate_regions({"Refer_object": [], "New_edit_instruction": ["Add a glass"]})
    with pytest.raises(ValueError):
        validate_regions({"regions": []})
    value = answer()
    value["regions"][0]["refer_object"] = ""
    with pytest.raises(ValueError):
        validate_regions(value)


@pytest.mark.parametrize(
    "box",
    [
        [0, 0, 0, 100],
        [500, 0, 200, 100],
        [-1, 0, 10, 10],
        [0, 0, 1001, 100],
        [0, 0, math.nan, 10],
        [True, 0, 10, 10],
        [0, 1, 2],
        None,
    ],
)
def test_invalid_boxes_never_get_synthesized_or_clamped(box):
    value = answer()
    value["regions"][0]["bbox_2d"] = box
    with pytest.raises(ValueError):
        validate_regions(value)


def test_no_partial_json_salvage():
    assert decode('```json\n{"regions": []}\n```') == {"regions": []}
    with pytest.raises(ValueError):
        decode('{"regions": [{"bbox_2d": [1,2,3,4]}')
    with pytest.raises(ValueError):
        decode('{"regions": []} trailing explanation')


def test_truncated_locator_reuses_parser_trace_without_native_receipt(tmp_path, monkeypatch):
    import json
    import sys
    from types import SimpleNamespace
    from PIL import Image

    from samtok_benchmark.postprocessing.magicbrush_mirage_recovery import recover_plan

    source = tmp_path / "source.png"
    Image.new("RGB", (100, 100)).save(source)
    trace_path = tmp_path / "old-traces.json"
    trace_path.write_text(json.dumps([{"response": ['{"saved": true}']}]))
    expected = [[("candles", "Light up the candles")]]

    def parse(cached, instructions):
        assert cached.chat([], max_new_tokens=512) == ['{"saved": true}']
        assert instructions == ["Light up the candles"]
        return expected

    native = SimpleNamespace(parse_instructions=parse, to_pixels=lambda *a, **k: (0, 0, 20, 30))
    monkeypatch.setitem(sys.modules, "mirage.vlm", native)
    vlm = SimpleNamespace(chat=lambda *a, **k: ['[{"bbox_2d":[0,0,200,300]}]'])

    def locate(images, phrases):
        assert vlm.grounding_tokens == 2048
        assert phrases == ["candles"]
        vlm.chat([[{"role": "user", "content": "native grounding"}]], 2048)
        return [[0, 0, 200, 300]]

    vlm.locate = locate
    item = {"strategy": "native_long_locator", "original_traces": {"path": str(trace_path)}}
    public = {"source": {"path": str(source)}, "instruction": "Light up the candles"}
    result = recover_plan(vlm, public, item, tmp_path / "new-plan")
    assert result["additional_vlm_calls"] == 1
    assert result["regions"][0]["new_instruction"] == "Light up the candles"


def test_eight_gpu_authorization_keeps_memory_and_single_card_guards(monkeypatch):
    from pathlib import Path
    import runpy
    import subprocess

    script = Path(__file__).resolve().parents[1] / "scripts/magicbrush_mirage_recovery_8gpu.py"
    gate = runpy.run_path(str(script))["authorized_gpu_gate"]
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "1605,79402")
    gate()
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1")
    with pytest.raises(ValueError):
        gate()
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "7")
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "10000,70007")
    with pytest.raises(RuntimeError):
        gate()
