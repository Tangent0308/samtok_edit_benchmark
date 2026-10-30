"""Synthetic unit tests only; none of these fixtures are experiment results."""

import json
from pathlib import Path

import numpy as np
import pytest

from samtok_benchmark.io import digest, sha256_file, write_json
from samtok_benchmark.ifbench import dev_judge as canonical
from samtok_benchmark.ifbench.fairness_dev_judge import (
    Cache,
    effective,
    restore_and_cache,
    validate_scores,
    verify_raw,
)
from samtok_benchmark.ifbench.dev_judge_stream import scored
from samtok_benchmark.ifbench.fairness_dev_report import Bootstrap, derived, make_row


def scores(k, success=True):
    def block(d):
        value = 4 if success else 0
        return {
            "score": value,
            "pass": value == 4 if d == "E" else value >= 3,
            "evidence": "Synthetic unit-test evidence.",
        }

    return {
        "units": [{"id": f"U{i + 1}", **{d: block(d) for d in "EPQ"}} for i in range(k)],
        "global_P": block("P"),
        "global_Q": block("Q"),
    }


def test_fixed_threshold_rejects_inconsistent_pass():
    value = scores(2)
    value["units"][0]["E"]["score"] = 3
    with pytest.raises(ValueError, match="fixed threshold"):
        validate_scores(value, ["U1", "U2"])


