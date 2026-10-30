"""Cross-version reuse must preserve native failures and scientific identity."""

from copy import deepcopy

import pytest

from samtok_benchmark.io import digest, sha256_file, write_json
from samtok_benchmark.ifbench import fairness_dev_cache as cache
from samtok_benchmark.ifbench.fairness_dev_plan import request_identity
from samtok_benchmark.ifbench.fairness_dev_worker import binding, reused_result


def fixture(tmp_path, monkeypatch):
    request = {"prompt": "public task", "parameters": {"resolution": 1024}, "seed": 42}
    public = {"source": {"size": [32, 32]}}
    parent = {
        "digest": "parent",
        "seed": 42,
        "configuration_sha256": "old",
        "model_specifications": {"mirage": {"weights": "pinned"}},
    }
    task = {
        "key": "mirage/S1/case",
        "model": "mirage",
        "setting": "S1",
        "case_id": "case",
        "request_sha256": "request",
        "public_digest": "public",
        "cache": {},
        "planner_dir": str(tmp_path / "planner"),
        "result_path": str(tmp_path / "result.json"),
    }
    task["scientific_digest"] = request_identity(parent, "mirage", request)
    result = {
        **binding(parent, task, "edit"),
        "status": "failed-planner",
        "error": "Original native JSONDecodeError",
        "inference_api_calls": 0,
    }
    write_json(task["result_path"], result)
    plan = deepcopy(parent)
    plan.update(digest="new", configuration_sha256="new-whole-run")
    new_task = deepcopy(task)
    new_task["scientific_digest"] = request_identity(plan, "mirage", request)
    receipt = {
        "parent_plan_digest": "parent",
        "original_result": task["result_path"],
        "original_result_sha256": sha256_file(tmp_path / "result.json"),
    }
    monkeypatch.setattr(cache, "completed_parent", lambda _: (parent, {task["key"]: task}))
    monkeypatch.setattr(cache, "verify_task", lambda *_: (request, public))
    return plan, new_task, receipt, request, public


def test_completed_native_failure_is_a_reusable_terminal_not_a_new_attempt(tmp_path, monkeypatch):
    plan, task, receipt, request, public = fixture(tmp_path, monkeypatch)
    value = cache.verify_completed_cache(plan, task, "edit", receipt, request, public)
    rebound = reused_result(value, binding(plan, task, "edit"), "receipt.json")
    assert rebound["status"] == "failed-planner"
    assert rebound["error"] == "Original native JSONDecodeError"
    assert rebound["plan_digest"] == "new" and rebound["reused"]
    assert rebound["inference_api_calls"] == 0


def test_resolution_or_weights_change_cannot_reuse_completed_output(tmp_path, monkeypatch):
    plan, task, receipt, request, public = fixture(tmp_path, monkeypatch)
    changed = deepcopy(request)
    changed["parameters"]["resolution"] = 2048
    with pytest.raises(ValueError, match="request/public input differs"):
        cache.verify_completed_cache(plan, task, "edit", receipt, changed, public)
    plan["model_specifications"]["mirage"]["weights"] = "different"
    with pytest.raises(ValueError, match="weights/native configuration differ"):
        cache.verify_completed_cache(plan, task, "edit", receipt, request, public)


def test_changed_parent_terminal_record_is_rejected(tmp_path, monkeypatch):
    plan, task, receipt, request, public = fixture(tmp_path, monkeypatch)
    write_json(task["result_path"], {"status": "generated", "fake": True})
    with pytest.raises(ValueError, match="Artifact changed"):
        cache.verify_completed_cache(plan, task, "edit", receipt, request, public)


def test_nested_reuse_retains_original_calls_without_counting_them_again():
    value = {
        "status": "planned",
        "native_planner_calls": 0,
        "reuse_original_metrics": {"native_planner_calls": 3},
    }
    result = reused_result(value, {"plan_digest": digest("new")}, "receipt")
    assert result["native_planner_calls"] == 0
    assert result["reuse_original_metrics"]["native_planner_calls"] == 3
