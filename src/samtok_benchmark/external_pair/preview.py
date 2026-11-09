"""Complete, metadata-ordered real-image comparisons; no selected-success filtering."""

from concurrent.futures import ThreadPoolExecutor
import html
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont, ImageOps

from samtok_benchmark.external_full.data import read, immutable
from samtok_benchmark.io import sha256_file

DESTINATION = Path("/opt/tiger/tanyue/visualization_tmp/ExternalValidation_20261109")


def font(size):
    for name in (
        "/tmp/NotoSansCJKsc-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def render(selection_path):
    selection = read(selection_path)
    bench = selection["benchmark"]
    index = {r["case_id"]: r for r in read(Path(selection["bundle"]) / "index.json")["cases"]}
    private = {r["case_id"]: r for r in read(Path(selection["bundle"]) / "private/evaluation.json")}
    target = DESTINATION / bench
    (target / "cases").mkdir(parents=True, exist_ok=True)
    root = Path(selection["results_root"]) / "run"

    def case(row):
        cid = row["case_id"]
        item = index[cid]
        annotations = private[cid]
        records = {}
        for model in ("qwen21", "sitedit"):
            p = root / model / "edit" / cid / "result.json"
            records[model] = read(p) if p.exists() else {"status": "not_generated"}
        panels = []
        if item["turn"] == 2:
            for model, title in (
                ("qwen21", "Base input = Base turn-1"),
                ("sitedit", "SITEdit input = SITEdit turn-1"),
            ):
                parent = root / model / "edit" / item["parent_case_id"] / "result.json"
                r = read(parent) if parent.exists() else {}
                panels.append((title, r.get("output_image")))
        else:
            panels.append(("Source (original resolution)", annotations["canonical_source"]["path"]))
            if bench == "interedit":
                public = read(item["public"])
                panels.append(("Public mask (model canvas)", public["mask"]["path"]))
        for model, title in (("qwen21", "Qwen-Image-2.1"), ("sitedit", "SITEdit")):
            r = records[model]
            panels.append(
                (
                    title + ("" if r["status"] == "completed" else ": " + r["status"]),
                    r.get("output_image"),
                )
            )
        panels.append(("Target (scoring only)", annotations["target"]["path"]))
        width, image_height, header, footer = 320, 300, 38, 130
        canvas = Image.new("RGB", (width * len(panels), header + image_height + footer), "white")
        draw = ImageDraw.Draw(canvas)
        evidence = []
        for col, (title, path) in enumerate(panels):
            draw.text((col * width + 8, 9), title, fill="black", font=font(14))
            if path:
                with Image.open(path) as image:
                    thumb = ImageOps.contain(
                        image.convert("RGB"),
                        (width - 10, image_height - 10),
                        Image.Resampling.LANCZOS,
                    )
                    canvas.paste(
                        thumb,
                        (
                            col * width + (width - thumb.width) // 2,
                            header + (image_height - thumb.height) // 2,
                        ),
                    )
                evidence.append({"label": title, "path": path, "sha256": sha256_file(path)})
            else:
                draw.text(
                    (col * width + 10, header + 100),
                    "No generated image",
                    fill="red",
                    font=font(17),
                )
        prompt = item.get("instruction")
        if not prompt and item.get("public"):
            prompt = read(item["public"])["instruction"]
        caption = f"{cid} | {row['task']}" + (f" | turn {row['turn']}" if row.get("turn") else "")
        draw.text((8, header + image_height + 3), caption, fill="black", font=font(15))
        visible = textwrap.wrap(prompt or "", width=max(80, (width * len(panels)) // 10))[:4]
        draw.multiline_text(
            (8, header + image_height + 27),
            "\n".join(visible),
            fill="black",
            font=font(15),
            spacing=3,
        )
        destination = target / "cases" / (cid + ".jpg")
        canvas.save(destination, quality=90)
        return {
            "case_id": cid,
            "task": row["task"],
            "turn": row.get("turn", 0),
            "cluster": row["cluster"],
            "instruction": prompt,
            "preview": str(destination),
            "sha256": sha256_file(destination),
            "panels": evidence,
            "statuses": {m: r["status"] for m, r in records.items()},
        }

    # This is only visualization; four image readers keep NAS I/O bounded.
    with ThreadPoolExecutor(max_workers=4) as pool:
        rendered = list(pool.map(case, selection["rows"]))
    immutable(
        target / "PROVENANCE.json",
        {
            "selection_sha256": sha256_file(selection_path),
            "rule": "all fixed cases in case-id order; no score filter",
            "cases": rendered,
        },
    )
    body = [
        f'<!doctype html><meta charset="utf-8"><title>{bench} paired validation</title>',
        "<style>body{font:16px sans-serif;max-width:1600px;margin:auto;padding:24px}img{width:100%;height:auto}section{margin:32px 0;border-bottom:1px solid #ccc}p{white-space:pre-wrap}</style>",
        f"<h1>{bench}: {len(rendered)} fixed paired cases</h1>",
        "<p>All selected cases, ordered by metadata. Target images are scoring-only references. Turn-2 inputs are each method’s own turn-1 output. Complete prompts are below each figure.</p>",
    ]
    md = [
        f"# {bench}：全部固定样本对照",
        "",
        "按 case id 顺序展示所有样本，不根据结果筛选。Target 仅用于评分；第二轮分别展示两方法各自第一轮输出作为输入。",
        "",
    ]
    for r in rendered:
        relative = "cases/" + Path(r["preview"]).name
        body += [
            f'<section id="{html.escape(r["case_id"])}"><h2>{html.escape(r["case_id"])}</h2><img loading="lazy" src="{relative}"><p>{html.escape(r["instruction"] or "")}</p></section>'
        ]
        md += [
            f"## {r['case_id']}",
            "",
            f"![真实输入输出对照]({relative})",
            "",
            r["instruction"] or "",
            "",
        ]
    (target / "index.html").write_text("\n".join(body))
    (target / "INDEX.md").write_text("\n".join(md))
    print(f"Complete case gallery: {target / 'INDEX.md'}", flush=True)
    return target
