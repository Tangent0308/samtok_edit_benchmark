"""Render current real inputs/outputs and engineering results, never infer scores."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from samtok_benchmark.io import sha256_file, write_json
from samtok_benchmark.paths import repository_root
from .fairness_dev_plan import MODELS, SETTINGS, read

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def sheet(items, destination, columns=2, cell=(560, 400)):
    rows = (len(items) + columns - 1) // columns
    image = Image.new("RGB", (columns * cell[0], rows * cell[1]), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT, 16)
    for i, (title, path) in enumerate(items):
        x, y = (i % columns) * cell[0], (i // columns) * cell[1]
        draw.text((x + 8, y + 6), title, fill="black", font=font)
        if path:
            with Image.open(path) as source:
                preview = ImageOps.contain(
                    source.convert("RGB"), (cell[0] - 16, cell[1] - 38), Image.Resampling.LANCZOS
                )
            image.paste(
                preview,
                (x + (cell[0] - preview.width) // 2, y + 32 + (cell[1] - 38 - preview.height) // 2),
            )
        else:
            draw.text((x + 20, y + 90), "No generated output", fill="darkred", font=font)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, quality=90)


def render(bundle, docs=None):
    bundle = Path(bundle).resolve()
    docs = Path(docs) if docs else repository_root() / "docs"
    plan = read(bundle / "plan.json")
    if plan.get("schema") != "ifbench-1mp-probe-v1":
        raise ValueError("This renderer requires a fixed 1MP engineering probe")
    shared = Path(plan["paths"]["shared"])
    assets = docs / "assets/current"
    provenance = {
        "plan": str(bundle / "plan.json"),
        "plan_sha256": sha256_file(bundle / "plan.json"),
        "configuration": str(bundle / "configuration.json"),
        "figures": [],
    }
    lines = [
        "# 当前 1MP 输入样例",
        "",
        "每个 setting 展示三个固定请求：清图、标注图及最终共享 prompt。模型专用路由见 [使用说明](USAGE.md)。所有图均来自本轮真实公共输入；S1 没有区域标注图。",
        "",
    ]
    for setting in SETTINGS:
        items, examples = [], []
        for cid in plan["gallery_case_ids"]:
            directory = shared / "requests" / setting / cid
            public, inputs = read(directory / "public.json"), read(directory / "inputs.json")
            items.append((cid + " / clean 1MP", public["source"]["path"]))
            items.append(
                (
                    cid + (" / annotation" if inputs["annotation"] else " / S1 clean"),
                    inputs["annotation"]["path"]
                    if inputs["annotation"]
                    else public["source"]["path"],
                )
            )
            examples.append((cid, inputs))
        path = assets / f"inputs-{setting}.jpg"
        sheet(items, path)
        provenance["figures"].append(
            {
                "path": str(path.relative_to(docs)),
                "sha256": sha256_file(path),
                "sources": [{"path": p, "sha256": sha256_file(Path(p))} for _, p in items],
            }
        )
        lines += [f"## {setting}", "", f"![{setting} 三个实际输入](assets/current/{path.name})", ""]
        for cid, inputs in examples:
            lines += [
                f"### {cid}",
                "",
                "双图模型的最终共享 prompt：",
                "",
                "```text",
                inputs["forms"]["dual"]["prompt"],
                "```",
                "",
            ]
            if inputs["forms"]["single"]["prompt"] != inputs["forms"]["dual"]["prompt"]:
                lines += [
                    "单图标注形式的最终共享 prompt：",
                    "",
                    "```text",
                    inputs["forms"]["single"]["prompt"],
                    "```",
                    "",
                ]
            lines += [
                f"七模型实际请求：[目录]({bundle / 'requests'})，键为 `<model>/{setting}/{cid}/request.json`。RePlan/MIRAGE 的完整原生规划消息另保存在本轮结果的 `planners/` 中。",
                "",
            ]
    (docs / "INPUT_EXAMPLES.md").write_text("\n".join(lines))
    counts = {
        m: {"generated": 0, "failed": 0, "pending": 0, "seconds": [], "sizes": set()}
        for m in MODELS
    }
    results = {}
    for task in plan["tasks"]:
        p = Path(task["result_path"])
        result = read(p) if p.exists() else {"status": "pending"}
        if result["status"] == "generated":
            if sha256_file(Path(result["output_image"])) != result["output_sha256"]:
                raise ValueError("Output bytes changed before visualization")
            if result.get("plan_digest") != plan["digest"]:
                raise ValueError("Output belongs to another plan")
            with Image.open(result["output_image"]) as im:
                if list(im.size) != read(task["canvas_transform"])["source_size"]:
                    raise ValueError("Output was not restored to canonical dimensions")
        status = (
            "generated"
            if result["status"] == "generated"
            else "pending"
            if result["status"] == "pending"
            else "failed"
        )
        c = counts[task["model"]]
        c[status] += 1
        if status == "generated":
            c["seconds"].append(result["wall_seconds"])
            c["sizes"].add(tuple(result["raw_size"]))
        results[task["key"]] = result
    report = [
        "# 当前评测结果与分析",
        "",
        "**主协议：统一约 1MP；正式全量结果：待评测。**",
        "",
        "本轮快速验证固定两张 dev 图（K=2、K=5），每模型运行 S1、S3-point、S5，共42个生成请求。另对三张固定图的十种 setting、七模型共210个请求完成CPU输入检查。样本只按公开K和固定名单选取，不按模型分数选择。",
        "",
        "本轮没有调用 Judge，因此没有 UnitPass / JointPass 分数或置信区间。下表的出图数量仅表示工程执行成功，不等同于编辑任务通过。",
        "",
        "| 模型 | 成功出图 | 失败 | 待完成 | 实测平均编辑调用秒数 | 实际原生输出尺寸 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for model, c in counts.items():
        mean = f"{sum(c['seconds']) / len(c['seconds']):.1f}" if c["seconds"] else "—"
        sizes = ", ".join(f"{w}×{h}" for w, h in sorted(c["sizes"])) or "—"
        report.append(
            f"| {model} | {c['generated']}/6 | {c['failed']} | {c['pending']} | {mean} | {sizes} |"
        )
    report += [
        "",
        "调用耗时来自实际 worker 记录，不含模型加载；包含该调用内的同步与结果落盘，不能当作纯GPU算子性能。",
        "",
        "## 各 setting 的模型对照",
        "",
        "表中仅列本轮工程出图数；未纳入此次GPU短测的setting标为“未短测”，不标为N/A。",
        "",
        "| Setting | " + " | ".join(MODELS) + " |",
        "|---|" + "---|" * len(MODELS),
    ]
    for setting in SETTINGS:
        cells = []
        for model in MODELS:
            group = [
                results[t["key"]]
                for t in plan["tasks"]
                if t["model"] == model and t["setting"] == setting
            ]
            cells.append(
                f"{sum(r['status'] == 'generated' for r in group)}/{len(group)}"
                if group
                else "未短测"
            )
        report.append(f"| {setting} | " + " | ".join(cells) + " |")
    report += [
        "",
        "## 正式评分表",
        "",
        "每格为 UnitPass / JointPass；分母为全量1,084图和3,872单元，最终附按源图配对bootstrap的95%置信区间。",
        "",
        "| Setting | " + " | ".join(MODELS) + " |",
        "|---|" + "---|" * len(MODELS),
    ]
    report += [f"| {s} | " + " | ".join(["待评测"] * len(MODELS)) + " |" for s in SETTINGS]
    report += [
        "",
        "## 当前输入与输出",
        "",
        "每张图依次展示公共清图和七模型回源输出。输入形式与最终prompt另见 [十种setting输入样例](INPUT_EXAMPLES.md)。",
    ]
    for setting in plan["settings"]:
        for cid in plan["case_ids"]:
            public = read(shared / "requests" / setting / cid / "public.json")
            items = [("Input / clean 1MP", public["source"]["path"])]
            for model in MODELS:
                result = results[f"{model}/{setting}/{cid}"]
                items.append(
                    (
                        model + " / " + result["status"],
                        result.get("output_image") if result["status"] == "generated" else None,
                    )
                )
            path = assets / f"outputs-{setting}-{cid}.jpg"
            sheet(items, path, columns=4, cell=(400, 340))
            provenance["figures"].append(
                {
                    "path": str(path.relative_to(docs)),
                    "sha256": sha256_file(path),
                    "sources": [{"path": p, "sha256": sha256_file(Path(p))} for _, p in items if p],
                }
            )
            report += [
                "",
                f"### {setting} · {cid}",
                "",
                f"![{setting} 七模型实际输出](assets/current/{path.name})",
            ]
    report += [
        "",
        "## 结论与边界",
        "",
        "- 公共输入严格限制在约1MP，清图和标注图同画布；原生planner也不读取更高清源图。",
        "- RePlan和MIRAGE保留原生约1MP输出网格，其他模型固定公共画布尺寸。所有输出按记录的内容框去留边、回到canonical尺寸。",
        "- 原生内部视觉编码与局部放大不同，统一全图分辨率不等于统一计算预算。",
        "- 这组极小样本只验证可运行性和几何流程，不能推断模型排名、全量正确率或置信区间。",
    ]
    review_path = assets / "VISUAL_REVIEW.json"
    if review_path.exists():
        review = read(review_path)
        if review["plan_sha256"] != provenance["plan_sha256"]:
            raise ValueError("Visual observations belong to another probe")
        for observation in review["observations"]:
            if sha256_file(Path(observation["output_image"])) != observation["output_sha256"]:
                raise ValueError("Visually inspected output changed")
            report.append("- " + observation["note"])
        report.append("- 上述缩略图检查为工程目视检查，不是独立人工评分或标记残留率统计。")
    report += [
        "",
        "## 结果位置与复现",
        "",
        f"- 运行包：`{bundle}`。",
        f"- 请求与输入：`{bundle / 'requests'}`、`{shared}`。",
        f"- 输出与原生规划：`{plan['results_root']}/runs/`。",
        f"- 本轮plan SHA256：`{sha256_file(bundle / 'plan.json')}`。",
        "- seed=42，每请求一次采样；失败保留完整记录，不挑图或额外采样。",
        "- 正式四机运行及路径见 [FULL_RUN.md](FULL_RUN.md)。",
    ]
    failures = [
        (key, r) for key, r in results.items() if r["status"] not in {"generated", "pending"}
    ]
    if failures:
        report += ["", "## 本轮失败", ""]
        report += [f"- `{key}`：`{r.get('error', r['status'])}`。" for key, r in failures]
    (docs / "RESULTS.md").write_text("\n".join(report) + "\n")
    write_json(assets / "PROVENANCE.json", provenance)
    write_json(
        Path(plan["results_root"]) / "REPORT.json",
        {
            "models": {m: {**c, "sizes": sorted(c["sizes"])} for m, c in counts.items()},
            "judge_calls": 0,
            "quality_scores": None,
            "plan_digest": plan["digest"],
            "failures": failures,
        },
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--docs", type=Path)
    a = p.parse_args()
    render(a.bundle, a.docs)


if __name__ == "__main__":
    main()
