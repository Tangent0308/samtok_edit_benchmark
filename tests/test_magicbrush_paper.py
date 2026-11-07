"""Keep the paper checkpoint and its statistics distinct from previous baselines."""

import copy

import numpy as np
import pytest

from samtok_benchmark.external_magicbrush_paper import MODELS
from samtok_benchmark.external_magicbrush_paper import common, report


def test_paper_configuration_preserves_native_defaults_and_metric_policy(monkeypatch):
    original = {
        "models": {
            "instructpix2pix": {
                "steps": 100,
                "resolution": 512,
                "seed": 42,
                "text_cfg": 7.5,
                "image_cfg": 1.5,
                "checkpoint": {"sha256": "original"},
            }
        },
        "metrics": {"binding": "unchanged"},
        "runtime": {"native": "native", "scoring": "scoring"},
    }
    before = copy.deepcopy(original)
    monkeypatch.setattr(common, "classic_config", lambda: original)
    monkeypatch.setattr(
        common,
        "read",
        lambda _: {
            "checkpoint": {
                "sha256": "5fe508a8a3c39ff1d267bcb0d1dcfe6dde41716f7530f46a23dc68ebaaaf46df"
            }
        },
    )
    monkeypatch.setattr(common, "sha256_file", lambda _: "manifest")
    config = common.config()
    assert original == before
    assert tuple(config["models"]) == MODELS
    assert config["metrics"] == before["metrics"]
    spec = config["models"][MODELS[0]]
    for key in ("steps", "resolution", "seed", "text_cfg", "image_cfg"):
        assert spec[key] == before["models"]["instructpix2pix"][key]
    assert spec["magicbrush_finetuned"]


def test_later_checkpoint_cannot_be_substituted(monkeypatch):
    monkeypatch.setattr(common, "classic_config", lambda: {})
    monkeypatch.setattr(common, "read", lambda _: {"checkpoint": {"sha256": "different"}})
    with pytest.raises(ValueError, match="Wrong MagicBrush checkpoint"):
        common.config()


def test_primary_projection_and_failure_penalties_preserve_full_denominator():
    source = {"status": "scored", "metrics": dict.fromkeys(report.METRICS, 0.2)}
    source["metrics"]["GT-CLIP-T"] = 0.7
    before = copy.deepcopy(source)
    selected = [
        ({"session_id": "a", "key": "a"}, {"status": "completed"}, report.primary_score(source)),
        ({"session_id": "b", "key": "b"}, {"status": "failed"}, None),
    ]
    row = report.summarise(
        MODELS[0],
        "single-turn",
        selected,
        ["a", "b"],
        np.array([[0, 1], [0, 0], [1, 1]], dtype=np.int32),
    )
    assert source == before
    assert row["target_count"] == 2 and row["generation_failed_count"] == 1
    assert row["metrics"]["L1"] == pytest.approx(0.6)
    assert row["metrics"]["CLIP-I"] == pytest.approx(-0.4)


@pytest.mark.parametrize(
    "metrics", [{"L1": 0.1}, {**dict.fromkeys(report.METRICS, 0.1), "unknown": 1}]
)
def test_bad_metric_schema_cannot_be_merged(metrics):
    with pytest.raises(ValueError, match="schema"):
        report.primary_score({"status": "scored", "metrics": metrics})
