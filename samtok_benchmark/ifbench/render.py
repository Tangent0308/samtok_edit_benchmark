"""Deterministic annotations from a validated public request (no manifest access)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from samtok_benchmark.io import sha256_file
from .public import verify

PALETTE = ((255, 0, 0), (0, 80, 255), (0, 170, 0), (255, 210, 0), (230, 0, 230))
COLOR_NAMES = ("red", "blue", "green", "yellow", "magenta")
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
RENDER_VERSION = "ifbench-outline-v1"


def specification():
    import PIL

    return {
        "version": RENDER_VERSION,
        "colors_rgb": [list(c) for c in PALETTE],
        "color_names": list(COLOR_NAMES),
        "font_path": str(FONT),
        "font_sha256": sha256_file(FONT),
        "font_size": "max(12, round(min(W,H)*0.02))",
        "rounding": "Python round: ties to even",
        "point_radius": "max(1,round(min(W,H)*0.01))",
        "white_ring": "max(1,round(min(W,H)*0.002))",
        "line_width": "max(1,round(min(W,H)*0.004))",
        "mask_contour": "all inside boundaries, including holes/components/borders; mask minus square erosion, zero padding",
        "labels": "U1..UK; white fill/color border/text; ordered greedy public-geometry-only placement; leader line",
        "label_priority": "avoid previous labels, minimize public-region overlap, minimize distance, candidate index",
        "image_geometry": "identity; no pad/crop/resize before model adapter",
        "Pillow": PIL.__version__,
        "numpy": np.__version__,
    }


def public_shape(unit, size, radius):
    """Only public geometry is used even for label placement."""
    w, h = size
    result = Image.new("L", (w, h), 0)
    if unit["locator"] == "mask":
        with Image.open(unit["region"]["path"]) as m:
            return m.convert("L").copy()
    d = ImageDraw.Draw(result)
    if unit["locator"] == "point":
        x, y = unit["region"]["coordinates"]
        d.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
    elif unit["locator"] == "box":
        x1, y1, x2, y2 = unit["region"]["coordinates"]
        d.rectangle((x1, y1, x2 - 1, y2 - 1), fill=255)
    return result


def anchor(unit):
    if unit["locator"] in {"point", "box"}:
        return tuple(unit["region"]["coordinates"][:2])
    with Image.open(unit["region"]["path"]) as im:
        y, x = np.nonzero(np.array(im.convert("L")) > 0)
    if not len(x):
        raise ValueError("Empty public mask")
    return int(x[0]), int(y[0])


def place_label(anchor_xy, label_size, size, margin, occupied, selected):
    x, y = anchor_xy
    tw, th = label_size
    w, h = size
    if tw > w or th > h:
        raise ValueError("Source too small for fixed label style")
    candidates = [
        (x + margin, y - th - margin),
        (x - tw - margin, y - th - margin),
        (x + margin, y + margin),
        (x - tw - margin, y + margin),
        (x - tw // 2, y - th - margin),
        (x - tw // 2, y + margin),
        (x + margin, y - th // 2),
        (x - tw - margin, y - th // 2),
    ]
    candidates += [
        (xx, yy) for yy in (0, (h - th) // 2, h - th) for xx in (0, (w - tw) // 2, w - tw)
    ]
    ranked = []
    for i, (xx, yy) in enumerate(candidates):
        xx, yy = max(0, min(xx, w - tw)), max(0, min(yy, h - th))
        overlap = int(occupied[yy : yy + th, xx : xx + tw].sum())
        region_overlap = int(selected[yy : yy + th, xx : xx + tw].sum())
        distance = abs(xx + tw / 2 - x) + abs(yy + th / 2 - y)
        ranked.append(((overlap, region_overlap, distance, i), (xx, yy, xx + tw, yy + th)))
    return min(ranked)[1]


def render(request, destination: Path):
    verify(request)
    image = Image.open(request["source"]["path"]).convert("RGB")
    w, h = image.size
    short = min(w, h)
    radius, ring, line = (
        max(1, round(short * 0.01)),
        max(1, round(short * 0.002)),
        max(1, round(short * 0.004)),
    )
    font = ImageFont.truetype(str(FONT), max(12, round(short * 0.02)))
    marked = [u for u in request["units"] if u["locator"] != "none"]
    if not marked:
        return None
    selected = np.zeros((h, w), dtype=bool)
    for u in marked:
        selected |= np.array(public_shape(u, (w, h), radius)) > 0
    # Draw all region marks before labels; later masks cannot erase earlier labels.
    for u in marked:
        color = PALETTE[int(u["id"][1:]) - 1]
        d = ImageDraw.Draw(image)
        if u["locator"] == "point":
            x, y = u["region"]["coordinates"]
            d.ellipse(
                (x - radius - ring, y - radius - ring, x + radius + ring, y + radius + ring),
                fill="white",
            )
            d.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
        elif u["locator"] == "box":
            x1, y1, x2, y2 = u["region"]["coordinates"]
            d.rectangle((x1, y1, x2 - 1, y2 - 1), outline=color, width=line)
        else:
            mask = public_shape(u, (w, h), radius)
            eroded = ImageOps.expand(mask, border=line, fill=0).filter(
                ImageFilter.MinFilter(2 * line + 1)
            )
            eroded = eroded.crop((line, line, w + line, h + line))
            edge = ImageChops.subtract(mask, eroded)
            image.paste(color, mask=edge)
    occupied = np.zeros((h, w), dtype=bool)
    labels = []
    for u in marked:
        color = PALETTE[int(u["id"][1:]) - 1]
        xy = anchor(u)
        d = ImageDraw.Draw(image)
        tb = d.textbbox((0, 0), u["id"], font=font)
        padding = max(2, line)
        tw, th = tb[2] - tb[0] + 2 * padding, tb[3] - tb[1] + 2 * padding
        box = place_label(xy, (tw, th), (w, h), radius + 2 * line, occupied, selected)
        x1, y1, x2, y2 = box
        end = (min(max(xy[0], x1), x2 - 1), min(max(xy[1], y1), y2 - 1))
        # A leader is a deterministic derivative of the same public geometry.
        d.line((xy, end), fill=color, width=max(1, line // 2))
        d.rectangle((x1, y1, x2 - 1, y2 - 1), fill="white", outline=color, width=max(1, line // 2))
        d.text((x1 + padding - tb[0], y1 + padding - tb[1]), u["id"], font=font, fill=color)
        occupied[y1:y2, x1:x2] = True
        labels.append(
            {
                "unit_id": u["id"],
                "anchor_xy": list(xy),
                "label_box_xyxy": list(box),
                "label_overlap_pixels": sum(
                    max(0, min(x2, b["label_box_xyxy"][2]) - max(x1, b["label_box_xyxy"][0]))
                    * max(0, min(y2, b["label_box_xyxy"][3]) - max(y1, b["label_box_xyxy"][1]))
                    for b in labels
                ),
            }
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)
    return {
        "path": str(destination.resolve()),
        "sha256": sha256_file(destination),
        "size": [w, h],
        "labels": labels,
        "renderer": RENDER_VERSION,
        "transform": {"scale_xy": [1, 1], "offset_xy": [0, 0]},
    }
