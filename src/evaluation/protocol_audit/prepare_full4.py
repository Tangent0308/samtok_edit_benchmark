"""Prepare and publish a fixed whole-release four-node run; CPU and metadata only."""

from __future__ import annotations

import argparse
import multiprocessing
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
from threading import Lock

from samtok_benchmark.io import digest, sha256_file, write_json
from samtok_benchmark.paths import repository_root
from samtok_benchmark.ifbench import full_plan
from samtok_benchmark.ifbench.fairness_dev_plan import (
    load_plan as load_dev,
    read,
    request_identity,
    verify_task,
    verify_cache,
)
from samtok_benchmark.ifbench.fairness_dev_revision import (
    revise_request,
    mice_text_audit,
    MiceTextOverflow,
)
from samtok_benchmark.ifbench.inputs import export_fairness_inputs
from samtok_benchmark.ifbench.plan import prepare_plan
from samtok_benchmark.ifbench.public import project
from evaluation.protocol_audit.prepare_fairness_dev20 import request_for, save
from evaluation.protocol_audit.prepare_fairness_dev20_revision import (
    attach_completed_cache,
    export_completed_judge,
    snapshot_repo,
)

REPO = repository_root()
SHARED_BASE = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
DEFAULT_PARENT = SHARED_BASE / ".ifbench-tmp/fairness-v21-qwen-repaired-dev20-20261031"
DEFAULT_BUNDLE = SHARED_BASE / ".ifbench-tmp/full4-v21-1084-20261031"
DEFAULT_RESULTS = SHARED_BASE / "experiments2/IF-Bench/full4-v21-1084-20261031"
DATASET = SHARED_BASE / "datasets/samtok_edit_benchmark_v2"
_BUILD_CASE = None


def _build_case_in_child(case):
    return _BUILD_CASE(case)


def source_snapshot(bundle, plan):
    if (bundle / "READY.json").exists():
        raise ValueError("Published bundles are immutable")
    if Path(plan["results_root"]).exists():
        raise ValueError("Cannot refresh source after any formal output directory exists")
    from samtok_benchmark.ifbench.render import specification

    renderer = specification()
    if plan.get("canvas_policy"):
        renderer["public_canvas"] = plan["canvas_policy"]
    historical_renderer = read(Path(plan["paths"]["shared"]) / "renderer.json")
    if renderer != historical_renderer:
        raise ValueError("Renderer/font/library configuration differs from approved shared inputs")
    if (bundle / "code_manifest.json").exists():
        history = bundle / "source_history.jsonl"
        with history.open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "previous_plan_digest": plan.get("digest"),
                        "previous_code_manifest_sha256": sha256_file(bundle / "code_manifest.json"),
                    }
                )
                + "\n"
            )
        (bundle / "code_manifest.json").unlink()
        shutil.rmtree(bundle / "repo")
    save(bundle / "assets/shared_inputs/renderer.json", renderer)
    plan["renderer_path"] = str(bundle / "assets/shared_inputs/renderer.json")
    plan["renderer_sha256"] = sha256_file(Path(plan["renderer_path"]))
    snapshot_repo(bundle)
    entry = "start_arnold_full4.sh" if plan.get("cluster_execution") else "start_full4.sh"
    shutil.copyfile(REPO / "src/evaluation/protocol_audit" / entry, bundle / "start.sh")
    (bundle / "start.sh").chmod(0o755)
    files = read(bundle / "code_manifest.json")["files"]
    plan["helper_sha256"] = {
        p: h for p, h in files.items() if p.startswith("src/") and p.endswith(".py")
    }
    plan.pop("digest", None)
    plan["digest"] = digest(plan)
    write_json(bundle / "plan.json", plan)
    return plan


