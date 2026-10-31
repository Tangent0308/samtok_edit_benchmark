"""Complete 1MP setting coverage with 49 unsampled, already frozen requests."""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import shutil
import sys

from samtok_benchmark.io import digest, read_jsonl, sha256_file, write_json
from samtok_benchmark.paths import repository_root
from . import canvas
from .fairness_dev_plan import (
    MODELS,
    SETTINGS,
    check_hash,
    read,
    request_identity,
    verify_task,
    verify_cache,
)
from .one_mp_probe import execute as execute_probe, load_plan as load_probe, summary
from .prepare_one_mp import PROBE_SETTINGS, selections

SCHEMA = "ifbench-1mp-coverage-v1"
COVERAGE_SETTINGS = [setting for setting in SETTINGS if setting not in PROBE_SETTINGS]

__all__ = ["load_plan", "verify_task", "verify_cache"]


def coverage_case(cases, configuration):
    return selections(cases, configuration)[0][1]  # fixed K=5 source, never output-driven


def prepare(bundle, origin):
    from evaluation.protocol_audit.prepare_fairness_dev20_revision import snapshot_repo

    bundle, origin = Path(bundle).resolve(), Path(origin).resolve()
    if bundle.exists() and any(bundle.iterdir()):
        raise ValueError("Coverage preparation needs a new empty directory")
    parent = load_probe(origin / "plan.json", helper_root=origin / "repo")
    completion = summary(parent)
    if any(row["pending"] for row in completion["models"].values()):
        raise ValueError("Finish the original probe before extending setting coverage")
    config = read(parent["configuration_reference"])
    case_id = coverage_case(read_jsonl(parent["case_manifest"]), config)
    bundle.mkdir(parents=True, exist_ok=True)
    for name in ("configuration.json", "bootstrap.json", "aliases.json"):
        shutil.copyfile(origin / name, bundle / name)
    auth = {
        "schema": SCHEMA,
        "coverage_and_judge_authorized": True,
        "case_id": case_id,
        "settings": COVERAGE_SETTINGS,
        "models": MODELS,
        "seed": 42,
        "quality_search": False,
        "one_sample_per_request": True,
    }
    write_json(bundle / "AUTHORIZATION.json", auth)
    plan = deepcopy(parent)
    plan.pop("digest")
    plan.update(
        schema=SCHEMA,
        case_ids=[case_id],
        gallery_case_ids=[case_id],
        settings=COVERAGE_SETTINGS,
        results_root=str(bundle / "results"),
        report_scope="engineering-setting-coverage",
        tasks=[],
        probe_origin={
            "path": str(origin / "plan.json"),
            "sha256": sha256_file(origin / "plan.json"),
            "code_manifest_sha256": sha256_file(origin / "code_manifest.json"),
        },
        configuration_reference=str(bundle / "configuration.json"),
        configuration_reference_sha256=sha256_file(bundle / "configuration.json"),
        authorization_path=str(bundle / "AUTHORIZATION.json"),
        authorization_sha256=sha256_file(bundle / "AUTHORIZATION.json"),
    )
    shared = Path(parent["paths"]["shared"])
    geometries = shared / "canvases" / case_id / "geometry.json"
    registered = {task["key"] for task in parent["tasks"]}
    for model in MODELS:
        for setting in COVERAGE_SETTINGS:
            key = f"{model}/{setting}/{case_id}"
            if key in registered:
                raise ValueError("Coverage must not resample an original probe request")
            original_output = (
                Path(parent["results_root"]) / "runs" / model / "outputs" / setting / case_id
            )
            if original_output.exists():
                raise ValueError(
                    "Previously unregistered request already has output/admission artifacts"
                )
            request_path = origin / "requests" / key / "request.json"
            public_path = shared / "requests" / setting / case_id / "public.json"
            request, public = read(request_path), read(public_path)
            inputs = read(public_path.with_name("inputs.json"))
            assets = [public["source"]]
            if inputs["annotation"]:
                assets.append(inputs["annotation"])
            assets += [u["region"] for u in public["units"] if u["locator"] == "mask"]
            input_files = {item["path"]: item["sha256"] for item in assets}
            if model == "replan":
                template = request["planner_template"]
                input_files[template] = sha256_file(Path(template))
            out = bundle / "results/runs" / model / "outputs" / setting / case_id
            task = {
                "key": key,
                "task_id": key,
                "model": model,
                "setting": setting,
                "case_id": case_id,
                "request_path": str(request_path),
                "request_sha256": sha256_file(request_path),
                "public_request": str(public_path),
                "public_digest": public["input_digest"],
                "input_files": input_files,
                "output_dir": str(out),
                "result_path": str(out / "result.json"),
                "planner_dir": str(
                    bundle / "results/runs" / model / "planners" / setting / case_id
                ),
                "scientific_digest": request_identity(plan, model, request),
                "cache": {},
                "cache_sha256": {},
                "canvas_transform": str(geometries),
                "canvas_transform_sha256": sha256_file(geometries),
            }
            if model == "mice":
                check = origin / "preflight/mice" / setting / case_id / "text_condition_check.json"
                task["text_preflight"] = {"path": str(check), "sha256": sha256_file(check)}
            verify_task(plan, task)
            plan["tasks"].append(task)
    snapshot_repo(bundle)
    manifest = read(bundle / "code_manifest.json")["files"]
    plan["helper_sha256"] = {
        path: sha
        for path, sha in manifest.items()
        if path.startswith("src/") and path.endswith(".py")
    }
    plan["case_manifest"] = str(bundle / "repo/data/v2_2.6.0/cases.jsonl")
    plan["digest"] = digest(plan)
    write_json(bundle / "plan.json", plan)
    load_plan(bundle / "plan.json", helper_root=bundle / "repo")
    write_json(
        bundle / "PREPARATION.json",
        {
            "plan_digest": plan["digest"],
            "sources": 1,
            "tasks": len(plan["tasks"]),
            "cpu_verified_requests": len(plan["tasks"]),
            "new_inference_calls": 0,
            "unchanged_frozen_requests": True,
            "selection": "fixed original K=5 dev source",
        },
    )
    return plan


