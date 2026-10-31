"""Run the registered dev workload, then Judge and stop before configuration freeze."""

from concurrent.futures import ThreadPoolExecutor
import argparse
import fcntl
import os
from pathlib import Path
from samtok_benchmark.paths import repository_root
import subprocess
import threading
import time

from samtok_benchmark.io import write_json
from .dev_plan import ROOT, read
from .dev_report import generate
from .dev_scope import active_plan
from .dev_balancer import identity

REPO = repository_root()
GEN = "/tmp/ifbench-audit-clean311/bin/python"
MASK = "/tmp/ifbench-audit-runtime/bin/python"
JUDGE = "/tmp/ifbench-judge-runtime/bin/python"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adopt-jobs", type=Path)
    args = parser.parse_args()
    lock = (ROOT / "controller.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    run_root = ROOT / "orchestration"
    run_root.mkdir(exist_ok=True)
    plan = active_plan()
    current = read(ROOT / "judge/current.json")
    judge_root = ROOT / "judge" / current["run_id"]
    probe = read(judge_root / "probe_bindings.json")
    assert probe and all(
        read(judge_root / "records" / f"{b['key']}.json")["status"] == "scored" for b in probe
    ), "Judge probe must pass first"
    started = time.monotonic()
    jobs = read(args.adopt_jobs) if args.adopt_jobs else []
    inherited = {}
    if args.adopt_jobs:
        for entry in jobs:
            if entry["status"] != "running":
                continue
            model = entry["command"][3]
            if model not in plan["candidates"]:
                assert identity(entry["pid"]) is None, "Deferred worker must stop before GPU reuse"
                entry.update(status="deferred-by-user", completed_at=time.time(), exit_code=None)
            else:
                entry["process_identity"] = identity(entry["pid"])
                inherited[int(entry["gpus"])] = entry
        write_json(run_root / "jobs.json", jobs)
    mutex = threading.Lock()
    done = threading.Event()

    def job(gpus, label, python, module, args):
        with mutex:
            index = len(jobs)
            entry = {
                "index": index,
                "label": label,
                "gpus": gpus,
                "status": "starting",
                "command": [python, "-m", module, *args],
            }
            jobs.append(entry)
        path = run_root / f"{index:03d}-{label}.log"
        env = {
            **os.environ,
            "CUDA_VISIBLE_DEVICES": gpus,
            "PYTHONPATH": str(REPO),
            "OMP_NUM_THREADS": "4",
            "TOKENIZERS_PARALLELISM": "false",
            "VLLM_WORKER_MULTIPROC_METHOD": "spawn",
        }
        tick = time.monotonic()
        with path.open("a") as log:
            proc = subprocess.Popen(
                entry["command"],
                cwd=REPO,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            with mutex:
                entry.update(pid=proc.pid, status="running", log=str(path), started_at=time.time())
                write_json(run_root / "jobs.json", jobs)
            rc = proc.wait()
        with mutex:
            entry.update(
                status="finished" if rc == 0 else "error",
                exit_code=rc,
                wall_seconds=time.monotonic() - tick,
                completed_at=time.time(),
            )
            write_json(run_root / "jobs.json", jobs)
        return rc

    def generate_model(gpu, model, components=False):
        if (ROOT / model / "PAUSED.json").exists():
            return
        args = [model]
        if components:
            args += ["--include-components"]
        job(
            str(gpu),
            f"{model}-gpu{gpu}",
            MASK if model == "maskflow" else GEN,
            "samtok_benchmark.ifbench.dev_runner",
            args,
        )

    def lane(gpu):
        if args.adopt_jobs:
            entry = inherited.get(gpu)
            if entry is not None:
                while (
                    entry["process_identity"] is not None
                    and identity(entry["pid"]) == entry["process_identity"]
                ):
                    time.sleep(10)
                with mutex:
                    entry.update(
                        status="ended-after-adoption",
                        completed_at=time.time(),
                        exit_code=None,
                        exit_code_note="Original parent was replaced; per-request results remain authoritative.",
                    )
                    write_json(run_root / "jobs.json", jobs)
            # The dispatcher chooses an active model; this argument is only a launch label.
            job(
                str(gpu),
                f"balanced-gpu{gpu}",
                GEN,
                "samtok_benchmark.ifbench.dev_runner",
                ["qwen2511"],
            )
            return
        if gpu in (0, 1):
            model = "replan" if gpu == 0 else "mirage"
            job(
                str(gpu),
                f"{model}-planner",
                GEN,
                "samtok_benchmark.ifbench.smoke_planners",
                [model, "--root", str(ROOT), "--dev"],
            )
            generate_model(gpu, model)
            generate_model(gpu, "qwen2511")
        elif gpu in (2, 3):
            model = "qwen21" if gpu == 2 else "flux3"
            job(
                str(gpu),
                f"{model}-component",
                JUDGE,
                "samtok_benchmark.ifbench.dev_components",
                [model],
            )
            generate_model(gpu, model, True)
        elif gpu == 4:
            generate_model(gpu, "mice")
        elif gpu == 6:
            generate_model(gpu, "qwen2511")
        generate_model(gpu, "maskflow")

    def progress():
        while not done.is_set():
            try:
                generate()
            except Exception as exc:
                write_json(
                    run_root / "progress_error.json", {"error": repr(exc), "time": time.time()}
                )
            done.wait(60)

    monitor = threading.Thread(target=progress, daemon=True)
    monitor.start()
    write_json(
        run_root / "controller.json",
        {
            "pid": os.getpid(),
            "status": "generation-running",
            "dev_plan_digest": plan["digest"],
            "started_at": time.time(),
            "freeze_authorized": False,
            "scope": plan.get("scope"),
            "adopted_jobs_from": str(args.adopt_jobs) if args.adopt_jobs else None,
        },
    )
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lane, range(8)))
        r = generate()
        blocks = {
            m: read(ROOT / m / "PAUSED.json")
            for m in plan["candidates"]
            if (ROOT / m / "PAUSED.json").exists()
        }
        if r["pending_tasks"] or blocks:
            state = "needs-attention"
        else:
            rc = job(
                "0,1,2,3,4,5,6,7",
                "canonical-judge",
                JUDGE,
                "samtok_benchmark.ifbench.dev_judge",
                [],
            )
            r = generate()
            state = (
                "ready-for-pre-freeze-review"
                if rc == 0 and r["ready_for_pre_freeze_review"]
                else "needs-attention"
            )
        write_json(
            run_root / "controller.json",
            {
                "pid": os.getpid(),
                "status": state,
                "dev_plan_digest": plan["digest"],
                "wall_seconds": time.monotonic() - started,
                "blocks": blocks,
                "freeze_authorized": False,
                "test_started": False,
                "scope": plan.get("scope"),
            },
        )
        if state == "ready-for-pre-freeze-review":
            write_json(
                ROOT / "REVIEW_REQUIRED.json",
                {
                    "status": state,
                    "report": str(ROOT / "PROGRESS.html"),
                    "instruction": "Stop: user approval required before freezing or any test inference.",
                },
            )
    finally:
        done.set()
        monitor.join(timeout=5)
        lock.close()


if __name__ == "__main__":
    main()