def prepare(bundle, parent_bundle, results, workers=8):
    bundle, parent_bundle, results = (p.resolve() for p in (bundle, parent_bundle, results))
    if (bundle.exists() and any(bundle.iterdir())) or results.exists():
        raise ValueError(
            "Use a new empty bundle and a new results path; never replace prior evidence"
        )
    parent_path = parent_bundle / "plan.json"
    parent = load_dev(parent_path, helper_root=parent_bundle / "repo")
    if (
        read(parent_bundle / "results/COMPLETED.json")["status"]
        != "completed-awaiting-freeze-review"
    ):
        raise ValueError("Only the completed repaired dev20 can be the reuse parent")
    bundle.mkdir(parents=True)
    reference = parent_bundle / "configuration.json"
    shutil.copyfile(reference, bundle / "configuration.json")
    config = read(reference)
    if (
        config["model_specifications"] != parent["model_specifications"]
        or config["judge_config"] != parent["judge_config"]
    ):
        raise ValueError("Current configuration no longer matches the approved completed run")
    save(
        bundle / "AUTHORIZATION.json",
        {
            "schema": full_plan.SCHEMA,
            "user_instruction": "下面我希望做全量的评测，并且最终结果不区分dev，直接就是所有数据的总结果。请你给我一个4机实验的实现。",
            "hardware_confirmation": "4 台均为 8×H100 80GB、相同挂载",
            "full_release_and_judge_authorized": True,
            "freeze_latest_fixed_configuration": True,
            "nodes": 4,
            "gpus_per_node": 8,
            "seed": 42,
            "one_sample_per_request": True,
            "quality_search": False,
            "report_scope": "all-1084",
            "reuse_policy": "exact completed terminal requests including native failures; retain all original costs",
            "unknown_admission_retry": False,
        },
    )
    shared = bundle / "assets/shared_inputs"
    manifest = REPO / "data/v2_2.6.0/cases.jsonl"
    cases, historical_split, assignments = prepare_plan(manifest, shared / "plan")
    owners = full_plan.assign_nodes(cases)
    owner = {cid: int(node) for node, ids in owners.items() for cid in ids}
    old_tasks = {t["key"]: t for t in parent["tasks"]}
    old_cases = set(parent["case_ids"])
    save(
        bundle / "historical_exposure.json",
        {
            "former_split_digest": historical_split["digest"],
            "former_dev": historical_split["dev"],
            "former_test": historical_split["test"],
            "fixed_dev20": parent["case_ids"],
            "historical_full_release_exposure": True,
            "reporting": "All sources are included in one total; this is not an unseen held-out estimate.",
        },
    )
    audit_ids = sorted(
        (c["id"] for c in cases), key=lambda c: digest(["full4-human-audit", 20261031, c])
    )[:10]
    plan = {
        "schema": full_plan.SCHEMA,
        "protocol_revision": "fairness-v2.1-full1084-four-node",
        "seed": 42,
        "model_order": full_plan.MODELS,
        "models": full_plan.MODELS,
        "settings": full_plan.SETTINGS,
        "case_ids": [c["id"] for c in cases],
        "node_assignments": owners,
        "shard_seed": full_plan.SHARD_SEED,
        "audit_case_ids": audit_ids,
        "audit_seed": 20261031,
        "authorization_path": str(bundle / "AUTHORIZATION.json"),
        "authorization_sha256": sha256_file(bundle / "AUTHORIZATION.json"),
        "configuration_reference": str(bundle / "configuration.json"),
        "configuration_reference_sha256": sha256_file(bundle / "configuration.json"),
        "configuration_sha256": parent["configuration_sha256"],
        "model_specifications": deepcopy(parent["model_specifications"]),
        "judge_config": deepcopy(parent["judge_config"]),
        "case_manifest": str(bundle / "repo/data/v2_2.6.0/cases.jsonl"),
        "case_manifest_sha256": sha256_file(manifest),
        "dataset_root": str(DATASET),
        "results_root": str(results),
        "cache_index": str(bundle / "cache/judge_index.json"),
        "paths": {**parent["paths"], "full_shared": str(shared)},
        "historical_exposure": str(bundle / "historical_exposure.json"),
        "historical_exposure_sha256": sha256_file(bundle / "historical_exposure.json"),
        "assignments_path": str(shared / "plan/assignments.json"),
        "assignments_sha256": sha256_file(shared / "plan/assignments.json"),
        "parent_run": {
            "plan": str(parent_path),
            "plan_sha256": sha256_file(parent_path),
            "completion_sha256": sha256_file(parent_bundle / "results/COMPLETED.json"),
            "code_manifest_sha256": sha256_file(parent_bundle / "code_manifest.json"),
        },
        "full_release_authorized": True,
        "freeze_authorized": True,
        "test_authorized": True,
        "report_scope": "all-1084",
        "quality_search": False,
        "tasks": [],
    }
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        str(Path(parent["paths"]["models"]) / "FLUX.2-klein-4B/tokenizer"), local_files_only=True
    )
    tokenizer_lock = Lock()

    def build_case(case):
        cid = case["id"]
        tasks, overflows = [], []
        for setting in full_plan.SETTINGS:
            if cid in old_cases:
                public_path = Path(old_tasks[f"qwen2511/{setting}/{cid}"]["public_request"])
                public = read(public_path)
                inputs = read(public_path.with_name("inputs.json"))
                expected = project(case, setting, assignments["assignments"][cid], DATASET)
                if public != expected:
                    raise ValueError("Prior public input differs from the full frozen assignment")
            else:
                public = project(case, setting, assignments["assignments"][cid], DATASET)
                directory = shared / "requests" / setting / cid
                inputs = export_fairness_inputs(public, directory)
                public_path = directory / "public.json"
            files = {public["source"]["path"]: public["source"]["sha256"]}
            if inputs["annotation"]:
                files[inputs["annotation"]["path"]] = inputs["annotation"]["sha256"]
            files.update(
                {
                    u["region"]["path"]: u["region"]["sha256"]
                    for u in public["units"]
                    if u["locator"] == "mask"
                }
            )
            for model in full_plan.MODELS:
                key = f"{model}/{setting}/{cid}"
                if cid in old_cases:
                    request, _ = verify_task(parent, old_tasks[key])
                else:
                    request = revise_request(
                        model, request_for(model, cid, setting, shared_root=shared)
                    )
                request_path = bundle / "requests" / key / "request.json"
                save(request_path, request)
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
                    "public_request": str(public_path),
                    "public_digest": public["input_digest"],
                    "input_files": input_files,
                    "output_dir": str(out),
                    "result_path": str(out / "result.json"),
                    "planner_dir": str(results / "runs" / model / "planners" / setting / cid),
                    "scientific_digest": request_identity(plan, model, request),
                    "cache": {},
                    "cache_sha256": {},
                }
                if model == "mice":
                    with tokenizer_lock:
                        try:
                            audit = mice_text_audit(
                                tokenizer, request["prompt"], 1 + len(request["regional_units"])
                            )
                        except MiceTextOverflow as error:
                            audit = error.audit
                            overflows.append({"key": key, "node": owner[cid], "audit": audit})
                    path = bundle / "preflight/mice" / setting / cid / "text_condition_check.json"
                    save(path, audit)
                    task["text_preflight"] = {"path": str(path), "sha256": sha256_file(path)}
                if cid in old_cases:
                    for stage in ["planner", "edit"] if model in {"replan", "mirage"} else ["edit"]:
                        attach_completed_cache(bundle, parent, task, old_tasks[key], stage)
                tasks.append(task)
        return tasks, overflows

    overflow = []
    # CPU-only Linux fork: each process owns its tokenizer and image decoder.
    # This avoids the GIL bottleneck in deterministic contour/prompt construction.
    global _BUILD_CASE
    _BUILD_CASE = build_case
    with multiprocessing.get_context("fork").Pool(processes=workers) as pool:
        for i, (tasks, warnings) in enumerate(pool.imap_unordered(_build_case_in_child, cases), 1):
            plan["tasks"].extend(tasks)
            overflow.extend(warnings)
            if i % 10 == 0 or i == len(cases):
                status = {
                    "prepared_sources": i,
                    "total_sources": len(cases),
                    "prepared_requests": len(plan["tasks"]),
                    "input_overflow_requests": len(overflow),
                    "new_inference_calls": 0,
                }
                write_json(bundle / "preparation_progress.json", status)
                print(json.dumps(status), flush=True)
    order = {cid: i for i, cid in enumerate(plan["case_ids"])}
    plan["tasks"].sort(
        key=lambda t: (
            full_plan.MODELS.index(t["model"]),
            full_plan.SETTINGS.index(t["setting"]),
            order[t["case_id"]],
        )
    )
    save(
        bundle / "preflight/TEXT_LIMITS.json",
        {
            "mice_input_overflows": overflow,
            "count": len(overflow),
            "policy": "native 200-token completeness failure, zero sampled calls, retained denominator; never truncate/rewrite",
        },
    )
    plan["text_preflight_path"] = str(bundle / "preflight/TEXT_LIMITS.json")
    plan["text_preflight_sha256"] = sha256_file(bundle / "preflight/TEXT_LIMITS.json")
    # Include all new answers of the repaired parent, not just its inherited cache index.
    _, judge_count = export_completed_judge(parent_path, bundle)
    plan["cache_index_sha256"] = sha256_file(bundle / "cache/judge_index.json")
    for name in ("aliases.json", "bootstrap.json"):
        shutil.copyfile(parent_bundle / name, bundle / name)
    plan = source_snapshot(bundle, plan)
    full_plan.load_plan(bundle / "plan.json")
    for task in plan["tasks"]:
        if task["cache"]:
            for stage in task["cache"]:
                verify_cache(plan, task, stage)
    save(
        bundle / "PREPARATION.json",
        {
            **full_plan.summary(plan),
            "mice_overflow_requests": len(overflow),
            "verified_judge_cache_keys": judge_count,
            "new_inference_calls": 0,
        },
    )
    print(json.dumps(full_plan.summary(plan)), flush=True)


