"""Pinned download, isolated extraction and bundle preparation for RefEdit-Bench.

The dataset is gated on Hugging Face. ``download`` needs a read token of an account that has accepted the dataset's
conditions; the token is read from a file and never printed or stored. Downloaded bytes are untrusted: ``extract``
only parses the Parquet table and decodes images (run it through ``scripts/refedit_data.py`` with ``python -I``) and
never executes anything shipped with the download.

Model-visible inputs (``public/``) hold only the shared canvas and the original ``editing_instruction``. The mask,
``edit_instruction_single`` and category live in ``private/evaluation.json`` and are read only for scoring.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import urllib.parse
import urllib.request

from PIL import Image

from samtok_benchmark.io import digest, sha256_file
from samtok_benchmark.ifbench.canvas import make_source, validate_geometry
from . import (DATASET_BYTES, DATASET_FILE, DATASET_REPO, DATASET_REVISION, EASY_CASES, NUM_CASES,
               OFFICIAL_CODE, OFFICIAL_COMMIT)

PUBLIC_KEYS = {"schema", "case_id", "source", "instruction", "input_digest"}
# Engineering dry runs on substitute images (never RefEdit data, never formal): see scripts/refedit_dryrun_bundle.py
DRYRUN_REVISION = "DRYRUN-NOT-REFEDIT"
CATEGORIES = ("Easy", "Hard")


def read(path):
    return json.loads(Path(path).read_text())


def immutable(path, value):
    """Never silently replace an existing input, configuration or receipt."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if read(path) != value:
            raise ValueError(f"Existing file has different content: {path}")
        return
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def case_id(index):
    return f"{index:03d}"


# ------------------------------------------------------------------------------------------------ download


