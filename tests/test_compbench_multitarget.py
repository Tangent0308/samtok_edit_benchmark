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


# --- Smoke gate: native method outcomes versus engineering faults (2026-11-10 revision) ---

SPANS = [
    "<|mt_start|><|mt_0001|><|mt_0257|><|mt_end|>",
    "<|mt_start|><|mt_0002|><|mt_0258|><|mt_end|>",
]


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _render(units):
    """Same line structure as the native numbered template: one region code per unit line."""
    lines = ["Execute all numbered instructions and keep everything else unchanged."]
    for u in units:
        lines.append(f"{u['id']}: {u['instruction']}" + (f" {u['token']}" if u["token"] else ""))
    return "\n".join(lines)


def _completed(root, row, *, seconds=(2.0, 30.0), peak=(20, 40), prompt=None, units=None):
    units = units or [
        {"id": f"U{i}", "instruction": s, "token": SPANS[i - 1], "source": "pass1"}
        for i, s in enumerate(row["units"], 1)
    ]
    native = {"units": units, "original_instruction": row["instruction"]}
    _write(
        root / "run/sitedit/tokens" / row["case_id"] / "result.json",
        {"status": "completed", "native": native, "inference_seconds": seconds[0],
         "peak_gpu_reserved_bytes": peak[0]},
    )
    _write(
        root / "run/sitedit/edit" / row["case_id"] / "result.json",
        {"status": "completed", "inference_seconds": seconds[1], "peak_gpu_reserved_bytes": peak[1],
         "output_image": "out.png", "placement": {"units": [{"id": u["id"]} for u in units]},
         "native": {"conditioning_prompt": prompt or _render(units)}},
    )
    _write(root / "scores/sitedit" / row["case_id"] / "local.json",
           {"status": "completed", "metrics": {"LC-I": 0.5}})


ONE_TARGET = '[{"label": "U1","instruction": "remove the rabbits"}]<|im_end|>'


def _native_failure(root, row, raw=ONE_TARGET, error=None):
    from samtok_benchmark.external_compbench.multitarget.adapters import (
        ENUMERATION_PROMPT,
        parse_enumeration,
    )

    if error is None:
        try:
            parse_enumeration(raw)
            error = "no error"
        except ValueError as exc:
            error = repr(exc)
    tokens = root / "run/sitedit/tokens" / row["case_id"]
    prompt = ENUMERATION_PROMPT + row["instruction"]
    _write(tokens / "enumeration.json", {"prompt": prompt, "raw": raw})
    _write(tokens / "result.json", {"status": "failed", "fatal": False, "error": error})
    _write(root / "run/sitedit/edit" / row["case_id"] / "result.json",
           {"status": "blocked_dependency", "fatal": False,
            "error": "RuntimeError('Previous native stage failed; no editor call made')"})
    _write(root / "scores/sitedit" / row["case_id"] / "local.json",
           {"status": "generation_failed", "generation_status": "blocked_dependency",
            "metrics": None})


def _plan():
    rows = [
        {"case_id": "a", "mode": "text", "instruction": "add a red fish and a blue fish",
         "units": ["add a red fish", "add a blue fish"]},
        {"case_id": "b", "mode": "text", "instruction": "remove the two cats",
         "units": ["remove one of the two cats", "remove the other of the two cats"]},
        {"case_id": "c", "mode": "native_enumeration", "instruction": "remove the rabbits",
         "units": []},
    ]
    return {"cases": rows, "case_ids": [r["case_id"] for r in rows]}


def test_smoke_gate_keeps_native_enumeration_failure_and_continues(tmp_path):
    from samtok_benchmark.external_compbench.multitarget.outcomes import smoke_gate, summarize

    plan = _plan()
    _completed(tmp_path, plan["cases"][0], seconds=(2.4, 30.3), peak=(20, 44))
    _completed(tmp_path, plan["cases"][1], seconds=(1.8, 25.2), peak=(20, 43))
    _native_failure(tmp_path, plan["cases"][2])
    summary = summarize(plan, tmp_path / "run", tmp_path / "scores")
    smoke_gate(summary)  # does not raise
    assert summary["counts"] == {"completed": 2, "native_failure": 1}
    assert summary["completed"] == 2 and len(summary["native_failures"]) == 1
    failure = summary["native_failures"][0]
    assert failure["case_id"] == "c" and "2–5 targets" in failure["error"]
    assert failure["downstream"] == {"edit": "blocked_dependency", "score": "generation_failed"}
    # Timing/memory only from completed requests, never from fields absent in failures.
    assert summary["inference_seconds"] == pytest.approx([32.7, 27.0])
    assert summary["peak_reserved_bytes"] == [44, 43]
    done = [c for c in summary["cases"] if c["outcome"] == "completed"]
    assert all(c["coded_units"] == 2 for c in done)
    assert all([u["id"] for u in c["units"]] == ["U1", "U2"] for c in done)


