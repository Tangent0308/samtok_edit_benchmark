"""Summarize complete repeated measurements; never manufacture latency or quality."""

from collections import Counter
from pathlib import Path
import statistics

from .common import load_plan, read, result_dir, save, stages


def summarize(records):
    complete = [r for r in records if r.get("status") == "completed"]
    values = [r["warm_stage_sum_seconds"] for r in complete]
    stage_names = sorted({s for r in complete for s in r["stage_seconds"]})
    return {
        "requests": len(records),
        "completed": len(complete),
        "statuses": dict(Counter(r["status"] for r in records)),
        "warm_stage_sum_mean_seconds": statistics.mean(values) if values else None,
        "warm_stage_sum_median_seconds": statistics.median(values) if values else None,
        "active_stage_peak_allocated_gib_max": max(
            (r["peak_allocated_bytes"] for r in complete), default=0
        )
        / 2**30
        if complete
        else None,
        "denoising_evaluations_mean": statistics.mean(r["denoising_evaluations"] for r in complete)
        if complete
        else None,
        "stage_mean_seconds": {
            s: statistics.mean(r["stage_seconds"][s] for r in complete) for s in stage_names
        },
        "denoising_count_sources": dict(Counter(r["denoising_count_source"] for r in complete)),
        "repeat_rgb_mismatches": sum(not r["repeat_rgb_identical"] for r in complete),
        "end_to_end_latency_seconds": None,
    }


