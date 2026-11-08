"""Isolated parsing of pinned Parquet bytes; never run dataset-shipped Python."""

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image

from samtok_benchmark.external_refedit.data import (
    immutable,
    read,
    verify_public as verify_text_public,
)
from samtok_benchmark.ifbench.canvas import make_source, validate_geometry
from samtok_benchmark.io import digest, sha256_file
from . import COUNTS, REVISION, VLM_TASKS


def verify_public(public):
    if public.get("schema") == "interedit.public.v1":
        from .mask_public import verify_public as verify_mask

        return verify_mask(public)
    return verify_text_public(public)


def identity(task, image_path):
    if task not in COUNTS:
        raise ValueError(f"Unknown task: {task}")
    suffix = hashlib.sha256(image_path.encode()).hexdigest()[:16]
    case = f"{task}--{suffix}"
    if task.startswith("multi_turn"):
        prefix, name = image_path.split("/", 1)
        turn = {"turn1_add": 1, "turn2_add": 2, "turn1_remove": 1, "turn2_remove": 2}[prefix]
        if not prefix.endswith(task.removeprefix("multi_turn_")):
            raise ValueError("Mismatched turn/task")
        sequence = f"{task}--{hashlib.sha256(name.encode()).hexdigest()[:16]}"
    else:
        sequence, turn = case, 0
    return case, sequence, turn


def make_public(case, source, instruction, directory):
    source, geometry = make_source(source, directory)
    public = {
        "schema": "refedit.public.v1",
        "case_id": case,
        "source": source,
        "instruction": instruction,
    }
    public["input_digest"] = digest(public)
    verify_public(public)
    immutable(Path(directory) / "public.json", public)
    return {
        "public": str(Path(directory) / "public.json"),
        "public_sha256": sha256_file(Path(directory) / "public.json"),
        "geometry": geometry,
    }


