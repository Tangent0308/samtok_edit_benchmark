"""Cheap progress and throughput estimate from scheduler receipts (no model/result changes)."""

from collections import defaultdict
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path


def main(control):
    c = Path(control)
    s = json.loads((c / "STATUS.json").read_text())
    groups = defaultdict(
        lambda: {"completed": 0, "failed": 0, "cached_on_entry": 0, "active_workers": 0}
    )
    for row in s["stages"].values():
        if row.get("stage") not in ("tokens", "edit", "metrics"):
            continue
        key = "/".join((row["benchmark"], row["model"], row["stage"]))
        group = groups[key]
        group["completed"] += row["new_completed"]
        group["failed"] += row["new_failed"]
        group["cached_on_entry"] += row.get("terminal_on_entry", 0)
        group["active_workers"] += row["phase"] == "running"
    result = {
        "updated_utc": s["updated_utc"],
        "seconds_since_update": (
            datetime.now(timezone.utc) - datetime.fromisoformat(s["updated_utc"])
        ).total_seconds(),
        "attempt": s["attempt"],
        "phase": s["phase"],
        "elapsed_minutes": s["elapsed_seconds"] / 60,
        "expected_edits": sum(r["generation_per_model"] * 2 for r in s["benchmarks"].values()),
        "finished_edits": sum(
            v["completed"] + v["failed"] + v["cached_on_entry"]
            for k, v in groups.items()
            if k.endswith("/edit")
        ),
        "groups": groups,
        "error": s.get("error"),
        "note": "Scheduler counters track terminal generation, not editing quality. CPU metric logs have separate per-case receipts.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--control", required=True)
    main(**vars(p.parse_args()))
