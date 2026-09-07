#!/usr/bin/env python3
"""Render every selected candidate into paginated human-review contact sheets."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
from PIL import Image, ImageDraw, ImageFilter, ImageFont


BASE = Path("/opt/tiger/tanyue/finegrained_edit_benchmark_selection")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=BASE / "output" / "selected_500.jsonl")
    parser.add_argument("--output", type=Path, default=BASE / "output" / "review_sheets")
    parser.add_argument("--per-page", type=int, default=25)
    return parser.parse_args()


def decode(cell: dict[str, Any], mode: str) -> Image.Image:
    with Image.open(io.BytesIO(cell["bytes"])) as image:
        return image.convert(mode).copy()


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def human_source(source: Image.Image, size: tuple[int, int], transform: str) -> Image.Image:
    sys.path.insert(0, "/opt/tiger/tanyue/HumanEdit")
    from humanedit_converter.images import center_cover, contain_pad, direct_resize
    if transform == "cover":
        return center_cover(source.convert("RGB"), size)
    if transform == "contain":
        return contain_pad(source.convert("RGB"), size)[0]
    return direct_resize(source.convert("RGB"), size)


def overlay(source: Image.Image, mask: Image.Image) -> Image.Image:
    source = source.convert("RGB").resize(mask.size, Image.Resampling.LANCZOS)
    alpha = mask.convert("L").point(lambda x: 105 if x >= 128 else 0)
    result = Image.composite(Image.new("RGB", source.size, (255, 35, 35)), source, alpha)
    dilated = mask.filter(ImageFilter.MaxFilter(7))
    eroded = mask.filter(ImageFilter.MinFilter(7))
    edge = Image.fromarray(((np.asarray(dilated) > np.asarray(eroded)) * 255).astype(np.uint8), "L")
    return Image.composite(Image.new("RGB", source.size, (255, 0, 0)), result, edge)


def fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    canvas = Image.new("RGB", size, (242, 243, 245))
    image = image.convert("RGB")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    canvas.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return canvas


def wrap(draw: ImageDraw.ImageDraw, text: str, text_font: ImageFont.FreeTypeFont, width: int, lines: int) -> list[str]:
    output: list[str] = []
    current = ""
    for word in text.split():
        candidate = (current + " " + word).strip()
        if draw.textbbox((0, 0), candidate, font=text_font)[2] <= width:
            current = candidate
        else:
            if current:
                output.append(current)
            current = word
    if current:
        output.append(current)
    if len(output) > lines:
        output = output[:lines]
        while output[-1] and draw.textbbox((0, 0), output[-1] + "...", font=text_font)[2] > width:
            output[-1] = output[-1][:-1]
        output[-1] += "..."
    return output


def load_visuals(records: list[dict[str, Any]]) -> dict[str, tuple[Image.Image, Image.Image, Image.Image | None]]:
    visuals: dict[str, tuple[Image.Image, Image.Image, Image.Image | None]] = {}
    parquet_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record["source_dataset"] != "ReShapeBench":
            parquet_groups[(record["source_dataset"], record["source_shard"])].append(record)

    for (dataset, shard_name), group in sorted(parquet_groups.items()):
        shard = Path(shard_name)
        if dataset == "CompBench":
            table = pq.read_table(shard, columns=["input_image", "edited_image", "mask"])
            for record in group:
                index = int(record["source_row"])
                row = {name: table[name][index].as_py() for name in table.column_names}
                source = decode(row["input_image"], "RGB")
                target = decode(row["edited_image"], "RGB")
                mask = decode(row["mask"], "L").point(lambda x: 255 if x >= 128 else 0)
                visuals[record["candidate_id"]] = source, mask, target
        else:
            table = pq.read_table(shard, columns=["INPUT_IMG", "MASK_IMG", "OUTPUT_IMG"])
            for record in group:
                index = int(record["source_row"])
                row = {name: table[name][index].as_py() for name in table.column_names}
                canvas = decode(row["MASK_IMG"], "RGBA")
                alpha = np.asarray(canvas.getchannel("A"))
                mask = Image.fromarray(np.where(alpha < 128, 255, 0).astype(np.uint8), "L")
                source = human_source(decode(row["INPUT_IMG"], "RGB"), canvas.size, record["alignment_transform"])
                target = decode(row["OUTPUT_IMG"], "RGB").resize(canvas.size, Image.Resampling.BICUBIC)
                visuals[record["candidate_id"]] = source, mask, target
        print(f"loaded visuals: {dataset} {shard.name} ({len(group)})", flush=True)

    for record in records:
        if record["source_dataset"] != "ReShapeBench":
            continue
        source = Image.open(record["source_image_path"]).convert("RGB")
        mask = Image.open(record["source_mask_path"]).convert("L").point(lambda x: 255 if x >= 128 else 0)
        visuals[record["candidate_id"]] = source, mask, None
    return visuals


def render_card(record: dict[str, Any], visual: tuple[Image.Image, Image.Image, Image.Image | None]) -> Image.Image:
    width, height = 390, 292
    card = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(card)
    strict = bool(record["strict_eligible"])
    color = (34, 139, 94) if strict else (220, 125, 28)
    draw.rounded_rectangle((1, 1, width - 2, height - 2), 10, fill="white", outline=color, width=3)
    title = f"{record['candidate_id']} | {record['edit_type']}"
    draw.text((10, 8), title, font=font(14, True), fill=(25, 31, 42))
    for i, line in enumerate(wrap(draw, record["instruction_original"], font(12), width - 20, 2)):
        draw.text((10, 30 + i * 16), line, font=font(12), fill=(50, 57, 68))
    source, mask, target = visual
    third = target if target is not None else mask
    labels = ("SRC", "REGION", "GT" if target is not None else "BOX")
    for i, (label, image) in enumerate(zip(labels, (source, overlay(source, mask), third))):
        x = 10 + i * 126
        draw.text((x, 67), label, font=font(11, True), fill=(72, 79, 89))
        card.paste(fit(image, (116, 176)), (x, 84))
    status = "STRICT" if strict else "REVIEW"
    draw.text(
        (10, 267),
        f"{status} | area={100 * record['mask_area_ratio']:.2f}% | cc={record['mask_components']}",
        font=font(11, True),
        fill=color,
    )
    return card


def render_pages(
    records: list[dict[str, Any]],
    visuals: dict[str, tuple[Image.Image, Image.Image, Image.Image | None]],
    output: Path,
    per_page: int,
) -> list[dict[str, Any]]:
    output.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, Any]] = []
    columns = 5
    rows = math.ceil(per_page / columns)
    card_w, card_h, gap, margin, header = 390, 292, 12, 18, 58
    datasets = ("CompBench", "HumanEdit", "ReShapeBench")
    for dataset in datasets:
        subset = [x for x in records if x["source_dataset"] == dataset]
        for page_number, start in enumerate(range(0, len(subset), per_page), start=1):
            chunk = subset[start : start + per_page]
            width = 2 * margin + columns * card_w + (columns - 1) * gap
            height = header + 2 * margin + rows * card_h + (rows - 1) * gap
            sheet = Image.new("RGB", (width, height), (230, 233, 238))
            draw = ImageDraw.Draw(sheet)
            draw.text(
                (margin, 12),
                f"{dataset} review sheet {page_number} | cases {start + 1}-{start + len(chunk)} / {len(subset)}",
                font=font(26, True),
                fill=(20, 25, 34),
            )
            filename = f"{dataset.lower()}_{page_number:02d}.jpg"
            for position, record in enumerate(chunk):
                col, row = position % columns, position // columns
                x = margin + col * (card_w + gap)
                y = header + margin + row * (card_h + gap)
                sheet.paste(render_card(record, visuals[record["candidate_id"]]), (x, y))
                index.append({
                    "candidate_id": record["candidate_id"], "source_dataset": dataset,
                    "sheet": filename, "position": position, "row": row, "column": col,
                })
            sheet.save(output / filename, quality=91, optimize=True)
            print(f"wrote {filename}: {len(chunk)} cards", flush=True)
    return index


def write_index(output: Path, index: list[dict[str, Any]]) -> None:
    with (output / "review_sheet_index.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(index[0]))
        writer.writeheader()
        writer.writerows(index)
    lines = ["# Review sheets", "", "Green border = strict automatic QC; orange border = manual/SAM2 review.", ""]
    for filename in sorted({x["sheet"] for x in index}):
        lines.extend([f"## {filename}", "", f"![{filename}]({filename})", ""])
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    records = [json.loads(line) for line in args.manifest.read_text().splitlines() if line.strip()]
    visuals = load_visuals(records)
    if len(visuals) != len(records):
        raise ValueError(f"loaded {len(visuals)} visuals for {len(records)} records")
    index = render_pages(records, visuals, args.output, args.per_page)
    write_index(args.output, index)
    print(f"rendered cards={len(index)} sheets={len(set(x['sheet'] for x in index))}", flush=True)


if __name__ == "__main__":
    main()
