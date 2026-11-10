"""Actual image comparisons for all nine requests, without selecting by score."""

from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont, ImageOps

from samtok_benchmark.external_refedit.data import immutable, read
from samtok_benchmark.io import sha256_file
from .plan import load


def render(control, parent_report, merged_report, output):
    plan, _ = load(control)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    parent, merged = read(parent_report), read(merged_report)
    old = {(r["model"], r["case_id"]): r for r in parent["per_case"]}
    new = {(r["model"], r["case_id"]): r for r in merged["per_case"]}
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    evidence = []
    lines = [
        "# CompBench 九条授权修复：输入与输出",
        "",
        "六条恢复模型已经输出的区域码，三条使用原 Pass1 的调试后枚举及逐目标定位。",
        "原记录全部保留。本页包含全部九条，不按得分挑图。",
        "",
    ]
    for row in plan["cases"]:
        cid = row["case_id"]
        public = read(row["public"])
        token = read(row["recovered_tokens"])
        canvas = Image.new("RGB", (1536, 500), "white")
        draw = ImageDraw.Draw(canvas)
        labels = ["Source", "Qwen-Image-2.1", "SITEdit before repair", "SITEdit after repair"]
        paths = [public["source"]["path"]]
        for record in (old["qwen21", cid], old["sitedit", cid], new["sitedit", cid]):
            generation = read(record["generation_record"])
            paths.append(generation.get("output_image"))
        bindings = []
        for col, (label, path) in enumerate(zip(labels, paths)):
            draw.text((col * 384 + 10, 10), label, font=font, fill="black")
            if path:
                image = ImageOps.contain(Image.open(path).convert("RGB"), (376, 376))
                canvas.paste(
                    image, (col * 384 + (384 - image.width) // 2, 36 + (376 - image.height) // 2)
                )
                bindings.append({"label": label, "path": path, "sha256": sha256_file(path)})
            else:
                draw.rectangle((col * 384 + 4, 36, (col + 1) * 384 - 4, 412), fill="#eeeeee")
                draw.text(
                    (col * 384 + 24, 200), "No output: native failure", font=small, fill="black"
                )
                bindings.append({"label": label, "path": None})
        for i, line in enumerate(textwrap.wrap(cid + " | " + row["instruction"], 165)):
            draw.text((8, 422 + 19 * i), line, font=small, fill="black")
        target = output / f"{cid}.jpg"
        canvas.save(target, quality=92)
        evidence.append(
            {
                "case_id": cid,
                "image": str(target),
                "sha256": sha256_file(target),
                "inputs": bindings,
            }
        )
        lines += [
            f"## {cid}",
            "",
            row["instruction"],
            "",
            f"![输入及方法输出对照]({target.name})",
            "",
        ]
        lines += [f"- {u['id']}: {u['instruction']}" for u in token["units"]]
        review = token["recovery_provenance"].get("selection", {})
        if review.get("warning"):
            lines += ["", "源图核验说明：" + review["warning"]]
        lines.append("")
    immutable(output / "PROVENANCE.json", {"plan_digest": plan["digest"], "cases": evidence})
    (output / "PREVIEWS.md").write_text("\n".join(lines))
    return str(output / "PREVIEWS.md")
