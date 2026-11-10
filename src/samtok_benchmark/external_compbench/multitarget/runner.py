"""At most four idle local GPUs; fixed smoke then immutable correction and CPU metrics."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import threading
import time

from samtok_benchmark.external_full.coordination import atomic
from samtok_benchmark.external_refedit.data import immutable, read
from .outcomes import smoke_gate, summarize
from .plan import load


def gpu_available(gpu):
    text = subprocess.check_output(
        [
            "nvidia-smi",
            f"--id={gpu}",
            "--query-gpu=memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        timeout=20,
    )
    used, total = map(int, text.strip().split(","))
    return used <= 2300 and total - used >= 70000, used


def environment(config, repo, gpu, scratch):
    method = Path(config["paths"]["sitedit_source"])
    env = dict(
        os.environ,
        CUDA_VISIBLE_DEVICES=gpu,
        CUDA_DEVICE_ORDER="PCI_BUS_ID",
        PYTHONPATH=os.pathsep.join(
            map(
                str,
                [
                    repo / "src",
                    method / "src",
                    method / "third_party/diffsynth",
                    method / "third_party",
                ],
            )
        ),
        PYTHONNOUSERSITE="1",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUNBUFFERED="1",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        TOKENIZERS_PARALLELISM="false",
        OMP_NUM_THREADS="4",
        MASTER_PORT=str(42000 + int(gpu or 0)),
        TORCHINDUCTOR_CACHE_DIR=str(scratch / "inductor"),
        TRITON_CACHE_DIR=str(scratch / "triton"),
    )
    for key in [
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "LD_PRELOAD",
        "IFBENCH_NATIVE_SOURCES",
        "RANK",
        "LOCAL_RANK",
        "WORLD_SIZE",
        "LOCAL_WORLD_SIZE",
        "MASTER_ADDR",
    ]:
        env.pop(key, None)
    return env


def run(control, attempt, scratch_root, gpus=("4", "5", "6", "7")):
    if not gpus or len(set(gpus)) != len(gpus) or set(gpus) - {"4", "5", "6", "7"}:
        raise ValueError("Use at most the four authorized idle GPUs 4–7")
    if not attempt.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Invalid attempt")
    control, scratch_root = Path(control).resolve(), Path(scratch_root).resolve()
    plan, config = load(control)
    repo = Path(__file__).parents[4]
    results = Path(plan["results_root"])
    logs = control / "attempts" / attempt
    logs.mkdir(parents=True, exist_ok=False)
    lease = control / "RUN.lock"
    lease.mkdir()
    owner = {
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "attempt": attempt,
        "plan_digest": plan["digest"],
        "gpus": list(gpus),
    }
    immutable(lease / "OWNER.json", owner)
    immutable(logs / "OWNER.json", owner)
    active, lock, stop = {}, threading.RLock(), threading.Event()
    status = {"phase": "starting", **owner, "expected": len(plan["case_ids"]), "stages": {}}

    def update(**kwargs):
        with lock:
            status.update(
                kwargs,
                updated_utc=datetime.now(timezone.utc).isoformat(),
                active={k: v.pid for k, v in active.items()},
            )
            atomic(control / "STATUS.json", status)

    def halt(signum, frame):
        stop.set()
        with lock:
            for child in active.values():
                if child.poll() is None:
                    child.send_signal(signal.SIGUSR1)

    old_signals = {
        s: signal.signal(s, halt) for s in (signal.SIGTERM, signal.SIGINT, signal.SIGUSR1)
    }

    def wait_gpu(gpu, label):
        while not stop.is_set():
            ready, used = gpu_available(gpu)
            if ready:
                return
            with lock:
                status["stages"][label] = {
                    "state": "waiting_for_idle_gpu",
                    "gpu": gpu,
                    "memory_used_mib": used,
                }
            update()
            stop.wait(30)
        raise RuntimeError("Stopped while waiting for an idle GPU")

    def launch(stage, ids, gpu, root, label):
        if stop.is_set():
            raise RuntimeError("Run was stopped")
        is_score = stage == "score"
        terminal_dir = root / ("scores" if is_score else f"run/sitedit/{stage}")
        if not is_score and any(not (terminal_dir / c / "result.json").exists() for c in ids):
            wait_gpu(gpu, label)
        runtime = config["runtime"][
            "metrics" if is_score else "pass1" if stage == "tokens" else "v4"
        ]
        scratch = scratch_root / attempt / label
        scratch.mkdir(parents=True, exist_ok=True)
        env = environment(config, repo, "" if is_score else gpu, scratch)
        command = [
            runtime,
            "-u",
            str(repo / "scripts/compbench_multitarget.py"),
            stage,
            "--control",
            str(control),
            "--output",
            str(root / ("scores" if is_score else "run")),
            "--case-ids",
            *ids,
        ]
        if is_score:
            command += ["--run", str(root / "run")]
        immutable(
            logs / f"{label}.command.json", {"command": command, "gpu": None if is_score else gpu}
        )
        tick = time.monotonic()
        with (logs / f"{label}.log").open("x") as stream:
            child = subprocess.Popen(
                command, env=env, cwd=scratch, stdout=stream, stderr=subprocess.STDOUT
            )
            with lock:
                active[label] = child
            while True:
                code = child.poll()
                completed = failed = 0
                for cid in ids:
                    path = (
                        root / "scores/sitedit" / cid / "local.json"
                        if is_score
                        else root / "run/sitedit" / stage / cid / "result.json"
                    )
                    try:
                        state = read(path)["status"]
                        completed += state == "completed"
                        failed += state != "completed"
                    except (FileNotFoundError, json.JSONDecodeError):
                        pass
                with lock:
                    status["stages"][label] = {
                        "state": "running" if code is None else "finished",
                        "gpu": None if is_score else gpu,
                        "expected": len(ids),
                        "completed": completed,
                        "failed": failed,
                        "returncode": code,
                        "seconds": time.monotonic() - tick,
                    }
                update()
                if code is not None:
                    break
                stop.wait(15)
                if stop.is_set() and child.poll() is None:
                    child.send_signal(signal.SIGUSR1)
                    time.sleep(2)
            with lock:
                del active[label]
        immutable(
            logs / f"{label}.exit.json", {"returncode": code, "seconds": time.monotonic() - tick}
        )
        if code:
            raise RuntimeError(
                f"{label} stopped with exit code {code}; inspect its immutable records"
            )

    def smoke():
        ids = read(control / "SMOKE.json")["case_ids"]
        root = scratch_root / "smoke"
        update(phase="smoke_waiting_for_idle_gpu")
        gpu = None
        while gpu is None and not stop.is_set():
            for candidate in gpus:
                ready, _ = gpu_available(candidate)
                if ready:
                    gpu = candidate
                    break
            if gpu is None:
                update()
                print(
                    "Waiting for an idle GPU among 4–7; existing processes are untouched.",
                    flush=True,
                )
                stop.wait(30)
        if gpu is None:
            raise RuntimeError("Stopped before smoke")
        update(phase="smoke")
        for stage in ("tokens", "edit", "score"):
            launch(stage, ids, gpu, root, f"smoke-{stage}")
        # Engineering faults stop here; a recorded native method failure does not block the
        # fixed cohort. Timing/memory come from completed requests only.
        summary = summarize(plan, root / "run", root / "scores", ids)
        update(smoke_outcomes={k: summary[k] for k in ("expected", "counts")})
        smoke_gate(summary)
        evidence = {
            "case_ids": ids,
            "smoke_root": str(root),
            "gpu": gpu,
            "completed": summary["completed"],
            "native_failures": summary["native_failures"],
            "engineering_failures": summary["engineering_failures"],
            "outcomes": summary["cases"],
            "inference_seconds": summary["inference_seconds"],
            "peak_reserved_bytes": summary["peak_reserved_bytes"],
        }
        mean_seconds = sum(evidence["inference_seconds"]) / len(evidence["inference_seconds"])
        evidence["formal_gpu_hours_estimate"] = mean_seconds * len(plan["case_ids"]) / 3600
        evidence["four_gpu_generation_hours_estimate"] = evidence[
            "formal_gpu_hours_estimate"
        ] / len(gpus)
        update(smoke=evidence)
        print(json.dumps({"smoke_completed": evidence}, ensure_ascii=False), flush=True)
        if evidence["four_gpu_generation_hours_estimate"] > 8:
            raise RuntimeError(
                "Measured correction exceeds the eight-hour local budget; formal inference not started"
            )
        immutable(control / "SMOKE_COMPLETED.json", evidence)

    try:
        update()
        if not (control / "SMOKE_COMPLETED.json").exists():
            smoke()
        update(phase="formal_waiting_or_running")

        def one_card(pair):
            rank, gpu = pair
            ids = plan["case_ids"][rank :: len(gpus)]
            try:
                for stage in ("tokens", "edit", "score"):
                    launch(stage, ids, gpu, results, f"gpu{gpu}-{stage}")
            except Exception:
                stop.set()
                raise

        with ThreadPoolExecutor(max_workers=len(gpus)) as pool:
            futures = [pool.submit(one_card, pair) for pair in enumerate(gpus)]
            for f in futures:
                f.result()
        audit = summarize(plan, results / "run", results / "scores")
        immutable(logs / "OUTCOMES.json", audit)
        update(
            phase="report",
            outcomes={k: audit[k] for k in ("expected", "counts")},
            native_failures=[i["case_id"] for i in audit["native_failures"]],
            engineering_failures=audit["engineering_failures"],
        )
        from .report import report

        merged = report(control, results, results / "reports" / attempt)
        from .preview import render

        preview = render(
            plan, results, "/opt/tiger/tanyue/visualization_tmp/CompBench_MultiTarget_20261110"
        )
        complete = all(g["complete"] for g in merged["rows"]["sitedit"]["groups"])
        update(
            phase=(
                "finished_with_engineering_failures"
                if audit["engineering_failures"]
                else "complete" if complete else "finished_with_missing_results"
            ),
            report=str(results / "reports" / attempt / "MERGED_REPORT.json"),
            preview=preview,
        )
        immutable(logs / "DONE.json", dict(status))
        return status
    except Exception as error:
        update(phase="stopped_or_failed", error=repr(error))
        raise
    finally:
        # Never terminate another user's process. Child workers finish their current
        # admitted request on SIGUSR1; an incomplete receipt is never auto-resampled.
        with lock:
            children = list(active.values())
        for child in children:
            if child.poll() is None:
                child.send_signal(signal.SIGUSR1)
                child.wait()
        immutable(logs / "RELEASED.json", owner)
        (lease / "OWNER.json").unlink()
        lease.rmdir()
        for s, handler in old_signals.items():
            signal.signal(s, handler)
