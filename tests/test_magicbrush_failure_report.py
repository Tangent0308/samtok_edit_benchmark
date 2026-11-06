"""CPU contracts for the authorized, separately labeled failure aggregation layer."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from samtok_benchmark.external_magicbrush import report as original
from samtok_benchmark.external_magicbrush.metrics import METRICS
from samtok_benchmark.io import sha256_file
from samtok_benchmark.postprocessing.magicbrush_failures import PENALTIES, build_report, publish


def fixture_report(status="failed"):
    draws = np.random.default_rng(original.BOOTSTRAP_SEED).integers(
        0, 2, size=(original.BOOTSTRAP_DRAWS, 2), dtype=np.int32
    )
    first = dict(zip(METRICS, [0.2, 0.1, 0.8, 0.8, 0.8]))
    second = dict(zip(METRICS, [0.4, 0.2, 0.6, 0.6, 0.6]))
    third = {"key": "mask-free/independent/b-1", "session_id": "b", "status": status}
    cases = [
        {
            "key": "mask-free/independent/a-1",
            "session_id": "a",
            "status": "scored",
            "metrics": first,
        },
        {
            "key": "mask-free/independent/a-2",
            "session_id": "a",
            "status": "scored",
            "metrics": second,
        },
        third,
    ]
    values = np.array([list(first.values()), list(second.values())])
    row = {
        "model": "mirage",
        "subset": "full",
        "track": "mask-free",
        "mode": "single-turn",
        "target_count": 3,
        "scored_count": 2,
        "complete": False,
        "available_only_means": dict(zip(METRICS, values.mean(axis=0))),
        "metrics": None,
        "CI95": None,
        "per_case": cases,
    }
    return {
        "schema": "magicbrush.report.v1",
        "scope": "full",
        "rows": [row],
        "statistics_code_sha256": sha256_file(Path(original.__file__)),
        "bootstrap": {
            "seed": original.BOOTSTRAP_SEED,
            "draws": original.BOOTSTRAP_DRAWS,
            "subsets": {
                "full": {
                    "sessions": ["a", "b"],
                    "indices_sha256": hashlib.sha256(draws.tobytes()).hexdigest(),
                }
            },
        },
        "overlap": {
            "excluded_sessions": 0,
            "clean_sessions": 2,
            "clean_turns": 3,
            "limits": "Synthetic unit-test population, never experiment data.",
        },
        "run_digest": "unit-test-only",
    }


def test_failed_request_enters_full_denominator_and_session_bootstrap():
    source = fixture_report()
    before = deepcopy(source)
    result = build_report(source)
    row = result["rows"][0]
    assert source == before
    assert row["complete"] and row["included_count"] == 3
    assert row["measured_count"] == 2 and row["generation_failed_count"] == 1
    assert row["metrics"]["L1"] == pytest.approx((0.2 + 0.4 + 1) / 3)
    assert row["metrics"]["L2"] == pytest.approx((0.1 + 0.2 + 1) / 3)
    assert row["metrics"]["CLIP-I"] == pytest.approx((0.8 + 0.6 - 1) / 3)
    assert row["CI95"]["L1"] == pytest.approx([0.3, 1.0])
    assert row["CI95"]["DINO"] == pytest.approx([-1.0, 0.7])
    assert result["bootstrap"] == source["bootstrap"]
    assert "metrics" not in row["per_case"][-1]
    assert row["per_case"][-1]["assigned_penalty"] == PENALTIES


@pytest.mark.parametrize("status", ["completed", "missing"])
def test_pending_generation_or_scoring_never_becomes_a_generation_failure(status):
    row = build_report(fixture_report(status))["rows"][0]
    assert not row["complete"] and row["unresolved_count"] == 1
    assert row["generation_failed_count"] == 0
    assert row["metrics"] is None and row["CI95"] is None


def test_all_failed_row_and_clean_subset_use_the_same_policy():
    source = fixture_report()
    for row in source["rows"]:
        for case in row["per_case"]:
            case.pop("metrics", None)
            case["status"] = "failed"
        row.update(scored_count=0, available_only_means=None)
    source["bootstrap"]["subsets"]["no_known_corpus_overlap"] = deepcopy(
        source["bootstrap"]["subsets"]["full"]
    )
    clean = deepcopy(source["rows"][0])
    clean["subset"] = "no_known_corpus_overlap"
    source["rows"].append(clean)
    for row in build_report(source)["rows"]:
        assert row["metrics"] == PENALTIES
        assert row["generation_failed_count"] == 3
        assert row["CI95"] == {k: [v, v] for k, v in PENALTIES.items()}


def test_completed_original_row_is_verified_and_unchanged():
    source = fixture_report()
    row = source["rows"][0]
    row["per_case"][-1].update(status="scored", metrics={k: 0.5 for k in METRICS})
    sums = np.array([[0.6, 0.3, 1.4, 1.4, 1.4], [0.5] * 5])
    counts = np.array([2, 1])
    indices = np.random.default_rng(original.BOOTSTRAP_SEED).integers(
        0, 2, size=(original.BOOTSTRAP_DRAWS, 2), dtype=np.int32
    )
    means = dict(zip(METRICS, sums.sum(axis=0) / 3))
    ci = dict(
        zip(
            METRICS,
            np.percentile(
                original.bootstrap(sums, counts, indices), [2.5, 97.5], axis=0
            ).T.tolist(),
        )
    )
    row.update(scored_count=3, complete=True, metrics=means, available_only_means=means, CI95=ci)
    result = build_report(source)["rows"][0]
    assert result["generation_failed_count"] == 0
    for metric in METRICS:
        assert result["metrics"][metric] == pytest.approx(row["metrics"][metric], abs=1e-12)
        assert result["CI95"][metric] == pytest.approx(row["CI95"][metric], abs=1e-12)


@pytest.mark.parametrize("corruption", ["bootstrap", "mean", "duplicate", "population"])
def test_inconsistent_source_report_is_rejected(corruption):
    source = fixture_report()
    if corruption == "bootstrap":
        source["bootstrap"]["subsets"]["full"]["indices_sha256"] = "wrong"
    elif corruption == "mean":
        source["rows"][0]["available_only_means"]["L1"] = 0.99
    elif corruption == "duplicate":
        source["rows"].append(deepcopy(source["rows"][0]))
    else:
        other = deepcopy(source["rows"][0])
        other["model"] = "sitedit"
        other["per_case"][-1]["key"] = "mask-free/independent/b-2"
        source["rows"].append(other)
    with pytest.raises(ValueError):
        build_report(source)


def test_publish_preserves_original_bytes_and_refuses_overwrite(tmp_path):
    source = tmp_path / "original" / "REPORT.json"
    source.parent.mkdir()
    source.write_text(json.dumps(fixture_report()))
    before = source.read_bytes()
    dest = tmp_path / "failure-inclusive"
    publish(source, dest)
    assert source.read_bytes() == before
    assert "失败惩罚" in (dest / "REPORT.md").read_text()
    with pytest.raises(ValueError):
        publish(source, dest)
    with pytest.raises(ValueError):
        publish(source, source.parent / "nested")
