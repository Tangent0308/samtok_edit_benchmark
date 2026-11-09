"""Changing scheduling hardware cannot silently change the frozen scientific plan."""

import json
import pytest

from samtok_benchmark.external_compare import execution
from samtok_benchmark.io import digest, sha256_file


@pytest.mark.parametrize(
    "gpus", [[], ["0"], ["0", "1", "2", "2"], ["0", "1", "2", "8"], list(map(str, range(8)))]
)
def test_exactly_four_distinct_authorized_cards(gpus):
    with pytest.raises(ValueError):
        execution.validate_gpus(gpus)


def test_recovery_binds_original_plan_and_gpu_list(tmp_path, monkeypatch):
    monkeypatch.setattr(execution, "source_identity", lambda: {"native.py": "fixed"})
    plan = {"cases": ["a", "b"], "configuration": "fixed"}
    plan["digest"] = digest(plan)
    original = tmp_path / "PLAN.json"
    original.write_text(json.dumps(plan))
    value = {
        "gpus": ["0", "1", "2", "3"],
        "parent_plan_digest": plan["digest"],
        "parent_plan_sha256": sha256_file(original),
        "generation_source_identity": {"native.py": "fixed"},
    }
    value["digest"] = digest(value)
    path = tmp_path / "execution.json"
    path.write_text(json.dumps(value))
    assert execution.verify(path, tmp_path, plan, value["gpus"]) == value
    with pytest.raises(ValueError, match="GPU list"):
        execution.verify(path, tmp_path, plan, ["4", "5", "6", "7"])
    original.write_text('{"changed":true}')
    with pytest.raises(ValueError, match="Original plan changed"):
        execution.verify(path, tmp_path, plan, value["gpus"])
