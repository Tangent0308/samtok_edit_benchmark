"""Small immutable-record and integrity helpers; no GPU imports."""

import hashlib
import json
import os
from pathlib import Path
import tempfile


def read(path):
    return json.loads(Path(path).read_text())


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""):
            h.update(b)
    return h.hexdigest()


def checked(path, expected):
    if sha(path) != expected:
        raise ValueError(f"SHA256 mismatch: {path}")


def save(path, value, *, immutable=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    # A complete temp file is linked, rather than exposing a partial admission.
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if immutable:
            try:
                os.link(name, path)
            except FileExistsError:
                if read(path) != value:
                    raise ValueError(f"Refusing to overwrite immutable record: {path}")
        else:
            os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def relative_path(root, name):
    root = Path(root).resolve()
    path = (root / name).resolve()
    if Path(name).is_absolute() or not path.is_relative_to(root):
        raise ValueError(f"Unsafe relative path: {name}")
    return path
