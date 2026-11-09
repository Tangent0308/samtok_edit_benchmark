"""Protect native weighting, paired cluster uncertainty and fixed test-family correction."""

import numpy as np
import pytest

from samtok_benchmark.external_pair.statistics import aggregate, analyze, endpoints, holm
from samtok_benchmark.external_full.simple_report import aggregate as native_aggregate
from samtok_benchmark.external_full.metrics import LABELS, WEIGHTS


def test_native_macro_and_area_weights():
    values = np.array([1.0, 3.0, 9.0])
    weights = np.array([1.0, 3.0, 2.0])
    groups = np.array(["a", "a", "b"])
    assert aggregate(values, weights, groups) == pytest.approx((2.5 + 9) / 2)
    counts = np.array([[1, 1, 1], [2, 2, 1]])
    assert aggregate(values, weights, groups, counts) == pytest.approx([5.75, 5.75])
    assert aggregate(values, weights, np.array(["all"] * 3)) == pytest.approx(28 / 6)


def test_holm_keeps_unavailable_family_members():
    assert holm([0.01, 0.04, None, 0.03]) == pytest.approx([0.04, 0.09, 1, 0.09])


def test_main_family_is_fixed_before_outcomes():
    rows = [{"task": "add", "turn": 0, "language": "en"}]
    assert (
        sum(
            ep.main
            for bench in ("compbench", "interedit", "omni_iie")
            for ep in endpoints(bench, rows)
        )
        == 53
    )


def test_paired_source_bootstrap_preserves_low_high_and_weights():
    selected, per_case = [], []
    for i in range(12):
        for level in ("low", "high"):
            cid = f"{i}-{level}"
            selected.append({"case_id": cid, "cluster": str(i), "task": level, "turn": 0})
            for model in ("sitedit", "qwen21"):
                v = 0.1 + i * 0.01 + (0.2 if model == "qwen21" else 0)
                metrics = {k: v for k in LABELS["omni_iie"]}
                metrics.update(_FG_Weight=(i + 1) / 13, _BG_Weight=(12 - i) / 13)
                per_case.append(
                    {
                        "case_id": cid,
                        "task": level,
                        "model": model,
                        "status": "completed",
                        "metrics": metrics,
                    }
                )
    report = {
        "case_ids": [r["case_id"] for r in selected],
        "models": ["sitedit", "qwen21"],
        "per_case": per_case,
        "rows": {},
    }
    for model in report["models"]:
        rs = [r for r in per_case if r["model"] == model]
        report["rows"][model] = {
            group: native_aggregate(
                [r for r in rs if group == "all" or r["task"] == group[5:]],
                LABELS["omni_iie"],
                WEIGHTS,
            )
            for group in ["all", "task/low", "task/high"]
        }
    a = analyze(
        "omni_iie", {"case_ids": report["case_ids"], "rows": selected}, report, repetitions=500
    )
    b = analyze(
        "omni_iie", {"case_ids": report["case_ids"], "rows": selected}, report, repetitions=500
    )
    assert a == b
    assert a["sampling"]["source_clusters"] == 12
    for row in a["rows"]:
        sign = 1 if row["direction"] == "lower" else -1
        assert row["benefit_delta"] == pytest.approx(sign * 0.2)
        assert row["benefit_CI95"] == pytest.approx([sign * 0.2] * 2)
        assert row["paired_source_clusters"] == 12
