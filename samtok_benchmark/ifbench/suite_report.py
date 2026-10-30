"""Self-contained galleries for smoke requests, with explicit failures and N/A."""

import argparse
import base64
from collections import Counter
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from samtok_benchmark.io import sha256_file, write_json
from . import SETTINGS
from .render import FONT
from .smoke_suite import ROOT, NAMES, SHARED


def overview(call, path):
    """A display-only schematic. It is never an input to a native regional model."""
    image = Image.open(call["source"]["path"]).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(FONT), max(16, round(min(image.size) * 0.025)))
    colors = ["#e63946", "#2477e8", "#2daa50", "#efc92e", "#ce3bce"]
    native = call.get("native", {}).get("units", [])
    regions = call.get("regions")
    boxes = []
    if regions:
        for i, r in enumerate(regions):
            box = r.get("bbox_2d", r.get("bbox"))
            if isinstance(box, dict):
                box = [box[k] for k in ("x1", "y1", "x2", "y2")]
            if box:
                boxes.append((r.get("unit_id", f"R{i + 1}"), box))
    else:
        boxes = [
            (u["unit_id"], u["box_xyxy_pixels_half_open"])
            for u in native
            if u["box_xyxy_pixels_half_open"]
        ]
    for i, (label, box) in enumerate(boxes):
        color = colors[i % len(colors)]
        draw.rectangle(box, outline=color, width=max(2, round(min(image.size) * 0.004)))
        draw.text(
            (box[0], max(0, box[1] - 35)),
            label,
            font=font,
            fill=color,
            stroke_width=1,
            stroke_fill="white",
        )
    image.save(path)
    return path