def publish(bundle, *, refresh_source=False):
    bundle = bundle.resolve()
    if (bundle / "READY.json").exists():
        raise ValueError("Bundle already published; cannot rewrite its freeze")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO).strip():
        raise ValueError("Commit the tested source before publishing a runnable bundle")
    plan = read(bundle / "plan.json")
    preparation = read(bundle / "PREPARATION.json")
    if (
        preparation["sources"] != full_plan.SOURCES
        or preparation["tasks"]
        != full_plan.SOURCES * len(full_plan.MODELS) * len(full_plan.SETTINGS)
        or preparation.get("new_inference_calls") != 0
    ):
        raise ValueError("Complete CPU preparation is required before publication")
    if refresh_source:
        plan = source_snapshot(bundle, plan)
    full_plan.load_plan(bundle / "plan.json")
    manifest = read(bundle / "code_manifest.json")["files"]
    for relative, sha in manifest.items():
        if sha256_file(REPO / relative) != sha:
            raise ValueError(f"Snapshot differs from committed source: {relative}")
    ready = {
        name + "_sha256": sha256_file(bundle / filename)
        for name, filename in [
            ("plan", "plan.json"),
            ("code_manifest", "code_manifest.json"),
            ("aliases", "aliases.json"),
            ("bootstrap", "bootstrap.json"),
        ]
    }
    ready.update(
        schema=full_plan.SCHEMA,
        nodes=4,
        gpus_per_node=8,
        report_scope="all-1084",
        entrypoint_sha256=sha256_file(bundle / "start.sh"),
        results_root=plan["results_root"],
        source_count=len(plan["case_ids"]),
        tasks=len(plan["tasks"]),
        preparation_sha256=sha256_file(bundle / "PREPARATION.json"),
        preparation_plan_digest=preparation["plan_digest"],
        source_commit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
    )
    save(bundle / "READY.json", ready)
    print(
        json.dumps({"published": str(bundle), "source_commit": ready["source_commit"]}), flush=True
    )


