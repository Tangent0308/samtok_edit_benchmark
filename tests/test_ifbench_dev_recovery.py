"""Placement repair must not permit quality search, scope drift or orphan retry."""

from copy import deepcopy

import pytest

from samtok_benchmark.io import digest, sha256_file, write_json
from samtok_benchmark.ifbench import fairness_dev_recovery as recovery


def specifications():
    old = {"model_specifications": {"qwen21": {
        "parameters": {"num_inference_steps": 40, "output_resolution": 2048,
                       "true_cfg_scale": 1.0, "use_kv_cache": True},
        "weight_revision": "pinned", "pipeline_revision": "native", "seed": 42,
    }}}
    new = deepcopy(old)
    new["model_specifications"]["qwen21"]["execution"] = {"memory_policy": "model_cpu_offload"}
    return old, new


def test_exact_native_placement_change_is_allowed():
    old, new = specifications()
    recovery.verify_placement_equivalence(old, new, "qwen21")
    old["model_specifications"]["qwen21"]["execution"] = {"memory_policy": "resident"}
    recovery.verify_placement_equivalence(old, new, "qwen21")


@pytest.mark.parametrize("field,value", [
    ("output_resolution", 1024), ("num_inference_steps", 4),
    ("true_cfg_scale", 4), ("use_kv_cache", False),
])
def test_sampling_changes_cannot_hide_behind_placement_equivalence(field, value):
    old, new = specifications()
    new["model_specifications"]["qwen21"]["parameters"][field] = value
    with pytest.raises(ValueError, match="weights/native configuration differ"):
        recovery.verify_placement_equivalence(old, new, "qwen21")


def test_weights_execution_and_nonqwen_changes_are_rejected():
    old, new = specifications()
    new["model_specifications"]["qwen21"]["weight_revision"] = "other"
    with pytest.raises(ValueError):
        recovery.verify_placement_equivalence(old, new, "qwen21")
    old, new = specifications()
    new["model_specifications"]["qwen21"]["execution"]["vae_tiling"] = True
    with pytest.raises(ValueError, match="Additional execution changes"):
        recovery.verify_placement_equivalence(old, new, "qwen21")
    old["model_specifications"]["mice"] = {"steps": 28}
    new["model_specifications"]["mice"] = {"steps": 4}
    with pytest.raises(ValueError):
        recovery.verify_placement_equivalence(old, new, "mice")


def terminal_oom():
    parameters = specifications()[0]["model_specifications"]["qwen21"]["parameters"]
    return {"status": "failed", "error_type": "OutOfMemoryError",
            "traceback": "image = self.vae.decode(latents)",
            "transformer_forward_calls": 40, "parameters": parameters}, parameters


@pytest.mark.parametrize("change", [
    {"status": "started"}, {"status": "generated", "output_sha256": "image"},
    {"error_type": "JSONDecodeError"}, {"traceback": "encoder()"},
    {"transformer_forward_calls": 20}, {"output_image": "diagnostic.png"},
])
def test_only_known_terminal_decode_oom_can_be_repaired(change):
    result, parameters = terminal_oom()
    recovery.check_decode_oom(result, parameters)
    result.update(change)
    with pytest.raises(ValueError, match="terminal full-denoise"):
        recovery.check_decode_oom(result, parameters)


def certificate(tmp_path, monkeypatch):
    bundle, root = tmp_path / "old", tmp_path / "recovered"
    parent = {"tasks": [], "judge_config": {"rubric": "fixed"},
              "model_order": ["qwen21"], "cache_index_sha256": "original-index"}
    def save(path, value):
        write_json(path, value)
        return {"path": str(path), "sha256": sha256_file(path)}
    refs = {"kind": "generation-terminal-and-judge-recovered"}
    refs["plan"] = save(bundle / "plan.json", parent)
    refs["code_manifest"] = save(bundle / "code_manifest.json", {"files": {}})
    refs["recovery_started"] = save(root / "RECOVERY_STARTED.json", {"config": {
        "original_plan": refs["plan"]["path"], "original_plan_sha256": refs["plan"]["sha256"],
        "original_code_manifest_sha256": refs["code_manifest"]["sha256"],
        "original_index_sha256": "original-index", "recovery_root": str(root),
    }})
    refs["recovery_completed"] = save(root / "RECOVERY_COMPLETED.json", {
        "status": "completed-awaiting-dev-review", "ready_for_review": True,
        "new_editor_calls": 0, "diagnostic_outputs_included": False,
        "original_scores_unchanged": True, "test_started": False, "frozen": False,
    })
    refs["judge_binding"] = save(root / "judge/plan_binding.json", {
        "plan_sha256": refs["plan"]["sha256"], "run_id": digest(parent["judge_config"]),
        "model_order": ["qwen21"],
    })
    monkeypatch.setattr(recovery, "load_plan", lambda *_, **__: parent)
    return {"repair_parent": refs}, root


def test_separate_recovery_is_pinned_without_inventing_parent_completion(tmp_path, monkeypatch):
    plan, _ = certificate(tmp_path, monkeypatch)
    recovery.recovered_parent(plan)
    assert not (tmp_path / "old/results/COMPLETED.json").exists()


def test_changed_or_diagnostic_recovery_is_rejected(tmp_path, monkeypatch):
    plan, root = certificate(tmp_path, monkeypatch)
    path = root / "RECOVERY_COMPLETED.json"
    completion = recovery.read(path)
    completion["diagnostic_outputs_included"] = True
    write_json(path, completion)
    with pytest.raises(ValueError, match="Artifact changed"):
        recovery.recovered_parent(plan)
    plan["repair_parent"]["recovery_completed"]["sha256"] = sha256_file(path)
    with pytest.raises(ValueError, match="approved scope"):
        recovery.recovered_parent(plan)
