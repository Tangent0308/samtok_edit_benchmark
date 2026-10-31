"""Strict 20-source fixed-protocol dev statistics and Markdown evidence.

This module reads existing outputs and effective canonical Judge records only.
Generation failures retain the complete denominator. Missing Judge scores remain
missing. There is no candidate search, score imputation, freeze or test action.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from samtok_benchmark.io import atomic_text, digest, sha256_file, write_json
from .fairness_dev_judge import (
    Cache,
    FAILURES,
    collect,
    load_plan,
    normalized_tasks,
    paths,
    read,
    resolve,
    validate_scores,
    verify_effective,
)

SEED = 20261027
REPLICATES = 10000


def quantiles(values):
    values = np.asarray(values)
    valid = np.isfinite(values)
    return {
        "CI95": np.quantile(values[valid], [0.025, 0.975]).tolist() if valid.any() else None,
        "valid_replicates": int(valid.sum()),
        "zero_denominator_replicates": int((~valid).sum()),
    }


class Bootstrap:
    def __init__(self, ks):
        self.ks = np.asarray(ks, dtype=int)
        self.indices = np.random.default_rng(SEED).integers(0, len(ks), (REPLICATES, len(ks)))
        self.k_indices = {}
        for k in range(2, 6):
            source = np.flatnonzero(self.ks == k)
            self.k_indices[k] = (
                (
                    source,
                    np.random.default_rng(SEED).choice(
                        source, (REPLICATES, len(source)), replace=True
                    ),
                )
                if len(source)
                else (source, None)
            )

    def rate(self, numerator, denominator, indices=None):
        ix = self.indices if indices is None else indices
        num = np.asarray(numerator)[ix].sum(1)
        den = np.asarray(denominator)[ix].sum(1)
        out = np.full(REPLICATES, np.nan)
        np.divide(num, den, out=out, where=den != 0)
        return out


def rates(up, jp, ks, unknown, boot, indices=None, selected=None):
    selected = np.arange(len(ks)) if selected is None else selected
    full = len(selected) > 0 and not np.any(unknown[selected])
    result = {
        "case_denominator": int(len(selected)),
        "unit_denominator": int(np.asarray(ks)[selected].sum()),
        "complete": bool(full),
        "missing_cases": int(unknown[selected].sum()),
        "UnitPass": float(up[selected].sum() / np.asarray(ks)[selected].sum()) if full else None,
        "JointPass": float(jp[selected].mean()) if full else None,
        "bootstrap": None,
    }
    distributions = {}
    if full:
        distributions = {
            "UnitPass": boot.rate(up, ks, indices),
            "JointPass": boot.rate(jp, np.ones(len(ks)), indices),
        }
        result["bootstrap"] = {name: quantiles(value) for name, value in distributions.items()}
    return result, distributions


def make_row(model, setting, context, bound, effective, boot):
    n = len(context["case_ids"])
    ks = boot.ks
    up, jp = np.zeros(n, dtype=int), np.zeros(n, dtype=int)
    unknown = np.zeros(n, dtype=bool)
    counts, proof = Counter(), []
    dimensions = {d: [] for d in ["E", "P", "Q", "global_P", "global_Q"]}
    applicable = []
    for i, cid in enumerate(context["case_ids"]):
        b = bound[model, setting, cid]
        status = b["generation_status"]
        key = b["judge_key"]
        score = None
        if status == "generated":
            judgment = effective.get(key)
            status = judgment["status"] if judgment else "judge-pending"
            if status == "scored":
                score = judgment["scores"]
                case = context["cases"][cid]
                validate_scores(score, [u["id"] for u in case["units"]])
                bits = [
                    u["E"]["score"] == 4 and u["P"]["score"] >= 3 and u["Q"]["score"] >= 3
                    for u in score["units"]
                ]
                up[i] = sum(bits)
                jp[i] = int(
                    all(bits)
                    and score["global_P"]["score"] >= 3
                    and score["global_Q"]["score"] >= 3
                )
                for d in "EPQ":
                    dimensions[d].extend(u[d]["score"] for u in score["units"])
                for d in ["global_P", "global_Q"]:
                    dimensions[d].append(score[d]["score"])
            else:
                unknown[i] = True
        elif status not in FAILURES:
            unknown[i] = True
        applicable.append(status != "not-applicable")
        counts[status] += 1
        proof.append(
            {
                "case_id": cid,
                "K": int(ks[i]),
                "task_key": b["key"],
                "judge_key": key,
                "status": status,
                "UnitPass_count": None if unknown[i] else int(up[i]),
                "JointPass": None if unknown[i] else int(jp[i]),
                "generation_record": b["result_path"],
                "generation_record_sha256": b.get("generation_record_sha256"),
            }
        )
    if any(applicable) and not all(applicable):
        raise ValueError("Per-case N/A cannot silently change a model-setting denominator")
    row, distributions = rates(up, jp, ks, unknown, boot)
    row.update(
        model=model,
        setting=setting,
        status_counts=dict(counts),
        not_applicable=not any(applicable),
        generation_failed_cases=sum(counts[k] for k in FAILURES),
        scored_cases=counts["scored"],
        scored_unit_denominator=sum(
            int(ks[i]) for i, p in enumerate(proof) if p["status"] == "scored"
        ),
        missing_units=int(ks[unknown].sum()),
        known_pass_units=int(up.sum()),
        known_joint_pass_cases=int(jp.sum()),
        per_case=proof,
        numeric_scores_among_scored_only={
            d: {
                "observed_denominator": len(v),
                "mean": float(np.mean(v)) if v else None,
                "histogram": dict(Counter(v)),
            }
            for d, v in dimensions.items()
        },
        by_K={},
    )
    for k, (selected, ix) in boot.k_indices.items():
        row["by_K"][str(k)], _ = rates(up, jp, ks, unknown, boot, ix, selected)
    return row, distributions


def derived(rows, distributions):
    definitions = [
        (f"Delta_lang_{m}", [f"S2-{m}", f"S3-{m}"], "difference") for m in ["point", "box", "mask"]
    ]
    definitions += [
        (f"G_region_{m}", [f"S2-{m}", "S1"], "difference") for m in ["point", "box", "mask"]
    ]
    definitions += [
        ("R_mod", ["S3-point", "S3-box", "S3-mask"], "ratio"),
        ("C_mix", ["S3-point", "S3-box", "S3-mask", "S4-noref"], "mix"),
    ]
    result = []
    for metric in ["UnitPass", "JointPass"]:
        for name, settings, kind in definitions:
            item = {
                "metric": metric,
                "diagnostic": name,
                "settings": settings,
                "value": None,
                "bootstrap": None,
                "unavailable_reason": None,
            }
            if any(rows[s][metric] is None for s in settings):
                item["unavailable_reason"] = (
                    "incomplete common full denominator; no subset substitution"
                )
            else:
                value = np.array([rows[s][metric] for s in settings])
                draws = np.array([distributions[s][metric] for s in settings])
                if kind == "difference":
                    point, dist = value[0] - value[1], draws[0] - draws[1]
                elif kind == "mix":
                    point, dist = value[:3].mean() - value[3], draws[:3].mean(0) - draws[3]
                else:
                    point = value.min() / value.max() if value.max() else None
                    dist = np.full(REPLICATES, np.nan)
                    np.divide(draws.min(0), draws.max(0), out=dist, where=draws.max(0) != 0)
                    if point is None:
                        item["unavailable_reason"] = "maximum modality rate is zero"
                item.update(
                    value=float(point) if point is not None else None, bootstrap=quantiles(dist)
                )
            result.append(item)
    return result


def source_view(request, call):
    for key in ["planner_image", "grounding_image"]:
        if request.get(key) and Path(request[key]).exists():
            return request[key]
    for data in [call, request]:
        for key in ["actual_source", "planner_image", "grounding_image", "image", "source_image"]:
            value = data.get(key)
            if isinstance(value, str) and Path(value).exists():
                return value
        if data.get("images"):
            images = data["images"]
            return images[1] if len(images) > 1 else images[0]
    return None


def example(context, task, binding, directory):
    cid = task["case_id"]
    case = context["cases"][cid]
    request_path = Path(task["request_path"]) if task.get("request_path") else None
    request = read(request_path) if request_path and request_path.exists() else {}
    result_path = Path(task["result_path"])
    call_path = result_path.with_name("call.json")
    result = read(result_path) if result_path.exists() else {}
    if not call_path.exists() and result.get("original_call"):
        call_path = Path(result["original_call"])
    call = read(call_path) if call_path.exists() else {}
    native = result.get("native_result", {})
    source = str(canonical_source(context, case))
    view = source_view(request, call) or source
    output = binding.get("output_image")
    figure = directory / "figures" / f"{task['model']}__{task['setting']}__{cid}.jpg"
    figure.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (1500, 450), "white")
    draw = ImageDraw.Draw(canvas)
    font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    font = (
        ImageFont.truetype(str(font_path), 16) if font_path.exists() else ImageFont.load_default()
    )
    draw.text(
        (8, 5),
        f"{task['model']} | {task['setting']} | {cid} | fixed first dev example",
        fill="black",
        font=font,
    )
    labels = [
        "Clean source",
        "Actual visual input; native regions in linked JSON",
        "Actual output" if output else binding["generation_status"],
    ]
    for i, (path, label) in enumerate(zip([source, view, output], labels)):
        draw.text((i * 500 + 7, 33), label, fill="black", font=font)
        if path and Path(path).exists():
            with Image.open(path) as image:
                thumb = ImageOps.contain(image.convert("RGB"), (490, 390))
            canvas.paste(
                thumb, (i * 500 + (500 - thumb.width) // 2, 56 + (390 - thumb.height) // 2)
            )
    canvas.save(figure, quality=89)
    prompt = call.get("prompt", request.get("prompt", request.get("global_original_prompt")))
    return {
        "model": task["model"],
        "setting": task["setting"],
        "case_id": cid,
        "figure": str(figure),
        "source": source,
        "actual_visual_input": view,
        "output": output,
        "prompt": prompt,
        "request_path": str(request_path) if request_path else None,
        "call_path": str(call_path) if call_path.exists() else None,
        "native_local_inputs": call.get(
            "sub_prompts", call.get("regions", call.get("actual_region_guidance"))
        ),
        "actual_editor_global_prompt": native.get(
            "global_prompt", result.get("actual_global_prompt")
        ),
        "actual_editor_region_guidance": native.get(
            "region_guidance", result.get("actual_region_guidance")
        ),
        "planner_inputs": {
            k: request[k]
            for k in ["parser_inputs", "grounding_hints", "planner_image", "grounding_image"]
            if k in request
        },
        "result_path": str(result_path) if result_path.exists() else None,
        "status": binding["generation_status"],
    }


def canonical_source(context, case):
    from .dev_judge import DATA

    return DATA / case["source"]["image"]


def calls_ledger(context):
    rows, planners_seen, planners, loads = [], set(), [], {}
    for task in normalized_tasks(context):
        path = Path(task["result_path"])
        result = read(path) if path.exists() else None
        if result:
            if result.get("load_record"):
                p = Path(result["load_record"])
                if p.exists():
                    loads[str(p)] = {"sha256": sha256_file(p), **read(p)}
            rows.append(
                {
                    "task_key": task["key"],
                    "status": result["status"],
                    "reused": bool(result.get("reused")),
                    "new_editor_api_calls": 0
                    if result.get("reused")
                    else result.get("inference_api_calls"),
                    "transformer_forward_calls": None
                    if result.get("reused")
                    else result.get("transformer_forward_calls"),
                    "wall_seconds": None
                    if result.get("reused")
                    else result.get("wall_seconds", result.get("seconds")),
                    "result": str(path),
                    "sha256": sha256_file(path),
                }
            )
        if task.get("planner_dir"):
            planner = resolve(task["planner_dir"], context["base"]) / "result.json"
            if planner.exists() and str(planner) not in planners_seen:
                planners_seen.add(str(planner))
                value = read(planner)
                if value.get("load_record"):
                    p = Path(value["load_record"])
                    if p.exists():
                        loads[str(p)] = {"sha256": sha256_file(p), **read(p)}
                counts = [
                    value[k]
                    for k in ["native_planner_calls", "extra_planner_api_calls"]
                    if value.get(k) is not None
                ]
                if len(set(counts)) > 1:
                    raise ValueError("Planner API alias counters disagree; do not sum or guess")
                planners.append(
                    {
                        "path": str(planner),
                        "sha256": sha256_file(planner),
                        "status": value["status"],
                        "reused": bool(value.get("reused")),
                        "new_api_calls": 0
                        if value.get("reused")
                        else counts[0]
                        if counts
                        else None,
                        "batch_items": value.get("extra_planner_batch_items"),
                        "wall_seconds": value.get("wall_seconds"),
                    }
                )
    judge_root, raws, effectives, admitted = paths(context)
    return {
        "editor_records": rows,
        "planner_records": planners,
        "worker_load_records_once": loads,
        "worker_load_seconds_sum_once": sum(v.get("seconds", 0) for v in loads.values()),
        "new_editor_api_calls_known": sum(r["new_editor_api_calls"] or 0 for r in rows),
        "unknown_editor_call_counts": sum(r["new_editor_api_calls"] is None for r in rows),
        "new_planner_api_calls_known": sum(r["new_api_calls"] or 0 for r in planners),
        "unknown_planner_call_counts": sum(r["new_api_calls"] is None for r in planners),
        "new_judge_admitted_calls": len(list(admitted.glob("*.json"))),
        "new_judge_raw_answers": len(list(raws.glob("*.json"))),
        "judge_execution_receipts": [
            str(p) for p in sorted((judge_root / "executions").glob("*/receipt.json"))
        ],
        "wall_seconds_are_per_request_records_not_total_gpu_utilization": True,
    }


def repair_history(context):
    """Keep failed historical compute distinct from this run's new calls."""
    records = []
    for task in context["plan"]["tasks"]:
        reference = task.get("repair_of")
        if not reference:
            continue
        if sha256_file(Path(reference["path"])) != reference["sha256"]:
            raise ValueError("Historical repair attempt changed")
        result = read(reference["path"])
        records.append({
            "key": task["key"], "original_attempt": reference,
            "status": result["status"], "error_type": result.get("error_type"),
            "inference_api_calls": result.get("inference_api_calls"),
            "transformer_forward_calls": result.get("transformer_forward_calls"),
            "wall_seconds": result.get("wall_seconds"),
        })
    return records


