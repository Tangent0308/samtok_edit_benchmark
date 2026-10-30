"""Prepare the approved v2.1 dev20 correction without GPU or Judge calls.

The parent bundle remains immutable. Only Qwen21 resolution and MICE's
annotation preamble change; all other requests are checked for exact reuse.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
from threading import Lock

from samtok_benchmark.io import digest, sha256_file
from samtok_benchmark.ifbench.fairness_dev_plan import (
    read,
    load_plan,
    request_identity,
    verify_task,
    verify_cache,
)
from samtok_benchmark.ifbench.fairness_dev_revision import (
    REVISION,
    MICE_HEADER,
    revise_request,
    mice_text_audit,
)
from evaluation.protocol_audit.prepare_fairness_dev20 import save

REPO = Path(__file__).resolve().parents[2]
DEFAULT_PARENT = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v2-dev20-20261030"
)
DEFAULT_BUNDLE = DEFAULT_PARENT.with_name("fairness-v21-dev20-20261030")


def file_reference(path):
    return {"path": str(path), "sha256": sha256_file(Path(path))}


def snapshot_repo(bundle):
    paths = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=REPO,
        )
        .decode()
        .split("\0")
    )
    selected = [
        p
        for p in paths
        if p
        and (
            p.startswith(
                ("samtok_benchmark/", "evaluation/protocol_audit/", "tests/", "docs/protocol/")
            )
            or p in {"AGENTS.md", "README.md", "pyproject.toml", "data/v2_2.6.0/cases.jsonl"}
        )
    ]
    files = {}
    for relative in sorted(set(selected)):
        source, target = REPO / relative, bundle / "repo" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        files[relative] = sha256_file(target)
    save(bundle / "code_manifest.json", {"files": files})
    shutil.copyfile(REPO / "evaluation/protocol_audit/start_fairness_dev20.sh", bundle / "start.sh")
    (bundle / "start.sh").chmod(0o755)


def attach_completed_cache(bundle, parent, task, old_task, stage):
    original = (
        Path(old_task["planner_dir"]) / "result.json"
        if stage == "planner"
        else Path(old_task["result_path"])
    )
    result = read(original)
    call = original.with_name("call.json")
    if not call.exists() and result.get("original_call"):
        call = Path(result["original_call"])
    evidence = [file_reference(original), file_reference(old_task["request_path"])]
    if call.exists():
        evidence.append(file_reference(call))
    for key in ("traces", "load_record", "planner_record"):
        if result.get(key):
            evidence.append(file_reference(result[key]))
    if old_task.get("cache", {}).get(stage):
        evidence.append(file_reference(old_task["cache"][stage]))
    receipt = {
        "kind": "completed-dev20",
        "stage": stage,
        "scientific_digest": task["scientific_digest"],
        "parent_plan_digest": parent["digest"],
        "original_result": str(original),
        "original_result_sha256": sha256_file(original),
        "evidence": evidence,
    }
    if call.exists():
        receipt["original_call"] = str(call)
    path = bundle / "cache/generation" / task["key"] / f"{stage}.json"
    save(path, receipt)
    task["cache"][stage] = str(path)
    task["cache_sha256"][stage] = sha256_file(path)


def export_completed_judge(parent_path, bundle):
    from samtok_benchmark.ifbench import fairness_dev_judge as judge

    context = judge.load_plan(parent_path, helper_root=parent_path.parent / "repo")
    bindings, jobs = [], {}
    # Preserve the validated full plan and original model ordering. Only the
    # independent reads are concurrent; canonical key deduplication is identical.
    with ThreadPoolExecutor(max_workers=8) as pool:
        for bound, collected in pool.map(
            lambda model: judge.collect(context, model=model), context["order"]
        ):
            bindings.extend(bound)
            for key, job in collected.items():
                if key in jobs:
                    jobs[key]["logical_keys"].extend(job["logical_keys"])
                else:
                    jobs[key] = job
    if len(bindings) != len(context["plan"]["tasks"]):
        raise ValueError("Completed Judge collection did not cover every parent task")
    print(f"Verified {len(bindings)} parent outcomes / {len(jobs)} unique Judge keys.", flush=True)
    prior_cache = judge.Cache(context["plan"]["cache_index"], context["config"])
    root, raws, effectives, admissions = judge.paths(context)
    entries = {}

    def checked_entry(item):
        key, job = item
        effective = effectives / f"{key}.json"
        value = read(effective)
        judge.verify_effective(value, job, context, prior_cache)
        chain = {p["path"]: p for p in value.get("cache_reuse", {}).get("provenance_files", [])}
        candidates = [effective, raws / f"{key}.json", admissions / f"{key}.json"]
        if value.get("execution_receipt"):
            candidates.append(Path(value["execution_receipt"]))
        for path in candidates:
            if path.exists():
                chain[str(path)] = file_reference(path)
        return key, {
            "effective_record": str(effective),
            "sha256": sha256_file(effective),
            "provenance_files": list(chain.values()),
            "case_id": job["case_id"],
        }

    with ThreadPoolExecutor(max_workers=8) as pool:
        entries.update(pool.map(checked_entry, jobs.items()))
    index = {
        "schema": "ifbench-exact-canonical-judge-cache-v1",
        "config": context["config"],
        "run_id": context["run_id"],
        "entries": entries,
        "source_plan": file_reference(parent_path),
    }
    path = bundle / "cache/judge_index.json"
    save(path, index)
    exported = judge.Cache(path, context["config"])
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda job: exported.lookup(job, context), jobs.values()))
    print(f"Verified all {len(entries)} exported Judge provenance chains.", flush=True)
    return bindings, len(entries)


def prepare(parent_bundle, bundle):
    parent_bundle, bundle = parent_bundle.resolve(), bundle.resolve()
    if bundle == parent_bundle or (bundle / "READY.json").exists():
        raise ValueError("Cannot replace the parent or a published bundle")
    if bundle.exists() and any(bundle.iterdir()):
        raise ValueError("Use a new empty bundle; do not overwrite preparation evidence")
    parent_path = parent_bundle / "plan.json"
    parent = load_plan(parent_path, helper_root=parent_bundle / "repo")
    completed = read(parent_bundle / "results/COMPLETED.json")
    if completed["plan_digest"] != parent["digest"] or (parent_bundle / "results/ACTIVE").exists():
        raise ValueError("Parent must be completed and inactive")
    bundle.mkdir(parents=True, exist_ok=True)
    selection = read(parent["selection_path"])
    save(bundle / "selection.json", selection)  # same IDs; never reselect using results
    save(
        bundle / "AUTHORIZATION.json",
        {
            "schema": parent["schema"],
            "protocol_revision": REVISION,
            "user_instruction": "根据你的建议修复各个推理的流程，修复后提交并推送，并给我新的8机小规模的实验入口指令。",
            "hardware_clarification": "单机 8 卡，沿用此前方式（推荐）",
            "dev20_and_judge_authorized": True,
            "fixed_configuration_approved": True,
            "quality_search": False,
            "test_authorized": False,
            "freeze_authorized": False,
            "seed": 42,
            "one_sample_per_request": True,
            "changes": {
                "qwen21_output_resolution": 2048,
                "mice_annotation_header": MICE_HEADER,
                "mice_effective_text_tokens_unchanged": 200,
            },
        },
    )
    plan = deepcopy(parent)
    plan.pop("digest")
    plan["protocol_revision"] = REVISION
    plan["parent_run"] = {
        "plan": str(parent_path),
        "plan_sha256": sha256_file(parent_path),
        "completion_sha256": sha256_file(parent_bundle / "results/COMPLETED.json"),
        "code_manifest_sha256": sha256_file(parent_bundle / "code_manifest.json"),
    }
    plan["model_specifications"]["qwen21"]["parameters"]["output_resolution"] = 2048
    plan["configuration_sha256"] = digest(
        {
            "parent_configuration": parent["configuration_sha256"],
            "revision": REVISION,
            "changes": read(bundle / "AUTHORIZATION.json")["changes"],
        }
    )
    for field, name in (("authorization", "AUTHORIZATION.json"), ("selection", "selection.json")):
        plan[field + "_path"] = str(bundle / name)
        plan[field + "_sha256"] = sha256_file(bundle / name)
    plan["results_root"] = str(bundle / "results")
    plan["case_manifest"] = str(bundle / "repo/data/v2_2.6.0/cases.jsonl")
    plan["cache_index"] = str(bundle / "cache/judge_index.json")
    helper_files = set(plan["helper_sha256"]) | {
        "samtok_benchmark/ifbench/fairness_dev_revision.py",
        "samtok_benchmark/ifbench/fairness_dev_cache.py",
    }
    plan["helper_sha256"] = {f: sha256_file(REPO / f) for f in sorted(helper_files)}
    plan["tasks"] = []
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        str(Path(plan["paths"]["models"]) / "FLUX.2-klein-4B/tokenizer"), local_files_only=True
    )
    changes, preserved_failures = [], []
    tokenizer_lock = Lock()

    def prepare_task(old_task):
        change, failed = None, None
        old_request, public = verify_task(parent, old_task)
        request = revise_request(old_task["model"], old_request)
        task = deepcopy(old_task)
        path = bundle / "requests" / task["key"] / "request.json"
        save(path, request)
        task.update(
            request_path=str(path), request_sha256=sha256_file(path), cache={}, cache_sha256={}
        )
        output = (
            bundle / "results/runs" / task["model"] / "outputs" / task["setting"] / task["case_id"]
        )
        task.update(
            output_dir=str(output),
            result_path=str(output / "result.json"),
            planner_dir=str(
                bundle
                / "results/runs"
                / task["model"]
                / "planners"
                / task["setting"]
                / task["case_id"]
            ),
        )
        task["scientific_digest"] = request_identity(plan, task["model"], request)
        if task["model"] == "mice":
            # Tokenizers can mutate padding/truncation configuration internally.
            # Parallelize artifact I/O, but serialize use of this shared instance.
            with tokenizer_lock:
                audit = mice_text_audit(
                    tokenizer, request["prompt"], 1 + len(request["regional_units"])
                )
            save(
                bundle
                / "preflight/mice"
                / task["setting"]
                / task["case_id"]
                / "text_condition_check.json",
                audit,
            )
        if request == old_request:
            stages = ["planner", "edit"] if task["model"] in {"replan", "mirage"} else ["edit"]
            for stage in stages:
                attach_completed_cache(bundle, parent, task, old_task, stage)
            previous = read(old_task["result_path"])
            if previous["status"].startswith("failed"):
                failed = task["key"]
        else:
            change = {
                "key": task["key"],
                "old_request_sha256": old_task["request_sha256"],
                "new_request_sha256": task["request_sha256"],
            }
        return task, change, failed

    with ThreadPoolExecutor(max_workers=8) as pool:
        # map preserves the parent's deterministic model/setting/case ordering.
        for task, change, failed in pool.map(prepare_task, parent["tasks"]):
            plan["tasks"].append(task)
            if change:
                changes.append(change)
            if failed:
                preserved_failures.append(failed)
            if len(plan["tasks"]) % 200 == 0:
                print(f"Prepared {len(plan['tasks'])}/1400 requests.", flush=True)
    snapshot_repo(bundle)
    save(bundle / "aliases.json", read(parent_bundle / "aliases.json"))
    save(bundle / "bootstrap.json", read(parent_bundle / "bootstrap.json"))
    bindings, judge_keys = export_completed_judge(parent_path, bundle)
    plan["cache_index_sha256"] = sha256_file(bundle / "cache/judge_index.json")
    plan["digest"] = digest(plan)
    save(bundle / "plan.json", plan)
    loaded = load_plan(bundle / "plan.json")
    from samtok_benchmark.ifbench.fairness_dev_cache import completed_parent

    # Prime this once; independent task validation must not duplicate the
    # shared parent snapshot scan on each of the eight I/O threads.
    completed_parent(loaded)

    def verify(task):
        verify_task(loaded, task)
        for stage in task["cache"]:
            verify_cache(loaded, task, stage)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(verify, loaded["tasks"]))
    unchanged = {t["key"] for t in plan["tasks"] if "edit" in t["cache"]}
    save(
        bundle / "PREPARATION.json",
        {
            "protocol_revision": REVISION,
            "logical_requests": len(plan["tasks"]),
            "changed_requests": changes,
            "new_generation_by_model": dict(Counter(c["key"].split("/")[0] for c in changes)),
            "new_generation_requests": len(changes),
            "reused_terminal_requests": len(unchanged),
            "preserved_failures": preserved_failures,
            "available_judge_cache_keys": judge_keys,
            "unchanged_unique_judge_keys": len(
                {b["judge_key"] for b in bindings if b["key"] in unchanged and b["judge_key"]}
            ),
            "new_gpu_calls_during_preparation": 0,
            "new_judge_calls_during_preparation": 0,
        },
    )
    print(
        f"Prepared {len(changes)} changed requests; {len(unchanged)} exact terminal reuses. Not published yet.",
        flush=True,
    )


def publish(bundle):
    """Publish only a clean, committed snapshot; run after checks and Git push."""
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO).strip():
        raise ValueError("Commit the reviewed source before publication")
    manifest = read(bundle / "code_manifest.json")["files"]
    for relative, expected in manifest.items():
        if (
            sha256_file(REPO / relative) != expected
            or sha256_file(bundle / "repo" / relative) != expected
        ):
            raise ValueError(f"Snapshot is not the checked-in source: {relative}")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    save(
        bundle / "READY.json",
        {
            "plan_sha256": sha256_file(bundle / "plan.json"),
            "code_manifest_sha256": sha256_file(bundle / "code_manifest.json"),
            "aliases_sha256": sha256_file(bundle / "aliases.json"),
            "bootstrap_sha256": sha256_file(bundle / "bootstrap.json"),
            "git_commit": commit,
            "protocol_revision": REVISION,
            "scope": "approved v2.1 fixed dev20 and Judge; stop before freeze/test",
            "new_inference_started": False,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, default=DEFAULT_PARENT)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if args.publish:
        publish(args.bundle.resolve())
    else:
        prepare(args.parent, args.bundle)
