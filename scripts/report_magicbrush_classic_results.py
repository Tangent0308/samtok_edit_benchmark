"""Merge classic MagicBrush results while retaining the scorer's auxiliary diagnostics.

This postprocessing entry stays outside the frozen generation/scoring module. It
reuses its record verification, primary-metric statistics, bootstrap, and report
layout. Original score.json files retain the additional GT-CLIP-T diagnostic.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from collections import Counter
from datetime import datetime, timezone
import statistics
import numpy as np
from samtok_benchmark.io import sha256_file
from samtok_benchmark.external_magicbrush.data import immutable, read
from samtok_benchmark.external_magicbrush.metrics import METRICS
from samtok_benchmark.external_magicbrush_classic.common import SOURCE_REPORT, SOURCE_REPORT_SHA
from samtok_benchmark.external_magicbrush_classic.report import (
    collect,
    summarise,
    DISPLAY_MODELS,
    DISPLAY_NAMES,
)


def primary_score(score):
    """Project primary metrics in a copy; never edit a scored answer or its identity."""
    if score["status"] != "scored":
        return score
    values = score["metrics"]
    if not set(METRICS) <= set(values) or set(values) - set(METRICS) - {"GT-CLIP-T"}:
        raise ValueError("Unexpected scorer metric schema")
    return {**score, "metrics": {k: values[k] for k in METRICS}}


def report(output):
    output = Path(output)
    plan, _, _, items, records = collect(output)
    records = [(m, i, r, primary_score(s) if s else None) for m, i, r, s in records]
    if plan["scope"] != "full" or len(plan["session_ids"]) != 535 or len(items) != 1571:
        raise ValueError("Final report requires every test session/request")
    if sha256_file(SOURCE_REPORT) != SOURCE_REPORT_SHA:
        raise ValueError("Existing report changed")
    source = read(SOURCE_REPORT)
    sessions = plan["session_ids"]
    indices = np.random.default_rng(20261105).integers(
        0, len(sessions), size=(10000, len(sessions)), dtype=np.int32
    )
    import hashlib

    if (
        hashlib.sha256(indices.tobytes()).hexdigest()
        != source["bootstrap"]["subsets"]["full"]["indices_sha256"]
    ):
        raise ValueError("Shared bootstrap indices differ")
    last = {sid: max(i["turn"] for i in items if i["session_id"] == sid) for sid in sessions}
    rows, methods = [], []
    for model in plan["models"]:
        chosen = [(i, r, s) for m, i, r, s in records if m == model]
        for mode in ("single-turn", "multi-turn"):
            panel = [
                (i, r, s)
                for i, r, s in chosen
                if (
                    i["mode"] == "independent"
                    if mode == "single-turn"
                    else i["turn"] == last[i["session_id"]]
                    and i["mode"] == ("independent" if i["turn"] == 1 else "iterative")
                )
            ]
            if len(panel) != (1053 if mode == "single-turn" else 535):
                raise ValueError("Final score denominator differs from full test set")
            rows.append(summarise(model, mode, panel, sessions, indices))
        successful = [r for _, r, _ in chosen if r and r["status"] == "completed"]
        methods.append(
            {
                "model": model,
                "generation_status": dict(
                    Counter(r["status"] if r else "missing" for _, r, _ in chosen)
                ),
                "mean_inference_seconds": statistics.fmean(
                    r["inference_seconds"] for r in successful
                )
                if successful
                else None,
                "inference_gpu_hours": sum(r["inference_seconds"] for r in successful) / 3600,
                "peak_allocated_gib": max(
                    (r["peak_gpu_allocated_bytes"] for r in successful), default=0
                )
                / 2**30,
            }
        )
    old_rows = [
        r
        for r in source["rows"]
        if r["model"] in DISPLAY_MODELS and r["track"] == "mask-free" and r["subset"] == "full"
    ]
    if len(old_rows) != 12:
        raise ValueError("Unexpected existing six-method row coverage")
    result = {
        "schema": "magicbrush.classic.merged.v1",
        "created": datetime.now(timezone.utc).isoformat(),
        "existing_report": {"path": str(SOURCE_REPORT), "sha256": SOURCE_REPORT_SHA},
        "addition_run": str(output),
        "models": list(DISPLAY_MODELS),
        "track": "mask-free",
        "subset": "full",
        "excluded_cases": [],
        "sessions": 535,
        "independent_turns": 1053,
        "bootstrap": source["bootstrap"],
        "policy": source["policy"],
        "new_methods": methods,
        "rows": old_rows + rows,
        "report_adapter": {
            "source_sha256": sha256_file(Path(__file__)),
            "rule": "Select the five frozen primary metrics; retain GT-CLIP-T unchanged in original score records.",
        },
    }
    destination = output / "report"
    if (destination / "MERGED_REPORT.json").exists():
        result["created"] = read(destination / "MERGED_REPORT.json")["created"]
    immutable(destination / "MERGED_REPORT.json", result)
    lines = [
        "# MagicBrush 无 mask 全量结果：八方法",
        "",
        "完整 535 会话、1,053 个独立编辑轮次；全部样本均纳入。",
        "",
        "新增 InstructPix2Pix 和 HIVE 使用官方原生 512 分辨率，其余六方法沿用冻结的约 1MP 配置；统一回源与五项评分。",
        "",
    ]
    for mode, title in [
        ("single-turn", "独立单轮：1,053 轮"),
        ("multi-turn", "连续多轮最终图：535 会话"),
    ]:
        panel = {r["model"]: r for r in result["rows"] if r["mode"] == mode}
        lines += [
            f"## {title}",
            "",
            "| 方法 | L1 ↓ | L2 ↓ | CLIP-I ↑ | DINO ↑ | CLIP-T ↑ |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for model in DISPLAY_MODELS:
            values = []
            for metric in METRICS:
                best = (min if metric in ("L1", "L2") else max)(
                    r["metrics"][metric] for r in panel.values()
                )
                value = panel[model]["metrics"][metric]
                cell = f"{value:.4f}"
                values.append(f"**{cell}**" if value == best else cell)
            lines.append("| " + DISPLAY_NAMES[model] + " | " + " | ".join(values) + " |")
        lines.append("")
    lines += [
        "L2 为均方误差，不开根号；相似度不是百分数。生成失败按既定规则赋 L1/L2=1、相似度=−1，全部计入分母。",
        "",
        "95% 区间、逐例贡献和可追溯来源见同目录 MERGED_REPORT.json；原始实验记录未改动。",
        "",
    ]
    path = destination / "MERGED_REPORT.md"
    if path.exists() and path.read_text() != "\n".join(lines):
        raise ValueError("Existing report text differs")
    path.write_text("\n".join(lines))
    return {"report": str(destination), "rows": len(result["rows"]), "methods": methods}


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(report(args.output), ensure_ascii=False, indent=2))
