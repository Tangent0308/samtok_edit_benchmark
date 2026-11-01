"""Build current 1MP public assets and immutable native requests, without GPUs."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import multiprocessing
from contextlib import ExitStack
from pathlib import Path
import shutil

from samtok_benchmark.io import digest, sha256_file, write_json
from samtok_benchmark.paths import repository_root
from . import canvas, full_plan
from .fairness_dev_plan import MODELS, SETTINGS, read, request_identity, verify_task
from .fairness_dev_revision import mice_text_audit, MiceTextOverflow
from .inputs import export_fairness_inputs
from .plan import prepare_plan
from .public import project
from .render import specification

BASE = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
RESOURCES = BASE / ".ifbench-tmp/fairness-v21-qwen-repaired-dev20-20261031"
PROBE_SCHEMA = "ifbench-1mp-probe-v1"
PROBE_SETTINGS = ["S1", "S3-point", "S5"]
_BUILD_CASE = None


def _build_case_in_child(case):
    return _BUILD_CASE(case)


def nas_resources(descriptor, aliases):
    """Resolve old staging aliases to the same immutable bytes on shared NAS."""
    paths = dict(descriptor["paths"])
    resolved = []
    for key in ("sources", "replan_planner_weights"):
        matches = [a for a in aliases if a["alias"] == paths[key]]
        if len(matches) != 1:
            raise ValueError(f"Exactly one pinned resource manifest required: {key}")
        item = matches[0]
        target = Path(item["target"])
        if not target.is_absolute() or not target.resolve().is_relative_to(BASE):
            raise ValueError(f"Resource must resolve on shared NAS: {key}")
        if not target.is_dir() or not item.get("files"):
            raise ValueError(f"Missing pinned NAS resource: {key}")
        paths[key] = str(target)
        resolved.append({**item, "alias": str(target)})
    if not Path(paths["models"]).resolve().is_relative_to(BASE):
        raise ValueError("Model weights must resolve on shared NAS")
    return paths, resolved


def selections(cases, reference):
    pool = reference["data"]["validation_pool_case_ids"]
    index = {c["id"]: c for c in cases}
    # Fixed public K/ID selection, never model scores or outputs.
    selected = [next(cid for cid in pool if len(index[cid]["units"]) == k) for k in (2, 5)]
    gallery = selected + [next(cid for cid in pool if len(index[cid]["units"]) == 4)]
    return selected, gallery


def prepare(bundle, *, scope="probe", resources=RESOURCES, results=None, workers=8):
    from evaluation.protocol_audit.prepare_fairness_dev20 import request_for
    from evaluation.protocol_audit.prepare_fairness_dev20_revision import snapshot_repo

    if type(workers) is not int or not 1 <= workers <= 16:
        raise ValueError("CPU preparation workers must be between 1 and 16")
    repo, bundle = repository_root(), Path(bundle).resolve()
    if bundle.exists() and any(bundle.iterdir()):
        raise ValueError("Use an empty bundle; existing requests and attempts are immutable")
    bundle.mkdir(parents=True, exist_ok=True)
    results = Path(results).resolve() if results else bundle / "results"
    if results.exists():
        raise ValueError("Use a new results directory")
    reference = read(repo / "configs/evaluation/fairness_v2_2_1mp.json")
    write_json(bundle / "configuration.json", reference)
    shared = bundle / "assets/shared_inputs"
    manifest = repo / "data/v2_2.6.0/cases.jsonl"
    cases, split, assignments = prepare_plan(manifest, shared / "plan")
    probe_ids, gallery_ids = selections(cases, reference)
    active_ids = [c["id"] for c in cases] if scope == "full" else probe_ids
    build_ids = active_ids if scope == "full" else gallery_ids
    settings = SETTINGS if scope == "full" else PROBE_SETTINGS
    owners = full_plan.assign_nodes(cases)
    owner = {cid: int(n) for n, ids in owners.items() for cid in ids}
    descriptor = read(Path(resources) / "plan.json")
    shutil.copyfile(Path(resources) / "bootstrap.json", bundle / "bootstrap.json")
    paths, aliases = nas_resources(descriptor, read(Path(resources) / "aliases.json"))
    write_json(bundle / "aliases.json", aliases)
    from evaluation.protocol_audit import fairness_flux3_replan

    fairness_flux3_replan.SOURCES = Path(paths["sources"])
    schema = full_plan.SCHEMA if scope == "full" else PROBE_SCHEMA
    auth = {
        "schema": schema,
        "full_release_and_judge_authorized": scope == "full",
        "probe_authorized": scope == "probe",
        "nodes": 4,
        "gpus_per_node": 8,
        "one_sample_per_request": True,
        "quality_search": False,
        "seed": 42,
        "protocol_revision": canvas.REVISION,
        "native_output_grid": ["replan", "mirage"],
    }
    write_json(bundle / "AUTHORIZATION.json", auth)
    from . import render

    font = bundle / "assets/fonts/DejaVuSans.ttf"
    font.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(render.FONT, font)
    if sha256_file(font) != sha256_file(render.FONT):
        raise ValueError("Packaged annotation font differs")
    render.FONT = font
    renderer = {**specification(), "public_canvas": canvas.POLICY}
    write_json(shared / "renderer.json", renderer)
    write_json(
        bundle / "historical_exposure.json",
        {
            "former_dev": split["dev"],
            "former_test": split["test"],
            "fixed_dev20": reference["data"]["validation_pool_case_ids"],
            "reporting": "all 1084 sources; not an unseen held-out estimate",
        },
    )
    write_json(
        bundle / "cache/judge_index.json",
        {"judge_config": reference["judge_config"], "entries": {}},
    )
    plan = {
        "schema": schema,
        "protocol_revision": canvas.REVISION,
        "seed": 42,
        "model_order": MODELS,
        "models": MODELS,
        "settings": settings,
        "case_ids": active_ids,
        "gallery_case_ids": gallery_ids,
        "node_assignments": owners,
        "shard_seed": full_plan.SHARD_SEED,
        "audit_case_ids": sorted(
            active_ids, key=lambda c: digest(["full4-human-audit", 20261031, c])
        )[:10],
        "audit_seed": 20261031,
        "canvas_policy": deepcopy(canvas.POLICY),
        "configuration_sha256": digest(reference),
        "model_specifications": reference["model_specifications"],
        "judge_config": reference["judge_config"],
        "case_manifest": str(manifest),
        "case_manifest_sha256": sha256_file(manifest),
        "dataset_root": str(BASE / "datasets/samtok_edit_benchmark_v2"),
        "results_root": str(results),
        "paths": {**paths, "shared": str(shared), "full_shared": str(shared)},
        "full_release_authorized": scope == "full",
        "freeze_authorized": scope == "full",
        "test_authorized": scope == "full",
        "report_scope": "all-1084" if scope == "full" else "engineering-probe",
        "quality_search": False,
        "tasks": [],
    }
    for key, relative in [
        ("authorization", "AUTHORIZATION.json"),
        ("configuration_reference", "configuration.json"),
        ("historical_exposure", "historical_exposure.json"),
        ("assignments", "assets/shared_inputs/plan/assignments.json"),
        ("renderer", "assets/shared_inputs/renderer.json"),
        ("cache_index", "cache/judge_index.json"),
    ]:
        path_key = key + "_path" if key in {"authorization", "assignments", "renderer"} else key
        plan[path_key] = str(bundle / relative)
        plan[key + "_sha256"] = sha256_file(bundle / relative)
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        str(Path(plan["paths"]["models"]) / "FLUX.2-klein-4B/tokenizer"), local_files_only=True
    )
    check_plan = {**plan, "case_ids": build_ids}

    def build_case(case):
        cid = case["id"]
        tasks, overflows = [], []
        canonical = project(case, "S1", assignments["assignments"][cid], Path(plan["dataset_root"]))
        asset_dir = shared / "canvases" / cid
        source, transform = canvas.make_source(canonical["source"], asset_dir)
        for setting in SETTINGS:
            public = canvas.project_public(
                project(case, setting, assignments["assignments"][cid], Path(plan["dataset_root"])),
                source,
                transform,
                asset_dir / "masks",
            )
            directory = shared / "requests" / setting / cid
            inputs = export_fairness_inputs(public, directory)
            files = {source["path"]: source["sha256"]}
            if inputs["annotation"]:
                files[inputs["annotation"]["path"]] = inputs["annotation"]["sha256"]
            files.update(
                {
                    u["region"]["path"]: u["region"]["sha256"]
                    for u in public["units"]
                    if u["locator"] == "mask"
                }
            )
            for model in MODELS:
                key = f"{model}/{setting}/{cid}"
                request = canvas.revise_request(
                    model, request_for(model, cid, setting, shared_root=shared), public
                )
                request_path = bundle / "requests" / key / "request.json"
                write_json(request_path, request)
                input_files = dict(files)
                if model == "replan":
                    input_files[request["planner_template"]] = sha256_file(
                        Path(request["planner_template"])
                    )
                out = results / "runs" / model / "outputs" / setting / cid
                task = {
                    "key": key,
                    "task_id": key,
                    "model": model,
                    "case_id": cid,
                    "setting": setting,
                    "node": owner[cid],
                    "request_path": str(request_path),
                    "request_sha256": sha256_file(request_path),
                    "public_request": str(directory / "public.json"),
                    "public_digest": public["input_digest"],
                    "input_files": input_files,
                    "output_dir": str(out),
                    "result_path": str(out / "result.json"),
                    "planner_dir": str(results / "runs" / model / "planners" / setting / cid),
                    "scientific_digest": request_identity(plan, model, request),
                    "cache": {},
                    "cache_sha256": {},
                    "canvas_transform": str(asset_dir / "geometry.json"),
                    "canvas_transform_sha256": sha256_file(asset_dir / "geometry.json"),
                }
                if model == "mice":
                    try:
                        audit = mice_text_audit(
                            tokenizer, request["prompt"], 1 + len(request["regional_units"])
                        )
                    except MiceTextOverflow as error:
                        audit = error.audit
                        overflows.append({"key": key, "node": owner[cid], "audit": audit})
                    path = bundle / "preflight/mice" / setting / cid / "text_condition_check.json"
                    write_json(path, audit)
                    task["text_preflight"] = {"path": str(path), "sha256": sha256_file(path)}
                tasks.append(task)
        for task in tasks:
            verify_task(check_plan, task)
        return tasks, overflows

    # Independent source groups own their output directories and tokenizer state.
    # CPU-only fork keeps the exact public constructor and per-request verifier.
    global _BUILD_CASE
    _BUILD_CASE = build_case
    selected_cases = [case for case in cases if case["id"] in build_ids]
    overflows, verified_requests = [], 0
    with ExitStack() as stack:
        if workers == 1:
            completed = map(build_case, selected_cases)
        else:
            pool = stack.enter_context(
                multiprocessing.get_context("fork").Pool(min(workers, len(selected_cases)))
            )
            completed = pool.imap_unordered(_build_case_in_child, selected_cases)
        for count, (tasks, warnings) in enumerate(completed, 1):
            verified_requests += len(tasks)
            overflows.extend(warnings)
            plan["tasks"].extend(
                task for task in tasks
                if task["case_id"] in active_ids and task["setting"] in settings
            )
            progress = {
                "prepared_sources": count,
                "total_sources": len(selected_cases),
                "cpu_verified_requests": verified_requests,
                "gpu_tasks_planned": len(plan["tasks"]),
                "new_inference_calls": 0,
            }
            write_json(bundle / "preparation_progress.json", progress)
            print(json.dumps(progress), flush=True)
    overflows.sort(key=lambda item: item["key"])
    write_json(
        bundle / "preflight/TEXT_LIMITS.json",
        {"count": len(overflows), "mice_input_overflows": overflows},
    )
    plan["text_preflight_path"] = str(bundle / "preflight/TEXT_LIMITS.json")
    plan["text_preflight_sha256"] = sha256_file(Path(plan["text_preflight_path"]))
    plan["tasks"].sort(
        key=lambda t: (
            MODELS.index(t["model"]),
            settings.index(t["setting"]),
            active_ids.index(t["case_id"]),
        )
    )
    # Every task, including gallery-only requests, was verified in its CPU process.
    snapshot_repo(bundle)
    files = read(bundle / "code_manifest.json")["files"]
    plan["helper_sha256"] = {
        p: h for p, h in files.items() if p.startswith("src/") and p.endswith(".py")
    }
    plan["case_manifest"] = str(bundle / "repo/data/v2_2.6.0/cases.jsonl")
    if scope == "full":
        plan["cluster_execution"] = {
            "platform": "arnold",
            "workers": 4,
            "gpus_per_worker": 8,
            "aggregate_node": 0,
            "automatic_retry": False,
        }
        shutil.copyfile(
            repo / "src/evaluation/protocol_audit/start_arnold_full4.sh", bundle / "start.sh"
        )
        (bundle / "start.sh").chmod(0o755)
    plan["digest"] = digest(plan)
    write_json(bundle / "plan.json", plan)
    write_json(
        bundle / "PREPARATION.json",
        {
            "plan_digest": plan["digest"],
            "sources": len(active_ids),
            "tasks": len(plan["tasks"]),
            "cpu_verified_requests": verified_requests,
            "gallery_sources": gallery_ids,
            "mice_overflows": len(overflows),
            "new_inference_calls": 0,
            "generation_cache_entries": 0,
            "judge_cache_entries": 0,
        },
    )
    return plan


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--scope", choices=["probe", "full"], default="probe")
    p.add_argument("--resources", type=Path, default=RESOURCES)
    p.add_argument("--results", type=Path)
    p.add_argument("--workers", type=int, default=8, help="CPU source preparation processes")
    a = p.parse_args()
    prepare(a.bundle, scope=a.scope, resources=a.resources, results=a.results, workers=a.workers)


if __name__ == "__main__":
    main()
