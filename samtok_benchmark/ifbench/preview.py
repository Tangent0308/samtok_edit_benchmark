"""Static milestone review with actual full-size inputs and exact prompt text."""

from __future__ import annotations

import html
from pathlib import Path
import shutil

from PIL import Image, ImageDraw, ImageFont

from samtok_benchmark.io import write_json
from . import SETTINGS
from .render import FONT


def make_contact_sheet(items, directory):
    width, row_h = 1600, 500
    sheet = Image.new("RGB", (width, 55 + row_h * len(items)), "#f3f4f6")
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(str(FONT), 20)
    small = ImageFont.truetype(str(FONT), 17)
    d.text(
        (20, 14),
        f"{directory.name} | actual inputs (display thumbnails; originals linked in HTML)",
        font=font,
        fill="black",
    )
    for row, (request, payload, case_dir) in enumerate(items):
        y = 55 + row * row_h
        d.text(
            (20, y + 8),
            f"{request['case_id']} | K={len(request['units'])} | "
            + ", ".join(f"{u['id']}:{u['locator']}" for u in request["units"]),
            font=small,
            fill="black",
        )
        images = [("SOURCE", request["source"]["path"])]
        if payload["annotation"]:
            images.append(("ANNOTATION", payload["annotation"]["path"]))
        for col, (label, path) in enumerate(images):
            image = Image.open(path).convert("RGB")
            image.thumbnail((770, 430))
            x = col * 800 + 15
            d.text((x, y + 35), label, font=small, fill="black")
            sheet.paste(image, (x + (770 - image.width) // 2, y + 63 + (430 - image.height) // 2))
    sheet.save(directory / "overview.jpg", quality=92)


def write_gallery(records, root: Path):
    assets = root / "gallery_sources"
    assets.mkdir(exist_ok=True)
    grouped = {s: [] for s in SETTINGS}
    for request, payload, case_dir in records:
        dest = assets / f"{request['case_id']}.jpg"
        if not dest.exists():
            shutil.copy2(request["source"]["path"], dest)
        grouped[request["setting"]].append((request, payload, case_dir))
    links = []
    for setting, items in grouped.items():
        directory = root / "requests" / setting
        directory.mkdir(parents=True, exist_ok=True)
        cards = []
        for request, payload, case_dir in items:
            esc = html.escape
            cid = request["case_id"]
            local = case_dir.name
            images = f'<figure><figcaption>原图（实际输入）</figcaption><a href="../../gallery_sources/{cid}.jpg"><img src="../../gallery_sources/{cid}.jpg"></a></figure>'
            if payload["annotation"]:
                images += f'<figure><figcaption>标记图（双图候选第2图；单图候选的唯一输入）</figcaption><a href="{local}/annotation.png"><img src="{local}/annotation.png"></a></figure>'
            else:
                images += "<p>本 setting 没有区域输入，因此没有标记图。</p>"
            prompts = []
            for mode, form in payload["forms"].items():
                prompts.append(
                    f'<details {"open" if mode == "dual" else ""}><summary>{esc(mode)}：最终共享候选 prompt；图像数 {len(form["images"])}</summary><pre>{esc(form["prompt"])}</pre><a href="{local}/prompt.{mode}.txt">原文TXT</a></details>'
                )
            native = []
            for u in payload["native"]["units"]:
                if u["mask"]:
                    native.append(
                        f'<figure><figcaption>{u["unit_id"]}：{esc(u["box_conversion"])}<br>白=选中区域</figcaption><a href="{local}/native/{u["unit_id"]}.png"><img src="{local}/native/{u["unit_id"]}.png"></a></figure>'
                    )
                else:
                    native.append(f"<p>{u['unit_id']}：未提供区域；未补定位结果。</p>")
            cards.append(
                f'<article><h2>{esc(cid)} · K={len(request["units"])}</h2><div class="images">{images}</div>'
                + "".join(prompts)
                + '<details><summary>原生区域转换：框和mask（不是模型输出）</summary><div class="masks">'
                + "".join(native)
                + f'</div><a href="{local}/native.json">完整坐标、mask和转换记录</a></details><p><a href="{local}/public.json">公共请求JSON</a> · <a href="{local}/inputs.json">全部输入形式JSON</a></p></article>'
            )
        style = "body{font:16px/1.6 system-ui,sans-serif;max-width:1700px;margin:auto;padding:24px;background:#f8fafc;color:#172033}article{background:white;border:1px solid #cbd5e1;border-radius:10px;padding:20px;margin:24px 0}.images,.masks{display:flex;gap:16px;flex-wrap:wrap}figure{margin:0;flex:1;min-width:250px}img{max-width:100%;max-height:700px;object-fit:contain}.masks figure{max-width:300px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f9;padding:15px}details{margin:14px 0}summary{cursor:pointer;font-weight:600}a{color:#1d4ed8}"
        (directory / "index.html").write_text(
            '<!doctype html><html lang="zh"><meta charset="utf-8"><title>'
            + setting
            + " 输入核对</title><style>"
            + style
            + '</style><body><a href="../../index.html">返回总索引</a><h1>'
            + setting
            + " · 3 个 dev 请求</h1><p>图像可点击查看原尺寸。这里没有模型输出，也没有评分。不同共享形式是候选构造，并非所有模型都使用所有候选；每方法候选总数仍≤4。单区域方法的顺序调用、模型专用token和内部prompt将在模型冒烟节点核对。</p>"
            + "".join(cards)
            + "</body></html>"
        )
        make_contact_sheet(items, directory)
        links.append(
            f'<li><a href="requests/{setting}/index.html">{setting}：3个请求、全尺寸输入、最终共享prompt及区域转换</a> · <a href="requests/{setting}/overview.jpg">总览图</a></li>'
        )
    (root / "index.html").write_text(
        '<!doctype html><html lang="zh"><meta charset="utf-8"><title>IF-Bench 输入核对 · 节点1</title><body style="max-width:1100px;margin:40px auto;font:18px/1.7 system-ui"><h1>IF-Bench：共享输入核对</h1><p>10个settings × 3个dev请求，共30个请求。无test图像、无模型推理、无Judge。</p><p>每页包含原图、标记图、双图/单图/坐标候选的最终共享prompt；S2额外包含丢弃区域候选。原生区域栏展示确定性转换。原图与标记图的缩略图仅用于浏览，实际文件保持源分辨率。</p><ul>'
        + "".join(links)
        + "</ul><p>所有材料为临时审核产物；尚未冻结各模型输入配置。</p></body></html>"
    )
    write_json(
        root / "gallery_index.json",
        {
            s: [
                {"case_id": r["case_id"], "input_digest": r["input_digest"], "directory": str(p)}
                for r, _, p in grouped[s]
            ]
            for s in SETTINGS
        },
    )
