"""Decode all pinned Inter-Edit/Omni records into a new full-run directory (python -I)."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
import tarfile

import numpy as np
from PIL import Image

from samtok_benchmark.external_refedit.data import immutable, read
from samtok_benchmark.ifbench.canvas import make_source
from samtok_benchmark.io import digest, sha256_file
from .data import make_public
from .mask_public import asset, verify_public


def safe_name(name):
    name = name.removeprefix("./")
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or not name:
        raise ValueError("Unsafe archive member")
    return name


def extract_archive(path, destination, wanted):
    found = set()
    with tarfile.open(path, "r|*") as stream:
        for member in stream:
            name = safe_name(member.name)
            if name not in wanted:
                continue
            if not member.isfile() or member.size > 64 * 1024 * 1024:
                raise ValueError("Invalid image archive member")
            blob = stream.extractfile(member).read()
            output = destination / name
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists():
                if output.read_bytes() != blob:
                    raise ValueError(f"Existing decoded bytes changed: {output}")
            else:
                with output.open("xb") as out:
                    out.write(blob)
            found.add(name)
    return found


def mask_public(row, directory, record_invalid=False):
    source, geometry = make_source(row["source"], directory)
    with Image.open(row["mask"]["path"]) as im:
        mask = im.convert("L").resize(tuple(geometry["source_size"]), Image.Resampling.NEAREST)
    binary = Image.fromarray((np.array(mask) > 128).astype(np.uint8) * 255)
    content = binary.resize(tuple(geometry["content_size"]), Image.Resampling.NEAREST)
    canvas = Image.new("L", tuple(geometry["canvas_size"]), 0)
    canvas.paste(content, tuple(geometry["offset_xy"]))
    path = directory / "mask.png"
    if path.exists():
        with Image.open(path) as old:
            if old.size != canvas.size or old.tobytes() != canvas.tobytes():
                raise ValueError("Public mask changed")
    else:
        canvas.save(path)
    public = {
        "schema": "interedit.public.v1",
        "case_id": row["case_id"],
        "source": source,
        "mask": asset(path),
        "instruction": row["instruction"],
    }
    public["input_digest"] = digest(public)
    invalid = not np.array(mask).any()
    # Retain malformed released data for review without inventing a selected
    # region. This switch only records the defect; it grants no inference or
    # scoring policy. The launcher separately requires an approved decision.
    if not (invalid and record_invalid):
        verify_public(public)
    immutable(directory / "public.json", public)
    return {
        "public": str(directory / "public.json"),
        "public_sha256": sha256_file(directory / "public.json"),
        "geometry": geometry,
        **({"input_error": "official_empty_mask"} if invalid else {}),
    }


def prepare(benchmark, existing, dataset, bundle, workers=8, record_invalid=False):
    existing, dataset, bundle = map(lambda p: Path(p).resolve(), (existing, dataset, bundle))
    if dataset == existing or dataset.is_relative_to(existing):
        raise ValueError("Do not modify the existing dataset")
    provenance = read(existing / "SOURCE.json")
    with ThreadPoolExecutor(max_workers=3) as pool:
        checks = list(
            pool.map(lambda x: sha256_file(x["path"]) == x["sha256"], provenance["files"])
        )
    if not all(checks):
        raise ValueError("Downloaded official bytes changed")
    if benchmark == "interedit":
        rows = read(existing / "raw/metadata.json")
        keys = ("source_path", "gt_path", "mask_path")
        prefix = ""
        archives = [
            existing / "raw" / name
            for name in ("source_images.tar", "target_images.tar", "masks.tar")
        ]
        expected = 6250
    elif benchmark == "omni_iie":
        rows = read(existing / "raw/single_turn.json")
        keys = (
            "original_image_path",
            "modified_image_path",
            "source_mask_path",
            "target_mask_path",
        )
        prefix = "single_turn/"
        archives = [existing / "raw/single_turn.tar.gz"]
        expected = 1723
    else:
        raise ValueError(benchmark)
    if len(rows) != expected:
        raise ValueError("The pinned release record count changed")
    wanted = {safe_name(prefix + safe_name(row[key])) for row in rows for key in keys}
    with ThreadPoolExecutor(max_workers=3) as pool:
        found = set().union(
            *pool.map(lambda p: extract_archive(p, dataset / "assets", wanted), archives)
        )
    if found != wanted:
        raise ValueError(f"Missing published assets: {sorted(wanted - found)[:10]}")
    print(f"Decoded {len(found)} published assets", flush=True)
    immutable(
        dataset / "SOURCE.json",
        {
            "upstream": provenance,
            "upstream_source_sha256": sha256_file(existing / "SOURCE.json"),
            "benchmark": benchmark,
            "requests": expected,
            "policy": "all released records; no filtering",
            "metadata": str(
                existing
                / "raw"
                / ("metadata.json" if benchmark == "interedit" else "single_turn.json")
            ),
            "declared_data_card_requests": 6250 if benchmark == "interedit" else 1725,
        },
    )

    def one(row):
        assets = {
            k: asset(dataset / "assets" / safe_name(prefix + safe_name(row[k]))) for k in keys
        }
        if benchmark == "interedit":
            cid = str(row["index"]).zfill(5)
            instruction, category = row["instruction"], row["edit_type"]
            source, target, mask = (assets[k] for k in keys)
            public = mask_public(
                {"case_id": cid, "source": source, "mask": mask, "instruction": instruction},
                bundle / "public" / cid,
                record_invalid=record_invalid,
            )
            extra = {"language": row["language"]}
        else:
            cid = (
                Path(row["original_image_path"]).parent.name.replace("(", "_").replace(")", "_")
                + "-"
                + row["sample_id"]
                + "-"
                + row["level"]
            )
            if "/" in cid or ".." in cid:
                raise ValueError("Unsafe case ID")
            instruction, category = row["modification_text"], row["level"]
            source, target, mask = (
                assets[k]
                for k in ("original_image_path", "modified_image_path", "target_mask_path")
            )
            public = make_public(cid, source, instruction, bundle / "public" / cid)
            extra = {"pair": row["original_image_path"], "source_mask": assets["source_mask_path"]}
        case = {
            "case_id": cid,
            "sequence_id": cid,
            "turn": 0,
            "parent_case_id": None,
            "task": category,
            "instruction": instruction,
            **public,
        }
        private = {
            "case_id": cid,
            "task": category,
            "turn": 0,
            "sequence_id": cid,
            "canonical_source": source,
            "target": target,
            "mask": mask,
            "instruction": instruction,
            **extra,
        }
        return case, private

    cases, private = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for case, row in pool.map(one, rows):
            cases.append(case)
            private.append(row)
            if len(cases) % 100 == 0:
                print(f"Prepared {len(cases)}/{expected}", flush=True)
    if len({r["case_id"] for r in cases}) != expected:
        raise ValueError("Duplicate release IDs")
    immutable(bundle / "private/evaluation.json", private)
    index = {
        "schema": "external.full.bundle.v1",
        "benchmark": benchmark,
        "scope": "full",
        "revision": provenance["revision"],
        "counts": dict(Counter(x["task"] for x in cases)),
        "cases": sorted(cases, key=lambda x: x["case_id"]),
        "provenance": {
            "source": str(dataset / "SOURCE.json"),
            "source_sha256": sha256_file(dataset / "SOURCE.json"),
            "private_sha256": sha256_file(bundle / "private/evaluation.json"),
        },
    }
    index["digest"] = digest(index)
    immutable(bundle / "index.json", index)
    print(f"READY INPUTS {benchmark}: {len(cases)} requests {index['digest']}", flush=True)
    return index
