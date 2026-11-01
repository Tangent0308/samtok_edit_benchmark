"""Shared approximately one-megapixel inputs and reversible canvas geometry.

Only public geometry is transformed. Canonical source/GT assets never enter a
model request; the separate restoration record is consumed by the worker.
"""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path

from PIL import Image

from samtok_benchmark.io import digest, sha256_file, write_json

PROTOCOL = "ifbench-tiered-1mp-v1"
REVISION = "fairness-v2.2-1mp"
POLICY = {
    "version": "ifbench.canvas.1mp.v1",
    "target_area": 1024**2,
    "grid": 32,
    "scale_backoff": 0.995,
    "background_rgb": [128, 128, 128],
    "image_resampling": "LANCZOS",
    "mask_resampling": "NEAREST",
    "rounding": "ties-to-even content size; ceil grid; centered padding, extra right/bottom",
    "coordinates": "continuous affine pixel coordinates; only visualization is rasterized",
    "native_output_grid": ["replan", "mirage"],
}


def geometry(size):
    if len(size) != 2 or any(type(v) is not int or v <= 0 for v in size):
        raise ValueError("Invalid canonical source dimensions")
    w, h = size
    scale = math.sqrt(POLICY["target_area"] / (w * h))
    for _ in range(10000):
        fw, fh = max(1, round(w * scale)), max(1, round(h * scale))
        cw, ch = ((fw + 31) // 32) * 32, ((fh + 31) // 32) * 32
        if cw * ch <= POLICY["target_area"]:
            break
        scale *= POLICY["scale_backoff"]
    else:
        raise ValueError("Could not construct bounded canvas")
    if min(cw, ch) < 64 or max(cw, ch) > 4096:
        raise ValueError("Canvas exceeds common native aspect-ratio limits")
    left, top = (cw - fw) // 2, (ch - fh) // 2
    return {
        "policy_digest": digest(POLICY),
        "source_size": list(size),
        "content_size": [fw, fh],
        "canvas_size": [cw, ch],
        "content_box": [left, top, left + fw, top + fh],
        "scale_xy": [fw / w, fh / h],
        "offset_xy": [left, top],
    }


def validate_geometry(record):
    if record != geometry(record["source_size"]):
        raise ValueError("Canvas geometry differs from the fixed 1MP policy")


def make_source(source, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if sha256_file(Path(source["path"])) != source["sha256"]:
        raise ValueError("Canonical source bytes changed")
    transform = geometry(source["size"])
    path = directory / "source.png"
    if not path.exists():
        with Image.open(source["path"]) as original:
            if list(original.size) != source["size"]:
                raise ValueError("Canonical source size changed")
            content = original.convert("RGB").resize(
                tuple(transform["content_size"]), Image.Resampling.LANCZOS
            )
        canvas = Image.new("RGB", tuple(transform["canvas_size"]), tuple(POLICY["background_rgb"]))
        canvas.paste(content, tuple(transform["offset_xy"]))
        canvas.save(path)
    asset = {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "size": transform["canvas_size"],
    }
    write_json(directory / "geometry.json", transform)
    return asset, transform


def project_public(public, source, transform, directory):
    """Accept an already projected setting; never inspect undisclosed regions."""
    from .public import public_digest, verify

    verify(public, assets=True)
    validate_geometry(transform)
    if public["source"]["size"] != transform["source_size"]:
        raise ValueError("Source/canvas transform mismatch")
    result = deepcopy(public)
    result["protocol"] = PROTOCOL
    result["source"] = deepcopy(source)
    sx, sy = transform["scale_xy"]
    ox, oy = transform["offset_xy"]
    directory = Path(directory)
    for unit in result["units"]:
        loc = unit["locator"]
        if loc in {"point", "box"}:
            original_coordinates = unit["region"]["coordinates"]
            coordinates = [
                v * (sx if i % 2 == 0 else sy) + (ox if i % 2 == 0 else oy)
                for i, v in enumerate(original_coordinates)
            ]
            if loc == "box":
                for i in (2, 3):
                    axis = i % 2
                    limit = float(transform["canvas_size"][axis])
                    if (
                        original_coordinates[i] == transform["source_size"][axis]
                        and limit < coordinates[i] <= math.nextafter(limit, math.inf)
                    ):
                        coordinates[i] = limit
            unit["region"]["coordinates"] = coordinates
        elif loc == "mask":
            original = unit["region"]
            path = directory / (original["sha256"] + ".png")
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                with Image.open(original["path"]) as mask:
                    resized = mask.convert("L").resize(
                        tuple(transform["content_size"]), Image.Resampling.NEAREST
                    )
                canvas = Image.new("L", tuple(transform["canvas_size"]), 0)
                canvas.paste(resized, (ox, oy))
                if canvas.getbbox() is None:
                    raise ValueError(
                        f"Public mask disappeared at 1MP: {public['case_id']}/{unit['id']}"
                    )
                canvas.save(path)
            unit["region"] = {"path": str(path.resolve()), "sha256": sha256_file(path)}
    result["input_digest"] = public_digest(result)
    verify(result, assets=True)
    return result


def revise_request(model, request, public):
    """Apply only approved size controls; preserve prompts and native methods."""
    from .fairness_dev_revision import revise_request as previous_revision

    result = previous_revision(model, request)
    w, h = public["source"]["size"]
    if model == "qwen21":
        result["parameters"]["output_resolution"] = 1024
    if model in {"qwen2511", "qwen21", "flux2_klein9b", "flux3"}:
        result["parameters"].update(width=w, height=h)
    if model == "mice":
        result["model_size"] = [w, h]
    result["resolution_policy"] = POLICY["version"]
    for key in ("request_digest", "call_digest"):
        if key in result:
            result.pop(key)
            result[key] = digest(result)
    return result


def restore_output(raw, transform):
    """One LANCZOS operation: native-size content crop -> canonical source."""
    validate_geometry(transform)
    cw, ch = transform["canvas_size"]
    rw, rh = raw.size
    box = tuple(
        v * (rw / cw if i % 2 == 0 else rh / ch) for i, v in enumerate(transform["content_box"])
    )
    return raw.convert("RGB").resize(
        tuple(transform["source_size"]), Image.Resampling.LANCZOS, box=box
    )


def verify_request(plan, task, request, public):
    """Reject crossed canvases, hidden high-resolution inputs and stale outputs."""
    from .fairness_dev_plan import check_hash, read

    if plan.get("canvas_policy") != POLICY or public["protocol"] != PROTOCOL:
        raise ValueError("Missing or changed common 1MP policy")
    check_hash(task["canvas_transform"], task["canvas_transform_sha256"])
    transform = read(task["canvas_transform"])
    validate_geometry(transform)
    if public["source"]["size"] != transform["canvas_size"]:
        raise ValueError("Public source is not the registered canvas")
    if request.get("resolution_policy") != POLICY["version"]:
        raise ValueError("Model request lacks the 1MP policy")
    model = task["model"]
    w, h = transform["canvas_size"]
    params = request["parameters"]
    base = {k: v for k, v in params.items() if k not in {"width", "height"}}
    expected = plan["model_specifications"][model]["parameters"]
    # Method helper parameters include API-only fields, checked by their existing adapters.
    if model in {"qwen2511", "qwen21", "flux2_klein9b"} and base != expected:
        raise ValueError("Changed frozen native sampling parameters")
    if model in {"qwen2511", "qwen21", "flux2_klein9b", "flux3"}:
        if (params.get("width"), params.get("height")) != (w, h):
            raise ValueError("Requested output differs from the shared canvas")
    elif "width" in params or "height" in params:
        raise ValueError("Do not override native method output grids")
    if model == "mice" and request["model_size"] != [w, h]:
        raise ValueError("MICE binding grid differs from shared canvas")
    images = list(request.get("images", []))
    images += [
        request[k]
        for k in ("image", "planner_image", "editor_image", "grounding_image", "edit_image")
        if k in request
    ]
    allowed = {public["source"]["path"]}
    inputs = read(Path(task["public_request"]).with_name("inputs.json"))
    if inputs["annotation"]:
        allowed.add(inputs["annotation"]["path"])
    if not images or any(p not in allowed for p in images):
        raise ValueError("Model/planner received an unregistered image")
    for path in set(images):
        with Image.open(path) as im:
            if list(im.size) != [w, h]:
                raise ValueError("Model/planner received a different image size")
    if request.get("source", public["source"]) != public["source"]:
        raise ValueError("Model source coordinates differ from the public canvas")
    return transform
