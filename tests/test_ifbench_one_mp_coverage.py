"""The bounded completion probe cannot silently expand or resample coverage."""

from copy import deepcopy
from pathlib import Path

import pytest

from samtok_benchmark.io import digest, sha256_file, write_json
from samtok_benchmark.paths import repository_root
from samtok_benchmark.ifbench import canvas, one_mp_coverage as coverage
from samtok_benchmark.ifbench.fairness_dev_plan import MODELS, SETTINGS, read
from samtok_benchmark.ifbench.prepare_one_mp import PROBE_SETTINGS


def fixture(tmp_path):
    repo = repository_root()
    config_path = repo / "configs/evaluation/fairness_v2_2_1mp.json"
    config = read(config_path)
    manifest = repo / "data/v2_2.6.0/cases.jsonl"
    cid = "v2-sa_8415518"
    origin = tmp_path / "origin/plan.json"
    write_json(origin, {"settings": PROBE_SETTINGS})
    write_json(origin.with_name("code_manifest.json"), {"files": {}})
    authorization = tmp_path / "AUTHORIZATION.json"
    write_json(
        authorization,
        {
            "schema": coverage.SCHEMA,
            "coverage_and_judge_authorized": True,
            "case_id": cid,
            "settings": coverage.COVERAGE_SETTINGS,
            "models": MODELS,
            "seed": 42,
            "quality_search": False,
            "one_sample_per_request": True,
        },
    )
    root = tmp_path / "results"
    tasks = []
    for model in MODELS:
        for setting in coverage.COVERAGE_SETTINGS:
            out = root / "runs" / model / "outputs" / setting / cid
            tasks.append(
                {
                    "model": model,
                    "setting": setting,
                    "case_id": cid,
                    "output_dir": str(out),
                    "result_path": str(out / "result.json"),
                    "cache": {},
                }
            )
    return {
        "schema": coverage.SCHEMA,
        "canvas_policy": canvas.POLICY,
        "seed": 42,
        "quality_search": False,
        "configuration_reference": str(config_path),
        "configuration_reference_sha256": sha256_file(config_path),
        "model_specifications": config["model_specifications"],
        "judge_config": config["judge_config"],
        "case_manifest": str(manifest),
        "case_manifest_sha256": sha256_file(manifest),
        "case_ids": [cid],
        "settings": coverage.COVERAGE_SETTINGS,
        "model_order": MODELS,
        "authorization_path": str(authorization),
        "authorization_sha256": sha256_file(authorization),
        "probe_origin": {
            "path": str(origin),
            "sha256": sha256_file(origin),
            "code_manifest_sha256": sha256_file(origin.with_name("code_manifest.json")),
        },
        "tasks": tasks,
        "results_root": str(root),
        "helper_sha256": {},
    }


def sealed(tmp_path, plan):
    plan = deepcopy(plan)
    plan["digest"] = digest(plan)
    path = tmp_path / "plan.json"
    write_json(path, plan)
    return path


def test_exact_disjoint_coverage(tmp_path):
    plan = coverage.load_plan(sealed(tmp_path, fixture(tmp_path)))
    assert len(plan["tasks"]) == 49
    assert not set(plan["settings"]) & set(PROBE_SETTINGS)
    assert set(plan["settings"]) | set(PROBE_SETTINGS) == set(SETTINGS)


@pytest.mark.parametrize("mutation", ["repeat", "other-source", "cache", "output-path", "config"])
def test_coverage_rejects_scope_and_identity_changes(tmp_path, mutation):
    plan = fixture(tmp_path)
    if mutation == "repeat":
        plan["tasks"][-1] = plan["tasks"][0]
    elif mutation == "other-source":
        plan["case_ids"] = ["v2-sa_607902"]
    elif mutation == "cache":
        plan["tasks"][0]["cache"] = {"edit": "not-an-unsampled-request"}
    elif mutation == "output-path":
        plan["tasks"][0]["output_dir"] = str(Path(plan["results_root"]).parent)
    else:
        plan["judge_config"] = {"changed": True}
    with pytest.raises(ValueError):
        coverage.load_plan(sealed(tmp_path, plan))