def repackage_arnold(bundle, source_bundle, results):
    """Reuse immutable full inputs, changing only launch code and output locations."""
    from concurrent.futures import ThreadPoolExecutor
    from samtok_benchmark.ifbench.fairness_dev_plan import check_hash
    from samtok_benchmark.ifbench.fairness_dev_judge import Cache

    bundle, source_bundle, results = (p.resolve() for p in (bundle, source_bundle, results))
    if (bundle.exists() and any(bundle.iterdir())) or results.exists():
        raise ValueError("Use a new empty bundle and new formal result path")
    ready = read(source_bundle / "READY.json")
    for name, key in (
        ("plan.json", "plan_sha256"),
        ("code_manifest.json", "code_manifest_sha256"),
        ("bootstrap.json", "bootstrap_sha256"),
        ("aliases.json", "aliases_sha256"),
        ("PREPARATION.json", "preparation_sha256"),
    ):
        check_hash(source_bundle / name, ready[key])
    original = full_plan.load_plan(source_bundle / "plan.json", helper_root=source_bundle / "repo")
    if Path(original["results_root"]).exists():
        raise ValueError(
            "Original full run has artifacts; inspect admissions instead of making a new run"
        )
    plan = deepcopy(original)
    plan.pop("digest")
    bundle.mkdir(parents=True)
    plan["results_root"] = str(results)
    plan["cluster_execution"] = {
        "platform": "arnold",
        "workers": 4,
        "gpus_per_worker": 8,
        "topology": "ARNOLD_ID/ARNOLD_WORKER_NUM/ARNOLD_WORKER_GPU/ARNOLD_WORKER_HOSTS",
        "control": "TCP rendezvous, shared heartbeat/barriers, common fatal-error propagation",
        "generation": "eight native single-GPU workers per source owner",
        "judge": "four independent frozen TP8/EP engines",
        "aggregate_node": 0,
        "automatic_retry": False,
    }
    plan["launch_parent"] = {
        "bundle": str(source_bundle),
        "ready_sha256": sha256_file(source_bundle / "READY.json"),
        "plan_sha256": sha256_file(source_bundle / "plan.json"),
        "input_rebuilds": 0,
        "scientific_configuration_changes": 0,
    }
    for task in plan["tasks"]:
        for key in ("output_dir", "result_path", "planner_dir"):
            task[key] = str(results / Path(task[key]).relative_to(original["results_root"]))
    # Inputs/prompts/planner caches retain their original absolute references and hashes.
    excluded = {"output_dir", "result_path", "planner_dir"}

    def inputs(tasks):
        return [{k: v for k, v in t.items() if k not in excluded} for t in tasks]

    if inputs(plan["tasks"]) != inputs(original["tasks"]):
        raise ValueError("A launch migration must not change any scientific request")
    input_digest = digest(inputs(plan["tasks"]))
    for name in ("aliases.json", "bootstrap.json", "configuration.json", "AUTHORIZATION.json"):
        shutil.copyfile(source_bundle / name, bundle / name)
    plan.update(
        authorization_path=str(bundle / "AUTHORIZATION.json"),
        configuration_reference=str(bundle / "configuration.json"),
        case_manifest=str(bundle / "repo/data/v2_2.6.0/cases.jsonl"),
    )
    # Relocate only live canonical-cache pointers, preserving the raw evidence bytes.
    cache = read(original["cache_index"])
    references = {}
    for entry in cache["entries"].values():
        refs = [(entry, "effective_record", entry["sha256"])]
        refs += [(ref, "path", ref["sha256"]) for ref in entry["provenance_files"]]
        for container, key, expected in refs:
            old = Path(container[key])
            new = bundle / old.relative_to(source_bundle)
            if old in references and references[old] != (new, expected):
                raise ValueError("Conflicting cache provenance hashes")
            references[old] = (new, expected)
            container[key] = str(new)

    def copy_evidence(item):
        old, (new, expected) = item
        check_hash(old, expected)
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(old, new)
        check_hash(new, expected)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(copy_evidence, references.items()))
    write_json(bundle / "cache/judge_index.json", cache)
    plan["cache_index"] = str(bundle / "cache/judge_index.json")
    plan["cache_index_sha256"] = sha256_file(Path(plan["cache_index"]))
    plan = source_snapshot(bundle, plan)
    full_plan.load_plan(bundle / "plan.json")
    cache_check = Cache(plan["cache_index"], plan["judge_config"]).verify_portable_files(bundle)
    save(
        bundle / "PREPARATION.json",
        {
            **full_plan.summary(plan),
            "new_inference_calls": 0,
            "completion_method": "Verified immutable full-input reuse; exact non-output task equality and relocated cache byte checks. All runtime input preflights remain mandatory.",
            "unchanged_task_inputs_digest": input_digest,
            "source_preparation": {
                "path": str(source_bundle / "PREPARATION.json"),
                "sha256": ready["preparation_sha256"],
            },
            "verified_canonical_cache": cache_check,
            "changed_inference_parameters": 0,
            "rebuilt_inputs": 0,
        },
    )
    print(json.dumps(full_plan.summary(plan)), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    p.add_argument("--parent", type=Path, default=DEFAULT_PARENT)
    p.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--publish", action="store_true")
    p.add_argument("--refresh-source", action="store_true")
    p.add_argument(
        "--reuse-full-inputs",
        type=Path,
        help="Prepare a new ARNOLD bundle from an unstarted frozen full-input bundle",
    )
    a = p.parse_args()
    if a.publish:
        publish(a.bundle, refresh_source=a.refresh_source)
    else:
        if a.refresh_source:
            p.error("--refresh-source requires --publish")
        if a.reuse_full_inputs:
            repackage_arnold(a.bundle, a.reuse_full_inputs, a.results)
        else:
            prepare(a.bundle, a.parent, a.results, a.workers)
