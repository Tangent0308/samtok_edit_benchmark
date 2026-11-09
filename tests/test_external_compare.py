"""Comparison expansion must preserve the cohort, configurations and reuse boundary."""

from copy import deepcopy
import json

import pytest

from samtok_benchmark.external_compare import ADDITIONAL, REUSED
from samtok_benchmark.external_compare.plan import extend_selection, verify_selection
from samtok_benchmark.io import digest, sha256_file


def fixture(tmp_path, bench):
    cfg = tmp_path / "configuration.json"
    cfg.write_text('{"seed":42}')
    source = tmp_path / "SELECTION.json"
    selection = {
        "benchmark": bench,
        "models": list(REUSED),
        "case_ids": ["a", "b"],
        "generation_case_ids": ["a", "b"],
        "rows": [{"case_id": "a", "cluster": "same"}, {"case_id": "b", "cluster": "same"}],
        "results_root": str(tmp_path / "old"),
        "configuration": str(cfg),
        "configuration_sha256": sha256_file(cfg),
        "bundle": "original-public-bundle",
        "analysis": {"seed": 20261109},
    }
    selection["digest"] = digest(selection)
    source.write_text(json.dumps(selection))
    return source, selection


@pytest.mark.parametrize("bench", tuple(ADDITIONAL))
def test_expansion_keeps_frozen_population(tmp_path, bench):
    source, original = fixture(tmp_path, bench)
    before = source.read_bytes()
    expanded = extend_selection(original, source, tmp_path / "new")
    verify_selection(expanded)
    assert source.read_bytes() == before
    assert expanded["case_ids"] == original["case_ids"]
    assert expanded["rows"] == original["rows"]
    assert expanded["configuration"] == original["configuration"]
    assert set(expanded["generation_models"]).isdisjoint(REUSED)
    assert ("replan" in expanded["models"]) == (bench == "compbench")


@pytest.mark.parametrize(
    "field,value",
    [
        ("case_ids", ["a"]),
        ("generation_models", ["mice"]),
        ("bundle", "other"),
        ("rows", [{"case_id": "a", "cluster": "other"}]),
    ],
)
def test_reject_changed_cohort_or_models(tmp_path, field, value):
    source, original = fixture(tmp_path, "compbench")
    expanded = deepcopy(extend_selection(original, source, tmp_path / "new"))
    expanded[field] = value
    expanded["digest"] = digest({k: v for k, v in expanded.items() if k != "digest"})
    with pytest.raises(ValueError, match="only add"):
        verify_selection(expanded)


def test_reject_configuration_edit(tmp_path):
    source, original = fixture(tmp_path, "interedit")
    expanded = extend_selection(original, source, tmp_path / "new")
    source.with_name("configuration.json").write_text('{"seed":43}')
    with pytest.raises(ValueError, match="configuration changed"):
        verify_selection(expanded)
