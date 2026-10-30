import json
import pytest
from samtok_benchmark.ifbench.dev_rejudge13 import pending_keys, effective
from samtok_benchmark.io import write_json


def test_failed_additional_attempt_is_terminal(tmp_path):
    write_json(tmp_path / "records/k.json", {"status": "judge-failed"})
    write_json(tmp_path / "admitted/k.json", {})
    assert pending_keys(["k"], tmp_path) == set()


def test_submitted_without_response_never_resampled(tmp_path):
    write_json(tmp_path / "admitted/k.json", {})
    with pytest.raises(ValueError, match="automatic retry forbidden"):
        pending_keys(["k"], tmp_path)


def test_scope_cannot_expand(tmp_path):
    write_json(tmp_path / "records/other.json", {})
    with pytest.raises(ValueError, match="outside"):
        pending_keys(["k"], tmp_path)


def test_missing_metric_remains_failed_after_single_additional_answer(tmp_path):
    f = {"score": 4, "pass": True, "evidence": "Original evidence"}
    text = json.dumps({"units": [{"id": "U1", "E": f, "P": f}], "global_P": f, "global_Q": f})
    raw = {"status": "judge-failed", "raw_response": {"text": text, "finish_reason": "stop"}}
    p = tmp_path / "raw.json"
    write_json(p, raw)
    out = effective(raw, ["U1"], p, "first", "repair")
    assert out["status"] == "judge-failed"
    assert out["additional_judge_calls"] == 1
    assert out["raw_response"] == raw["raw_response"]


def test_approved_threshold_repair_adds_no_model_call(tmp_path):
    f = {"score": 4, "pass": False, "evidence": "Original evidence"}
    text = json.dumps(
        {"units": [{"id": "U1", "E": f, "P": f, "Q": f}], "global_P": f, "global_Q": f}
    )
    raw = {"status": "judge-failed", "raw_response": {"text": text, "finish_reason": "stop"}}
    p = tmp_path / "raw.json"
    write_json(p, raw)
    out = effective(raw, ["U1"], p, "first", "repair")
    assert out["status"] == "scored" and out["deterministic_repair_used"]
    assert out["repair_inference_calls"] == 0 and out["additional_judge_calls"] == 1
    assert out["scores"]["units"][0]["E"]["score"] == 4
