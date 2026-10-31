"""Immutable contracts for the approved 20-image fairness dev evaluation.

This module performs CPU verification only. Public request paths retain their
audited names; a portable launcher supplies byte-checked filesystem aliases.
"""

from __future__ import annotations

import json
from pathlib import Path
import threading

from PIL import Image

from samtok_benchmark.io import digest, sha256_file
from .public import verify

SCHEMA = "ifbench-fairness-dev20-v1"
MODELS = ["qwen2511", "qwen21", "flux3", "replan", "mirage", "mice", "flux2_klein9b"]
SETTINGS = [
    "S1",
    "S2-point",
    "S2-box",
    "S2-mask",
    "S3-point",
    "S3-box",
    "S3-mask",
    "S4-ref",
    "S4-noref",
    "S5",
]
_PUBLIC_CACHE = set()
_CACHE_LOCK = threading.Lock()


def read(path):
    return json.loads(Path(path).read_text())


def check_hash(path, expected):
    """Read the bytes even when metadata is unchanged.

    Shared and coarse-timestamp filesystems can report identical size, mtime
    and ctime for two different same-length writes. Metadata is not an
    integrity guarantee for a resumed evaluation.
    """
    path = Path(path)
    if sha256_file(path) != expected:
        raise ValueError(f"Artifact changed: {path}")


def request_identity(plan, model, request):
    """Bind the complete prepared request and the audited scientific config."""
    return digest(
        {
            "request": request,
            "model": model,
            "configuration_sha256": plan["configuration_sha256"],
            "specification": plan["model_specifications"][model],
        }
    )


def load_plan(path, *, helper_root=None):
    """Verify active code by default; an explicit root verifies archived evidence."""
    plan = read(path)
    if plan.get("schema") != SCHEMA or plan.get("digest") != digest(
        {k: v for k, v in plan.items() if k != "digest"}
    ):
        raise ValueError("Invalid dev20 plan/digest")
    if plan["model_order"] != MODELS or plan["settings"] != SETTINGS or plan["seed"] != 42:
        raise ValueError("Changed approved models/settings/seed")
    if (
        len(set(plan["case_ids"])) != 20
        or plan.get("test_authorized")
        or plan.get("freeze_authorized")
    ):
        raise ValueError("Dev20 authorization scope violated")
    check_hash(plan["authorization_path"], plan["authorization_sha256"])
    auth = read(plan["authorization_path"])
    if not auth.get("dev20_and_judge_authorized") or auth.get("test_authorized"):
        raise ValueError("Missing dev20 authorization")
    check_hash(plan["selection_path"], plan["selection_sha256"])
    selection = read(plan["selection_path"])
    if selection["case_ids"] != plan["case_ids"]:
        raise ValueError("Selection differs from approved plan")
    split = read(Path(plan["paths"]["shared"]) / "plan/splits.json")
    if (
        split["digest"] != selection["parent_split_digest"]
        or not set(plan["case_ids"]) <= set(split["dev"])
        or set(plan["case_ids"]) & set(split["test"])
    ):
        raise ValueError("Dev20 must remain inside the original dev pool and outside test")
    expected = {(m, s, c) for m in MODELS for s in SETTINGS for c in plan["case_ids"]}
    actual = [(t["model"], t["setting"], t["case_id"]) for t in plan["tasks"]]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Incomplete or duplicated dev20 tasks")
    source_root = (
        Path(helper_root) if helper_root is not None else Path(__file__).resolve().parents[2]
    )
    for filename, expected_sha in plan["helper_sha256"].items():
        check_hash(source_root / filename, expected_sha)
    return plan


def verify_task(plan, task):
    check_hash(task["request_path"], task["request_sha256"])
    request = read(task["request_path"])
    public = read(task["public_request"])
    # Reuse expensive image decoding only after verifying the actual asset
    # bytes against the public request on every check, never from file stats.
    verify(public, assets=False)
    assets = [public["source"]] + [u["region"] for u in public["units"] if u["locator"] == "mask"]
    for asset in assets:
        check_hash(asset["path"], asset["sha256"])
    public_identity = digest(public)
    with _CACHE_LOCK:
        cached = public_identity in _PUBLIC_CACHE
    verify(public, assets=not cached)
    if not cached:
        with _CACHE_LOCK:
            _PUBLIC_CACHE.add(public_identity)
    if public["input_digest"] != task["public_digest"]:
        raise ValueError("Public input binding changed")
    if public["case_id"] != task["case_id"] or public["setting"] != task["setting"]:
        raise ValueError("Case/setting mismatch")
    if task["case_id"] not in plan["case_ids"] or request.get("seed") != 42:
        raise ValueError("Unregistered request")
    if (
        task["model"] == "qwen21"
        and request["parameters"] != plan["model_specifications"]["qwen21"]["parameters"]
    ):
        raise ValueError("Qwen21 request parameters differ from the fixed model specification")
    if request_identity(plan, task["model"], request) != task["scientific_digest"]:
        raise ValueError("Scientific request identity changed")
    for path, expected in task["input_files"].items():
        check_hash(path, expected)
    if task.get("repair_of"):
        from .fairness_dev_recovery import verify_repair_target

        verify_repair_target(plan, task, request, public)
    return request, public


