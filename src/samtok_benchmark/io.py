"""Deterministic manifests and atomic output writes."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    result = []
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{number}: invalid JSON") from exc
                if not isinstance(value, dict):
                    raise ValueError(f"{path}:{number}: expected an object")
                result.append(value)
    return result


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def write_json(path: Path, value) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_jsonl(path: Path, values) -> None:
    atomic_text(path, "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in values))


def asset_path(root: Path, reference: str) -> Path:
    """Release references are portable relative paths, confined to the data root."""
    ref = Path(reference)
    root = Path(root).resolve()
    if ref.is_absolute() or ".." in ref.parts:
        raise ValueError(f"expected a dataset-relative asset path: {reference}")
    path = (root / ref).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"asset escapes dataset root: {reference}")
    return path
