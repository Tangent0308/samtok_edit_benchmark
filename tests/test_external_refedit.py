"""RefEdit-Bench external protocol regressions; no model downloads, network or GPU inference."""

import json
import math
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from samtok_benchmark.io import digest, sha256_file
from samtok_benchmark.external_refedit import data, score
from samtok_benchmark.external_refedit.adapters import FLUX3_PREFIX, native_request

ROOT = Path(__file__).parents[1]
TEXT = "Remove the half full mug of beer to the left of the pizza."


@pytest.fixture
def config():
    return json.loads((ROOT / "configs/external/refedit.json").read_text())


@pytest.fixture
def public(tmp_path):
    path = tmp_path / "source.png"
    Image.new("RGB", (64, 48), "gray").save(path)
    obj = {"schema": "refedit.public.v1", "case_id": "007",
           "source": {"path": str(path), "sha256": sha256_file(path), "size": [64, 48]}, "instruction": TEXT}
    obj["input_digest"] = digest(obj)
    return obj


def resign(value):
    value.pop("input_digest", None)
    value["input_digest"] = digest(value)
    return value


# ------------------------------------------------------------------------------------------------ inputs


@pytest.mark.parametrize("key", ["mask", "edit_instruction_single", "category"])
def test_private_fields_cannot_enter_public(public, key):
    public[key] = "private"
    with pytest.raises(ValueError):
        data.verify_public(resign(public))


@pytest.mark.parametrize("model", ["qwen21", "qwen2511", "replan", "mirage", "flux3", "mice", "flux2_klein9b"])
def test_every_baseline_gets_only_canvas_and_original_instruction(public, config, model):
    call = native_request(model, public, config)
    text = json.dumps(call)
    assert "mask" not in text.replace("instance_masks", "") and "single" not in text
    expected = FLUX3_PREFIX + TEXT if model == "flux3" else TEXT
    assert call["prompt"] == expected
    images = set(call["images"]) | {call[k] for k in ("image", "planner_image", "editor_image",
                                                      "grounding_image", "edit_image") if k in call}
    assert images == {public["source"]["path"]}


def test_native_parameters_follow_frozen_specifications(public, config):
    assert native_request("qwen21", public, config)["parameters"] == {
        "num_inference_steps": 40, "true_cfg_scale": 1.0, "output_resolution": 1024, "use_kv_cache": True,
        "width": 64, "height": 48}
    flux2 = native_request("flux2_klein9b", public, config)
    assert flux2["parameters"] == {"num_inference_steps": 4, "guidance_scale": 1.0, "max_sequence_length": 512,
                                   "width": 64, "height": 48}
    assert flux2["weight_revision"] == "92196c8e11f7b6cf2b7493e037d8c5345c559216"
    flux3 = native_request("flux3", public, config)
    assert flux3["parameters"] == {"model": "distilled", "steps": 16, "guidance": None, "pup": False,
                                   "safety": False, "width": 64, "height": 48}
    mice = native_request("mice", public, config)
    assert mice["regional_units"] == [] and mice["global_unit_ids"] == ["U1"] and mice["model_size"] == [64, 48]
    mirage = native_request("mirage", public, config)
    assert mirage["parser_inputs"] == [TEXT] and config["model_specifications"]["mirage"]["parameters"][
        "patch_ratio"] == 0.2
    replan = native_request("replan", public, config)
    assert "seed" not in replan["parameters"] and "native_planner_max_new_tokens" not in replan["parameters"]


def test_sitedit_configuration_is_the_frozen_main_row(config):
    main_row = json.loads(Path("/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/"
                               "deps/sitedit-aa5a414/configs/ifbench/main_row.json").read_text())
    assert config["sitedit"] == main_row


# ------------------------------------------------------------------------------------------------ placement


SPAN = "<|mt_start|><|mt_0001|><|mt_0300|><|mt_end|>"