def show_rate(row, name):
    if row.get("not_applicable"):
        return "N/A"
    if row[name] is None:
        return "待完整评分"
    ci = row["bootstrap"][name]["CI95"]
    return f"{100 * row[name]:.2f}% [{100 * ci[0]:.2f}, {100 * ci[1]:.2f}]"


def input_route(model, setting):
    if model in {"qwen2511", "qwen21", "flux3", "flux2_klein9b"}:
        route = "清图＋公开prompt" if setting == "S1" else "清图＋共享标注图，prompt逐U绑定"
        return route + ("；boxes=None、PUP关" if model == "flux3" else "；无PE/改写器")
    if model == "replan":
        return (
            "清图" if setting == "S1" else "共享标注图"
        ) + "→原生planner，response原样→清图联合编辑"
    if model == "mirage":
        return (
            "每U原生parse保留全部pairs；"
            + ("清图" if setting == "S1" else "共享标注图＋公开hint")
            + "原生grounding→清图联合编辑"
        )
    if setting == "S1":
        return "单张清图＋global prompt，0区域实例"
    if setting.endswith("-point"):
        return "单张共享点标注图＋global prompt，0硬区域实例"
    if setting.endswith("-box"):
        return "单张清图＋原生normalized bbox/local prompt"
    if setting.endswith("-mask"):
        return "单张清图＋原生mask/local prompt"
    return "单图；有point用共享标注图；point/none→global，box/mask→原生区域local"


