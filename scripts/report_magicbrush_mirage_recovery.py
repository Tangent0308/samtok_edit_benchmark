#!/usr/bin/env python3
"""Produce the requested six-method comparison from verified, immutable measured reports."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from samtok_benchmark.external_magicbrush.data import immutable, read
from samtok_benchmark.postprocessing.magicbrush_mirage_recovery import (
    METRICS,
    NAS,
    check,
    proof,
    verify_manifest,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    root = args.root
    manifest, _ = verify_manifest(root)
    latest = read(root / "REPORT.json")
    parent = NAS / "experiments2/SAMTokEdit/external_magicbrush"
    baselines_path = parent / "magicbrush_paper_20261107/report/MERGED_REPORT.json"
    ours_path = parent / "r2_20261110/REPORT.json"
    baselines, ours = read(baselines_path), read(ours_path)
    indices = latest["bootstrap"]["indices_sha256"]
    if indices != ours["bootstrap"]["indices_sha256"]:
        raise ValueError("Latest SITEdit and MIRAGE bootstrap indices differ")
    rows = []
    names = [
        ("instructpix2pix_magicbrush", "InstructPix2Pix-MagicBrush"),
        ("qwen21", "Qwen-Image-2.1"),
        ("replan", "RePlan"),
        ("mirage", "MIRAGE"),
        ("mice", "MICE"),
        ("sitedit", "SITEdit（最终版本）"),
    ]
    for model, label in names:
        if model == "mirage":
            row = {
                "metrics": {m: latest["metrics"][m]["mean"] for m in METRICS},
                "CI95": {m: latest["metrics"][m]["CI95"] for m in METRICS},
                "source": proof(root / "REPORT.json"),
            }
        elif model == "sitedit":
            row = {
                "metrics": ours["rows"]["R2_1000"]["metrics"],
                "CI95": ours["rows"]["R2_1000"]["CI95"],
                "source": proof(ours_path),
            }
        else:
            original = next(
                r
                for r in baselines["rows"]
                if r["model"] == model
                and r["subset"] == "full"
                and r["track"] == "mask-free"
                and r["mode"] == "single-turn"
            )
            if not original["complete"] or original["target_count"] != 1053:
                raise ValueError("Baseline row is not complete full single-turn")
            row = {
                "metrics": original["metrics"],
                "CI95": original["CI95"],
                "source": proof(baselines_path),
            }
        rows.append({"model": model, "name": label, "requests": 1053, **row})
    stages = {}
    for stage in ("plan", "edit", "score"):
        records = [read(root / stage / i["case_id"] / "result.json") for i in manifest["items"]]
        stages[stage] = {
            "counts": dict(Counter(r["status"] for r in records)),
            "measured_request_gpu_hours": sum(r.get("seconds", 0) for r in records) / 3600,
            "peak_allocated_gib": max(r.get("peak_allocated_bytes", 0) for r in records) / 2**30,
            "additional_vlm_calls": sum(
                r.get("native", {}).get("additional_vlm_calls", 0) for r in records
            ),
        }
    # Recheck all merged score receipts before publishing the comparison.
    for row in latest["per_case"]:
        check(row["score_record"])
    result = {
        "setting": "mask-free independent single-turn",
        "requests": 1053,
        "sessions": 535,
        "rows": rows,
        "recovery_costs": stages,
        "coverage": latest["coverage"],
        "bootstrap_indices_sha256": indices,
        "scope_note": "MIRAGE: original successful outputs plus the fixed native-VLM recovery policy; other rows unchanged",
        "script": proof(Path(__file__).resolve()),
    }
    immutable(root / "COMPARISON.json", result)
    lines = [
        "# MagicBrush：无 mask 独立单轮",
        "",
        "全部 1,053 请求、535 会话；SITEdit 使用最终 R2@1000。",
        "",
        "| 方法 | L1 ↓ | L2 ↓ | CLIP-I ↑ | DINO ↑ | CLIP-T ↑ |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| "
            + row["name"]
            + " | "
            + " | ".join(f"{row['metrics'][m]:.4f}" for m in METRICS)
            + " |"
        )
    lines.extend(
        [
            "",
            "MIRAGE 使用原生 Qwen3.5-9B 的固定条件式规划恢复，原编辑器、权重和评分器不变。原 915 张成功输出保留，138 条原失败全部进入恢复清单。没有按输出或分数选样。",
            "",
            "恢复覆盖：`"
            + json.dumps(latest["coverage"], ensure_ascii=False)
            + "`。逐图来源和 95% 会话级 bootstrap 区间见 `REPORT.json` / `COMPARISON.json`。",
            "",
            "成本为本轮逐请求实测 GPU 时间，不含加载／排队时间；原尝试和冒烟成本另存原始目录。",
            "",
            "| 阶段 | 计数 | GPU·h | 峰值 allocated / GiB | 额外 VLM 调用 |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for stage, stats in stages.items():
        lines.append(
            f"| {stage} | {stats['counts']} | {stats['measured_request_gpu_hours']:.4f} | {stats['peak_allocated_gib']:.2f} | {stats['additional_vlm_calls']} |"
        )
    lines.extend(
        [
            "",
            "完整协议与额外调用说明：仓库 `docs/MAGICBRUSH_MIRAGE_RECOVERY.md`。旧结果、旧失败、已有其他方法结果均未覆盖。",
            "",
        ]
    )
    text = "\n".join(lines)
    target = root / "COMPARISON.md"
    if target.exists() and target.read_text() != text:
        raise ValueError("Refusing to replace an existing comparison")
    if not target.exists():
        target.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
