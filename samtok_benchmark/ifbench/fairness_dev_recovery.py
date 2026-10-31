"""Audited reuse after a terminal generation run and separate Judge recovery.

This is deliberately narrower than a general retry mechanism: only identified
Qwen2.1 decode OOMs may be rerun, with native component placement as the sole
configuration change. A completed Judge recovery is not a fabricated completion
of the original controller.
"""

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

from samtok_benchmark.io import digest
from .fairness_dev_plan import check_hash, load_plan, read, verify_task


@lru_cache(maxsize=4)
def _recovered_parent(serialized):
    references = json.loads(serialized)
    if references["kind"] != "generation-terminal-and-judge-recovered":
        raise ValueError("Unknown recovery parent contract")
    for name in ("plan", "code_manifest", "recovery_started", "recovery_completed", "judge_binding"):
        ref = references[name]
        check_hash(ref["path"], ref["sha256"])
    path = Path(references["plan"]["path"])
    manifest_path = Path(references["code_manifest"]["path"])
    if manifest_path != path.parent / "code_manifest.json":
        raise ValueError("Recovery parent manifest is not beside the original plan")
    for relative, expected in read(manifest_path)["files"].items():
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("Unsafe recovery parent code path")
        check_hash(path.parent / "repo" / relative, expected)
    parent = load_plan(path, helper_root=path.parent / "repo")
    started = read(references["recovery_started"]["path"])
    completed = read(references["recovery_completed"]["path"])
    bound = read(references["judge_binding"]["path"])
    config = started["config"]
    if (
        config["original_plan"] != str(path)
        or config["original_plan_sha256"] != references["plan"]["sha256"]
        or config["original_code_manifest_sha256"] != references["code_manifest"]["sha256"]
        or config["original_index_sha256"] != parent["cache_index_sha256"]
        or bound["plan_sha256"] != references["plan"]["sha256"]
        or bound["run_id"] != digest(parent["judge_config"])
        or bound["model_order"] != parent["model_order"]
    ):
        raise ValueError("Judge recovery is not bound to the original plan/code/rubric")
    recovery_root = Path(config["recovery_root"])
    for name, relative in (
        ("recovery_started", "RECOVERY_STARTED.json"),
        ("recovery_completed", "RECOVERY_COMPLETED.json"),
        ("judge_binding", "judge/plan_binding.json"),
    ):
        if Path(references[name]["path"]) != recovery_root / relative:
            raise ValueError("Judge recovery references mix different result roots")
    if (
        completed.get("status") != "completed-awaiting-dev-review"
        or completed.get("ready_for_review") is not True
        or completed.get("new_editor_calls") != 0
        or completed.get("diagnostic_outputs_included") is not False
        or completed.get("original_scores_unchanged") is not True
        or completed.get("test_started") is not False
        or completed.get("frozen") is not False
    ):
        raise ValueError("Separate Judge recovery did not complete in the approved scope")
    return parent, {task["key"]: task for task in parent["tasks"]}


def recovered_parent(plan):
    return _recovered_parent(json.dumps(plan["repair_parent"], sort_keys=True))


def verify_placement_equivalence(parent, plan, model):
    """Accept only the explicitly authorized resident -> native offload move."""
    old = deepcopy(parent["model_specifications"][model])
    new = deepcopy(plan["model_specifications"][model])
    if model == "qwen21":
        old_execution = old.pop("execution", {})
        new_execution = new.pop("execution", {})
        if old_execution.pop("memory_policy", "resident") != "resident":
            raise ValueError("Recovery requires the original resident Qwen placement")
        if new_execution.pop("memory_policy", None) != "model_cpu_offload":
            raise ValueError("Recovery requires native model_cpu_offload")
        if old_execution != new_execution:
            raise ValueError("Additional execution changes are not placement equivalence")
    if old != new:
        raise ValueError("Recovered model weights/native configuration differ")


def check_decode_oom(result, parameters):
    if (
        result.get("status") != "failed"
        or result.get("error_type") != "OutOfMemoryError"
        or "self.vae.decode(" not in result.get("traceback", "")
        or result.get("transformer_forward_calls") != parameters["num_inference_steps"]
        or result.get("parameters") != parameters
        or result.get("output_image")
        or result.get("output_sha256")
    ):
        raise ValueError("Repair target must be a terminal full-denoise Qwen decode OOM")


def verify_repair_target(plan, task, request, public):
    from .fairness_dev_worker import binding, verify_existing

    if task["model"] != "qwen21" or task.get("cache"):
        raise ValueError("Only uncached Qwen requests may receive the authorized repair")
    parent, tasks = recovered_parent(plan)
    previous = tasks[task["key"]]
    verify_placement_equivalence(parent, plan, "qwen21")
    old_request, old_public = verify_task(parent, previous)
    if request != old_request or public != old_public:
        raise ValueError("Repair changed public request/input")
    reference = task["repair_of"]
    if reference["path"] != previous["result_path"]:
        raise ValueError("Repair does not refer to the registered original attempt")
    check_hash(reference["path"], reference["sha256"])
    result = read(reference["path"])
    verify_existing(result, binding(parent, previous, "edit"))
    check_decode_oom(result, request["parameters"])
    return result
