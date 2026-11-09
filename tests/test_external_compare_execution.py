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
        "device_policy": {"max_concurrent": 4},
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


def test_four_card_pool_avoids_new_foreign_occupancy():
    pool = execution.DevicePool(["0", "1", "3", "4"])
    snapshot = {str(i): (1605, 81559) for i in range(8)}
    for gpu in ("2", "6", "7"):
        snapshot[gpu] = (50000, 81559)
    assert [pool.claim(snapshot) for _ in range(4)] == ["0", "1", "3", "4"]
    assert pool.claim(snapshot) is None
    pool.release("1")
    snapshot["1"] = (50000, 81559)
    assert pool.claim(snapshot) == "5"
    assert pool.held == {"0", "3", "4", "5"}