def load_plan(path, *, helper_root=None):
    path = Path(path).resolve()
    plan = read(path)
    if plan.get("schema") != SCHEMA or plan.get("digest") != digest(
        {k: v for k, v in plan.items() if k != "digest"}
    ):
        raise ValueError("Invalid setting-coverage plan identity")
    if (
        plan.get("canvas_policy") != canvas.POLICY
        or plan.get("seed") != 42
        or plan.get("quality_search") is not False
    ):
        raise ValueError("Changed fixed coverage policy")
    check_hash(plan["configuration_reference"], plan["configuration_reference_sha256"])
    config = read(plan["configuration_reference"])
    if (
        plan["model_specifications"] != config["model_specifications"]
        or plan["judge_config"] != config["judge_config"]
    ):
        raise ValueError("Coverage changed model/Judge configuration")
    check_hash(plan["case_manifest"], plan["case_manifest_sha256"])
    cid = coverage_case(read_jsonl(plan["case_manifest"]), config)
    if (
        plan["case_ids"] != [cid]
        or plan["settings"] != COVERAGE_SETTINGS
        or plan["model_order"] != MODELS
    ):
        raise ValueError("Coverage is limited to one fixed K=5 source and seven missing settings")
    expected = {(m, s, cid) for m in MODELS for s in COVERAGE_SETTINGS}
    if (
        len(plan["tasks"]) != len(expected)
        or {(t["model"], t["setting"], t["case_id"]) for t in plan["tasks"]} != expected
    ):
        raise ValueError("Coverage tasks are incomplete or duplicated")
    check_hash(plan["authorization_path"], plan["authorization_sha256"])
    auth = read(plan["authorization_path"])
    if auth != {
        "schema": SCHEMA,
        "coverage_and_judge_authorized": True,
        "case_id": cid,
        "settings": COVERAGE_SETTINGS,
        "models": MODELS,
        "seed": 42,
        "quality_search": False,
        "one_sample_per_request": True,
    }:
        raise ValueError("Coverage authorization changed")
    origin = plan["probe_origin"]
    check_hash(origin["path"], origin["sha256"])
    check_hash(Path(origin["path"]).parent / "code_manifest.json", origin["code_manifest_sha256"])
    parent = read(origin["path"])
    if set(plan["settings"]) & set(parent["settings"]):
        raise ValueError("Coverage would resample an already registered setting")
    for task in plan["tasks"]:
        if task.get("cache"):
            raise ValueError("Coverage requires unsampled requests, not generation caches")
        out = (
            Path(plan["results_root"]) / "runs" / task["model"] / "outputs" / task["setting"] / cid
        )
        if task["output_dir"] != str(out) or task["result_path"] != str(out / "result.json"):
            raise ValueError("Output escapes the dedicated coverage run")
    root = Path(helper_root) if helper_root else repository_root()
    for relative, expected_sha in plan["helper_sha256"].items():
        check_hash(root / relative, expected_sha)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "run", "worker", "status"])
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--origin", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--model", choices=MODELS)
    parser.add_argument("--stage", choices=["planner", "edit"])
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.bundle, args.origin)
    elif args.action == "worker":
        from .fairness_dev_worker import run_worker

        run_worker(
            args.plan,
            args.model,
            args.stage,
            args.shard,
            args.shards,
            plan_api=sys.modules[__name__],
        )
    elif args.action == "run":
        execute_probe(
            args.plan,
            plan_api=sys.modules[__name__],
            lanes=[
                (["qwen2511"], [0, 1]),
                (["qwen21"], [2]),
                (["flux3", "mice", "flux2_klein9b"], [3]),
                (["replan"], [4]),
                (["mirage"], [5, 6, 7]),
            ],
        )
    else:
        import json

        print(json.dumps(summary(load_plan(args.plan)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