def test_model_collection_preserves_full_order_and_shared_output_keys(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from PIL import Image
    from samtok_benchmark.ifbench import fairness_dev_judge as judge
    from samtok_benchmark.ifbench import fairness_dev_plan as plan_api

    image = tmp_path / "output.png"
    Image.new("RGB", (16, 16)).save(image)
    case = {
        "id": "synthetic",
        "source": {"sha256": "source", "size": [16, 16]},
        "units": [
            {
                "id": "U1",
                "operation": "attribute",
                "instruction_ref": "Change color",
                "completion_requirement": "Color changed",
                "preserve": [],
                "target": {"mask_sha256": "mask"},
            }
        ],
    }
    tasks = []
    for model, status in [("first", "generated"), ("second", "generated"), ("failed", "failed")]:
        key = f"{model}/S1/synthetic"
        task = {
            "key": key,
            "model": model,
            "case_id": "synthetic",
            "setting": "S1",
            "result_path": str(tmp_path / model / "result.json"),
            "request_path": None,
            "request_sha256": "request",
            "public_digest": "public",
            "scientific_digest": key,
        }
        record = {
            **task,
            "plan_digest": "full-plan",
            "task_id": key,
            "stage": "edit",
            "seed": 42,
            "status": status,
            "output_image": str(image),
            "output_sha256": sha256_file(image),
        }
        write_json(task["result_path"], record)
        tasks.append(task)
    context = {
        "plan": {"digest": "full-plan", "settings": ["S1"], "tasks": tasks},
        "order": ["first", "second", "failed"],
        "case_ids": ["synthetic"],
        "base": tmp_path,
        "cases": {"synthetic": case},
        "config": {"synthetic": True},
    }

    def verify_unchanged_plan(plan, task):
        assert plan["tasks"] is tasks and plan["digest"] == "full-plan"

    monkeypatch.setattr(plan_api, "verify_task", verify_unchanged_plan)
    full_bindings, full_jobs = judge.collect(context)
    with ThreadPoolExecutor(max_workers=3) as pool:
        parts = list(pool.map(lambda m: judge.collect(context, model=m), context["order"]))
    assert [b for bindings, _ in parts for b in bindings] == full_bindings
    assert len(full_jobs) == 1
    only_job = next(iter(full_jobs.values()))
    assert only_job["logical_keys"] == [tasks[0]["key"], tasks[1]["key"]]
    assert parts[0][1].keys() == parts[1][1].keys() == full_jobs.keys()
    assert parts[2][0][0]["generation_status"] == "failed" and parts[2][1] == {}
    with pytest.raises(ValueError, match="unregistered model"):
        judge.collect(context, model="unknown")


def test_truncated_answer_not_repaired(tmp_path):
    raw = {
        "status": "judge-failed",
        "raw_response": {"text": json.dumps(scores(2)), "finish_reason": "length"},
        "reason": "Truncated",
    }
    path = tmp_path / "raw.json"
    write_json(path, raw)
    before = read_bytes(path)
    value = effective(raw, ["U1", "U2"], path)
    assert value["status"] == "judge-failed" and not value["deterministic_repair_used"]
    assert "scores" not in value and read_bytes(path) == before


def read_bytes(path):
    return Path(path).read_bytes()


def test_admitted_without_raw_is_never_retried(tmp_path):
    write_json(tmp_path / "judge/admitted/unresolved.json", {"key": "unresolved"})
    with pytest.raises(RuntimeError, match="no automatic retry"):
        restore_and_cache({"root": tmp_path}, {}, Cache(None, {"synthetic": True}))


def test_cache_rejects_other_output_even_if_score_valid(tmp_path):
    config = {"synthetic": True}
    case = {
        "id": "synthetic-case",
        "source": {"sha256": "source"},
        "units": [
            {
                "id": f"U{i + 1}",
                "operation": "attribute",
                "instruction_ref": "Synthetic instruction",
                "completion_requirement": "Synthetic completion",
                "preserve": [],
                "target": {"mask_sha256": f"mask{i}"},
            }
            for i in range(2)
        ],
    }
    key = canonical.binding(case, "expected-output", config)
    value = {
        "key": key,
        "run_id": digest(config),
        "output_sha256": "other-output",
        "status": "scored",
        "scores": scores(2),
        "raw_response": {"text": json.dumps(scores(2)), "finish_reason": "stop"},
    }
    record = tmp_path / "record.json"
    write_json(record, value)
    index = tmp_path / "index.json"
    write_json(
        index,
        {
            "config": config,
            "entries": {
                key: {
                    "effective_record": str(record),
                    "sha256": sha256_file(record),
                    "provenance_files": [{"path": str(record), "sha256": sha256_file(record)}],
                }
            },
        },
    )
    cache = Cache(index, config)
    with pytest.raises(ValueError, match="binding differs"):
        cache.lookup(
            {"key": key, "case": case, "record": {"output_sha256": "expected-output"}},
            {"run_id": digest(config)},
        )


def test_raw_restore_rejects_changed_output_and_scores():
    case = {"units": [{"id": "U1"}, {"id": "U2"}]}
    job = {"key": "synthetic-key", "case": case, "record": {"output_sha256": "synthetic-output"}}
    raw = scored(
        (job["key"], (case, job["record"])),
        {"text": json.dumps(scores(2)), "finish_reason": "stop"},
        "synthetic-run",
    )
    verify_raw(raw, job, {"run_id": "synthetic-run"})
    raw["output_sha256"] = "different-output"
    with pytest.raises(ValueError, match="different binding"):
        verify_raw(raw, job, {"run_id": "synthetic-run"})
    raw["output_sha256"] = job["record"]["output_sha256"]
    raw["scores"] = scores(2, False)
    with pytest.raises(ValueError, match="original parser"):
        verify_raw(raw, job, {"run_id": "synthetic-run"})


def test_cache_overlay_requires_actual_raw_chain(tmp_path):
    config = {"synthetic": True}
    case = {"units": [{"id": "U1"}, {"id": "U2"}]}
    job = {"key": "synthetic-key", "case": case, "record": {"output_sha256": "synthetic-output"}}
    raw = scored(
        (job["key"], (case, job["record"])),
        {"text": json.dumps(scores(2)), "finish_reason": "stop"},
        digest(config),
    )
    raw_path = tmp_path / "raw.json"
    write_json(raw_path, raw)
    overlay = effective(raw, ["U1", "U2"], raw_path)
    record = tmp_path / "effective.json"
    write_json(record, overlay)
    entry = {
        "effective_record": str(record),
        "sha256": sha256_file(record),
        "provenance_files": [{"path": str(record), "sha256": sha256_file(record)}],
    }
    index = tmp_path / "index.json"
    write_json(index, {"config": config, "entries": {job["key"]: entry}})
    with pytest.raises(ValueError, match="provenance is incomplete"):
        Cache(index, config).lookup(job, {"run_id": digest(config)})
    entry["provenance_files"].append({"path": str(raw_path), "sha256": sha256_file(raw_path)})
    write_json(index, {"config": config, "entries": {job["key"]: entry}})
    value = Cache(index, config).lookup(job, {"run_id": digest(config)})
    assert value["new_judge_calls"] == 0 and value["scores"] == raw["scores"]


def fixture():
    ks = [2, 5] * 10
    ids = [f"synthetic-{i}" for i in range(20)]
    context = {
        "case_ids": ids,
        "cases": {
            cid: {"units": [{"id": f"U{j + 1}"} for j in range(ks[i])]} for i, cid in enumerate(ids)
        },
    }
    bound = {
        ("model", "S1", cid): {
            "key": cid,
            "generation_status": "generated",
            "judge_key": cid,
            "result_path": f"/synthetic/{cid}",
            "generation_record_sha256": "synthetic",
        }
        for cid in ids
    }
    effective_records = {
        cid: {"status": "scored", "scores": scores(ks[i])} for i, cid in enumerate(ids)
    }
    return context, bound, effective_records, Bootstrap(ks)


def test_generation_failure_keeps_all_units_and_cases_in_denominator():
    context, bound, judged, boot = fixture()
    bound["model", "S1", context["case_ids"][0]]["generation_status"] = "failed-planner"
    row, draws = make_row("model", "S1", context, bound, judged, boot)
    assert row["complete"] and row["case_denominator"] == 20 and row["unit_denominator"] == 70
    assert row["UnitPass"] == 68 / 70 and row["JointPass"] == 19 / 20
    assert row["generation_failed_cases"] == 1 and row["scored_unit_denominator"] == 68
    assert len(draws["UnitPass"]) == 10000


def test_judge_failure_is_missing_not_zero_and_keeps_full_denominator():
    context, bound, judged, boot = fixture()
    judged[context["case_ids"][0]] = {"status": "judge-failed"}
    row, draws = make_row("model", "S1", context, bound, judged, boot)
    assert not row["complete"] and row["UnitPass"] is None and row["JointPass"] is None
    assert (
        row["case_denominator"] == 20
        and row["unit_denominator"] == 70
        and row["missing_units"] == 2
    )
    assert row["generation_failed_cases"] == 0 and draws == {}
    assert row["by_K"]["2"]["JointPass"] is None
    assert row["by_K"]["5"]["JointPass"] == 1


def test_paired_bootstrap_difference_zero_for_identical_rows():
    context, bound, judged, boot = fixture()
    judged[context["case_ids"][2]] = {"status": "scored", "scores": scores(2, False)}
    row, draws = make_row("model", "S1", context, bound, judged, boot)
    settings = ["S1", "S2-point", "S2-box", "S2-mask", "S3-point", "S3-box", "S3-mask", "S4-noref"]
    result = derived({s: row for s in settings}, {s: draws for s in settings})
    for metric in result:
        if metric["diagnostic"] != "R_mod":
            assert abs(metric["value"]) < 1e-15
            assert np.max(np.abs(metric["bootstrap"]["CI95"])) < 1e-15
        else:
            assert metric["value"] == 1


def test_zero_robustness_denominator_is_na():
    context, bound, judged, boot = fixture()
    for key in judged:
        judged[key]["scores"] = scores(len(context["cases"][key]["units"]), False)
    row, draws = make_row("model", "S1", context, bound, judged, boot)
    settings = ["S1", "S2-point", "S2-box", "S2-mask", "S3-point", "S3-box", "S3-mask", "S4-noref"]
    result = derived({s: row for s in settings}, {s: draws for s in settings})
    for value in result:
        if value["diagnostic"] == "R_mod":
            assert value["value"] is None and value["bootstrap"]["CI95"] is None
            assert value["bootstrap"]["zero_denominator_replicates"] == 10000
