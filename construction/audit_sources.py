"""Recompute selected image fingerprints; audit against recorded training and v1 sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from samtok_benchmark.io import read_jsonl, sha256_file, write_json, write_jsonl
from review_state import final_decisions

UPSTREAM = Path("/mnt/bn/strategy-mllm-train/user/tanyue/datasets/PACO_benchmark_candidates")
REPO = Path(__file__).resolve().parents[1]


def fingerprint(path):
    with Image.open(path) as raw:
        im = ImageOps.exif_transpose(raw).convert("RGB")

    def variant(img):
        gray = img.convert("L")
        dct = cv2.dct(np.array(gray.resize((32, 32), Image.Resampling.LANCZOS), dtype=np.float32))[
            :8, :8
        ]
        d = np.array(gray.resize((9, 8), Image.Resampling.LANCZOS))
        return {
            "pixel_sha256": hashlib.sha256(
                b"RGB\0" + struct.pack(">QQ", *img.size) + img.tobytes()
            ).hexdigest(),
            "phash64": f"{int.from_bytes(np.packbits(dct > np.median(dct)).tobytes(), 'big'):016x}",
            "dhash64": f"{int.from_bytes(np.packbits(d[:, 1:] > d[:, :-1]).tobytes(), 'big'):016x}",
        }

    return {
        "path": str(path),
        "actual_byte_sha256": sha256_file(path),
        "size_wh": list(im.size),
        **variant(im),
        "horizontal_flip": variant(ImageOps.mirror(im)),
        "status": "ok",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    args = p.parse_args()
    root = args.root
    pool = read_jsonl(root / "candidate_pool.jsonl")
    decisions = [d for d in final_decisions(root) if d["decision"] == "accept"]
    selected = []
    for d in decisions:
        c = pool[d["index"]]
        selected.append(
            {"candidate_id": c["candidate_id"], **fingerprint(root / c["source_image"])}
        )
    audit = root / "audit"
    audit.mkdir(exist_ok=True)
    write_jsonl(audit / "selected_fingerprints.jsonl", selected)
    training_cache = UPSTREAM / "audit/training_image_fingerprints.jsonl"
    training = read_jsonl(training_cache)
    if any(x["status"] != "ok" for x in training):
        raise ValueError("incomplete training cache; inspect before claiming coverage")
    # Recover source paths for both v1 formal release and its later expansion.
    paths = {x["source_image_original"] for x in read_jsonl(REPO / "data/v1/provenance.jsonl")}
    legacy_rows = read_jsonl(REPO / "docs/results/qwen21_text_only_20261009/case_reviews.jsonl")
    inventory = {}
    for name in [
        "formal_candidate_pool_950.jsonl",
        "formal_candidate_pool_955.jsonl",
        "formal_candidate_pool_934_scored_repo.jsonl",
    ]:
        for item in read_jsonl(UPSTREAM / "goal_1k" / name):
            inventory[item["candidate_id"]] = item["source_image"]
    missing_ids = []
    for item in read_jsonl(UPSTREAM / "goal_1k/sav_source_review/test_review_queue.jsonl"):
        inventory[item["candidate_id"]] = item["image_path"]
    for r in legacy_rows:
        if r["batch"] == "new":
            key = r["case_id"].removeprefix("exp500-")
            if key in inventory:
                paths.add(inventory[key])
            elif r["source_dataset"] == "SA-V":
                missing_ids.append(key)
        m = re.search(r"paco_lvis_v1_(\d+)_", r["case_id"])
        if m:
            paths.add(
                f"/mnt/bn/strategy-mllm-train/intern/common_datasets/coco/val2017/{int(m[1]):012d}.jpg"
            )
        m = re.search(r"adepart_(\d+)_", r["case_id"])
        if m:
            paths.add(
                str(
                    UPSTREAM
                    / f"goal_1k/ade20k_part234/official/ADE20KPart234/images/validation/ADE_val_{int(m[1]):08d}.jpg"
                )
            )
    if missing_ids:
        raise ValueError(f"Unresolved legacy source identities: {missing_ids}")
    old_cache = audit / "v1_source_fingerprints.jsonl"
    cached = {x["path"]: x for x in read_jsonl(old_cache)} if old_cache.exists() else {}
    old = [
        cached[x]
        if x in cached and sha256_file(Path(x)) == cached[x]["actual_byte_sha256"]
        else fingerprint(Path(x))
        for x in sorted(paths)
    ]
    write_jsonl(audit / "v1_source_fingerprints.jsonl", old)
    lut = np.array([i.bit_count() for i in range(256)], dtype=np.uint8)
    flags = []
    counts = {}
    for group, records, threshold in [
        ("training", training, 8),
        ("v1", old, 10),
        ("v2_internal", selected, 10),
    ]:
        hashes = np.array([int(r["phash64"], 16) for r in records], dtype=np.uint64)
        pixels = {r["pixel_sha256"] for r in records}
        bytes_ = {r["actual_byte_sha256"] for r in records}
        exact = set()
        for i, c in enumerate(selected):
            variants = [("original", c), ("horizontal_flip", c["horizontal_flip"])]
            for variant, fp in variants:
                distances = lut[
                    (hashes ^ np.uint64(int(fp["phash64"], 16))).view(np.uint8).reshape(-1, 8)
                ].sum(axis=1)
                for j in np.flatnonzero(distances <= threshold):
                    if group == "v2_internal" and j <= i:
                        continue
                    r = records[j]
                    flags.append(
                        {
                            "group": group,
                            "candidate_id": c["candidate_id"],
                            "variant": variant,
                            "phash_distance": int(distances[j]),
                            "match_path": r["path"],
                            "match_candidate_id": r.get("candidate_id"),
                            "pixel_exact": fp["pixel_sha256"] == r["pixel_sha256"],
                            "byte_exact": c["actual_byte_sha256"] == r["actual_byte_sha256"],
                        }
                    )
                if group != "v2_internal" and (
                    fp["pixel_sha256"] in pixels or c["actual_byte_sha256"] in bytes_
                ):
                    exact.add(c["candidate_id"])
        counts[group] = {
            "reference_images": len(records),
            "phash_threshold": threshold,
            "exact_candidates": sorted(exact),
        }
    write_jsonl(audit / "overlap_flags.jsonl", flags)
    write_json(
        audit / "source_audit.json",
        {
            "selected_images": len(selected),
            "comparisons": counts,
            "flags": len(flags),
            "legacy_cases_covered": len(legacy_rows),
            "legacy_new_source_lookup": "candidate ID -> original source via versioned goal_1k inventories; PNG repackaging does not define a new source",
            "training_cache": str(training_cache),
            "training_cache_sha256": sha256_file(training_cache),
            "training_protocol": json.loads(
                (UPSTREAM / "audit/image_fingerprint_protocol.json").read_text()
            ),
            "scope": "Known task training source AND target cache; all v1 formal and expansion sources. Unknown base-model pretraining is not certified. Perceptual flags require recorded disposition.",
        },
    )
    print(
        json.dumps({"images": len(selected), "flags": flags, "counts": counts}, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
