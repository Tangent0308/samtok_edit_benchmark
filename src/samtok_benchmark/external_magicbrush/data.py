"""Data-only HTTP download and isolated decoding; never import code shipped with data."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
import hashlib
from pathlib import Path
import re
import urllib.request

import numpy as np
from PIL import Image

from samtok_benchmark.io import sha256_file
from samtok_benchmark.external_refedit.data import immutable, read
from . import DATASET, REVISION, OFFICIAL_COMMIT, NUM_TURNS, NUM_SESSIONS

REPO = Path(__file__).resolve().parents[3]


def download(root, workers=2):
    """Only pinned official files; anonymous access, SHA checks, resumable partial files."""
    root = Path(root).resolve()
    manifest = read(REPO / "configs/external/magicbrush_data.json")
    assert manifest["revision"] == REVISION
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    def get(entry):
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe upstream path")
        target = raw / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/{entry['path']}"
        if not target.exists():
            partial = target.with_name(target.name + ".partial")
            offset = partial.stat().st_size if partial.exists() else 0
            headers = {"User-Agent": "if-bench-magicbrush/1"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=600
            ) as response:
                resume = offset and response.status == 206
                if resume and not response.headers.get("Content-Range", "").startswith(
                    f"bytes {offset}-"
                ):
                    raise ValueError("Unexpected partial response")
                with partial.open("ab" if resume else "wb") as stream:
                    for block in iter(lambda: response.read(8 << 20), b""):
                        stream.write(block)
            if partial.stat().st_size != entry["size"]:
                raise ValueError(f"Wrong download size: {entry['path']}")
            expected = (entry.get("lfs") or {}).get("oid")
            if expected and sha256_file(partial) != expected:
                raise ValueError(f"Wrong download hash: {entry['path']}")
            partial.rename(target)
        sha = sha256_file(target)
        if target.stat().st_size != entry["size"] or (
            (entry.get("lfs") or {}).get("oid", sha) != sha
        ):
            raise ValueError(f"Pinned download identity differs: {target}")
        if not entry.get("lfs"):
            b = target.read_bytes()
            if (
                hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest()
                != entry["oid"]
            ):
                raise ValueError(f"Git blob differs: {target}")
        print(f"verified {entry['path']} ({target.stat().st_size} bytes)", flush=True)
        return {
            "path": str(target.relative_to(root)),
            "url": url,
            "bytes": target.stat().st_size,
            "sha256": sha,
            "upstream_lfs_sha256": (entry.get("lfs") or {}).get("oid"),
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        files = list(pool.map(get, manifest["files"]))
    source = {
        "dataset": DATASET,
        "revision": REVISION,
        "split": "test",
        "access": "public; no credentials",
        "license": "CC BY 4.0; underlying COCO source-image rights retained",
        "license_url": f"https://github.com/OSU-NLP-Group/MagicBrush/blob/{OFFICIAL_COMMIT}/LICENSE",
        "official_code_commit": OFFICIAL_COMMIT,
        "files": files,
        "untrusted": "Read using python -I; downloaded programs are never executed.",
    }
    if (root / "SOURCE.json").exists():
        old = read(root / "SOURCE.json")
        assert all(old[k] == v for k, v in source.items())
        return old
    source["downloaded_at"] = datetime.now(timezone.utc).isoformat()
    immutable(root / "SOURCE.json", source)
    return source


def bytes_image(data):
    if not isinstance(data, bytes) or not data or len(data) > 100 << 20:
        raise ValueError("Invalid embedded image bytes")
    with Image.open(BytesIO(data)) as im:
        im.load()
        return im.copy()


def write_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Refusing to overwrite different bytes: {path}")
    else:
        with path.open("xb") as stream:
            stream.write(data)


def extract(root):
    """Preserve original PNG bytes, validate turn chains and official text metadata."""
    import pyarrow.parquet as pq

    root = Path(root).resolve()
    source = read(root / "SOURCE.json")
    if source["revision"] != REVISION:
        raise ValueError("Dataset revision mismatch")
    for f in source["files"]:
        if sha256_file(root / f["path"]) != f["sha256"]:
            raise ValueError(f"Downloaded bytes changed: {f['path']}")
    metadata = {
        name: read(root / "raw/test_metadata" / (name + ".json"))
        for name in ["edit_sessions", "edit_turns", "local_descriptions", "global_descriptions"]
    }
    rows, masks = [], {}
    for item in source["files"]:
        if not item["path"].endswith(".parquet"):
            continue
        parquet = pq.ParquetFile(root / item["path"])
        for batch in parquet.iter_batches(batch_size=8):
            for row in batch.to_pylist():
                if set(row) != {
                    "img_id",
                    "turn_index",
                    "source_img",
                    "mask_img",
                    "instruction",
                    "target_img",
                }:
                    raise ValueError("Unexpected parquet fields")
                sid, turn = row["img_id"], row["turn_index"]
                if (
                    not isinstance(sid, str)
                    or not re.fullmatch(r"[0-9]{1,12}", sid)
                    or turn not in (1, 2, 3)
                ):
                    raise ValueError("Invalid session/turn")
                if not isinstance(row["instruction"], str) or not row["instruction"].strip():
                    raise ValueError("Invalid instruction")
                entry = {
                    "case_id": f"{sid}-{turn}",
                    "session_id": sid,
                    "turn": turn,
                    "instruction": row["instruction"],
                }
                decoded = {}
                for column, kind in [
                    ("source_img", "source"),
                    ("mask_img", "mask"),
                    ("target_img", "target"),
                ]:
                    data = row[column]["bytes"]
                    im = bytes_image(data)
                    path = root / "extracted/images" / sid / f"{turn}-{kind}.png"
                    write_bytes(path, data)
                    entry[kind] = {
                        "path": str(path),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "size": list(im.size),
                        "mode": im.mode,
                    }
                    decoded[kind] = im
                if (
                    decoded["source"].size not in {(500, 500), (1024, 1024)}
                    or decoded["mask"].size != (1024, 1024)
                    or decoded["target"].size != (1024, 1024)
                ):
                    raise ValueError(f"Unexpected official image dimensions: {entry['case_id']}")
                a = np.asarray(decoded["mask"].convert("RGBA").getchannel("A"))
                signature = (
                    decoded["mask"].mode,
                    int(a.min()),
                    int(a.max()),
                    bool((a < 128).any()),
                )
                masks[str(signature)] = masks.get(str(signature), 0) + 1
                target_name = f"{sid}-output{turn}.png"
                expected = metadata["edit_sessions"][sid][turn - 1]
                if (
                    expected["output"] != target_name
                    or expected["instruction"] != row["instruction"]
                ):
                    raise ValueError(
                        f"Parquet/official instruction metadata differ: {entry['case_id']}"
                    )
                entry["local_description"] = metadata["local_descriptions"][sid][target_name]
                entry["global_description"] = metadata["global_descriptions"][sid][target_name]
                if not isinstance(entry["local_description"], str):
                    raise ValueError(f"Non-string local description: {entry['case_id']}")
                rows.append(entry)
    if len(rows) != NUM_TURNS or len({r["case_id"] for r in rows}) != NUM_TURNS:
        raise ValueError("Expected exactly 1,053 unique test turns")
    sessions = {}
    for row in rows:
        sessions.setdefault(row["session_id"], []).append(row)
    if len(sessions) != NUM_SESSIONS:
        raise ValueError("Expected exactly 535 test sessions")
    if sorted(metadata["edit_turns"], key=lambda r: r["output"]) != sorted(
        [r for values in metadata["edit_sessions"].values() for r in values],
        key=lambda r: r["output"],
    ):
        raise ValueError("Official flat/session metadata differ")
    for sid, turns in sessions.items():
        turns.sort(key=lambda r: r["turn"])
        if [r["turn"] for r in turns] != list(range(1, len(turns) + 1)):
            raise ValueError(f"Non-contiguous turns: {sid}")
        for previous, current in zip(turns, turns[1:]):
            with (
                Image.open(previous["target"]["path"]) as a,
                Image.open(current["source"]["path"]) as b,
            ):
                if a.convert("RGB").tobytes() != b.convert("RGB").tobytes():
                    raise ValueError(f"Independent-turn GT chain mismatch: {sid}")
    rows.sort(key=lambda r: (int(r["session_id"]), r["turn"]))
    immutable(root / "extracted/turns.json", rows)
    receipt = {
        "source_sha256": sha256_file(root / "SOURCE.json"),
        "turns": len(rows),
        "sessions": len(sessions),
        "turn_count_distribution": {
            str(k): sum(len(t) == k for t in sessions.values()) for k in (1, 2, 3)
        },
        "empty_local_descriptions": [r["case_id"] for r in rows if not r["local_description"]],
        "mask_encodings": masks,
        "turns_sha256": sha256_file(root / "extracted/turns.json"),
    }
    immutable(root / "extracted/EXTRACT.json", receipt)
    return receipt


def load_turns(root, assets=False):
    root = Path(root)
    proof = read(root / "extracted/EXTRACT.json")
    path = root / "extracted/turns.json"
    if sha256_file(path) != proof["turns_sha256"]:
        raise ValueError("Extracted annotations changed")
    rows = read(path)
    if assets:
        for row in rows:
            for k in ("source", "mask", "target"):
                if sha256_file(row[k]["path"]) != row[k]["sha256"]:
                    raise ValueError("Extracted image changed")
    return rows
