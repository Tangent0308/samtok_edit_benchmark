"""Balance future GPU handoffs without interrupting existing dev requests."""

from collections import Counter, defaultdict
import fcntl
import os
from pathlib import Path
import statistics
import subprocess
import time

from samtok_benchmark.io import write_json
from .dev_plan import ROOT, SMOKE, read
from .smoke_suite import SHARED
from .dev_scope import active_plan

CONTROL = ROOT / "engineering" / "balanced_queue"
REPO = Path(__file__).resolve().parents[2]
GEN = "/tmp/ifbench-audit-clean311/bin/python"
MASK = "/tmp/ifbench-audit-runtime/bin/python"


def identity(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return None if fields[0] == "Z" else fields[19]
    except (FileNotFoundError, ProcessLookupError):
        return None


def choose(work, available, active):
    """Give the free GPU to the longest projected queue after adding this worker."""
    eligible = [m for m in work if available[m] and work[m] > 0]
    return max(eligible, key=lambda m: (work[m] / (active[m] + 1), m)) if eligible else None


def workloads(plan):
    units = {
        cid: len(read(SHARED / "requests/S1" / cid / "public.json")["units"])
        for cid in plan["case_ids"]
    }
    samples = defaultdict(list)
    pending = []
    blocked = {m for m in plan["candidates"] if (ROOT / m / "PAUSED.json").exists()}
    for task in plan["tasks"]:
        model = task["model"]
        path = ROOT / "runs" / task["key"] / "result.json"
        if path.exists():
            result = read(path)
            seconds = result.get("pipeline_wall_seconds")
            if result["status"] == "generated" and seconds is not None:
                divisor = units[task["case_id"]] if model == "maskflow" else 1
                samples[(model, task["form"], task["setting"] == "S1")].append(seconds / divisor)
        elif model not in blocked:
            if (
                task["component"]
                and not (
                    ROOT / "components" / model / f"{task['case_id']}--{task['setting']}.json"
                ).exists()
            ):
                continue
            pending.append(task)
    smoke = defaultdict(list)
    for model in plan["candidates"]:
        for path in (SMOKE / model / "runs").glob("*/result.json"):
            result = read(path)
            seconds = result.get("pipeline_wall_seconds")
            if result["status"] == "generated" and seconds is not None:
                task = result["task"]
                divisor = units[task["case_id"]] if model == "maskflow" else 1
                smoke[(model, task["form"], task["setting"] == "S1")].append(seconds / divisor)
    for key, values in smoke.items():
        if key not in samples:
            samples[key] = values
    work, available = Counter(), Counter()
    for task in pending:
        model = task["model"]
        if model == "maskflow" and task["setting"] in ("S1", "S5"):
            seconds = 0.01  # Scheduling weight only, never reported as measured runtime.
        else:
            key = (model, task["form"], task["setting"] == "S1")
            values = samples.get(key) or samples.get((model, task["form"], False))
            if not values:
                raise ValueError(f"No measured timing evidence for {key}")
            seconds = statistics.mean(values) * (
                units[task["case_id"]] if model == "maskflow" else 1
            )
        work[model] += seconds
        if not (ROOT / "runs" / task["key"] / "started.json").exists():
            available[model] += 1
    return work, available


def run(requested_model):
    CONTROL.mkdir(parents=True, exist_ok=True)
    plan = active_plan()
    config = read(CONTROL / "enabled.json")
    assert config["dev_plan_digest"] == plan["digest"]
    pid = os.getpid()
    key = f"{pid}-{identity(pid)}"
    registry = CONTROL / f"worker-{key}.json"
    iteration = 0
    while True:
        with (CONTROL / "allocation.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            active = Counter()
            dispatchers = set()
            for path in CONTROL.glob("worker-*.json"):
                entry = read(path)
                if identity(entry["pid"]) != entry["process_identity"]:
                    continue
                dispatchers.add(entry["pid"])
                if entry["status"] == "running" and entry["pid"] != pid:
                    active[entry["model"]] += 1
            # Existing workers keep their current request queues and are never signaled.
            for job in read(ROOT / "orchestration/jobs.json"):
                if job["status"] != "running" or job["pid"] in dispatchers or job["pid"] == pid:
                    continue
                if identity(job["pid"]) is None:
                    continue
                argv = job["command"]
                if "samtok_benchmark.ifbench.dev_runner" in argv:
                    active[argv[argv.index("samtok_benchmark.ifbench.dev_runner") + 1]] += 1
            work, available = workloads(plan)
            # An interrupted request can be accounted as failed by the ordinary worker.
            for model in work:
                if active[model] == 0 and not available[model]:
                    available[model] = 1
            model = choose(work, available, active)
            entry = {
                "pid": pid,
                "process_identity": identity(pid),
                "requested_model": requested_model,
                "model": model,
                "visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
                "status": "running" if model else "finished",
                "dev_plan_digest": plan["digest"],
                "iteration": iteration,
                "active_workers_before_assignment": dict(active),
                "estimated_queue_seconds": dict(work),
                "time": time.time(),
            }
            write_json(registry, entry)
            write_json(CONTROL / f"assignment-{key}-{iteration}.json", entry)
        if model is None:
            return
        args = [
            MASK if model == "maskflow" else GEN,
            "-m",
            "samtok_benchmark.ifbench.dev_runner",
            model,
            "--exact-model",
            "--include-components",
        ]
        log_path = CONTROL / f"run-{key}-{iteration}-{model}.log"
        with log_path.open("a") as log:
            proc = subprocess.Popen(
                args, cwd=REPO, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT
            )
            entry.update(child_pid=proc.pid, log=str(log_path), command=args)
            write_json(registry, entry)
            code = proc.wait()
        entry.update(status="finished", exit_code=code, completed_at=time.time())
        write_json(registry, entry)
        write_json(CONTROL / f"completed-{key}-{iteration}.json", entry)
        if code != 0:
            # No retry loop on environment/load errors. Preserve the model's failure evidence.
            write_json(
                ROOT / model / "PAUSED.json",
                {
                    "reason": "Balanced worker exited with an error; no automatic retry",
                    "exit_code": code,
                    "log": str(log_path),
                },
            )
        iteration += 1
