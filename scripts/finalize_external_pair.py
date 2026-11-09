"""Monitor the existing run and finish CPU reports without changing any model process."""

import argparse
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from samtok_benchmark.external_full.data import read, immutable
from samtok_benchmark.external_full.coordination import atomic
from samtok_benchmark.external_pair.preview import render
from samtok_benchmark.external_pair.report import run


def main(control, attempt, analysis_id=None):
    control = Path(control)
    plan = read(control / "PLAN.json")
    attempt_dir = control / "attempts" / attempt
    report_dir = control / "analysis" / (analysis_id or attempt)
    report_dir.mkdir(parents=True, exist_ok=False)
    immutable(report_dir / "OWNER.json", {"pid": os.getpid(), "attempt": attempt})
    selections = [(Path(e["selection"]), read(e["selection"])) for e in plan["benchmarks"]]
    galleries = {}
    log = (report_dir / "MONITOR.jsonl").open("x")
    try:
        while True:
            try:
                state = read(control / "STATUS.json")
            except (FileNotFoundError, ValueError):
                time.sleep(3)
                continue
            if state["attempt"] != attempt or state["plan_digest"] != plan["digest"]:
                raise ValueError("Scheduler identity changed")
            groups = defaultdict(lambda: {"completed": 0, "failed": 0})
            for s in state["stages"].values():
                if s.get("stage") == "edit":
                    group = groups[s["benchmark"] + "/" + s["model"]]
                    group["completed"] += s["new_completed"]
                    group["failed"] += s["new_failed"]
            receipt = {
                "checked_utc": datetime.now(timezone.utc).isoformat(),
                "scheduler_updated_utc": state["updated_utc"],
                "phase": state["phase"],
                "edit_counts": dict(groups),
                "galleries": galleries.copy(),
                "error": state.get("error"),
            }
            age = (
                datetime.now(timezone.utc) - datetime.fromisoformat(state["updated_utc"])
            ).total_seconds()
            receipt["heartbeat_stale"] = age > 120
            atomic(report_dir / "STATUS.json", receipt)
            import json

            log.write(json.dumps(receipt, ensure_ascii=False) + "\n")
            log.flush()
            print(json.dumps(receipt, ensure_ascii=False), flush=True)
            if (attempt_dir / "FAILED.json").exists():
                raise RuntimeError("Generation/scoring stopped; preserve evidence and inspect")
            for path, selection in selections:
                bench = selection["benchmark"]
                if bench not in galleries and all(
                    (attempt_dir / f"{bench}-{m}-GENERATED.json").exists()
                    for m in ("sitedit", "qwen21")
                ):
                    galleries[bench] = str(render(path))
            if (attempt_dir / "DONE.json").exists():
                reports = run(control, attempt)
                immutable(
                    report_dir / "DONE.json",
                    {
                        "plan_digest": plan["digest"],
                        "paired_reports": [
                            str(Path(r["results_root"]) / "report/REPORT.md") for r in reports
                        ],
                        "galleries": galleries,
                    },
                )
                print("All paired reports and complete case galleries finished.", flush=True)
                return
            time.sleep(30)
    except BaseException as error:
        immutable(report_dir / "FAILED.json", {"error": repr(error)})
        raise
    finally:
        log.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--analysis-id")
    main(**vars(parser.parse_args()))
