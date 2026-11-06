#!/usr/bin/env python3
"""Publish the four-node MagicBrush entry with an independent scientific baseline seal."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

if not sys.flags.isolated:
    raise SystemExit("Use python -I")
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


FROZEN = [
    "src/samtok_benchmark/external_magicbrush/metrics.py",
    "src/samtok_benchmark/external_magicbrush/scoring.py",
    "src/samtok_benchmark/external_magicbrush/report.py",
    "configs/external/magicbrush.json",
    "configs/external/magicbrush_arnold.template.json",
    "scripts/refedit_stage.py",
    "scripts/refedit_runtime.py",
]


def git(*args):
    return subprocess.check_output(["git", "-C", str(REPO), *args], text=True).strip()


def verify(package, commit, *, payload=True):
    ready = read(Path(package) / "READY.json")
    if ready["source_commit"] != commit or git("rev-parse", "HEAD") != commit:
        raise ValueError("Published source commit differs from checkout/entry")
    if sha(ready["baseline"]) != ready["baseline_sha256"]:
        raise ValueError("Scientific baseline seal changed")
    baseline = read(ready["baseline"])
    if ready["topology"] != {"workers": 4, "gpus_per_worker": 8}:
        raise ValueError("Wrong topology")
    for key in [
        "bundle",
        "bundle_digest",
        "results_root",
        "generation_source_code",
        "arnold_config_template_sha256",
        "estimate_sha256",
    ]:
        if ready[key] != baseline[key]:
            raise ValueError(f"Scientific identity changed: {key}")
    for relative, expected in {
        **ready["generation_source_code"],
        **ready["unchanged_code"],
    }.items():
        if sha(REPO / relative) != expected:
            raise ValueError(f"Tested generation/scoring/configuration changed: {relative}")
    if any(ready["assets"].get(p) != v for p, v in baseline["assets"].items()):
        raise ValueError("Baseline scientific assets were not preserved")
    if payload:
        verify_assets(ready["assets"])
    return {
        "verified": True,
        "assets": len(ready["assets"]),
        "source_commit": commit,
        "topology": ready["topology"],
        "ready_sha256": sha(Path(package) / "READY.json"),
    }


def publish(package, baseline_ready, expected_baseline_sha):
    if git("status", "--porcelain") or git("branch", "--show-current") != "eval-magicbrush":
        raise ValueError("Publish from a clean eval-magicbrush worktree")
    commit = git("rev-parse", "HEAD")
    if git("ls-remote", "origin", "refs/heads/eval-magicbrush").split()[0] != commit:
        raise ValueError("Push the branch before publication")
    package, baseline_ready = Path(package).resolve(), Path(baseline_ready).resolve()
    if not package.is_relative_to(NAS) or not baseline_ready.is_relative_to(NAS):
        raise ValueError("Both packages must be on NAS")
    if sha(baseline_ready) != expected_baseline_sha:
        raise ValueError("Original READY differs from the approved smoke package")
    parent, old = read(baseline_ready), baseline_ready.parent
    unchanged = {}

    for relative in FROZEN:
        original = subprocess.check_output(
            ["git", "-C", str(REPO), "show", f"{parent['source_commit']}:{relative}"]
        )
        unchanged[relative] = hashlib.sha256(original).hexdigest()
        if sha(REPO / relative) != unchanged[relative]:
            raise ValueError(f"Frozen implementation changed: {relative}")
    for relative, expected in parent["generation_source_code"].items():
        if sha(REPO / relative) != expected:
            raise ValueError(f"Generation changed: {relative}")
    package.mkdir(parents=True, exist_ok=False)
    (package / "bootstrap.sh").write_bytes(
        (REPO / "scripts/arnold/magicbrush_cluster_bootstrap.sh").read_bytes()
    )
    # Preserve scientific paths/bytes, while removing dependencies on retired launch files.
    baseline = {
        k: parent[k]
        for k in [
            "bundle",
            "bundle_digest",
            "results_root",
            "generation_source_code",
            "arnold_config_template_sha256",
            "estimate_sha256",
        ]
    }
    baseline.update(
        schema="magicbrush.scientific-baseline.v1",
        reference_commit=parent["source_commit"],
        reference_ready_sha256=expected_baseline_sha,
        assets={
            p: v
            for p, v in parent["assets"].items()
            if p not in {str(old / "bootstrap.sh"), str(old / "BASELINE.json")}
        },
    )
    with (package / "BASELINE.json").open("x") as stream:
        json.dump(baseline, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    assets = {
        **baseline["assets"],
        str(package / "BASELINE.json"): sha(package / "BASELINE.json"),
        str(package / "bootstrap.sh"): sha(package / "bootstrap.sh"),
    }
    verify_assets(assets)
    ready = {
        **baseline,
        "schema": "magicbrush.ready.cluster.v1",
        "source_commit": commit,
        "topology": {"workers": 4, "gpus_per_worker": 8},
        "baseline": str(package / "BASELINE.json"),
        "baseline_sha256": sha(package / "BASELINE.json"),
        "estimate": parent.get("estimate", str(old / "ESTIMATE.json")),
        "overlap": parent.get("overlap", str(old / "overlap/OVERLAP.json")),
        "unchanged_code": unchanged,
        "assets": assets,
    }
    with (package / "READY.json").open("x") as stream:
        json.dump(ready, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    ready_sha = sha(package / "READY.json")
    bootstrap_sha = sha(package / "bootstrap.sh")
    start = f"""#!/usr/bin/env bash
set -Eeuo pipefail
: "${{MAGICBRUSH_ATTEMPT:?Set a new attempt id}}"
export MAGICBRUSH_PACKAGE={shlex.quote(str(package))}
export MAGICBRUSH_COMMIT={commit}
[[ "$(sha256sum "$MAGICBRUSH_PACKAGE/READY.json" | cut -d' ' -f1)" == {ready_sha} ]] || exit 2
[[ "$(sha256sum "$MAGICBRUSH_PACKAGE/bootstrap.sh" | cut -d' ' -f1)" == {bootstrap_sha} ]] || exit 2
exec bash "$MAGICBRUSH_PACKAGE/bootstrap.sh" "$@"
"""
    with (package / "start.sh").open("x") as stream:
        stream.write(start)
    return verify(package, commit, payload=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["publish", "verify"])
    p.add_argument("--package", required=True)
    p.add_argument("--baseline-ready")
    p.add_argument("--baseline-ready-sha256")
    p.add_argument("--commit")
    args = p.parse_args()
    result = (
        publish(args.package, args.baseline_ready, args.baseline_ready_sha256)
        if args.command == "publish"
        else verify(args.package, args.commit)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
