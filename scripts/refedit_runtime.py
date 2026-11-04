#!/usr/bin/env python3
"""Pack and unpack the SITEdit Pass1/S2 virtual environments for a remote (ARNOLD) worker.

``pack`` (run once on the machine whose environments passed the smoke tests) writes an uncompressed tar per
environment next to a JSON descriptor holding its SHA-256, size and package versions. ``unpack`` (run on the remote
worker) verifies the archive SHA-256, extracts it with traversal checks into a node-local directory, and proves with a
CPU-only import that the expected package versions load from inside the unpacked environment.

The environments are uv virtualenvs whose interpreter is ``/usr/bin/python3.11``; the only absolute symlink allowed is
``bin/python -> /usr/bin/python3.11``. They are invoked as ``<env>/bin/python -m ...``, which makes them relocatable
(CPython finds ``pyvenv.cfg`` next to the invoked path). Their editable finders point at the NAS method checkout; the
launcher's PYTHONPATH (the node-local, commit-verified method clone) takes precedence, which ``unpack`` also checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time

ENVIRONMENTS = {
    "v4": {"packages": {"torch": "2.8.0", "transformers": "5.12.1", "peft": "0.20.0"}},
    "pass1": {"packages": {"torch": "2.8.0", "transformers": "5.19.0", "peft": "0.20.0"}},
}
INTERPRETER = "/usr/bin/python3.11"


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(16 << 20), b""):
            value.update(block)
    return value.hexdigest()


def probe(python, packages, method_source=None):
    paths = []
    if method_source:
        paths = [f"{method_source}/src", f"{method_source}/third_party/diffsynth", f"{method_source}/third_party"]
    env = {"PATH": "/usr/bin:/bin", "CUDA_VISIBLE_DEVICES": "", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": os.pathsep.join(paths)}
    code = (
        "import importlib, importlib.metadata as m, json, sys; "
        f"expected = {packages!r}; "
        "actual = {k: m.version(k).split('+')[0] for k in expected}; "
        "assert actual == expected, (actual, expected); "
        "assert sys.version_info[:2] == (3, 11); "
        "files = {}\n"
        "for name in ('samtok_edit21', 'diffsynth', 'samtok'):\n"
        "    try:\n"
        "        module = importlib.import_module(name)\n        files[name] = module.__file__ or list(module.__path__)[0]\n"
        "    except Exception as error:\n"
        "        files[name] = repr(error)\n"
        "import torch; assert not torch.cuda.is_initialized()\n"
        "print(json.dumps({'packages': actual, 'prefix': sys.prefix, 'modules': files}))"
    )
    out = subprocess.run([str(python), "-B", "-c", code], env=env, check=True, capture_output=True, text=True)
    value = json.loads(out.stdout.strip().splitlines()[-1])
    if method_source:
        for name, path in value["modules"].items():
            if not str(Path(path).resolve()).startswith(str(Path(method_source).resolve())):
                raise RuntimeError(f"{name} imports from {path}, not from the verified method clone")
    return value


def pack(name, source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    archive = output / f"env_{name}.tar"
    descriptor = output / f"env_{name}.json"
    if descriptor.exists():
        raise SystemExit(f"Descriptor exists; never overwritten: {descriptor}")
    proof = probe(source / "bin/python", ENVIRONMENTS[name]["packages"])
    output.mkdir(parents=True, exist_ok=True)
    partial = archive.with_name(archive.name + ".partial")
    tick = time.monotonic()
    with tarfile.open(partial, "x", format=tarfile.PAX_FORMAT) as tar:
        tar.add(str(source), arcname=".", recursive=True,
                filter=lambda info: None if info.name.endswith(".pyc") or "/__pycache__" in info.name else info)
    partial.rename(archive)
    value = {"name": name, "archive": str(archive), "sha256": sha256(archive), "bytes": archive.stat().st_size,
             "source": str(source), "interpreter": INTERPRETER, "packages": ENVIRONMENTS[name]["packages"],
             "probe": proof, "packed_seconds": time.monotonic() - tick,
             "packed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with descriptor.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: value[k] for k in ("archive", "sha256", "bytes")}))


def safe_extract(archive, destination):
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:") as tar:
        for member in tar:
            target = (destination / member.name).resolve()
            if not target.is_relative_to(destination):
                raise RuntimeError(f"Unsafe archive member: {member.name}")
            if member.issym():
                link = Path(member.linkname)
                if link.is_absolute():
                    if not (member.name in ("./bin/python", "bin/python") and member.linkname == INTERPRETER):
                        raise RuntimeError(f"Unexpected absolute link: {member.name} -> {member.linkname}")
                elif not (target.parent / link).resolve().is_relative_to(destination):
                    raise RuntimeError(f"Link escapes the environment: {member.name}")
            elif member.islnk():
                if not (destination / member.linkname).resolve().is_relative_to(destination):
                    raise RuntimeError(f"Hard link escapes the environment: {member.name}")
            elif not (member.isfile() or member.isdir()):
                raise RuntimeError(f"Unsupported archive member: {member.name}")
            # Members were validated above; "fully_trusted" keeps the archived modes (3.11.4+ has filters).
            options = {"filter": "fully_trusted"} if hasattr(tarfile, "data_filter") else {}
            tar.extract(member, destination, set_attrs=True, **options)


def unpack(descriptor_path, expected_sha, destination, method_source):
    descriptor_path, destination = Path(descriptor_path), Path(destination)
    if sha256(descriptor_path) != expected_sha:
        raise SystemExit(f"Runtime descriptor changed: {descriptor_path}")
    descriptor = json.loads(descriptor_path.read_text())
    ready = destination / ".refedit_runtime_ready.json"
    if ready.exists():
        if json.loads(ready.read_text())["archive_sha256"] != descriptor["sha256"]:
            raise SystemExit(f"Existing runtime differs; not overwriting: {destination}")
    else:
        if destination.exists() and any(destination.iterdir()):
            raise SystemExit(f"Incomplete existing runtime; inspect before removing: {destination}")
        if not Path(INTERPRETER).is_file():
            raise SystemExit(f"{INTERPRETER} is required by the archived virtualenv")
        archive = Path(descriptor["archive"])
        if archive.stat().st_size != descriptor["bytes"] or sha256(archive) != descriptor["sha256"]:
            raise SystemExit(f"Runtime archive missing, truncated or changed: {archive}")
        tick = time.monotonic()
        safe_extract(archive, destination)
        ready.write_text(json.dumps({"archive_sha256": descriptor["sha256"],
                                     "extract_seconds": time.monotonic() - tick}) + "\n")
    proof = probe(destination / "bin/python", descriptor["packages"], method_source)
    print(json.dumps({"runtime": descriptor["name"], "destination": str(destination), **proof}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pack")
    p.add_argument("--name", choices=sorted(ENVIRONMENTS), required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--output", required=True)
    p = sub.add_parser("unpack")
    p.add_argument("--descriptor", required=True)
    p.add_argument("--descriptor-sha256", required=True)
    p.add_argument("--destination", required=True)
    p.add_argument("--method-source", required=True)
    args = parser.parse_args()
    if args.command == "pack":
        pack(args.name, args.source, args.output)
    else:
        unpack(args.descriptor, args.descriptor_sha256, args.destination, args.method_source)


if __name__ == "__main__":
    sys.exit(main())
