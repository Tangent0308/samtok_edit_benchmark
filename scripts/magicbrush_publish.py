#!/usr/bin/env python3
"""Publish/verify a NAS-only MagicBrush handoff after successful smoke tests; standard library only."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_assets(entries):
    def one(item):
        path, expected = item
        if not Path(path).resolve().is_relative_to(NAS):
            raise ValueError(f"Package references a node-local file: {path}")
        if sha(path) != expected:
            raise ValueError(f"Package asset changed: {path}")

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(one, entries.items()))


def publish(package):
    if subprocess.check_output(
        ["git", "-C", str(REPO), "status", "--porcelain"], text=True
    ).strip():
        raise ValueError("Commit all branch changes before publishing")
    branch = subprocess.check_output(
        ["git", "-C", str(REPO), "branch", "--show-current"], text=True
    ).strip()
    if branch != "eval-magicbrush":
        raise ValueError("Publish only from eval-magicbrush")
    commit = subprocess.check_output(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
    ).strip()
    package = Path(package).resolve()
    bundle = package / "bundle"
    index = read(bundle / "index.json")
    estimate = read(package / "ESTIMATE.json")
    if not estimate["all_methods_smoke_passed"] or estimate["bundle_digest"] != index["digest"]:
        raise ValueError("Successful matching smoke tests are required before READY")
    for relative, expected in estimate["source_code"].items():
        if sha(REPO / relative) != expected:
            raise ValueError("Generation code changed after smoke")
    entries = {}
    entries[str(package / "bootstrap.sh")] = sha(REPO / "scripts/arnold/magicbrush_bootstrap.sh")
    for c in index["cases"]:
        entries[c["public"]] = c["public_sha256"]
        public = read(c["public"])
        for key in ["source", "mask", "annotation"]:
            if public[key]:
                entries[public[key]["path"]] = public[key]["sha256"]
        if c["canonical_mask"]:
            entries[c["canonical_mask"]["path"]] = c["canonical_mask"]["sha256"]
        geometry = Path(public["source"]["path"]).parent / "geometry.json"
        entries[str(geometry)] = sha(geometry)
    entries[str(bundle / "private/evaluation.json")] = index["evaluation_sha256"]
    for row in read(bundle / "private/evaluation.json"):
        for key in ["source", "mask", "target"]:
            entries[row[key]["path"]] = row[key]["sha256"]
    parity = read(package / "METRIC_PARITY.json")
    for key, relative in [
        ("code_sha256", "src/samtok_benchmark/external_magicbrush/metrics.py"),
        ("scoring_code_sha256", "src/samtok_benchmark/external_magicbrush/scoring.py"),
    ]:
        if parity["scorer_identity"][key] != sha(REPO / relative):
            raise ValueError("Scoring code changed after metric parity validation")
    if parity["check_script_sha256"] != sha(REPO / "scripts/magicbrush_metric_check.py"):
        raise ValueError("Metric validation script changed")
    for relative in [
        "bundle/index.json",
        "overlap/OVERLAP.json",
        "METRIC_PARITY.json",
        "ESTIMATE.json",
        "assets/DejaVuSans.ttf",
        "assets/FONT_SOURCE.json",
        "assets/FONT_LICENSE.txt",
    ]:
        entries[str(package / relative)] = sha(package / relative)
    config = read(REPO / "configs/external/magicbrush.json")
    # These are trusted runtime descriptors from the read-only RefEdit template. Bind the mutable
    # NAS files as well as the archived-payload checks performed by the staging scripts.
    for relative in [
        ".ifbench-tmp/fairness-v2-dev20-20261030/bootstrap.json",
        ".ifbench-tmp/external_bench_20261102/refedit_runtimes/env_v4.json",
        ".ifbench-tmp/external_bench_20261102/refedit_runtimes/env_pass1.json",
    ]:
        path = NAS / relative
        entries[str(path)] = sha(path)
    for name in ["clip", "dino"]:
        root = Path(config["metrics"]["root"]) / name
        proof = read(root / "SOURCE.json")
        entries[str(root / "SOURCE.json")] = sha(root / "SOURCE.json")
        for item in proof["files"]:
            entries[str(root / item["path"])] = item["sha256"]
    verify_assets(entries)
    ready = {
        "schema": "magicbrush.ready.v1",
        "source_commit": commit,
        "bundle_digest": index["digest"],
        "bundle": str(bundle),
        "assets": entries,
        "results_root": config["formal_results_root"] + "/run_001",
        "estimate_sha256": sha(package / "ESTIMATE.json"),
        "generation_source_code": estimate["source_code"],
        "arnold_config_template_sha256": sha(
            REPO / "configs/external/magicbrush_arnold.template.json"
        ),
    }
    with (package / "READY.json").open("x") as stream:
        json.dump(ready, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return {
        "source_commit": commit,
        "bundle_digest": index["digest"],
        "ready_sha256": sha(package / "READY.json"),
        "assets": len(entries),
    }


def verify(package, commit):
    ready = read(Path(package) / "READY.json")
    if ready["source_commit"] != commit:
        raise ValueError("Entrypoint commit differs from published READY")
    for relative, expected in ready["generation_source_code"].items():
        if sha(REPO / relative) != expected:
            raise ValueError("Published generation source differs")
    if (
        sha(REPO / "configs/external/magicbrush_arnold.template.json")
        != ready["arnold_config_template_sha256"]
    ):
        raise ValueError("Published run configuration differs")
    verify_assets(ready["assets"])
    return {"verified": True, "assets": len(ready["assets"]), "source_commit": commit}


def main():
    if not sys.flags.isolated:
        raise SystemExit("Use python -I")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["publish", "verify"])
    parser.add_argument("--package", required=True)
    parser.add_argument("--commit")
    args = parser.parse_args()
    result = (
        publish(args.package) if args.command == "publish" else verify(args.package, args.commit)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
