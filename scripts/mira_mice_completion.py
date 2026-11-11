#!/usr/bin/env python3
# ruff: noqa: E402 - isolated CLI explicitly adds the repository source path.
"""Add MICE to frozen MIRA inputs without changing native generation or Judge modules."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from samtok_benchmark.io import digest, sha256_file
from samtok_benchmark.external_mira.data import read, immutable, load_bundle, verify_public
from samtok_benchmark.external_mira import worker, adapters

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
CONTROL = NAS / ".ifbench-tmp/external_additions_20261111/mira_mice"
FORMAL = NAS / "experiments2/SAMTokEdit/external_mira/mice_20261111"
BUNDLE = NAS / ".ifbench-tmp/external_bench_20261102/mira_bundle"
_original_identity = worker.source_identity


def identity():
    values = _original_identity()
    # MICE adds its already frozen text completeness/default checks.
    extra = REPO / "src/samtok_benchmark/ifbench/fairness_dev_revision.py"
    values[str(extra.relative_to(REPO / "src"))] = sha256_file(extra)
    values["scripts/mira_mice_completion.py"] = sha256_file(__file__)
    return values


def native_request(public, config):
    verify_public(public)
    prompt = public["original_instruction"]
    image = public["source"]["path"]
    unit = {"id": "U1", "instruction": prompt, "has_ref": True, "locator": "none", "region": None}
    return {
        "source": public["source"],
        "images": [image],
        "image": image,
        "prompt": prompt,
        "seed": 42,
        "public_input_digest": public["input_digest"],
        "configuration_id": "mira-mice-native-text-v1",
        "parameters": config["model_specifications"]["mice"]["parameters"],
        "public_units": [unit],
        "global_unit_ids": ["U1"],
        "regional_units": [],
        "global_original_prompt": prompt,
        "annotation": None,
        "model_size": public["source"]["size"],
        "resolution_policy": "ifbench.canvas.1mp.v1",
    }


class NativeMice:
    def __init__(self, config, root):
        from samtok_benchmark.ifbench.fairness_dev_worker import NativeBackend

        self.config = config
        self.backend = NativeBackend("mice", "edit", config, root)

    def run(self, public, out, previous=None):
        request = native_request(public, self.config)
        self.backend.reset()
        self.backend.preflight(request, public, out)
        raw, detail = self.backend.run(request, public, out, native_plan=None)
        self.backend.synchronize()
        return raw, {
            "native": detail,
            "calls": dict(self.backend.metrics),
            "memory": self.backend.memory(),
            "environment": self.backend.environment(),
        }


def prepare():
    config = read(NAS / "experiments2/SAMTokEdit/external_mira/run_001/CONFIG.json")
    prior = read(NAS / ".ifbench-tmp/compbench_full5_20261109/package-v1/configuration.json")
    config["model_specifications"]["mice"] = prior["model_specifications"]["mice"]
    config["formal_results_root"] = str(FORMAL)
    index = load_bundle(BUNDLE)
    immutable(CONTROL / "CONFIG.json", config)
    immutable(
        CONTROL / "PLAN.json",
        {
            "schema": "mira.mice.completion.v1",
            "case_ids": [x["case_id"] for x in index["cases"]],
            "models": ["mice"],
            "bundle": str(BUNDLE),
            "bundle_digest": index["digest"],
            "config_digest": digest(config),
            "source_code": identity(),
            "seed": 42,
            "input_policy": "The unchanged original composite instruction and public clean canvas; no GT regions.",
            "gpus": [4, 5, 6, 7],
            "smoke": ["001", "100", "200"],
            "authorization": "User approved MIRA/MICE full completion on four local GPUs on 2026-11-11.",
        },
    )
    for run, ids in (
        (CONTROL / "smoke/run", ["001", "100", "200"]),
        (FORMAL / "run", [x["case_id"] for x in index["cases"]]),
    ):
        immutable(run / "CONFIG.json", config)
        immutable(
            run / "RUN.json",
            {
                "scope": "smoke" if run == CONTROL / "smoke/run" else "full",
                "bundle": str(BUNDLE),
                "bundle_digest": index["digest"],
                "config": str(CONTROL / "CONFIG.json"),
                "config_digest": digest(config),
                "source_code": identity(),
                "case_ids": ids,
                "models": ["mice"],
                "seed": 42,
            },
        )
    judge = read(NAS / "experiments2/SAMTokEdit/external_mira/r2_20261110/JUDGE_CONFIG.json")
    immutable(CONTROL / "JUDGE_CONFIG.json", judge)
    print(
        json.dumps({"prepared": True, "root": str(FORMAL), "cases": len(index["cases"])}),
        flush=True,
    )


def guard():
    gpu = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if gpu not in {"4", "5", "6", "7"}:
        raise ValueError("Use one of local GPUs 4–7")
    used, free = map(
        int,
        subprocess.check_output(
            [
                "nvidia-smi",
                "-i",
                gpu,
                "--query-gpu=memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            text=True,
        )
        .strip()
        .split(","),
    )
    if used > 2300 or free < 70000:
        raise RuntimeError(f"GPU {gpu} is occupied; do not touch other jobs")


def run(shard, shards, smoke):
    guard()
    plan = read(CONTROL / "PLAN.json")
    config = read(CONTROL / "CONFIG.json")
    if plan["source_code"] != identity() or plan["config_digest"] != digest(config):
        raise ValueError("Sealed code/config changed")
    target = CONTROL / "smoke/run" if smoke else FORMAL / "run"
    ids = plan["smoke"] if smoke else plan["case_ids"]
    if shards != 1 and shards != 4:
        raise ValueError("Only one smoke worker or four formal workers")
    if not smoke and (shards != 4 or int(os.environ["CUDA_VISIBLE_DEVICES"]) != 4 + shard):
        raise ValueError("Invalid fixed shard")

    def build(model, stage, cfg, root):
        if (model, stage) != ("mice", "edit"):
            raise ValueError("MICE only")
        return NativeMice(cfg, root)

    with (
        patch.object(worker, "MODELS", (*worker.MODELS, "mice")),
        patch.object(worker, "source_identity", identity),
        patch.object(adapters, "build", build),
    ):
        status = worker.run(
            BUNDLE, CONTROL / "CONFIG.json", target, "mice", "edit", ids, shard, shards
        )
    immutable(
        CONTROL / ("smoke" if smoke else "formal") / f"shard-{shard}-DONE.json",
        {"counts": status, "finished": datetime.now(timezone.utc).isoformat()},
    )
    print(json.dumps(status), flush=True)
    if status.get("fatal"):
        raise SystemExit(2)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["prepare", "run"])
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=4)
    a = ap.parse_args()
    if a.command == "prepare":
        prepare()
    else:
        run(a.shard, a.shards, a.smoke)


if __name__ == "__main__":
    main()
