"""Verified foreground bootstrap for one native eight-GPU source partition."""

from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import sys
import time

# This file is launched with the system Python before the pinned runtimes exist.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.protocol_audit.bootstrap_fairness_dev20 import (  # noqa: E402
    read,
    save,
    sha,
    checked,
    verify_aliases,
    check_gpus,
    prepare_runtime,
)


def local_source_alias(item):
    """Materialize the pinned upstream sources locally without rewriting paths."""
    alias, target = Path(item["alias"]), Path(item["target"])
    if not alias.is_absolute() or not target.is_absolute() or not item.get("files"):
        raise ValueError("Expected absolute source alias with a nonempty manifest")
    for relative in item["files"]:
        path = Path(relative)
        if not path.parts or path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe upstream source member")
    if os.path.lexists(alias):
        if alias.resolve().is_relative_to(Path("/mnt")):
            raise RuntimeError(
                f"Source alias executes shared code: {alias}; use a fresh worker container"
            )
        for relative, expected in item["files"].items():
            checked(alias / relative, expected)
        return {"alias": str(alias), "status": "verified-node-local", "target": str(target)}
    # A failed copy remains evidence; never overwrite an existing source tree.
    alias.mkdir(parents=True)
    for relative, expected in item["files"].items():
        path = Path(relative)
        checked(target / path, expected)
        output = alias / path
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target / path, output)
        checked(output, expected)
    return {"alias": str(alias), "status": "copied-node-local", "target": str(target)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", required=True, type=Path)
    p.add_argument("--node", type=int, choices=range(4))
    p.add_argument("--validate-only", action="store_true")
    p.add_argument("--status", action="store_true")
    a = p.parse_args()
    bundle = a.bundle.resolve()
    ready = read(bundle / "READY.json")
    if ready.get("schema") != "ifbench-full-release-four-node-v1":
        raise ValueError("Not an authorized full-release bundle")
    if a.status:
        result = {"bundle": str(bundle), "results_root": ready["results_root"], "nodes": {}}
        for n in range(4):
            directory = Path(ready["results_root"]) / "nodes" / f"node-{n}"
            result["nodes"][str(n)] = {
                name: read(directory / name) if (directory / name).exists() else None
                for name in ("progress.json", "COMPLETED.json", "ERROR.json")
            }
        final = Path(ready["results_root"]) / "report/COMPLETED.json"
        result["aggregate"] = read(final) if final.exists() else None
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return
    if a.node is None:
        p.error("--node 0, 1, 2 or 3 is required for execution")
    for key, relative in [
        ("plan_sha256", "plan.json"),
        ("code_manifest_sha256", "code_manifest.json"),
        ("bootstrap_sha256", "bootstrap.json"),
        ("aliases_sha256", "aliases.json"),
        ("entrypoint_sha256", "start.sh"),
    ]:
        checked(bundle / relative, ready[key])
    # The ARNOLD entry stages the byte-identical pinned snapshot under local /tmp.
    repo = Path(__file__).resolve().parents[3]
    files = read(bundle / "code_manifest.json")["files"]
    for relative, expected in files.items():
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("Unsafe source manifest path")
        checked(repo / relative, expected)
    checked(__file__, files["src/evaluation/protocol_audit/bootstrap_full4.py"])
    descriptor = read(bundle / "bootstrap.json")
    work = Path(os.environ.get("IFBENCH_FULL4_WORK", "/tmp/ifbench/full4-runtime-20261031"))
    work.mkdir(parents=True, exist_ok=True)
    lock = (work / "bootstrap.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.set_inheritable(lock.fileno(), True)
    host_lock = Path("/tmp/ifbench/full4-host.lock").open("a")
    fcntl.flock(host_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.set_inheritable(host_lock.fileno(), True)
    if platform.machine() != "x86_64" or tuple(
        int(x) for x in platform.libc_ver()[1].split(".")[:2]
    ) < (2, 36):
        raise RuntimeError("Pinned generation runtime requires x86_64 Linux and glibc >= 2.36")
    gpus = check_gpus(70, 8)
    items = read(bundle / "aliases.json")
    if os.environ.get("IFBENCH_CLUSTER_MANAGED") == "1":
        source_alias = read(bundle / "plan.json")["paths"]["sources"]
        sources = [i for i in items if i["alias"] == source_alias]
        if len(sources) != 1:
            raise ValueError("One pinned upstream source alias is required")
        aliases = [local_source_alias(sources[0])]
        aliases += verify_aliases([i for i in items if i["alias"] != source_alias])
    else:
        aliases = verify_aliases(items)
    proofs, pythons, environments = {}, {}, {}
    for name in ("generation", "judge"):
        pythons[name], environments[name], proofs[name] = prepare_runtime(
            name, descriptor[name], work, repo
        )
    if shutil.which("gcc") is None or shutil.which("g++") is None:
        raise RuntimeError("Native kernels need gcc and g++")
    receipt = {
        "node": a.node,
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "time": time.time(),
        "generation_python": str(pythons["generation"]),
        "judge_python": str(pythons["judge"]),
        "cpu_import_proofs": proofs,
        "aliases": aliases,
        "gpus": gpus,
        "bootstrap_sha256": sha(bundle / "bootstrap.json"),
        "validate_only": a.validate_only,
        "executed_repository": str(repo),
    }
    path = (
        bundle / "validation" / f"node-{a.node}" / f"{socket.gethostname()}-{time.time_ns()}.json"
    )
    save(path, receipt)
    if os.environ.get("IFBENCH_CLUSTER_DIRECTORY"):
        save(
            Path(os.environ["IFBENCH_CLUSTER_DIRECTORY"]) / "nodes" / str(a.node) / "runtime.json",
            receipt,
        )
    env = environments["generation"]
    env.update(
        IFBENCH_GENERATION_PYTHON=str(pythons["generation"]),
        IFBENCH_JUDGE_PYTHON=str(pythons["judge"]),
        IFBENCH_RUNTIME_RECEIPT=str(path),
        PYTHONUNBUFFERED="1",
        TRITON_CACHE_DIR=str(work / "kernels/triton"),
        TORCHINDUCTOR_CACHE_DIR=str(work / "kernels/inductor"),
        TORCH_EXTENSIONS_DIR=str(work / "kernels/extensions"),
        VLLM_CACHE_ROOT=str(work / "kernels/vllm"),
    )
    command = [
        str(pythons["generation"]),
        "-m",
        "samtok_benchmark.ifbench.full_run",
        "--plan",
        str(bundle / "plan.json"),
        "--node",
        str(a.node),
    ]
    if a.validate_only:
        command.append("--validate-only")
    print(
        json.dumps({"node": a.node, "runtime_receipt": str(path), "foreground": True}), flush=True
    )
    os.chdir(repo)
    os.execve(command[0], command, env)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"FULL4 BOOTSTRAP FAILED: {type(error).__name__}: {error}", file=sys.stderr, flush=True
        )
        raise SystemExit(1)
