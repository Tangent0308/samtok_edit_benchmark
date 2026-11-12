#!/usr/bin/env python3
"""Prepare an immutable offline NAS package; this command never initializes CUDA."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from samtok_benchmark.inference_cost.common import digest, read, save, sha  # noqa: E402
from samtok_benchmark.inference_cost.prepare import prepare  # noqa: E402


def git(directory, *args):
    return subprocess.check_output(["git", "-C", str(directory), *args], text=True).strip()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("package", "results", "bundle", "sit-run", "method-source", "runtime-descriptors"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    if git(REPO, "status", "--porcelain"):
        raise RuntimeError("Commit the profiling code before publishing its snapshot")
    if git(a.method_source, "rev-parse", "HEAD") != "8beaffbd24a773cb7441948df57e65c576e31126":
        raise ValueError("SITEdit must be the approved R2 source revision")
    if git(a.method_source, "status", "--porcelain"):
        raise ValueError("SITEdit source has uncommitted changes")
    package = a.package.resolve()
    if not str(package).startswith("/mnt/") or not str(a.results.resolve()).startswith("/mnt/"):
        raise ValueError("Package and outputs must be on the shared NAS")
    package.mkdir(parents=True, exist_ok=False)
    source_commit = git(REPO, "rev-parse", "HEAD")
    plan = prepare(a.bundle, a.sit_run, a.method_source, package / "PLAN.base.json")
    plan["source_commit"] = source_commit
    plan["digest"] = digest({k: v for k, v in plan.items() if k != "digest"})
    save(package / "PLAN.json", plan, immutable=True)
    (package / "PLAN.base.json").unlink()
    paths = [
        "src",
        "scripts/inference_cost.py",
        "scripts/inference_cost_bootstrap.py",
        "scripts/inference_cost_start.sh",
        "scripts/publish_inference_cost.py",
        "docs/INFERENCE_COST.md",
        "tests/test_inference_cost.py",
        "pyproject.toml",
    ]
    with (package / "code.tar").open("xb") as out:
        subprocess.run(
            ["git", "-C", str(REPO), "archive", source_commit, *paths], stdout=out, check=True
        )
    with (package / "method.tar").open("xb") as out:
        subprocess.run(
            [
                "git",
                "-C",
                str(a.method_source),
                "archive",
                plan["method_commit"],
                "src",
                "third_party",
                "configs/ifbench/main_row.json",
            ],
            stdout=out,
            check=True,
        )
    shutil.copyfile(REPO / "scripts/inference_cost_bootstrap.py", package / "bootstrap.py")
    shutil.copyfile(REPO / "scripts/inference_cost_start.sh", package / "start.sh")
    shutil.copyfile(REPO / "docs/INFERENCE_COST.md", package / "README.md")
    shutil.copyfile(REPO / "docs/USAGE.md", package / "USAGE.md")
    (package / "start.sh").chmod(0o755)
    runtimes = {"generation": read(a.bundle / "bootstrap.json")["generation"]}
    for name in ("v4", "pass1"):
        runtimes[name] = read(a.runtime_descriptors / f"env_{name}.json")
    for name, spec in runtimes.items():
        if Path(spec["archive"]).stat().st_size != spec["bytes"]:
            raise ValueError(f"Runtime archive missing/truncated: {name}")
    save(package / "RUNTIMES.json", runtimes, immutable=True)
    dependencies = {}
    # All reused native source files are pinned by the completed benchmark's manifest.
    aliases = Path(plan["baseline_config"]["configuration_reference"]).parent / "aliases.json"
    dependencies[str(aliases)] = sha(aliases)
    source = plan["baseline_config"]["paths"]["sources"]
    for alias in read(aliases):
        if alias["alias"] == source:
            for relative, expected in alias["files"].items():
                path = Path(source) / relative
                if sha(path) != expected:
                    raise ValueError(f"Native source differs from the frozen benchmark: {path}")
                dependencies[str(path)] = expected
    # New and frozen benchmark wrappers must agree byte-for-byte on model behavior.
    frozen = [
        "samtok_benchmark/ifbench/" + n + ".py"
        for n in [
            "fairness_dev_worker",
            "smoke_adapters",
            "smoke_suite",
            "fairness_dev_revision",
            "public",
            "canvas",
        ]
    ]
    frozen.append("evaluation/protocol_audit/fairness_flux3_replan.py")
    frozen_proof = {}
    for path in frozen:
        if sha(REPO / "src" / path) != sha(a.bundle / "repo/src" / path):
            raise ValueError(f"Frozen model interface differs: {path}")
        frozen_proof[path] = sha(REPO / "src" / path)
    # Explicitly bind both trained adapters, including CodeInjector tensors.
    for name in ("pass1_adapter", "dit_adapter"):
        for path in sorted(Path(plan["method"][name]).rglob("*")):
            if path.is_file() and path.suffix in {".json", ".safetensors", ".bin", ".pt"}:
                dependencies[str(path)] = sha(path)
    save(package / "FROZEN_MODEL_INTERFACES.json", frozen_proof, immutable=True)
    ready = {
        "schema": "ifbench.inference-cost.ready.v1",
        "source_commit": source_commit,
        "method_commit": plan["method_commit"],
        "plan_digest": plan["digest"],
        "results_root": str(a.results.resolve()),
        "gpu_validation": "pending_remote_warmup",
        "files": {str(f.relative_to(package)): sha(f) for f in package.iterdir() if f.is_file()},
        "dependencies": dependencies,
        "runtime_archive_check": "size checked at publication; SHA256 verified before extraction on the worker",
    }
    save(package / "READY.json", ready, immutable=True)
    print(
        json.dumps(
            {
                "package": str(package),
                "results_root": ready["results_root"],
                "source_commit": source_commit,
                "plan_digest": plan["digest"],
                "ready_sha256": sha(package / "READY.json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