def verify_cache(plan, task, stage):
    """Recheck old *actual* calls and raw records, not just receipt digests."""
    cache_path = task.get("cache", {}).get(stage)
    if cache_path is None:
        return None
    check_hash(cache_path, task["cache_sha256"][stage])
    receipt = read(cache_path)
    request, public = verify_task(plan, task)
    if receipt["scientific_digest"] != task["scientific_digest"] or receipt["stage"] != stage:
        raise ValueError("Cache belongs to another scientific request/stage")
    for item in receipt["evidence"]:
        check_hash(item["path"], item["sha256"])
    if receipt["kind"] in {"completed-dev20", "recovered-dev20"}:
        from .fairness_dev_cache import verify_completed_cache

        return verify_completed_cache(
            plan, task, stage, receipt, request, public,
            recovered=receipt["kind"] == "recovered-dev20",
        )
    old_call = read(receipt["original_call"])
    old_result = read(receipt["original_result"])
    kind = receipt["kind"]
    if kind in {"old-qwen-dual", "old-flux3-s1"}:
        fields = ["images", "prompt", "parameters", "seed"]
        if kind == "old-flux3-s1":
            fields += ["boxes"]
            if task["setting"] != "S1":
                raise ValueError("Old FLUX3 reuse is only exact S1")
        for field in fields:
            if old_call[field] != request[field]:
                raise ValueError(f"Old native call differs: {field}")
        if (
            old_call["input_digest"] != public["input_digest"]
            or old_call["source"] != public["source"]
        ):
            raise ValueError("Old call used different public source/input")
        if kind == "old-qwen-dual" and (
            old_call["task"]["candidate"] != "dual"
            or any(old_call["extra_component_calls"].values())
        ):
            raise ValueError("Not the audited unenhanced Qwen dual call")
        configuration = read(receipt["old_environment"])["configuration"]
        if any(configuration[k] != v for k, v in request["parameters"].items()):
            raise ValueError("Historical worker parameters differ")
        if task["model"] == "qwen21" and (
            configuration["prompt_enhancer"] is not False
            or configuration["weight_cache_revision"]
            != plan["model_specifications"]["qwen21"]["weight_revision"]
        ):
            raise ValueError("Qwen21 historical weights/enhancer differ")
        if (
            task["model"] == "flux3"
            and configuration["source_revision"]
            != plan["model_specifications"]["flux3"]["method_commit"]
        ):
            raise ValueError("FLUX3 historical source differs")
    elif kind == "old-replan-s1":
        if task["setting"] != "S1":
            raise ValueError("Old RePlan reuse is only exact S1")
        planner = read(receipt["old_planner"])
        group = planner["groups"][0]
        if planner["status"] != "planned" or len(planner["groups"]) != 1:
            raise ValueError("Old planner was not a complete native plan")
        if group["instruction"] != request["prompt"] or group["response"] != old_call["response"]:
            raise ValueError("Old RePlan instruction/response differs")
        if group["template"] != Path(request["planner_template"]).read_text():
            raise ValueError("Old RePlan template differs")
        if (
            old_call["images"] != [request["editor_image"]]
            or request["editor_image"] != request["planner_image"]
        ):
            raise ValueError("Old RePlan did not use the same clean image")
        if (
            old_call["input_digest"] != public["input_digest"]
            or old_call["seed"] != request["seed"]
        ):
            raise ValueError("Old RePlan public input/seed differs")
        configuration = read(receipt["old_environment"])["configuration"]
        if any(configuration[k] != v for k, v in request["parameters"].items()):
            raise ValueError("Old RePlan parameters differ")
        if (
            configuration["source_revision"]
            != plan["model_specifications"]["replan"]["method_commit"]
        ):
            raise ValueError("Old RePlan source differs")
        if stage == "planner":
            return {
                "status": "native-response-returned",
                "response": group["response"],
                "prompt": request["prompt"],
                "seed": 42,
                "reused": True,
                "public_input_digest": public["input_digest"],
                "configuration_id": request["configuration_id"],
                "planner_image": request["planner_image"],
                "planner_image_sha256": request["image_sha256"][request["planner_image"]],
                "template_sha256": sha256_file(Path(request["planner_template"])),
                "native_planner_calls": 0,
                "reused_native_planner_calls": planner["extra_planner_calls"],
                "reuse_receipt": str(cache_path),
            }
    elif kind == "fixed-validation":
        previous_request = read(receipt["original_request"])
        if previous_request != request:
            raise ValueError("Previous fixed validation request differs")
        if stage == "planner":
            result = dict(old_result)
            for key in ["plan_digest", "call_digest", "request_digest"]:
                result.pop(key, None)
            for key in [
                "native_planner_calls",
                "extra_planner_api_calls",
                "extra_planner_batch_items",
            ]:
                result["reused_" + key] = result.get(key, 0)
            result.update(
                reused=True,
                native_planner_calls=0,
                extra_planner_api_calls=0,
                reuse_receipt=str(cache_path),
            )
            return result
    else:
        raise ValueError(f"Unsupported cache verification policy: {kind}")
    if old_result["status"] != "generated":
        raise ValueError("Only successful exact computations may be reused")
    check_hash(receipt["output_image"], old_result["output_sha256"])
    with Image.open(receipt["output_image"]) as image:
        if list(image.size) != public["source"]["size"]:
            raise ValueError("Cached output was not resized to the source canvas")
    result = {
        "status": "generated",
        "output_image": receipt["output_image"],
        "output_sha256": old_result["output_sha256"],
        "raw_size": old_result.get("raw_size"),
        "inference_api_calls": 0,
        "reused": True,
        "reuse_receipt": str(cache_path),
        "original_call": receipt["original_call"],
        "original_result": receipt["original_result"],
        "reused_inference_api_calls": old_result.get("inference_api_calls", 1),
    }
    for key in [
        "native_result",
        "actual_global_prompt",
        "actual_region_guidance",
        "generation_metadata",
    ]:
        if key in old_result:
            result[key] = old_result[key]
    return result
