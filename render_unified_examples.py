#!/usr/bin/env python3
"""Render representative cards from the unified benchmark manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


DEFAULT_BENCHMARK_ROOT = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark"
)
DEFAULT_OUTPUT = DEFAULT_BENCHMARK_ROOT / "visual_examples"
EXAMPLES = {
    "compbench": [
        "cb_train-00000-of-00007_0356",
        "cb_train-00005-of-00007_0284",
        "cb_train-00006-of-00007_0351",
        "cb_train-00006-of-00007_0401",
    ],
    "humanedit": [
        "he_8VPSh4Wj61Q",
        "he_3NQAnprYLaY",
        "he_AXQQ0Kq69es",
        "he__ropNcPmpW8",
    ],
}

REGION_COLORS = [
    (239, 68, 68),
    (34, 197, 94),
    (249, 115, 22),
]
EVALUATION_COLOR = (59, 130, 246)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-root", type=Path, default=DEFAULT_BENCHMARK_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = Path("/usr/share/fonts/truetype/dejavu") / name
    if path.is_file():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def fit_image(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    canvas = Image.new("RGB", size, "#eef1f5")
    copy = image.convert("RGB")
    copy.thumbnail(size, Image.Resampling.LANCZOS)
    x = (size[0] - copy.width) // 2
    y = (size[1] - copy.height) // 2
    canvas.paste(copy, (x, y))
    return canvas


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    prefix: str,
    value: str | None,
    font: ImageFont.ImageFont,
    bold_font: ImageFont.ImageFont,
    width: int,
    fill: str = "#273142",
) -> int:
    x, y = xy
    draw.text((x, y), prefix, font=bold_font, fill="#111827")
    prefix_width = int(draw.textlength(prefix, font=bold_font))
    value_text = value if value is not None else "null"
    first_width = max(80, width - prefix_width)
    lines = wrap_text(draw, value_text, font, first_width)
    draw.text((x + prefix_width, y), lines[0], font=font, fill=fill)
    line_height = font.size + 5 if hasattr(font, "size") else 21
    for line in lines[1:]:
        y += line_height
        draw.text((x, y), line, font=font, fill=fill)
    return y + line_height


def annotated_source(record: dict, root: Path) -> Image.Image:
    source = Image.open(root / record["source_image"]).convert("RGB")
    source_array = np.asarray(source).astype(np.float32)

    evaluation = np.asarray(Image.open(root / record["evaluation_mask"]).convert("L")) > 0
    source_array[evaluation] = (
        source_array[evaluation] * 0.82 + np.asarray(EVALUATION_COLOR, dtype=np.float32) * 0.18
    )

    masks: list[np.ndarray] = []
    for index, region in enumerate(record["regions"]):
        mask = np.asarray(Image.open(root / region["mask"]).convert("L")) > 0
        masks.append(mask)
        color = np.asarray(REGION_COLORS[index], dtype=np.float32)
        source_array[mask] = source_array[mask] * 0.48 + color * 0.52

    annotated = Image.fromarray(np.clip(source_array, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(annotated)
    scale = max(2, round(min(source.size) / 160))
    label_font = load_font(max(15, round(min(source.size) / 30)), bold=True)
    for index, (region, mask) in enumerate(zip(record["regions"], masks), start=1):
        color = REGION_COLORS[index - 1]
        x1, y1, x2, y2 = region["box"]
        draw.rectangle((x1, y1, x2 - 1, y2 - 1), outline=color, width=scale)
        px, py = region["point"]
        radius = max(10, round(min(source.size) * 0.018))
        outline_width = max(3, round(min(source.size) * 0.005))
        draw.ellipse(
            (px - radius, py - radius, px + radius, py + radius),
            fill=color,
            outline="white",
            width=outline_width,
        )
        label = f"R{index}"
        label_box = draw.textbbox((x1, max(0, y1 - label_font.size - 7)), label, font=label_font)
        draw.rectangle(label_box, fill=color)
        draw.text((label_box[0], label_box[1]), label, font=label_font, fill="white")
    return annotated


def no_reference_panel(record: dict, size: tuple[int, int]) -> Image.Image:
    panel = Image.new("RGB", size, "#f3f4f6")
    draw = ImageDraw.Draw(panel)
    title_font = load_font(21, bold=True)
    text_font = load_font(17)
    draw.text((18, 24), "No target reference", font=title_font, fill="#374151")
    draw.text((18, 57), "Reference-free evaluation", font=text_font, fill="#6b7280")
    y = 100
    for line in wrap_text(draw, record["target"]["expected_local_content"], text_font, size[0] - 36):
        draw.text((18, y), line, font=text_font, fill="#111827")
        y += 24
    return panel


def render_card(record: dict, root: Path) -> Image.Image:
    width, height = 860, 650
    panel_size = (252, 252)
    card = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((1, 1, width - 2, height - 2), radius=18, outline="#d1d5db", width=2)

    title_font = load_font(23, bold=True)
    label_font = load_font(16, bold=True)
    body_font = load_font(16)
    body_bold = load_font(16, bold=True)
    meta_font = load_font(15)

    draw.text((22, 17), record["id"], font=title_font, fill="#111827")
    meta = f"{record['edit_type']}  |  {len(record['regions'])} region(s)"
    meta_width = draw.textlength(meta, font=meta_font)
    draw.text((width - 22 - meta_width, 23), meta, font=meta_font, fill="#4b5563")

    panel_x = [22, 304, 586]
    panel_y = 79
    labels = ["SOURCE", "REGION INPUT", "TARGET REFERENCE"]
    for x, label in zip(panel_x, labels):
        draw.text((x, 55), label, font=label_font, fill="#4b5563")

    source = Image.open(root / record["source_image"]).convert("RGB")
    card.paste(fit_image(source, panel_size), (panel_x[0], panel_y))
    source.close()
    card.paste(fit_image(annotated_source(record, root), panel_size), (panel_x[1], panel_y))
    reference = record["target"]["reference_image"]
    if reference is None:
        target_panel = no_reference_panel(record, panel_size)
    else:
        target_image = Image.open(root / reference).convert("RGB")
        target_panel = fit_image(target_image, panel_size)
        target_image.close()
    card.paste(target_panel, (panel_x[2], panel_y))

    y = 354
    content_width = width - 44
    y = draw_wrapped(
        draw,
        (22, y),
        "Instruction: ",
        record["instruction"]["with_location_reference"],
        body_font,
        body_bold,
        content_width,
    )
    y += 4
    y = draw_wrapped(
        draw,
        (22, y),
        "Region-only: ",
        record["instruction"]["region_only"],
        body_font,
        body_bold,
        content_width,
    )
    y += 4
    draw_wrapped(
        draw,
        (22, y),
        "Expected local content: ",
        record["target"]["expected_local_content"],
        body_font,
        body_bold,
        content_width,
    )
    return card


def render_sheet(dataset: str, records: list[dict], root: Path, output: Path) -> None:
    width, height = 1770, 1400
    sheet = Image.new("RGB", (width, height), "#e9edf3")
    draw = ImageDraw.Draw(sheet)
    heading_font = load_font(34, bold=True)
    legend_font = load_font(16)
    title = dataset.replace("_", " ").title() + " — unified benchmark examples"
    draw.text((24, 18), title, font=heading_font, fill="#111827")
    draw.text(
        (1040, 31),
        "Blue: evaluation region   Red/green: input regions   Dot center: exact point",
        font=legend_font,
        fill="#374151",
    )
    positions = [(20, 82), (890, 82), (20, 744), (890, 744)]
    for record, position in zip(records, positions):
        sheet.paste(render_card(record, root), position)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, optimize=True)


def main() -> None:
    args = parse_args()
    manifest = args.benchmark_root / "benchmark.jsonl"
    records = {
        record["id"]: record
        for record in (json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines())
    }
    for dataset, case_ids in EXAMPLES.items():
        missing = [case_id for case_id in case_ids if case_id not in records]
        if missing:
            raise KeyError(f"missing example IDs: {missing}")
        destination = args.output / f"{dataset}_examples.png"
        render_sheet(dataset, [records[case_id] for case_id in case_ids], args.benchmark_root, destination)
        print(destination)


if __name__ == "__main__":
    main()
