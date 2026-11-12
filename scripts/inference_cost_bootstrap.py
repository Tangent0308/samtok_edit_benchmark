#!/usr/bin/env python3
"""Offline, foreground bootstrap for one dedicated eight-H100 profiling worker."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import time


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def extract(archive, destination, skip_python=False):
    """No extraction through links. Only the archived venv interpreter may escape."""
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir(parents=True)
    links = set()
    with tarfile.open(archive, "r:") as source:
        for member in source:
            name = os.path.normpath(member.name)
            if os.path.isabs(name) or name == ".." or name.startswith("../"):
                raise ValueError(f"Unsafe archive member: {member.name}")
            if any(str(p) in links for p in Path(name).parents):
                raise ValueError(f"Archive writes through a link: {member.name}")
            if member.issym() and skip_python and name == "bin/python":
                if member.linkname != "/usr/bin/python3.11":
                    raise ValueError("Unexpected archived interpreter")
                continue
            if member.issym() or member.islnk():
                target = os.path.normpath(
                    os.path.join(os.path.dirname(name), member.linkname)
                    if member.issym()
                    else member.linkname
                )
                if os.path.isabs(target) or target == ".." or target.startswith("../"):
                    raise ValueError(f"Archive link escapes: {member.name}")
                links.add(name)
            elif not (member.isfile() or member.isdir()):
                raise ValueError(f"Unsupported archive entry: {member.name}")
            options = {"filter": "fully_trusted"} if hasattr(tarfile, "data_filter") else {}
            source.extract(member, destination, **options)


def local_archive(archive, expected, cache):
    """Read large NAS archives once; hash while staging, then extract locally."""
    cache = Path(cache)
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        if sha(cache) != expected:
            raise ValueError(f"Local archive changed: {cache}")
        return cache
    partial = cache.with_suffix(".partial")
    h = hashlib.sha256()
    with Path(archive).open("rb") as src, partial.open("xb") as dest:
        for block in iter(lambda: src.read(8 << 20), b""):
            dest.write(block)
            h.update(block)
    if h.hexdigest() != expected:
        raise ValueError(f"Archive hash differs: {archive}")
    partial.rename(cache)
    return cache


def unpack(archive, expected, destination, skip_python=False):
    destination = Path(destination)
    receipt = destination / ".cost_archive.json"
    if receipt.exists():
        if read(receipt)["sha256"] != expected:
            raise ValueError(f"Existing local runtime belongs to another archive: {destination}")
        return
    archive = local_archive(archive, expected, destination.with_suffix(".verified.tar"))
    # A bootstrap interrupted during extraction has only an incomplete local cache.
    # Leave it intact; use a fresh attempt-specific staging directory instead.
    extract(archive, destination, skip_python)
    save(receipt, {"sha256": expected, "unpacked_at": time.time()})
    archive.unlink()  # This bootstrap's verified node-local cache only.


def sit_runtime(descriptor, destination, base, repo, method):
    destination = Path(destination)
    unpack(descriptor["archive"], descriptor["sha256"], destination, skip_python=True)
    for name in ("python", "python3", "python3.11"):
        link = destination / "bin" / name
        if os.path.lexists(link):
            link.unlink()
        link.symlink_to(base / "bin/python3.11")
    (destination / "pyvenv.cfg").write_text(
        f"home = {base}/bin\ninclude-system-site-packages = false\nversion_info = 3.11.2\n"
    )
    wrapper = destination / "python"
    paths = [repo / "src", method / "src", method / "third_party/diffsynth", method / "third_party"]
    q = shlex.quote
    wrapper.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "unset PYTHONHOME PYTHONPATH CPATH CPLUS_INCLUDE_PATH LIBRARY_PATH LD_LIBRARY_PATH\n"
        "export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1\n"
        f"export PYTHONPATH={q(os.pathsep.join(map(str, paths)))}\n"
        f"export LD_LIBRARY_PATH={q(str(base / 'lib'))}:/usr/local/nvidia/lib:/usr/local/nvidia/lib64\n"
        f"export CPATH={q(str(base / 'include'))}\n"
        f'exec {q(str(destination / "bin/python"))} "$@"\n'
    )
    wrapper.chmod(0o755)
    probe = (
        "import importlib.metadata as m,json,torch,sys; "
        f"expected={descriptor['packages']!r}; "
        "actual={n:m.version(n).split('+')[0] for n in expected}; "
        "assert expected==actual,(expected,actual); "
        "from samtok_edit21.evaluation import ifbench; "
        f"assert ifbench.__file__.startswith({str(method)!r}); "
        "assert not torch.cuda.is_initialized(); "
        "print(json.dumps({'packages':actual,'python':sys.version,'module':ifbench.__file__}))"
    )
    done = subprocess.run(
        [str(wrapper), "-B", "-c", probe],
        env=dict(os.environ, CUDA_VISIBLE_DEVICES=""),
        check=True,
        text=True,
        capture_output=True,
        timeout=180,
    )
    return str(wrapper), json.loads(done.stdout.strip().splitlines()[-1])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--attempt", required=True)
    p.add_argument("--validate-only", action="store_true")
    p.add_argument("--smoke-only", action="store_true")
    a = p.parse_args()
    import re

    if not re.fullmatch(r"[A-Za-z0-9_-]+", a.attempt):
        raise ValueError("Unsafe attempt ID")
    package = a.package.resolve()
    ready = read(package / "READY.json")
    output = Path(ready["results_root"])
    startup = output / "bootstrap" / a.attempt
    startup.mkdir(parents=True, exist_ok=False)
    log = (startup / "bootstrap.log").open("a", buffering=1)

    class Tee:
        def __init__(self, stream):
            self.stream = stream

        def write(self, data):
            log.write(data)
            return self.stream.write(data)

        def flush(self):
            log.flush()
            self.stream.flush()

    sys.stdout, sys.stderr = Tee(sys.stdout), Tee(sys.stderr)
    # One owner covers bootstrap as well as generation, across attempts/hosts.
    lock = (output / "launch.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    heartbeat_stop = threading.Event()

    def heartbeat():
        while not heartbeat_stop.is_set():
            save(
                startup / "HEARTBEAT.json",
                {
                    "updated_unix": time.time(),
                    "pid": os.getpid(),
                    "host": socket.gethostname(),
                    "attempt": a.attempt,
                },
            )
            heartbeat_stop.wait(15)

    threading.Thread(target=heartbeat, daemon=True).start()

    def status(stage, **fields):
        value = {
            "stage": stage,
            "attempt": a.attempt,
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "updated_unix": time.time(),
            **fields,
        }
        save(startup / "STATUS.json", value)
        save(output / "STARTUP.json", value)
        print(json.dumps(value, ensure_ascii=False), flush=True)

    try:
        status("verifying_package")
        for name, expected in ready["files"].items():
            if sha(package / name) != expected:
                raise ValueError(f"Published package changed: {name}")
        # Do not reuse any unrelated /tmp tree; a new attempt always has its own cache.
        local = Path("/tmp/ifbench-cost") / ready["plan_digest"][:16] / a.attempt
        local.mkdir(parents=True, exist_ok=False)
        if shutil.disk_usage(local).free < 50 * 2**30:
            raise RuntimeError("At least 50 GiB of free node-local storage is required")
        unpack(package / "code.tar", ready["files"]["code.tar"], local / "repo")
        repo = local / "repo"
        sys.path.insert(0, str(repo / "src"))
        from samtok_benchmark.inference_cost.common import check_idle, gpu_snapshot

        check_idle(gpu_snapshot())
        # Never run eight identical copies of this entry in a multi-worker job.
        for name in ("ARNOLD_WORKER_NUM", "ARNOLD_WORKER_COUNT"):
            if name in os.environ and int(os.environ[name]) != 1:
                raise RuntimeError("Submit one worker with eight GPUs, not a multi-node job")
        plan = read(package / "PLAN.json")
        for path, expected in ready["dependencies"].items():
            if sha(path) != expected:
                raise ValueError(f"Pinned dependency changed: {path}")
        unpack(package / "method.tar", ready["files"]["method.tar"], local / "method")
        from evaluation.protocol_audit.bootstrap_fairness_dev20 import prepare_runtime

        runtime_spec = read(package / "RUNTIMES.json")
        status("restoring_generation_runtime")
        spec = runtime_spec["generation"]
        archive = local_archive(spec["archive"], spec["sha256"], local / "generation.verified.tar")
        generation, _, proof = prepare_runtime(
            "generation", dict(spec, archive=str(archive)), local, repo
        )
        archive.unlink()
        interpreters, proofs = {"generation": str(generation)}, {"generation": proof}
        for name in ("pass1", "v4"):
            status(f"restoring_{name}_runtime")
            python, proof = sit_runtime(
                runtime_spec[name],
                local / name,
                local / "generation/cpython",
                repo,
                local / "method",
            )
            interpreters[name], proofs[name] = python, proof
        runtime = {
            "python": interpreters,
            "proofs": proofs,
            "local_root": str(local),
            "method_source": str(local / "method"),
            "ready_sha256": sha(package / "READY.json"),
        }
        save(startup / "RUNTIME.json", runtime)
        status("controller", plan_digest=plan["digest"], results_root=str(output))
        # Import/call in this foreground process; signal handling remains in the controller.
        from samtok_benchmark.inference_cost.control import run

        run(
            package / "PLAN.json",
            output,
            startup / "RUNTIME.json",
            a.attempt,
            validate_only=a.validate_only,
            smoke_only=a.smoke_only,
        )
        progress_path = (output / "smoke" if a.smoke_only else output) / "PROGRESS.json"
        status(
            "finished", results_root=str(output), controller_status=read(progress_path)["status"]
        )
    except BaseException as error:
        status("failed", error=repr(error))
        raise
    finally:
        heartbeat_stop.set()
        lock.close()


if __name__ == "__main__":
    main()
