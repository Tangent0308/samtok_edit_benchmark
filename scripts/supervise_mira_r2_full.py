#!/usr/bin/env python3
"""Finish missing MIRA judgments after the live pipeline, without touching generation."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_mira_r2_full as run  # noqa: E402


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def active(pid):
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes()
        state = Path(f"/proc/{pid}/stat").read_text().split(")", 1)[1].split()[0]
        return b"run_mira_r2_full.py" in cmd and state != "Z"
    except FileNotFoundError:
        return False


def count_scores(directory):
    path = directory / "scores/per_image_results.jsonl"
    if not path.exists():
        return 0
    rows = run.read_rows(path)
    images = [r["image"] for r in rows]
    if len(set(images)) != len(images):
        raise ValueError("Duplicate score commits; manual inspection required")
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=run.BASE / run.PROFILE["default_run_name"])
    parser.add_argument("--scratch", type=Path,
                        default=Path(run.PROFILE["scratch"]))
    parser.add_argument("--key-file", type=Path, help="Defaults to MIRA_API_KEY_FILE")
    parser.add_argument("--append-results", type=Path,
                        help="Explicit destination for the section 16.6 Markdown summary")
    args = parser.parse_args()
    root, scratch = args.root.resolve(), args.scratch.resolve()
    if root.parent != run.BASE or root.name in {
            "run_001", "scores_gpt54_001", "audited_report_v2", "execution_audit",
            "overlap_audit", "diagnostics"} or scratch.is_relative_to(run.BASE):
        raise ValueError("Unexpected output or scratch root")
    initial = run.read(root / "STATUS.json")
    if initial.get("status") == "complete":
        if args.append_results:
            run.append_section(run.read(root / "SUMMARY_CONTENT.json")["markdown"], args.append_results)
        print(f"Run already complete; no GPU or API work: {root}", flush=True)
        return
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "logs").mkdir(exist_ok=True)
    lock = (scratch / "recovery.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    pid = initial.get("pipeline_pid")
    # The original coordinator may be waiting for its live generation workers even if a
    # Judge batch has failed. Never replace that coordinator or interrupt its children.
    while pid and active(pid):
        run.write_json(root / "SUPERVISOR.json", {
            "status": "watching_live_pipeline", "updated_at": timestamp(),
            "pid": os.getpid(), "generation_pipeline_pid": pid,
            "policy": "After live workers exit, retry infrastructure/API-capacity failures until complete."})
        time.sleep(30)
    plan = run.read(root / "run_001/RUN.json")
    config = run.read(root / "run_001/CONFIG.json")
    judge_config = run.read(root / "JUDGE_CONFIG.json")
    batches = run.batch_cases(plan["case_ids"])
    for cid in plan["case_ids"]:
        path = root / "run_001/sitedit/edit" / cid / "result.json"
        if not path.exists() or run.read(path)["status"] != "completed":
            raise RuntimeError(f"Generation requires inspection: {cid}; no resampling attempted")
    evaluator = run.ensure_evaluator(judge_config["source"])
    pending = {name: cases for name, cases in batches.items()
               if not run.judge_complete(root / "scores_gpt54" / name / "sitedit", cases)}
    credentials = run.credential_env(args.key_file) if pending else dict(os.environ)
    env = dict(credentials, CUDA_VISIBLE_DEVICES="", PYTHONPATH=str(run.REPO / "src"),
               PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="4")
    env.pop("LD_PRELOAD", None)

    def finish_batch(name, cases):
        directory = root / "scores_gpt54" / name / "sitedit"
        job = run.export(plan["bundle"], scratch / "judge_views" / name, directory,
                         "sitedit", config, evaluator, judge_config)
        if job["valid_outputs"] != len(cases) or job["unscorable"]:
            raise ValueError("Unexpected incomplete score export")
        if run.judge_complete(directory, cases):
            return name
        attempts_path = directory / "RECOVERY_ATTEMPTS.json"
        attempts = run.read(attempts_path) if attempts_path.exists() else []
        consecutive_errors = 0
        while not run.judge_complete(directory, cases):
            attempt = len(attempts) + 1
            logfile = scratch / "logs" / f"recovery_{name}_{attempt:03d}.log"
            command = [config["runtime"]["generation"], "-B", "-u", "-m",
                       "samtok_benchmark.external_mira", "judge", "--job", str(directory / "JOB.json")]
            started = timestamp()
            with logfile.open("x") as log:
                code = subprocess.run(command, cwd=run.REPO, env=env, stdout=log,
                                      stderr=subprocess.STDOUT).returncode
            attempts.append({"attempt": attempt, "started_at": started, "ended_at": timestamp(),
                             "exit_code": code, "committed_scores": count_scores(directory),
                             "log": str(logfile), "authorization": "User requested retrying resource shortages until full completion."})
            run.write_json(attempts_path, attempts)
            if code == 0:
                if not run.judge_complete(directory, cases):
                    raise RuntimeError("Judge exited successfully with missing scores")
                break
            text = logfile.read_text(errors="replace")
            if not run.transient_error(text):
                raise RuntimeError(f"Non-transient Judge error in {name}; inspect {logfile}")
            consecutive_errors += 1
            delay = run.retry_delay(consecutive_errors)
            print(f"{timestamp()} {name}: transient failure; retry missing scores in {delay}s", flush=True)
            # Short intervals keep this CPU-only supervisor responsive to interruption.
            for _ in range(delay // 10):
                time.sleep(10)
        print(f"{timestamp()} {name}: {len(cases)} committed scores", flush=True)
        return name

    run.write_json(root / "SUPERVISOR.json", {"status": "completing_missing_scores", "pid": os.getpid(),
                                             "updated_at": timestamp(), "pending_batches": list(pending)})
    # Two API lanes reduce pressure on the provider while inference is already finished.
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(finish_batch, name, cases) for name, cases in pending.items()]
        for future in futures:
            future.result()
    run.finish(root, plan, batches, args.append_results)
    run.write_json(root / "SUPERVISOR.json", {"status": "complete", "updated_at": timestamp(),
                                             "total": 200, "scored": 200})
    status = run.read(root / "STATUS.json")
    status.update(status="complete", generated=200, scored=200, finished_at=timestamp(),
                  report=str(root / "REPORT.json"),
                  appended=str(args.append_results) if args.append_results else None)
    run.write_json(root / "STATUS.json", status)
    print("Full 200-image evaluation complete", flush=True)


if __name__ == "__main__":
    main()
