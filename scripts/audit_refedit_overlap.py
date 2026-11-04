#!/usr/bin/env python3
"""RefEdit-Bench training-overlap audit for SITEdit (CPU only; no model, no network).

Training side (prepared once, ``--stage training``):

1. Re-verify the SHA-256 of every training-metadata file bound by the MIRA overlap inventory (Pass1 step 2000,
   S1 step 6000, S2 step 16000 rows, merged records, dev sets); reuse its 646,908 image fingerprints only if all match.
2. Fingerprint every RefCOCO/gRES image of the SAMTok training mixture (bytes embedded in
   ``mix_gres8k_ver4k_train.parquet``), keyed by COCO train2014 id.
3. Trace COCO ids into SITEdit's actual training: derived-edit cases (``SAMTok_Derived_Edit_Labeling``) -> cleaned
   manifest -> merged ``derived-*`` records -> S1/S2 ``edit_merged`` rows and Pass1 step-2000 rows.

Benchmark side (``--stage benchmark``): fingerprint the 200 extracted RefEdit-Bench images (and their mirror images)
and compare against both sets with the MIRA thresholds (dHash <= 6 or pHash <= 8, plus exact file/pixel equality).
Candidates require visual adjudication; nothing is excluded automatically.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import time

import numpy as np
from PIL import Image, ImageOps

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from audit_mira_overlap import perceptual  # noqa: E402  (identical hashing to the MIRA audit)

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
MIRA_AUDIT = NAS / ".ifbench-tmp/external_bench_20261102/overlap_audit_20261102"
MIX = NAS / "datasets/SAMTok_Training_Data/mix_gres8k_ver4k_train.parquet"
DERIVED = NAS / "datasets/SAMTok_Derived_Edit_Labeling/combined/manifest.jsonl"
CLEANED = NAS / "datasets/SAMTokEdit_Cleaned_20261009/manifest.jsonl"
MERGED = NAS / "datasets/SAMTokEdit_Merged_20261029/records.jsonl"
S2 = NAS / "experiments2/SAMTokEdit/qwen21_v3/data/round2_scaleup_20261030"
PASS1 = NAS / "experiments2/SAMTokEdit/pass1_localization_lora_formal_20261030_0939"
COCO = re.compile(r"COCO_train2014_(\d{12})\.jpg$")


def file_sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def lines(path):
    with Path(path).open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def fingerprint_bytes(raw):
    with Image.open(BytesIO(raw)) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
    dhash, phash = perceptual(image)
    mirror = ImageOps.mirror(image)
    mdhash, mphash = perceptual(mirror)
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size": list(image.size),
            "pixel_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
            "dhash": f"{dhash:016x}", "phash": f"{phash:016x}",
            "mirror_dhash": f"{mdhash:016x}", "mirror_phash": f"{mphash:016x}"}


def _gres_item(args):
    row, path, raw = args
    match = COCO.search(path or "")
    return {"mix_row": row, "path": path, "coco_id": int(match.group(1)) if match else None,
            **fingerprint_bytes(raw)}


def training(output, workers):
    import pyarrow.parquet as pq

    output.mkdir(parents=True, exist_ok=True)
    inventory = json.loads((MIRA_AUDIT / "INVENTORY.json").read_text())
    checks = [{"path": e["path"], "sha256": e["sha256"], "match": file_sha(e["path"]) == e["sha256"]}
              for e in inventory["inputs"]]
    fingerprints = MIRA_AUDIT / "FINGERPRINTS.jsonl"
    receipt = {"mira_inventory_inputs": checks, "mira_inventory_all_match": all(c["match"] for c in checks),
               "mira_fingerprints": {"path": str(fingerprints), "sha256": file_sha(fingerprints),
                                     "rows": sum(1 for _ in fingerprints.open())},
               "mira_inventory_rows": inventory["rows"], "mira_unique_image_paths": inventory["unique_image_paths"]}
    if not receipt["mira_inventory_all_match"]:
        raise SystemExit("Training metadata changed since the MIRA inventory; re-run that inventory first")
    # gRES images embedded in the SAMTok training mixture.
    table = pq.ParquetFile(MIX).read(columns=["source", "images"])
    sources = table.column("source").to_pylist()
    images = table.column("images").combine_chunks()
    flat, offsets = images.flatten(), images.offsets.to_pylist()
    paths, data = flat.field("path"), flat.field("bytes")
    jobs = [(i, paths[offsets[i]].as_py(), data[offsets[i]].as_py()) for i, s in enumerate(sources)
            if s == "gres" and offsets[i + 1] > offsets[i]]
    with ProcessPoolExecutor(workers) as pool:
        gres = list(pool.map(_gres_item, jobs, chunksize=32))
    with (output / "GRES_FINGERPRINTS.jsonl").open("w") as stream:
        for row in gres:
            stream.write(json.dumps(row) + "\n")
    # Trace COCO ids into actual SITEdit training rows.
    derived_case_coco = {}
    for row in lines(DERIVED):
        if row["source_subset"] == "gres":
            path = jobs_by_row(jobs).get(int(row["parquet_row_index"]))
            match = COCO.search(path or "")
            derived_case_coco[row["case_id"]] = int(match.group(1)) if match else None
    link = {}
    for row in lines(CLEANED):
        if row.get("dataset") == "derived":
            link[row["id"]] = ((row.get("provenance") or {}).get("locator") or {}).get("original_id")
    merged = {}
    for row in lines(MERGED):
        if row.get("origin") != "derived":
            continue
        original = link.get(row["source_ref"])
        if original in derived_case_coco:
            merged[row["id"]] = {"coco_id": derived_case_coco[original], "derived_case": original,
                                 "split": row["split"], "default": row["default"],
                                 "source_image": row["source_image"], "target_image": row["target_image"]}
    use = defaultdict(set)
    for stage in ("s1", "s2"):
        for row in lines(S2 / f"rows_{stage}.jsonl"):
            if row["kind"] == "edit_merged" and row["id"] in merged:
                use[row["id"]].add(f"{stage}_train")
    meta = json.loads((PASS1 / "runs/formal/step_2000/metadata.json").read_text())
    batches = json.loads((PASS1 / "data/prepared/batch_plan.json").read_text())
    seen = {i for b in batches["batches"][:meta["step"]] for i in b["indices"] if i >= 0}
    merged_images = {str(NAS / "datasets/SAMTokEdit_Merged_20261029" / v["source_image"]): k for k, v in merged.items()}
    for split in ("train", "dev", "test"):
        for index, row in enumerate(lines(PASS1 / "data/prepared" / f"{split}.jsonl")):
            key = merged_images.get(row["image"])
            if key:
                use[key].add(f"pass1_{split}" + ("" if split != "train" else "_seen" if index in seen
                                                 else "_planned_unseen"))
    coco_use = defaultdict(lambda: {"records": [], "scopes": set()})
    for key, value in merged.items():
        entry = coco_use[value["coco_id"]]
        entry["records"].append({"id": key, "scopes": sorted(use.get(key, ())), "split": value["split"],
                                 "default": value["default"]})
        entry["scopes"] |= use.get(key, set())
    trace = {str(k): {"records": v["records"], "scopes": sorted(v["scopes"])} for k, v in sorted(coco_use.items())}
    (output / "COCO_TRAINING_USE.json").write_text(json.dumps(trace) + "\n")
    receipt.update({
        "gres_rows": len(jobs), "gres_unique_coco_ids": len({g["coco_id"] for g in gres}),
        "derived_gres_cases": len(derived_case_coco), "merged_records_from_gres": len(merged),
        "merged_records_used_in_training": sum(bool(use.get(k)) for k in merged),
        "coco_ids_in_actual_training_rows": sum(bool(v["scopes"]) for v in trace.values()),
        "gres_fingerprints_sha256": file_sha(output / "GRES_FINGERPRINTS.jsonl"),
        "inputs": {str(p): file_sha(p) for p in (MIX, DERIVED, CLEANED)},
        "scope_note": "S1/S2 rows and Pass1 step-2000 rows are traced; the SAMTok base model's own training "
                      "(Qwen3-VL-8B-SAMTok) is outside this record and only bounded by the local SAMTok training "
                      "mixture, whose use for that checkpoint is not verified here."})
    (output / "TRAINING.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: v for k, v in receipt.items() if k not in ("mira_inventory_inputs", "inputs")}, indent=2))


_JOBS_INDEX = {}


def jobs_by_row(jobs):
    if not _JOBS_INDEX:
        _JOBS_INDEX.update({row: path for row, path, _ in jobs})
    return _JOBS_INDEX


def _distances(query, rows, field_d, field_p):
    qd, qp = np.uint64(int(query["dhash"], 16)), np.uint64(int(query["phash"], 16))
    md, mp = np.uint64(int(query["mirror_dhash"], 16)), np.uint64(int(query["mirror_phash"], 16))
    dd = np.minimum(np.bitwise_count(rows[field_d] ^ qd), np.bitwise_count(rows[field_d] ^ md))
    pd = np.minimum(np.bitwise_count(rows[field_p] ^ qp), np.bitwise_count(rows[field_p] ^ mp))
    return dd, pd


def benchmark(dataset, output):
    output = Path(output)
    training_receipt = json.loads((output / "TRAINING.json").read_text())
    annotations = [json.loads(s) for s in (dataset / "extracted/annotations.jsonl").read_text().splitlines()]
    queries = []
    for row in annotations:
        raw = (dataset / "extracted" / row["image"]).read_bytes()
        queries.append({"case_id": row["case_id"], "category": row["category"], **fingerprint_bytes(raw)})
    (output / "REFEDIT_FINGERPRINTS.json").write_text(json.dumps(queries, indent=1) + "\n")
    sets = {}
    gres = list(lines(output / "GRES_FINGERPRINTS.jsonl"))
    sets["gres"] = (gres, {"d": np.array([int(r["dhash"], 16) for r in gres], np.uint64),
                           "p": np.array([int(r["phash"], 16) for r in gres], np.uint64)})
    mira = list(lines(MIRA_AUDIT / "FINGERPRINTS.jsonl"))
    scopes = {r["path"]: r["scopes"] for r in lines(MIRA_AUDIT / "INVENTORY.jsonl")}
    sets["sitedit_training_inventory"] = (mira, {"d": np.array([int(r["dhash"], 16) for r in mira], np.uint64),
                                                 "p": np.array([int(r["phash"], 16) for r in mira], np.uint64)})
    coco_use = json.loads((output / "COCO_TRAINING_USE.json").read_text())
    candidates = []
    for query in queries:
        for name, (rows, arrays) in sets.items():
            dd, pd = _distances(query, {"d": arrays["d"], "p": arrays["p"]}, "d", "p")
            for i in np.where((dd <= 6) | (pd <= 8))[0]:
                row = rows[i]
                item = {"case_id": query["case_id"], "category": query["category"], "set": name,
                        "dhash_distance": int(dd[i]), "phash_distance": int(pd[i]),
                        "file_equal": row["sha256"] == query["sha256"],
                        "pixels_equal": row["size"] == query["size"] and row["pixel_sha256"] == query["pixel_sha256"]}
                if name == "gres":
                    item.update(coco_id=row["coco_id"], mix_row=row["mix_row"],
                                training_use=coco_use.get(str(row["coco_id"]), {}).get("scopes", []))
                else:
                    item.update(path=row["path"], scopes=scopes.get(row["path"], []))
                candidates.append(item)
    (output / "CANDIDATES.json").write_text(json.dumps(candidates, indent=1) + "\n")
    report = {"benchmark_images": len(queries), "candidate_pairs": len(candidates),
              "candidate_cases": sorted({c["case_id"] for c in candidates}),
              "gres_candidate_cases": sorted({c["case_id"] for c in candidates if c["set"] == "gres"}),
              "training_candidate_cases": sorted({c["case_id"] for c in candidates
                                                  if c["set"] == "sitedit_training_inventory"}),
              "exact_cases": sorted({c["case_id"] for c in candidates if c["file_equal"] or c["pixels_equal"]}),
              "policy": "dHash64 <= 6 OR pHash64 <= 8 (also against the mirror image); visual adjudication required",
              "training_receipt": {k: training_receipt[k] for k in (
                  "gres_rows", "gres_unique_coco_ids", "merged_records_from_gres", "merged_records_used_in_training",
                  "coco_ids_in_actual_training_rows", "mira_unique_image_paths")}}
    (output / "STATUS.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("training", "benchmark"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    tick = time.monotonic()
    if args.stage == "training":
        training(args.output, args.workers)
    else:
        benchmark(args.dataset, args.output)
    print(f"seconds: {time.monotonic() - tick:.0f}")


if __name__ == "__main__":
    main()
