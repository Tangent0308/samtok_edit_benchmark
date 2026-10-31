"""Build an offline bilingual PDF directly from every frozen public case."""

from __future__ import annotations

import argparse
import io
import json
import re
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--preview-dir", type=Path)
    parser.add_argument("--target-details", action="store_true", help="Include enlarged selected-mask crops for visual audit")
    args = parser.parse_args()
    package = args.package
    meta = json.loads((package / "package_metadata.json").read_text())
    cases = sorted(
        (json.loads(p.read_text()) for p in (package / "cases").glob("*.json")),
        key=lambda c: c["index"],
    )
    assert len(cases) == meta["cases"]
    case_count = len(cases)
    fonts = {n: ImageFont.truetype(str(args.font), n) for n in (25, 27, 29, 42)}
    path = package / f"benchmark_all_{case_count}_cases.pdf"
    page_height = 2200 if args.target_details else 1800
    canvas = Canvas(str(path), pagesize=(1200, page_height / 2))
    canvas.setTitle(f"SAMTok Benchmark {meta['instruction_version']} — 全部 {case_count} cases")
    canvas.setAuthor("SAMTok Benchmark")

    def wrap(draw, text, xy, width, size=27):
        x, y = xy
        line = ""
        for char in re.findall(r"[A-Za-z0-9][A-Za-z0-9’'-]*|[^\s]|\s+", text):
            if draw.textlength(line + char, font=fonts[size]) > width:
                draw.text((x, y), line, font=fonts[size], fill="#243650")
                y += size + 9
                line = ""
            line += char
        draw.text((x, y), line, font=fonts[size], fill="#243650")
        return y + size + 9

    for i, case in enumerate(cases):
        page = Image.new("RGB", (2400, page_height), "#f4f7fb")
        draw = ImageDraw.Draw(page)
        draw.text((45, 24), f"{i + 1:03d} / {case_count}   {case['id']}   ·   {len(case['units'])} 个编辑目标", font=fonts[42], fill="#122743")
        draw.text((45, 87), f"Release {meta['instruction_version']}  |  Instruction protocol 1.0  |  源图与任务展示，尚无模型编辑结果", font=fonts[25], fill="#526580")
        for col, (label, relative) in enumerate([
            ("原始源图", case["source"]["image"]),
            ("正式混合输入：每个目标使用各自冻结的交互形式", case["formal_input_image"]),
        ]):
            x = 45 + col * 1180
            draw.text((x, 137), label, font=fonts[29], fill="#243650")
            draw.rounded_rectangle((x, 185, x + 1130, 1025), radius=18, fill="white")
            with Image.open(package / relative) as image:
                image = ImageOps.contain(image.convert("RGB"), (1110, 820), Image.Resampling.LANCZOS)
                page.paste(image, (x + (1130 - image.width) // 2, 195 + (820 - image.height) // 2))
        y = 1044
        if args.target_details:
            draw.text((45, y), "目标局部：全部原始 mask 仅用于审核；模型正式输入仍以上方混合形式为准", font=fonts[25], fill="#526580")
            with Image.open(package / case["source"]["image"]) as original:
                source = original.convert("RGB")
                dimmed = source.point(lambda value: round(value * .5))
                slot = 2310 // len(case["units"])
                for j, unit in enumerate(case["units"]):
                    x = 45 + j * slot
                    draw.text((x + 8, y + 38), f"{unit['id']}  {unit['operation']}", font=fonts[25], fill="#176d8c")
                    with Image.open(package / unit["target"]["mask"]) as binary:
                        mask = binary.convert("L")
                        overlay = Image.composite(source, dimmed, mask)
                        boundary = ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(5)), mask)
                        overlay.paste((255, 45, 100), (0, 0), boundary)
                        x1, y1, x2, y2 = unit["target"]["box"]
                        pad = max(16, int(max(x2 - x1, y2 - y1) * .2))
                        crop = overlay.crop((max(0, x1-pad), max(0, y1-pad), min(source.width, x2+pad), min(source.height, y2+pad)))
                    crop = ImageOps.contain(crop, (slot-16, 275), Image.Resampling.LANCZOS)
                    draw.rounded_rectangle((x, y+76, x+slot-8, y+359), radius=12, fill="white")
                    page.paste(crop, (x+(slot-8-crop.width)//2, y+80+(275-crop.height)//2))
            y += 400
        for unit in case["public_units"]:
            form = ("ref + " if unit["has_ref"] else "no-ref + ") + unit["locator"]
            draw.rounded_rectangle((45, y, 2355, y + 120), radius=12, fill="white")
            draw.text((65, y + 10), f"{unit['id']}  {unit['operation']}  |  {form}", font=fonts[27], fill="#176d8c")
            end = wrap(draw, unit["instruction"], (575, y + 7), 1750)
            wrap(draw, unit["instruction_zh"], (575, end), 1750, 25)
            y += 128
        draw.text((45, page_height - 55), "add 区域优先指直接承载/附着对象；本版全部使用直接锚点。图像已嵌入，支持离线查看和放大。", font=fonts[25], fill="#526580")
        buffer = io.BytesIO()
        page.save(buffer, format="JPEG", quality=91)
        if args.preview_dir:
            args.preview_dir.mkdir(parents=True, exist_ok=True)
            page.save(args.preview_dir / f"{i + 1:04d}.jpg", quality=91)
        buffer.seek(0)
        canvas.drawImage(ImageReader(buffer), 0, 0, width=1200, height=page_height / 2)
        canvas.showPage()
        if (i + 1) % 25 == 0:
            print(f"PDF cases: {i + 1}/{len(cases)}", flush=True)
    canvas.save()
    print(path)


if __name__ == "__main__":
    main()
