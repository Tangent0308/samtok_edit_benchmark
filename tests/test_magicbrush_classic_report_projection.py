"""An auxiliary scorer diagnostic must not invalidate complete primary scores."""

import copy
import importlib.util
from pathlib import Path

import numpy as np
import pytest

path = Path(__file__).parents[1] / "scripts/report_magicbrush_classic_results.py"
spec = importlib.util.spec_from_file_location("classic_report_adapter", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_auxiliary_metric_is_preserved_in_source_and_excluded_from_primary_statistics():
    source = {
        "status": "scored",
        "identity": {"key": "immutable"},
        "metrics": {
            "L1": 0.1,
            "L2": 0.02,
            "CLIP-I": 0.9,
            "DINO": 0.8,
            "CLIP-T": 0.3,
            "GT-CLIP-T": 0.4,
        },
    }
    before = copy.deepcopy(source)
    selected = module.primary_score(source)
    row = module.summarise(
        "hive",
        "single-turn",
        [
            (
                {"key": "mask-free/independent/30-1", "session_id": "30"},
                {"status": "completed"},
                selected,
            )
        ],
        ["30"],
        np.zeros((10, 1), dtype=np.int32),
    )
    assert source == before
    assert selected["identity"] == source["identity"]
    assert row["metrics"] == {k: before["metrics"][k] for k in module.METRICS}
    assert "GT-CLIP-T" not in row["per_case"][0]["metrics"]
    assert row["complete"] and row["target_count"] == 1


@pytest.mark.parametrize(
    "metrics", [{"L1": 0.1}, {**dict.fromkeys(module.METRICS, 0.1), "unexpected": 1.0}]
)
def test_missing_or_unknown_metrics_are_rejected(metrics):
    with pytest.raises(ValueError, match="schema"):
        module.primary_score({"status": "scored", "metrics": metrics})


def test_score_failure_is_not_converted_to_a_measurement():
    source = {"status": "failed", "error": "scoring exception"}
    assert module.primary_score(source) is source