@pytest.mark.parametrize("text,expected,rule", [
    ("Remove the half full mug of beer to the left of the pizza.",
     "Remove the half full mug of beer to the left of the pizza {}.", "remove_end"),
    ("Can the horse which has a blue color rein be white?",
     "Can the horse which has a blue color rein {} be white?", "question_be"),
    ("Change the color of the bag next to the man to red.",
     "Change the color of the bag next to the man {} to red.", "attribute_method"),
    ("Replace the left cup with a teapot.", "Replace the left cup {} with a teapot.", "replace_with"),
    ("Add a red hat to the person on the left.", "Add a red hat to the person on the left {}.", "add_end"),
    ("Turn the second car from the right into a truck.",
     "Turn the second car from the right {} into a truck.", "attribute_into"),
    ("Give the man in the blue shirt a beard.", "Give the man in the blue shirt {} a beard.", "give_before_object"),
    ("Can you remove the dog on the sofa?", "Can you remove the dog on the sofa {}?", "remove_end"),
    ("The zebra on the right should be pink.", "The zebra on the right should be pink {}.", "fallback_end"),
])
def test_token_follows_the_selector_phrase(text, expected, rule):
    from samtok_benchmark.external_refedit.placement import place

    placed, info = place(text, SPAN)
    assert info["rule"] == rule
    assert placed == expected.format(SPAN)
    assert placed.replace(" " + SPAN, "") == text


# ------------------------------------------------------------------------------------------------ scoring


def test_official_mask_uses_first_polygon_and_15px_dilation():
    import cv2
    from PIL import ImageDraw

    polygons = [[10, 10, 30, 10, 30, 30, 10, 30], [40, 40, 50, 40, 50, 50]]
    got = score.official_mask(json.dumps(polygons), (64, 64))
    reference = Image.new("L", (64, 64), 0)
    ImageDraw.Draw(reference).polygon(polygons[0], outline=1, fill=1)
    expected = cv2.dilate(np.array(reference), np.ones((15, 15), np.uint8), iterations=1)
    assert np.array_equal(got, expected) and got[45, 45] == 0 and got[3, 3] == 1 and got[2, 2] == 0


@pytest.mark.parametrize("text,kind,expected", [
    ('{"score": [7, 9], "reasoning": "ok"}', "sc", (7.0, 9.0)),
    ('```json\n{"score": [3, 10], "reasoning": "x"}\n```', "sc", (3.0, 10.0)),
    ('{"score": 8, "reasoning": "fine"}', "pq", 8.0),
    ('{"score": [6], "reasoning": "fine"}', "pq", 6.0),
    ('{"score": [11, 2]}', "sc", None),
    ('{"score": [5]}', "sc", None),
    ("no json here", "pq", None),
    ('{"score": true}', "pq", None),
])
def test_unparsable_or_out_of_range_answers_are_missing_not_zero(text, kind, expected):
    answer = score.parse_answer(text, kind)
    if expected is None:
        assert answer is None
    elif kind == "sc":
        assert (answer["s1"], answer["s2"]) == expected
    else:
        assert answer["pq"] == expected


def test_paid_ledger_refuses_beyond_cap(tmp_path):
    ledger = score.Ledger(tmp_path / "ledger.jsonl", 2)
    assert ledger.claim({"x": 1}) == 1
    assert score.Ledger(tmp_path / "ledger.jsonl", 2).claim({"x": 2}) == 2
    with pytest.raises(RuntimeError):
        ledger.claim({"x": 3})
    assert len((tmp_path / "ledger.jsonl").read_text().splitlines()) == 2


def _scored(directory, case, s1, s2, pq):
    path = directory / "cases" / case
    path.mkdir(parents=True)
    (path / "sc.json").write_text(json.dumps({"answer": {"s1": s1, "s2": s2}}))
    (path / "pq.json").write_text(json.dumps({"answer": {"pq": pq}}))


def test_overall_is_per_image_mean_and_missing_is_not_zero(tmp_path):
    cases = ["000", "001", "100", "101"]
    for model, values in {"sitedit": [(8, 6, 9), (4, 9, 4), (6, 6, 9), None],
                          "qwen21": [(5, 5, 5), (5, 5, 5), (5, 5, 5), (5, 5, 5)]}.items():
        directory = tmp_path / model
        bindings = []
        for case, value in zip(cases, values):
            bindings.append({"case_id": case, "category": "Easy" if int(case) < 100 else "Hard"})
            if value:
                _scored(directory, case, *value)
        (directory / "JOB.json").write_text(json.dumps({"total": 4, "valid_outputs": 4, "unscorable": [],
                                                        "bindings": bindings}))
    report = score.aggregate(tmp_path, ["sitedit", "qwen21"], replicates=200)
    ours = report["rows"][0]
    easy = ours["splits"]["Easy"]
    assert easy["n"] == 2 and easy["SC"] == pytest.approx(5.0)
    assert easy["O"] == pytest.approx((math.sqrt(6 * 9) + math.sqrt(4 * 4)) / 2)
    assert ours["judge_missing"] == 1 and ours["splits"]["Hard"]["n"] == 1
    assert report["paired_reference_minus_baseline"]["qwen21"]["All"]["n_common"] == 3