class _DropAuthOnCrossHost(urllib.request.HTTPRedirectHandler):
    """Follow redirects, but never forward the HF token to another host (e.g. a pre-signed CDN URL)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            for key in list(new.headers):
                if key.lower() == "authorization":
                    del new.headers[key]
            new.unredirected_hdrs.pop("Authorization", None)
        return new


def _open(url, token=None, timeout=120):
    request = urllib.request.Request(url, headers={"User-Agent": "samtok-benchmark-refedit/1"})
    if token:
        # Kept on same-host redirects (HF resolve-cache), removed by the handler on cross-host ones.
        request.add_header("Authorization", f"Bearer {token}")
    return urllib.request.build_opener(_DropAuthOnCrossHost).open(request, timeout=timeout)


def read_token(path):
    token = Path(path).read_text().strip()
    if not token or any(c.isspace() for c in token):
        raise ValueError("Token file must contain exactly one token")
    return token


def upstream_entries(token):
    url = (f"https://huggingface.co/api/datasets/{DATASET_REPO}/tree/{DATASET_REVISION}"
           f"?recursive=true&expand=false")
    with _open(url, token) as response:
        rows = json.load(response)
    return {row["path"]: row for row in rows if row.get("type") == "file"}


def download(root, token_file):
    """Fetch exactly the pinned Parquet file (and the public card); verify size and upstream SHA-256."""
    root = Path(root).resolve()
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    token = read_token(token_file)
    entries = upstream_entries(token)
    entry = entries[DATASET_FILE]
    lfs = entry.get("lfs") or {}
    upstream_sha = lfs.get("oid") if isinstance(lfs.get("oid"), str) and len(lfs.get("oid", "")) == 64 \
        and all(c in "0123456789abcdef" for c in lfs["oid"]) else None
    if entry.get("size") != DATASET_BYTES:
        raise ValueError(f"Upstream size differs from the pinned file: {entry.get('size')}")
    target = raw / Path(DATASET_FILE).name
    if not target.exists():
        url = f"https://huggingface.co/datasets/{DATASET_REPO}/resolve/{DATASET_REVISION}/{DATASET_FILE}"
        partial = target.with_name(target.name + ".partial")
        value = hashlib.sha256()
        with _open(url, token, timeout=600) as response, partial.open("xb") as stream:
            for block in iter(lambda: response.read(1 << 20), b""):
                value.update(block)
                stream.write(block)
        if partial.stat().st_size != DATASET_BYTES or (upstream_sha and value.hexdigest() != upstream_sha):
            partial.unlink()
            raise ValueError("Downloaded bytes differ from the pinned upstream identity")
        partial.rename(target)
    actual = sha256_file(target)
    if target.stat().st_size != DATASET_BYTES or (upstream_sha and actual != upstream_sha):
        raise ValueError("Existing download differs from the pinned upstream identity")
    card = raw / "README.md"
    if not card.exists():
        url = f"https://huggingface.co/datasets/{DATASET_REPO}/resolve/{DATASET_REVISION}/README.md"
        with _open(url, token) as response:
            content = response.read()
        blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if blob != entries["README.md"]["oid"]:
            raise ValueError("Dataset card differs from the pinned revision")
        with card.open("xb") as stream:
            stream.write(content)
    source = {
        "dataset": DATASET_REPO,
        "url": f"https://huggingface.co/datasets/{DATASET_REPO}/tree/{DATASET_REVISION}",
        "revision": DATASET_REVISION,
        "access": "gated (auto approval); downloaded with a read token of an account that accepted the conditions",
        "license": "Not stated on the dataset card, the official repository or the project page. Images come "
                   "from RefCOCO/MS-COCO and remain subject to the COCO image terms.",
        "official_code": {"repository": OFFICIAL_CODE, "commit": OFFICIAL_COMMIT},
        "files": [
            {"path": f"raw/{target.name}", "upstream_path": DATASET_FILE, "bytes": target.stat().st_size,
             "sha256": actual, "upstream_lfs_sha256": upstream_sha},
            {"path": "raw/README.md", "upstream_path": "README.md", "bytes": card.stat().st_size,
             "sha256": sha256_file(card), "upstream_git_blob": entries["README.md"]["oid"]},
        ],
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "untrusted": "Parsed only with python -I; nothing shipped with the download is executed.",
    }
    path = root / "SOURCE.json"
    if path.exists():
        previous = read(path)
        if previous["files"] != source["files"] or previous["revision"] != DATASET_REVISION:
            raise ValueError("SOURCE.json describes different bytes")
        return previous
    immutable(path, source)
    return source


# ------------------------------------------------------------------------------------------------ extract


def parse_mask(text):
    """The official notebook draws ``json.loads(mask)[0]``; keep the full list for auditing."""
    polygons = json.loads(text)
    if not isinstance(polygons, list) or not polygons:
        raise ValueError("Mask must be a non-empty list of polygons")
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise ValueError("Invalid polygon")
        flat = [v for point in polygon for v in (point if isinstance(point, list) else [point])]
        if len(flat) < 6 or len(flat) % 2 or not all(isinstance(v, (int, float)) for v in flat):
            raise ValueError("Polygon must have at least three numeric points")
    return polygons


def extract(root):
    """Decode the pinned Parquet table into images and one annotation line per official row index."""
    import pyarrow.parquet as pq

    root = Path(root).resolve()
    source = read(root / "SOURCE.json")
    for item in source["files"]:
        if sha256_file(root / item["path"]) != item["sha256"]:
            raise ValueError(f"Dataset bytes changed: {item['path']}")
    table = pq.read_table(root / source["files"][0]["path"])
    expected = {"input_image", "editing_instruction", "edit_instruction_single", "mask", "category"}
    if set(table.column_names) != expected or table.num_rows != NUM_CASES:
        raise ValueError(f"Unexpected table: {table.column_names}, {table.num_rows} rows")
    out = root / "extracted"
    images = out / "images"
    images.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, row in enumerate(table.to_pylist()):
        data = row["input_image"]["bytes"] if isinstance(row["input_image"], dict) else None
        if not data:
            raise ValueError(f"Row {index} has no embedded image bytes")
        with Image.open(BytesIO(data)) as image:
            image.load()
            fmt, size, mode = image.format, list(image.size), image.mode
        suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}.get(fmt)
        if suffix is None:
            raise ValueError(f"Unsupported embedded image format {fmt!r} in row {index}")
        path = images / f"{case_id(index)}{suffix}"
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError(f"Extracted image differs: {path}")
        else:
            with path.open("xb") as stream:
                stream.write(data)
        category = row["category"]
        expected_category = CATEGORIES[0] if index < EASY_CASES else CATEGORIES[1]
        polygons = parse_mask(row["mask"])
        for key in ("editing_instruction", "edit_instruction_single"):
            if not isinstance(row[key], str) or not row[key].strip():
                raise ValueError(f"Row {index} has an empty {key}")
        rows.append({
            "index": index, "case_id": case_id(index), "image": f"images/{path.name}",
            "image_sha256": hashlib.sha256(data).hexdigest(), "image_format": fmt, "image_mode": mode,
            "size": size, "category": category, "official_split": expected_category,
            "category_matches_official_index_rule": category == expected_category,
            "editing_instruction": row["editing_instruction"],
            "edit_instruction_single": row["edit_instruction_single"],
            "mask": row["mask"], "mask_polygons": len(polygons),
            "embedded_image_path": row["input_image"].get("path"),
        })
    content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    annotations = out / "annotations.jsonl"
    if annotations.exists():
        if annotations.read_text() != content:
            raise ValueError("Existing extracted annotations differ")
    else:
        annotations.write_text(content)
    receipt = {"source_sha256": sha256_file(root / "SOURCE.json"), "rows": len(rows),
               "annotations_sha256": sha256_file(annotations),
               "categories": {c: sum(r["category"] == c for r in rows) for c in sorted({r["category"] for r in rows})},
               "category_mismatches_with_index_rule": [r["index"] for r in rows
                                                       if not r["category_matches_official_index_rule"]],
               "multi_polygon_masks": [r["index"] for r in rows if r["mask_polygons"] > 1],
               "image_formats": sorted({r["image_format"] for r in rows})}
    immutable(out / "EXTRACT.json", receipt)
    return receipt


def load_annotations(root):
    root = Path(root).resolve()
    receipt = read(root / "extracted/EXTRACT.json")
    path = root / "extracted/annotations.jsonl"
    if sha256_file(path) != receipt["annotations_sha256"]:
        raise ValueError("Extracted annotations changed")
    rows = [json.loads(s) for s in path.read_text().splitlines() if s.strip()]
    if [r["index"] for r in rows] != list(range(NUM_CASES)):
        raise ValueError("This protocol requires the complete pinned 200-row release in official order")
    for row in rows:
        if sha256_file(root / "extracted" / row["image"]) != row["image_sha256"]:
            raise ValueError(f"Extracted image changed: {row['image']}")
    return rows


# ------------------------------------------------------------------------------------------------ bundle


def verify_public(public, assets=True):
    if set(public) != PUBLIC_KEYS or public["schema"] != "refedit.public.v1":
        raise ValueError("Unexpected fields in public request")
    if digest({k: v for k, v in public.items() if k != "input_digest"}) != public["input_digest"]:
        raise ValueError("Public input digest mismatch")
    source = public["source"]
    if set(source) != {"path", "sha256", "size"}:
        raise ValueError("Invalid public source")
    if not isinstance(public["instruction"], str) or not public["instruction"].strip():
        raise ValueError("Missing public instruction")
    if assets:
        if sha256_file(source["path"]) != source["sha256"]:
            raise ValueError("Public image changed")
        with Image.open(source["path"]) as image:
            if list(image.size) != source["size"]:
                raise ValueError("Public image size changed")


def prepare(root, output):
    root = Path(root).resolve()
    header = {"dataset_revision": DATASET_REVISION, "source_sha256": sha256_file(root / "SOURCE.json"),
              "extract_sha256": sha256_file(root / "extracted/EXTRACT.json")}
    return build_bundle(load_annotations(root), root / "extracted", output, header)


def build_bundle(rows, image_root, output, header):
    """Public canvas + original instruction per case; scoring fields only in private/evaluation.json."""
    output = Path(output).resolve()
    cases, evaluation = [], []
    for row in rows:
        original = Path(image_root) / row["image"]
        canonical = {"path": str(original), "sha256": row["image_sha256"], "size": row["size"]}
        directory = output / "public" / row["case_id"]
        source, geometry = make_source(canonical, directory)
        public = {"schema": "refedit.public.v1", "case_id": row["case_id"], "source": source,
                  "instruction": row["editing_instruction"]}
        public["input_digest"] = digest(public)
        verify_public(public)
        immutable(directory / "public.json", public)
        cases.append({"case_id": row["case_id"], "category": row["category"],
                      "public": str(directory / "public.json"),
                      "public_sha256": sha256_file(directory / "public.json"), "geometry": geometry})
        evaluation.append({key: row[key] for key in ("case_id", "index", "category", "official_split",
                                                    "editing_instruction", "edit_instruction_single", "mask")}
                          | {"source": canonical})
    index = {"schema": "refedit.bundle.v1", **header, "cases": cases}
    index["digest"] = digest(index)
    immutable(output / "index.json", index)
    immutable(output / "private/evaluation.json", evaluation)
    return index


def load_bundle(path, case_ids=None):
    index = read(Path(path) / "index.json")
    dryrun = index.get("dryrun") is True and index["dataset_revision"] == DRYRUN_REVISION
    if (index["schema"] != "refedit.bundle.v1" or (index["dataset_revision"] != DATASET_REVISION and not dryrun)
            or len(index["cases"]) != NUM_CASES or len({c["case_id"] for c in index["cases"]}) != NUM_CASES):
        raise ValueError("Expected the complete pinned 200-case public bundle")
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
