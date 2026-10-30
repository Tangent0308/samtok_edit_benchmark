"""Verified dual-runtime bootstrap; never launches background evaluation workers."""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import time


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def checked(path, digest):
    if not Path(path).is_file() or sha(path) != digest:
        raise RuntimeError(f"Missing or changed file: {path}")


def extract_checked(archive, destination, skip_links=None):
    """Reject archive traversal; accept only relative internal symlinks."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:") as source:
        for member in source:
            if member.name in (skip_links or {}):
                if not member.issym() or member.linkname != skip_links[member.name]:
                    raise RuntimeError(f"Unexpected relocatable interpreter link: {member.name}")
                continue
            target = (destination / member.name).resolve()
            if not target.is_relative_to(destination):
                raise RuntimeError(f"Unsafe archive member: {member.name}")
            if member.issym() or member.islnk():
                link = Path(member.linkname)
                resolved = (
                    (target.parent / link).resolve()
                    if member.issym()
                    else (destination / link).resolve()
                )
                if link.is_absolute() or not resolved.is_relative_to(destination):
                    raise RuntimeError(f"Unsafe archive link: {member.name} -> {member.linkname}")
            if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                raise RuntimeError(f"Unsupported archive member: {member.name}")
            source.extract(member, destination)


def verify_aliases(items):
    """Validate all inputs before creating any missing alias; never replace paths."""
    checked_items = []
    for item in items:
        alias, target = Path(item["alias"]), Path(item["target"])
        if not alias.is_absolute() or not target.is_absolute() or not target.exists():
            raise RuntimeError(f"Alias needs absolute existing target: {item}")
        files = item.get("files", {})
        if not files:
            raise RuntimeError(f"Alias needs a nonempty expected file manifest: {alias}")
        for relative, digest in files.items():
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise RuntimeError(f"Unsafe alias member: {relative}")
            checked(target / relative if relative else target, digest)
        exists = os.path.lexists(alias)
        if exists:
            if alias.is_symlink() and alias.resolve() != target.resolve():
                raise RuntimeError(f"Existing alias points elsewhere; refusing overwrite: {alias}")
            for relative, digest in files.items():
                checked(alias / relative if relative else alias, digest)
        checked_items.append((alias, target, exists))
    for alias, target, exists in checked_items:
        if not exists:
            alias.parent.mkdir(parents=True, exist_ok=True)
            alias.symlink_to(target, target_is_directory=target.is_dir())
    return [
        {"alias": str(a), "target": str(t), "status": "verified-existing" if e else "created"}
        for a, t, e in checked_items
    ]


def runtime_environment(runtime, repo):
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.update(
        PYTHONNOUSERSITE="1",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONPATH=str(repo),
        OMP_NUM_THREADS="4",
        TOKENIZERS_PARALLELISM="false",
        VLLM_WORKER_MULTIPROC_METHOD="spawn",
    )
    env["PATH"] = str(runtime / "env/bin") + ":" + env.get("PATH", "")
    library = runtime / "cpython/lib"
    if library.is_dir():
        env["LD_LIBRARY_PATH"] = str(library) + (
            ":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else ""
        )
        env["CPATH"] = str(runtime / "cpython/include") + (
            ":" + env["CPATH"] if env.get("CPATH") else ""
        )
    return env


def write_wrapper(name, destination, descriptor, repo):
    """Each child gets only its own Python ABI, libraries and package search path."""
    real_python = destination / descriptor["python"]
    base = destination / ("cpython" if name == "generation" else "cpython-3.12.13-linux-x86_64-gnu")
    bin_dir = real_python.parent
    wrapper = destination / "python"
    quote = shlex.quote
    content = (
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "unset PYTHONHOME PYTHONPATH CPATH CPLUS_INCLUDE_PATH LIBRARY_PATH LD_LIBRARY_PATH\n"
        "export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1\n"
        f"export PYTHONPATH={quote(str(repo))}\n"
        f'export PATH={quote(str(bin_dir))}:"$PATH"\n'
        f"export LD_LIBRARY_PATH={quote(str(base / 'lib'))}:/usr/local/nvidia/lib:/usr/local/nvidia/lib64\n"
        f"export LIBRARY_PATH={quote(str(base / 'lib'))}\n"
        f"export CPATH={quote(str(base / 'include'))}\n"
        f"export CPLUS_INCLUDE_PATH={quote(str(base / 'include'))}\n"
        f'exec {quote(str(real_python))} "$@"\n'
    )
    wrapper.write_text(content)
    wrapper.chmod(0o755)
    return wrapper


def probe_python(python, descriptor, env):
    # Third-party imports sometimes probe device capabilities. This process is
    # strictly a CPU preflight; real workers inherit the original visible GPUs.
    env = dict(env, CUDA_VISIBLE_DEVICES="", PYTORCH_NVML_BASED_CUDA_CHECK="1")
    modules = descriptor["imports"]
    program = (
        "import importlib,importlib.metadata as m,json,sys; "
        f"mods={modules!r}; [importlib.import_module(n) for n in mods]; "
        f'print(json.dumps({{"version":list(sys.version_info[:3]),"packages":{{n:m.version(n) for n in {list(descriptor["packages"])!r}}},'
        '"module_files":{n:getattr(importlib.import_module(n),"__file__",None) for n in mods},'
        '"cuda_initialized":__import__("torch").cuda.is_initialized()}))'
    )
    result = subprocess.run(
        [str(python), "-c", program], env=env, text=True, capture_output=True, timeout=180
    )
    if result.returncode:
        raise RuntimeError(f"CPU import preflight failed for {python}:\n{result.stderr[-6000:]}")
    try:
        data = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError) as exc:
        raise RuntimeError(f"Invalid CPU preflight result: {result.stdout[-2000:]}") from exc
    if (
        data["version"] != descriptor["python_version"]
        or data["packages"] != descriptor["packages"]
    ):
        raise RuntimeError(f"Runtime versions differ: {data}")
    if data["cuda_initialized"]:
        raise RuntimeError("CPU preflight unexpectedly initialized CUDA")
    return data


def prepare_runtime(name, descriptor, work, repo):
    archive = Path(descriptor["archive"])
    destination = work / name
    ready = destination / "runtime.ready.json"
    if ready.exists():
        cached = read(ready)
        if cached["archive_sha256"] != descriptor["sha256"]:
            raise RuntimeError(f"Existing runtime differs; not overwriting: {destination}")
        print(f"Verifying cached {name} runtime.", flush=True)
        for relative, digest in cached.get("imported_module_sha256", {}).items():
            checked(destination / relative, digest)
    else:
        if destination.exists() and any(destination.iterdir()):
            raise RuntimeError(
                f"Incomplete existing runtime; inspect before removing: {destination}"
            )
        if not archive.is_file() or archive.stat().st_size != descriptor["bytes"]:
            raise RuntimeError(f"Missing/truncated runtime archive: {archive}")
        print(f"Verifying {name} archive ({descriptor['bytes']} bytes).", flush=True)
        checked(archive, descriptor["sha256"])
        print(f"Extracting {name} runtime to {destination}.", flush=True)
        skip_links = (
            {
                "ifbench-judge-runtime/bin/python": "/home/tiger/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu/bin/python3.12"
            }
            if name == "judge"
            else None
        )
        extract_checked(archive, destination, skip_links)
        if name == "generation":
            base = destination / "cpython"
            environment = destination / "env"
            (environment / "bin").mkdir(exist_ok=True)
            for filename in ("python", "python3", "python3.11"):
                (environment / "bin" / filename).symlink_to(base / "bin/python3.11")
            (environment / "pyvenv.cfg").write_text(
                f"home = {base}/bin\nimplementation = CPython\nversion_info = 3.11.2\ninclude-system-site-packages = false\n"
            )
            (environment / "lib/python3.11/site-packages/zz_ifbench_vendor.pth").write_text(
                str(destination / "user_site") + "\n" + str(destination / "system_site") + "\n"
            )
        else:
            base = destination / "cpython-3.12.13-linux-x86_64-gnu"
            environment = destination / "ifbench-judge-runtime"
            for filename in ("python", "python3", "python3.12"):
                link = environment / "bin" / filename
                if os.path.lexists(link):
                    link.unlink()
                link.symlink_to(base / "bin/python3.12")
            (environment / "pyvenv.cfg").write_text(
                f"home = {base}/bin\nimplementation = CPython\nversion_info = 3.12.13\ninclude-system-site-packages = false\n"
            )
        save(ready, {"archive_sha256": descriptor["sha256"], "prepared_at": time.time()})
    if descriptor.get("archive_receipt"):
        checked(descriptor["archive_receipt"], descriptor["archive_receipt_sha256"])
    if descriptor.get("payload_manifest"):
        checked(descriptor["payload_manifest"], descriptor["payload_manifest_sha256"])
        payload = read(descriptor["payload_manifest"])
        for entry in payload["files"]:
            checked(destination / entry["path"], entry["sha256"])
    python = write_wrapper(name, destination, descriptor, repo)
    env = runtime_environment(destination, repo)
    print(f"CPU import preflight: {name}.", flush=True)
    proof = probe_python(python, descriptor, env)
    imported = {}
    for filename in proof["module_files"].values():
        if filename:
            path = Path(filename).resolve()
            if not path.is_relative_to(destination.resolve()):
                raise RuntimeError(f"Runtime imported an external package: {path}")
            imported[str(path.relative_to(destination.resolve()))] = sha(path)
    save(
        ready,
        {
            "archive_sha256": descriptor["sha256"],
            "validated_at": time.time(),
            "imported_module_sha256": imported,
        },
    )
    return python, env, proof


def check_gpus(min_free_gib=70, required=8):
    query = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.free,uuid",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = [
        dict(zip(("index", "name", "total_mib", "free_mib", "uuid"), (v.strip() for v in row)))
        for row in csv.reader(query.stdout.splitlines())
    ]
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if visible is not None:
        selected = [x.strip() for x in visible.split(",") if x.strip()]
        rows = [r for r in rows if r["index"] in selected or r["uuid"] in selected]
    if len(rows) != required:
        raise RuntimeError(
            f"Expected {required} visible GPUs, found {len(rows)}; CUDA_VISIBLE_DEVICES={visible!r}"
        )
    bad = [
        r
        for r in rows
        if "H100" not in r["name"]
        or float(r["total_mib"]) < 79 * 1024
        or float(r["free_mib"]) < min_free_gib * 1024
    ]
    if bad:
        raise RuntimeError(
            f"Need H100 80GB with >= {min_free_gib} GiB free each; no processes were killed: {bad}"
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--runtime-only",
        action="store_true",
        help="CPU runtime preparation/import checks only; no aliases/GPU checks/evaluation",
    )
    modes.add_argument(
        "--validate-only",
        action="store_true",
        help="Full startup preflight, without launching the evaluation coordinator",
    )
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    descriptor = read(bundle / "bootstrap.json")
    repo = bundle / "repo"
    work = Path(
        os.environ.get("IFBENCH_DEV20_WORK", "/tmp/ifbench/fairness-dev20-runtime-20261030")
    )
    work.mkdir(parents=True, exist_ok=True)
    lock = (work / "bootstrap.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError("Another foreground dev20 launcher is active on this machine") from exc
    os.set_inheritable(lock.fileno(), True)
    if platform.machine() != "x86_64" or tuple(
        int(x) for x in platform.libc_ver()[1].split(".")[:2]
    ) < (2, 36):
        raise RuntimeError("Generation runtime requires x86_64 Linux with glibc >= 2.36")
    if not args.runtime_only:
        ready = read(bundle / "READY.json")
        for field, relative in [
            ("bootstrap_sha256", "bootstrap.json"),
            ("plan_sha256", "plan.json"),
            ("aliases_sha256", "aliases.json"),
            ("code_manifest_sha256", "code_manifest.json"),
        ]:
            checked(bundle / relative, ready[field])
        package_files = read(bundle / "code_manifest.json")["files"]
        required = (
            "samtok_benchmark/ifbench/fairness_dev_run.py",
            "evaluation/protocol_audit/bootstrap_fairness_dev20.py",
            "evaluation/protocol_audit/start_fairness_dev20.sh",
        )
        if not package_files or any(name not in package_files for name in required):
            raise RuntimeError("code_manifest.json must pin the completed runner snapshot")
        for relative, digest in package_files.items():
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise RuntimeError(f"Unsafe code manifest path: {relative}")
            checked(repo / relative, digest)
        checked(
            bundle / "start.sh", package_files["evaluation/protocol_audit/start_fairness_dev20.sh"]
        )
        aliases = verify_aliases(read(bundle / "aliases.json"))
        gpus = check_gpus(
            descriptor.get("min_free_gpu_gib", 70), descriptor.get("required_gpus", 8)
        )
    else:
        aliases, gpus = [], []
    proofs, pythons, environments = {}, {}, {}
    for name in ("generation", "judge"):
        pythons[name], environments[name], proofs[name] = prepare_runtime(
            name, descriptor[name], work, repo
        )
    if shutil.which("gcc") is None or shutil.which("g++") is None:
        raise RuntimeError(
            "Native kernels require gcc and g++; install the matching system build tools before launch"
        )
    receipt = {
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "time": time.time(),
        "generation_python": str(pythons["generation"]),
        "judge_python": str(pythons["judge"]),
        "cpu_import_proofs": proofs,
        "aliases": aliases,
        "gpus": gpus,
        "bootstrap_sha256": sha(bundle / "bootstrap.json"),
        "runtime_only": args.runtime_only,
        "validate_only": args.validate_only,
    }
    receipt_path = bundle / "results/bootstrap" / socket.gethostname() / "runtime_paths.json"
    save(receipt_path, receipt)
    print(json.dumps(receipt, ensure_ascii=False), flush=True)
    if args.runtime_only or args.validate_only:
        return
    env = environments["generation"]
    env.update(
        IFBENCH_GENERATION_PYTHON=str(pythons["generation"]),
        IFBENCH_JUDGE_PYTHON=str(pythons["judge"]),
        IFBENCH_RUNTIME_RECEIPT=str(receipt_path),
    )
    os.chdir(repo)
    command = [
        str(pythons["generation"]),
        "-m",
        "samtok_benchmark.ifbench.fairness_dev_run",
        "--plan",
        str(bundle / "plan.json"),
    ]
    print("Starting the foreground evaluation coordinator.", flush=True)
    os.execve(command[0], command, env)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"BOOTSTRAP FAILED: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
