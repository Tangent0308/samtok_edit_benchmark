#!/usr/bin/env python3
"""Download the publisher's pinned paper checkpoint; never execute its payload."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
REVISION = "628a7ed05dbb1668b1180ed00e2211d660b0e1f3"
FILENAME = "MagicBrush-epoch-000168.ckpt"
SHA256 = "5fe508a8a3c39ff1d267bcb0d1dcfe6dde41716f7530f46a23dc68ebaaaf46df"
SIZE = 14580610474


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare():
    folder = NAS / "models/pretrained_models/MagicBrushPaper_20261107"
    # The frozen native loader supports this separate, hash-checked local cache.
    local = Path("/tmp/claude_magicbrush_20261105/classic_baselines/downloads/paper") / FILENAME
    local.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://huggingface.co/osunlp/InstructPix2Pix-MagicBrush/resolve/{REVISION}/{FILENAME}"
    if not local.exists():
        part = local.with_suffix(".part")
        h, count, announced = hashlib.sha256(), 0, 0
        with urllib.request.urlopen(url, timeout=120) as response, part.open("wb") as stream:
            while block := response.read(8 * 1024**2):
                stream.write(block)
                h.update(block)
                count += len(block)
                if count - announced >= 1024**3:
                    print(json.dumps({"downloaded_bytes": count, "total_bytes": SIZE}), flush=True)
                    announced = count
        if count != SIZE or h.hexdigest() != SHA256:
            raise ValueError("Official checkpoint size/hash mismatch")
        part.rename(local)
    if local.stat().st_size != SIZE or checksum(local) != SHA256:
        raise ValueError("Local cached checkpoint changed")
    target = folder / "raw" / FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        part = target.with_suffix(".part")
        shutil.copyfile(local, part)
        if checksum(part) != SHA256:
            raise ValueError("Shared checkpoint copy differs")
        part.rename(target)
    elif checksum(target) != SHA256:
        raise ValueError("Existing shared checkpoint differs")
    record = {
        "relative": "paper/" + FILENAME,
        "path": str(target),
        "local_cache": str(local),
        "url": url,
        "repo": "osunlp/InstructPix2Pix-MagicBrush",
        "revision": REVISION,
        "bytes": SIZE,
        "sha256": SHA256,
        "license": "creativeml-openrail-m",
        "checkpoint_role": "paper checkpoint, not the later best checkpoint",
        "untrusted_download": True,
        "not_executed": True,
    }
    manifest = folder / "SOURCE.json"
    if manifest.exists():
        saved = json.loads(manifest.read_text())
        if saved["checkpoint"] != record:
            raise ValueError("Existing manifest differs")
    else:
        with manifest.open("x") as stream:
            json.dump(
                {"checkpoint": record, "downloaded_utc": datetime.now(timezone.utc).isoformat()},
                stream,
                indent=2,
            )
    print(json.dumps({"manifest": str(manifest), "sha256": SHA256}), flush=True)


if __name__ == "__main__":
    prepare()
