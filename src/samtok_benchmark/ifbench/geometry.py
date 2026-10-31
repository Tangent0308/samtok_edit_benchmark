"""Region conversions consuming public geometry only, with explicit loss records."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw


def small_box(point, size):
    w, h = size
    side = max(1, round(min(w, h) * 0.05))
    x, y = point
    x1, y1 = math.floor(x - side / 2), math.floor(y - side / 2)
    return [max(0, x1), max(0, y1), min(w, x1 + side), min(h, y1 + side)]


def to_box(unit, size):
    loc, region = unit["locator"], unit["region"]
    if loc == "none":
        return None
    if loc == "point":
        return small_box(region["coordinates"], size)
    if loc == "box":
        return list(region["coordinates"])
    with Image.open(region["path"]) as im:
        box = im.convert("L").getbbox()
    if box is None:
        raise ValueError("Empty public mask")
    return list(box)


def to_mask(unit, size):
    if unit["locator"] == "none":
        return None
    if unit["locator"] == "mask":
        with Image.open(unit["region"]["path"]) as im:
            if im.size != tuple(size):
                raise ValueError("Mask/source geometry differs")
            return im.convert("L").copy()
    box = to_box(unit, size)
    result = Image.new("L", tuple(size), 0)
    x1, y1, x2, y2 = box
    ImageDraw.Draw(result).rectangle((x1, y1, x2 - 1, y2 - 1), fill=255)
    return result


def conversion_record(unit, size):
    box = to_box(unit, size)
    w, h = size
    return {
        "unit_id": unit["id"],
        "input_modality": unit["locator"],
        "box_xyxy_pixels_half_open": box,
        "box_xyxy_normalized": [box[0] / w, box[1] / h, box[2] / w, box[3] / h] if box else None,
        "box_yxyx_normalized": [box[1] / h, box[0] / w, box[3] / h, box[2] / w] if box else None,
        "box_conversion": {
            "point": "fixed-short-side-5-percent-box",
            "box": "identity",
            "mask": "tight-nonzero-half-open-bbox",
            "none": "unavailable",
        }[unit["locator"]],
        "shape_lost_in_box": unit["locator"] == "mask",
        "point_expansion_is_object_extent_prediction": False,
        "hidden_geometry_used": False,
        "external_model_used": False,
        "source_role": "anchor" if unit["operation"] == "add" else "target",
    }


def mask_array(mask):
    return np.asarray(mask.convert("L")) > 0
