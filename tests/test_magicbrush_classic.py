"""Scientific contracts for the separate classic-method extension."""

import numpy as np
import pytest

from samtok_benchmark.external_magicbrush_classic.backend import native_size
from samtok_benchmark.external_magicbrush_classic.common import select_requests, smoke_session
from samtok_benchmark.external_magicbrush_classic.report import METRICS, PENALTY, summarise


def index_fixture():
    cases = []
    for sid, length in [("1", 1), ("2", 2), ("3", 3)]:
        for turn in range(1, length + 1):
            for track in ("mask-free", "mask-provided"):
                cases.append(
                    {"session_id": sid, "case_id": f"{sid}-{turn}", "turn": turn, "track": track}
                )
    return {"sessions": ["1", "2", "3"], "cases": cases}


def test_full_cohort_and_recurrent_dependencies():
    index = index_fixture()
    items = select_requests(index, index["sessions"])
    assert len(items) == 9
    assert sum(i["mode"] == "independent" for i in items) == 6
    assert {i["session_id"] for i in items} == set(index["sessions"])
    assert all(i["track"] == "mask-free" for i in items)
    keys = {i["key"] for i in items}
    assert len(keys) == len(items)
    assert all(i["previous_key"] in keys for i in items if i["mode"] == "iterative")
    parts = [select_requests(index, index["sessions"][n::4]) for n in range(4)]
    assert sorted(i["key"] for p in parts for i in p) == sorted(keys)


def test_smoke_has_three_requests_without_score_selection():
    index = index_fixture()
    sid = smoke_session(index)
    assert sid == "2"
    assert len(select_requests(index, [sid])) == 3


def test_native_canvas_dimensions():
    assert native_size(1024, 1024) == (512, 512)
    assert native_size(512, 1024) == (256, 512)


def record(sid, number, value=None):
    item = {"session_id": sid, "key": f"mask-free/independent/{sid}-{number}"}
    if value is None:
        return item, {"status": "failed"}, None
    return (
        item,
        {"status": "completed"},
        {"status": "scored", "metrics": {m: value for m in METRICS}},
    )


def test_failed_cases_stay_in_denominator_and_session_bootstrap():
    cases = [record("1", 1, 0.2), record("1", 2), record("2", 1, 0.4)]
    indices = np.array([[0, 0], [0, 1], [1, 0], [1, 1]], dtype=np.int32)
    row = summarise("hive", "single-turn", cases, ["1", "2"], indices)
    assert row["target_count"] == 3 and row["generation_failed_count"] == 1
    assert row["measured_count"] == 2 and row["unresolved_count"] == 0
    for metric in METRICS:
        expected = (0.2 + PENALTY[metric] + 0.4) / 3
        assert row["metrics"][metric] == pytest.approx(expected)
        distribution = [(0.2 + PENALTY[metric]) / 2, expected, expected, 0.4]
        assert row["CI95"][metric] == pytest.approx(np.percentile(distribution, [2.5, 97.5]))


@pytest.mark.parametrize(
    "generation,score",
    [
        (None, None),
        ({"status": "completed"}, None),
        ({"status": "completed"}, {"status": "failed"}),
    ],
)
def test_missing_or_failed_scoring_is_never_invented(generation, score):
    case = ({"session_id": "1", "key": "mask-free/independent/1-1"}, generation, score)
    with pytest.raises(ValueError):
        summarise("hive", "single-turn", [case], ["1"], np.array([[0]], dtype=np.int32))


def test_checkpoint_loader_rejects_unreviewed_globals(tmp_path):
    import torch
    from pathlib import Path
    from samtok_benchmark.external_magicbrush_classic.backend import load_tensors

    checkpoint = tmp_path / "unreviewed.ckpt"
    torch.save({"state_dict": {"w": torch.ones(2)}, "metadata": Path("unused")}, checkpoint)
    with pytest.raises(ValueError, match="Unreviewed checkpoint globals"):
        load_tensors(checkpoint)
