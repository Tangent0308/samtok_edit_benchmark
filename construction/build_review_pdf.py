"""Build an offline bilingual PDF directly from every frozen public case."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True)
    args = parser.parse_args()
    package = args.package
    meta = json.loads((package / "package_metadata.json").read_text())
    cases = sorted(
        (json.loads(p.read_text()) for p in (package / "cases").glob("*.json")),
        key=lambda c: c["index"],
    )
    assert len(cases) == meta["cases"]
    fonts = {n: ImageFont.truetype(str(args.font), n) for n in (25, 27, 29, 42)}
    path = package / "benchmark_all_200_cases.pdf"
    canvas = Canvas(str(path), pagesize=(1200, 900))
    canvas.setTitle(f"SAMTok Benchmark {meta['instruction_version']} — 全部 200 cases")
    canvas.setAuthor("SAMTok Benchmark")

    def wrap(draw, text, xy, width, size=27):
        x, y = xy
        line = ""
        for char in text:
            if draw.textlength(line + char, font=fonts[size]) > width:
                draw.text((x, y), line, font=fonts[size], fill="#243650")
                y += size + 9
                line = ""
            line += char
        draw.text((x, y), line, font=fonts[size], fill="#243650")
        return y + size + 9

    for i, case in enumerate(cases):
        page = Image.new("RGB", (2400, 1800), "#f4f7fb")
        draw = ImageDraw.Draw(page)
        draw.text((45, 24), f"{i + 1:03d} / 200   {case['id']}   ·   {len(case['units'])} 个编辑目标", font=fonts[42], fill="#122743")
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
        for unit in case["public_units"]:
            form = ("ref + " if unit["has_ref"] else "no-ref + ") + unit["locator"]
            draw.rounded_rectangle((45, y, 2355, y + 120), radius=12, fill="white")
            draw.text((65, y + 10), f"{unit['id']}  {unit['operation']}  |  {form}", font=fonts[27], fill="#176d8c")
            end = wrap(draw, unit["instruction"], (575, y + 7), 1750)
            wrap(draw, unit["instruction_zh"], (575, end), 1750, 25)
            y += 128
        draw.text((45, 1745), "add 区域指已有支撑物或空间锚点；区域不是新增物体轮廓。图像已嵌入，支持离线查看和放大。", font=fonts[25], fill="#526580")
        buffer = io.BytesIO()
        page.save(buffer, format="JPEG", quality=91)
        buffer.seek(0)
        canvas.drawImage(ImageReader(buffer), 0, 0, width=1200, height=900)
        canvas.showPage()
        if (i + 1) % 25 == 0:
            print(f"PDF cases: {i + 1}/{len(cases)}", flush=True)
    canvas.save()
    print(path)


if __name__ == "__main__":
    main()
