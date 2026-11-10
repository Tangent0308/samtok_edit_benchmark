"""Fixed-case visual evidence, with no score-driven example selection."""

import json
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont

from samtok_benchmark.external_refedit.data import read
from samtok_benchmark.io import sha256_file


def render(plan, results, output):
    results, output = Path(results), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    original_root = Path(plan["original_report"]).parents[2]
    cases = {r["case_id"]: r for r in plan["cases"]}
    ids = sorted(set(plan["case_ids"][::24]) | set(plan["native_enumeration_case_ids"]))
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    records, lines = (
        [],
        ["# 固定案例输入/输出对照", "", "案例在推理前按 ID 间隔和枚举分支确定，不按评分筛选。", ""],
    )
    for cid in ids:
        row = cases[cid]
        public = read(row["public"])
        result_path = results / "run/sitedit/edit" / cid / "result.json"
        edited = read(result_path)
        tokens = read(results / "run/sitedit/tokens" / cid / "result.json")
        previous = read(original_root / "run/sitedit/edit" / cid / "result.json")
        base = read(original_root / "run/qwen21/edit" / cid / "result.json")
        entries = [
            ("Source", public["source"]["path"]),
            ("Qwen-Image-2.1", base.get("output_image")),
            ("SITEdit: old composite U1", previous.get("output_image")),
            ("SITEdit: per-target", edited.get("output_image")),
        ]
        width, height, tile = 1280, 430, 320
        canvas = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(canvas)
        for i, (label, path) in enumerate(entries):
            draw.text((i * tile + 8, 8), label, fill="black", font=font)
            if path:
                with Image.open(path) as im:
                    im = im.convert("RGB")
                    im.thumbnail((tile, tile))
                    canvas.paste(im, (i * tile + (tile - im.width) // 2, 36))
            else:
                draw.text((i * tile + 8, 100), "No generated output", fill="red", font=font)
        draw.text(
            (8, 365),
            "\n".join(textwrap.wrap(row["instruction"], width=115)),
            fill="black",
            font=font,
        )
        target = output / (cid + ".jpg")
        canvas.save(target, quality=93)
        units = tokens.get("native", {}).get("units", [])
        lines += [f"## {cid}", "", row["instruction"], "", f"![输入和输出]({target.name})", ""]
        lines += [f"- {u['id']}: {u['instruction']}；区域码：`{u['token']}`" for u in units]
        lines.append("")
        records.append(
            {
                "case_id": cid,
                "preview": str(target),
                "sha256": sha256_file(target),
                "new_result": str(result_path),
                "new_result_sha256": sha256_file(result_path),
            }
        )
    (output / "PREVIEWS.md").write_text("\n".join(lines))
    (output / "PROVENANCE.json").write_text(json.dumps(records, indent=2))
    return str(output / "PREVIEWS.md")
