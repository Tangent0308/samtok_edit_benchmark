import json

import pytest

from samtok_benchmark.ifbench.dev_judge_shard import pending_items, validate_result
from samtok_benchmark.ifbench.dev_judge_stream import scored
from samtok_benchmark.io import digest, write_json


def sample():
    config = {"fixed": "config"}
    item = ("key1", ({"units": [{"id": "U1"}]}, {"output_sha256": "imagehash"}))
    field = {"score": 4, "pass": True, "evidence": "before/after"}
    raw = {
        "text": json.dumps(
            {
                "units": [{"id": "U1", "E": field, "P": field, "Q": field}],
                "global_P": field,
                "global_Q": field,
            }
        ),
        "finish_reason": "stop",
    }
    return config, item, scored(item, raw, digest(config))


def test_missing_admitted_response_refuses_resampling(tmp_path):
    _, item, _ = sample()
    write_json(tmp_path / "admitted/key1.json", {"key": "key1"})
    with pytest.raises(ValueError, match="no automatic retry"):
        pending_items([item], tmp_path)


def test_both_valid_and_failed_records_are_terminal(tmp_path):
    _, item, result = sample()
    write_json(tmp_path / "records/key1.json", result)
    assert pending_items([item], tmp_path) == []
    write_json(tmp_path / "records/key1.json", {"status": "judge-failed"})
    assert pending_items([item], tmp_path) == []


def test_shard_rejects_foreign_record(tmp_path):
    _, item, _ = sample()
    write_json(tmp_path / "records/foreign.json", {})
    with pytest.raises(ValueError, match="outside shard"):
        pending_items([item], tmp_path)


def test_merge_reparses_raw_scores_and_rejects_tampering():
    config, item, result = sample()
    validate_result(result, item, config)
    result["scores"]["global_P"]["score"] = 0
    with pytest.raises(ValueError, match="validation failed"):
        validate_result(result, item, config)


def test_merge_rejects_wrong_output_or_run():
    config, item, result = sample()
    result["output_sha256"] = "changed"
    with pytest.raises(ValueError, match="binding mismatch"):
        validate_result(result, item, config)


def test_failed_response_stays_failed_without_repair_or_resampling():
    config, item, _ = sample()
    result = scored(item, {"text": "malformed", "finish_reason": "stop"}, digest(config))
    assert result["status"] == "judge-failed"
    validate_result(result, item, config)
