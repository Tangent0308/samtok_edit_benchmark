#!/usr/bin/env python3
"""Node-local staging for the RefEdit-Bench ARNOLD entry: native method sources and the baseline runtime.

* ``sources``: copy the pinned native method sources from NAS and verify every file against the committed manifest
  (``configs/external/refedit_native_sources.json``); an existing staged copy is verified, never overwritten.
* ``generation``: unpack the IF-Bench generation runtime archive (the one the IF-Bench full runs used) with the frozen
  ``prepare_runtime`` helper, which verifies the archive SHA-256, its payload manifest and a CPU import probe.
* ``config``: write the run configuration with node-local paths from the committed template; an existing file must
  match byte for byte, so every attempt of one run uses an identical configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def stage_sources(manifest_path, destination):
    manifest = json.loads(Path(manifest_path).read_text())
    source, destination = Path(manifest["source"]), Path(destination)
    partial = destination.with_name(destination.name + ".partial")
    if not destination.exists():
        if partial.exists():
            shutil.rmtree(partial)
        for relative in manifest["files"]:
            target = partial / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, target)
        partial.rename(destination)
    staged = {str(p.relative_to(destination)) for p in destination.rglob("*")
              if p.is_file() and "__pycache__" not in p.parts}
    if staged != set(manifest["files"]):
        raise SystemExit(f"Staged sources differ in file set: {sorted(staged ^ set(manifest['files']))[:5]}")
    for relative, expected in manifest["files"].items():
        if sha256(destination / relative) != expected:
            raise SystemExit(f"Staged native source changed: {relative}")
    print(json.dumps({"sources": str(destination), "files": len(manifest["files"])}))


def stage_generation(bootstrap, work):
    from evaluation.protocol_audit.bootstrap_fairness_dev20 import prepare_runtime

    descriptor = json.loads(Path(bootstrap).read_text())["generation"]
    python, _, proof = prepare_runtime("generation", descriptor, Path(work), REPO)
    print(json.dumps({"generation": str(Path(work) / "generation/env/bin/python"), "wrapper": str(python),
                      "packages": proof["packages"]}))


def write_config(template, output, root):
    value = json.loads(Path(template).read_text().replace("@RUNTIME_ROOT@", str(root)))
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    output = Path(output)
    if output.exists():
        if output.read_text() != text:
            raise SystemExit(f"Existing run configuration differs: {output}")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text)
    print(json.dumps({"config": str(output), "sha256": sha256(output)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("sources")
    p.add_argument("--manifest", default=str(REPO / "configs/external/refedit_native_sources.json"))
    p.add_argument("--destination", required=True)
    p = sub.add_parser("generation")
    p.add_argument("--bootstrap", default="/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/"
                                          "fairness-v2-dev20-20261030/bootstrap.json")
    p.add_argument("--work", required=True)
    p = sub.add_parser("config")
    p.add_argument("--template", default=str(REPO / "configs/external/refedit_arnold.template.json"))
    p.add_argument("--output", required=True)
    p.add_argument("--root", required=True)
    args = parser.parse_args()
    if args.command == "sources":
        stage_sources(args.manifest, args.destination)
    elif args.command == "generation":
        stage_generation(args.bootstrap, args.work)
    else:
        write_config(args.template, args.output, args.root)


if __name__ == "__main__":
    main()
