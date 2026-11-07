"""Chinese pilot report and real input/output contact sheets; no image selection by score."""

import json
import math
from pathlib import Path
import statistics
import textwrap

from PIL import Image, ImageDraw, ImageFont, ImageOps

from samtok_benchmark.external_pilot.data import load_bundle, read, immutable


def report(root, previews, doc=None):
    root, previews = Path(root), Path(previews)
    index = load_bundle(root / "bundle")
    rows = read(root / "bundle/private/evaluation.json")
    ids = [x["case_id"] for x in index["cases"]]
    metrics = ["rest_clip_sim", "ssim_similarity_outside_mask", "aligned_mse_diff", "aligned_psnr"]
    results = {}
    for model in ("sitedit", "qwen21"):
        values = []
        for cid in ids:
            r = read(root / "run" / model / "edit" / cid / "result.json")
            j = read(root / "scores" / model / cid / "judge/score.json")
            local = read(root / "scores" / model / cid / "local.json")
            values.append({"case_id": cid, "generation": r["status"], "correct": j["correct"],
                           "answer": j["answer"], "expected": j["expected"], **local["metrics"],
                           "edit_seconds": r["inference_seconds"],
                           "peak_allocated_gib": r["peak_gpu_allocated_bytes"] / 1024**3})
        means = {}
        for key in metrics:
            valid = [x[key] for x in values if isinstance(x[key], (int, float)) and math.isfinite(x[key])]
            means[key] = {"mean": statistics.mean(valid) if valid else None, "count": len(valid)}
        results[model] = {"n": len(values), "correct": sum(x["correct"] for x in values),
                          "accuracy": sum(x["correct"] for x in values) / len(values),
                          "metrics": means, "per_case": values,
                          "mean_edit_seconds": statistics.mean(x["edit_seconds"] for x in values),
                          "peak_allocated_gib": max(x["peak_allocated_gib"] for x in values)}
    payload = {"benchmark": "GIE-Bench", "scope": "9-request stratified pilot, not full benchmark",
               "bundle_digest": index["digest"], "judge": "gpt-5.4-2026-03-05", "models": results,
               "warning": "Published MSE/PSNR threshold selects all pixels on released 0/1 masks; these are not corrected background scores."}
    immutable(root / "report/REPORT.json", payload)
    lines = ["# GIE-Bench 小子集结果", "", "固定 seed 20261107，每类 1 条，共 9 条；两模型同一子集，每条 seed 42，仅生成一次。Judge 为 GPT-5.4，保留官方题目、提示和精确匹配规则。这是快速验证，不代表全量表现。", "",
             "| 方法 | 生成 | 问答正确率 ↑ | 区域外 CLIP ↑ | 区域外 SSIM ↑ | 官方脚本 MSE ↓ | 官方脚本 PSNR ↑ |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for model, name in [("sitedit", "SITEdit"), ("qwen21", "Qwen-Image-2.1")]:
        r = results[model]
        vals = [f"{r['metrics'][k]['mean']:.4f}" if r["metrics"][k]["mean"] is not None else "N/A" for k in metrics]
        lines.append(f"| {name} | {r['n']}/9 | {r['correct']}/9 ({r['accuracy']:.2%}) | " + " | ".join(vals) + " |")
    lines += ["", "注意：官方数据 mask 为 0/1，但 MSE/PSNR 发布代码使用 `<128` 判区域外，因此其结果实际是配准后的全图误差。上表原样保留官方代码，不将这两列解释为背景保持。CLIP/SSIM 按正确的 0/1 mask 计算。各指标有效分母见 REPORT.json。", "",
              "| 方法 | 平均编辑调用用时（秒） | 峰值 allocated 显存（GiB） |", "|---|---:|---:|"]
    for model in results:
        r = results[model]
        lines.append(f"| {model} | {r['mean_edit_seconds']:.2f} | {r['peak_allocated_gib']:.2f} |")
    lines += ["", "用时为真实记录的编辑调用时间，不含模型加载。SITEdit 的额外 Pass1 调用和完整阶段记录保留在 run/sitedit/tokens/。", "",
              "## 逐例结果", "", "| Case | 编辑类别 | SITEdit | 底座 |", "|---|---|---:|---:|"]
    by_model = {m: {x["case_id"]: x for x in r["per_case"]} for m, r in results.items()}
    for row in rows:
        cid = row["case_id"]
        lines.append(f"| {cid} | {row['canonical_category']} | {int(by_model['sitedit'][cid]['correct'])} | {int(by_model['qwen21'][cid]['correct'])} |")
    lines += ["", "1 表示 GPT-5.4 选择的选项与官方答案完全相同；0 表示不同。不能将两个模型均生成成功等同于正确完成编辑。", "",
              "## 文件与复现", "", f"- 原始结果与报告：`{root}`。", f"- 全部对比图：`{previews}`。",
              "- 数据、代码、权重与输入配置详见 GIE_EVALUATION.md；分支 eval-gie。", "", "## 全部案例对比", ""]
    previews.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 19)
    for row in rows:
        cid = row["case_id"]
        title = textwrap.fill(cid + ": " + row["edit_instruction"], 100)
        offset = 38 + 23 * len(title.splitlines())
        canvas = Image.new("RGB", (1290, offset + 480), "white")
        draw = ImageDraw.Draw(canvas)
        draw.multiline_text((15, 10), title, font=font, fill="black")
        paths = [("Source", row["canonical_source"]["path"]),
                 ("SITEdit", root / "run/sitedit/edit" / cid / "output.png"),
                 ("Qwen-Image-2.1", root / "run/qwen21/edit" / cid / "output.png")]
        for i, (name, path) in enumerate(paths):
            image = ImageOps.contain(Image.open(path).convert("RGB"), (410, 430))
            draw.text((i * 430 + 10, offset), name, font=font, fill="black")
            canvas.paste(image, (i * 430 + 10 + (410-image.width)//2, offset+35+(430-image.height)//2))
        destination = previews / (cid + ".png")
        canvas.save(destination)
        lines += [f"### {cid} · {row['canonical_category']}", "", row["edit_instruction"], "",
                  f"![{cid} 输入输出对照]({destination})", ""]
    markdown = "\n".join(lines) + "\n"
    (root / "report/REPORT.md").write_text(markdown)
    (previews / "REPORT.md").write_text(markdown)
    if doc:
        Path(doc).write_text(markdown.split("## 全部案例对比")[0])
    print(json.dumps({m: {k: v for k, v in r.items() if k != "per_case"} for m, r in results.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--previews", required=True)
    p.add_argument("--doc")
    a = p.parse_args()
    report(a.root, a.previews, a.doc)
