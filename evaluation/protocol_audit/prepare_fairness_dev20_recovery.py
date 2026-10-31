"""Prepare the authorized 177-request Qwen2.1 placement repair and exact reuses."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

from samtok_benchmark.io import digest, sha256_file
from samtok_benchmark.ifbench.fairness_dev_plan import (
    load_plan, read, request_identity, verify_cache, verify_task,
)
from samtok_benchmark.ifbench.fairness_dev_recovery import recovered_parent, check_decode_oom
from samtok_benchmark.ifbench.fairness_dev_worker import binding, verify_existing
from evaluation.protocol_audit.prepare_fairness_dev20 import save
from evaluation.protocol_audit.prepare_fairness_dev20_revision import (
    REPO, attach_completed_cache, export_completed_judge, file_reference, publish, snapshot_repo,
)

BASE = Path("/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp")


def prepare(parent_bundle, judge_root, bundle):
    parent_bundle, judge_root, bundle = (
        p.resolve() for p in (parent_bundle, judge_root, bundle)
    )
    if bundle.exists() and any(bundle.iterdir()):
        raise ValueError("Use a new empty bundle; preserve every published or partial artifact")
    parent_path = parent_bundle / "plan.json"
    parent = load_plan(parent_path, helper_root=parent_bundle / "repo")
    plan = deepcopy(parent)
    plan.pop("digest")
    plan["repair_parent"] = {
        "kind": "generation-terminal-and-judge-recovered",
        "plan": file_reference(parent_path),
        "code_manifest": file_reference(parent_bundle / "code_manifest.json"),
        "recovery_started": file_reference(judge_root / "RECOVERY_STARTED.json"),
        "recovery_completed": file_reference(judge_root / "RECOVERY_COMPLETED.json"),
        "judge_binding": file_reference(judge_root / "judge/plan_binding.json"),
    }
    recovered_parent(plan)
    plan["previous_completed_ancestor"] = plan.pop("parent_run", None)
    plan["model_specifications"]["qwen21"]["execution"] = {
        "memory_policy": "model_cpu_offload"
    }
    plan["configuration_sha256"] = digest({
        "parent_configuration": parent["configuration_sha256"],
        "repair": "authorized Qwen21 resident to native model_cpu_offload placement",
    })
    bundle.mkdir(parents=True, exist_ok=True)
    save(bundle / "selection.json", read(parent["selection_path"]))
    save(bundle / "AUTHORIZATION.json", {
        "schema": parent["schema"],
        "user_instruction": "现在在本机，用你修复过的qwen2.1，跑qwen2.1，然后完成所有模型没完成的judge，如果有问题的你进行修复，形成新的结果+报告。开始。",
        "date": "2026-10-31",
        "dev20_and_judge_authorized": True,
        "fixed_configuration_approved": True,
        "test_authorized": False,
        "freeze_authorized": False,
        "quality_search": False,
        "seed": 42,
        "repair_terminal_qwen_decode_oom_only": True,
        "reuse_successful_resident_qwen_outputs_after_exact_input_check": True,
        "diagnostic_output_reuse": False,
        "preserve_original_attempts_and_costs": True,
        "changes": {"qwen21_memory_policy": "model_cpu_offload"},
    })
    for field, name in (("authorization", "AUTHORIZATION.json"), ("selection", "selection.json")):
        plan[field + "_path"] = str(bundle / name)
        plan[field + "_sha256"] = sha256_file(bundle / name)
    plan["results_root"] = str(bundle / "results")
    plan["case_manifest"] = str(bundle / "repo/data/v2_2.6.0/cases.jsonl")
    plan["cache_index"] = str(bundle / "cache/judge_index.json")
    helpers = set(plan["helper_sha256"]) | {
        "samtok_benchmark/ifbench/fairness_dev_recovery.py",
        "samtok_benchmark/ifbench/qwen21_memory.py",
    }
    plan["helper_sha256"] = {p: sha256_file(REPO / p) for p in sorted(helpers)}
    plan["tasks"] = []

    def prepare_task(old_task):
        request, _ = verify_task(parent, old_task)
        original = read(old_task["result_path"])
        verify_existing(original, binding(parent, old_task, "edit"))
        task = deepcopy(old_task)
        path = bundle / "requests" / task["key"] / "request.json"
        save(path, request)
        out = bundle / "results/runs" / task["model"] / "outputs" / task["setting"] / task["case_id"]
        planner = bundle / "results/runs" / task["model"] / "planners" / task["setting"] / task["case_id"]
        task.update(
            request_path=str(path), request_sha256=sha256_file(path),
            output_dir=str(out), result_path=str(out / "result.json"),
            planner_dir=str(planner), cache={}, cache_sha256={},
            scientific_digest=request_identity(plan, task["model"], request),
        )
        if task["model"] == "qwen21" and original["status"] != "generated":
            check_decode_oom(original, request["parameters"])
            task["repair_of"] = file_reference(old_task["result_path"])
        else:
            for stage in (["planner", "edit"] if task["model"] in {"replan", "mirage"} else ["edit"]):
                attach_completed_cache(bundle, parent, task, old_task, stage, kind="recovered-dev20")
        return task

    with ThreadPoolExecutor(max_workers=8) as pool:
        for task in pool.map(prepare_task, parent["tasks"]):
            plan["tasks"].append(task)
            if len(plan["tasks"]) % 200 == 0:
                print(f"Prepared {len(plan['tasks'])}/1400 unchanged requests.", flush=True)
    repaired = [t for t in plan["tasks"] if t.get("repair_of")]
    reuse = [t for t in plan["tasks"] if t.get("cache", {}).get("edit")]
    if len(repaired) != 177 or len(reuse) != 1223:
        raise ValueError("Repair scope differs from the authorized 177 OOMs / 1223 terminal reuses")
    snapshot_repo(bundle)
    for name in ("aliases.json", "bootstrap.json"):
        save(bundle / name, read(parent_bundle / name))
    _, count = export_completed_judge(parent_path, bundle, result_root=judge_root)
    plan["cache_index_sha256"] = sha256_file(bundle / "cache/judge_index.json")
    plan["digest"] = digest(plan)
    save(bundle / "plan.json", plan)
    loaded = load_plan(bundle / "plan.json")

    def verify(task):
        verify_task(loaded, task)
        for stage in task["cache"]:
            verify_cache(loaded, task, stage)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(verify, loaded["tasks"]))
    save(bundle / "PREPARATION.json", {
        "logical_requests": len(plan["tasks"]),
        "new_generation_requests": len(repaired),
        "new_generation_by_model": dict(Counter(t["model"] for t in repaired)),
        "repair_targets": [{"key": t["key"], **t["repair_of"]} for t in repaired],
        "reused_terminal_requests": len(reuse),
        "reused_qwen_resident_successes": sum(t["model"] == "qwen21" for t in reuse),
        "available_judge_cache_keys": count,
        "new_gpu_calls_during_preparation": 0,
        "diagnostic_outputs_included": False,
        "test_started": False,
        "frozen": False,
    })
    print(f"Validated {len(repaired)} repairs, {len(reuse)} terminal reuses, {count} Judge keys.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, default=BASE / "fairness-v21-dev20-20261030")
    parser.add_argument("--judge-root", type=Path, default=BASE / "fairness-v21-recovery-20261031/results")
    parser.add_argument("--bundle", type=Path, default=BASE / "fairness-v21-qwen-repaired-dev20-20261031")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if args.publish:
        publish(args.bundle.resolve())
    else:
        prepare(args.parent, args.judge_root, args.bundle)
