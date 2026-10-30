"""Exact reuse of completed fixed dev runs, including terminal native failures."""

from functools import lru_cache
from pathlib import Path

from PIL import Image

from samtok_benchmark.io import digest
from .fairness_dev_plan import read, check_hash, request_identity, verify_task


@lru_cache(maxsize=4)
def _parent(path, plan_sha, completion_sha, manifest_sha):
    """Validate the immutable parent once per worker; task artifacts are rehashed."""
    path = Path(path)
    root = path.parent
    check_hash(path, plan_sha)
    check_hash(root / "results/COMPLETED.json", completion_sha)
    check_hash(root / "code_manifest.json", manifest_sha)
    plan = read(path)
    if plan["digest"] != digest({k: v for k, v in plan.items() if k != "digest"}):
        raise ValueError("Parent plan digest changed")
    completion = read(root / "results/COMPLETED.json")
    if (
        completion["plan_digest"] != plan["digest"]
        or completion["status"] != "completed-awaiting-freeze-review"
        or completion["code_manifest_sha256"] != manifest_sha
    ):
        raise ValueError("Parent dev run did not complete with the pinned code")
    for relative, expected in read(root / "code_manifest.json")["files"].items():
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("Unsafe parent code path")
        check_hash(root / "repo" / relative, expected)
    return plan, {t["key"]: t for t in plan["tasks"]}


def completed_parent(plan):
    p = plan["parent_run"]
    return _parent(p["plan"], p["plan_sha256"], p["completion_sha256"], p["code_manifest_sha256"])


def verify_completed_cache(plan, task, stage, receipt, request, public):
    from .fairness_dev_plan import verify_cache
    from .fairness_dev_worker import binding, verify_existing

    parent, tasks = completed_parent(plan)
    old_task = tasks[task["key"]]
    if receipt["parent_plan_digest"] != parent["digest"]:
        raise ValueError("Completed cache has a different parent plan")
    previous_request, previous_public = verify_task(parent, old_task)
    if previous_request != request or previous_public != public:
        raise ValueError("Completed native request/public input differs")
    model = task["model"]
    if parent["model_specifications"][model] != plan["model_specifications"][model]:
        raise ValueError("Completed model weights/native configuration differ")
    if old_task["scientific_digest"] != request_identity(parent, model, previous_request):
        raise ValueError("Parent scientific identity changed")
    result_path = (
        Path(old_task["planner_dir"]) / "result.json"
        if stage == "planner"
        else Path(old_task["result_path"])
    )
    if str(result_path) != receipt["original_result"]:
        raise ValueError("Completed cache result is not the registered parent result")
    check_hash(result_path, receipt["original_result_sha256"])
    result = read(result_path)
    verify_existing(result, binding(parent, old_task, stage))
    if old_task.get("cache", {}).get(stage):
        original = verify_cache(parent, old_task, stage)
        for field in ("status", "output_sha256", "response"):
            if original.get(field) != result.get(field):
                raise ValueError(f"Completed reuse differs from its original evidence: {field}")
    if result["status"] == "generated":
        check_hash(result["output_image"], result["output_sha256"])
        with Image.open(result["output_image"]) as image:
            if list(image.size) != public["source"]["size"]:
                raise ValueError("Completed output has a different source canvas")
    elif stage == "edit" and result["status"] not in {"failed", "failed-planner"}:
        raise ValueError("Completed editor cache is not terminal")
    if result.get("planner_record") and result.get("planner_result_sha256"):
        check_hash(result["planner_record"], result["planner_result_sha256"])
    if result.get("traces"):
        check_hash(result["traces"], result["traces_sha256"])
    value = {**result, "original_result": str(result_path), "parent_plan_digest": parent["digest"]}
    if receipt.get("original_call"):
        value["original_call"] = receipt["original_call"]
    # Old load costs remain reachable through original_result, but must not
    # appear as model loads of this new run.
    value.pop("load_record", None)
    return value
