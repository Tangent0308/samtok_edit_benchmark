"""Monitor only this comparison and finalize CPU tables when the native queue finishes."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from samtok_benchmark.external_full.data import read, immutable
from samtok_benchmark.external_full.coordination import atomic
from samtok_benchmark.external_compare.report import run


def main(control, attempt, analysis_id=None):
    control = Path(control)
    output = control / "analysis" / (analysis_id or attempt)
    output.mkdir(parents=True, exist_ok=False)
    immutable(output / "OWNER.json", {"pid": os.getpid(), "attempt": attempt})
    plan = read(control / "PLAN.json")
    log = (output / "MONITOR.jsonl").open("x")
    try:
        while True:
            try:
                state = read(control / "STATUS.json")
            except (FileNotFoundError, ValueError):
                time.sleep(3)
                continue
            if state["attempt"] != attempt or state["plan_digest"] != plan["digest"]:
                raise ValueError("Supervisor identity changed")
            groups = defaultdict(lambda: {"completed": 0, "failed": 0, "active": 0})
            for s in state["stages"].values():
                if s.get("model"):
                    group = groups["/".join((s["benchmark"], s["model"], s["stage"]))]
                    group["completed"] += s["new_completed"]
                    group["failed"] += s["new_failed"]
                    group["active"] += s["phase"] == "running"
            receipt = {
                "checked_utc": datetime.now(timezone.utc).isoformat(),
                "scheduler_updated_utc": state["updated_utc"],
                "phase": state["phase"],
                "groups": dict(groups),
                "error": state.get("error"),
                "metric_failures_observed": [
                    {"log": str(path), "message": line}
                    for path in (control / "attempts" / attempt).glob("*metrics*.log")
                    for line in path.read_text(errors="replace").splitlines()
                    if ": score_failed " in line
                ],
                "expected_new_edits": plan["new_generation_requests"],
                "finished_new_edits": sum(
                    g["completed"] + g["failed"] for k, g in groups.items() if k.endswith("/edit")
                ),
            }
            receipt["heartbeat_stale"] = (
                datetime.now(timezone.utc) - datetime.fromisoformat(state["updated_utc"])
            ).total_seconds() > 120
            atomic(output / "STATUS.json", receipt)
            log.write(json.dumps(receipt, ensure_ascii=False) + "\n")
            log.flush()
            print(json.dumps(receipt, ensure_ascii=False), flush=True)
            if (control / "attempts" / attempt / "FAILED.json").exists():
                raise RuntimeError("Comparison stopped; preserve evidence and inspect")
            if (control / "attempts" / attempt / "DONE.json").exists():
                run(control, attempt)
                immutable(
                    output / "DONE.json", {"plan_digest": plan["digest"], "reports_complete": True}
                )
                return
            time.sleep(30)
    except BaseException as error:
        immutable(output / "FAILED.json", {"error": repr(error)})
        raise
    finally:
        log.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--control", required=True)
    p.add_argument("--attempt", required=True)
    p.add_argument("--analysis-id")
    main(**vars(p.parse_args()))