def report(plan, output):
    profile = load_plan(plan)
    root = Path(output)
    per_case, all_terminal, diagnostics = [], True, []
    for model in profile["models"]:
        for request in profile["requests"]:
            repeats = []
            for rep in range(profile["repetitions"]):
                records = []
                for stage in stages(model):
                    path = (
                        result_dir(root, model, request["setting"], stage, request["case_id"], rep)
                        / "result.json"
                    )
                    if path.exists():
                        record = read(path)
                        if record["identity"]["plan_digest"] != profile["digest"]:
                            raise ValueError("Measurement comes from a different plan")
                        records.append(record)
                        for field in ("reference_rgb_equal", "reference_tokens_equal"):
                            if record.get(field) is False:
                                diagnostics.append({"type": field, "record": str(path)})
                        if record.get("reference_check_error"):
                            diagnostics.append(
                                {
                                    "type": "reference_check_error",
                                    "record": str(path),
                                    "error": record["reference_check_error"],
                                }
                            )
                    else:
                        all_terminal = False
                if len(records) != len(stages(model)):
                    repeats.append({"status": "pending"})
                elif any(r["status"] != "completed" for r in records):
                    repeats.append({"status": "failed", "stages": records})
                else:
                    last = records[-1]
                    calls = last["calls"]
                    repeats.append(
                        {
                            "status": "completed",
                            "stages": records,
                            "warm_stage_sum_seconds": sum(r["native_seconds"] for r in records),
                            "peak_allocated_bytes": max(r["peak_allocated_bytes"] for r in records),
                            "peak_reserved_bytes": max(r["peak_reserved_bytes"] for r in records),
                            "denoising_evaluations": calls.get(
                                "transformer_forward_calls", calls.get("expected_dit_forwards", 0)
                            ),
                            "denoising_count_source": "forward_hook"
                            if "transformer_forward_calls" in calls
                            else "frozen_loop_expected_count",
                            "stage_seconds": {
                                stage: r["native_seconds"]
                                for stage, r in zip(stages(model), records)
                            },
                            "raw_rgb_sha256": last.get("raw_rgb_sha256"),
                        }
                    )
            item = {
                "model": model,
                "setting": request["setting"],
                "case_id": request["case_id"],
                "K": request["units"],
                "repeats": repeats,
                "status": "incomplete",
            }
            if all(r["status"] == "completed" for r in repeats):
                item.update(
                    status="completed",
                    warm_stage_sum_seconds=statistics.median(
                        r["warm_stage_sum_seconds"] for r in repeats
                    ),
                    peak_allocated_bytes=max(r["peak_allocated_bytes"] for r in repeats),
                    denoising_evaluations=statistics.mean(
                        r["denoising_evaluations"] for r in repeats
                    ),
                    denoising_count_source=repeats[0]["denoising_count_source"],
                    stage_seconds={
                        s: statistics.median(r["stage_seconds"][s] for r in repeats)
                        for s in stages(model)
                    },
                    repeat_rgb_identical=len({r["raw_rgb_sha256"] for r in repeats}) == 1,
                )
            elif any(r["status"] == "failed" for r in repeats):
                item["status"] = "failed"
            per_case.append(item)
            if item.get("repeat_rgb_identical") is False:
                diagnostics.append(
                    {
                        "type": "repeat_rgb_mismatch",
                        "model": model,
                        "setting": request["setting"],
                        "case_id": request["case_id"],
                    }
                )
    rows = []
    for model in profile["models"]:
        for setting in profile["settings"]:
            selected = [r for r in per_case if r["model"] == model and r["setting"] == setting]
            rows.append(
                {
                    "model": model,
                    "setting": setting,
                    **summarize(selected),
                    "by_K": {
                        str(k): summarize([r for r in selected if r["K"] == k]) for k in range(2, 6)
                    },
                }
            )
    value = {
        "schema": "ifbench.inference-cost.report.v1",
        "complete": all_terminal,
        "plan_digest": profile["digest"],
        "rows": rows,
        "per_case": per_case,
        "timing_definition": profile["timing_definition"],
        "memory_definition": profile["memory_definition"],
        "aggregation": "Median of three repetitions per source, then mean/median across sources; all three must complete.",
        "quality_scores_changed": False,
        "end_to_end_measured": False,
        "review_required": bool(diagnostics),
        "diagnostics": diagnostics,
    }
    # Additional matched-cohort comparison; never hide the original coverage.
    paired_rows = []
    for setting in profile["settings"]:
        usable = set.intersection(
            *[
                {
                    r["case_id"]
                    for r in per_case
                    if r["model"] == model
                    and r["setting"] == setting
                    and r["status"] == "completed"
                }
                for model in profile["models"]
            ]
        )
        for model in profile["models"]:
            selected = [
                r
                for r in per_case
                if r["model"] == model and r["setting"] == setting and r["case_id"] in usable
            ]
            paired_rows.append(
                {
                    "model": model,
                    "setting": setting,
                    "case_ids": sorted(usable),
                    **summarize(selected),
                }
            )
    value["paired_complete_rows"] = paired_rows
    worker_records = []
    for path in sorted((root / "attempts").glob("*/*/worker-*.json")):
        record = read(path)
        worker_records.append(
            {
                "path": str(path),
                "model": record.get("model"),
                "setting": record.get("setting"),
                "stage": record.get("stage"),
                "load_seconds": record.get("load_seconds"),
                "worker_wall_seconds": record.get("worker_wall_seconds"),
                "status": record.get("status"),
            }
        )
    value["worker_accounting"] = worker_records
    if profile.get("unified_execution"):
        value["execution_control"] = profile["unified_execution"]
        value["quality_result_reuse"] = False
        value["quality_review_required"] = True
        value["implementation_validations"] = [
            {"path": str(p), **read(p)}
            for p in sorted((root / "attempts").glob("*/*/VALIDATION-*.json"))
        ]
    save(root / "REPORT.json", value)
    text = [
        "# IF-Bench 推理开销",
        "",
        "当前指标是各阶段已加载模型的同步耗时之和，不是实测端到端响应时间。",
        "每个源图先取三次重复的中位数，再在源图间统计。失败或未完成请求另记，不混入成功耗时。",
        (
            "本补测所有编辑器的前向次数均由实际 forward hook 记录；次数不等同于 FLOPs。"
            if profile.get("unified_execution")
            else "SITEdit 前向次数沿用冻结去噪循环的计数公式；其余方法读取原生 wrapper 的前向 hook。次数不等同于 FLOPs。"
        ),
        "",
        "| 方法 | Setting | 完整请求 | 定位／规划（秒） | 编辑（秒） | 阶段耗时和（秒）↓ | 单阶段峰值显存（GiB）↓ | 去噪前向次数 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]

    def fmt(v):
        return "待测" if v is None else f"{v:.3f}"

    for r in rows:
        text.append(
            f"| {r['model']} | {r['setting']} | {r['completed']}/{r['requests']} | "
            f"{fmt(r['stage_mean_seconds'].get('planner', r['stage_mean_seconds'].get('tokens', 0)))} | "
            f"{fmt(r['stage_mean_seconds'].get('edit'))} | "
            f"{fmt(r['warm_stage_sum_mean_seconds'])} | {fmt(r['active_stage_peak_allocated_gib_max'])} | "
            f"{fmt(r['denoising_evaluations_mean'])} |"
        )
    text += [
        "",
        "K=2…5 的分桶结果与逐次记录见同目录 REPORT.json。原始分数和模型输出未被修改。",
        f"输出／token 一致性待检查项：{len(diagnostics)}；详见 diagnostics。",
        "共同完成的配对耗时表见 paired_complete_rows；加载和 worker 占用时长见 worker_accounting。",
        "",
    ]
    if profile.get("unified_execution"):
        text += [
            "本表为统一 Diffusers／GPU 驻留的执行变体；专用区域注意力和规划流程保持原生。",
            "Qwen/SITEdit 使用相同的 DiT 注意力实现和原始文本特征提取；SITEdit 保留原生区域码、LoRA、CodeInjector 和 guidance。",
            "实现检查通过不等于质量等价；变更后端产生的新输出不能直接继承原质量分数。",
            "阶段耗时之和仍不是冷启动或端到端响应时间。",
            "",
        ]
    (root / "REPORT.md").write_text("\n".join(text))
    plot(rows, root / "COST_VS_K.svg")
    return value


def plot(rows, destination):
    """Standalone SVG from observed summaries only; no plotting dependency."""
    import html

    models = list(dict.fromkeys(r["model"] for r in rows))
    colors = ["#0072b2", "#d55e00", "#009e73", "#cc79a7", "#000000"]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="420" viewBox="0 0 1000 420">',
        '<rect width="1000" height="420" fill="white"/>',
        '<g font-family="Arial,sans-serif" font-size="14" fill="#222">',
        '<text x="30" y="25">Warm stage sum (seconds); five fixed sources per K</text>',
    ]
    for panel, setting in enumerate(dict.fromkeys(r["setting"] for r in rows)):
        offset = 75 + panel * 490
        selected = [r for r in rows if r["setting"] == setting]
        values = [
            v["warm_stage_sum_mean_seconds"]
            for r in selected
            for v in r["by_K"].values()
            if v["warm_stage_sum_mean_seconds"] is not None
        ]
        high = max(values, default=1) * 1.1 or 1
        parts.append(f'<text x="{offset + 140}" y="55">{html.escape(setting)}</text>')
        for tick in range(5):
            y = 325 - tick * 60
            parts.append(
                f'<line x1="{offset}" y1="{y}" x2="{offset + 360}" y2="{y}" stroke="#ddd"/>'
            )
            parts.append(
                f'<text x="{offset - 12}" y="{y + 5}" text-anchor="end">{high * tick / 4:.0f}</text>'
            )
        for i, k in enumerate(range(2, 6)):
            parts.append(f'<text x="{offset + i * 120}" y="350" text-anchor="middle">K={k}</text>')
        for r in selected:
            color = colors[models.index(r["model"]) % len(colors)]
            coordinates = []
            for k, v in r["by_K"].items():
                if v["warm_stage_sum_mean_seconds"] is None:
                    continue
                x = offset + (int(k) - 2) * 120
                y = 325 - v["warm_stage_sum_mean_seconds"] / high * 240
                coordinates.append(f"{x},{y:.2f}")
                parts.append(f'<circle cx="{x}" cy="{y:.2f}" r="4" fill="{color}"/>')
            if len(coordinates) > 1:
                parts.append(
                    f'<polyline points="{" ".join(coordinates)}" fill="none" stroke="{color}" stroke-width="2"/>'
                )
    for i, model in enumerate(models):
        x = 35 + i * 190
        parts.append(f'<circle cx="{x}" cy="390" r="5" fill="{colors[i % len(colors)]}"/>')
        parts.append(f'<text x="{x + 12}" y="395">{html.escape(model)}</text>')
    parts.append("</g></svg>")
    Path(destination).write_text("\n".join(parts))