def setting_comparisons(report):
    """Present existing main rows by setting without recalculating any scores."""
    models, settings = report["model_order"], report["settings"]
    rows = {(row["model"], row["setting"]): row for row in report["rows"]}
    expected = {(model, setting) for model in models for setting in settings}
    if len(rows) != len(report["rows"]) or set(rows) != expected:
        raise ValueError("Model comparisons require exactly one main row per model and setting")
    names = {model: report["model_specifications"][model]["name"] for model in models}
    md = [
        "## 同一 setting 下的模型对比",
        "",
        f"以下仅比较已固定的主配置，共用同一批 {report['source_count']} 张源图、"
        f"{report['units_per_model_setting']} 个编辑单元。模型顺序沿用执行计划；"
        "S2丢弃区域补充行另列，不混入这些主结果。",
        "",
        "先分别展示两个通过率的总览；点击setting可跳转到含95%置信区间的七模型对比表。"
        "百分数与区间均直接引用既有统计，不重新评分或选择配置。",
        "",
    ]
    for metric in ("UnitPass", "JointPass"):
        md += [
            f"### {metric} 总览",
            "",
            "| Setting | " + " | ".join(names[model] for model in models) + " |",
            "|---|" + "---:|" * len(models),
        ]
        for setting in settings:
            values = [show_rate(rows[model, setting], metric).split(" [", 1)[0] for model in models]
            md.append(f"| [{setting}](#{setting.lower()}) | " + " | ".join(values) + " |")
        md.append("")
    md += [
        "各setting下的方括号为源图paired bootstrap的95%区间，端点单位也是百分比。"
        "生成/规划失败仍计入原分母；Judge缺分单列，不能当作0分。",
        "",
    ]
    for setting in settings:
        md += [
            f"### {setting}",
            "",
            "| 模型 | UnitPass [95% CI] | JointPass [95% CI] | 单元/源图分母 | 生成/规划失败 | Judge缺分源图 |",
            "|---|---|---|---:|---:|---:|",
        ]
        for model in models:
            row = rows[model, setting]
            md.append(
                f"| {names[model]} | {show_rate(row, 'UnitPass')} | {show_rate(row, 'JointPass')} | "
                f"{row['unit_denominator']}/{row['case_denominator']} | "
                f"{row['generation_failed_cases']} | {row['missing_cases']} |"
            )
        md.append("")
    return md


