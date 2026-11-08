"""Strict public mask contract. No target/reference/scoring annotation is accepted."""

from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from samtok_benchmark.ifbench.canvas import make_source
from samtok_benchmark.io import digest, sha256_file
from samtok_benchmark.external_refedit.data import immutable

KEYS = {"schema", "case_id", "source", "mask", "instruction", "input_digest"}


def asset(path):
    with Image.open(path) as im:
        return {
            "path": str(Path(path).resolve()),
            "size": list(im.size),
            "sha256": sha256_file(path),
        }


def verify_public(public):
    if set(public) != KEYS or public["schema"] != "interedit.public.v1":
        raise ValueError("Unknown/private public fields")
    if public["input_digest"] != digest({k: v for k, v in public.items() if k != "input_digest"}):
        raise ValueError("Public digest changed")
    if not isinstance(public["instruction"], str) or not public["instruction"].strip():
        raise ValueError("Empty public instruction")
    for key in ("source", "mask"):
        if public[key] != asset(public[key]["path"]):
            raise ValueError("Changed public image")
    mask = np.array(Image.open(public["mask"]["path"]).convert("L"))
    if (
        public["source"]["size"] != public["mask"]["size"]
        or not np.isin(mask, [0, 255]).all()
        or not mask.any()
    ):
        raise ValueError("Invalid public mask")


def prepare(rows, output, provenance):
    output = Path(output).resolve()
    cases = []
    for row in rows:
        if set(row) != {"case_id", "source", "mask", "instruction"}:
            raise ValueError("Private annotation passed to public builder")
        directory = output / "public" / row["case_id"]
        source, geometry = make_source(row["source"], directory)
        if row["mask"] != asset(row["mask"]["path"]):
            raise ValueError("Canonical public mask changed")
        mask = Image.open(row["mask"]["path"]).convert("L")
        # Released masks use a smaller normalized image grid; the native scorer maps
        # them to source size with NEAREST. Apply the same deterministic mapping.
        mask = mask.resize(tuple(geometry["source_size"]), Image.Resampling.NEAREST)
        mask = Image.fromarray((np.array(mask) > 128).astype(np.uint8) * 255)
        content = mask.resize(tuple(geometry["content_size"]), Image.Resampling.NEAREST)
        mapped = Image.new("L", tuple(geometry["canvas_size"]), 0)
        mapped.paste(content, tuple(geometry["offset_xy"]))
        path = directory / "mask.png"
        stream = BytesIO()
        mapped.save(stream, format="PNG")
        if path.exists():
            if path.read_bytes() != stream.getvalue():
                raise ValueError("Mapped public mask changed")
        else:
            path.write_bytes(stream.getvalue())
        public = {
            "schema": "interedit.public.v1",
            "case_id": row["case_id"],
            "source": source,
            "mask": asset(path),
            "instruction": row["instruction"],
        }
        public["input_digest"] = digest(public)
        verify_public(public)
        immutable(directory / "public.json", public)
        cases.append(
            {
                "case_id": row["case_id"],
                "public": str(directory / "public.json"),
                "public_sha256": sha256_file(directory / "public.json"),
                "geometry": geometry,
            }
        )
    index = {
        "schema": "external.pilot.bundle.v1",
        "scope": "fixed-small-subset",
        "provenance": provenance,
        "cases": cases,
    }
    index["digest"] = digest(index)
    immutable(output / "index.json", index)
    return index
