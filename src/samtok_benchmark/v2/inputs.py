"""Prepare explicit public inputs; evaluator annotations never reach an editor job."""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from samtok_benchmark.io import asset_path, digest, sha256_file, write_jsonl
from samtok_benchmark.v2 import PROTOCOLS
from samtok_benchmark.v2.dataset import validate, load_cases

VARIANTS = ("mixed", "all_ref", "all_mask_noref", "single")
COLORS = ((235, 40, 75), (0, 150, 240), (0, 190, 110), (220, 135, 0))
PUBLIC_KEYS = {
    "schema_version",
    "job_id",
    "case_id",
    "variant",
    "unit_ids",
    "protocol",
    "prompt",
    "units",
    "images",
    "source_size",
    "input_files",
    "input_digest",
    "manifest_sha256",
}
UNIT_KEYS = {"id", "operation", "has_ref", "locator", "instruction", "region"}


def modes(case, variant):
    units = copy.deepcopy(case["units"])
    if variant == "all_ref":
        for u in units:
            u["interaction"] = {"has_ref": True, "locator": "none"}
    elif variant == "all_mask_noref":
        for u in units:
            u["interaction"] = {"has_ref": False, "locator": "mask"}
    return units


def render_locators(case, units, root, path):
    """Only supplied locators are drawn. Ref-only units have no graphical hint."""
    image = Image.open(asset_path(root, case["source"]["image"])).convert("RGB")
    w, h = image.size
    line = max(2, round(min(w, h) / 180))
    font = ImageFont.load_default(size=max(13, round(min(w, h) / 30)))
    for u in units:
        locator = u["interaction"]["locator"]
        if locator == "none":
            continue
        color = COLORS[int(u["id"][1:]) - 1]
        target = u["target"]
        if locator == "mask":
            mask = Image.open(asset_path(root, target["mask"])).convert("L")
            alpha = mask.point(lambda v: round(v * 0.35))
            image = Image.composite(Image.new("RGB", image.size, color), image, alpha)
            edge = np.array(mask) > np.array(mask.filter(ImageFilter.MinFilter(3)))
            image.paste(color, (0, 0, w, h), Image.fromarray(edge.astype("uint8") * 255))
            x, y = target["point"]
        elif locator == "box":
            x1, y1, x2, y2 = target["box"]
            ImageDraw.Draw(image).rectangle((x1, y1, x2 - 1, y2 - 1), outline=color, width=line)
            x, y = x1, y1
        else:
            x, y = target["point"]
            r = max(4, line * 2)
            d = ImageDraw.Draw(image)
            d.ellipse((x - r - 1, y - r - 1, x + r + 1, y + r + 1), fill="white")
            d.ellipse((x - r, y - r, x + r, y + r), fill=color)
        d = ImageDraw.Draw(image)
        bx = d.textbbox((0, 0), u["id"], font=font)
        tw, th = bx[2] - bx[0] + 6, bx[3] - bx[1] + 6
        lx, ly = min(max(0, x + line * 3), w - tw), min(max(0, y - th - line), h - th)
        d.rectangle((lx, ly, lx + tw, ly + th), fill=color)
        d.text((lx + 3, ly + 3 - bx[1]), u["id"], font=font, fill="white")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _digest(job):
    return digest({k: v for k, v in job.items() if k != "input_digest"})


def verify_job(job):
    if set(job) != PUBLIC_KEYS:
        raise ValueError("unexpected or missing public job fields")
    if job["protocol"] not in PROTOCOLS or job["input_digest"] != _digest(job):
        raise ValueError("public input digest/protocol mismatch")
    if job["schema_version"] != "2.0" or job["variant"] not in VARIANTS:
        raise ValueError("invalid public schema/variant")
    size = job["source_size"]
    if len(size) != 2 or any(type(v) is not int or v <= 0 for v in size):
        raise ValueError("invalid source dimensions")
    width, height = size
    expected_images = 1 + int(
        job["protocol"] == "visual_locator_v2" and any(u["locator"] != "none" for u in job["units"])
    )
    if len(job["images"]) != expected_images:
        raise ValueError("unexpected image count for the supplied interaction protocol")
    files = {f["path"]: f for f in job["input_files"]}
    if len(files) != len(job["input_files"]) or not job["images"]:
        raise ValueError("invalid input file inventory")
    used = set(job["images"])
    if len(job["units"]) != len(set(job["unit_ids"])):
        raise ValueError("duplicate unit binding")
    if [u["id"] for u in job["units"]] != job["unit_ids"]:
        raise ValueError("unit binding mismatch")
    for u in job["units"]:
        if set(u) - UNIT_KEYS or not {
            "id",
            "instruction",
            "operation",
            "has_ref",
            "locator",
        } <= set(u):
            raise ValueError("private/unknown field in public unit")
        if type(u["has_ref"]) is not bool or u["locator"] not in {"none", "point", "box", "mask"}:
            raise ValueError("invalid interaction")
        if not u["has_ref"] and u["locator"] == "none":
            raise ValueError("no-ref requires localization")
        r = u.get("region")
        native_region = job["protocol"] == "native_regions_v2" and u["locator"] != "none"
        if native_region:
            if not isinstance(r, dict) or set(r) != {u["locator"]}:
                raise ValueError("native region must expose only the supplied modality")
            if u["locator"] == "mask":
                used.add(r["mask"])
            else:
                coords = r[u["locator"]]
                count = 2 if u["locator"] == "point" else 4
                if (
                    not isinstance(coords, list)
                    or len(coords) != count
                    or any(type(v) is not int for v in coords)
                ):
                    raise ValueError("native coordinates must be integer source pixels")
                if count == 2:
                    if not (0 <= coords[0] < width and 0 <= coords[1] < height):
                        raise ValueError("native point lies outside source")
                elif not (
                    0 <= coords[0] < coords[2] <= width and 0 <= coords[1] < coords[3] <= height
                ):
                    raise ValueError("invalid native half-open box")
        elif r is not None:
            raise ValueError("unsupplied locator leaked to editor")
    if set(files) != used:
        raise ValueError("unreferenced or unbound public file")
    for f in files.values():
        if sha256_file(Path(f["path"])) != f["sha256"]:
            raise ValueError("input asset changed")
    with Image.open(job["images"][0]) as im:
        if list(im.size) != job["source_size"]:
            raise ValueError("source size changed")
    for path in job["images"][1:]:
        with Image.open(path) as im:
            if list(im.size) != size:
                raise ValueError("locator/source size mismatch")


