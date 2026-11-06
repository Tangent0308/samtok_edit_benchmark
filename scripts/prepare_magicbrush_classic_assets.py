"""Fetch only publisher assets, without executing downloaded Python or pickle."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import time
import urllib.request

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
ROOT = NAS / ".ifbench-tmp/magicbrush_classic_20261106"
LOCAL = Path("/tmp/claude_magicbrush_20261105/classic_baselines/downloads")
WEIGHTS = NAS / "models/pretrained_models/MagicBrushClassic_20261106"
for p in (ROOT, LOCAL, WEIGHTS / "raw"):
    p.mkdir(parents=True, exist_ok=True)


def read_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "IF-Bench classic baseline research"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(16 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch_file(spec):
    dest = WEIGHTS / spec["relative"]
    local = LOCAL / spec["relative"]
    proof = dest.with_name(dest.name + ".SOURCE.json")
    if proof.exists():
        old = json.loads(proof.read_text())
        assert old["url"] == spec["url"] and sha(dest) == old["sha256"]
        assert old["bytes"] == spec["bytes"]
        if spec.get("sha256"):
            assert old["sha256"] == spec["sha256"]
        return old
    local.parent.mkdir(parents=True, exist_ok=True)
    partial = local.with_name(local.name + ".partial")
    if not local.exists():
        if spec["bytes"] > 1 << 30:
            parts = LOCAL / (local.name + ".parts")
            parts.mkdir(exist_ok=True)
            block_size = 64 << 20

            def one_part(start):
                end = min(spec["bytes"] - 1, start + block_size - 1)
                path = parts / str(start)
                if path.exists() and path.stat().st_size == end - start + 1:
                    return path
                for retry in range(4):
                    try:
                        req = urllib.request.Request(
                            spec["url"], headers={"Range": f"bytes={start}-{end}"}
                        )
                        with (
                            urllib.request.urlopen(req, timeout=180) as r,
                            path.with_suffix(".partial").open("wb") as f,
                        ):
                            assert (
                                r.status == 206
                                and r.headers["Content-Range"]
                                == f"bytes {start}-{end}/{spec['bytes']}"
                            )
                            for block in iter(lambda: r.read(4 << 20), b""):
                                f.write(block)
                        assert path.with_suffix(".partial").stat().st_size == end - start + 1
                        path.with_suffix(".partial").rename(path)
                        return path
                    except Exception:
                        if retry == 3:
                            raise
                        time.sleep(1 + retry)

            with ThreadPoolExecutor(max_workers=6) as pieces:
                ordered = list(pieces.map(one_part, range(0, spec["bytes"], block_size)))
            with partial.open("wb") as f:
                for path in ordered:
                    with path.open("rb") as src:
                        shutil.copyfileobj(src, f, 16 << 20)
        else:
            with urllib.request.urlopen(spec["url"], timeout=600) as r, partial.open("wb") as f:
                for block in iter(lambda: r.read(16 << 20), b""):
                    f.write(block)
        assert partial.stat().st_size == spec["bytes"], spec
        partial.rename(local)
    digest = sha(local)
    assert local.stat().st_size == spec["bytes"], spec
    if spec.get("sha256"):
        assert digest == spec["sha256"], spec
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        assert sha(dest) == digest, dest
    else:
        writing = dest.with_name(dest.name + ".copying")
        shutil.copyfile(local, writing)
        assert sha(writing) == digest
        writing.rename(dest)
    result = {
        **spec,
        "sha256": digest,
        "path": str(dest),
        "downloaded_utc": datetime.now(timezone.utc).isoformat(),
        "untrusted_download": True,
        "not_executed": True,
    }
    proof.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps({"downloaded": str(dest), "bytes": spec["bytes"], "sha256": digest}), flush=True
    )
    return result


def source_repo(name, repo, commit=None):
    if commit is None:
        commit = json.loads(read_url(f"https://api.github.com/repos/{repo}/commits/HEAD"))["sha"]
    out = ROOT / "deps" / name
    proof = out / "SOURCE.json"
    if proof.exists():
        existing = json.loads(proof.read_text())
        assert existing["commit"] == commit
        return existing
    url = f"https://codeload.github.com/{repo}/tar.gz/{commit}"
    payload = read_url(url)
    raw = LOCAL / f"{name}-{commit}.tar.gz"
    raw.write_bytes(payload)
    entries = []
    out.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member in archive.getmembers():
            nameparts = PurePosixPath(member.name).parts
            assert nameparts and not member.name.startswith("/") and ".." not in nameparts
            if member.isdir():
                continue
            assert member.isfile(), member.name
            assert len(nameparts) > 1
            relative = Path(*nameparts[1:])
            dest = out / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            assert not dest.exists()
            with archive.extractfile(member) as src, dest.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            entries.append(
                {"path": str(relative), "sha256": sha(dest), "bytes": dest.stat().st_size}
            )
    result = {
        "repo": repo,
        "commit": commit,
        "url": url,
        "archive_sha256": hashlib.sha256(payload).hexdigest(),
        "files": entries,
        "path": str(out),
        "not_executed_at_download": True,
    }
    proof.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"source": repo, "commit": commit, "files": len(entries)}), flush=True)
    return result


revision = "31519b5cb02a7fd89b906d88731cd4d6a7bbf88d"
repo = "timbrooks/instruct-pix2pix"
tree = json.loads(
    read_url(
        f"https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=true&expand=false"
    )
)
entries = {r["path"]: r for r in tree if r.get("type") == "file"}
want = [
    "instruct-pix2pix-00-22000.ckpt",
    "text_encoder/config.json",
    "text_encoder/model.safetensors",
    "tokenizer/merges.txt",
    "tokenizer/vocab.json",
    "tokenizer/special_tokens_map.json",
    "tokenizer/tokenizer_config.json",
]
specs = []
for filename in want:
    row = entries[filename]
    relative = (
        "raw/" + filename if filename.endswith(".ckpt") else "text_init/" + Path(filename).name
    )
    specs.append(
        {
            "relative": relative,
            "url": f"https://huggingface.co/{repo}/resolve/{revision}/{filename}",
            "repo": repo,
            "revision": revision,
            "bytes": row["size"],
            "sha256": row.get("lfs", {}).get("oid"),
        }
    )
hive_url = "https://storage.googleapis.com/sfr-hive-data-research/checkpoints/hive_rw.ckpt"
generation = "1680591487158488"
size = 14580611882
etag = '"0e334d6dbb33b33f77fa0807dceb17ab"'
specs.append(
    {
        "relative": "raw/hive_rw.ckpt",
        "url": hive_url + "?generation=" + generation,
        "bytes": size,
        "gcs_generation": generation,
        "etag": etag,
        "sha256": "2447cd419b8ea7e40a3215c7e9c135d78923819a1d4232663c7314ba5bcbdca3",
        "publisher_source": "https://github.com/salesforce/HIVE/blob/9b10442a73061ca99bbbe57d58f34343fe5066e8/scripts/download_checkpoints.sh",
    }
)
jobs = [
    ("ip2p", "timothybrooks/instruct-pix2pix", "0dffd1eeb02611c35088462d1df88714ce2b52f4"),
    ("hive", "salesforce/HIVE", "9b10442a73061ca99bbbe57d58f34343fe5066e8"),
    ("taming", "CompVis/taming-transformers", "3ba01b241669f5ade541ce990f7650a3b8f65318"),
    ("clip", "openai/CLIP", "d05afc436d78f1c48dc0dbf8e5980a9d471f35f6"),
]
with ThreadPoolExecutor(max_workers=4) as pool:
    futures = [pool.submit(fetch_file, spec) for spec in specs]
    sources = [pool.submit(source_repo, *job) for job in jobs]
    files = [f.result() for f in futures]
    deps = [f.result() for f in sources]
manifest = {"files": files, "sources": deps, "time_utc": datetime.now(timezone.utc).isoformat()}
if (ROOT / "ASSETS.json").exists():
    previous = json.loads((ROOT / "ASSETS.json").read_text())
    assert previous["files"] == files and previous["sources"] == deps
    manifest["time_utc"] = previous["time_utc"]
(ROOT / "ASSETS.json").write_text(json.dumps(manifest, indent=2) + "\n")
print("Asset download and SHA verification complete.", flush=True)
