"""Single-node, exclusive-output launcher. Reuse finished images; never resample unknown admissions."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import signal
import socket
import subprocess
import threading
import time

from samtok_benchmark.io import digest, sha256_file, write_json
from samtok_benchmark.external_refedit.cli import SCHEDULE, runtime_for
from .bundle import load_bundle, requests, smoke_sessions
from .data import immutable, read, write_bytes
from .worker import REPO, gpu_gate, source_identity, stages, verify_config, result_path


def plan_tasks(models, sessions, count_by_session, cards, smoke=False, estimate=None):
    """Scheduling estimates affect execution order only, never model inputs or scores."""
    tasks = []
    for model in models:
        timing = (estimate or {}).get(model, {})
        per_case = timing.get("generation_seconds_mean") or sum(
            SCHEDULE["estimated_case_seconds"][model].values()
        )
        count = sum(count_by_session[s] for s in sessions)
        shards = 1 if smoke else max(1, min(cards, len(sessions), round(count * per_case / 7200)))
        for shard in range(shards):
            selected = sessions[shard::shards]
            tasks.append(
                {
                    "model": model,
                    "shard": shard,
                    "shards": shards,
                    "session_ids": selected,
                    "estimated_seconds": sum(count_by_session[s] for s in selected) * per_case,
                }
            )
    return sorted(tasks, key=lambda t: (-t["estimated_seconds"], t["model"], t["shard"]))


def all_terminal(output, model, stage, items, wave):
    selected = [
        i for i in items if wave == -1 or (0 if i["mode"] == "independent" else i["turn"]) == wave
    ]
    return bool(selected) and all(
        result_path(output, model, stage, i["key"]).exists() for i in selected
    )


def launch(args):
    config = read(args.config)
    verify_config(config)
    index = load_bundle(args.bundle)
    cards = [int(x) for x in args.gpus.split(",")]
    if not cards or len(cards) != len(set(cards)) or any(c < 0 for c in cards):
        raise ValueError("GPU ids must be unique nonnegative integers")
    if not args.models or len(args.models) != len(set(args.models)):
        raise ValueError("Models must be unique")
    gpu_gate(config, cards)
    sessions = smoke_sessions(index) if args.smoke else index["sessions"]
    output = Path(args.output).resolve()
    formal = Path(config["formal_results_root"]).resolve()
    if args.smoke == output.is_relative_to(formal):
        raise ValueError(
            "Smoke output must be outside the formal root; formal output must be within it"
        )
    cache_root = Path(
        args.cache_dir or f"/tmp/ifbench-magicbrush-cache-{digest(str(output))[:12]}"
    ).resolve()
    if cache_root.is_relative_to(formal):
        raise ValueError(
            "Native debug working directories and caches must stay outside formal results"
        )
    estimate = read(args.estimate) if args.estimate else None
    if not args.smoke:
        if not estimate or not estimate["all_methods_smoke_passed"]:
            raise ValueError(
                "Formal execution requires measured successful smoke tests for all eight methods"
            )
        if (
            estimate["source_code"] != source_identity()
            or estimate["bundle_digest"] != index["digest"]
        ):
            raise ValueError("Smoke and formal generation identities differ")
        hours = estimate["total_gpu_hours_estimate"] / len(cards)
        if socket.gethostname() == config["local_gpu_policy"]["restricted_host"] and hours > 8:
            raise ValueError(
                f"Estimated {hours:.1f} h exceeds local 8 h cap; use the single-node ARNOLD entry"
            )
    output.mkdir(parents=True, exist_ok=True)
    lock = (output / "LAUNCH.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    immutable(output / "CONFIG.json", config)
    identity = source_identity()
    plan = {
        "schema": "magicbrush.run.v1",
        "scope": "smoke" if args.smoke else "full",
        "bundle": str(Path(args.bundle).resolve()),
        "bundle_digest": index["digest"],
        "config": str(output / "CONFIG.json"),
        "config_digest": digest(config),
        "session_ids": sessions,
        "models": args.models,
        "source_code": identity,
        "seed": 42,
    }
    immutable(output / "RUN.json", plan)
    for relative, sha in identity.items():
        saved = output / "source_snapshot" / relative
        write_bytes(saved, (REPO / relative).read_bytes())
        if sha256_file(saved) != sha:
            raise ValueError("Source snapshot changed")
    attempt = output / "attempts" / args.attempt
    attempt.mkdir(parents=True, exist_ok=False)
    items = requests(index, sessions, args.smoke)
    counts = {sid: sum(i["session_id"] == sid for i in items) for sid in sessions}
    timing = {r["model"]: r for r in estimate["methods"]} if estimate else None
    tasks = plan_tasks(args.models, sessions, counts, len(cards), args.smoke, timing)
    immutable(
        attempt / "TASKS.json",
        {"gpus": cards, "tasks": tasks, "started": datetime.now(timezone.utc).isoformat()},
    )
    queue, history, children = list(tasks), [], {}
    guard, stopping = threading.Lock(), threading.Event()

    def stop(signum, frame):
        stopping.set()
        with guard:
            pids = list(children.values())
        for child in pids:
            if child.poll() is None:
                child.send_signal(signal.SIGUSR1)

    signal.signal(signal.SIGUSR1, stop)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def run_task(card, task):
        model = task["model"]
        subset = requests(index, task["session_ids"], args.smoke)
        waves = [-1] if len(stages(model)) == 1 else [0, 2, 3]
        for wave in waves:
            for stage in stages(model):
                if stopping.is_set():
                    return
                if not any(
                    wave == -1 or (0 if i["mode"] == "independent" else i["turn"]) == wave
                    for i in subset
                ):
                    continue
                # Finished stages are already bound by RUN/source snapshots. Reports reverify receipt/output hashes.
                if all_terminal(output, model, stage, subset, wave):
                    continue
                deadline = time.monotonic() + 1800
                while not stopping.is_set():
                    try:
                        gpu_gate(config, [card])
                        break
                    except ValueError as error:
                        if "occupied" not in str(error) or time.monotonic() >= deadline:
                            raise
                        # NVML can lag a worker's exit; a new unrelated job may also occupy the card.
                        # Wait without signaling it, and recheck before importing the next model.
                        stopping.wait(10)
                if stopping.is_set():
                    return
                runtime = config["runtime"][runtime_for(model, stage)]
                name = f"{model}-{stage}-{task['shard']}of{task['shards']}-wave{wave}"
                work = cache_root / "work" / args.attempt / name
                work.mkdir(parents=True)
                environment = dict(
                    os.environ,
                    CUDA_DEVICE_ORDER="PCI_BUS_ID",
                    CUDA_VISIBLE_DEVICES=str(card),
                    PYTHONNOUSERSITE="1",
                    PYTHONDONTWRITEBYTECODE="1",
                    PYTHONUNBUFFERED="1",
                    OMP_NUM_THREADS="4",
                    TOKENIZERS_PARALLELISM="false",
                    HF_HUB_OFFLINE="1",
                    TRANSFORMERS_OFFLINE="1",
                    MASTER_PORT=str(42000 + card),
                )
                for key in [
                    "PYTHONPATH",
                    "PYTHONHOME",
                    "PYTHONSTARTUP",
                    "LD_PRELOAD",
                    "IFBENCH_NATIVE_SOURCES",
                ]:
                    environment.pop(key, None)
                cache = cache_root / model / str(card)
                environment["TORCHINDUCTOR_CACHE_DIR"] = str(cache / "inductor")
                environment["TRITON_CACHE_DIR"] = str(cache / "triton")
                command = [
                    runtime,
                    "-I",
                    "-B",
                    str(REPO / "scripts/magicbrush.py"),
                    "worker",
                    "--bundle",
                    plan["bundle"],
                    "--config",
                    plan["config"],
                    "--output",
                    str(output),
                    "--model",
                    model,
                    "--stage",
                    stage,
                    "--wave",
                    str(wave),
                    "--sessions",
                    *task["session_ids"],
                ]
                if args.smoke:
                    command.append("--smoke")
                tick = time.monotonic()
                print(f"GPU {card}: start {name}", flush=True)
                with (attempt / (name + ".log")).open("x") as log:
                    process = subprocess.Popen(
                        command, env=environment, cwd=work, stdout=log, stderr=subprocess.STDOUT
                    )
                    with guard:
                        children[card] = process
                        write_json(
                            attempt / "ACTIVE.json", {str(c): p.pid for c, p in children.items()}
                        )
                    code = process.wait()
                with guard:
                    children.pop(card, None)
                    history.append(
                        {
                            "gpu": card,
                            "task": name,
                            "returncode": code,
                            "wall_seconds": time.monotonic() - tick,
                            "pid": process.pid,
                        }
                    )
                    write_json(attempt / "HISTORY.json", history)
                    write_json(
                        attempt / "ACTIVE.json", {str(c): p.pid for c, p in children.items()}
                    )
                print(f"GPU {card}: finished {name}; exit={code}", flush=True)
                if code:
                    # Don't load another editor after a failed/unknown prerequisite stage.
                    return

    def lane(card):
        while not stopping.is_set():
            with guard:
                if not queue:
                    return
                task = queue.pop(0)
            run_task(card, task)

    try:
        with ThreadPoolExecutor(max_workers=len(cards)) as pool:
            list(pool.map(lane, cards))
    finally:
        lock.close()
    result = {
        "stopped": stopping.is_set(),
        "task_processes": len(history),
        "failed_processes": sum(r["returncode"] != 0 for r in history),
        "remaining_tasks": len(queue),
    }
    immutable(attempt / "DONE.json", result)
    return result
