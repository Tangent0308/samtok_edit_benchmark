"""Read-only COCO provenance and image-fingerprint audit against the existing training inventory."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from scipy.fft import dctn

from samtok_benchmark.io import sha256_file
from .data import immutable, load_turns, read


def lines(path):
    import json

    with Path(path).open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def perceptual(image):
    gray = image.convert("L")
    small = np.asarray(gray.resize((9, 8), Image.Resampling.LANCZOS), dtype=np.int16)
    d = int.from_bytes(np.packbits(small[:, 1:] > small[:, :-1]).tobytes(), "big")
    low = dctn(
        np.asarray(gray.resize((32, 32), Image.Resampling.LANCZOS), dtype=float),
        type=2,
        norm="ortho",
    )[:8, :8]
    p = int.from_bytes(np.packbits(low > np.median(low)).tobytes(), "big")
    return f"{d:016x}", f"{p:016x}"


def fingerprint(item):
    with Image.open(item["path"]) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
    d, p = perceptual(image)
    md, mp = perceptual(ImageOps.mirror(image))
    return {
        **item,
        "sha256": sha256_file(item["path"]),
        "size": list(image.size),
        "pixel_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
        "dhash": d,
        "phash": p,
        "mirror_dhash": md,
        "mirror_phash": mp,
    }


def actual_training(scopes):
    return any(
        s in {"s1_train", "s2_train", "pass1_train_seen", "pass1_train_source"}
        or s.startswith(("s1_train_", "s2_train_"))
        for s in scopes
    )


def audit(dataset, training_root, output):
    """Only exact identity or traced COCO ids confirm overlap; hash neighbours stay candidates."""
    output, training_root = Path(output), Path(training_root)
    receipt = read(training_root / "TRAINING.json")
    main = Path(receipt["mira_fingerprints"]["path"])
    inventory = main.with_name("INVENTORY.jsonl")
    inventory_receipt = read(main.with_name("INVENTORY.json"))
    bindings = [
        *receipt["mira_inventory_inputs"],
        {"path": str(main), "sha256": receipt["mira_fingerprints"]["sha256"]},
        {"path": str(inventory), "sha256": inventory_receipt["inventory_sha256"]},
        {
            "path": str(training_root / "GRES_FINGERPRINTS.jsonl"),
            "sha256": receipt["gres_fingerprints_sha256"],
        },
    ]

    def verify(entry):
        if sha256_file(entry["path"]) != entry["sha256"]:
            raise ValueError(f"Previously audited training input changed: {entry['path']}")
        return {"path": entry["path"], "sha256": entry["sha256"]}

    with ThreadPoolExecutor(max_workers=4) as pool:
        verified = list(pool.map(verify, bindings))
    print("Training receipt, metadata and fingerprint identities verified", flush=True)
    turns = load_turns(dataset)
    unique = {}
    for row in turns:
        for kind in ("source", "target"):
            a = row[kind]
            item = unique.setdefault(a["sha256"], {"path": a["path"], "uses": []})
            item["uses"].append(
                {"session_id": row["session_id"], "case_id": row["case_id"], "kind": kind}
            )
    with ThreadPoolExecutor(max_workers=4) as pool:
        queries = list(pool.map(fingerprint, unique.values()))
    immutable(output / "TEST_FINGERPRINTS.json", queries)
    scopes = {r["path"]: r["scopes"] for r in lines(inventory)}
    coco_use = read(training_root / "COCO_TRAINING_USE.json")
    gres = list(lines(training_root / "GRES_FINGERPRINTS.jsonl"))
    training = list(lines(main))
    known_coco = {str(r["coco_id"]) for r in gres if r.get("coco_id") is not None}
    sessions = sorted({r["session_id"] for r in turns}, key=int)
    id_matches = [
        {
            "session_id": sid,
            "coco_id": int(sid),
            "in_samtok_training_corpus": sid in known_coco,
            "finetuning_scopes": coco_use.get(sid, {}).get("scopes", []),
            "actual_finetuning": actual_training(coco_use.get(sid, {}).get("scopes", [])),
            "evidence": coco_use.get(sid, {}).get("records", []),
        }
        for sid in sessions
        if sid in known_coco or sid in coco_use
    ]
    candidates = []
    for name, rows in [("sitedit_inventory", training), ("samtok_gres_corpus", gres)]:
        d = np.array([int(r["dhash"], 16) for r in rows], dtype=np.uint64)
        p = np.array([int(r["phash"], 16) for r in rows], dtype=np.uint64)
        exact_file, exact_pixel = {}, {}
        for i, r in enumerate(rows):
            exact_file.setdefault(r["sha256"], []).append(i)
            exact_pixel.setdefault((tuple(r["size"]), r["pixel_sha256"]), []).append(i)
        for n, q in enumerate(queries):
            dd = np.minimum(
                np.bitwise_count(d ^ np.uint64(int(q["dhash"], 16))),
                np.bitwise_count(d ^ np.uint64(int(q["mirror_dhash"], 16))),
            )
            pd = np.minimum(
                np.bitwise_count(p ^ np.uint64(int(q["phash"], 16))),
                np.bitwise_count(p ^ np.uint64(int(q["mirror_phash"], 16))),
            )
            ids = set(np.where((dd <= 6) | (pd <= 8))[0].tolist())
            ids.update(exact_file.get(q["sha256"], []))
            ids.update(exact_pixel.get((tuple(q["size"]), q["pixel_sha256"]), []))
            for i in sorted(ids):
                r = rows[i]
                scope = (
                    scopes.get(r["path"], [])
                    if name == "sitedit_inventory"
                    else coco_use.get(str(r.get("coco_id")), {}).get("scopes", [])
                )
                candidates.append(
                    {
                        "query_path": q["path"],
                        "uses": q["uses"],
                        "set": name,
                        "training_path": r["path"],
                        "training_coco_id": r.get("coco_id"),
                        "dhash_distance": int(dd[i]),
                        "phash_distance": int(pd[i]),
                        "file_equal": q["sha256"] == r["sha256"],
                        "pixels_equal": q["size"] == r["size"]
                        and q["pixel_sha256"] == r["pixel_sha256"],
                        "scopes": scope,
                        "actual_finetuning": actual_training(scope),
                    }
                )
            if (n + 1) % 100 == 0:
                print(f"{name}: {n + 1}/{len(queries)} image fingerprints compared", flush=True)
    exact = [c for c in candidates if c["file_equal"] or c["pixels_equal"]]
    confirmed = {r["session_id"] for r in id_matches if r["actual_finetuning"]}
    confirmed.update(u["session_id"] for c in exact if c["actual_finetuning"] for u in c["uses"])
    corpus = {r["session_id"] for r in id_matches if r["in_samtok_training_corpus"]}
    corpus.update(
        u["session_id"] for c in exact if c["set"] == "samtok_gres_corpus" for u in c["uses"]
    )
    excluded = confirmed | corpus
    report = {
        "schema": "magicbrush.overlap.v1",
        "sessions": len(sessions),
        "turns": len(turns),
        "query_unique_images": len(queries),
        "verified_training_inputs": verified,
        "training_receipt_sha256": sha256_file(training_root / "TRAINING.json"),
        "coco_trace_sha256": sha256_file(training_root / "COCO_TRAINING_USE.json"),
        "training_fingerprint_rows": len(training),
        "gres_fingerprint_rows": len(gres),
        "coco_id_matches": id_matches,
        "candidate_pairs": len(candidates),
        "candidate_sessions": sorted(
            {u["session_id"] for c in candidates for u in c["uses"]}, key=int
        ),
        "confirmed_finetuning_overlap": sorted(confirmed, key=int),
        "known_samtok_corpus_overlap": sorted(corpus, key=int),
        "excluded_sessions": sorted(excluded, key=int),
        "clean_sessions": [sid for sid in sessions if sid not in excluded],
        "clean_turns": sum(r["session_id"] not in excluded for r in turns),
        "policy": "Common session exclusion: confirmed actual-finetuning overlap OR known SAMTok corpus COCO/image identity. Perceptual neighbours alone do not trigger exclusion.",
        "limits": "Actual use of the local gRES mixture by the frozen SAMTok base checkpoint is not verified. Foundation pretraining and undocumented data use are outside this audit. Clean means no overlap identified within audited inventories.",
    }
    immutable(output / "CANDIDATES.json", candidates)
    immutable(output / "OVERLAP.json", report)
    return {
        k: v
        for k, v in report.items()
        if k
        not in {
            "verified_training_inputs",
            "coco_id_matches",
            "candidate_sessions",
            "clean_sessions",
        }
    }
