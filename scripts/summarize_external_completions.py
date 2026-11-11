#!/usr/bin/env python3
# ruff: noqa: E402 - isolated CLI explicitly adds the repository source path.
"""Merge all 144 new R2 cases as one cohort, preserving original measurements."""

import argparse
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from samtok_benchmark.external_refedit.data import read, immutable
from samtok_benchmark.external_full.report import report
from samtok_benchmark.io import sha256_file

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
CONTROL = NAS / ".ifbench-tmp/external_additions_20261111/compbench"
BASE = NAS / "experiments2/SAMTokEdit/external_compbench"
NEW = BASE / "r2_multitarget_manual_20261111"
OLD = BASE / "r2_20261110"


def link(path, target):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        if path.resolve() != target.resolve():
            raise ValueError("Existing read-only view changed")
    else:
        path.symlink_to(target, target_is_directory=True)


def main():
    global NEW
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--merge-sitedit", action="store_true")
    p.add_argument("--parsed", action="store_true")
    a = p.parse_args()
    if not a.merge_sitedit:
        raise ValueError("Specify --merge-sitedit")
    if a.parsed:
        NEW = NEW / "final"
    plan = read(CONTROL / "sitedit/PLAN.json")
    full = read(CONTROL / "mirage/PLAN.json")["case_ids"]
    changed = set(plan["case_ids"])
    if len(changed) != 144 or len(full) != 3285 or not changed < set(full):
        raise ValueError("Unexpected full/replacement cohort")
    view = CONTROL / "merged_r2_view"
    bindings = []
    for cid in full:
        origin = NEW if cid in changed else OLD
        gen = origin / "run/sitedit/edit" / cid
        scores = origin / "scores/sitedit" / cid
        r, s = read(gen / "result.json"), read(scores / "local.json")
        if s["identity"]["result_sha256"] != sha256_file(gen / "result.json"):
            raise ValueError("Score no longer binds to original output")
        if r["status"] == "completed":
            call = read(gen / "call.json")
            adapter = (
                NAS
                / "experiments2/SAMTokEdit/quality_anchor_20261104/runs_v5/v6_full/r2/train/adapter_1000"
            )
            if (
                call["dit_adapter"] != str(adapter)
                or call["parameters"]["num_inference_steps"] != 40
            ):
                raise ValueError("Mixed SITEdit checkpoint or steps")
            if call["parameters"]["seed"] != 42 or call["parameters"]["pass2_te"] != "raw":
                raise ValueError("Mixed native generation setting")
        link(view / "run/sitedit/edit" / cid, gen)
        link(view / "scores/sitedit" / cid, scores)
        bindings.append(
            {
                "case_id": cid,
                "origin": str(origin),
                "generation": str(gen / "result.json"),
                "score": str(scores / "local.json"),
                "result_sha256": sha256_file(gen / "result.json"),
            }
        )
    immutable(
        NEW / "FULL_MERGE_PROVENANCE.json",
        {
            "replacement_count": 144,
            "unchanged_count": 3141,
            "selection": "Replace every multi-object request; no output or score selection",
            "decomposition": str(CONTROL / "MANUAL_DECOMPOSITION.json"),
            "bindings": bindings,
        },
    )
    report(plan["bundle"], view / "run", view / "scores", NEW / "full_report", ["sitedit"], full)
    print(f"Full R2 report: {NEW / 'full_report'}", flush=True)


if __name__ == "__main__":
    main()
