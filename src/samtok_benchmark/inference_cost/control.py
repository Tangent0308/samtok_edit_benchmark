"""Foreground eight-GPU coordinator; one homogeneous method/stage per wave."""

from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time

from .common import (
    check_idle,
    gpu_snapshot,
    identity,
    jobs,
    load_plan,
    read,
    read_status,
    result_dir,
    save,
    sha,
    stages,
    terminal,
)


def run(plan, output, runtime, attempt, validate_only=False, smoke_only=False):
    profile = load_plan(plan)
    root, rt = Path(output), read(runtime)
    if smoke_only:
        root = root / "smoke"
    if not re.fullmatch(r"[A-Za-z0-9_-]+", attempt):
        raise ValueError("Unsafe attempt ID")
    root.mkdir(parents=True, exist_ok=True)
    attempt_root = root / "attempts" / attempt
    attempt_root.mkdir(parents=True, exist_ok=False)
    with (root / "controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        save(root / "PLAN_BINDING.json", {"digest": profile["digest"]}, immutable=True)
        for p, expected in profile["assets"].items():
            if sha(p) != expected:
                raise ValueError(f"Frozen input changed: {p}")
        for name, python in rt["python"].items():
            if not Path(python).is_file():
                raise FileNotFoundError(f"Missing {name} runtime: {python}")
        snapshot = gpu_snapshot()
        check_idle(snapshot)
        save(
            attempt_root / "PREFLIGHT.json",
            {
                "plan_digest": profile["digest"],
                "gpu": snapshot,
                "host": socket.gethostname(),
                "cpu_count": os.cpu_count(),
                "runtime": rt,
                "validate_only": validate_only,
            },
        )
        state = {
            "attempt": attempt,
            "host": socket.gethostname(),
            "plan_digest": profile["digest"],
            "status": "validated",
            "started_utc": datetime.now(timezone.utc).isoformat(),
        }

        def progress(**fields):
            state.update(fields, updated_utc=datetime.now(timezone.utc).isoformat())
            save(root / "PROGRESS.json", state)

        progress()
        if validate_only:
            return
        stopped = False

        def stopping(*args):
            nonlocal stopped
            stopped = True

        signal.signal(signal.SIGUSR1, stopping)
        signal.signal(signal.SIGTERM, stopping)
        script = Path(__file__).resolve().parents[3] / "scripts/inference_cost.py"
        waves = [
            (m, st, stage)
            for m in profile["models"]
            for st in profile["settings"]
            for stage in stages(m)
        ]
        try:
            for number, (model, setting, stage) in enumerate(waves, 1):
                if stopped:
                    progress(status="stopped")
                    return
                phase = attempt_root / f"{number:02d}-{model}-{setting}-{stage}"
                phase.mkdir()
                # Completed phases are read once and skipped without loading models.
                all_done = all(
                    terminal(
                        result_dir(root, model, setting, stage, r["case_id"], rep) / "result.json",
                        identity(profile, model, setting, stage, r["case_id"], rep),
                    )
                    for gpu in range(8)
                    for r, rep in list(jobs(profile, model, setting, gpu))[
                        : 1 if smoke_only else None
                    ]
                )
                if all_done:
                    progress(
                        status="running",
                        wave=number,
                        waves=len(waves),
                        phase=phase.name,
                        phase_status="cached",
                    )
                    continue
                progress(
                    status="running",
                    wave=number,
                    waves=len(waves),
                    phase=phase.name,
                    phase_status="loading",
                    workers={},
                )
                processes, streams = [], []
                name = (
                    "pass1"
                    if model == "sitedit" and stage == "tokens"
                    else "v4"
                    if model == "sitedit"
                    else "generation"
                )
                for gpu in range(8):
                    env = os.environ.copy()
                    env.update(
                        CUDA_VISIBLE_DEVICES=str(gpu),
                        PYTHONNOUSERSITE="1",
                        IFBENCH_COST_METHOD=rt["method_source"],
                        PYTHONDONTWRITEBYTECODE="1",
                        TOKENIZERS_PARALLELISM="false",
                        TQDM_DISABLE="1",
                        OMP_NUM_THREADS="4",
                        MKL_NUM_THREADS="4",
                        HF_HUB_OFFLINE="1",
                        TRANSFORMERS_OFFLINE="1",
                        TORCHINDUCTOR_CACHE_DIR=str(Path(rt["local_root"]) / "inductor" / str(gpu)),
                        TRITON_CACHE_DIR=str(Path(rt["local_root"]) / "triton" / str(gpu)),
                    )
                    env.pop("IFBENCH_NATIVE_SOURCES", None)
                    args = [
                        rt["python"][name],
                        "-B",
                        str(script),
                        "worker",
                        "--plan",
                        str(plan),
                        "--output",
                        str(root),
                        "--phase-root",
                        str(phase),
                        "--model",
                        model,
                        "--setting",
                        setting,
                        "--stage",
                        stage,
                        "--shard",
                        str(gpu),
                    ]
                    if smoke_only:
                        args.append("--smoke")
                    stream = (phase / f"gpu-{gpu}.log").open("w")
                    streams.append(stream)
                    processes.append(
                        subprocess.Popen(args, env=env, stdout=stream, stderr=subprocess.STDOUT)
                    )
                start, go, workers = time.monotonic(), False, {}
                try:
                    while True:
                        for gpu in range(8):
                            p = phase / f"worker-{gpu}.json"
                            latest = read_status(p, workers.get(str(gpu)))
                            if latest:
                                workers[str(gpu)] = latest
                        finished = sum(
                            w.get(k, 0)
                            for w in workers.values()
                            for k in ("completed", "failed", "blocked", "cached")
                        )
                        total = sum(
                            len(
                                list(jobs(profile, model, setting, gpu))[
                                    : 1 if smoke_only else None
                                ]
                            )
                            for gpu in range(8)
                        )
                        estimates = []
                        for gpu, w in workers.items():
                            needed = len(
                                list(jobs(profile, model, setting, int(gpu)))[
                                    : 1 if smoke_only else None
                                ]
                            )
                            remaining = max(
                                0,
                                needed
                                - sum(
                                    w.get(k, 0)
                                    for k in ("completed", "failed", "blocked", "cached")
                                ),
                            )
                            if w.get("last_native_seconds") is not None:
                                estimates.append(remaining * w["last_native_seconds"])
                        progress(
                            workers=workers,
                            phase_status="measuring" if go else "loading_or_warmup",
                            phase_elapsed_seconds=time.monotonic() - start,
                            phase_measurements_terminal=finished,
                            phase_measurements_total=total,
                            estimated_current_phase_seconds_left=max(estimates)
                            if len(estimates) == 8
                            else None,
                            eta_scope="Current stage only; loading, subsequent methods and report not estimated.",
                        )
                        exits = [p.poll() for p in processes]
                        if any(code not in (None, 0) for code in exits):
                            raise RuntimeError(f"Worker failed in {phase}; inspect gpu logs")
                        if (
                            not go
                            and len(workers) == 8
                            and all(w["status"] in {"ready", "done"} for w in workers.values())
                        ):
                            save(
                                phase / "GO.json",
                                {
                                    "released": time.time(),
                                    "loaded_workers": sum(
                                        w["status"] == "ready" for w in workers.values()
                                    ),
                                    "already_terminal_workers": sum(
                                        w["status"] == "done" for w in workers.values()
                                    ),
                                },
                                immutable=True,
                            )
                            go = True
                        if all(code is not None for code in exits):
                            break
                        if stopped:
                            save(phase / "STOP.json", {"reason": "user_or_platform_signal"})
                            for p in processes:
                                if p.poll() is None:
                                    p.send_signal(signal.SIGUSR1)
                        if not go and time.monotonic() - start > 7200:
                            raise TimeoutError("Worker loading/warmup exceeded two hours")
                        snap = gpu_snapshot()
                        counts = {}
                        for process in snap["processes"]:
                            counts[process["uuid"]] = counts.get(process["uuid"], 0) + 1
                        if any(n > 1 for n in counts.values()):
                            raise RuntimeError(
                                "Another GPU process appeared; timings require isolation"
                            )
                        save(phase / "GPU_LATEST.json", snap)
                        time.sleep(10)
                except BaseException:
                    save(phase / "STOP.json", {"reason": "controller_error"})
                    for p in processes:
                        if p.poll() is None:
                            p.send_signal(signal.SIGUSR1)
                    deadline = time.monotonic() + 600
                    while any(p.poll() is None for p in processes) and time.monotonic() < deadline:
                        time.sleep(2)
                    for p in processes:
                        if p.poll() is None:
                            p.terminate()  # Only this coordinator's own child PID.
                    for p in processes:
                        try:
                            p.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            p.kill()
                            p.wait()
                    raise
                finally:
                    for stream in streams:
                        stream.close()
            from .report import report

            result = report(plan, root)
            progress(
                status="complete" if result["complete"] else "incomplete",
                report=str(root / "REPORT.json"),
            )
        except BaseException as error:
            progress(status="failed", error=repr(error))
            save(attempt_root / "FAILED.json", {"error": repr(error), "time": time.time()})
            raise
