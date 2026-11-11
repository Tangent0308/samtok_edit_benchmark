#!/usr/bin/env python3
# ruff: noqa: E402 - isolated CLI explicitly adds the repository source path.
"""Preserve native Pass1 answers and recover only two known JSON punctuation errors.

No prediction is repeated, added, reordered or selected. This entry reuses the
frozen native renderer/editor and objective scorer with separately bound inputs.
"""

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import socket
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from samtok_benchmark.external_refedit.data import immutable, read
from samtok_benchmark.external_compbench.recovery9.parsing import recover_answer
from samtok_benchmark.io import digest, sha256_file

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
BASE = NAS / ".ifbench-tmp/external_additions_20261111/compbench"
CONTROL = BASE / "syntax_recovery"
ORIGINAL_ROOT = NAS / "experiments2/SAMTokEdit/external_compbench/r2_multitarget_manual_20261111"
FINAL_ROOT = ORIGINAL_ROOT / "final"
spec = importlib.util.spec_from_file_location(
    "frozen_completion", BASE / "repo/scripts/complete_external_baselines.py"
)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
old_manual_identity = old.manual_identity


def identity():
    value = old_manual_identity()
    value["syntax_recovery/entry.py"] = sha256_file(__file__)
    value["syntax_recovery/parsing.py"] = sha256_file(
        REPO / "src/samtok_benchmark/external_compbench/recovery9/parsing.py"
    )
    return value


def bind():
    old.CONTROL = CONTROL
    old.ROOTS = dict(old.ROOTS, sitedit=FINAL_ROOT)
    old.manual_identity = identity


def prepare():
    old_plan = read(BASE / "sitedit/PLAN.json")
    old_config = read(BASE / "sitedit/CONFIG.json")
    old.method_path(old_config)
    if old_manual_identity() != old_plan["source_code"]:
        raise ValueError("Native source snapshot changed")
    entries = []
    for cid in old_plan["case_ids"]:
        p = ORIGINAL_ROOT / "run/sitedit/tokens" / cid / "result.json"
        r = read(p)
        if r["identity"]["source_code"] != old_plan["source_code"] or r["status"] != "completed":
            raise ValueError("Only complete native predictions from this frozen run are allowed")
        if r["identity"] != read(p.with_name("ADMITTED.json"))["identity"]:
            raise ValueError("Native prediction admission differs")
        recovery = recover_answer(r["native"]["raw"], r["native"]["request"])
        if set(recovery["parsed"]["spans"]) != {"U1", "U2"}:
            raise ValueError("Each reviewed target must have its own predicted code")
        entries.append(
            {
                "case_id": cid,
                "native_result": str(p),
                "native_sha256": sha256_file(p),
                "recovery": recovery,
            }
        )
    provenance = {
        "schema": "compbench.native.syntax.recovery.v1",
        "entries": entries,
        "rules": ["missing_mask_key_after_label", "duplicated_label_literal"],
        "source": "Existing authorized recovery9.parsing.recover_answer; unchanged rule bytes",
        "policy": "Parse the original answer only; preserve token sequence, labels, order and every original record. "
        "No repeated Pass1 or manual token/region changes.",
        "new_grounder_requests": 0,
        "recoveries": sum(bool(e["recovery"]["repairs"]) for e in entries),
    }
    provenance["digest"] = digest(provenance)
    immutable(CONTROL / "RECOVERY.json", provenance)
    config = copy.deepcopy(old_config)
    config["formal_results_root"] = str(FINAL_ROOT)
    config["benchmark"]["native_answer_syntax_recovery"] = provenance["digest"]
    plan = dict(
        old_plan,
        results_root=str(FINAL_ROOT),
        source_code=identity(),
        scientific_config_digest=digest(old.worker.scientific_config(config)),
    )
    immutable(CONTROL / "sitedit/CONFIG.json", config)
    immutable(CONTROL / "sitedit/PLAN.json", plan)
    immutable(FINAL_ROOT / "CONFIG.json", config)
    for name in ("PLAN.json", "CONFIG.json"):
        immutable(CONTROL / "mirage" / name, read(BASE / "mirage" / name))
    for e in entries:
        tick = time.monotonic()
        r = read(e["native_result"])
        if sha256_file(e["native_result"]) != e["native_sha256"]:
            raise ValueError("Native answer changed")
        native = copy.deepcopy(r["native"])
        native["parsed"] = e["recovery"]["parsed"]
        native["syntax_recovery"] = {
            "repairs": e["recovery"]["repairs"],
            "repaired_text": e["recovery"]["repaired_text"],
            "native_result": e["native_result"],
            "native_sha256": e["native_sha256"],
            "recovery_digest": provenance["digest"],
        }
        for unit in native["units"]:
            unit["token"] = native["parsed"]["spans"][unit["id"]]
            unit["source"] = "pass1_recovered_json" if e["recovery"]["repairs"] else "pass1"
        native["fallback_units"] = 0
        ident = copy.deepcopy(r["identity"])
        ident.pop("digest")
        ident["source_code"] = identity()
        ident["config_digest"] = plan["scientific_config_digest"]
        ident["digest"] = digest(ident)
        dest = FINAL_ROOT / "run/sitedit/tokens" / e["case_id"]
        immutable(
            dest / "ADMITTED.json",
            {
                "identity": ident,
                "operation": "cpu_derived_native_answer",
                "native_result": e["native_result"],
                "native_sha256": e["native_sha256"],
            },
        )
        result = {
            "identity": ident,
            "status": "completed",
            "native": native,
            "operation": "cpu_derived_native_answer",
            "calls": {"grounder_requests": 0, "reused_native_grounder_requests": 1},
            "host": socket.gethostname(),
            "gpu": None,
            "wall_seconds": time.monotonic() - tick,
            "native_generation_record": e["native_result"],
            "native_generation_sha256": e["native_sha256"],
        }
        # A resumed CPU derivation must retain its original measured duration.
        if (dest / "result.json").exists():
            previous = read(dest / "result.json")
            if any(
                previous[k] != result[k] for k in ("identity", "native", "native_generation_sha256")
            ):
                raise ValueError("Derived tokens changed")
        else:
            immutable(dest / "result.json", result)
        immutable(dest / "SYNTAX.json", e["recovery"])
    print(
        json.dumps(
            {
                "derived": len(entries),
                "syntax_recovered": provenance["recoveries"],
                "new_predictions": 0,
                "final_root": str(FINAL_ROOT),
            }
        ),
        flush=True,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["prepare", "run", "score", "report"])
    p.add_argument("--model", choices=["sitedit", "mirage"])
    p.add_argument("--stage", choices=["plan", "edit"])
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=4)
    p.add_argument("--cohort", type=int, choices=[1, 2])
    a = p.parse_args()
    if a.command == "prepare":
        prepare()
    else:
        bind()
        old.execute(a.model, a.command, a.stage, a.shard, a.shards, False, a.cohort)


if __name__ == "__main__":
    main()
