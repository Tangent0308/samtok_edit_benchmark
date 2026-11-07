#!/usr/bin/env python3
"""Read-only experiment monitoring; write observations outside formal results."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import time

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")


def read(path):
    for delay in (0, 0.1, 0.5):
        if delay:
            time.sleep(delay)
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    prep = NAS / ".ifbench-tmp/magicbrush_paper_20261107"
    output = NAS / "experiments2/SAMTokEdit/external_magicbrush/magicbrush_paper_20261107"
    destination = prep / "monitor" / args.attempt
    destination.mkdir(parents=True, exist_ok=True)
    cache = {}
    while True:
        state = read(prep / "supervision" / args.attempt / "STATUS.json") or {}
        for kind, glob in [
            ("generation", "runs/*/edit/*/*/*/result.json"),
            ("scoring", "scores/*/*/*/*/score.json"),
        ]:
            for path in output.glob(glob):
                if str(path) not in cache:
                    record = read(path)
                    if record:
                        cache[str(path)] = (kind, record)
        generated = [r for k, r in cache.values() if k == "generation"]
        scored = [r for k, r in cache.values() if k == "scoring"]
        times = [r["inference_seconds"] for r in generated if r["status"] == "completed"]
        failures = [
            {"kind": k, "key": r.get("identity", {}).get("key"), "error": r.get("error")}
            for k, r in cache.values()
            if r["status"] == "failed"
        ]
        record = {
            "observed_utc": datetime.now(timezone.utc).isoformat(),
            "controller": state,
            "expected_unique_generations": 1571,
            "generation": dict(Counter(r["status"] for r in generated)),
            "scoring": dict(Counter(r["status"] for r in scored)),
            "mean_inference_seconds": statistics.fmean(times) if times else None,
            "failures": failures,
        }
        if times:
            # This is a throughput estimate, never a measured experiment result.
            record["ideal_generation_remaining_seconds_four_cards"] = (
                max(0, 1571 - len(generated)) * statistics.fmean(times) / 4
            )
        temporary = destination / "CURRENT.tmp"
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        temporary.replace(destination / "CURRENT.json")
        with (destination / "history.jsonl").open("a") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(json.dumps({k: v for k, v in record.items() if k != "controller"}), flush=True)
        if not args.watch or state.get("stage") in {
            "complete",
            "failed",
            "stopped",
            "needs_cluster",
        }:
            return
        time.sleep(50)


if __name__ == "__main__":
    main()
