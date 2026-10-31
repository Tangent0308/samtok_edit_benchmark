"""Bounded native GPU engineering probe: two fixed dev sources, three settings."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import time

from samtok_benchmark.io import digest, read_jsonl, write_json
from samtok_benchmark.paths import repository_root
from . import canvas
from .fairness_dev_plan import MODELS, check_hash, read, verify_task, verify_cache
from .prepare_one_mp import PROBE_SCHEMA, PROBE_SETTINGS, selections

__all__ = ["load_plan", "verify_task", "verify_cache"]


def load_plan(path, *, helper_root=None):
    path = Path(path)
    plan = read(path)
    if plan.get("schema") != PROBE_SCHEMA or plan.get("digest") != digest(
        {k: v for k, v in plan.items() if k != "digest"}
    ):
        raise ValueError("Invalid 1MP probe identity")
    if (
        plan.get("canvas_policy") != canvas.POLICY
        or plan.get("seed") != 42
        or plan.get("quality_search") is not False
    ):
        raise ValueError("Changed 1MP probe policy")
    check_hash(plan["configuration_reference"], plan["configuration_reference_sha256"])
    config = read(plan["configuration_reference"])
    if (
        plan["model_specifications"] != config["model_specifications"]
        or plan["judge_config"] != config["judge_config"]
    ):
        raise ValueError("Changed model or Judge configuration")
    check_hash(plan["case_manifest"], plan["case_manifest_sha256"])
    cases = read_jsonl(plan["case_manifest"])
    ids, _ = selections(cases, config)
    if (
        plan["case_ids"] != ids
        or plan["settings"] != PROBE_SETTINGS
        or plan["model_order"] != MODELS
    ):
        raise ValueError("Probe may use only its fixed two dev sources and three settings")
    expected = {(m, s, c) for m in MODELS for s in PROBE_SETTINGS for c in ids}
    if (
        len(plan["tasks"]) != len(expected)
        or {(t["model"], t["setting"], t["case_id"]) for t in plan["tasks"]} != expected
    ):
        raise ValueError("Incomplete or duplicated probe coverage")
    check_hash(plan["authorization_path"], plan["authorization_sha256"])
    if read(plan["authorization_path"]).get("probe_authorized") is not True:
        raise ValueError("Probe authorization missing")
    root = Path(helper_root) if helper_root else repository_root()
    for relative, expected_sha in plan["helper_sha256"].items():
        check_hash(root / relative, expected_sha)
    if any(t["cache"] for t in plan["tasks"]):
        raise ValueError("New 1MP probe must not import generation caches")
    return plan


def summary(plan):
    from .fairness_dev_worker import binding, verify_existing

    counts, records = {}, []
    for task in plan["tasks"]:
        model = task["model"]
        counts.setdefault(model, {"generated": 0, "failed": 0, "pending": 0})
        p = Path(task["result_path"])
        if not p.exists():
            counts[model]["pending"] += 1
            continue
        result = read(p)
        verify_existing(result, binding(plan, task, "edit"))
        status = "generated" if result["status"] == "generated" else "failed"
        counts[model][status] += 1
        records.append(
            {
                "key": task["key"],
                "result": str(p),
                "status": result["status"],
                "raw_size": result.get("raw_size"),
                "input_size": result.get("input_size"),
                "wall_seconds": result.get("wall_seconds"),
                "error": result.get("error"),
            }
        )
    return {
        "plan_digest": plan["digest"],
        "models": counts,
        "records": records,
        "judge_calls": 0,
        "quality_scores": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def execute(path, *, plan_api=None, lanes=None):
    from .fairness_dev_run import run_processes

    path = Path(path).resolve()
    plan_api = plan_api or sys.modules[__name__]
    module_name = getattr(getattr(plan_api, "__spec__", None), "name", None) or plan_api.__name__
    plan = plan_api.load_plan(path)
    for task in plan["tasks"]:
        verify_task(plan, task)
    root = Path(plan["results_root"])
    root.mkdir(parents=True, exist_ok=True)
    claim = root / "ACTIVE"
    claim.mkdir()  # never overwrite an active or crashed controller claim
    write_json(claim / "owner.json", {"pid": os.getpid(), "plan_digest": plan["digest"]})
    receipt = root / "executions" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt.mkdir(parents=True)
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "0,1,2,3,4,5,6,7").split(",")
    if len(visible) != 8:
        raise ValueError("Probe requires eight visible GPUs")
    lanes = lanes or [
        (["qwen2511"], [0, 1]),
        (["qwen21"], [2, 3]),
        (["flux3", "mice", "flux2_klein9b"], [4]),
        (["replan"], [5]),
        (["mirage"], [6, 7]),
    ]
    env_base = dict(
        os.environ,
        PYTHONPATH=str(repository_root() / "src"),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        TOKENIZERS_PARALLELISM="false",
        PYTHONUNBUFFERED="1",
        OMP_NUM_THREADS="4",
    )

    def lane(models, gpus):
        for model in models:
            for stage in ["planner", "edit"] if model in {"replan", "mirage"} else ["edit"]:
                directory = receipt / f"{model}-{stage}"
                directory.mkdir()
                commands = []
                for shard, gpu in enumerate(gpus):
                    command = [
                        sys.executable,
                        "-m",
                        module_name,
                        "worker",
                        "--plan",
                        str(path),
                        "--model",
                        model,
                        "--stage",
                        stage,
                        "--shard",
                        str(shard),
                        "--shards",
                        str(len(gpus)),
                    ]
                    commands.append((command, dict(env_base, CUDA_VISIBLE_DEVICES=visible[gpu])))
                result = run_processes(
                    commands,
                    plan,
                    {"model": model, "stage": stage},
                    directory,
                    progress_callback=lambda *_: None,
                )
                write_json(directory / "receipt.json", result)

    tick = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(lanes)) as pool:
        pending = [pool.submit(lane, *item) for item in lanes]
        while pending:
            done, pending = wait(pending, timeout=20)
            for future in done:
                future.result()
            write_json(root / "progress.json", summary(plan))
    result = summary(plan)
    result.update(wall_seconds=time.monotonic() - tick, status="generation-validation-completed")
    write_json(root / "COMPLETED.json", result)
    (claim / "owner.json").unlink()
    claim.rmdir()
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["run", "worker", "status"])
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--model", choices=MODELS)
    p.add_argument("--stage", choices=["planner", "edit"])
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=1)
    a = p.parse_args()
    if a.action == "worker":
        from .fairness_dev_worker import run_worker

        run_worker(a.plan, a.model, a.stage, a.shard, a.shards, plan_api=sys.modules[__name__])
    elif a.action == "run":
        execute(a.plan)
    else:
        import json

        print(json.dumps(summary(load_plan(a.plan)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
