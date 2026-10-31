"""Scientific geometry and public-information contracts for the 1MP protocol."""

from copy import deepcopy
import math

import numpy as np
from PIL import Image
import pytest

from samtok_benchmark.ifbench import MANIFEST_SHA256, SCHEMA, PROTOCOL
from samtok_benchmark.ifbench import canvas
from samtok_benchmark.ifbench.public import public_digest, verify
from samtok_benchmark.ifbench.inputs import export_fairness_inputs
from samtok_benchmark.io import sha256_file, read_jsonl
from samtok_benchmark.paths import repository_root


def public_fixture(tmp_path, locator="box"):
    source = tmp_path / "source.png"
    Image.new("RGB", (1300, 913), (20, 60, 200)).save(source)
    units = [
        {
            "id": f"U{i}",
            "operation": "attribute",
            "instruction": "Make the selected region red.",
            "has_ref": False,
            "locator": locator,
            "region": {"coordinates": [13, 17, 14, 18] if locator == "box" else [13, 17]},
        }
        for i in (1, 2)
    ]
    request = {
        "schema": SCHEMA,
        "protocol": PROTOCOL,
        "request_id": "example--S3-box",
        "case_id": "example",
        "setting": "S3-" + locator,
        "source": {"path": str(source), "size": [1300, 913], "sha256": sha256_file(source)},
        "units": units,
        "manifest_sha256": MANIFEST_SHA256,
    }
    request["input_digest"] = public_digest(request)
    return request


def test_entire_release_fits_single_and_multi_reference_limits():
    cases = read_jsonl(repository_root() / "data/v2_2.6.0/cases.jsonl")
    assert len(cases) == 1084
    for case in cases:
        g = canvas.geometry(case["source"]["size"])
        w, h = g["canvas_size"]
        fw, fh = g["content_size"]
        assert w % 32 == h % 32 == 0
        assert w * h <= 1024**2 and 64 <= min(w, h) and max(w, h) <= 4096
        assert 0 <= w - fw < 32 and 0 <= h - fh < 32
        assert g == canvas.geometry(case["source"]["size"])


def test_continuous_coordinates_and_no_private_geometry(tmp_path):
    original = public_fixture(tmp_path)
    source, g = canvas.make_source(original["source"], tmp_path / "canvas")
    projected = canvas.project_public(original, source, g, tmp_path / "masks")
    assert projected["source"]["path"] != original["source"]["path"]
    for old, new in zip(original["units"], projected["units"]):
        assert new["instruction"] == old["instruction"]
        assert set(new["region"]) == {"coordinates"}
        p = new["region"]["coordinates"]
        assert p[2] > p[0] and p[3] > p[1]
        for i, value in enumerate(p):
            assert (value - g["offset_xy"][i % 2]) / g["scale_xy"][i % 2] == pytest.approx(
                old["region"]["coordinates"][i]
            )
    verify(projected, assets=True)
    export_fairness_inputs(projected, tmp_path / "inputs")  # subpixel box remains drawable
    changed = deepcopy(projected)
    changed["units"][0]["region"]["coordinates"][0] = math.nan
    changed["input_digest"] = public_digest(changed)
    with pytest.raises(ValueError):
        verify(changed)


def test_point_request_never_receives_mask_or_box(tmp_path):
    original = public_fixture(tmp_path, "point")
    source, g = canvas.make_source(original["source"], tmp_path / "canvas")
    result = canvas.project_public(original, source, g, tmp_path / "masks")
    assert all(
        set(u["region"]) == {"coordinates"} and len(u["region"]["coordinates"]) == 2
        for u in result["units"]
    )
    export_fairness_inputs(result, tmp_path / "inputs")


def test_inverse_mapping_removes_padding_at_different_native_sizes():
    g = canvas.geometry([1300, 913])
    assert g["canvas_size"] != g["content_size"]
    clean = Image.new("RGB", tuple(g["canvas_size"]), (128, 128, 128))
    clean.paste(Image.new("RGB", tuple(g["content_size"]), (0, 0, 255)), tuple(g["offset_xy"]))
    for scale in (1, 2):
        raw = clean.resize(tuple(v * scale for v in clean.size), Image.Resampling.NEAREST)
        restored = canvas.restore_output(raw, g)
        assert restored.size == (1300, 913)
        pixels = np.asarray(restored)
        assert pixels[10:-10, 10:-10, 2].min() == 255
        assert pixels[10:-10, 10:-10, :2].max() == 0


def test_native_method_grids_are_not_overridden():
    public = {"source": {"size": [1248, 832]}}
    for model in ["replan", "mirage"]:
        request = {"parameters": {"num_inference_steps": 40}, "prompt": "unchanged"}
        revised = canvas.revise_request(model, request, public)
        assert revised["parameters"] == request["parameters"]
        assert revised["prompt"] == "unchanged"
    request = {
        "parameters": {"num_inference_steps": 40, "output_resolution": 2048},
        "prompt": "unchanged",
    }
    revised = canvas.revise_request("qwen21", request, public)
    assert revised["parameters"] == {
        "num_inference_steps": 40,
        "output_resolution": 1024,
        "width": 1248,
        "height": 832,
    }


def test_tampered_geometry_cannot_change_output_alignment():
    g = canvas.geometry([1300, 913])
    g["content_box"][0] += 1
    with pytest.raises(ValueError):
        canvas.restore_output(Image.new("RGB", (1024, 1024)), g)


def test_worker_preserves_raw_and_restores_canonical_content(tmp_path):
    from test_ifbench_fairness_dev_worker import FakeBackend, fixture_plan, run
    from samtok_benchmark.io import write_json
    from samtok_benchmark.ifbench.fairness_dev_plan import read

    plan = fixture_plan(tmp_path, count=1)
    plan["canvas_policy"] = canvas.POLICY
    task = plan["tasks"][0]
    g = canvas.geometry([31, 23])
    transform = tmp_path / "geometry.json"
    write_json(transform, g)
    task["canvas_transform"] = str(transform)
    task["canvas_transform_sha256"] = sha256_file(transform)
    public = read(task["public_request"])
    public["source"]["size"] = g["canvas_size"]
    write_json(task["public_request"], public)
    raw = Image.new("RGB", tuple(g["canvas_size"]), "red")
    raw.paste(Image.new("RGB", tuple(g["content_size"]), "blue"), tuple(g["offset_xy"]))

    class CanvasBackend(FakeBackend):
        def run(self, request, public, out, native_plan):
            super().run(request, public, out, native_plan)
            return raw, {}

    run(tmp_path, plan, CanvasBackend())
    result = read(task["result_path"])
    assert result["status"] == "generated"
    assert result["input_size"] == result["raw_size"] == g["canvas_size"]
    with Image.open(result["raw_image"]) as saved:
        assert saved.tobytes() == raw.tobytes()
    with Image.open(result["output_image"]) as output:
        assert output.size == (31, 23)
        assert output.tobytes() == canvas.restore_output(raw, g).tobytes()
        assert output.tobytes() != raw.resize((31, 23), Image.Resampling.LANCZOS).tobytes()
