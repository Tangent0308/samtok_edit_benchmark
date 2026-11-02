"""Pinned public download, lossless text splitting, and an isolated scoring manifest."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request

from PIL import Image

from samtok_benchmark.io import digest, sha256_file
from samtok_benchmark.ifbench.canvas import make_source, validate_geometry
from . import DATASET_REVISION

REPO = "ziqiangoodgood/MIRAGE"
SEPARATOR = re.compile(r"[,\.]\s+and\s+(?=(?:Change|Add|Replace|Remove|Wrap)\b)")
OPERATIONS = {"Change": "attribute", "Add": "add", "Replace": "replace",
              "Remove": "remove", "Wrap": "add"}


def read(path):
    return json.loads(Path(path).read_text())


def immutable(path, value):
    """Never silently replace an existing input, configuration, or receipt."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if read(path) != value:
            raise ValueError(f"Existing file has different content: {path}")
        return
    with path.open("x") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def get(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.read()
        except (OSError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def download(root, cache=None):
    """Fetch exactly the pinned annotations and their images; verify upstream content hashes."""
    root = Path(root).resolve()
    files = json.loads(get(f"https://huggingface.co/api/datasets/{REPO}/tree/"
                          f"{DATASET_REVISION}/benchmark?recursive=true&limit=1000"))
    metadata = {f["path"]: f for f in files if f["type"] == "file"}
    base = f"https://huggingface.co/datasets/{REPO}/resolve/{DATASET_REVISION}/"

    def fetch(name):
        info = metadata[name]
        target = root / name
        cached = Path(cache) / Path(name).name if cache else None
        content = (target.read_bytes() if target.exists() else
                   cached.read_bytes() if cached and cached.is_file() else get(base + name))
        expected = info.get("lfs", {}).get("oid")
        actual = (hashlib.sha256(content).hexdigest() if expected else
                  hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest())
        if actual != (expected or info["oid"]) or len(content) != info["size"]:
            raise ValueError(f"Upstream content identity mismatch: {name}")
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as f:
                f.write(content)
        return {"path": name, "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content), "upstream_oid": info["oid"]}

    annotation = fetch("benchmark/annotations.jsonl")
    rows = load_annotations(root)
    names = ["benchmark/" + r["image"] for r in rows]
    with ThreadPoolExecutor(max_workers=6) as pool:
        assets = list(pool.map(fetch, names))
    receipt = {"dataset": REPO, "revision": DATASET_REVISION,
               "num_images": len(rows), "files": [annotation, *assets]}
    immutable(root / "DOWNLOAD.json", receipt)
    return receipt


def split_instruction(text):
    """Split only public punctuation; retain character offsets into the original instruction."""
    boundaries, start = [], 0
    for match in SEPARATOR.finditer(text):
        boundaries.append((start, match.start()))
        start = match.end()
    boundaries.append((start, len(text)))
    result = []
    for start, end in boundaries:
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        instruction = text[start:end]
        if not instruction or instruction.split()[0] not in OPERATIONS:
            raise ValueError(f"Unsupported public instruction grammar: {instruction!r}")
        result.append({"instruction": instruction, "text_span": [start, end],
                       "operation": OPERATIONS[instruction.split()[0]]})
    if len(result) != 5:
        raise ValueError(f"Expected five publicly expressed edits, got {len(result)}")
    return result


def load_annotations(root):
    path = Path(root) / "benchmark/annotations.jsonl"
    rows = [json.loads(s) for s in path.read_text().splitlines() if s.strip()]
    if len(rows) != 200 or len({r["image"] for r in rows}) != 200:
        raise ValueError("This protocol requires the complete pinned 200-image MIRA release")
    for row in rows:
        name = Path(row["image"])
        if name.name != str(name) or not name.suffix:
            raise ValueError("Unsafe or unsupported source filename")
        # Counts from masks are used only for scoring-annotation integrity, never for inference parsing.
        if len(row["mask"]) != 5 or any(not m for m in row["mask"]):
            raise ValueError(f"Invalid evaluation mask list: {name}")
        split_instruction(row["editing_instruction"])
    return sorted(rows, key=lambda r: r["image"])


def verify_public(public, assets=True):
    keys = {"schema", "case_id", "source", "original_instruction", "units", "input_digest"}
    if set(public) != keys or public["schema"] != "mira.public.v1":
        raise ValueError("Unexpected fields in public request")
    if digest({k: v for k, v in public.items() if k != "input_digest"}) != public["input_digest"]:
        raise ValueError("Public input digest mismatch")
    units = public["units"]
    expected = split_instruction(public["original_instruction"])
    for i, (unit, part) in enumerate(zip(units, expected, strict=True), 1):
        if unit != {"id": f"U{i}", "has_ref": True, "locator": "none", **part}:
            raise ValueError("Public units must come only from the original text")
    source = public["source"]
    if set(source) != {"path", "sha256", "size"}:
        raise ValueError("Invalid public source")
    if assets:
        if sha256_file(source["path"]) != source["sha256"]:
            raise ValueError("Public image changed")
        with Image.open(source["path"]) as image:
            if list(image.size) != source["size"]:
                raise ValueError("Public image size changed")


def prepare(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    receipt = read(root / "DOWNLOAD.json")
    if receipt["revision"] != DATASET_REVISION:
        raise ValueError("Dataset revision differs from this protocol")
    for asset in receipt["files"]:
        if sha256_file(root / asset["path"]) != asset["sha256"]:
            raise ValueError(f"Dataset bytes changed: {asset['path']}")
    cases, evaluation = [], []
    for row in load_annotations(root):
        case_id = Path(row["image"]).stem
        original = root / "benchmark" / row["image"]
        with Image.open(original) as im:
            size = list(im.size)
        canonical = {"path": str(original), "sha256": sha256_file(original), "size": size}
        directory = output / "public" / case_id
        source, geometry = make_source(canonical, directory)
        units = [{"id": f"U{i}", "has_ref": True, "locator": "none", **part}
                 for i, part in enumerate(split_instruction(row["editing_instruction"]), 1)]
        public = {"schema": "mira.public.v1", "case_id": case_id, "source": source,
                  "original_instruction": row["editing_instruction"], "units": units}
        public["input_digest"] = digest(public)
        verify_public(public)
        immutable(directory / "public.json", public)
        cases.append({"case_id": case_id, "public": str(directory / "public.json"),
                      "public_sha256": sha256_file(directory / "public.json"),
                      "geometry": geometry})
        evaluation.append({"case_id": case_id, "image": row["image"], "source": canonical,
                           "editing_instruction": row["editing_instruction"], "mask": row["mask"],
                           "instructions": [u["instruction"] for u in units]})
    index = {"schema": "mira.bundle.v1", "dataset_revision": DATASET_REVISION,
             "download_sha256": sha256_file(root / "DOWNLOAD.json"), "cases": cases}
    index["digest"] = digest(index)
    immutable(output / "index.json", index)
    immutable(output / "private/evaluation.json", evaluation)
    return index


def load_bundle(path, case_ids=None):
    index = read(Path(path) / "index.json")
    if (index["schema"] != "mira.bundle.v1" or index["dataset_revision"] != DATASET_REVISION or
            len(index["cases"]) != 200 or len({c["case_id"] for c in index["cases"]}) != 200):
        raise ValueError("Expected the complete pinned 200-source public bundle")
    if index["digest"] != digest({k: v for k, v in index.items() if k != "digest"}):
        raise ValueError("Bundle digest mismatch")
    for item in index["cases"]:
        if case_ids is not None and item["case_id"] not in case_ids:
            continue
        if sha256_file(item["public"]) != item["public_sha256"]:
            raise ValueError("Public request changed")
        verify_public(read(item["public"]))
        validate_geometry(item["geometry"])
    return index
