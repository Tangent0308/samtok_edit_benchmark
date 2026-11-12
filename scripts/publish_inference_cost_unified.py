#!/usr/bin/env python3
"""Publish a separate controlled-backend package; never invokes a GPU or start.sh."""

import argparse
from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from samtok_benchmark.inference_cost.common import digest, load_plan, read, save, sha  # noqa: E402


def git(*args):
    return subprocess.check_output(["git", "-C", str(REPO), *args], text=True).strip()


def make_plan(parent, package, commit):
    plan = deepcopy(parent)
    plan.update(
        schema="ifbench.inference-cost.unified.v1",
        source_commit=commit,
        parent_plan_digest=parent["digest"],
        capacity_probe=True,
    )
    # Validate the migrated method first, before spending GPU time on other rows.
    plan["models"] = ["sitedit", *[m for m in parent["models"] if m != "sitedit"]]
    plan["baseline_config"]["model_specifications"]["qwen21"]["execution"] = {
        "memory_policy": "resident"
    }
    plan["unified_execution"] = {
        "id": "diffusers_resident_v1",
        "backend": "diffusers",
        "memory_policy": "resident",
        "codebook_path": str(package / "codebook.safetensors"),
        "qwen_shared_pipeline": "UnifiedQwenPipeline / segmented SDPA / pre-final-RMSNorm backbone features",
        "native_method_mechanisms": "RePlan region attention; MIRAGE local/global branches; MICE region binding",
        "compilation": "No new whole-model compilation. Preserve required native RePlan FlexAttention. Qwen/SITEdit reset compiler state per request.",
        "cache": "Native exact KV caches only; no added approximate cache",
        "precision": "BF16 backbones; retain trained FP32 LoRA/injector and native codec precision",
        "quality_result_reuse": False,
        "output_parity_expected": {
            "qwen21": False,
            "sitedit": False,
            "replan": True,
            "mirage": True,
            "mice": True,
        },
        "validation": "Strict trained weight names/shapes, codebook fingerprint, real prompt feature equality, trained DiT prefill/cache numerical checks, one successful warmup per active worker",
        "numerical_tolerances": {
            "prompt_features_atol": 0,
            "prompt_features_rtol": 0,
            "dit_relative_rmse_max": 0.02,
            "dit_cosine_min": 0.999,
        },
        "sampling": "Retain 40/40/40/4/40 steps, native guidance, native per-method noise generator and condition-image resize area",
    }
    plan["digest"] = digest({k: v for k, v in plan.items() if k != "digest"})
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "parent",
        "package",
        "results",
        "extra",
        "codebook",
        "cpu-validation",
        "gpu-validation",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if git("status", "--porcelain"):
        raise RuntimeError("Commit before publishing")
    package, results = args.package.resolve(), args.results.resolve()
    if not all(str(p).startswith("/mnt/") for p in (package, results)):
        raise ValueError("Package and result roots must be on shared NAS")
    parent_ready = read(args.parent / "READY.json")
    for name, expected in parent_ready["files"].items():
        if sha(args.parent / name) != expected:
            raise ValueError(f"Parent package changed: {name}")
    parent = load_plan(args.parent / "PLAN.json")
    validation = read(args.cpu_validation)
    if validation.get("status") != "passed":
        raise ValueError("CPU numerical/weight audit has not passed")
    for path, expected in validation["source_files"].items():
        if sha(path) != expected:
            raise ValueError(f"Validated source changed: {path}")
    for path, expected in read(args.parent / "FROZEN_MODEL_INTERFACES.json").items():
        if sha(REPO / "src" / path) != expected:
            raise ValueError(f"Frozen native model interface changed: {path}")
    if sha(args.codebook) != validation["codebook_sha256"]:
        raise ValueError("Validated codebook changed")
    gpu_proof = read(args.gpu_validation)
    if gpu_proof.get("status") != "passed" or len(gpu_proof.get("checks", [])) != 4:
        raise ValueError("The two migrated editors must pass their two-case GPU smoke")
    if gpu_proof["tested_unified_source_sha256"] != sha(
        REPO / "src/samtok_benchmark/inference_cost/unified.py"
    ):
        raise ValueError("GPU-validated adapter changed")
    expected_smoke = {(m, s) for m in ("sitedit", "qwen21") for s in ("S1", "S3-mask")}
    if {(r["model"], r["setting"]) for r in gpu_proof["checks"]} != expected_smoke:
        raise ValueError("GPU smoke has unexpected model/setting coverage")
    package.mkdir(parents=True, exist_ok=False)
    commit = git("rev-parse", "HEAD")
    plan = make_plan(parent, package, commit)
    save(package / "PLAN.json", plan, immutable=True)
    for path, expected in plan["assets"].items():
        if sha(path) != expected:
            raise ValueError(f"Public asset changed: {path}")
    paths = [
        "src",
        "scripts/inference_cost.py",
        "scripts/inference_cost_bootstrap.py",
        "scripts/inference_cost_start.sh",
        "scripts/publish_inference_cost_unified.py",
        "scripts/validate_inference_cost_unified.py",
        "docs/INFERENCE_COST_UNIFIED.md",
        "tests/test_inference_cost.py",
        "tests/test_inference_cost_unified.py",
        "pyproject.toml",
    ]
    with (package / "code.tar").open("xb") as output:
        subprocess.run(
            ["git", "-C", str(REPO), "archive", commit, *paths], stdout=output, check=True
        )
    for source, destination in [
        (args.parent / "method.tar", "method.tar"),
        (args.parent / "FROZEN_MODEL_INTERFACES.json", "FROZEN_MODEL_INTERFACES.json"),
        (args.codebook, "codebook.safetensors"),
        (args.cpu_validation, "CPU_VALIDATION.json"),
        (args.gpu_validation, "GPU_SMOKE.json"),
        (REPO / "scripts/inference_cost_start.sh", "start.sh"),
        (REPO / "scripts/inference_cost_bootstrap.py", "bootstrap.py"),
        (REPO / "docs/INFERENCE_COST_UNIFIED.md", "README.md"),
    ]:
        shutil.copyfile(source, package / destination)
    (package / "start.sh").chmod(0o755)
    with tarfile.open(package / "extra.tar", "x") as archive:
        for path in sorted(args.extra.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                archive.add(path, arcname=str(path.relative_to(args.extra)), recursive=False)
    specs = read(args.parent / "RUNTIMES.json")
    save(package / "RUNTIMES.json", {k: specs[k] for k in ("generation", "pass1")}, immutable=True)
    save(
        package / "PUBLIC_INPUT_IDENTITY.json",
        {
            "parent_package": str(args.parent),
            "parent_ready_sha256": sha(args.parent / "READY.json"),
            "public_asset_bytes_unchanged": True,
            "asset_count": len(plan["assets"]),
            "assets_digest": digest(plan["assets"]),
            "case_ids": plan["case_ids"],
            "settings": plan["settings"],
            "repetitions": plan["repetitions"],
        },
        immutable=True,
    )
    ready = dict(
        schema="ifbench.inference-cost.unified.ready.v1",
        source_commit=commit,
        method_commit=plan["method_commit"],
        plan_digest=plan["digest"],
        results_root=str(results),
        parent_ready_sha256=sha(args.parent / "READY.json"),
        gpu_validation="pending_remote_gated_execution",
        local_gpu_validation="qwen21_and_sitedit_two_cases_each_passed_not_used_for_timing",
        cpu_validation="passed",
        files={str(p.relative_to(package)): sha(p) for p in package.iterdir() if p.is_file()},
        dependencies={
            **parent_ready["dependencies"],
            **{r["path"]: sha(r["path"]) for r in gpu_proof["checks"]},
        },
    )
    save(package / "READY.json", ready, immutable=True)
    print(
        {
            "package": str(package),
            "results_root": str(results),
            "commit": commit,
            "plan_digest": plan["digest"],
            "ready_sha256": sha(package / "READY.json"),
        }
    )


if __name__ == "__main__":
    main()