def prepare(
    manifest: Path, root: Path, output: Path, protocol="visual_locator_v2", variants=("mixed",)
):
    if protocol not in PROTOCOLS or not variants or set(variants) - set(VARIANTS):
        raise ValueError("invalid protocol or diagnostic variant")
    validate(manifest, root)
    output.mkdir(parents=True, exist_ok=True)
    jobs = []
    for case in load_cases(manifest):
        for variant in variants:
            all_units = modes(case, variant)
            groups = [[u] for u in all_units] if variant == "single" else [all_units]
            for units in groups:
                job_id = f"{case['id']}--{variant}" + (
                    f"-{units[0]['id']}" if variant == "single" else ""
                )
                source = asset_path(root, case["source"]["image"])
                images = [str(source)]
                files = [
                    {
                        "path": str(source),
                        "sha256": case["source"]["sha256"],
                        "role": "clean_source",
                    }
                ]
                public = []
                for u in units:
                    i = u["interaction"]
                    p = {
                        "id": u["id"],
                        "operation": u["operation"],
                        **i,
                        "instruction": u[
                            "instruction_ref" if i["has_ref"] else "instruction_noref"
                        ],
                    }
                    if protocol == "native_regions_v2" and i["locator"] != "none":
                        loc = i["locator"]
                        if loc == "mask":
                            mask = asset_path(root, u["target"]["mask"])
                            p["region"] = {"mask": str(mask)}
                            files.append(
                                {
                                    "path": str(mask),
                                    "sha256": u["target"]["mask_sha256"],
                                    "role": u["id"] + "_user_mask",
                                }
                            )
                        else:
                            p["region"] = {loc: u["target"][loc]}
                    public.append(p)
                if protocol == "visual_locator_v2" and any(u["locator"] != "none" for u in public):
                    locator_image = (output / "locators" / f"{job_id}.png").resolve()
                    render_locators(case, units, root, locator_image)
                    images.append(str(locator_image))
                    files.append(
                        {
                            "path": str(locator_image),
                            "sha256": sha256_file(locator_image),
                            "role": "user_locators",
                        }
                    )
                intro = (
                    "Edit the first image and return one edited image at the same size. Execute every numbered unit completely. "
                    "Each unit concerns a different physical object. Keep all non-target objects, other parts, people, background, "
                    "camera framing and pose unchanged. Allow only local appearance/shadow adjustments physically necessary for the requested edits. "
                    "Ref means a textual referring expression; no reference image is provided. "
                )
                if protocol == "visual_locator_v2":
                    intro += "If a second image is supplied, it is only a copy with user locators: labeled points, outlined boxes, or translucent masks. Associate each locator with its unit ID. Never reproduce colored locators or labels in the output. "
                else:
                    intro += "Use each unit's supplied native region (integer pixel point, half-open xyxy box, or binary full-size mask). "
                intro += "A point or box selects a part/object; it is not a license to change every nearby pixel. Edit every visible piece specified by that unit, including pieces separated by occlusion. A ref-only unit has no region hint."
                prompt = (
                    intro
                    + "\n\n"
                    + "\n".join(
                        f"{u['id']} [{'ref' if u['has_ref'] else 'no ref'}; {u['locator']}]: {u['instruction']}"
                        for u in public
                    )
                )
                job = {
                    "schema_version": "2.0",
                    "job_id": job_id,
                    "case_id": case["id"],
                    "variant": variant,
                    "unit_ids": [u["id"] for u in public],
                    "protocol": protocol,
                    "prompt": prompt,
                    "units": public,
                    "images": images,
                    "source_size": case["source"]["size"],
                    "input_files": files,
                    "manifest_sha256": sha256_file(manifest),
                }
                job["input_digest"] = _digest(job)
                verify_job(job)
                jobs.append(job)
    write_jsonl(output / "jobs.jsonl", jobs)
    return jobs
