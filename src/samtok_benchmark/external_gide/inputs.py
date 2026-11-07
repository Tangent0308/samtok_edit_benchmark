"""Deterministic public coordinates and explicit two-instruction syntax only."""

import json
import re

POLYGON = re.compile(r"four-point region defined by the coordinates (\[\[.*?\]\])")
BOX = re.compile(r"bounding box (\[[^\]]+\])")
SPLIT = re.compile(r",\s+and\s+(?=(?:add|replace|remove)\b)", re.IGNORECASE)
PREFIX = "Coordinate frame: "


def kind(text):
    return "polygon" if POLYGON.search(text) else "box" if BOX.search(text) else "text"


def project(text, geometry):
    sx, sy = geometry["scale_xy"]
    ox, oy = geometry["offset_xy"]
    w, h = geometry["source_size"]
    if match := POLYGON.search(text):
        points = json.loads(match[1])
        if len(points) != 4 or any(len(p) != 2 or not (0 <= p[0] <= w and 0 <= p[1] <= h) for p in points):
            raise ValueError("Invalid published polygon coordinates")
        value = [[x*sx+ox, y*sy+oy] for x, y in points]
    elif match := BOX.search(text):
        x, y, width, height = json.loads(match[1])
        if not (0 <= x < x+width <= w and 0 <= y < y+height <= h):
            raise ValueError("Invalid published xywh box")
        value = [x*sx+ox, y*sy+oy, width*sx, height*sy]
    else:
        return text
    mapped = text[:match.start(1)] + json.dumps(value) + text[match.end(1):]
    cw, ch = geometry["canvas_size"]
    return f"{PREFIX}all coordinates below are pixel coordinates on this {cw} by {ch} image.\n" + mapped


def instructions(text):
    if text.startswith(PREFIX):
        text = text.split("\n", 1)[1]
    units = SPLIT.split(text, maxsplit=1)
    if len(units) != 2 or any(not x.strip() for x in units):
        raise ValueError("Public text lacks the benchmark's explicit two-instruction separator")
    return [x.strip() for x in units]
