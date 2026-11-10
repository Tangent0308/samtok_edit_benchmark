#!/usr/bin/env python3
"""Verify R2 weights, saved inference calls and optional pilot PNG parity on CPU."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess

from report_mira_r2 import write_new
import run_mira_r2_full as run


def validate_call(call, result):
    expected = {"num_inference_steps": 40, "seed": 42, "use_kv_cache": True,
                "cfg_scale": 2.0, "mode": "inline", "pass2_te": "raw"}
    if any(call["parameters"].get(k) != v for k, v in expected.items()):
        raise ValueError("Wrong R2 inference parameters")
    # aa5a414 data/protocol.py: TOKEN_SPAN and strip_tokens (no model import).
    negative = re.sub(r"\s*<\|mt_start\|>(?:<\|mt_\d+\|>)*<\|mt_end\|>", "", call["prompt"])
    negative = re.sub(r"[ \t]+([.,;:])", r"\1", negative)
    if negative != call["parameters"]["negative_prompt"]:
        raise ValueError("Negative branch must be the same prompt without region tokens")
    if (call["fallback_units"] != 0 or result["fallback_units"] != 0
            or result["status"] != "completed" or result["native"]["blend"] is not None
            or result["native"]["pass2_te"] != "raw"
            or result["native"]["actual_variant"] != "inline"
            or result["calls"] != {"inference_api_calls": 1, "expected_dit_forwards": 80}):
        raise ValueError("Unexpected native editing flow")


def audit(root, baseline, pilot=None, subset=None):
    config = run.read(root / "run_001/CONFIG.json")
    original = run.read(baseline / "run_001/CONFIG.json")
    restored = deepcopy(config)
    restored["sitedit"]["dit_adapter"] = original["sitedit"]["dit_adapter"]
    if restored != original or config["sitedit"]["dit_adapter"] != str(run.ADAPTER):
        raise ValueError("Configuration does not match the R2 profile")
    provenance = run.read(root / "PROVENANCE.json")
    if run.sha256_file(baseline / "run_001/CONFIG.json") != provenance["original_config_sha256"]:
        raise ValueError("Baseline configuration changed")
    adapter = Path(config["sitedit"]["dit_adapter"])
    hashes = {name: run.sha256_file(adapter / name) for name in provenance["adapter_files"]}
    if hashes != provenance["adapter_files"]:
        raise ValueError("Checkpoint bytes differ from execution receipts")
    metadata = run.read(adapter / "adapter.json")
    if (metadata["grounding"]["update"], metadata["rank"], metadata["alpha"]) != (1000, 32, 32):
        raise ValueError("Expected R2 step 1000 and native LoRA rank/alpha 32/32")
    source = Path(config["paths"]["sitedit_source"])
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    changes = subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True)
    if commit != run.PROFILE["reference"]["method_commit"] or changes.strip():
        raise ValueError("Method source differs from the frozen aa5a414 snapshot")
    plan = run.read(root / "run_001/RUN.json")
    if plan["source_code"] != provenance["source_code"] or run.source_identity() != plan["source_code"]:
        raise ValueError("Native benchmark source changed")
    for name, sha in plan["source_code"].items():
        if run.sha256_file(root / "run_001/source_snapshot" / name) != sha:
            raise ValueError(f"Execution snapshot changed: {name}")

    def check_case(case):
        directory = root / "run_001/sitedit/edit" / case
        call, result = run.read(directory / "call.json"), run.read(directory / "result.json")
        validate_call(call, result)
        if call != run.read(baseline / "run_001/sitedit/edit" / case / "call.json"):
            raise ValueError(f"v4/R2 calls differ: {case}")
        fresh = run.read(root / "run_001/sitedit/tokens" / case / "result.json")
        old = run.read(baseline / "run_001/sitedit/tokens" / case / "result.json")
        if fresh["status"] != "completed" or any(
                fresh["native"][k] != old["native"][k] for k in ("units", "request", "raw", "parsed")):
            raise ValueError(f"v4/R2 Pass1 outputs differ: {case}")
        for label in ("raw", "output"):
            if run.sha256_file(result[f"{label}_image"]) != result[f"{label}_sha256"]:
                raise ValueError(f"Changed {label} image: {case}")
        return {"case_id": case, "Pass1_equal": True, "S2_call_equal": True,
                "raw_sha256": result["raw_sha256"], "output_sha256": result["output_sha256"]}

    run.batch_cases(plan["case_ids"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(check_case, plan["case_ids"]))
    result = {"schema": "mira.r2.inference_audit.v1", "verified": True,
              "sources": len(records), "checkpoint": str(adapter), "adapter_files": hashes,
              "actual_update": metadata["grounding"]["update"], "method_commit": commit,
              "native_source_files": len(plan["source_code"]),
              "all_call_parameters_verified": True, "Pass1_identical_to_v4": len(records),
              "S2_calls_identical_to_v4": len(records), "cases": records}
    if pilot is not None:
        pilot_config = run.read(pilot / "CONFIG.json")
        variant = pilot_config["sitedit"].pop("diagnostic_variant")
        expected = {"gamma": 2.0, "schedule": "constant", "rescale": None,
                    "adapter": str(adapter), "lora_scale": 1.0, "off_step": 0}
        if pilot_config != config or any(variant[k] != v for k, v in expected.items()):
            raise ValueError("Pilot configuration differs from the full R2 run")
        ids = run.read(subset)["case_ids"]
        if len(set(ids)) != len(ids) or not set(ids) <= set(plan["case_ids"]):
            raise ValueError("Invalid pilot source subset")
        for case in ids:
            previous = pilot / "sitedit/edit" / case
            current = root / "run_001/sitedit/edit" / case
            a, b = run.read(previous / "result.json"), run.read(current / "result.json")
            if (run.read(previous / "call.json") != run.read(current / "call.json")
                    or a["raw_sha256"] != b["raw_sha256"]
                    or a["output_sha256"] != b["output_sha256"]
                    or run.sha256_file(a["output_image"]) != b["output_sha256"]):
                raise ValueError(f"Pilot and full-run output differ: {case}")
        result["pilot"] = {"root": str(pilot), "case_ids": ids, "identical_output_pngs": len(ids),
                           "configuration_matches": True}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path, default=run.BASE)
    parser.add_argument("--r2-root", type=Path, default=run.BASE / run.PROFILE["default_run_name"])
    parser.add_argument("--pilot-root", type=Path)
    parser.add_argument("--pilot-subset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.pilot_root) != bool(args.pilot_subset):
        parser.error("Pass both --pilot-root and --pilot-subset, or neither")
    result = audit(args.r2_root, args.baseline_root, args.pilot_root, args.pilot_subset)
    protected = [args.r2_root, args.baseline_root, run.QUALITY]
    if args.pilot_root:
        protected.append(args.pilot_root)
    write_new(args.output, {"AUDIT.json": json.dumps(result, indent=2) + "\n"}, protected)
    print(f"Verified R2 weights and all {result['sources']} inference records: {args.output}")


if __name__ == "__main__":
    main()
