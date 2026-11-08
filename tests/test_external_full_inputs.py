"""Partition coverage and every method's access to the same public mask."""

from collections import Counter
import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image

from samtok_benchmark.external_full import coordination
from samtok_benchmark.external_full.mask_adapters import native_request, MASK_PROMPT
from samtok_benchmark.external_full.mask_public import asset
from samtok_benchmark.external_full.simple_report import aggregate
from samtok_benchmark.external_full.input_policy import runnable_ids
from samtok_benchmark.external_full.prepare_single import mask_public
from samtok_benchmark.io import digest

ROOT = Path(__file__).parents[1]


def entry_module():
    spec = importlib.util.spec_from_file_location(
        "entry_test", ROOT / "scripts/external_full_entry.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_four_node_eight_gpu_ownership_keeps_chains():
    cases = []
    for i in range(3193):
        for turn in (1, 2) if i < 288 else (0,):
            cases.append({"case_id": f"{i}-{turn}", "sequence_id": str(i), "turn": turn})
    index = {"cases": cases}
    groups = [entry_module().partition(index, r, coordination) for r in range(4)]
    assert sum(map(len, groups)) == 3481
    assert len(set().union(*map(set, groups))) == 3481
    totals = [len(g) for g in groups]
    assert max(totals) - min(totals) <= 1
    owners = {cid: rank for rank, group in enumerate(groups) for cid in group}
    for i in range(288):
        assert owners[f"{i}-1"] == owners[f"{i}-2"]
    gpu_jobs = []
    for group in groups:
        sequences = sorted({x["sequence_id"] for x in cases if x["case_id"] in group})
        for gpu in range(8):
            owned = set(sequences[gpu::8])
            gpu_jobs.append([x["case_id"] for x in cases if x["sequence_id"] in owned])
    assert Counter(cid for shard in gpu_jobs for cid in shard) == Counter(
        x["case_id"] for x in cases
    )


def test_mask_input_reaches_every_native_adapter(tmp_path):
    source = tmp_path / "source.png"
    mask = tmp_path / "mask.png"
    Image.new("RGB", (64, 64), "gray").save(source)
    im = Image.new("L", (64, 64), 0)
    im.paste(255, (10, 10, 40, 40))
    im.save(mask)
    public = {
        "schema": "interedit.public.v1",
        "case_id": "test",
        "source": asset(source),
        "mask": asset(mask),
        "instruction": "Add a red ball.",
    }
    public["input_digest"] = digest(public)
    cfg = json.loads(next((ROOT / "configs/external").glob("*_full4.json")).read_text())
    for model in cfg["model_specifications"]:
        out = tmp_path / model
        out.mkdir()
        request = native_request(model, public, cfg, out)
        assert request["public_input_digest"] == public["input_digest"]
        if model in {"qwen21", "qwen2511", "flux2_klein9b", "flux3"}:
            assert request["images"] == [str(source), str(mask)]
            assert public["instruction"] in request["prompt"]
            if model == "qwen21":
                assert request["prompt"] == MASK_PROMPT + public["instruction"]
        elif model == "mice":
            assert request["regional_units"][0]["region"]["path"] == str(mask)
            assert request["prompt"].count("$BREAKFLAG$") == 1
        else:
            assert request["public_annotation"]["source_mask_sha256"] == public["mask"]["sha256"]
            with Image.open(request["public_annotation"]["path"]) as marked:
                assert marked.size == (64, 64) and marked.tobytes() != Image.open(source).tobytes()
            assert request.get("editor_image", request.get("edit_image")) == str(source)


def test_omni_weights_and_failure_denominator():
    rows = [
        {"status": "completed", "metrics": {"BG_LPIPS": 0.2, "_BG_Weight": 3}},
        {"status": "completed", "metrics": {"BG_LPIPS": 0.6, "_BG_Weight": 1}},
        {"status": "generation_failed", "metrics": None},
    ]
    value = aggregate(rows, {"BG_LPIPS": "x"}, {"BG_LPIPS": "_BG_Weight"})["metrics"]["BG_LPIPS"]
    assert value["mean"] == pytest.approx(0.3)
    assert value["scored"] == 2 and value["expected"] == 3 and not value["complete"]


def test_remote_entry_refuses_other_topologies(monkeypatch):
    module = entry_module()
    monkeypatch.setenv("ARNOLD_WORKER_NUM", "2")
    monkeypatch.setenv("ARNOLD_WORKER_GPU", "8")
    monkeypatch.setenv("ARNOLD_ID", "0")
    with pytest.raises(ValueError):
        module.topology()
    monkeypatch.setenv("ARNOLD_WORKER_NUM", "4")
    monkeypatch.setenv("ARNOLD_ID", "3")
    assert module.topology() == 3


def test_invalid_data_requires_exact_explicit_decision(tmp_path):
    source, mask = tmp_path / "source.png", tmp_path / "mask.png"
    Image.new("RGB", (64, 64), "gray").save(source)
    Image.new("L", (64, 64), 0).save(mask)
    row = {
        "case_id": "bad",
        "source": asset(source),
        "mask": asset(mask),
        "instruction": "Change the selected object.",
    }
    with pytest.raises(ValueError, match="Invalid public mask"):
        mask_public(row, tmp_path / "strict")
    public = mask_public(row, tmp_path / "preserved", record_invalid=True)
    assert public["input_error"] == "official_empty_mask"
    cases = {"cases": [{"case_id": "good"}, {"case_id": "bad", **public}]}
    with pytest.raises(ValueError, match="confirmed policy"):
        runnable_ids(cases, ["good", "bad"], {})
    cfg = {"data_input_errors": {"policy": "retain-as-data-invalid-na", "case_ids": ["bad"]}}
    assert runnable_ids(cases, ["good", "bad"], cfg) == ["good"]
    assert len(cases["cases"]) == 2
    cfg["data_input_errors"]["case_ids"] = ["different"]
    with pytest.raises(ValueError, match="exact case list"):
        runnable_ids(cases, ["good", "bad"], cfg)
