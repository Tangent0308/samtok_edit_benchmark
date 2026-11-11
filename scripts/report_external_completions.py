#!/usr/bin/env python3
# ruff: noqa: E402 - isolated CLI explicitly adds the repository source path.
"""Wait for terminal reports and assemble the requested five-method comparison."""

import argparse
import json
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from samtok_benchmark.external_refedit.data import immutable, read
from samtok_benchmark.io import sha256_file

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
CONTROL = NAS / ".ifbench-tmp/external_additions_20261111"
COMP = NAS / "experiments2/SAMTokEdit/external_compbench"
SOURCES = {
    "old_comp": COMP / "full5_20261109/reports/run001/REPORT.json",
    "new_sitedit": COMP / "r2_multitarget_manual_20261111/final/full_report/REPORT.json",
    "new_mirage": COMP / "mirage_20261111/report/REPORT.json",
    "mira": NAS / "experiments2/SAMTokEdit/external_mira/mice_20261111/ALL_MODELS_COMPARISON.json",
    "magicbrush": NAS
    / "experiments2/SAMTokEdit/external_magicbrush/mirage_recovery_20261111/COMPARISON.json",
}
ORDER = ["qwen21", "replan", "mirage", "mice", "sitedit"]
NAMES = {
    "qwen21": "Qwen-Image-2.1",
    "replan": "RePlan",
    "mirage": "MIRAGE",
    "mice": "MICE",
    "sitedit": "SITEdit R2@1000",
}
GROUPS = [
    "Local Editing",
    "Multi-object Editing",
    "Implicit Reasoning",
    "Multi-turn (Turn 1)",
    "Multi-turn (Turn 2)",
]
METRICS = ["LC-T", "LC-I", "PSNR", "SSIM", "LPIPS"]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wait", action="store_true")
    args = p.parse_args()
    while not all(p.exists() for p in SOURCES.values()):
        state_path = CONTROL / "compbench/syntax_recovery/STATUS.json"
        try:
            state = read(state_path)
        except (FileNotFoundError, json.JSONDecodeError):
            state = {}
        if state.get("status") == "error":
            raise RuntimeError("Pipeline stopped; preserve evidence and inspect STATUS.json")
        if not args.wait:
            raise RuntimeError("Not all final reports are available")
        time.sleep(60)
    data = {k: read(p) for k, p in SOURCES.items()}
    ids = set(data["new_sitedit"]["case_ids"])
    if len(ids) != 3285 or set(data["new_mirage"]["case_ids"]) != ids:
        raise ValueError("Final methods must cover the same full objective cohort")
    merged = {}
    for model in ORDER:
        report = (
            data["new_sitedit"]
            if model == "sitedit"
            else data["new_mirage"]
            if model == "mirage"
            else data["old_comp"]
        )
        observed = {
            r["case_id"] for r in report["per_case"] if r["model"] == model and r["case_id"] in ids
        }
        if observed != ids:
            raise ValueError(f"Missing comparison requests for {model}")
        row = report["rows"][model]
        merged[model] = {
            **row,
            "groups": [g for g in row["groups"] if g["group"] in GROUPS],
            "tasks": [t for t in row["tasks"] if t["task"] not in {"action", "location", "view"}],
        }
    obj = {
        "schema": "external.completion.comparison.v1",
        "compbench_case_ids": sorted(ids),
        "models": ORDER,
        "compbench": merged,
        "mira": data["mira"],
        "magicbrush": data["magicbrush"],
        "sources": {k: {"path": str(p), "sha256": sha256_file(p)} for k, p in SOURCES.items()},
        "sitedit_input": "All 144 multi-object cases use individually reviewed public units and original native Pass1 codes; one joint final R2 S2 call.",
        "failure_policy": data["new_mirage"]["failure_policy"],
    }
    dest = COMP / "mirage_20261111/ALL_MODELS_COMPARISON.json"
    immutable(dest, obj)
    md = [
        "# 外部评测补全结果",
        "",
        "本轮新增 MIRA/MICE、CompBench/MIRAGE，并将最终 SITEdit R2@1000 的全部 144 条多目标请求更新为逐条审核的单目标单元。旧结果保持只读；下表中的 SITEdit 仅使用最终检查点。",
        "",
        "## MIRA-Bench",
        "",
        "200 张源图，原生 GPT-5.4 PF/Cons。",
        "",
        "| 方法 | PF ↑ | Cons ↑ |",
        "|---|---:|---:|",
    ]
    by_model = {r["model"]: r for r in data["mira"]["rows"]}
    for model in ORDER:
        row = by_model[model]
        md.append(f"| {NAMES[model]} | {row['PF']:.3f} | {row['Cons']:.3f} |")
    md += [
        "",
        "MICE 原始 PQ/Overall 及历史基线的覆盖、评分时间与来源见 MIRA 补全报告。底座/SITEdit 的同时段 PQ 对比保持单独口径，不与本次新增行拼算 Overall。",
        "",
        "## CompBench",
        "",
        "仅 3,285 条官方客观评分请求。按官方子任务等权聚合；两轮任务使用各方法自己的前轮输出。",
        "",
    ]
    for group in GROUPS:
        md += [
            f"### {group}",
            "",
            "| 方法 | LC-T ↑ | LC-I ↑ | PSNR ↑ | SSIM ↑ | LPIPS ↓ |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for model in ORDER:
            g = next(x for x in merged[model]["groups"] if x["group"] == group)
            values = g["valid_mean"]
            if any(values.get(k) is None for k in METRICS):
                raise ValueError("No score can be invented for a wholly unscored group")
            formats = [
                f"{values[k]:.3f}" if k in {"LC-T", "PSNR"} else f"{values[k]:.4f}" for k in METRICS
            ]
            md.append("| " + " | ".join([NAMES[model], *formats]) + " |")
        md.append("")
    md += [
        "## 核验与范围",
        "",
        "- SITEdit：R2@1000、Pass1 step 2000、raw SAMTok TE、LoRA 1.0、γ=2、40 步、seed 42；逐目标放码后一次联合出图。",
        "- 每条拆分在出图前固定。10 条已有原生回答仅按既有严格规则恢复 JSON 拼写，区域码原文、标签和顺序不变；没有新增 Pass1 调用或人工区域。",
        "- 新的 144 条整体替换旧多目标条目；其余 3,141 条 R2 结果及所有既有基线复用，不逐例按分数选输出。",
        "- MagicBrush 结果未重新评测；其完整结果与来源随比较 JSON 原样保留。",
        "- 各方法的原生失败／评分缺失及有效覆盖保留在比较 JSON 中；没有用其他 benchmark 的失败惩罚补分。",
        "",
        "## 结果来源",
        "",
    ]
    for key, p in SOURCES.items():
        md.append(f"- [{key}]({p})")
    text = "\n".join(md) + "\n"
    for p in (
        COMP / "mirage_20261111/ALL_MODELS_COMPARISON_ZH.md",
        Path(
            "/opt/tiger/tanyue/visualization_tmp/ExternalBench_Completions_20261111/RESULTS_ZH.md"
        ),
    ):
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.read_text() != text:
            raise ValueError("An existing completed report differs; do not overwrite it")
        if not p.exists():
            p.write_text(text)
    print(dest, flush=True)


if __name__ == "__main__":
    main()