# ------------------------------------------------------------------------------------------------ data + worker


def _fake_dataset(root, n):
    pa = pytest.importorskip("pyarrow")
    import io

    import pyarrow.parquet as pq

    rows = {"input_image": [], "editing_instruction": [], "edit_instruction_single": [], "mask": [],
            "category": []}
    for i in range(n):
        buffer = io.BytesIO()
        Image.new("RGB", (40 + i, 30), (i * 20 % 255, 80, 120)).save(buffer, format="JPEG")
        rows["input_image"].append({"bytes": buffer.getvalue(), "path": None})
        rows["editing_instruction"].append(f"Remove the cup number {i}.")
        rows["edit_instruction_single"].append("Remove the cup.")
        rows["mask"].append(json.dumps([[2, 2, 20, 2, 20, 20, 2, 20]]))
        rows["category"].append("Easy" if i < n // 2 else "Hard")
    raw = root / "raw"
    raw.mkdir(parents=True)
    pq.write_table(pa.table(rows), raw / "test-00000-of-00001.parquet")
    (raw / "README.md").write_text("card")
    (root / "SOURCE.json").write_text(json.dumps({"revision": data.DATASET_REVISION, "files": [
        {"path": "raw/test-00000-of-00001.parquet", "sha256": sha256_file(raw / "test-00000-of-00001.parquet")},
        {"path": "raw/README.md", "sha256": sha256_file(raw / "README.md")}]}))


def test_extract_prepare_and_worker_never_resample(tmp_path, monkeypatch, config):
    from samtok_benchmark.external_refedit import worker

    n = 4
    monkeypatch.setattr(data, "NUM_CASES", n)
    monkeypatch.setattr(data, "EASY_CASES", n // 2)
    _fake_dataset(tmp_path / "ds", n)
    receipt = data.extract(tmp_path / "ds")
    assert receipt["rows"] == n and receipt["category_mismatches_with_index_rule"] == []
    index = data.prepare(tmp_path / "ds", tmp_path / "bundle")
    private = json.loads((tmp_path / "bundle/private/evaluation.json").read_text())
    assert private[0]["edit_instruction_single"] == "Remove the cup."
    public = json.loads(Path(index["cases"][0]["public"]).read_text())
    assert set(public) == data.PUBLIC_KEYS and public["instruction"] == "Remove the cup number 0."

    calls = []

    class Fake:
        def run(self, public, out, previous=None):
            calls.append(public["case_id"])
            return Image.new("RGB", tuple(public["source"]["size"]), "white"), {"calls": {"fake": 1}}

    monkeypatch.setattr(worker, "verify_config", lambda c: None)
    monkeypatch.setattr(worker, "load_bundle", lambda b, c=None: data.load_bundle(b, c))
    import samtok_benchmark.external_refedit.adapters as adapters
    monkeypatch.setattr(adapters, "build", lambda *a: Fake())
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(config))
    ids = [c["case_id"] for c in index["cases"]]
    out = tmp_path / "run"
    # A crashed earlier claim without a terminal record must not be resampled.
    (out / "qwen21/edit" / ids[1]).mkdir(parents=True)
    (out / "qwen21/edit" / ids[1] / "ADMITTED.json").write_text("{}")
    first = worker.run(tmp_path / "bundle", cfg_path, out, "qwen21", "edit", ids)
    assert first["completed"] == n - 1 and first["unknown"] == 1 and ids[1] not in calls
    result = json.loads((out / "qwen21/edit" / ids[0] / "result.json").read_text())
    assert result["output_size"] == private[0]["source"]["size"]
    second = worker.run(tmp_path / "bundle", cfg_path, out, "qwen21", "edit", ids)
    assert second["reused"] == n - 1 and len(calls) == n - 1
