"""Publication must restrict the roster without altering scientific inputs or settings."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "publisher", ROOT / "scripts/external_full_publish.py"
)
PUBLISHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUBLISHER)
FIVE = ["sitedit", "qwen21", "replan", "mice", "flux2_klein9b"]


def fixture():
    config = json.loads((ROOT / "configs/external/compbench_full4.json").read_text())
    index = {
        "cases": [{"task": "action"}] * 89
        + [{"task": "location"}] * 73
        + [{"task": "view"}] * 34
        + [{"task": "add"}] * 3285
    }
    return config, index


def test_five_methods_keep_scientific_config_and_limit_paid_calls():
    cfg, index = fixture()
    original = copy.deepcopy(cfg)
    root = PUBLISHER.NAS / "experiments2/SAMTokEdit/external_compbench/full5_20261109"
    updated, selected = PUBLISHER.deployment_config(cfg, "compbench", index, FIVE, root)
    assert selected == FIVE
    assert cfg == original
    for key in ("seed", "sitedit", "model_specifications", "benchmark", "paths", "runtime"):
        assert updated[key] == original[key]
    assert updated["formal_results_root"] == str(root)
    assert updated["scoring"]["vlm_config"]["max_formal_requests"] == 980
    updated["scoring"]["vlm_config"]["max_formal_requests"] = 1568
    assert updated["scoring"] == original["scoring"]


def test_default_keeps_legacy_eight_method_configuration():
    cfg, index = fixture()
    updated, selected = PUBLISHER.deployment_config(cfg, "compbench", index)
    assert selected == PUBLISHER.MODELS
    assert updated == cfg


@pytest.mark.parametrize("models", [[], ["sitedit", "sitedit"], ["unknown"]])
def test_invalid_rosters_rejected(models):
    cfg, index = fixture()
    with pytest.raises(ValueError, match="distinct supported"):
        PUBLISHER.deployment_config(cfg, "compbench", index, models)


def test_wrong_result_root_and_excess_budget_rejected():
    cfg, index = fixture()
    with pytest.raises(ValueError, match="benchmark-specific"):
        PUBLISHER.deployment_config(cfg, "compbench", index, FIVE, "/tmp/unapproved")
    cfg["scoring"]["vlm_config"]["max_formal_requests"] = 979
    with pytest.raises(ValueError, match="authorized VLM"):
        PUBLISHER.deployment_config(cfg, "compbench", index, FIVE)
