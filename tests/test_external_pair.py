"""Cohort isolation, complete chains and safe local authorization contracts."""

from collections import Counter

import pytest

from samtok_benchmark.external_pair.runner import partition
from samtok_benchmark.external_pair.selection import quotas, select
from samtok_benchmark.external_pair import worker


def synthetic_compbench():
    cases, annotations = [], []
    for task in (
        "add",
        "remove",
        "replace",
        "implicit_reasoning",
        "multi_object_add",
        "multi_object_remove",
        "multi_turn_add",
        "multi_turn_remove",
    ):
        for i in range(45):
            sid = f"{task}-{i}"
            for turn in (1, 2) if task.startswith("multi_turn") else (0,):
                cid = f"{sid}-{turn}"
                cases.append(
                    {
                        "case_id": cid,
                        "sequence_id": sid,
                        "task": task,
                        "turn": turn,
                        "parent_case_id": f"{sid}-1" if turn == 2 else None,
                    }
                )
                annotations.append(
                    {
                        "case_id": cid,
                        "upstream_file": task,
                        "upstream_row": i * 3 + turn,
                        "canonical_source": {"sha256": sid},
                    }
                )
    return {"cases": cases}, annotations


def test_fixed_selection_and_source_holdout():
    index, private = synthetic_compbench()
    # Previously inspected turn 2 excludes its preceding turn too.
    prior = {"selected": [{"file": "multi_turn_add", "row": 2}]}
    a = select("compbench", index, private, prior, ["remove-1-0"])
    b = select(
        "compbench",
        {"cases": list(reversed(index["cases"]))},
        list(reversed(private)),
        prior,
        ["remove-1-0"],
    )
    assert a == b
    assert len(a["case_ids"]) == 240
    assert not {"multi_turn_add-0-1", "multi_turn_add-0-2", "remove-1-0"} & set(a["case_ids"])
    assert Counter(r["task"] for r in a["rows"]) == dict.fromkeys(
        {r["task"] for r in a["rows"]}, 30
    )
    assert a["independent_source_clusters"] == 210
    shards = partition(index, a["case_ids"], list(map(str, range(8))))
    assert sorted(len(rows) for rows in shards.values()) == [30] * 8
    owners = {r["case_id"]: gpu for gpu, rows in shards.items() for r in rows}
    assert len(owners) == 240
    for r in a["rows"]:
        if r["turn"] == 2:
            assert owners[r["case_id"]] == owners[r["case_id"][:-1] + "1"]


def test_proportional_pair_quotas():
    assert quotas({"a": 10, "b": 20, "c": 70}, 20) == {"a": 2, "b": 4, "c": 14}
    assert quotas({"small": 1, "large": 99}, 10) == {"small": 1, "large": 9}
    with pytest.raises(ValueError):
        quotas({"a": 1}, 2)


def test_local_authorization_preserves_existing_jobs(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setattr(worker.subprocess, "check_output", lambda *a, **k: "1605, 81559\n")
    worker.guard()
    monkeypatch.setattr(worker.subprocess, "check_output", lambda *a, **k: "3000, 81559\n")
    with pytest.raises(RuntimeError, match="occupied"):
        worker.guard()
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1")
    with pytest.raises(RuntimeError, match="Exactly one"):
        worker.guard()
