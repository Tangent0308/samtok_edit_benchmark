"""Foreground eight-GPU entry point: fixed dev generation, canonical Judge, report."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from samtok_benchmark.paths import repository_root, source_pythonpath
import signal
import socket
import statistics
import subprocess
import sys
import time

from samtok_benchmark.io import sha256_file, write_json
from .fairness_dev_plan import load_plan, read, verify_task, verify_cache, check_hash

PLANNERS = {"replan", "mirage"}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def verify_package(plan_path):
    bundle = Path(plan_path).resolve().parent
    ready = read(bundle / "READY.json")
    for name, key in [
        ("plan.json", "plan_sha256"),
        ("code_manifest.json", "code_manifest_sha256"),
        ("aliases.json", "aliases_sha256"),
        ("bootstrap.json", "bootstrap_sha256"),
    ]:
        check_hash(bundle / name, ready[key])
    repo = repository_root()
    manifest = read(bundle / "code_manifest.json")
    for relative, expected in manifest["files"].items():
        check_hash(repo / relative, expected)
    return bundle


def preflight(plan, plan_path, *, check_gpus=True):
    from .fairness_dev_judge import Cache

    # A preparation-host /tmp dependency must fail before any model is loaded,
    # rather than after all generation has completed on another machine.
    cache = Cache(plan["cache_index"], plan["judge_config"])
    if cache.index_sha256 != plan["cache_index_sha256"]:
        raise ValueError("Judge cache index changed before generation")
    judge_files = cache.verify_portable_files(Path(plan_path).resolve().parent)

    def inspect(task):
        verify_task(plan, task)
        for stage in task.get("cache", {}):
            verify_cache(plan, task, stage)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(inspect, plan["tasks"]))
    if check_gpus:
        data = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,name,memory.free", "--format=csv,noheader,nounits"],
            text=True,
        )
        rows = [s.split(",") for s in data.strip().splitlines()]
        if len(rows) != 8 or any("H100" not in r[1] or int(r[2]) < 70 * 1024 for r in rows):
            raise ValueError(
                "This entry requires eight H100 80GB GPUs, each with at least 70 GiB free"
            )
    return {
        "validated_tasks": len(plan["tasks"]),
        "generation_caches": sum("edit" in t["cache"] for t in plan["tasks"]),
        "planner_caches": sum("planner" in t["cache"] for t in plan["tasks"]),
        "plan_digest": plan["digest"],
        "new_inference_calls": 0,
        "judge_cache_files": judge_files,
        "checked_at": timestamp(),
    }


def snapshot(plan, phase=None):
    summary = {m: Counter() for m in plan["model_order"]}
    stage_times = []
    stage_left = 0
    for task in plan["tasks"]:
        path = Path(task["result_path"])
        result = read(path) if path.exists() else None
        summary[task["model"]][result["status"] if result else "pending"] += 1
        if result and result.get("reused"):
            summary[task["model"]]["reused"] += 1
        if phase and phase["model"] == task["model"]:
            stage_path = (
                Path(task["planner_dir"]) / "result.json" if phase["stage"] == "planner" else path
            )
            value = read(stage_path) if stage_path.exists() else None
            if value is None:
                stage_left += 1
            elif not value.get("reused") and value.get("wall_seconds", 0) > 0:
                stage_times.append(value["wall_seconds"])
    total = Counter()
    for counts in summary.values():
        total.update(counts)
    eta = (statistics.median(stage_times) * stage_left / 8) if len(stage_times) >= 4 else None
    judge_progress = Path(plan["results_root"]) / "judge/progress.json"
    return {
        "updated_at": timestamp(),
        "phase": phase,
        "models": {m: dict(v) for m, v in summary.items()},
        "generation": dict(total),
        "logical_requests": len(plan["tasks"]),
        "current_phase_eta_seconds_estimate": eta,
        "eta_basis": "median completed call time, remaining requests / 8; excludes future phases and reloads",
        "judge": read(judge_progress) if judge_progress.exists() else None,
        "test_started": False,
        "frozen": False,
    }


def print_progress(plan, phase=None):
    state = snapshot(plan, phase)
    root = Path(plan["results_root"])
    write_json(root / "progress.json", state)
    lines = [
        "# IF-Bench dev20 进度",
        "",
        f"更新：{state['updated_at']}",
        f"阶段：{phase or '统计/评分'}。仅dev；未冻结、未启动test。",
        "",
        "| 模型 | 已出图 | 失败 | 待完成 | 精确复用 |",
        "|---|---:|---:|---:|---:|",
    ]
    for model, counts in state["models"].items():
        failures = sum(v for k, v in counts.items() if k.startswith("failed"))
        lines.append(
            f"| {model} | {counts.get('generated', 0)} | {failures} | {counts.get('pending', 0)} | {counts.get('reused', 0)} |"
        )
    eta = state["current_phase_eta_seconds_estimate"]
    lines += [
        "",
        (
            "当前生成/规划阶段预计剩余约 %.1f 分钟（按已完成调用实测，不含后续模型和Judge）。"
            % (eta / 60)
        )
        if eta is not None
        else "当前阶段ETA：尚无足够本轮完成记录。",
        "",
        f"Judge实时记录：{root}/judge/progress.json",
        f"统计报告：{root}/report/REPORT.md",
        "",
    ]
    (root / "PROGRESS.md").write_text("\n".join(lines))
    print(json.dumps(state, ensure_ascii=False), flush=True)
    return state


def run_processes(commands, plan, phase, receipt_dir):
    children = []
    logs = []
    tick = time.monotonic()
    try:
        for index, (command, environment) in enumerate(commands):
            log_path = receipt_dir / f"worker-{index}.log"
            log = log_path.open("a")
            logs.append(log)
            child = subprocess.Popen(
                command,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            children.append(child)
        write_json(
            receipt_dir / "children.json",
            [
                {
                    "pid": p.pid,
                    "command": commands[i][0],
                    "log": str(receipt_dir / f"worker-{i}.log"),
                }
                for i, p in enumerate(children)
            ],
        )
        last = 0
        while any(p.poll() is None for p in children):
            if time.monotonic() - last >= 30:
                print_progress(plan, phase)
                last = time.monotonic()
            failures = [p.returncode for p in children if p.poll() not in (None, 0)]
            if failures:
                raise RuntimeError(
                    f"Worker exited with code {failures}; inspect {receipt_dir}. No automatic retry."
                )
            time.sleep(2)
        codes = [p.wait() for p in children]
        if any(codes):
            raise RuntimeError(f"Worker failed: {codes}; inspect {receipt_dir}")
        return {
            "status": "completed",
            "wall_seconds": time.monotonic() - tick,
            "return_codes": codes,
        }
    finally:
        # Only this controller's explicitly spawned process groups, never other GPU jobs.
        for p in children:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
        for p in children:
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
        for log in logs:
            log.close()


def execute(plan_path, *, validate_only=False):
    bundle = verify_package(plan_path)
    plan = load_plan(plan_path)
    root = Path(plan["results_root"])
    root.mkdir(parents=True, exist_ok=True)
    if (root / "COMPLETED.json").exists() and not validate_only:
        if read(root / "COMPLETED.json")["plan_digest"] != plan["digest"]:
            raise ValueError("Completion belongs to another plan")
        print(
            "This dev20 plan already completed. Existing outputs and scores retained; no new calls.",
            flush=True,
        )
        return
    receipt = preflight(plan, plan_path, check_gpus=not validate_only)
    print(json.dumps({"preflight": receipt}), flush=True)
    if validate_only:
        return receipt
    generation_python = os.environ.get("IFBENCH_GENERATION_PYTHON", sys.executable)
    judge_python = os.environ.get("IFBENCH_JUDGE_PYTHON")
    if not judge_python:
        raise ValueError(
            "Launch through start.sh so the separate canonical Judge runtime is verified"
        )
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "0,1,2,3,4,5,6,7").split(",")
    if len(visible) != 8:
        raise ValueError("Eight CUDA_VISIBLE_DEVICES are required")
    claim = root / "ACTIVE"
    try:
        claim.mkdir()
    except FileExistsError:
        raise RuntimeError(
            f"Existing active/crashed controller claim: {claim}. Do not launch a duplicate; inspect owner and unresolved attempts."
        )
    write_json(
        claim / "owner.json",
        {
            "hostname": socket.gethostname(),
            "pid": os.getpid(),
            "started_at": timestamp(),
            "plan_digest": plan["digest"],
        },
    )
    execution = root / "executions" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    execution.mkdir(parents=True)
    state = {
        "status": "running",
        "plan_digest": plan["digest"],
        "started_at": timestamp(),
        "phases": [],
        "test_started": False,
        "frozen": False,
        "code_manifest_sha256": sha256_file(bundle / "code_manifest.json"),
    }
    write_json(execution / "receipt.json", state)
    base_env = os.environ.copy()
    base_env["PYTHONPATH"] = source_pythonpath(bundle / "repo")
    base_env.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        TOKENIZERS_PARALLELISM="false",
        PYTHONUNBUFFERED="1",
        OMP_NUM_THREADS="4",
    )

    def terminate(signum, _frame):
        raise KeyboardInterrupt(
            f"Controller received signal {signum}; admitted attempts will not auto-retry"
        )

    signal.signal(signal.SIGTERM, terminate)
    started = time.monotonic()
    try:
        for model in plan["model_order"]:
            for stage in ["planner", "edit"] if model in PLANNERS else ["edit"]:
                phase = {"model": model, "stage": stage}
                phase_dir = execution / f"{model}-{stage}"
                phase_dir.mkdir()
                commands = []
                for shard, gpu in enumerate(visible):
                    env = base_env.copy()
                    env["CUDA_VISIBLE_DEVICES"] = gpu
                    command = [
                        generation_python,
                        "-m",
                        "samtok_benchmark.ifbench.fairness_dev_worker",
                        "--plan",
                        str(plan_path),
                        "--model",
                        model,
                        "--stage",
                        stage,
                        "--shard",
                        str(shard),
                        "--shards",
                        "8",
                    ]
                    commands.append((command, env))
                result = run_processes(commands, plan, phase, phase_dir)
                state["phases"].append({**phase, **result})
                write_json(execution / "receipt.json", state)
        if print_progress(plan)["generation"].get("pending", 0):
            raise RuntimeError("Generation phases exited with unattempted requests")
        phase_dir = execution / "canonical-judge"
        phase_dir.mkdir()
        command = [
            judge_python,
            "-m",
            "samtok_benchmark.ifbench.fairness_dev_judge",
            "--plan",
            str(plan_path),
        ]
        result = run_processes(
            [(command, base_env)], plan, {"model": "all", "stage": "judge"}, phase_dir
        )
        state["phases"].append({"stage": "judge", **result})
        command = [
            judge_python,
            "-m",
            "samtok_benchmark.ifbench.fairness_dev_report",
            "--plan",
            str(plan_path),
        ]
        subprocess.run(command, env=base_env, check=True)
        state.update(
            status="completed-awaiting-freeze-review",
            ended_at=timestamp(),
            wall_seconds=time.monotonic() - started,
        )
        write_json(execution / "receipt.json", state)
        write_json(root / "COMPLETED.json", state)
        write_json(
            root / "REVIEW_REQUIRED.json",
            {
                "plan_digest": plan["digest"],
                "report": str(root / "report/REPORT.md"),
                "reason": "User-required stop after fixed dev20 results, before freeze/test",
                "test_started": False,
                "frozen": False,
            },
        )
        print_progress(plan)
        (claim / "owner.json").unlink()
        claim.rmdir()
        print(
            f"Dev20 completed. Review {root}/report/REPORT.md. Stopped before freeze/test.",
            flush=True,
        )
    except BaseException as error:
        state.update(
            status="stopped-with-error",
            error=repr(error),
            ended_at=timestamp(),
            wall_seconds=time.monotonic() - started,
        )
        write_json(execution / "receipt.json", state)
        write_json(root / "ERROR.json", state)
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--validate-only", action="store_true")
    p.add_argument("--status", action="store_true")
    a = p.parse_args()
    if a.status:
        print(json.dumps(snapshot(load_plan(a.plan)), ensure_ascii=False, indent=2))
    else:
        execute(a.plan.resolve(), validate_only=a.validate_only)


if __name__ == "__main__":
    main()
