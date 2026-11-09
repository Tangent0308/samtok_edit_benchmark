"""Local eight-card queue with overlapping unchanged CPU metrics and owned-PID shutdown."""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import threading
import time
import uuid

from samtok_benchmark.external_full.data import read, immutable
from samtok_benchmark.external_full.worker import stages, source_identity
from samtok_benchmark.external_full.coordination import atomic
from samtok_benchmark.external_full.launch import select_cases
from samtok_benchmark.io import digest, sha256_file
from . import MODELS


def partition(index, case_ids, gpus):
    """Balance request counts while preserving each autoregressive chain."""
    groups = defaultdict(list)
    for row in select_cases(index, case_ids):
        if row["case_id"] in case_ids:
            groups[row["sequence_id"]].append(row)
    shards, counts = {g: [] for g in gpus}, dict.fromkeys(gpus, 0)
    for sid in sorted(groups, key=lambda k: (-len(groups[k]), k)):
        gpu = min(gpus, key=lambda g: (counts[g], int(g)))
        shards[gpu].extend(groups[sid])
        counts[gpu] += len(groups[sid])
    return shards


def run(control, attempt, gpus):
    if len(set(gpus)) != 8 or set(gpus) != set(map(str, range(8))):
        raise ValueError("This authorized validation uses exactly local GPUs 0–7")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", attempt):
        raise ValueError("Invalid attempt")
    control = Path(control).resolve()
    manifest = read(control / "PLAN.json")
    if manifest["digest"] != digest({k: v for k, v in manifest.items() if k != "digest"}):
        raise ValueError("Fixed validation plan changed")
    repo = Path(__file__).parents[3]
    if manifest["generation_source_identity"] != source_identity():
        raise ValueError("Frozen generation source changed")
    if any(
        sha256_file(repo / path) != sha for path, sha in manifest["orchestration_source"].items()
    ):
        raise ValueError("Committed validation scheduler changed")
    jobs = []
    for entry in manifest["benchmarks"]:
        path = Path(entry["selection"])
        selection = read(path)
        if sha256_file(path) != entry["selection_sha256"] or selection["digest"] != digest(
            {k: v for k, v in selection.items() if k != "digest"}
        ):
            raise ValueError("Fixed selection changed")
        if sha256_file(selection["configuration"]) != selection["configuration_sha256"]:
            raise ValueError("Validation configuration changed")
        jobs.append(selection)
    logs = control / "attempts" / attempt
    logs.mkdir(parents=True, exist_ok=False)
    lease = control / "LOCAL.lock"
    owner = {
        "attempt": attempt,
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "nonce": uuid.uuid4().hex,
        "plan_digest": manifest["digest"],
    }
    try:
        lease.mkdir()
    except FileExistsError:
        previous = read(lease / "OWNER.json")
        released = control / "attempts" / previous["attempt"] / "RELEASED.json"
        if not released.exists() or read(released) != previous:
            raise RuntimeError(
                "Previous local attempt has not released its workers; inspect before recovery"
            )
        lease.rename(logs / ("retired-" + previous["nonce"]))
        lease.mkdir()
    atomic(lease / "OWNER.json", owner)
    immutable(logs / "OWNER.json", owner)
    stop = threading.Event()
    lock = threading.RLock()
    active, progress = {}, {}
    started = time.monotonic()
    state = {
        "schema": "external.paired.progress.v1",
        "attempt": attempt,
        "phase": "preflight",
        "plan_digest": manifest["digest"],
        "pid": os.getpid(),
        "benchmarks": {
            s["benchmark"]: {
                "expected_per_model": len(s["case_ids"]),
                "generation_per_model": len(s["generation_case_ids"]),
            }
            for s in jobs
        },
    }

    def status():
        with lock:
            state.update(
                updated_utc=datetime.now(timezone.utc).isoformat(),
                elapsed_seconds=time.monotonic() - started,
                active={k: v.pid for k, v in active.items()},
                stages=dict(progress),
            )
            atomic(control / "STATUS.json", state)

    def halt(signum, frame):
        stop.set()
        with lock:
            for child in active.values():
                if child.poll() is None:
                    try:
                        child.send_signal(signal.SIGUSR1)
                    except ProcessLookupError:
                        pass

    previous_signals = {
        s: signal.signal(s, halt) for s in (signal.SIGINT, signal.SIGTERM, signal.SIGUSR1)
    }
    environment = dict(
        os.environ,
        PYTHONNOUSERSITE="1",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUNBUFFERED="1",
        OMP_NUM_THREADS="4",
        TOKENIZERS_PARALLELISM="false",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        CUDA_DEVICE_ORDER="PCI_BUS_ID",
    )
    for key in (
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "LD_PRELOAD",
        "IFBENCH_NATIVE_SOURCES",
        "RANK",
        "LOCAL_RANK",
        "WORLD_SIZE",
        "LOCAL_WORLD_SIZE",
        "MASTER_ADDR",
    ):
        environment.pop(key, None)

    def execute(label, command, env, info=None):
        if stop.is_set():
            raise RuntimeError("Validation stop requested")
        destination = logs / (label + ".log")
        tick, seen, offset, tail = time.monotonic(), set(), 0, ""
        info = dict(info or {})
        info.update(new_completed=0, new_failed=0, phase="starting")
        with lock:
            progress[label] = info
        print(f"START {label}", flush=True)
        try:
            with destination.open("x") as stream:
                child = subprocess.Popen(
                    command,
                    cwd=repo,
                    env=env,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                with lock:
                    active[label] = child
                    if stop.is_set():
                        child.send_signal(signal.SIGUSR1)
                immutable(logs / (label + ".pid.json"), {"pid": child.pid, "command": command})
                pattern = re.compile(
                    r"(?:sitedit|qwen21)/(?:tokens|edit)/([^:\n]+): (completed|failed|blocked_dependency) "
                )
                while True:
                    code = child.poll()
                    with destination.open(errors="replace") as reader:
                        reader.seek(offset)
                        text = tail + reader.read()
                        offset = reader.tell()
                    for cid, outcome in pattern.findall(text.replace("\r", "\n")):
                        if cid not in seen:
                            seen.add(cid)
                            info["new_completed" if outcome == "completed" else "new_failed"] += 1
                    tail = text[-2048:]
                    with lock:
                        info.update(
                            phase="running" if code is None else "terminal",
                            wall_seconds=time.monotonic() - tick,
                            returncode=code,
                        )
                    status()
                    if code is not None:
                        break
                    stop.wait(5) if not stop.is_set() else time.sleep(1)
                if code:
                    raise RuntimeError(f"{label} exited {code}; see {destination}")
        finally:
            if "child" in locals():
                if child.poll() is None:
                    child.send_signal(signal.SIGUSR1)
                    child.wait()
                with lock:
                    active.pop(label, None)
                immutable(
                    logs / (label + ".exit.json"),
                    {"returncode": child.returncode, "seconds": time.monotonic() - tick},
                )
        print(f"END {label}", flush=True)

    def generate(selection, model, gpu, rows):
        cfg = read(selection["configuration"])
        for wave in (0, 1):
            ids = [r["case_id"] for r in rows if (r["turn"] == 2) == bool(wave)]
            if not ids:
                continue
            for stage in stages(model):
                runtime = (
                    "pass1" if stage == "tokens" else "v4" if model == "sitedit" else "generation"
                )
                label = f"{selection['benchmark']}-{model}-gpu{gpu}-wave{wave}-{stage}"
                scratch = Path("/tmp/ifbench/external-validation") / attempt / label
                scratch.mkdir(parents=True, exist_ok=False)
                paths = [str(repo / "src")]
                if model == "sitedit":
                    method = Path(cfg["paths"]["sitedit_source"])
                    paths.extend(
                        str(method / p) for p in ("src", "third_party/diffsynth", "third_party")
                    )
                env = dict(
                    environment,
                    CUDA_VISIBLE_DEVICES=gpu,
                    PYTHONPATH=os.pathsep.join(paths),
                    MASTER_PORT=str(43000 + int(gpu)),
                    TORCHINDUCTOR_CACHE_DIR=str(scratch / "inductor"),
                    TRITON_CACHE_DIR=str(scratch / "triton"),
                )
                output = Path(selection["results_root"]) / "run"
                reused = sum((output / model / stage / cid / "result.json").exists() for cid in ids)
                command = [
                    cfg["runtime"][runtime],
                    "-u",
                    "-m",
                    "samtok_benchmark.external_pair.worker",
                    "--bundle",
                    selection["bundle"],
                    "--config-path",
                    selection["configuration"],
                    "--output",
                    str(output),
                    "--model",
                    model,
                    "--stage",
                    stage,
                    "--case-ids",
                    *ids,
                ]
                execute(
                    label,
                    command,
                    env,
                    {
                        "benchmark": selection["benchmark"],
                        "model": model,
                        "stage": stage,
                        "gpu": gpu,
                        "expected": len(ids),
                        "terminal_on_entry": reused,
                    },
                )

    def scoring(selection, model):
        cfg = read(selection["configuration"])
        base = Path(selection["results_root"])
        env = dict(
            environment,
            CUDA_VISIBLE_DEVICES="",
            PYTHONPATH="",
            TORCH_HOME=cfg["scoring"]["torch_home"],
        )

        def shard(rank):
            command = [
                cfg["runtime"]["metrics"],
                "-I",
                "scripts/external_full.py",
                "score",
                "--config",
                selection["configuration"],
                "--bundle",
                selection["bundle"],
                "--run",
                str(base / "run"),
                "--output",
                str(base / "scores"),
                "--models",
                model,
                "--shard",
                str(rank),
                "--shards",
                "4",
                "--case-ids",
                *selection["case_ids"],
            ]
            execute(
                f"{selection['benchmark']}-{model}-metrics{rank}",
                command,
                env,
                {"benchmark": selection["benchmark"], "model": model, "stage": "metrics"},
            )

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(shard, range(4)))

    try:
        status()
        # Verify only selected public inputs and canonical assets; no model or API calls.
        for selection in jobs:
            cfg = read(selection["configuration"])
            command = [
                cfg["runtime"]["metrics"],
                "-I",
                "scripts/external_full_preflight.py",
                "--config",
                selection["configuration"],
                "--bundle",
                selection["bundle"],
                "--case-ids",
                *selection["case_ids"],
                "--output",
                str(logs / (selection["benchmark"] + "-PREFLIGHT.json")),
            ]
            execute(
                selection["benchmark"] + "-preflight",
                command,
                dict(environment, CUDA_VISIBLE_DEVICES="", PYTHONPATH=""),
            )
        state["phase"] = "generation-and-scoring"
        with ThreadPoolExecutor(max_workers=1) as metrics_pool:
            metrics = []
            for selection in jobs:
                index = read(Path(selection["bundle"]) / "index.json")
                shards = partition(index, selection["generation_case_ids"], gpus)
                for model in MODELS:
                    with ThreadPoolExecutor(max_workers=8) as pool:
                        futures = [
                            pool.submit(generate, selection, model, gpu, shards[gpu])
                            for gpu in gpus
                        ]
                        try:
                            for future in futures:
                                future.result()
                        except BaseException:
                            halt(None, None)
                            raise
                    immutable(
                        logs / f"{selection['benchmark']}-{model}-GENERATED.json",
                        {"case_ids": selection["case_ids"]},
                    )
                    metrics.append(metrics_pool.submit(scoring, selection, model))
                    for done in metrics:
                        if done.done():
                            done.result()
            state["phase"] = "finishing-metrics"
            status()
            for future in metrics:
                future.result()
        state["phase"] = "native-reports"
        status()
        for selection in jobs:
            cfg = read(selection["configuration"])
            base = Path(selection["results_root"])
            command = [
                cfg["runtime"]["metrics"],
                "-I",
                "scripts/external_full.py",
                "report",
                "--bundle",
                selection["bundle"],
                "--run",
                str(base / "run"),
                "--scores",
                str(base / "scores"),
                "--output",
                str(base / "native_reports" / attempt),
                "--models",
                *MODELS,
                "--case-ids",
                *selection["case_ids"],
            ]
            execute(
                selection["benchmark"] + "-native-report",
                command,
                dict(environment, CUDA_VISIBLE_DEVICES="", PYTHONPATH=""),
            )
        state["phase"] = "generation-and-native-metrics-complete"
        status()
        immutable(
            logs / "DONE.json",
            {
                "plan_digest": manifest["digest"],
                "scientific_generation_complete": True,
                "paid_api_calls": 0,
                "paired_analysis_pending": True,
            },
        )
    except BaseException as error:
        halt(None, None)
        state.update(phase="failed-or-stopped", error=repr(error))
        status()
        immutable(logs / "FAILED.json", {"error": repr(error)})
        raise
    finally:
        halt(None, None)
        with lock:
            children = list(active.values())
        for child in children:
            child.wait()
        immutable(logs / "RELEASED.json", owner)
        for sig, handler in previous_signals.items():
            signal.signal(sig, handler)
