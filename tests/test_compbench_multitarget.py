"""Regression contracts for per-target codes, original information and immutable reruns."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from samtok_benchmark.external_compbench.multitarget.text import (
    compile_instruction,
    validate_enumeration,
)
from samtok_benchmark.io import digest

METHOD = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/deps/sitedit-aa5a414"
)


def test_coordinate_two_objects_without_splitting_colours():
    original = (
        "add a white and red fish above the yellow fish and a black and red fish on the upper right"
    )
    row = compile_instruction(original)
    assert row["units"] == [
        "add a white and red fish above the yellow fish",
        "add a black and red fish on the upper right",
    ]


def test_references_and_shared_adjectives_are_preserved():
    assert compile_instruction("add two birds flying above the birds")["units"] == [
        "add one bird flying above the birds",
        "add another bird flying above the birds",
    ]
    assert compile_instruction("add two giraffes on the left of the giraffes")["units"] == [
        "add one giraffe on the left of the giraffes",
        "add another giraffe on the left of the giraffes",
    ]
    assert compile_instruction("remove the leftmost and rightmost white cow")["units"] == [
        "remove the leftmost white cow",
        "remove rightmost white cow",
    ]
    assert compile_instruction("remove the grey and the yellow bird on the rightmost of the birds")[
        "units"
    ] == ["remove the grey bird", "remove the yellow bird on the rightmost of the birds"]


def test_count_expansion_adds_no_spatial_hint():
    assert compile_instruction("remove the two sea turtles")["units"] == [
        "remove one of the two sea turtles",
        "remove the other of the two sea turtles",
    ]
    assert compile_instruction("add two white goats")["units"] == [
        "add one white goat",
        "add another white goat",
    ]
    for text in [
        "remove the rabbits",
        "remove the planes",
        "remove all the black ducks except the right one",
    ]:
        result = compile_instruction(text)
        assert result["mode"] == "native_enumeration" and not result["units"]


def test_not_every_and_is_a_second_target():
    for text in ["add a black and white fish", "remove the black and white dog"]:
        with pytest.raises(ValueError):
            compile_instruction(text)


def test_native_enumeration_is_strict_and_keeps_removal():
    row = [
        {"label": "U1", "instruction": "remove the rabbit on the left"},
        {"label": "U2", "instruction": "remove the rabbit on the right"},
    ]
    assert validate_enumeration(row) == [u["instruction"] for u in row]
    for bad in [
        row[:1],
        row[::-1],
        row + [row[0]],
        [{**row[0], "mask": "private"}, row[1]],
        [{**row[0], "instruction": "add a rabbit"}, row[1]],
    ]:
        with pytest.raises(ValueError):
            validate_enumeration(bad)


@pytest.fixture
def native_method(monkeypatch):
    if not (METHOD / "src").exists():
        pytest.skip("Frozen SITEdit dependency is not installed in this checkout")
    monkeypatch.syspath_prepend(str(METHOD / "src"))


def make_public(tmp_path):
    from samtok_benchmark.external_compbench.multitarget.text import compile_instruction
    from samtok_benchmark.external_full.data import make_public
    from samtok_benchmark.io import sha256_file

    path = tmp_path / "input.png"
    Image.new("RGB", (64, 64), "white").save(path)
    original = "add a red fish on the left and a blue fish on the right"
    row = make_public(
        "test",
        {"path": str(path), "sha256": sha256_file(path), "size": [64, 64]},
        original,
        tmp_path / "public",
    )
    public = json.loads(Path(row["public"]).read_text())
    decomposition = {
        "case_id": "test",
        "instruction": original,
        "public_digest": public["input_digest"],
        **compile_instruction(original),
    }
    return public, decomposition


def test_one_pass1_call_returns_and_binds_each_unit(tmp_path, native_method):
    from samtok_benchmark.external_compbench.multitarget.adapters import MultiTokens, multi_prompt
    from samtok_edit21.preparation.round2_data import multi_edit_prompt
    from samtok_edit21.data.protocol import strip_tokens

    public, decomposition = make_public(tmp_path)
    calls = []
    spans = [
        "<|mt_start|><|mt_0001|><|mt_0257|><|mt_end|>",
        "<|mt_start|><|mt_0002|><|mt_0258|><|mt_end|>",
    ]

    def ground(image, request, **kwargs):
        calls.append(request)
        assert [t["instruction"] for t in request["targets"]] == decomposition["units"]
        assert all(t["locator"] == "none" and "region" not in t for t in request["targets"])
        return {
            "raw": "test",
            "parsed": {"complete": True, "spans": dict(zip(["U1", "U2"], spans))},
        }

    adapter = MultiTokens.__new__(MultiTokens)
    adapter.method = {"pass1_max_new_tokens": 512}
    adapter.by_id = {"test": decomposition}
    adapter.models = SimpleNamespace(
        grounder=SimpleNamespace(ground=ground),
        codec=SimpleNamespace(decode_strict=lambda *a: [np.ones((8, 8), dtype=bool)]),
    )
    out = tmp_path / "tokens"
    out.mkdir()
    _, answer = adapter.run(public, out)
    assert len(calls) == 1 and answer["calls"]["grounder_requests"] == 1
    assert answer["calls"]["enumeration_requests"] == 0
    prompt, placement, guided = multi_prompt(public, answer["native"])
    assert guided and placement["decomposition_digest"] == digest(decomposition["units"])
    expected = multi_edit_prompt([f"{s} {t}" for s, t in zip(decomposition["units"], spans)])
    assert prompt == expected
    assert strip_tokens(prompt) == multi_edit_prompt(decomposition["units"])
    assert (
        prompt.index("U1:") < prompt.index(spans[0]) < prompt.index("U2:") < prompt.index(spans[1])
    )
    assert public["instruction"] == decomposition["instruction"]


def test_native_prompt_rejects_wrong_unit_order(tmp_path, native_method):
    from samtok_benchmark.external_compbench.multitarget.adapters import multi_prompt

    public, decomposition = make_public(tmp_path)
    tokens = {
        "original_instruction": public["instruction"],
        "decomposition_digest": "test",
        "units": [
            {"id": "U2", "instruction": decomposition["units"][0], "token": None},
            {"id": "U1", "instruction": decomposition["units"][1], "token": None},
        ],
    }
    with pytest.raises(ValueError, match="ordering"):
        multi_prompt(public, tokens)


def test_runtime_wrapper_restores_frozen_modules():
    from samtok_benchmark.external_compbench.multitarget.worker import corrected_implementation
    from samtok_benchmark.external_full import adapters, worker
    from samtok_benchmark.external_refedit import adapters as native

    old = adapters.build, worker.source_identity, native.sitedit_prompt
    with pytest.raises(RuntimeError):
        with corrected_implementation():
            assert (adapters.build, worker.source_identity, native.sitedit_prompt) != old
            raise RuntimeError("test")
    assert (adapters.build, worker.source_identity, native.sitedit_prompt) == old


def test_full_table_replaces_fixed_cases_even_if_new_score_is_lower():
    from samtok_benchmark.external_compbench.multitarget.report import combine
    from samtok_benchmark.external_full.score import METRICS

    original = {"models": ["sitedit", "qwen21"], "per_case": []}
    for model in original["models"]:
        for i in range(3285):
            original["per_case"].append(
                {
                    "model": model,
                    "case_id": str(i),
                    "task": "add",
                    "status": "completed",
                    "metrics": dict.fromkeys(METRICS, 0.9),
                }
            )
    replacement = {**original["per_case"][0], "metrics": dict.fromkeys(METRICS, 0.1)}
    plan = {
        "case_ids": ["0"],
        "digest": "test",
        "original_report": "original",
        "original_report_sha256": "test",
    }
    result = combine(plan, original, {"per_case": [replacement]})
    assert result["per_case"][0]["metrics"]["LC-I"] == 0.1
    assert result["per_case"][1]["metrics"]["LC-I"] == 0.9
    assert result["rows"]["qwen21"]["tasks"][0]["scored"] == 3285
    assert result["rows"]["sitedit"]["tasks"][0]["scored"] == 3285
    replacement = {**replacement, "status": "failed", "metrics": None}
    result = combine(plan, original, {"per_case": [replacement]})
    assert result["per_case"][0]["status"] == "failed"
    assert result["rows"]["sitedit"]["tasks"][0]["scored"] == 3284
    with pytest.raises(ValueError, match="cover all"):
        combine(plan, original, {"per_case": []})