@pytest.mark.parametrize(
    "fault",
    [
        "cuda_error_on_native_case",
        "valid_enumeration_but_failed",
        "text_case_failed",
        "fatal_flag",
        "missing_score",
        "edit_exception",
        "score_exception",
        "dependency_not_recorded",
        "grounding_after_failed_enumeration",
    ],
)
def test_engineering_failures_stop_the_smoke(tmp_path, fault):
    from samtok_benchmark.external_compbench.multitarget.outcomes import smoke_gate, summarize

    plan = _plan()
    a, b, c = plan["cases"]
    _completed(tmp_path, a)
    _completed(tmp_path, b)
    _native_failure(tmp_path, c)
    edit_b = tmp_path / "run/sitedit/edit/b/result.json"
    score_b = tmp_path / "scores/sitedit/b/local.json"
    tokens_c = tmp_path / "run/sitedit/tokens/c"
    if fault == "cuda_error_on_native_case":
        _native_failure(tmp_path, c, error="RuntimeError('CUDA error: out of memory')")
    elif fault == "valid_enumeration_but_failed":
        raw = json.dumps([{"label": "U1", "instruction": "remove the left rabbit"},
                          {"label": "U2", "instruction": "remove the right rabbit"}])
        _native_failure(tmp_path, c, raw=raw, error="RuntimeError('load failed')")
    elif fault == "text_case_failed":
        _write(tmp_path / "run/sitedit/tokens/b/result.json",
               {"status": "failed", "fatal": False, "error": "ValueError('x')"})
    elif fault == "fatal_flag":
        record = json.loads((tokens_c / "result.json").read_text())
        _write(tokens_c / "result.json", {**record, "fatal": True})
    elif fault == "missing_score":
        score_b.unlink()
    elif fault == "edit_exception":
        _write(edit_b, {"status": "failed", "error": "RuntimeError('CUDA error')"})
    elif fault == "score_exception":
        _write(score_b, {"status": "failed", "error": "OSError('lpips weights')", "metrics": None})
    elif fault == "dependency_not_recorded":
        score_c = tmp_path / "scores/sitedit/c/local.json"
        _write(score_c, {"status": "completed", "metrics": {"x": 1}})
    elif fault == "grounding_after_failed_enumeration":
        _write(tokens_c / "request.json", {"targets": []})
    summary = summarize(plan, tmp_path / "run", tmp_path / "scores")
    assert summary["engineering_failures"]
    with pytest.raises(RuntimeError, match="engineering failures"):
        smoke_gate(summary)


@pytest.mark.parametrize("fault", ["swapped_codes", "merged_unit", "wrong_decomposition"])
def test_completed_requires_each_code_bound_to_its_own_unit(tmp_path, fault):
    from samtok_benchmark.external_compbench.multitarget.outcomes import summarize

    plan = _plan()
    a = plan["cases"][0]
    units = [
        {"id": f"U{i}", "instruction": s, "token": SPANS[i - 1], "source": "pass1"}
        for i, s in enumerate(a["units"], 1)
    ]
    if fault == "swapped_codes":
        swapped = [{**units[0], "token": SPANS[1]}, {**units[1], "token": SPANS[0]}]
        _completed(tmp_path, a, units=units, prompt=_render(swapped))
    elif fault == "merged_unit":
        _completed(tmp_path, a, units=[{**units[0], "instruction": a["instruction"]}])
    else:
        changed = [{**u, "instruction": u["instruction"] + " now"} for u in units]
        _completed(tmp_path, a, units=changed)
    summary = summarize(plan, tmp_path / "run", tmp_path / "scores", ["a"])
    assert summary["counts"] == {"engineering_failure": 1}


def test_smoke_without_any_completed_request_stops(tmp_path):
    from samtok_benchmark.external_compbench.multitarget.outcomes import smoke_gate, summarize

    plan = _plan()
    _native_failure(tmp_path, plan["cases"][2])
    summary = summarize(plan, tmp_path / "run", tmp_path / "scores", ["c"])
    assert summary["inference_seconds"] == [] and summary["completed"] == 0
    with pytest.raises(RuntimeError, match="No smoke request completed"):
        smoke_gate(summary)


@pytest.mark.parametrize("pattern", ["same_code_for_both_units", "no_code_text_template"])
def test_native_pass1_outcomes_still_complete(tmp_path, pattern):
    """Formal r2 run: identical spans or text-only fallback are method outcomes, not faults."""
    from samtok_benchmark.external_compbench.multitarget.outcomes import summarize

    plan = _plan()
    a = plan["cases"][0]
    if pattern == "same_code_for_both_units":
        units = [
            {"id": f"U{i}", "instruction": s, "token": SPANS[0], "source": "pass1"}
            for i, s in enumerate(a["units"], 1)
        ]
        _completed(tmp_path, a, units=units)
    else:
        units = [
            {"id": f"U{i}", "instruction": s, "token": None, "source": "fallback_text"}
            for i, s in enumerate(a["units"], 1)
        ]
        _completed(tmp_path, a, units=units)
        record = tmp_path / "run/sitedit/edit/a/result.json"
        edit = json.loads(record.read_text())
        _write(record, {**edit, "placement": None})
    summary = summarize(plan, tmp_path / "run", tmp_path / "scores", ["a"])
    assert summary["counts"] == {"completed": 1}
    assert summary["cases"][0]["coded_units"] == (2 if pattern.startswith("same") else 0)


def test_missing_placement_with_codes_is_a_fault(tmp_path):
    from samtok_benchmark.external_compbench.multitarget.outcomes import summarize

    plan = _plan()
    a = plan["cases"][0]
    _completed(tmp_path, a)
    record = tmp_path / "run/sitedit/edit/a/result.json"
    _write(record, {**json.loads(record.read_text()), "placement": None})
    summary = summarize(plan, tmp_path / "run", tmp_path / "scores", ["a"])
    assert summary["counts"] == {"engineering_failure": 1}
