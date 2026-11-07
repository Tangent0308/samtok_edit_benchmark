#!/usr/bin/env python3
"""Publish a clean eval-compbench Git snapshot and immutable launch descriptor on NAS."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[1]
NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def publish(destination, bundle, runtimes):
    destination, bundle, runtimes = map(lambda x: Path(x).resolve(), (destination, bundle, runtimes))
    if any(not p.is_relative_to(NAS) for p in (destination, bundle, runtimes)):
        raise ValueError("All persistent package references must be on NAS")
    if destination.exists():
        raise ValueError("Publish to a new package directory; do not replace READY or prior packages")
    if subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip() != "eval-compbench":
        raise ValueError("Publish only eval-compbench")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO, text=True).strip():
        raise ValueError("Commit all changes before publication")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    remote = subprocess.check_output(["git", "ls-remote", "origin", "refs/heads/eval-compbench"], cwd=REPO, text=True).split()[0]
    if remote != commit:
        raise ValueError("Push the source commit before publication")
    cfg = json.loads((REPO / "configs/external/compbench_full.json").read_text())
    if cfg["scoring"]["vlm"] != "gpt54-paper-v2-confirmed":
        raise ValueError("Confirm the complete scoring protocol before publishing")
    prompts = cfg["scoring"]["vlm_config"]
    if not Path(prompts["prompts"]).resolve().is_relative_to(NAS) or sha(prompts["prompts"]) != prompts["prompts_sha256"]:
        raise ValueError("Scoring prompt path/identity is invalid")
    index = json.loads((bundle / "index.json").read_text())
    if index["scope"] != "full" or len(index["cases"]) != 3481:
        raise ValueError("A full 3,481-row bundle is required")
    destination.mkdir(parents=True)
    archive = destination / "repo.tar"
    with archive.open("xb") as stream:
        subprocess.run(["git", "archive", "--format=tar", commit, "src", "scripts", "configs",
                        "tests", "pyproject.toml", "AGENTS.md"], cwd=REPO, stdout=stream, check=True)
    shutil.copyfile(REPO / "scripts/arnold/compbench_bootstrap.sh", destination / "start.sh")
    shutil.copyfile(REPO / "scripts/compbench_entry.py", destination / "entry.py")
    descriptor = runtimes / "metrics-runtime.json"
    config = destination / "configuration.json"
    config.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    value = {"schema": "compbench.full.ready.v1", "source_commit": commit,
             "bundle": str(bundle), "bundle_digest": index["digest"], "index_sha256": sha(bundle / "index.json"),
             "results_root": cfg["formal_results_root"], "code": {"archive": str(archive), "sha256": sha(archive)},
             "configuration": str(config), "configuration_sha256": sha(config),
             "metrics_runtime": str(descriptor), "metrics_descriptor_sha256": sha(descriptor),
             "entry_sha256": sha(destination / "entry.py"), "start_sha256": sha(destination / "start.sh"),
             "topology": {"workers": 1, "gpus_per_worker": 8}, "judge_status": cfg["scoring"]["vlm"]}
    (destination / "READY.json").write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps({"package": str(destination), "ready_sha256": sha(destination / "READY.json"),
                      "source_commit": commit, "bundle_digest": index["digest"], "results_root": value["results_root"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("destination", "bundle", "runtimes"):
        parser.add_argument("--" + key, required=True)
    publish(**vars(parser.parse_args()))
