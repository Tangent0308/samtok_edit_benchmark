"""The sole private-to-public boundary. Downstream code receives only this schema."""

from __future__ import annotations

import copy
import math
from pathlib import Path

import numpy as np
from PIL import Image

from samtok_benchmark.io import asset_path, digest, sha256_file
from . import MANIFEST_SHA256, PROTOCOL, SCHEMA, SETTINGS
from .plan import modes

TOP_KEYS = {
    "schema",
    "protocol",
    "request_id",
    "case_id",
    "setting",
    "source",
    "units",
    "manifest_sha256",
    "input_digest",
}
UNIT_KEYS = {"id", "operation", "instruction", "has_ref", "locator", "region"}


def public_digest(request):
    obj = copy.deepcopy(request)
    obj.pop("input_digest", None)
    obj["source"].pop("path", None)
    for u in obj["units"]:
        if u["locator"] == "mask":
            u["region"].pop("path", None)
    return digest(obj)


def project(case, setting, assigned, dataset_root: Path):
    selected = modes(setting, assigned)
    units = []
    for unit in sorted(case["units"], key=lambda u: int(u["id"][1:])):
        m = selected[unit["id"]]
        locator = m["locator"]
        region = None
        if locator == "mask":
            region = {
                "path": str(asset_path(dataset_root, unit["target"]["mask"])),
                "sha256": unit["target"]["mask_sha256"],
            }
        elif locator in {"point", "box"}:
            region = {"coordinates": list(unit["target"][locator])}
        units.append(
            {
                "id": unit["id"],
                "operation": unit["operation"],
                "instruction": unit["instruction_ref" if m["has_ref"] else "instruction_noref"],
                "has_ref": m["has_ref"],
                "locator": locator,
                "region": region,
            }
        )
    request = {
        "schema": SCHEMA,
        "protocol": PROTOCOL,
        "request_id": f"{case['id']}--{setting}",
        "case_id": case["id"],
        "setting": setting,
        "source": {
            "path": str(asset_path(dataset_root, case["source"]["image"])),
            "sha256": case["source"]["sha256"],
            "size": list(case["source"]["size"]),
        },
        "units": units,
        "manifest_sha256": MANIFEST_SHA256,
    }
    request["input_digest"] = public_digest(request)
    verify(request)
    return request


def verify(request, assets=False):
    from .canvas import PROTOCOL as CANVAS_PROTOCOL

    if set(request) != TOP_KEYS or request["schema"] != SCHEMA or request["protocol"] not in {PROTOCOL, CANVAS_PROTOCOL}:
        raise ValueError("Private/unknown/missing public fields or wrong schema")
    if request["setting"] not in SETTINGS or request["manifest_sha256"] != MANIFEST_SHA256:
        raise ValueError("Wrong setting/release")
    if request["input_digest"] != public_digest(request):
        raise ValueError("Public request digest mismatch")
    source = request["source"]
    if set(source) != {"path", "sha256", "size"} or len(source["size"]) != 2:
        raise ValueError("Invalid public source")
    w, h = source["size"]
    if any(type(x) is not int or x <= 0 for x in (w, h)):
        raise ValueError("Invalid source size")
    ids = [u["id"] for u in request["units"]]
    if ids != [f"U{i + 1}" for i in range(len(ids))] or not 2 <= len(ids) <= 5:
        raise ValueError("Incomplete or unordered unit IDs")
    for u in request["units"]:
        if (
            set(u) != UNIT_KEYS
            or not isinstance(u["instruction"], str)
            or not u["instruction"].strip()
        ):
            raise ValueError("Private/unknown/missing public unit fields")
        if u["operation"] not in {"add", "remove", "replace", "attribute"}:
            raise ValueError("Unknown operation")
        if type(u["has_ref"]) is not bool or (not u["has_ref"] and u["locator"] == "none"):
            raise ValueError("No-ref without a locator")
        loc, r = u["locator"], u["region"]
        if loc == "none":
            if r is not None:
                raise ValueError("Hidden geometry in none input")
        elif loc == "mask":
            if not isinstance(r, dict) or set(r) != {"path", "sha256"}:
                raise ValueError("Mask input must not expose hidden point or box")
            if assets:
                if sha256_file(Path(r["path"])) != r["sha256"]:
                    raise ValueError("Mask asset changed")
                with Image.open(r["path"]) as im:
                    if list(im.size) != source["size"]:
                        raise ValueError("Mask dimensions differ from source")
                    pixels = np.asarray(im.convert("L"))
                    if not np.isin(pixels, [0, 255]).all() or not pixels.any():
                        raise ValueError("Empty/nonbinary mask")
        elif loc in {"point", "box"}:
            if not isinstance(r, dict) or set(r) != {"coordinates"}:
                raise ValueError("Coordinates must not expose other locator types")
            p = r["coordinates"]
            numeric = (int, float) if request["protocol"] == CANVAS_PROTOCOL else (int,)
            if len(p) != (2 if loc == "point" else 4) or any(type(x) not in numeric or not math.isfinite(x) for x in p):
                raise ValueError("Invalid public pixel coordinates")
            valid = (
                (0 <= p[0] < w and 0 <= p[1] < h)
                if loc == "point"
                else (0 <= p[0] < p[2] <= w and 0 <= p[1] < p[3] <= h)
            )
            if not valid:
                raise ValueError("Invalid/out-of-bounds public geometry")
        else:
            raise ValueError("Unknown locator")
    if assets:
        if sha256_file(Path(source["path"])) != source["sha256"]:
            raise ValueError("Source asset changed")
        with Image.open(source["path"]) as im:
            if list(im.size) != source["size"]:
                raise ValueError("Source dimensions changed")
