"""Resume only the unchanged v2.1 Judge/report into a separate temporary root.

The outer lease uses the old Judge's own controller lock; the child also locks
its new result root. No generation command, failed-request retry, old ACTIVE
removal, old score rewrite, or frozen snapshot update is performed here.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
import traceback

from samtok_benchmark.io import sha256_file, write_json
from evaluation.protocol_audit.wait_qwen21_memory_probe import blocking_reasons, query_resources


def read(path):
    return json.loads(Path(path).read_text())


def run(config_path):
    config = read(config_path)
    parent = Path(config["original_plan"]).parent
    root = Path(config["recovery_root"])
    root.mkdir(parents=True, exist_ok=True)
    if (root / "RECOVERY_COMPLETED.json").exists() or (root / "RECOVERY_ERROR.json").exists():
        raise ValueError("Recovery already has a terminal record; inspect it instead of retrying")
    outer = (parent / "results/judge/controller.lock").open("r")
    fcntl.flock(outer, fcntl.LOCK_EX | fcntl.LOCK_NB)
    own = (root / "recovery.lock").open("a")
    fcntl.flock(own, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def verify_originals():
        for relative, field in [
            ("plan.json", "original_plan_sha256"),
            ("cache/judge_index.json", "original_index_sha256"),
            ("code_manifest.json", "original_code_manifest_sha256"),
        ]:
            if sha256_file(parent / relative) != config[field]:
                raise ValueError(f"Original artifact changed: {relative}")
        if sha256_file(config["runtime_wrapper"]) != config["runtime_wrapper_sha256"]:
            raise ValueError("Judge wrapper changed")
        # This recovery was prepared before any original new Judge admission.
        # A concurrent/unknown attempt must be investigated, never duplicated.
        if list((parent / "results/judge/admitted").glob("*.json")):
            raise ValueError("Original root now contains Judge admissions; do not duplicate")

    def status(phase, **extra):
        value = {
            "time": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
            "phase": phase,
            "original_plan": config["original_plan"],
            "results_root": str(root),
            "new_editor_calls": 0,
            **extra,
        }
        write_json(root / "RECOVERY_STATUS.json", value)
        print(json.dumps(value, ensure_ascii=False), flush=True)

    def child(module, label, *, cpu=False, extra=()):
        command = [
            config["runtime_wrapper"],
            "-m",
            module,
            "--plan",
            config["original_plan"],
            "--root",
            str(root),
            *extra,
        ]
        env = dict(os.environ)
        env.update(
            CUDA_VISIBLE_DEVICES="" if cpu else "0,1,2,3,4,5,6,7",
            PYTHONUNBUFFERED="1",
            OMP_NUM_THREADS="4",
            TOKENIZERS_PARALLELISM="false",
        )
        log_path = root / f"{label}.log"
        with log_path.open("x") as log:
            process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
            while process.poll() is None:
                detail = {"child_pid": process.pid, "log": str(log_path)}
                progress = root / "judge/progress.json"
                try:
                    detail["judge_progress"] = read(progress)
                except (FileNotFoundError, json.JSONDecodeError):
                    pass
                status(label, **detail)
                time.sleep(20)
            if process.returncode:
                raise RuntimeError(
                    f"{label} exited {process.returncode}; inspect {log_path}. No retry."
                )

    try:
        verify_originals()
        for relative, expected in read(parent / "code_manifest.json")["files"].items():
            if sha256_file(parent / "repo" / relative) != expected:
                raise ValueError(f"Fixed original snapshot changed: {relative}")
        old_effective = {
            str(p): sha256_file(p)
            for p in sorted((parent / "results/judge/effective_records").glob("*.json"))
        }
        write_json(
            root / "RECOVERY_STARTED.json",
            {
                "config": config,
                "config_sha256": sha256_file(config_path),
                "script_sha256": sha256_file(Path(__file__)),
                "original_effective_sha256": old_effective,
                "lock_note": "Both canonical flock contracts retained; cross-host filesystem lock semantics not independently verified.",
            },
        )
        child(
            "samtok_benchmark.ifbench.fairness_dev_judge",
            "cpu_preflight",
            cpu=True,
            extra=("--dry-run",),
        )
        dry = read(root / "judge/dry_run.json")
        if (
            dry["eligible_unique_jobs"] != config["maximum_new_judge_calls"]
            or not dry["all_generation_terminal"]
            or dry["new_judge_calls"] != 0
        ):
            raise ValueError("Recovery scope differs from the inspected unattempted Judge set")
        probe = Path(config["local_probe"])
        resource_config = read(probe / "plan.json")
        ready = 0
        while ready < 3:
            snapshot = query_resources(resource_config.get("training_workflows", []))
            reasons = blocking_reasons(snapshot, resource_config)
            if not (probe / "GATE_FINISHED.json").exists():
                reasons.append("local_two_case_probe_not_finished")
            ready = ready + 1 if not reasons else 0
            status("waiting_for_eight_gpus", blocking_reasons=reasons, idle_streak=ready)
            time.sleep(15)
        verify_originals()
        child("samtok_benchmark.ifbench.fairness_dev_judge", "judge")
        child("samtok_benchmark.ifbench.fairness_dev_report", "report", cpu=True)
        verify_originals()
        if any(sha256_file(path) != expected for path, expected in old_effective.items()):
            raise ValueError("Original effective scores changed during recovery")
        raws = [read(p) for p in (root / "judge/raw_records").glob("*.json")]
        admissions = list((root / "judge/admitted").glob("*.json"))
        if len(raws) != len(admissions) or len(raws) != config["maximum_new_judge_calls"]:
            raise ValueError("Unexpected or unresolved Judge admissions; no automatic retry")
        report = read(root / "report/REPORT.json")
        outcome = {
            "status": "completed-awaiting-dev-review",
            "report": str(root / "report/REPORT.md"),
            "ready_for_review": report["ready_for_review"],
            "new_judge_calls": sum(r.get("new_judge_calls", 0) for r in raws),
            "raw_answers": len(raws),
            "original_scores_unchanged": True,
            "new_editor_calls": 0,
            "diagnostic_outputs_included": False,
            "test_started": False,
            "frozen": False,
        }
        write_json(root / "RECOVERY_COMPLETED.json", outcome)
        status("completed", **outcome)
        return 0
    except BaseException as error:
        write_json(
            root / "RECOVERY_ERROR.json",
            {
                "error": repr(error),
                "traceback": traceback.format_exc(),
                "automatic_retry": False,
            },
        )
        status("stopped-with-error", error=repr(error))
        raise
    finally:
        own.close()
        outer.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    raise SystemExit(run(parser.parse_args().config))
