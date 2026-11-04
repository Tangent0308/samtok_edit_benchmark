#!/usr/bin/env python3
"""Side-by-side comparison sheets (source + every method's restored output) for visual inspection.

Reads only completed generation receipts and the public instruction; images are resized for display only. Writes JPG
pages and one multi-page PDF. No scores are drawn, so the sheets cannot be mistaken for judged results.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont

LABELS = {"sitedit": "SITEdit", "qwen21": "Qwen-Image-2.1", "qwen2511": "Qwen-Image-Edit-2511",
          "replan": "RePlan", "mirage": "MIRAGE", "flux3": "FLUX.3 Klein", "mice": "MICE",
          "flux2_klein9b": "FLUX.2 Klein-9B"}


def font(size, path=None):
    for candidate in [path, "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if candidate and Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def tile(path, width, height):
    canvas = Image.new("RGB", (width, height), (245, 245, 245))
    if path and Path(path).exists():
        with Image.open(path) as image:
            image = image.convert("RGB")
            scale = min(width / image.width, height / image.height)
            image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))),
                                 Image.Resampling.LANCZOS)
            canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
    return canvas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--banner", default="")
    parser.add_argument("--rows-per-page", type=int, default=4)
    parser.add_argument("--tile", type=int, default=300)
    args = parser.parse_args()
    run, output = Path(args.run), Path(args.output)
    plan = json.loads((run / "RUN.json").read_text())
    models = plan["models"]
    cases = args.cases or plan["case_ids"]
    index = {c["case_id"]: c for c in json.loads((Path(plan["bundle"]) / "index.json").read_text())["cases"]}
    output.mkdir(parents=True, exist_ok=True)
    size, header, gap = args.tile, 64, 6
    title_font, text_font, small = font(22), font(17), font(14)
    columns = ["source"] + models
    width = len(columns) * (size + gap) + gap
    pages = []
    for start in range(0, len(cases), args.rows_per_page):
        chunk = cases[start:start + args.rows_per_page]
        height = 50 + 30 + len(chunk) * (size + header + gap) + gap
        page = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(page)
        draw.text((gap, 10), args.banner, fill=(170, 0, 0), font=title_font)
        for j, name in enumerate(columns):
            draw.text((gap + j * (size + gap), 52), LABELS.get(name, name), fill="black", font=text_font)
        y = 80
        for case in chunk:
            public = json.loads(Path(index[case]["public"]).read_text())
            line = f"[{case} | {index[case].get('category', '')}] {public['instruction']}"
            draw.text((gap, y + 4), "\n".join(textwrap.wrap(line, width=int(width / 9.5))[:2]), fill="black",
                      font=small)
            y += header
            page.paste(tile(public["source"]["path"], size, size), (gap, y))
            for j, model in enumerate(models, 1):
                result_path = run / model / "edit" / case / "result.json"
                result = json.loads(result_path.read_text()) if result_path.exists() else {}
                image = result.get("output_image") if result.get("status") == "completed" else None
                page.paste(tile(image, size, size), (gap + j * (size + gap), y))
                if not image:
                    draw.text((gap + j * (size + gap) + 10, y + size // 2), "no output", fill=(170, 0, 0),
                              font=text_font)
            y += size + gap
        path = output / f"page_{start // args.rows_per_page + 1:03d}.jpg"
        page.save(path, quality=88)
        pages.append(page)
    if pages:
        pages[0].save(output / "comparison.pdf", save_all=True, append_images=pages[1:], resolution=100)
    print(json.dumps({"pages": len(pages), "output": str(output)}))


if __name__ == "__main__":
    main()
