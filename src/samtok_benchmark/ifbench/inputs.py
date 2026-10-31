"""Shared input forms. These are serializers, not selected model configurations."""

from __future__ import annotations

from pathlib import Path

from samtok_benchmark.io import digest, sha256_file, write_json
from .geometry import conversion_record, to_mask
from .public import verify
from .render import COLOR_NAMES, render

BASE = "Apply all of the following edits to the image. Keep everything else unchanged."
SELECTOR_NOTE = (
    "Each supplied region selects a source object, part, or anchor. "
    "For an addition, it selects the attachment or support location, not the outline of the new object."
)
DUAL = (
    "Image 1 is the clean source image to edit. Image 2 is the same image with colored marks and U labels. "
    "Use the marks only to identify the selected regions in Image 1. Return only the edited Image 1. "
    "Do not reproduce any marks, labels, or leader lines."
)
SINGLE = (
    "Edit the supplied image using its colored marks and U labels to identify the selected regions. "
    "Remove all marks, labels, and leader lines from the final edited image."
)


def global_prompt(request):
    return BASE + "\n" + "\n".join(f"{u['id']}. {u['instruction']}" for u in request["units"])


def visual_prompt(request, mode):
    if mode not in {"dual", "single"}:
        raise ValueError(mode)
    if not any(u["locator"] != "none" for u in request["units"]):
        return global_prompt(request)
    lines = []
    for u in request["units"]:
        tag = ""
        if u["locator"] != "none":
            color = COLOR_NAMES[int(u["id"][1:]) - 1]
            shape = {"point": "point", "box": "box", "mask": "mask contour"}[u["locator"]]
            tag = f" [{color} {shape}, label {u['id']}]"
        lines.append(f"{u['id']}.{tag} {u['instruction']}")
    return (
        (DUAL if mode == "dual" else SINGLE)
        + "\n"
        + SELECTOR_NOTE
        + "\n"
        + BASE
        + "\n"
        + "\n".join(lines)
    )


def coordinate_prompt(request):
    if not any(u["locator"] != "none" for u in request["units"]):
        return global_prompt(request)
    w, h = request["source"]["size"]
    prefix = (
        f"The source image is {w} pixels wide and {h} pixels high. Coordinates use the source canvas, "
        "origin at the top-left, x increasing rightward and y increasing downward. "
        "Points are (x,y) pixel locations. Boxes are half-open (x1,y1,x2,y2) pixel bounds. "
        "Use coordinates to identify regions; do not draw coordinates or labels in the output."
    )
    lines = []
    for u in request["units"]:
        tag = ""
        if u["locator"] == "point":
            tag = f" [point (x,y)={u['region']['coordinates']}]"
        elif u["locator"] in {"box", "mask"}:
            rec = conversion_record(u, (w, h))
            tag = f" [box (x1,y1,x2,y2)={rec['box_xyxy_pixels_half_open']}]"
        lines.append(f"{u['id']}.{tag} {u['instruction']}")
    return prefix + "\n" + SELECTOR_NOTE + "\n" + BASE + "\n" + "\n".join(lines)


def discard_region_prompt(request):
    if not request["setting"].startswith("S2-") or not all(u["has_ref"] for u in request["units"]):
        raise ValueError("Discard-region candidate is permitted only for S2 here")
    return global_prompt(request)


def export_inputs(request, directory: Path):
    verify(request, assets=True)
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "public.json", request)
    annotation = render(request, directory / "annotation.png")
    source = request["source"]["path"]
    forms = {}
    for mode in ("dual", "single", "coordinates"):
        prompt = (
            coordinate_prompt(request) if mode == "coordinates" else visual_prompt(request, mode)
        )
        paths = [source]
        if annotation:
            if mode == "dual":
                paths.append(annotation["path"])
            elif mode == "single":
                paths = [annotation["path"]]
        (directory / f"prompt.{mode}.txt").write_text(prompt + "\n")
        forms[mode] = {
            "images": paths,
            "prompt": prompt,
            "discard_region": False,
            "lossy_mask_to_box": mode == "coordinates"
            and any(u["locator"] == "mask" for u in request["units"]),
        }
    if request["setting"].startswith("S2-"):
        prompt = discard_region_prompt(request)
        forms["discard-region"] = {
            "images": [source],
            "prompt": prompt,
            "discard_region": True,
            "report_scope": "S2-best-adapted-only; excluded from paired region/language deltas",
        }
        (directory / "prompt.discard-region.txt").write_text(prompt + "\n")
    regions = []
    for u in request["units"]:
        rec = conversion_record(u, request["source"]["size"])
        mask = to_mask(u, request["source"]["size"])
        rec["mask"] = None
        if mask is not None:
            path = directory / "native" / f"{u['id']}.png"
            path.parent.mkdir(exist_ok=True)
            mask.save(path)
            rec["mask"] = {
                "path": str(path.resolve()),
                "sha256": sha256_file(path),
                "white_means_selected": True,
                "area_pixels": sum(mask.histogram()[1:]),
            }
        rec["instruction"] = u["instruction"]
        regions.append(rec)
    native = {
        "global_prompt": global_prompt(request),
        "units": regions,
        "missing_region_units": [u["id"] for u in request["units"] if u["locator"] == "none"],
        "no_automatic_grounding": True,
        "single_mask_sequence_order": [u["id"] for u in request["units"]],
    }
    write_json(directory / "native.json", native)
    payload = {
        "request_id": request["request_id"],
        "public_input_digest": request["input_digest"],
        "forms": forms,
        "annotation": annotation,
        "native": native,
        "model_adapter_status": "shared forms only; model-specific API serialization is checked at smoke milestone",
    }
    payload["digest"] = digest(payload)
    write_json(directory / "inputs.json", payload)
    return payload


def export_fairness_inputs(request, directory: Path):
    """Export only the two visual forms used by the frozen seven-method protocol."""
    verify(request, assets=True)
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "public.json", request)
    annotation = render(request, directory / "annotation.png")
    source = request["source"]["path"]
    forms = {}
    for mode in ("dual", "single"):
        prompt = visual_prompt(request, mode)
        images = [source]
        if annotation:
            images = [source, annotation["path"]] if mode == "dual" else [annotation["path"]]
        forms[mode] = {"images": images, "prompt": prompt, "discard_region": False,
                       "lossy_mask_to_box": False}
        (directory / f"prompt.{mode}.txt").write_text(prompt + "\n")
    payload = {"request_id": request["request_id"], "public_input_digest": request["input_digest"],
               "forms": forms, "annotation": annotation,
               "model_adapter_status": "frozen fairness v2.1 dual/single forms; no legacy conversions"}
    payload["digest"] = digest(payload)
    write_json(directory / "inputs.json", payload)
    return payload