def panel(root, tasks, dest):
    canvas = Image.new("RGB", (1800, 55 + 460 * len(tasks)), "#f1f5f9")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(str(FONT), 18)
    draw.text(
        (15, 12),
        f"{root.name} | {dest.stem} | source / actual input or schematic / output",
        font=font,
        fill="black",
    )
    for i, t in enumerate(tasks):
        d = root / "runs" / t["id"]
        r = json.loads((d / "result.json").read_text())
        c = json.loads((d / "call.json").read_text())
        y = 55 + i * 460
        draw.text(
            (15, y + 3),
            f"{t['case_id']} | {t['setting']} | {t['form']} | {r['status']}",
            font=font,
            fill="black",
        )
        source = c["source"]["path"]
        imgs = c["images"]
        if len(imgs) > 1:
            mid = imgs[1]
            label = "ACTUAL annotation input"
        elif t["form"] == "single":
            mid = imgs[0]
            label = "ACTUAL single input; left is context"
        elif c.get("native", {}).get("units") and t["setting"] != "S1":
            mid = overview(c, d / "region_schematic.jpg")
            label = "REGION SCHEMATIC (not an input image)"
        elif c.get("regions"):
            mid = overview(c, d / "region_schematic.jpg")
            label = "NATIVE PLANNER boxes (schematic)"
        else:
            mid = None
            label = "NO REGION INPUT"
        for col, (title, p) in enumerate(
            [("SOURCE", source), (label, mid), ("OUTPUT / status below", r.get("output_image"))]
        ):
            x = 15 + col * 600
            draw.text((x, y + 30), title, font=font, fill="black")
            if p:
                image = Image.open(p).convert("RGB")
                image.thumbnail((570, 390))
                canvas.paste(
                    image, (x + (570 - image.width) // 2, y + 60 + (390 - image.height) // 2)
                )
            else:
                draw.text(
                    (x + 30, y + 190),
                    r["status"] if col == 2 else "Not supplied",
                    font=font,
                    fill="#475569",
                )
    dest.parent.mkdir(exist_ok=True)
    canvas.save(dest, quality=93)


def generate(model):
    from markdown_it import MarkdownIt

    root = ROOT / model
    plan = json.loads((root / "plan.json").read_text())
    records = {}
    calls = {}
    missing = []
    for t in plan["tasks"]:
        d = root / "runs" / t["id"]
        if not (d / "result.json").exists():
            missing.append(t["id"])
            continue
        r = json.loads((d / "result.json").read_text())
        c = json.loads((d / "call.json").read_text())
        assert r["plan_digest"] == c["plan_digest"] == plan["digest"]
        if r["status"] == "generated":
            assert sha256_file(Path(r["output_image"])) == r["output_sha256"]
            with Image.open(r["output_image"]) as im:
                assert im.mode == "RGB" and list(im.size) == c["source"]["size"]
        records[t["id"]] = r
        calls[t["id"]] = c
    statuses = Counter(r["status"] for r in records.values())
    summary = {
        "model": NAMES[model],
        "statuses": dict(statuses),
        "missing": missing,
        "inference_api_calls": sum(r.get("inference_api_calls", 0) for r in records.values()),
        "transformer_forward_calls": sum(
            r.get("transformer_forward_calls", 0) for r in records.values()
        ),
        "pipeline_wall_seconds": sum(r.get("pipeline_wall_seconds", 0) for r in records.values()),
        "peak_gpu_allocated_bytes": max(
            (r.get("peak_gpu_allocated_bytes", 0) for r in records.values()), default=0
        ),
        "judge_calls": 0,
        "quality_scores_computed": False,
        "settings": {
            s: dict(Counter(r["status"] for r in records.values() if r["task"]["setting"] == s))
            for s in SETTINGS
        },
    }
    write_json(root / "summary.json", summary)
    if missing:
        raise ValueError(f"{model}: incomplete ({len(missing)} requests)")
    aliases = []
    for t in plan["tasks"]:
        if t["setting"] != "S1":
            continue
        src = records[t["id"]]
        for setting in ("S2-point", "S2-box", "S2-mask"):
            public = json.loads(
                (SHARED / "requests" / setting / t["case_id"] / "inputs.json").read_text()
            )
            s1 = json.loads((SHARED / "requests" / "S1" / t["case_id"] / "inputs.json").read_text())
            assert public["forms"]["discard-region"]["prompt"] == s1["forms"]["dual"]["prompt"]
            assert public["forms"]["discard-region"]["images"] == s1["forms"]["dual"]["images"]
            aliases.append(
                {
                    "case_id": t["case_id"],
                    "setting": setting,
                    "form": "discard-region",
                    "reuse_task": t["id"],
                    "status": "reused-identical-S1-path"
                    if src["status"] == "generated"
                    else src["status"],
                    "output_image": src.get("output_image"),
                    "additional_inference_calls": 0,
                    "reason": "Dropping region leaves exactly the S1 public input; native planning, if present, reuses its same recorded output.",
                }
            )
    write_json(root / "aliases.json", aliases)
    observations_path = root / "observations.json"
    observations = (
        json.loads(observations_path.read_text())
        if observations_path.exists()
        else {"observations": []}
    )
    report = f"# {NAMES[model]}：新协议冒烟报告\n\n**这是接口与行为检查，不是正式质量评分；未运行Judge、dev选型或test。**\n\n"
    report += "|汇报项|结论|\n|---|---|\n"
    report += f"|做了什么|固定3个dev case，结果状态：`{dict(statuses)}`；见全部实际输入/输出与prompt。生成成功不等于编辑通过。|\n"
    report += "|问题与偏差|见下方具体样例、环境配置及未执行原因；没有因输出质量改seed或重采样。|\n"
    report += "|阻塞项|N/A保持N/A；协议待确认或运行失败保留原原因，不补图、不填分数。|\n"
    report += (
        "|下一步|汇入统一问题/推荐报告；候选最终选择仍需同预算dev JointPass，冻结前等待确认。|\n\n"
    )
    report += (
        "## 实测调用\n\n```json\n" + json.dumps(summary, ensure_ascii=False, indent=2) + "\n```\n\n"
    )
    report += "运行耗时为实际请求wall之和，不等于纯GPU kernel时长，不用于速度排名。原始图保存在raw.png，评测尺寸图为output.png；MaskFlow另保存每个串行单元的输入、有效预处理mask、seed、输出与逆裁剪坐标。\n\n"
    for p in sorted(root.glob("worker*.environment.json")):
        env = json.loads(p.read_text())
        report += (
            f"<details>\n<summary>{p.name}：固定配置与环境</summary>\n\n```json\n"
            + json.dumps(env, ensure_ascii=False, indent=2)
            + "\n```\n\n</details>\n\n"
        )
    report += "## 定性观察与推荐边界\n\n"
    for o in observations["observations"]:
        report += f"- `{o['task_id']}`：{o['finding']}\n"
    report += "\n观察者为助手图像检查，不冒称独立人工审查；未计算标记残留率或任何通过分数。\n\n"
    image_paths = []
    for setting in SETTINGS:
        tasks = [
            t for t in plan["tasks"] if t["setting"] == setting and t["form"] in ("native", "dual")
        ]
        path = root / "comparisons" / f"{setting}.jpg"
        panel(root, tasks, path)
        image_paths.append(path)
        report += f"## {setting}\n\n![实际请求对照]({path})\n\n"
        for t in tasks:
            report += request_section(root, t, records[t["id"]], calls[t["id"]], image_paths)
    extra = [t for t in plan["tasks"] if t["form"] not in ("native", "dual")]
    if extra:
        path = root / "comparisons" / "alternative-S3-mask.jpg"
        panel(root, extra, path)
        image_paths.append(path)
        report += f"## S3-mask 备选输入路径\n\n![备选路径]({path})\n\n"
        for t in extra:
            report += request_section(root, t, records[t["id"]], calls[t["id"]], image_paths)
    report += "\n全部产物在/tmp/ifbench；没有新增正式评测结果。原生区域的示意图不是模型实际收到的附加图像。S2丢区域复用或N/A见aliases.json，不参与主配对结果的区域增益/语言依赖解释。\n"
    (root / "REPORT.md").write_text(report)
    rendered = MarkdownIt("commonmark", {"html": True}).enable("table").render(report)
    for p in image_paths:
        mime = "image/png" if p.suffix == ".png" else "image/jpeg"
        uri = f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()
        rendered = rendered.replace(f'src="{p}"', f'src="{uri}"')
    style = "body{font:17px/1.6 system-ui;max-width:1800px;margin:25px auto;padding:20px;color:#172033}img{max-width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f9;padding:15px}td,th{border:1px solid #cbd5e1;padding:10px}table{border-collapse:collapse}h2{margin-top:40px}details{margin:12px 0}a{color:#1d4ed8}"
    (root / "REPORT.html").write_text(
        f'<!doctype html><html lang="zh"><meta charset="utf-8"><title>{NAMES[model]} smoke</title><style>{style}</style><body>{rendered}</body></html>'
    )
    return summary


def request_section(root, task, result, call, image_paths):
    d = root / "runs" / task["id"]
    text = f"### {task['case_id']} · {task['form']}\n\n状态：**{result['status']}**。 [完整调用]({d / 'call.json'}) · [实测记录]({d / 'result.json'})\n\n"
    if result["status"] != "generated":
        text += result.get("reason", result.get("error", "")) + "\n\n"
    else:
        text += f"[原生输出]({d / 'raw.png'}) · [源图尺寸输出]({d / 'output.png'})\n\n"
    prompt = result.get("final_prompt", call.get("response", call["prompt"]))
    text += "**最终输入文本**\n\n```text\n" + prompt + "\n```\n\n"
    if call.get("sub_prompts"):
        text += (
            "**区域分支文本**\n\n```json\n"
            + json.dumps(call["sub_prompts"], ensure_ascii=False, indent=2)
            + "\n```\n\n"
        )
    if call.get("planner_record"):
        text += f"[原生规划器实际prompt、预测及调用记录]({call['planner_record']})\n\n"
    if call.get("regions"):
        text += "<details><summary>实际区域参数（预览框仅用于展示）</summary>\n\n```json\n"
        text += (
            json.dumps(call["regions"], ensure_ascii=False, indent=2) + "\n```\n\n</details>\n\n"
        )
    for unit_id, mask in zip(call.get("regional_unit_ids", []), call.get("masks", []), strict=True):
        path = Path(mask)
        image_paths.append(path)
        text += f"<details><summary>{unit_id}：实际传给MICE的原生mask（接口再缩放到latent网格）</summary>\n\n![实际mask]({path})\n\n</details>\n\n"
    if call.get("unit_requests"):
        for unit in call["unit_requests"]:
            path = d / "units" / unit["unit_id"] / "actual_mask.png"
            if path.exists():
                image_paths.append(path)
                text += f"<details><summary>{unit['unit_id']}：实际预处理mask及单元指令</summary>\n\n{unit['prompt']}\n\n![实际mask]({path})\n\n</details>\n\n"
    return text


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("model", choices=NAMES)
    a = p.parse_args()
    print(json.dumps(generate(a.model), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
