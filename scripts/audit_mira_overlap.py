#!/usr/bin/env python3
"""Trace actual SITEdit training rows and compare MIRA with source/target image fingerprints."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import time

import numpy as np
from PIL import Image, ImageOps
from scipy.fft import dctn

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
PASS1 = NAS / "experiments2/SAMTokEdit/pass1_localization_lora_formal_20261030_0939"
S2 = NAS / "experiments2/SAMTokEdit/qwen21_v3/data/round2_scaleup_20261030"
MERGED = NAS / "datasets/SAMTokEdit_Merged_20261029"
RELEASE = NAS / "datasets/sa1b_samtok_edit_50k_20261014/release"


def read(path):
    return json.loads(Path(path).read_text())


def lines(path):
    with Path(path).open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def file_sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def build_inventory(output):
    manifest = output / "INVENTORY.jsonl"
    receipt = output / "INVENTORY.json"
    if receipt.exists():
        prior = read(receipt)
        assert file_sha(manifest) == prior["inventory_sha256"]
        for entry in prior["inputs"]:
            assert file_sha(entry["path"]) == entry["sha256"], "Training metadata changed"
        return list(lines(manifest)), prior
    assets = {}
    inputs = []
    counts = Counter()

    def add(path, scope, source_id=None):
        key = str(path)
        row = assets.setdefault(key, {"path": key, "scopes": set(), "source_ids": set()})
        row["scopes"].add(scope)
        if source_id:
            row["source_ids"].add(source_id)

    def bind(path):
        inputs.append({"path": str(path), "sha256": file_sha(path)})

    metadata = read(PASS1 / "runs/formal/step_2000/metadata.json")
    batches = read(PASS1 / "data/prepared/batch_plan.json")
    seen = {i for batch in batches["batches"][:metadata["step"]] for i in batch["indices"] if i >= 0}
    assert len(seen) == metadata["requests_seen"]
    for split in ("train", "dev", "test"):
        path = PASS1 / "data/prepared" / f"{split}.jsonl"
        bind(path)
        for index, row in enumerate(lines(path)):
            scope = f"pass1_{split}_source"
            if split == "train" and index not in seen:
                scope = "pass1_planned_unseen_source"
            add(row["image"], scope, row["group"])
            counts[scope] += 1
    bind(PASS1 / "data/prepared/batch_plan.json")
    bind(PASS1 / "runs/formal/step_2000/metadata.json")
    wanted = defaultdict(set)
    pool_wanted = defaultdict(set)
    for stage in ("s1", "s2"):
        path = S2 / f"rows_{stage}.jsonl"
        bind(path)
        for row in lines(path):
            counts[f"{stage}_train_rows"] += 1
            if row["kind"] == "edit_merged":
                wanted[row["id"]].add(f"{stage}_train")
            elif row["kind"] in ("hl", "hl_ref", "hlm"):
                pool_wanted[row["source_id"]].add(f"{stage}_train_source")
            else:
                raise ValueError(f"Unhandled training row kind: {row['kind']}")
    assert counts["s1_train_rows"] == 192000 and counts["s2_train_rows"] == 512000
    found = set()
    record_path = MERGED / "records.jsonl"
    bind(record_path)
    for number, row in enumerate(lines(record_path), 1):
        rid = row["id"]
        if rid in wanted:
            found.add(rid)
            for scope in wanted[rid]:
                add(MERGED / row["source_image"], scope + "_source", row["group"])
                add(MERGED / row["target_image"], scope + "_target", rid)
        if number % 100000 == 0:
            print(f"Training records scanned: {number}; selected records found: {len(found)}", flush=True)
    assert found == set(wanted), "Unresolved merged training IDs"
    pool_hash = hashlib.sha256()
    for sid, scopes in sorted(pool_wanted.items()):
        path = S2 / "pool" / f"{sid}.json"
        with path.open() as stream:
            prefix = stream.read(8192)
        match = re.search(r'"image"\s*:\s*("(?:[^"\\]|\\.)*")', prefix)
        image = json.loads(match[1]) if match else read(path)["image"]
        pool_hash.update(json.dumps([sid, image], separators=(",", ":")).encode())
        for scope in scopes:
            add(image, scope, sid)
    dev = S2 / "eval_c1.json"
    bind(dev)
    dev_edits = set()
    for row in read(dev):
        if "image" in row:
            add(row["image"], "s1_s2_dev_source", row.get("source_id"))
        elif row["set"] == "edit":
            dev_edits.add(row["sample_id"])
        else:
            raise ValueError("Unhandled validation image reference")
    release_path = RELEASE / "annotations/train_protocol_v2.jsonl"
    bind(release_path)
    found_dev = set()
    for row in lines(release_path):
        if row["sample_id"] in dev_edits:
            found_dev.add(row["sample_id"])
            add(RELEASE / row["source_image"], "s1_s2_dev_source", row["source_id"])
            add(RELEASE / row["edited_image"], "s1_s2_dev_target", row["sample_id"])
    assert found_dev == dev_edits
    values = [{**row, "scopes": sorted(row["scopes"]), "source_ids": sorted(row["source_ids"])}
              for _, row in sorted(assets.items())]
    with manifest.open("x") as stream:
        for row in values:
            stream.write(json.dumps(row) + "\n")
    result = {"inputs": inputs, "rows": dict(counts), "unique_image_paths": len(values),
              "inventory_sha256": file_sha(manifest), "pool_image_mapping_sha256": pool_hash.hexdigest(),
              "pass1_step": metadata["step"], "pass1_actual_requests": len(seen),
              "scope": "Pass1 step 2000 actual/planned rows; predecessor S1 step6000; S2 step16000; declared dev/test images.",
              "excluded": "Foundation-model pretraining and undocumented development use are not covered."}
    receipt.write_text(json.dumps(result, indent=2) + "\n")
    return values, result


def perceptual(image):
    gray = image.convert("L")
    small = np.asarray(gray.resize((9, 8), Image.Resampling.LANCZOS), dtype=np.int16)
    dhash = int.from_bytes(np.packbits(small[:, 1:] > small[:, :-1]).tobytes(), "big")
    matrix = np.asarray(gray.resize((32, 32), Image.Resampling.LANCZOS), dtype=float)
    low = dctn(matrix, type=2, norm="ortho")[:8, :8]
    phash = int.from_bytes(np.packbits(low > np.median(low)).tobytes(), "big")
    return dhash, phash


def fingerprint(path):
    path = Path(path)
    info = path.stat()
    raw = path.read_bytes()
    with Image.open(BytesIO(raw)) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
    dhash, phash = perceptual(image)
    return {"path": str(path), "bytes": info.st_size, "mtime_ns": info.st_mtime_ns,
            "sha256": hashlib.sha256(raw).hexdigest(), "size": list(image.size),
            "pixel_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
            "dhash": f"{dhash:016x}", "phash": f"{phash:016x}"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    tick = time.monotonic()
    inventory, metadata = build_inventory(args.output)
    print(f"Inventory complete: {len(inventory)} source/target image paths", flush=True)
    dataset = NAS / "datasets/MIRA-Bench/benchmark"
    queries = []
    for row in lines(dataset / "annotations.jsonl"):
        fp = fingerprint(dataset / row["image"])
        fp["case"] = Path(row["image"]).stem
        queries.append(fp)
    (args.output / "MIRA_FINGERPRINTS.json").write_text(json.dumps(queries, indent=2) + "\n")
    qd = np.array([int(r["dhash"], 16) for r in queries], dtype=np.uint64)
    qp = np.array([int(r["phash"], 16) for r in queries], dtype=np.uint64)
    known = {}
    fingerprints = args.output / "FINGERPRINTS.jsonl"
    if fingerprints.exists():
        known = {r["path"]: r for r in lines(fingerprints)}
    candidates = []
    errors = []
    scanned = 0

    def inspect(item):
        try:
            cached = known.get(item["path"])
            info = Path(item["path"]).stat()
            if cached:
                assert (cached["bytes"], cached["mtime_ns"]) == (info.st_size, info.st_mtime_ns), "Image changed since audit"
                fp = cached
            else:
                fp = fingerprint(item["path"])
            dd = np.bitwise_count(qd ^ np.uint64(int(fp["dhash"], 16)))
            pd = np.bitwise_count(qp ^ np.uint64(int(fp["phash"], 16)))
            matches = []
            for i in np.where((dd <= 6) | (pd <= 8))[0]:
                query = queries[i]
                matches.append({"case": query["case"], "path": fp["path"], "scopes": item["scopes"],
                    "source_ids": item["source_ids"], "dhash_distance": int(dd[i]), "phash_distance": int(pd[i]),
                    "file_equal": fp["sha256"] == query["sha256"],
                    "pixels_equal": fp["size"] == query["size"] and fp["pixel_sha256"] == query["pixel_sha256"]})
            return fp, matches, None, cached is not None
        except Exception as error:
            return None, [], {"path": item["path"], "scopes": item["scopes"], "error": repr(error)}, False

    with fingerprints.open("a") as stream, ThreadPoolExecutor(max_workers=args.workers) as pool:
        for start in range(0, len(inventory), 512):
            for fp, matches, error, reused in pool.map(inspect, inventory[start:start + 512]):
                scanned += 1
                if error:
                    errors.append(error)
                elif not reused:
                    stream.write(json.dumps(fp) + "\n")
                candidates.extend(matches)
            stream.flush()
            status = {"status": "scanning", "scanned": scanned, "total": len(inventory),
                      "errors": len(errors), "candidate_pairs": len(candidates), "seconds": time.monotonic() - tick}
            (args.output / "STATUS.json").write_text(json.dumps(status, indent=2) + "\n")
            if start % 5120 == 0:
                print(json.dumps(status), flush=True)
    (args.output / "CANDIDATES.json").write_text(json.dumps(candidates, indent=2) + "\n")
    (args.output / "ERRORS.json").write_text(json.dumps(errors, indent=2) + "\n")
    exact = sorted({r["case"] for r in candidates if r["file_equal"] or r["pixels_equal"]})
    report = {"status": "fingerprints_complete" if not errors else "fingerprints_incomplete",
        "inventory": metadata, "benchmark_sources": 200, "scanned": scanned, "errors": len(errors),
        "exact_match_cases": exact, "candidate_pairs": len(candidates),
        "candidate_cases": sorted({r["case"] for r in candidates}),
        "near_duplicate_policy": "dHash64 <= 6 OR pHash64 <= 8; candidates require visual adjudication, not automatic exclusion.",
        "limitations": "Finite perceptual hashes do not exhaustively detect arbitrary crops, mirroring or transformations. MIRA has no shared original IDs, so opaque filenames are not ID-match evidence.",
        "seconds": time.monotonic() - tick}
    (args.output / "STATUS.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "inventory"}), flush=True)


if __name__ == "__main__":
    main()
