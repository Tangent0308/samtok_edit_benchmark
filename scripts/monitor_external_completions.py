#!/usr/bin/env python3
"""Read-only experiment monitoring; all monitor state stays outside formal results."""

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import time

from PIL import Image

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
CONTROL = NAS / ".ifbench-tmp/external_additions_20261111"
STATUS = CONTROL / "compbench/syntax_recovery/STATUS.json"
ROOTS = {
    "sitedit": NAS
    / "experiments2/SAMTokEdit/external_compbench/r2_multitarget_manual_20261111/final",
    "mirage": NAS / "experiments2/SAMTokEdit/external_compbench/mirage_20261111",
}


def read(path):
    for _ in range(3):
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(0.2)
    return None


def save(path, obj):
    tmp = path.with_suffix(".writing.json")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def main():
    cache, defects, last = {}, {}, {}
    while True:
        tick = time.monotonic()
        status = read(STATUS)
        if status:
            last = status
        counts = {}
        for model, root in ROOTS.items():
            for stage in ("tokens", "edit") if model == "sitedit" else ("plan", "edit"):
                directory = root / "run" / model / stage
                for p in directory.glob("*/result.json"):
                    key = str(p)
                    if key in cache:
                        continue
                    value = read(p)
                    if not value:
                        continue
                    cache[key] = {
                        "model": model,
                        "stage": stage,
                        "case_id": p.parent.name,
                        "status": value["status"],
                        "seconds": value.get("wall_seconds"),
                    }
                    if value["status"] != "completed":
                        defects[key] = {
                            "type": "native_or_execution_failure",
                            "error": value.get("error"),
                            "fatal": value.get("fatal", False),
                        }
                    elif stage == "edit":
                        try:
                            with Image.open(value["output_image"]) as im:
                                if list(im.size) != value["output_size"]:
                                    raise ValueError("Output dimensions differ from receipt")
                                im.verify()
                        except Exception as exc:
                            defects[key] = {"type": "output_integrity", "error": repr(exc)}
                selected = [
                    x for x in cache.values() if x["model"] == model and x["stage"] == stage
                ]
                summary = dict(Counter(x["status"] for x in selected))
                summary["terminal"] = len(selected)
                if stage == "edit":
                    seconds = [
                        x["seconds"]
                        for x in selected
                        if x["status"] == "completed" and x["seconds"] is not None
                    ]
                    if seconds:
                        summary["observed_mean_seconds"] = statistics.fmean(seconds)
                        summary["estimated_generation_hours_at_four_gpus"] = (
                            max(0, (144 if model == "sitedit" else 3285) - len(selected))
                            * statistics.fmean(seconds)
                            / (4 * 3600)
                        )
                counts[f"{model}/{stage}"] = summary
        mira = read(NAS / "experiments2/SAMTokEdit/external_mira/mice_20261111/REPORT.json")
        progress = {
            "updated": datetime.now(timezone.utc).isoformat(),
            "controller_status": last.get("status"),
            "active": last.get("active"),
            "counts": counts,
            "issues": defects,
            "mira_mice": {
                k: mira.get(k) for k in ("complete", "scored", "PF", "Cons", "PQ", "Overall")
            }
            if mira
            else None,
            "eta_note": "Generation estimate from measured completed cases; excludes pending planners, scoring and unknown API/resource delays.",
        }
        save(CONTROL / "MONITOR.json", progress)
        print(
            json.dumps(
                {k: progress[k] for k in ("updated", "controller_status", "counts")},
                ensure_ascii=False,
            ),
            flush=True,
        )
        if last.get("status") == "complete" and mira and mira.get("complete"):
            return
        time.sleep(max(1, 60 - (time.monotonic() - tick)))


if __name__ == "__main__":
    main()