def markdown(report, directory):
    md = [
        "# IF-Bench：固定20图dev评测",
        "",
        "**UnitPass 是全部编辑单元的通过比例；JointPass 是同图全部单元及全局保护/质量同时通过的图片比例。方括号为95%置信区间。** 两者的分母分别是单元数和20张源图，不是两个Judge的分数。",
        "",
        "本轮每模型一套已批准的固定输入，不进行候选排名或选型。生成/规划失败保留在原分母；Judge缺分不补零，相关完整行和派生指标保留缺失。20图结果不冒称108图dev或正式test结果。",
        "",
        "| 做了什么 | 问题与偏差 | 阻塞项 | 下一步 |",
        "|---|---|---|---|",
        f"| 已生成{report['generation_counts'].get('generated', 0)}个逻辑输出；完整统计行{sum(r['complete'] for r in report['rows'])}/{len(report['rows'])} | 原生失败及评分缺分见逐行账本；不人为补分 | {'无评分缺失' if report['ready_for_review'] else '尚有生成/评分待完成或Judge缺分'} | 汇报固定方案完整20图结果，停在用户确认门；不自动freeze/test |",
        "",
    ]
    if report.get("protocol_revision"):
        md += [
            f"协议版本：`{report['protocol_revision']}`。Qwen2.1 使用2K；MICE使用已批准短前导及原生200-token完整性检查。未变请求精确复用，历史原生失败保留；不把复用当作新推理。",
            "",
        ]
    if report.get("repair_parent"):
        md += [
            "本报告属于单独的工程修复运行：Qwen2.1 原 23 个成功输出经输入/权重/采样参数逐项核验后复用，保留其 resident 来源；原 177 个终止于 VAE 解码的 OOM 请求使用原生 `model_cpu_offload` 重新执行。2K、40步、CFG=1、KV cache、BF16、seed42及公开输入保持原值。两张工程诊断输出不进入本报告。其他六模型原输出/原生失败和已有 Judge 分数精确复用。",
            "",
            "旧177次失败已经完成去噪，不是零成本；原 attempt 的调用、forward及耗时保留在 `REPORT.json` 的 `repair_history`，不与本轮新增调用混算，也不从旧/新输出中按分数择优。",
            "",
        ]
    md += setting_comparisons(report)
    md += [
        "## 按模型列出的完整分数与输入方式",
        "",
        "| 模型 | Setting | UnitPass [95% CI] | JointPass [95% CI] | 单元/源图分母 | 生成失败/缺分源图 | 实际输入方式 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in report["rows"]:
        md.append(
            f"| {row['model']} | {row['setting']} | {show_rate(row, 'UnitPass')} | {show_rate(row, 'JointPass')} | {row['unit_denominator']}/{row['case_denominator']} | {row['generation_failed_cases']}/{row['missing_cases']} | {input_route(row['model'], row['setting'])} |"
        )
    md += [
        "",
        "置信区间使用源图cluster的paired bootstrap：所有模型/setting共享抽样索引，seed=20261027、10000次、percentile 95%。K桶在桶内按图抽样；UnitPass每次重新按抽中的单元总数计算。完整原始评分、有效overlay、输出SHA与逐case证据在JSON，不使用部分子集代替完整分母。",
        "",
        f"实际选中 {report['source_count']} 张源图、每行 {report['units_per_model_setting']} 个单元；K分布 {json.dumps(report['K_counts'], ensure_ascii=False)}。同setting使用同一份公开输入；原生planner得到的框是该方法的内部预测，不是新增GT。",
        "",
        "## 固定参数、权重与组件",
        "",
        "| 模型 | 固定参数 | 方法commit / 权重revision | 原生组件 |",
        "|---|---|---|---|",
    ]
    for model in report["model_order"]:
        spec = report["model_specifications"][model]
        params = {
            k: spec[k]
            for k in ["parameters", "planner_defaults", "attention_defaults", "negative_prompt", "execution"]
            if k in spec
        }
        revisions = f"代码 `{spec['method_commit']}`；权重 `{spec['weight_revision']}`"
        if spec.get("planner_weight_revision"):
            revisions += f"；planner `{spec['planner_weight_revision']}`"
        md.append(
            f"| {model} | `{json.dumps(params, ensure_ascii=False)}`；seed42 | {revisions} | "
            + "；".join(spec["components"])
            + " |"
        )
    md += [
        "",
        "全部主配置关闭外加SAM、grounder、caption转换、PE/PUP。RePlan/MIRAGE的命名方法本身包含原生VLM规划，它们的调用单独记录；不能把完整方法成绩称为裸骨干成绩。FLUX3实际请求还固定safety=False；完整逐case配置以已校验请求为准。",
        "",
        "## S2丢弃区域补充（exact S1 reuse）",
        "",
        "按已确认协议单列S1输入/输出及其评分的精确别名，不增加模型或Judge调用，不进入70条主行，不进行搜索或按分数替换主输入。S1缺分时补充行也缺分。",
        "",
        "| 模型 | S2补充setting | UnitPass [95% CI] | JointPass [95% CI] | 来源 |",
        "|---|---|---|---|---|",
    ]
    for row in report["s2_discard_supplement"]:
        md.append(
            f"| {row['model']} | {row['setting']} / discard-region | {show_rate(row, 'UnitPass')} | {show_rate(row, 'JointPass')} | exact S1 reuse |"
        )
    md += ["", "## 派生指标", "", "| 模型 | 口径 | 指标 | 值 [95% CI] |", "|---|---|---|---|"]
    for model, values in report["derived"].items():
        for value in values:
            if value["value"] is None:
                shown = (
                    "待完整评分"
                    if value["unavailable_reason"].startswith("incomplete")
                    else "N/A：" + str(value["unavailable_reason"])
                )
            else:
                ci = value["bootstrap"]["CI95"]
                shown = f"{value['value']:.4f} [{ci[0]:.4f}, {ci[1]:.4f}]"
            md.append(f"| {model} | {value['metric']} | {value['diagnostic']} | {shown} |")
    md += [
        "",
        "Δ_lang=S2−S3；G_region=S2−S1；R_mod=min(S3三模态)/max(S3三模态)；C_mix=三模态S3均值−S4-noref。差值以比例点表示，形式鲁棒性为比值。max=0时R_mod为N/A。setting差值包含原生预处理/路由差异，不应解读为纯因果效应。",
        "",
        "## 按目标数K分桶的JointPass",
        "",
        "| 模型 | Setting | K2 | K3 | K4 | K5 |",
        "|---|---|---|---|---|---|",
    ]
    for row in report["rows"]:
        values = []
        for k in range(2, 6):
            bucket = row["by_K"][str(k)]
            if bucket["case_denominator"] == 0:
                values.append("N/A（0图）")
            elif bucket["JointPass"] is None:
                values.append(f"缺分（{bucket['case_denominator']}图）")
            else:
                ci = bucket["bootstrap"]["JointPass"]["CI95"]
                values.append(
                    f"{100 * bucket['JointPass']:.1f}% [{100 * ci[0]:.1f},{100 * ci[1]:.1f}] n={bucket['case_denominator']}"
                )
        md.append(f"| {row['model']} | {row['setting']} | " + " | ".join(values) + " |")
    md += [
        "",
        "## 实际输入、输出与最终prompt",
        "",
        "每模型×setting固定展示plan内第一张源图；不按输出优劣换例。左清图、中实际视觉输入、右输出；原生box/mask/local字段同时保存于调用JSON。失败例保留失败状态。此图册不是尚待完成的正式随机10例人工抽检。",
        "",
    ]
    for row in report["examples"]:
        image = Path(row["figure"]).relative_to(directory)
        md += [
            f"### {row['model']} / {row['setting']} / {row['case_id']}",
            "",
            f"![真实输入输出]({image})",
            "",
            "```text",
            row["prompt"] if row["prompt"] is not None else "实际prompt尚未落盘；见请求JSON。",
            "```",
            "",
        ]
        if (
            row["native_local_inputs"] is not None
            or row["planner_inputs"]
            or row["actual_editor_region_guidance"] is not None
        ):
            md += [
                "```json",
                json.dumps(
                    {
                        k: row[k]
                        for k in [
                            "native_local_inputs",
                            "planner_inputs",
                            "actual_editor_global_prompt",
                            "actual_editor_region_guidance",
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "```",
                "",
            ]
        if isinstance(row["native_local_inputs"], list):
            for region in row["native_local_inputs"]:
                if isinstance(region, dict) and region.get("latent_mask"):
                    mask = Path(region["latent_mask"])
                    if not mask.exists() or (
                        region.get("sha256") and sha256_file(mask) != region["sha256"]
                    ):
                        raise ValueError("Actual native binding mask is missing or changed")
                    md += [
                        f"实际原生区域输入 {region.get('unit_id', '')}（模型网格分辨率的二值mask）：",
                        "",
                        f"![实际native mask]({mask})",
                        "",
                    ]
        md += [
            f"[实际请求]({row['request_path']})"
            + (
                f" · [原始结果]({row['result_path']})"
                if row["result_path"]
                else " · 原始结果待落盘"
            )
            + (f" · [实际调用]({row['call_path']})" if row["call_path"] else ""),
            "",
        ]
    ledger = report["calls"]
    md += [
        "## 计算账本与未完成交付",
        "",
        f"已记录新编辑API {ledger['new_editor_api_calls_known']} 次，调用数未知的编辑记录 {ledger['unknown_editor_call_counts']} 份；新原生规划API {ledger['new_planner_api_calls_known']} 次；本轮Judge已admitted {ledger['new_judge_admitted_calls']} 次、保存raw {ledger['new_judge_raw_answers']} 份。复用旧分数不增加调用。完整逐项调用/forward/耗时及Judge执行receipt见 [REPORT.json](REPORT.json)。这些逐请求耗时不能冒称总墙钟或完整GPU利用率。",
        "",
        "尚未完成或不在本轮：两名独立人工残留审查与Cohen κ、正式随机10例抽检、GT selector paste-back诊断、另行登记的消融、正式freeze/test。不得把本脚本生成的图册当成人工质量评分。没有外接†/‡/§增强新行；旧增强系统结果继续只保留历史。",
        "",
    ]
    return "\n".join(md)


def run(plan, root=None):
    context = load_plan(plan, root)
    directory = context["root"] / "report"
    directory.mkdir(parents=True, exist_ok=True)
    bindings, jobs = collect(context)
    _, _, effective_root, _ = paths(context)
    cache_path = context["plan"].get("cache_index", context["plan"].get("judge_cache_index"))
    cache = Cache(resolve(cache_path, context["base"]) if cache_path else None, context["config"])
    if (
        context["plan"].get("cache_index_sha256")
        and cache.index_sha256 != context["plan"]["cache_index_sha256"]
    ):
        raise ValueError("Historical Judge index changed from the fixed plan")
    effective = {}
    for key, job in jobs.items():
        path = effective_root / f"{key}.json"
        if path.exists():
            value = read(path)
            verify_effective(value, job, context, cache)
            effective[key] = value
    bound = {(b["model"], b["setting"], b["case_id"]): b for b in bindings}
    boot = Bootstrap([len(context["cases"][cid]["units"]) for cid in context["case_ids"]])
    rows, derived_values = [], {}
    for model in context["order"]:
        model_rows, model_dist = {}, {}
        for setting in context["plan"]["settings"]:
            row, dist = make_row(model, setting, context, bound, effective, boot)
            rows.append(row)
            model_rows[setting] = row
            model_dist[setting] = dist
        derived_values[model] = derived(model_rows, model_dist)
    examples = []
    for task in normalized_tasks(context):
        if task["case_id"] == context["case_ids"][0]:
            examples.append(
                example(
                    context, task, bound[task["model"], task["setting"], task["case_id"]], directory
                )
            )
    discard = []
    for row in rows:
        if row["setting"] == "S1":
            for setting in ["S2-point", "S2-box", "S2-mask"]:
                discard.append(
                    {
                        **row,
                        "setting": setting,
                        "role": "supplement-only",
                        "source_setting": "S1",
                        "input_policy": "discard-region; exact S1 input/output/Judge reuse",
                        "new_editor_calls": 0,
                        "new_judge_calls": 0,
                        "selection_performed": False,
                    }
                )
    report = {
        "schema": "ifbench-fixed-dev20-report-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "plan_digest": context["plan"].get("digest"),
        "plan_sha256": context["plan_sha256"],
        "protocol_revision": context["plan"].get("protocol_revision"),
        "parent_run": context["plan"].get("parent_run"),
        "repair_parent": context["plan"].get("repair_parent"),
        "repair_history": repair_history(context),
        "run_id": context["run_id"],
        "case_ids": context["case_ids"],
        "model_order": context["order"],
        "settings": context["plan"]["settings"],
        "model_specifications": context["plan"]["model_specifications"],
        "K_counts": dict(Counter(map(int, boot.ks))),
        "source_count": len(context["case_ids"]),
        "units_per_model_setting": int(boot.ks.sum()),
        "generation_counts": dict(Counter(b["generation_status"] for b in bindings)),
        "rows": rows,
        "derived": derived_values,
        "s2_discard_supplement": discard,
        "bootstrap": {
            "seed": SEED,
            "replicates": REPLICATES,
            "cluster": "source image",
            "shared_indices_sha256": digest(boot.indices.tolist()),
            "CI": "percentile .025/.975",
            "K_buckets": "within-bucket source-image resampling",
        },
        "judge_config": context["config"],
        "calls": calls_ledger(context),
        "examples": examples,
        "judge_bindings": {
            "unique_output_keys": len(jobs),
            "effective_statuses": dict(Counter(v["status"] for v in effective.values())),
            "historical_cache_reused_keys": sum("cache_reuse" in v for v in effective.values()),
            "new_deterministic_repair_keys": sum(
                v.get("deterministic_repair_used", False) and "cache_reuse" not in v
                for v in effective.values()
            ),
        },
        "ready_for_review": all(row["complete"] or row["not_applicable"] for row in rows),
        "candidate_selection": None,
        "frozen": False,
        "test_started": False,
        "model_calls_by_report": 0,
        "human_kappa": None,
        "population_marker_residual_rate": None,
        "pasteback_diagnostic": "not executed",
    }
    write_json(directory / "REPORT.json", report)
    atomic_text(directory / "REPORT.md", markdown(report, directory))
    return {
        "report": str(directory / "REPORT.md"),
        "complete_rows": sum(r["complete"] for r in rows),
        "rows": len(rows),
        "ready_for_review": report["ready_for_review"],
        "model_calls": 0,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--root", type=Path)
    a = p.parse_args()
    print(json.dumps(run(a.plan, a.root), ensure_ascii=False), flush=True)