def asset(blob, path):
    with Image.open(BytesIO(blob)) as image:
        image.load()
        size = list(image.size)
        pixel_sha = hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()
        fmt = image.format
    path = path.with_suffix({"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[fmt])
    path.parent.mkdir(parents=True, exist_ok=True)
    expected = hashlib.sha256(blob).hexdigest()
    if path.exists():
        if sha256_file(path) != expected:
            raise ValueError(f"Extracted asset changed: {path}")
    else:
        with path.open("xb") as stream:
            stream.write(blob)
    return {"path": str(path), "sha256": expected, "size": size, "rgb_pixels_sha256": pixel_sha}


def prepare(existing, dataset, bundle, workers=4):
    import pyarrow.parquet as pq

    existing, dataset, bundle = map(lambda p: Path(p).resolve(), (existing, dataset, bundle))
    if dataset == existing or dataset.is_relative_to(existing):
        raise ValueError("Use a new derived data directory; preserve the existing download")
    metadata, sources, cases, private = [], [], [], []
    paths = sorted((existing / "data").glob("*.parquet"))
    if len(paths) != 9:
        raise ValueError("Expected the seven single-turn and two multi-turn shards")
    for path in paths:
        revision, expected, *_ = (
            (existing / ".cache/huggingface/download/data" / (path.name + ".metadata"))
            .read_text()
            .splitlines()
        )
        actual = sha256_file(path)
        if revision != REVISION or actual != expected:
            raise ValueError(f"Official download identity mismatch: {path}")
        print(f"Verified source shard {path.name}", flush=True)
        sources.append(
            {
                "path": str(path),
                "sha256": actual,
                "url": f"https://huggingface.co/datasets/BohanJia/CompBench/resolve/{REVISION}/data/{path.name}",
            }
        )
        rows = pq.read_table(
            path, columns=["task", "image_path", "instruction", "caption"]
        ).to_pylist()
        metadata.extend({**r, "file": path.name, "row": i} for i, r in enumerate(rows))
    if dict(Counter(r["task"] for r in metadata)) != COUNTS:
        raise ValueError("The released task counts changed")
    sequences = defaultdict(dict)
    for row in metadata:
        cid, seq, turn = identity(row["task"], row["image_path"])
        if turn in sequences[seq]:
            raise ValueError("Duplicated row or sequence turn")
        sequences[seq][turn] = cid
    for seq, turns in sequences.items():
        if set(turns) not in ({0}, {1, 2}):
            raise ValueError(f"Incomplete sequence: {seq}")
    immutable(
        dataset / "SOURCE.json",
        {
            "repo": "BohanJia/CompBench",
            "revision": REVISION,
            "license": "CC BY 4.0",
            "files": sources,
            "counts": COUNTS,
            "total_requests": 3481,
            "two_turn_sequences": sum(1 in v for v in sequences.values()),
            "policy": "All published rows, no deduplication or score-based filtering",
        },
    )

    def extract(args):
        row, filename, row_number = args
        cid, sequence, turn = identity(row["task"], row["image_path"])
        assets = {
            key: asset(row[key]["bytes"], dataset / "assets" / cid / key)
            for key in ("input_image", "edited_image", "mask")
            if row.get(key) is not None
        }
        if "mask" not in assets and row["task"] not in VLM_TASKS:
            raise ValueError(f"Missing objective scoring mask: {cid}")
        item = {
            "case_id": cid,
            "sequence_id": sequence,
            "turn": turn,
            "task": row["task"],
            "instruction": row["instruction"],
            "parent_case_id": sequences[sequence][1] if turn == 2 else None,
        }
        if turn != 2:
            # The intermediate GT source of turn 2 is deliberately absent from public assets.
            source = {k: v for k, v in assets["input_image"].items() if k != "rgb_pixels_sha256"}
            item.update(make_public(cid, source, row["instruction"], bundle / "public" / cid))
        row_private = {
            "case_id": cid,
            "task": row["task"],
            "turn": turn,
            "sequence_id": sequence,
            "canonical_source": assets["input_image"],
            "target": assets["edited_image"],
            "mask": assets.get("mask"),
            "caption": row["caption"],
            "instruction": row["instruction"],
            "image_path": row["image_path"],
            "upstream_file": filename,
            "upstream_row": row_number,
        }
        return item, row_private

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for path in paths:
            for batch in pq.ParquetFile(path).iter_batches(batch_size=32):
                start = sum(1 for x in private if x["upstream_file"] == path.name)
                arguments = [(row, path.name, start + i) for i, row in enumerate(batch.to_pylist())]
                for item, priv in pool.map(extract, arguments):
                    cases.append(item)
                    private.append(priv)
            print(f"Prepared {path.name}: {len(cases)}/3481 requests", flush=True)
    by_id = {r["case_id"]: r for r in private}
    pair_audit = []
    for item in cases:
        if item["turn"] == 2:
            previous = by_id[item["parent_case_id"]]["target"]
            current = by_id[item["case_id"]]["canonical_source"]
            pair_audit.append(
                {
                    "case_id": item["case_id"],
                    "parent_case_id": item["parent_case_id"],
                    "bytes_equal": previous["sha256"] == current["sha256"],
                    "pixels_equal": previous["size"] == current["size"]
                    and previous["rgb_pixels_sha256"] == current["rgb_pixels_sha256"],
                }
            )
    immutable(bundle / "private/evaluation.json", private)
    immutable(dataset / "PAIR_AUDIT.json", pair_audit)
    index = {
        "schema": "compbench.full.bundle.v1",
        "revision": REVISION,
        "scope": "full",
        "counts": COUNTS,
        "cases": sorted(cases, key=lambda x: (x["sequence_id"], x["turn"])),
        "provenance": {
            "source": str(dataset / "SOURCE.json"),
            "source_sha256": sha256_file(dataset / "SOURCE.json"),
            "private_sha256": sha256_file(bundle / "private/evaluation.json"),
            "pair_audit_sha256": sha256_file(dataset / "PAIR_AUDIT.json"),
        },
    }
    index["digest"] = digest(index)
    immutable(bundle / "index.json", index)
    return index


def load_bundle(path, case_ids=None):
    index = read(Path(path) / "index.json")
    if index["schema"] not in {"compbench.full.bundle.v1", "external.full.bundle.v1"} or index[
        "digest"
    ] != digest({k: v for k, v in index.items() if k != "digest"}):
        raise ValueError("Invalid full CompBench bundle")
    for item in index["cases"]:
        if case_ids is not None and item["case_id"] not in case_ids:
            continue
        if item["turn"] == 2:
            if (
                any(k in item for k in ("public", "source", "geometry"))
                or not item["parent_case_id"]
            ):
                raise ValueError("Turn 2 must be resolved from model output, never canonical GT")
        else:
            if sha256_file(item["public"]) != item["public_sha256"]:
                raise ValueError("Public request modified")
            verify_public(read(item["public"]))
            validate_geometry(item["geometry"])
    return index


def resolve_input(item, model_root, expected_parent=None):
    """Returns public input plus parent binding, or an explicit dependency status."""
    if item["turn"] != 2:
        return item, None, None
    parent_path = Path(model_root) / "edit" / item["parent_case_id"] / "result.json"
    if not parent_path.exists():
        return None, None, "waiting_parent"
    parent = read(parent_path)
    if expected_parent and any(parent["identity"].get(k) != v for k, v in expected_parent.items()):
        raise ValueError("Parent model/configuration/bundle/code identity differs")
    binding = {
        "case_id": item["parent_case_id"],
        "receipt_sha256": sha256_file(parent_path),
        "output_sha256": parent.get("output_sha256"),
    }
    if parent["identity"]["case_id"] != item["parent_case_id"]:
        raise ValueError("Parent identity mismatch")
    if parent["status"] != "completed":
        return item, binding, "failed_parent"
    if sha256_file(parent["output_image"]) != parent["output_sha256"]:
        raise ValueError("Parent output modified")
    source = {
        "path": parent["output_image"],
        "sha256": parent["output_sha256"],
        "size": parent["output_size"],
    }
    immutable(Path(model_root) / "inputs" / item["case_id"] / "parent.json", binding)
    resolved = make_public(
        item["case_id"], source, item["instruction"], Path(model_root) / "inputs" / item["case_id"]
    )
    return {**item, **resolved}, binding, None
