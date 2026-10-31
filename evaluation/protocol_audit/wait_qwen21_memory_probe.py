"""Wait for local training to finish before one two-case diagnostic.

This CPU-only gate never kills jobs, imports torch, resumes an attempt, or runs
Judge. Unknown GPU processes block admission, including processes whose host
PIDs cannot be resolved inside this container.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
import time

from samtok_benchmark.io import sha256_file, write_json


def utc():
    return datetime.now(timezone.utc).isoformat()


def query_resources(tracked_workflows=()):
    def query(flag):
        output = subprocess.check_output(
            ["nvidia-smi", flag, "--format=csv,noheader,nounits"], text=True, timeout=15
        )
        return [[part.strip() for part in row] for row in csv.reader(output.splitlines())]

    gpus = [
        {"index": int(index), "uuid": uuid, "free_mib": int(free), "utilization": int(util)}
        for index, uuid, free, util in query("--query-gpu=index,uuid,memory.free,utilization.gpu")
    ]
    processes = [
        {"pid": int(pid), "gpu_uuid": uuid, "used_mib": int(used)}
        for pid, uuid, used in query("--query-compute-apps=pid,gpu_uuid,used_gpu_memory")
    ]
    meminfo = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    alive = []
    for workflow in tracked_workflows:
        try:
            fields = Path(f"/proc/{workflow['pid']}/stat").read_text().rsplit(")", 1)[1].split()
        except FileNotFoundError:
            continue
        if fields[0] != "Z" and fields[19] == workflow["start_ticks"]:
            alive.append(workflow)
    return {
        "hostname": socket.gethostname(),
        "gpus": gpus,
        "processes": processes,
        "cpu_available_gib": int(meminfo["MemAvailable"].split()[0]) / 1024**2,
        "training_workflows_alive": alive,
    }


def blocking_reasons(snapshot, config):
    reasons = []
    if snapshot["hostname"] != config["hostname"]:
        reasons.append("different_hostname")
    gpus = snapshot["gpus"]
    if sorted(g["uuid"] for g in gpus) != sorted(config["all_gpu_uuids"]):
        reasons.append("different_or_missing_gpu_set")
    allowed = config.get("existing_background_processes", [])
    unexpected = [
        process
        for process in snapshot["processes"]
        if not any(
            process["pid"] == item["pid"]
            and process["gpu_uuid"] in item["gpu_uuids"]
            and process.get("used_mib", float("inf")) <= item["maximum_used_mib"]
            for item in allowed
        )
    ]
    if unexpected:
        reasons.append("gpu_processes_still_active")
    if snapshot.get("training_workflows_alive"):
        reasons.append("training_workflow_still_active")
    if any(g["free_mib"] < config["minimum_free_mib"] for g in gpus):
        reasons.append("insufficient_gpu_memory")
    if any(g["utilization"] > config["maximum_idle_utilization"] for g in gpus):
        reasons.append("gpu_work_still_active")
    if snapshot["cpu_available_gib"] < config["minimum_cpu_available_gib"]:
        reasons.append("insufficient_cpu_memory")
    return reasons


def verify_sources(config):
    for name, digest in config["source_sha256"].items():
        if sha256_file(Path(name)) != digest:
            raise ValueError(f"Diagnostic source changed: {name}")


def run(plan_path):
    config = json.loads(plan_path.read_text())
    plan_sha = sha256_file(plan_path)
    root = Path(config["output_directory"]).parent
    root.mkdir(parents=True, exist_ok=True)
    with (root / "gate.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (root / "ADMITTED.json").exists() or Path(config["output_directory"]).exists():
            raise ValueError("This diagnostic has already been admitted; no automatic retry")
        verify_sources(config)
        write_json(
            root / "GATE_IDENTITY.json",
            {
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "time": utc(),
                "probe_plan_sha256": plan_sha,
                "poll_seconds": config["poll_seconds"],
                "policy": "training completed; only explicitly recorded background processes allowed",
                "existing_background_processes": config.get("existing_background_processes", []),
            },
        )
        idle_streak = 0
        last_sample = None
        while True:
            if (root / "STOP_LOCAL_PROBE").exists():
                write_json(root / "gate_status.json", {"time": utc(), "status": "stopped"})
                return 0
            if sha256_file(plan_path) != plan_sha:
                raise ValueError("Diagnostic plan changed while waiting")
            now = time.monotonic()
            if last_sample is not None and now - last_sample > 2 * config["poll_seconds"]:
                idle_streak = 0
            last_sample = now
            try:
                snapshot = query_resources(config.get("training_workflows", []))
                reasons = blocking_reasons(snapshot, config)
                idle_streak = idle_streak + 1 if not reasons else 0
                status = {
                    "time": utc(),
                    "status": "waiting_for_training_release",
                    "idle_streak": idle_streak,
                    "required_idle_polls": config["idle_polls"],
                    "blocking_reasons": reasons,
                    "snapshot": snapshot,
                    "new_inference_calls": 0,
                }
            except Exception as error:
                idle_streak = 0
                status = {
                    "time": utc(),
                    "status": "waiting_for_resource_query",
                    "error": repr(error),
                    "idle_streak": 0,
                    "new_inference_calls": 0,
                }
            write_json(root / "gate_status.json", status)
            with (root / "resource_history.jsonl").open("a") as history:
                history.write(json.dumps(status, ensure_ascii=False) + "\n")
            print(json.dumps({k: v for k, v in status.items() if k != "snapshot"}), flush=True)
            if idle_streak >= config["idle_polls"]:
                verify_sources(config)
                fresh = query_resources(config.get("training_workflows", []))
                if blocking_reasons(fresh, config):
                    idle_streak = 0
                    continue
                grant = {
                    "time": utc(),
                    "checked_at_epoch": time.time(),
                    "status": "ready",
                    "probe_plan_sha256": plan_sha,
                    "training_pids_remaining": [],
                    "snapshot": fresh,
                    "idle_streak": idle_streak,
                }
                write_json(root / "RESOURCE_GRANTED.json", grant)
                # Persist before process creation: a launcher failure is visible,
                # and cannot silently resubmit a possibly admitted native call.
                with (root / "ADMITTED.json").open("x") as admission:
                    json.dump({**grant, "maximum_new_inference_calls": 2}, admission, indent=2)
                env = dict(os.environ)
                env["CUDA_VISIBLE_DEVICES"] = config["gpu_uuid"]
                command = [
                    config["runtime_wrapper"],
                    config["probe_script"],
                    "--plan",
                    str(plan_path),
                ]
                with (root / "probe.log").open("x") as log:
                    try:
                        child = subprocess.Popen(
                            command, env=env, stdout=log, stderr=subprocess.STDOUT
                        )
                    except Exception as error:
                        write_json(
                            root / "GATE_FINISHED.json",
                            {
                                "time": utc(),
                                "status": "launch_failed",
                                "error": repr(error),
                                "automatic_retry": False,
                            },
                        )
                        raise
                    write_json(
                        root / "gate_status.json",
                        {
                            "time": utc(),
                            "status": "diagnostic_running",
                            "child_pid": child.pid,
                            "maximum_new_inference_calls": 2,
                            "log": str(root / "probe.log"),
                        },
                    )
                    code = child.wait()
                write_json(
                    root / "GATE_FINISHED.json",
                    {
                        "time": utc(),
                        "status": "finished",
                        "returncode": code,
                        "automatic_retry": False,
                        "formal_results_replaced": False,
                    },
                )
                return code
            time.sleep(config["poll_seconds"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    raise SystemExit(run(parser.parse_args().plan))
