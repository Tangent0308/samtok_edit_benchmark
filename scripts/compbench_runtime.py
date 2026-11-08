#!/usr/bin/env python3
"""Archive the tested CPU metrics runtime; relocate only interpreter links on the remote node."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def probe(python):
    code = ("import importlib.metadata as m,json,torch; "
            "print(json.dumps({k:m.version(k) for k in "
            "('torch','torchvision','transformers','Pillow','numpy','torchmetrics','lpips','pyarrow','openai')})); "
            "assert not torch.cuda.is_initialized()")
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="", PYTHONNOUSERSITE="1", PYTHONPATH="")
    return json.loads(subprocess.check_output([str(python), "-I", "-c", code], env=env, text=True))


def pack(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    descriptor = destination / "metrics-runtime.json"
    if descriptor.exists():
        value = json.loads(descriptor.read_text())
        if sha(value["archive"]) != value["sha256"]:
            raise ValueError("Published archive changed")
        print(json.dumps(value))
        return
    packages = probe(source / "bin/python")
    archive = destination / "metrics-runtime.tar"
    tick = time.monotonic()

    def keep(member):
        name = member.name.removeprefix("./")
        if name in ("bin/python", "bin/python3", "bin/python3.11", "lib64"):
            return None
        if name.endswith(".pyc") or "__pycache__" in Path(name).parts:
            return None
        return member

    with tarfile.open(archive, "x") as stream:
        stream.add(source, arcname=".", filter=keep)
    value = {"archive": str(archive), "sha256": sha(archive), "bytes": archive.stat().st_size,
             "packages": packages, "python": "3.11.2; staged generation CPython", "seconds": time.monotonic() - tick}
    with descriptor.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    print(json.dumps(value))


def unpack(descriptor, expected_sha, destination, interpreter):
    descriptor, destination, interpreter = Path(descriptor), Path(destination), Path(interpreter)
    if sha(descriptor) != expected_sha:
        raise ValueError("Runtime descriptor changed")
    value = json.loads(descriptor.read_text())
    ready = destination / "METRICS_READY.json"
    if ready.exists():
        if json.loads(ready.read_text())["archive_sha256"] != value["sha256"]:
            raise ValueError("Existing metrics runtime differs")
    else:
        if destination.exists() and any(destination.iterdir()):
            raise ValueError("Incomplete runtime directory; preserve it and select a fresh staging path")
        if sha(value["archive"]) != value["sha256"]:
            raise ValueError("Runtime archive changed")
        destination.mkdir(parents=True, exist_ok=True)
        # The pinned generation runtime is CPython 3.11.2 (before tarfile's filter=).
        # Reuse the checked lexical/link traversal guard already used for Pass1/S2.
        spec = importlib.util.spec_from_file_location("runtime_archive_guard", Path(__file__).with_name("refedit_runtime.py"))
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        helper.safe_extract(Path(value["archive"]), destination)
        for name in ("python", "python3", "python3.11"):
            (destination / "bin" / name).symlink_to(interpreter)
        (destination / "lib64").symlink_to("lib")
        (destination / "pyvenv.cfg").write_text(
            f"home = {interpreter.parent}\ninclude-system-site-packages = false\nversion = 3.11.2\nexecutable = {interpreter}\n")
        # The tested small metrics venv shares torch/torchvision with the pinned generation
        # runtime. Redirect that exact dependency to the staged copy, not the old host's /tmp.
        shared = interpreter.parents[2] / "user_site"
        if not (shared / "torch/__init__.py").exists():
            raise ValueError("Staged generation torch dependency is missing")
        site = destination / "lib/python3.11/site-packages"
        (site / "benchmark-runtime.pth").write_text(str(shared) + "\n")
        actual = probe(destination / "bin/python")
        if actual != value["packages"]:
            raise ValueError("Metrics packages differ after staging")
        ready.write_text(json.dumps({"archive_sha256": value["sha256"], "packages": actual}) + "\n")
    if probe(destination / "bin/python") != value["packages"]:
        raise ValueError("Metrics runtime changed")
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="", PYTHONPATH="", PYTHONNOUSERSITE="1")
    origin = subprocess.check_output([str(destination / "bin/python"), "-I", "-c",
             "import torch; print(torch.__file__)"], env=env, text=True).strip()
    if not Path(origin).is_relative_to(interpreter.parents[2] / "user_site"):
        raise ValueError("Metrics torch loaded from outside the staged generation runtime")
    print(f"Metrics runtime ready: {destination}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("pack")
    a.add_argument("--source", required=True)
    a.add_argument("--destination", required=True)
    a = sub.add_parser("unpack")
    for name in ("descriptor", "expected-sha", "destination", "interpreter"):
        a.add_argument("--" + name, required=True)
    args = vars(p.parse_args())
    command = args.pop("command")
    (pack if command == "pack" else unpack)(**args)
