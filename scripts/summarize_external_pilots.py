"""Summarize the eight fixed, independently scored external pilot reports."""

import argparse
import hashlib
import json
from pathlib import Path
import re

SPECS = (
    ("gie", "gie", "GIE-Bench", "GIE", 9, "文字指令编辑的正确性与非编辑区域保持"),
    ("compbench", "compbench", "CompBench", "COMPBENCH", 8, "多对象、隐含意图与组合编辑"),
    ("complexbench_edit", "complexbench-edit", "ComplexBench-Edit", "COMPLEXBENCH_EDIT", 10, "并行多指令与链式指令"),
    ("interedit", "interedit", "Inter-Edit", "INTEREDIT", 8, "公开 mask 引导的区域编辑"),
    ("complex_edit", "complex-edit", "Complex-Edit", "COMPLEX_EDIT", 8, "同图不同复杂度的复合指令"),
    ("gedit", "gedit", "GEdit-Bench", "GEDIT", 11, "十一类通用图像编辑"),
    ("omni_iie", "omni-iie", "Omni IIE Bench", "OMNI_IIE", 8, "同图 low/high 配对的隐含意图编辑"),
    ("gide", "gide", "GIDE-Bench", "GIDE", 8, "文字、框、多边形指引的双目标编辑"),
)
PREVIEW_NAMES = {"omni_iie": "OmniIIEBench_20261107"}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(slug, raw):
    if slug != "gie":
        return raw
    result = dict(raw)
    result["metric_labels"] = {
        "accuracy": "编辑正确率 ↑", "rest_clip_sim": "区域外 CLIP ↑",
        "ssim_similarity_outside_mask": "区域外 SSIM ↑",
        "aligned_mse_diff": "官方 MSE ↓", "aligned_psnr": "官方 PSNR ↑",
    }
    result["notes"] = ["GIE 官方 MSE/PSNR 代码对 0/1 mask 使用 <128 阈值，实际覆盖全图；不把这两项称作背景指标。"]
    result["models"] = {}
    for model, r in raw["models"].items():
        metrics = dict(r["metrics"])
        metrics["accuracy"] = {"mean": r["accuracy"], "count": r["n"]}
        result["models"][model] = {
            **r, "generated": sum(x["generation"] == "completed" for x in r["per_case"]),
            "metrics": metrics,
        }
    return result


def number(value):
    return "N/A" if value is None else f"{value:.4f}"


