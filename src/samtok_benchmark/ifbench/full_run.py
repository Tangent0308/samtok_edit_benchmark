"""One foreground node: eight native workers, one TP8 Judge, then global aggregation."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import socket
import statistics
import sys
import time
import uuid

from samtok_benchmark.io import sha256_file, write_json
from samtok_benchmark.paths import source_pythonpath
from .full_plan import load_plan, node_tasks, verify_task, verify_cache
from .fairness_dev_plan import read, check_hash
from .fairness_dev_run import verify_package, run_processes, PLANNERS
from .fairness_dev_judge import Cache


def stamp():
    return datetime.now(timezone.utc).isoformat()


def claim_node(directory, plan_digest):
    claim = directory / "ACTIVE"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        claim.mkdir()
    except FileExistsError as error:
        raise RuntimeError(
            f"Node already active or crashed: {claim}; inspect owner before releasing a stale claim"
        ) from error
    owner = {
        "token": uuid.uuid4().hex,
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "started_at": stamp(),
        "plan_digest": plan_digest,
    }
    write_json(claim / "owner.json", owner)
    return owner


def release_node(directory, owner):
    claim = directory / "ACTIVE"
    if read(claim / "owner.json") != owner:
        raise RuntimeError("Refusing to release another controller claim")
    (claim / "owner.json").unlink()
    claim.rmdir()


def preflight(plan, bundle, node, workers=8):
    tasks = node_tasks(plan, node)
    cache = Cache(plan["cache_index"], plan["judge_config"])
    if cache.index_sha256 != plan["cache_index_sha256"]:
        raise ValueError("Judge cache changed")
    portable = cache.verify_portable_files(bundle)

    def verify(t):
        verify_task(plan, t)
        if t.get("text_preflight"):
            check_hash(t["text_preflight"]["path"], t["text_preflight"]["sha256"])
        for stage in t["cache"]:
            verify_cache(plan, t, stage)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(verify, tasks))
    return {
        "node": node,
        "tasks": len(tasks),
        "sources": len(plan["node_assignments"][str(node)]),
        "verified_generation_caches": sum("edit" in t["cache"] for t in tasks),
        "judge_cache_files": portable,
        "new_inference_calls": 0,
        "at": stamp(),
    }


def progress(plan, node, phase, state):
    """Read eight small worker counters, not every shared result on each heartbeat."""
    root = Path(plan["results_root"]) / "nodes" / f"node-{node}"
    states, samples = [], []
    if phase and phase["stage"] in ("planner", "edit"):
        for shard in range(8):
            parent = root / "workers" / phase["model"] / phase["stage"] / f"shard-{shard}-of-8"
            files = sorted(parent.glob("*/status.json"))
            if files:
                worker = read(files[-1])
                states.append(worker)
                if worker.get("last_task"):
                    model, setting, cid = worker["last_task"].split("/")
                    stage_dir = "planners" if phase["stage"] == "planner" else "outputs"
                    path = (
                        Path(plan["results_root"])
                        / "runs"
                        / model
                        / stage_dir
                        / setting
                        / cid
                        / "result.json"
                    )
                    if path.exists():
                        r = read(path)
                        if not r.get("reused") and r.get("wall_seconds", 0) > 0:
                            samples.append(r["wall_seconds"])
    done = sum(w.get("completed", 0) + w.get("already_terminal", 0) for w in states)
    total = (
        len(plan["node_assignments"][str(node)]) * len(plan["settings"])
        if phase and phase["model"] != "all"
        else None
    )
    eta = (
        statistics.median(samples) * max(0, total - done) / 8
        if total is not None and len(samples) >= 4
        else None
    )
    judge = root / "judge/progress.json"
    result = {
        "node": node,
        "host": socket.gethostname(),
        "updated_at": stamp(),
        "status": state["status"],
        "plan_digest": plan["digest"],
        "phase": phase,
        "phase_terminal_requests": done,
        "phase_total_requests": total,
        "phase_worker_failures": sum(w.get("failed", 0) for w in states),
        "phase_eta_seconds_estimate": eta,
        "eta_scope": "current stage only; excludes later models/Judge/loading",
        "completed_phases": state["phases"],
        "judge": read(judge) if judge.exists() else None,
        "report_scope": "all-1084",
        "frozen": True,
    }
    write_json(root / "progress.json", result)
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("completed_phases", "judge")},
            ensure_ascii=False,
        ),
        flush=True,
    )
    return result


def execute(plan_path, node, validate_only=False):
    bundle = verify_package(plan_path)
    plan = load_plan(plan_path)
    tasks = node_tasks(plan, node)
    directory = Path(plan["results_root"]) / "nodes" / f"node-{node}"
    done = directory / "COMPLETED.json"
    if done.exists() and not validate_only:
        if read(done)["plan_digest"] != plan["digest"]:
            raise ValueError("Node completion belongs to another plan")
        print(f"Node {node} already completed; no new generation or Judge calls.", flush=True)
        from .full_report import aggregate_if_ready

        return aggregate_if_ready(bundle)
    if validate_only:
        receipt = preflight(plan, bundle, node)
        write_json(bundle / "validation" / f"node-{node}/requests.json", receipt)
        print(json.dumps(receipt), flush=True)
        return receipt
    if "IFBENCH_JUDGE_PYTHON" not in os.environ:
        raise RuntimeError(
            "Launch the published foreground start.sh to isolate generation/Judge runtimes"
        )
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "0,1,2,3,4,5,6,7").split(",")
    if len(visible) != 8 or len(set(visible)) != 8:
        raise ValueError("Exactly eight distinct visible GPUs required")
    owner = claim_node(directory, plan["digest"])
    execution = directory / "executions" / owner["token"]
    execution.mkdir(parents=True)
    state = {
        "execution_id": owner["token"],
        "node": node,
        "host": socket.gethostname(),
        "status": "running",
        "plan_digest": plan["digest"],
        "code_manifest_sha256": sha256_file(bundle / "code_manifest.json"),
        "started_at": stamp(),
        "phases": [],
    }
    write_json(execution / "receipt.json", state)
    started = time.monotonic()
    phase = None

    def terminate(signum, frame):
        raise KeyboardInterrupt(
            f"Signal {signum}; no admitted request will be retried automatically"
        )

    signal.signal(signal.SIGTERM, terminate)
    env = dict(
        os.environ,
        PYTHONPATH=source_pythonpath(bundle / "repo"),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        TOKENIZERS_PARALLELISM="false",
        PYTHONUNBUFFERED="1",
        OMP_NUM_THREADS="4",
    )

    def callback(p, ph):
        return progress(p, node, ph, state)

    try:
        receipt = preflight(plan, bundle, node)
        write_json(execution / "preflight.json", receipt)
        for model in plan["model_order"]:
            for stage in ["planner", "edit"] if model in PLANNERS else ["edit"]:
                phase = {"model": model, "stage": stage}
                phase_dir = execution / f"{model}-{stage}"
                phase_dir.mkdir()
                commands = []
                for shard, gpu in enumerate(visible):
                    command = [
                        os.environ.get("IFBENCH_GENERATION_PYTHON", sys.executable),
                        "-m",
                        "samtok_benchmark.ifbench.full_worker",
                        "--plan",
                        str(plan_path),
                        "--node",
                        str(node),
                        "--model",
                        model,
                        "--stage",
                        stage,
                        "--shard",
                        str(shard),
                        "--shards",
                        "8",
                    ]
                    commands.append((command, dict(env, CUDA_VISIBLE_DEVICES=gpu)))
                result = run_processes(commands, plan, phase, phase_dir, progress_callback=callback)
                state["phases"].append({**phase, **result})
                write_json(execution / "receipt.json", state)
        if any(not Path(t["result_path"]).exists() for t in tasks):
            raise RuntimeError("Generation workers exited with unattempted owned requests")
        phase = {"model": "all", "stage": "judge"}
        phase_dir = execution / "canonical-judge"
        phase_dir.mkdir()
        command = [
            os.environ["IFBENCH_JUDGE_PYTHON"],
            "-m",
            "samtok_benchmark.ifbench.full_judge",
            "--plan",
            str(plan_path),
            "--node",
            str(node),
        ]
        result = run_processes([(command, env)], plan, phase, phase_dir, progress_callback=callback)
        state["phases"].append({**phase, **result})
        # Recheck owned canonical records and export a checked merge receipt, without inference.
        from .full_report import verify_node

        verification = verify_node(plan_path, node)
        state.update(
            status="completed",
            ended_at=stamp(),
            wall_seconds=time.monotonic() - started,
            verification=verification,
        )
        write_json(execution / "receipt.json", state)
        write_json(done, state)
        if (directory / "ERROR.json").exists():
            (
                directory / "ERROR.json"
            ).unlink()  # original execution receipt remains immutable evidence
        progress(plan, node, None, state)
    except BaseException as error:
        state.update(
            status="stopped-with-error",
            error=repr(error),
            ended_at=stamp(),
            wall_seconds=time.monotonic() - started,
        )
        write_json(execution / "receipt.json", state)
        write_json(directory / "ERROR.json", state)
        progress(plan, node, phase, state)
        raise
    finally:
        # run_processes has joined/terminated only our children before this point.
        release_node(directory, owner)
    from .full_report import aggregate_if_ready

    return aggregate_if_ready(bundle)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", required=True, type=Path)
    p.add_argument("--node", required=True, type=int, choices=range(4))
    p.add_argument("--validate-only", action="store_true")
    a = p.parse_args()
    execute(a.plan.resolve(), a.node, a.validate_only)
