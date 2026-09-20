#!/usr/bin/env python3
"""Render every SAMTok case as input / RePlan+Qwen / RePlan+FLUX.2 panels."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps
from tqdm import tqdm

if __package__:
    from .runner import DATASET_ROOT, MANIFEST, OUTPUT_ROOT, SETTINGS, write_json
else:
    from runner import DATASET_ROOT, MANIFEST, OUTPUT_ROOT, SETTINGS, write_json


MODELS = ("qwen2511", "flux2_klein4b")
MODEL_LABELS = {"qwen2511": "RePlan + Qwen-Image-Edit-2511", "flux2_klein4b": "RePlan + FLUX.2-klein-4B"}
SETTING_LABELS = {"text_only": "Text only", "mask_annotation": "Mask locator", "box_annotation": "Box locator", "point_annotation": "Point locator"}
COLORS = ((235, 50, 45), (45, 180, 70), (45, 105, 230))
TILE = 272
GAP = 12
LABEL = 36
HEADER = 120
ROW_GAP = 32
LEFT = 14
PANEL_WIDTH = LEFT * 2 + 5 * TILE + 4 * GAP
PANEL_HEIGHT = HEADER + 3 * (TILE + LABEL + ROW_GAP) + 8


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = Path("/usr/share/fonts/truetype/dejavu") / name
    return ImageFont.truetype(str(path), size)


def text_fit(draw: ImageDraw.ImageDraw, value: str, face: ImageFont.FreeTypeFont, width: int) -> str:
    if draw.textlength(value, font=face) <= width:
        return value
    while value and draw.textlength(value + "…", font=face) > width:
        value = value[:-1]
    return value.rstrip() + "…"


def load_rgb(path: Path) -> Image.Image:
    with Image.open(path) as original:
        return ImageOps.exif_transpose(original).convert("RGB")


def put_tile(canvas: Image.Image, draw: ImageDraw.ImageDraw, image: Image.Image | None,
             col: int, row: int, caption: str, empty: str = "Unavailable") -> None:
    x = LEFT + col * (TILE + GAP)
    y = HEADER + row * (TILE + LABEL + ROW_GAP)
    draw.rectangle((x, y, x + TILE - 1, y + TILE - 1), fill="#e8ebee", outline="#cbd3da")
    if image is None:
        face = font(17)
        draw.text((x + 16, y + TILE // 2 - 12), text_fit(draw, empty, face, TILE - 32), font=face, fill="#5b6571")
    else:
        contained = ImageOps.contain(image, (TILE - 4, TILE - 4), Image.Resampling.LANCZOS)
        canvas.paste(contained, (x + (TILE - contained.width) // 2, y + (TILE - contained.height) // 2))
    label_face = font(17, bold=True)
    draw.text((x + 4, y + TILE + 5), text_fit(draw, caption, label_face, TILE - 8), font=label_face, fill="#182331")


def plan_overview(source: Image.Image, records: dict[str, dict | None]) -> Image.Image:
    result = Image.new("RGB", (TILE, TILE), "#eff2f5")
    draw = ImageDraw.Draw(result)
    mini = (TILE - 12) // 2
    for index, setting in enumerate(SETTINGS):
        x = (index % 2) * (mini + 4) + 2
        y = (index // 2) * (mini + 4) + 2
        image = ImageOps.fit(source, (mini, mini), Image.Resampling.LANCZOS)
        result.paste(image, (x, y))
        record = records.get(setting)
        if record:
            guidance = record.get("region_guidance") or []
            for region_index, region in enumerate(guidance):
                bbox = region.get("bbox")
                if not isinstance(bbox, list) or len(bbox) != 4:
                    continue
                sx = mini / source.width
                sy = mini / source.height
                color = COLORS[region_index % len(COLORS)]
                draw.rectangle((x + bbox[0] * sx, y + bbox[1] * sy,
                                x + bbox[2] * sx, y + bbox[3] * sy), outline=color, width=3)
        else:
            draw.rectangle((x, y, x + mini, y + mini), fill="#d7dde3")
        draw.rectangle((x + 2, y + 2, x + 25, y + 24), fill="#17212b")
        draw.text((x + 7, y + 3), "TMBP"[index], font=font(15, bold=True), fill="white")
    return result


def panel_path(out_dir: Path, index: int) -> Path:
    return out_dir / "cases" / f"{index:04d}.jpg"


def output_for(root: Path, model: str, setting: str, index: int) -> tuple[Image.Image | None, dict | None]:
    base = root / "inference" / model / setting / f"{index:04d}"
    image_path, json_path = base.with_suffix(".png"), base.with_suffix(".json")
    if not image_path.is_file() or not json_path.is_file():
        return None, None
    return load_rgb(image_path), json.loads(json_path.read_text(encoding="utf-8"))


def render_case(row: dict, output_root: Path, dataset_root: Path, out_dir: Path) -> Path:
    index = row["eval_index"]
    source_path = Path(row["prepared"]["baseline_inputs"]["text_only"]["images"][0])
    source = load_rgb(source_path)
    canvas = Image.new("RGB", (PANEL_WIDTH, PANEL_HEIGHT), "white")
    draw = ImageDraw.Draw(canvas)
    title = f"#{index:04d}  {row['id']}  |  {row['source_dataset']}  |  {row['edit_type']}  |  {len(row['regions'])} region(s)"
    draw.text((LEFT, 9), text_fit(draw, title, font(25, bold=True), PANEL_WIDTH - 2 * LEFT),
              font=font(25, bold=True), fill="#142131")
    instruction = row["instruction"]["with_location_reference"].strip().replace("\n", " ")
    draw.text((LEFT, 47), text_fit(draw, instruction, font(19), PANEL_WIDTH - 2 * LEFT),
              font=font(19), fill="#37475a")
    draw.text((LEFT, 79), "Inputs / reference", font=font(20, bold=True), fill="#526171")

    put_tile(canvas, draw, source, 0, 0, "Clean source")
    for column, setting in enumerate(SETTINGS[1:], start=1):
        locator = Path(row["prepared"]["baseline_inputs"][setting]["images"][1])
        put_tile(canvas, draw, load_rgb(locator), column, 0, SETTING_LABELS[setting])
    target_ref = row["target"]["reference_image"]
    target = load_rgb(dataset_root / target_ref) if target_ref else None
    put_tile(canvas, draw, target, 4, 0, "Target reference" if target_ref else "No target (MIRAGE)",
             empty="No edited target published")

    for model_row, model in enumerate(MODELS, start=1):
        records = {}
        for column, setting in enumerate(SETTINGS):
            output, record = output_for(output_root, model, setting, index)
            records[setting] = record
            count = len(record.get("region_guidance") or []) if record else None
            caption = SETTING_LABELS[setting] + (f"  |  {count} box(es)" if count is not None else "  |  pending")
            put_tile(canvas, draw, output, column, model_row, caption, empty="Pending generation")
        put_tile(canvas, draw, plan_overview(source, records), 4, model_row, "Planner boxes: T / M / B / P")
        row_y = HEADER + model_row * (TILE + LABEL + ROW_GAP) - 27
        draw.text((LEFT, row_y), MODEL_LABELS[model], font=font(20, bold=True),
                  fill="#295c90" if model == "qwen2511" else "#9b5722")

    out_path = panel_path(out_dir, index)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.stem + f".{os.getpid()}.tmp.jpg")
    canvas.save(tmp, quality=86, optimize=True)
    os.replace(tmp, out_path)
    return out_path


def make_contacts(rows: list[dict], out_dir: Path, page_size: int) -> list[dict]:
    pages = []
    contact_dir = out_dir / "pages"
    contact_dir.mkdir(parents=True, exist_ok=True)
    columns = 2
    thumb_width = 760
    thumb_height = round(PANEL_HEIGHT * thumb_width / PANEL_WIDTH)
    pad = 14
    page_rows = math.ceil(page_size / columns)
    for page_index in tqdm(range(math.ceil(len(rows) / page_size)), desc="Contact pages"):
        batch = rows[page_index * page_size:(page_index + 1) * page_size]
        sheet = Image.new("RGB", (columns * thumb_width + (columns + 1) * pad,
                                  page_rows * thumb_height + (page_rows + 1) * pad), "#dde3e8")
        for pos, row in enumerate(batch):
            with Image.open(panel_path(out_dir, row["eval_index"])) as panel:
                thumb = panel.convert("RGB").resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
            x = pad + (pos % columns) * (thumb_width + pad)
            y = pad + (pos // columns) * (thumb_height + pad)
            sheet.paste(thumb, (x, y))
        path = contact_dir / f"page_{page_index + 1:03d}.jpg"
        tmp = path.with_name(path.stem + f".{os.getpid()}.tmp.jpg")
        sheet.save(tmp, quality=84, optimize=True)
        os.replace(tmp, path)
        pages.append({"page": page_index + 1, "file": f"pages/{path.name}",
                      "first_index": batch[0]["eval_index"], "last_index": batch[-1]["eval_index"]})
    return pages


def make_html(rows: list[dict], pages: list[dict], out_dir: Path) -> None:
    page_links = " ".join(
        f'<a href="{html.escape(p["file"])}">{p["first_index"]:04d}–{p["last_index"]:04d}</a>'
        for p in pages
    )
    cards = []
    for row in rows:
        idx = row["eval_index"]
        cards.append(
            f'<article data-dataset="{html.escape(row["source_dataset"])}" '
            f'data-search="{html.escape((row["id"] + " " + row["instruction"]["with_location_reference"]).lower())}">'
            f'<a href="cases/{idx:04d}.jpg" target="_blank"><img loading="lazy" src="cases/{idx:04d}.jpg" alt="Case {idx:04d}"></a>'
            f'<div>#{idx:04d} · {html.escape(row["id"])} · {html.escape(row["source_dataset"])} · {html.escape(row["edit_type"])}</div>'
            f'</article>'
        )
    page = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RePlan × SAMTok 656</title>
<style>body{font-family:system-ui,sans-serif;margin:0;background:#f3f5f7;color:#172230}header{position:sticky;top:0;background:#fff;z-index:2;padding:16px 24px;box-shadow:0 2px 8px #0002}h1{margin:0 0 8px;font-size:24px}p{margin:6px 0}input,select{padding:8px;font-size:16px;margin-right:8px}nav{padding:12px 24px;background:#e7edf3;line-height:2}nav a{display:inline-block;margin-right:10px}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(450px,1fr));gap:18px;padding:24px}article{background:white;padding:10px;border-radius:8px;box-shadow:0 2px 8px #0001}article img{width:100%;height:auto}article div{font-size:14px;overflow-wrap:anywhere}article[hidden]{display:none}</style></head><body>
<header><h1>RePlan × SAMTok Edit Benchmark: 656 cases</h1><p>Each panel: clean source, three locators, target reference; RePlan + Qwen and RePlan + FLUX.2 four-setting outputs; planner boxes. Click any panel for the full image.</p><input id="query" placeholder="Search ID or instruction"><select id="dataset"><option value="">All datasets</option><option value="compbench">CompBench</option><option value="humanedit">HumanEdit</option><option value="mirage">MIRAGE</option></select><span id="count"></span></header>
<nav><strong>Contact pages:</strong> """ + page_links + "</nav><main>" + "\n".join(cards) + """</main><script>const q=document.getElementById('query'),d=document.getElementById('dataset'),cards=[...document.querySelectorAll('article')],count=document.getElementById('count');function apply(){const needle=q.value.trim().toLowerCase(),dataset=d.value;let n=0;for(const card of cards){const visible=(!needle||card.dataset.search.includes(needle))&&(!dataset||card.dataset.dataset===dataset);card.hidden=!visible;if(visible)n++;}count.textContent=n+' cases';}q.addEventListener('input',apply);d.addEventListener('change',apply);apply();</script></body></html>"""
    (out_dir / "index.html").write_text(page, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--indices", type=int, nargs="*")
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--cases-per-page", type=int, default=8)
    args = parser.parse_args()
    out_dir = args.out_dir or args.output_root / "visualizations/replan_comparison"
    rows = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line]
    if args.indices:
        selected = set(args.indices)
        rows = [row for row in rows if row["eval_index"] in selected]
    if not rows:
        raise ValueError("No cases selected")
    missing = []
    for row in rows:
        for model in MODELS:
            for setting in SETTINGS:
                image = args.output_root / "inference" / model / setting / f"{row['eval_index']:04d}.png"
                sidecar = image.with_suffix(".json")
                if not image.is_file() or not sidecar.is_file():
                    missing.append(f"{model}/{setting}/{row['eval_index']:04d}")
    if missing and not args.allow_incomplete:
        raise RuntimeError(f"Missing {len(missing)} outputs; first: {missing[:12]}")
    out_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(render_case, row, args.output_root, args.dataset_root, out_dir): row for row in rows}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Case panels"):
            future.result()
    pages = make_contacts(rows, out_dir, args.cases_per_page)
    make_html(rows, pages, out_dir)
    write_json(out_dir / "gallery_report.json", {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cases": len(rows), "panels": len(rows), "contact_pages": len(pages),
        "missing_model_outputs": len(missing), "first_missing": missing[:20],
        "models": {model: MODEL_LABELS[model] for model in MODELS},
        "case_indices": [row["eval_index"] for row in rows],
    })
    print(f"Gallery: {out_dir / 'index.html'}")


if __name__ == "__main__":
    main()
