#!/usr/bin/env python3
"""Render paged visual audits of the frozen MIRAGE region selection."""

from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


DEFAULT_ROOT = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/datasets/MIRAGE/benchmark"
)
DEFAULT_SELECTION = Path(__file__).with_name("mirage_selected_regions.jsonl")
COLORS = ((239, 68, 68), (34, 197, 94))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}", size)


def polygon(value: list) -> list[tuple[float, float]]:
    if len(value) == 1 and isinstance(value[0], list):
        value = value[0]
    return [(float(value[index]), float(value[index + 1])) for index in range(0, len(value), 2)]


def render_panel(annotation: dict, selection: dict, root: Path) -> Image.Image:
    panel = Image.new("RGB", (360, 445), "white")
    draw = ImageDraw.Draw(panel)
    draw.text(
        (10, 7),
        f"{selection['candidate_id']}  selected={selection['selected_region_indices']}",
        font=font(17, True),
        fill="#111827",
    )
    with Image.open(root / annotation["image"]) as handle:
        source = handle.convert("RGBA")
    overlay = Image.new("RGBA", source.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for position, source_index in enumerate(selection["selected_region_indices"]):
        points = polygon(annotation["mask"][source_index - 1])
        color = COLORS[position]
        overlay_draw.polygon(points, fill=(*color, 72), outline=(*color, 255), width=7)
        xs, ys = zip(*points)
        x, y = sum(xs) / len(xs), sum(ys) / len(ys)
        overlay_draw.ellipse((x - 28, y - 28, x + 28, y + 28), fill=(*color, 255))
        label = f"R{position + 1}"
        label_font = font(25, True)
        bbox = overlay_draw.textbbox((0, 0), label, font=label_font)
        overlay_draw.text(
            (x - (bbox[2] - bbox[0]) / 2, y - (bbox[3] - bbox[1]) / 2 - 3),
            label,
            font=label_font,
            fill="white",
        )
    visual = Image.alpha_composite(source, overlay).convert("RGB")
    visual.thumbnail((340, 340), Image.Resampling.LANCZOS)
    panel.paste(visual, ((360 - visual.width) // 2, 34))
    y = 380
    for atom in selection["selected_atomic_edits"]:
        text = f"R{atom['region']}: {atom['refer_object']}"
        for line in textwrap.wrap(text, width=44):
            draw.text((10, y), line, font=font(14), fill="#374151")
            y += 17
    return panel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--output", type=Path, default=Path("/tmp/mirage_selection_audit"))
    args = parser.parse_args()
    annotations = read_jsonl(args.benchmark_root / "annotations.jsonl")
    selections = read_jsonl(args.selection)
    args.output.mkdir(parents=True, exist_ok=True)
    for page_index, start in enumerate(range(0, len(selections), 20), 1):
        page = Image.new("RGB", (1820, 1840), "#e5e7eb")
        for offset, selection in enumerate(selections[start : start + 20]):
            case_id = int(selection["source_row"])
            panel = render_panel(annotations[case_id], selection, args.benchmark_root)
            x = 5 + (offset % 5) * 363
            y = 5 + (offset // 5) * 458
            page.paste(panel, (x, y))
        destination = args.output / f"mirage_selection_{start:03d}_{min(start + 19, len(selections) - 1):03d}.jpg"
        page.save(destination, quality=94)
        print(destination)


if __name__ == "__main__":
    main()
