"""CPU release contracts, separate from the real-checkpoint numerical audit."""

import importlib.util
from pathlib import Path
import json

from samtok_benchmark.inference_cost.common import digest


def publisher():
    path = Path(__file__).resolve().parents[1] / "scripts/publish_inference_cost_unified.py"
    spec = importlib.util.spec_from_file_location("unified_publisher", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plan_preserves_every_public_byte_and_method_parameter(tmp_path):
    parent = {
        "digest": "original",
        "method": {"steps": 40, "token_guidance": 2, "seed": 42},
        "baseline_config": {
            "model_specifications": {
                "qwen21": {"execution": {"memory_policy": "model_cpu_offload"}}
            }
        },
        "models": ["qwen21", "replan", "mirage", "mice", "sitedit"],
        "requests": [{"case_id": "case", "public": "/nas/public.json"}],
        "assets": {"/nas/public.json": "original-sha"},
        "tasks": [{"request_path": "/nas/request.json"}],
        "repetitions": 3,
        "settings": ["S1", "S3-mask"],
    }
    before = json.dumps(parent, sort_keys=True)
    plan = publisher().make_plan(parent, tmp_path, "commit")
    assert json.dumps(parent, sort_keys=True) == before
    for key in ("method", "requests", "assets", "tasks", "repetitions", "settings"):
        assert plan[key] == parent[key]
    assert set(plan["models"]) == set(parent["models"])
    assert plan["models"][0] == "sitedit"
    assert (
        plan["baseline_config"]["model_specifications"]["qwen21"]["execution"]["memory_policy"]
        == "resident"
    )
    assert plan["unified_execution"]["quality_result_reuse"] is False
    assert plan["digest"] == digest({k: v for k, v in plan.items() if k != "digest"})
    assert plan["digest"] != parent["digest"]


def test_report_requires_quality_review_even_when_measurements_complete(tmp_path):
    from samtok_benchmark.inference_cost import common
    from samtok_benchmark.inference_cost.report import report

    plan = {
        "models": ["qwen21"],
        "settings": ["S1"],
        "repetitions": 3,
        "requests": [{"case_id": "c", "setting": "S1", "units": 2}],
        "timing_definition": "test",
        "memory_definition": "test",
        "unified_execution": {"backend": "diffusers", "quality_result_reuse": False},
    }
    plan["digest"] = digest(plan)
    path = tmp_path / "plan.json"
    common.save(path, plan)
    for rep in range(3):
        common.save(
            common.result_dir(tmp_path, "qwen21", "S1", "edit", "c", rep) / "result.json",
            {
                "identity": common.identity(plan, "qwen21", "S1", "edit", "c", rep),
                "status": "completed",
                "native_seconds": 2.0,
                "peak_allocated_bytes": 1,
                "peak_reserved_bytes": 1,
                "calls": {"transformer_forward_calls": 40},
                "raw_rgb_sha256": "synthetic",
                "native": {},
            },
        )
    result = report(path, tmp_path)
    assert result["complete"] is True
    assert result["quality_review_required"] is True
    assert result["quality_result_reuse"] is False
    assert result["end_to_end_measured"] is False