def summarize(results, previews, output, doc=None):
    reports, evidence = {}, {}
    for slug, _, _, _, n, _ in SPECS:
        root = results / ("external_"+slug) / "pilot_20261107"
        path = root / "report/REPORT.json"
        report = normalized(slug, read(path))
        if any(r["n"] != n for r in report["models"].values()):
            raise ValueError(f"Unexpected sample count: {slug}")
        reports[slug] = report
        evidence[slug] = {"report": str(path), "sha256": sha(path), "bundle_digest": report["bundle_digest"]}
    lines = ["# 八个外部 benchmark：SITEdit 与 Qwen-Image-2.1 小子集验证", "",
        "固定 70 条请求、两方法各生成一次，共 140 个预定输出。抽样 seed 为 20261107，生成 seed 为 42。每个 benchmark 独立分支、固定输入后再生成和评分；不按结果换样、调参或挑选重采样。", "",
        "SITEdit 为 aa5a414 冻结主行：Pass1 step2000、S2 adapter16000、raw SAMTok TE、40 步、token guidance 2；base 为 Qwen-Image-2.1 原生 40 步、CFG 1。两方法获得相同公开信息，约 1MP 画布，输出回源后再采用各 benchmark 的原生评分预处理。", "",
        "涉及付费 Judge 的项目统一采用用户指定 GPT-5.4；保留各官方提示、证据与聚合定义。因此这是同协议重评的两模型对比，不能直接和使用其他 Judge 的论文数字混排。所有数值均来自实际输出和评分记录，没有估计填分。", "",
        "这些是分层小子集观察，不是完整测试集排名或显著性结论。不同 benchmark 的指标不能相加为一个总分。", "",
        "## 完成情况与分支", "",
        "| 顺序 | Benchmark | 请求数 | SITEdit 出图 | Base 出图 | 主要验证内容 |", "|---:|---|---:|---:|---:|---|"]
    for i, (slug, branch, title, upper, n, purpose) in enumerate(SPECS, 1):
        r = reports[slug]
        link = f"https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-{branch}/docs/{upper}_RESULTS.md"
        lines.append(f"| {i} | [{title}]({link}) | {n} | {r['models']['sitedit']['generated']}/{n} | {r['models']['qwen21']['generated']}/{n} | {purpose} |")
    audit_path = output/"AUDIT.json"
    if audit_path.exists():
        checked = read(audit_path)
        assert all(checked[s]["report_sha256"] == evidence[s]["sha256"] for s in reports)
        means = sum(x["independently_verified_means"] for x in checked.values())
        calls = sum(x["api_responses"] for x in checked.values())
        choices = sum(x["api_choices"] for x in checked.values())
        lines += ["", f"独立核对：{means} 个汇总数值均由逐例评分复算一致；{calls} 次实际 API 请求、{choices} 个答案全部正常结束。[核对记录]({audit_path})。"]
    lines += ["", "## 这轮验证说明什么", "",
        "- **CompBench 是本轮最明确的正向信号**：SITEdit 的局部文本/图像一致性与三项背景保持指标均优于 base。可以优先考虑扩大预先固定的样本规模来验证这一观察。",
        "- **GIE 与 Inter-Edit 体现分项取舍**：SITEdit 的部分区域外保持指标更好，但编辑正确性或区域内目标相似度并未同时领先，不能用保持分数替代任务成功。",
        "- **Omni IIE 的结果也是混合的**：SITEdit 的 LPIPS、SSIM、BG LPIPS 更好；base 的全图/前景 CLIP 相似度等指标更好。缺少 QA 的本轮结果不足以直接衡量隐含意图是否全部完成。",
        "- **ComplexBench-Edit、Complex-Edit、GEdit-Bench 与 GIDE 的主要指令/综合评分为 base 较高**。保留全部固定样例，没有隐藏较低分项目。这一观察只适用于当前冻结输入适配与小子集。",
        "- 本轮不选择新 checkpoint、不改 token guidance、不尝试多个 prompt 后择优。后续若扩大评测，应先确定完整协议和样本，不能把本轮子集当作完整 benchmark 报分。", "",
        "## 已确认的协议边界", "",
        "- CompBench 仅选官方可评分的六类；action/location/view 未被这轮 8 条请求覆盖。",
        "- Inter-Edit 保留四项不依赖 reference_image 的客观指标；缺参考图的指标及 VLM 为 N/A。",
        "- Omni IIE 保留八项官方可运行指标；QA 和 Overall 为 N/A，不生成额外问题。其 BG_CLIP-I 实现会丢弃遮罩 alpha，含义需按下文说明解读。",
        "- GIE 原始 MSE/PSNR 的阈值行为照官方代码保留，不误称为背景分数。",
        "- Qwen2.1 的部分区域提示输出原生带透明背景；所有输出按已固定的 RGB 回源/评分口径处理，不回贴源图、不补背景。原始 RGBA 与独立诊断保留。",
        "- 所有数据采用官方发布源和固定版本。未借用训练标注或私有评测信息增强生成；门控数据仅在用户授权后下载。", "",
        "## 各项实际分数", "", "↑ 越高越好，↓ 越低越好；加粗仅表示当前小子集的较优数值，不表示统计显著。"]
    for slug, branch, title, upper, n, _ in SPECS:
        r = reports[slug]
        lines += ["", f"### {title}（{n} 条）", "", "| 指标 | SITEdit | Qwen-Image-2.1 | 有效评分数（各方法） |", "|---|---:|---:|---:|"]
        for key, label in r["metric_labels"].items():
            a, b = [r["models"][m]["metrics"][key] for m in ("sitedit", "qwen21")]
            av, bv = a["mean"], b["mean"]
            af, bf = number(av), number(bv)
            if av is not None and bv is not None and af != bf:
                if (av < bv) == ("↓" in label):
                    af = f"**{af}**"
                else:
                    bf = f"**{bf}**"
            lines.append(f"| {label} | {af} | {bf} | {a['count']}/{n}；{b['count']}/{n} |")
        lines += ["", *[f"- {x}" for x in r.get("notes", [])], "",
            f"- 结果文件：[{title} REPORT.json]({evidence[slug]['report']})。",
            f"- 评测代码与输入说明：[eval-{branch}](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-{branch}/docs/{upper}_EVALUATION.md)。"]
        directory = previews / PREVIEW_NAMES.get(slug, title.replace(" ", "")+"_20261107")
        cid = r["models"]["sitedit"]["per_case"][0]["case_id"]
        preview = directory/(cid+".png")
        if not preview.exists():
            raise FileNotFoundError(preview)
        lines += [f"- [全部请求的图文对比]({directory/'REPORT.md'})。", "",
            f"下图为固定抽样清单的首条请求 `{cid}`，不按得分挑选展示。", "", f"![{title} 输入与两方法输出]({preview})"]
    lines += ["", "## 运行开销", "", "| Benchmark | SITEdit 平均编辑秒数 | Base 平均编辑秒数 | SITEdit / Base 峰值 allocated GiB |", "|---|---:|---:|---:|"]
    for slug, _, title, _, _, _ in SPECS:
        a, b = [reports[slug]["models"][m] for m in ("sitedit", "qwen21")]
        lines.append(f"| {title} | {a['mean_edit_seconds']:.2f} | {b['mean_edit_seconds']:.2f} | {a['peak_allocated_gib']:.2f} / {b['peak_allocated_gib']:.2f} |")
    lines += ["", "以上仅为实测编辑调用，不含权重加载；SITEdit 的额外 Pass1 或 codec 阶段另存逐阶段收据。峰值是 PyTorch allocated，不含同卡其他任务。GPU 只使用用户允许且空闲的 4–7；评分使用 CPU 或授权 API。", "",
        "## 可追溯证据", "", "汇总读取各分支独立保存的 REPORT.json。完整输入、逐例输出、评分原文、失败和配置身份均在各结果根；SOURCE.json 和 SUBSET.json 位于对应 NAS 数据目录。", "",
        "| Benchmark | REPORT.json SHA256 |", "|---|---|"]
    for slug, _, title, _, _, _ in SPECS:
        lines.append(f"| {title} | `{evidence[slug]['sha256']}` |")
    output.mkdir(parents=True, exist_ok=True)
    (output/"REPORT.md").write_text(re.sub(r"\n{3,}", "\n\n", "\n".join(lines))+"\n")
    (output/"SOURCES.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+"\n")
    if doc:
        text = [line for line in lines if not line.startswith(("![", "下图为固定抽样清单"))]
        text[2:2] = [f"带全部对比图的总报告：`{output/'REPORT.md'}`。图片保存在指定可视化目录，不提交到 Git。", ""]
        doc.write_text(re.sub(r"\n{3,}", "\n\n", "\n".join(text))+"\n")
    print(output/"REPORT.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--previews", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--doc", type=Path)
    args = parser.parse_args()
    summarize(args.results, args.previews, args.output, args.doc)
