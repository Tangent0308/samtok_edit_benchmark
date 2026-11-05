"""Deterministic actual-input/output contact sheets; no generated illustrative substitutes."""

from __future__ import annotations

from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageOps

from samtok_benchmark.io import sha256_file, write_json
from .bundle import annotation_font, load_bundle, requests, smoke_sessions
from .data import read
from .worker import result_path


def preview(output, destination):
    output, destination = Path(output), Path(destination)
    plan = read(output / "RUN.json")
    index = load_bundle(plan["bundle"])
    items = requests(index, plan["session_ids"], plan["scope"] == "smoke")
    selected = smoke_sessions(index)
    items = [i for i in items if i["session_id"] in selected]
    private = {r["case_id"]: r for r in read(Path(plan["bundle"]) / "private/evaluation.json")}
    destination.mkdir(parents=True, exist_ok=True)
    font = annotation_font(18)
    small = annotation_font(14)
    receipts = []
    for item in items:
        columns = []
        if item["mode"] == "independent":
            p = read(item["public"])
            columns.append(("Public source", p["source"]["path"]))
            if p["annotation"]:
                columns.append(("Public mask annotation", p["annotation"]["path"]))
        columns.append(
            ("Official target (scoring only)", private[item["case_id"]]["target"]["path"])
        )
        for model in plan["models"]:
            p = result_path(output, model, "edit", item["key"])
            r = read(p) if p.exists() else {}
            # Recurrent source is method-specific; show it beside each output, never substitute GT.
            if item["mode"] == "iterative":
                public_path = output / "public_recurrent" / model / item["key"] / "public.json"
                public = read(public_path) if public_path.exists() else None
                columns.append((model + " input", public["source"]["path"] if public else None))
            columns.append(
                (model, r.get("output_image") if r.get("status") == "completed" else None)
            )
        width, cell, header, label = 4 * 288, 288, 120, 38
        height = header + ((len(columns) + 3) // 4) * (cell + label)
        sheet = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(sheet)
        draw.text((12, 12), item["key"], font=font, fill="black")
        for n, line in enumerate(textwrap.wrap(item["instruction"], width=120)):
            draw.text((12, 42 + n * 19), line, font=small, fill="black")
        evidence = []
        for n, (title, path) in enumerate(columns):
            x, y = (n % 4) * cell, header + (n // 4) * (cell + label)
            draw.text((x + 4, y + 4), title, font=small, fill="black")
            if path:
                with Image.open(path) as im:
                    view = ImageOps.contain(im.convert("RGB"), (cell - 8, cell - 8))
                sheet.paste(
                    view, (x + (cell - view.width) // 2, y + label + (cell - view.height) // 2)
                )
                evidence.append({"label": title, "path": path, "sha256": sha256_file(path)})
            else:
                draw.text((x + 8, y + 100), "Missing / failed; see receipt", font=small, fill="red")
        path = destination / (item["key"].replace("/", "--") + ".jpg")
        sheet.save(path, quality=90)
        receipts.append(
            {
                "key": item["key"],
                "sheet": str(path),
                "sha256": sha256_file(path),
                "sources": evidence,
            }
        )
    write_json(destination / "PROVENANCE.json", receipts)
    md = [
        "# MagicBrush 输入／输出对比",
        "",
        "固定选择仅依据会话 id 与轮次，不按分数或输出挑选。GT 只用于评分与展示。",
        "",
    ]
    for row in receipts:
        md += [f"## {row['key']}", "", f"![{row['key']}]({Path(row['sheet']).name})", ""]
    (destination / "README.md").write_text("\n".join(md))
    return {"sheets": len(receipts), "index": str(destination / "README.md")}
