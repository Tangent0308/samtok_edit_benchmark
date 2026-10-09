"""Readable source/overlay/context cards for actual visual candidate decisions."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

COLORS = [(235, 45, 65), (20, 135, 235), (240, 170, 0), (155, 65, 225)]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def fit(im, size):
    factor = min(size[0] / im.width, size[1] / im.height)
    pic = im.resize((round(im.width * factor), round(im.height * factor)), Image.Resampling.LANCZOS)
    out = Image.new("RGB", size, "#f2f3f5")
    out.paste(pic, ((size[0] - pic.width) // 2, (size[1] - pic.height) // 2))
    return out


def overlay(im, masks, colors=COLORS):
    arr = np.array(im).copy()
    for m, c in zip(masks, colors):
        arr[m] = (arr[m] * 0.58 + np.array(c) * 0.42).astype("uint8")
        border = m & ~ndi.binary_erosion(m)
        arr[border] = c
    return Image.fromarray(arr)


def render(root, record, index):
    im = Image.open(root / record["source_image"]).convert("RGB")
    masks = [np.array(Image.open(root / u["mask"])) > 0 for u in record["units"]]
    over = overlay(im, masks)
    for i, u in enumerate(record["units"]):
        x, y = u["geometry"]["point"]
        dr = ImageDraw.Draw(over)
        font = ImageFont.truetype(FONT, 18)
        tx = max(0, min(x, im.width - 32))
        ty = max(0, y - 25)
        dr.rectangle((tx, ty, tx + 32, ty + 25), fill="white")
        dr.text((tx + 2, ty), f"U{i + 1}", font=font, fill=COLORS[i])
    pw, ph = 700, 445
    fig = Image.new("RGB", (1400, 800), "white")
    dr = ImageDraw.Draw(fig)
    font = ImageFont.truetype(FONT, 19)
    small = ImageFont.truetype(FONT, 15)
    title = f"{index:04d}  {record['candidate_id']}  |  {im.width}x{im.height}  |  {len(masks)} distinct annotated parents"
    dr.text((12, 8), title, font=font, fill="black")
    fig.paste(fit(im, (pw, ph)), (0, 40))
    fig.paste(fit(over, (pw, ph)), (pw, 40))
    cw = 1400 // len(masks)
    for i, (u, m) in enumerate(zip(record["units"], masks)):
        x = i * cw
        label = f"U{i + 1} {u['category']} / parent {u['parent_instance_id']}"
        dr.text((x + 5, 492), label[:72], font=small, fill=COLORS[i])
        g = u["geometry"]
        b = g["box"]
        pad = max(16, int(max(b[2] - b[0], b[3] - b[1]) * 0.20))
        crop = (
            max(0, b[0] - pad),
            max(0, b[1] - pad),
            min(im.width, b[2] + pad),
            min(im.height, b[3] + pad),
        )
        fig.paste(fit(im.crop(crop), (cw // 2 - 6, 235)), (x + 3, 519))
        fig.paste(
            fit(overlay(im, [m], [COLORS[i]]).crop(crop), (cw // 2 - 6, 235)),
            (x + cw // 2 + 3, 519),
        )
        dr.text(
            (x + 5, 762),
            f"area {g['area_fraction']:.2%}; parts {g['significant_components']}; original ann {u['annotation_id']}",
            font=small,
            fill="#333333",
        )
    dest = root / "review_cards"
    dest.mkdir(exist_ok=True)
    path = dest / f"{index:04d}_{record['candidate_id']}.jpg"
    fig.save(path, quality=94)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    root = args.root
    records = [json.loads(x) for x in (root / "candidate_pool.jsonl").read_text().splitlines()]
    subset = list(enumerate(records))[args.start : args.start + args.count]
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        paths = list(ex.map(lambda pair: render(root, pair[1], pair[0]), subset))
    sheets = root / "review_sheets"
    sheets.mkdir(exist_ok=True)
    for offset in range(0, len(paths), 2):
        ss = Image.new("RGB", (1400, 800 * len(paths[offset : offset + 2])), "white")
        for j, p in enumerate(paths[offset : offset + 2]):
            ss.paste(Image.open(p), (0, 800 * j))
        ss.save(
            sheets
            / f"{args.start + offset:04d}_{args.start + offset + len(paths[offset : offset + 2]) - 1:04d}.jpg",
            quality=95,
        )
    print(
        f"Rendered {len(paths)} individual cards and {(len(paths) + 1) // 2} two-case sheets",
        flush=True,
    )


if __name__ == "__main__":
    main()
