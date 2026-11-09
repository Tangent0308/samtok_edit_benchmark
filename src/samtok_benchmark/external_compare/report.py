"""Compare native scores on exactly the same fixed cohort, with read-only provenance checks."""

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import csv
import hashlib
import io
from pathlib import Path
import statistics

import numpy as np

from samtok_benchmark.external_full.data import immutable, read
from samtok_benchmark.external_full.worker import scientific_config, stages
from samtok_benchmark.external_full.metrics import WEIGHTS
from samtok_benchmark.external_pair.statistics import (
    SEED,
    LOWER,
    aggregate,
    endpoints,
    finite,
    interval,
    task,
)
from samtok_benchmark.io import digest, sha256_file
from . import REUSED
from .plan import checked, verify_selection

NAMES = {
    "sitedit": "SITEdit",
    "qwen21": "Qwen-Image-2.1",
    "mice": "MICE",
    "flux2_klein9b": "FLUX.2 Klein-9B",
    "replan": "RePlan",
}
BENCH_NAMES = {"compbench": "CompBench", "interedit": "Inter-Edit", "omni_iie": "Omni IIE"}
GROUP_NAMES = {
    "all": "整体",
    "task/low": "Low",
    "task/high": "High",
    "Local Editing": "单目标局部编辑",
    "Multi-object Editing": "多目标编辑",
    "Implicit Reasoning": "隐式指令",
    "Multi-turn (Turn 1)": "连续编辑第 1 轮",
    "Multi-turn (Turn 2)": "连续编辑第 2 轮",
}


def audit(selection, plan, native):
    """Bind every reused/new stage and score to the same code, config and selected case."""
    models = selection["models"]
    wanted = set(selection["case_ids"])
    if set(native["models"]) != set(models) or set(native["case_ids"]) != wanted:
        raise ValueError("Native report has a different model/case population")
    if len(native["per_case"]) != len(models) * len(wanted):
        raise ValueError("Missing/duplicate native report rows")
    if len({(r["model"], r["case_id"]) for r in native["per_case"]}) != len(native["per_case"]):
        raise ValueError("Duplicate per-case rows")
    cfg = read(selection["configuration"])
    config_digest = digest(scientific_config(cfg))
    base = Path(selection["results_root"])
    original = Path(selection["reused_results_root"])
    private = {r["case_id"]: r for r in read(Path(selection["bundle"]) / "private/evaluation.json")}
    reference_score = read(
        original / "scores" / REUSED[0] / selection["case_ids"][0] / "local.json"
    )
    reference_implementation = reference_score["identity"]["implementation"]
    for section in ("run", "scores"):
        for model in REUSED:
            if (base / section / model).resolve() != (original / section / model).resolve():
                raise ValueError("Reused model directory no longer resolves to original records")
    invalid = set(selection.get("data_invalid_case_ids", []))

    def inspect(job):
        model, stage, cid = job
        path = base / "run" / model / stage / cid / "result.json"
        if cid in invalid:
            if path.exists():
                raise ValueError("Inference exists for an invalid public input")
            return {"model": model, "stage": stage, "case_id": cid, "status": "data_input_invalid"}
        record = read(path)
        identity = record["identity"]
        if identity["digest"] != digest({k: v for k, v in identity.items() if k != "digest"}):
            raise ValueError("Generation identity digest changed")
        if any(
            identity[k] != v
            for k, v in {
                "model": model,
                "stage": stage,
                "case_id": cid,
                "bundle_digest": selection["bundle_digest"],
                "config_digest": config_digest,
                "source_code": plan["generation_source_identity"],
            }.items()
        ):
            raise ValueError(f"Generation identity differs: {path}")
        if read(path.with_name("ADMITTED.json"))["identity"] != identity:
            raise ValueError("Admission/result mismatch")
        if stage == "edit" and len(stages(model)) == 2:
            previous = base / "run" / model / stages(model)[0] / cid / "result.json"
            if identity["previous_sha256"] != sha256_file(previous):
                raise ValueError("Previous native stage changed")
        if record["status"] == "completed" and stage == "edit":
            for prefix in ("raw", "output"):
                if sha256_file(record[prefix + "_image"]) != record[prefix + "_sha256"]:
                    raise ValueError("Generated pixels changed")
        if stage == "edit":
            score_path = base / "scores" / model / cid / "local.json"
            score = read(score_path)
            if any(
                score["identity"][k] != v
                for k, v in {
                    "model": model,
                    "case_id": cid,
                    "bundle_digest": selection["bundle_digest"],
                    "result_sha256": sha256_file(path),
                    "output_sha256": record.get("output_sha256"),
                    "private_row_digest": digest(private[cid]),
                    "implementation": reference_implementation,
                }.items()
            ):
                raise ValueError("Score/generation mismatch")
        return {
            "model": model,
            "stage": stage,
            "case_id": cid,
            "status": record["status"],
            "record": str(path),
            "record_sha256": sha256_file(path),
            **{
                k: record.get(k)
                for k in (
                    "inference_seconds",
                    "load_seconds",
                    "wall_seconds",
                    "peak_gpu_allocated_bytes",
                    "error",
                    "fatal",
                )
            },
        }

    jobs = [(m, s, c) for m in models for s in stages(m) for c in selection["case_ids"]]
    with ThreadPoolExecutor(max_workers=12) as pool:
        records = list(pool.map(inspect, jobs))
    grouped = defaultdict(list)
    for record in records:
        grouped[record["model"], record["stage"]].append(record)
    costs = []
    for (model, stage), rows in grouped.items():
        times = [r["inference_seconds"] for r in rows if r.get("inference_seconds") is not None]
        costs.append(
            {
                "model": model,
                "stage": stage,
                "status_counts": dict(Counter(r["status"] for r in rows)),
                "mean_inference_seconds": statistics.fmean(times) if times else None,
                "recorded_inference_gpu_hours": sum(times) / 3600,
                "recorded_load_seconds": sum(r.get("load_seconds") or 0 for r in rows),
                "peak_allocated_GiB": max(
                    (r.get("peak_gpu_allocated_bytes") or 0 for r in rows), default=0
                )
                / 2**30,
            }
        )
    return {
        "records": records,
        "costs": costs,
        "failures": [r for r in records if r["status"] != "completed"],
    }


def analyze(selection, native, repetitions=10000):
    bench, models, rows = selection["benchmark"], selection["models"], selection["rows"]
    lookup = {(r["model"], r["case_id"]): r for r in native["per_case"]}
    clusters = sorted({r["cluster"] for r in rows})
    cluster_index = {c: i for i, c in enumerate(clusters)}
    draws = (
        np.random.default_rng(SEED)
        .multinomial(len(clusters), np.ones(len(clusters)) / len(clusters), size=repetitions)
        .astype(np.int32)
    )
    output = []
    for ep in endpoints(bench, rows):
        selected = [
            r
            for r in rows
            if (not ep.tasks or task(r) in ep.tasks)
            and (ep.language is None or r.get("language") == ep.language)
        ]
        indices = np.array([cluster_index[r["cluster"]] for r in selected])
        groups = np.array([task(r) if ep.macro else "all" for r in selected])
        weights = np.ones(len(selected))
        values = np.full((len(models), len(selected)), np.nan)
        weight_key = WEIGHTS.get(ep.metric) if bench == "omni_iie" else None
        for j, item in enumerate(selected):
            ws = []
            for i, model in enumerate(models):
                record = lookup[model, item["case_id"]]
                value = (record.get("metrics") or {}).get(ep.metric)
                if record["status"] == "completed" and finite(value):
                    values[i, j] = value
                    if weight_key:
                        ws.append(record["metrics"][weight_key])
            if ws:
                if not all(finite(w) and w >= 0 and abs(w - ws[0]) < 1e-12 for w in ws):
                    raise ValueError("Native area weights changed across methods")
                weights[j] = ws[0]
        common = np.isfinite(values).all(axis=0)
        counts = draws[:, indices]
        result = {
            "group": ep.group,
            "metric": ep.metric,
            "main_endpoint": ep.main,
            "direction": "lower" if ep.metric in LOWER else "higher",
            "expected": len(selected),
            "common_scored": int(common.sum()),
            "models": {},
        }
        for i, model in enumerate(models):
            v = values[i]
            point = float(aggregate(v, weights, groups))
            if bench == "compbench":
                section, field = ("groups", "group") if ep.main else ("tasks", "task")
                expected = next(r for r in native["rows"][model][section] if r[field] == ep.group)[
                    "valid_mean"
                ][ep.metric]
            else:
                expected = native["rows"][model][ep.group]["metrics"][ep.metric]["mean"]
            if expected is not None and (not finite(point) or abs(point - expected) > 1e-10):
                raise ValueError("Comparison mean differs from the native evaluator")
            restricted = np.where(common, v, np.nan)
            common_point = float(aggregate(restricted, weights, groups))
            result["models"][model] = {
                "mean": point if finite(point) else None,
                "CI95": interval(aggregate(v, weights, groups, counts)),
                "scored": int(np.isfinite(v).sum()),
                "common_mean": common_point if finite(common_point) else None,
            }
        output.append(result)
    return {
        "rows": output,
        "bootstrap": {
            "seed": SEED,
            "repetitions": repetitions,
            "unit": "canonical source cluster",
            "cluster_order": clusters,
            "shared_bootstrap_counts_sha256": hashlib.sha256(draws.tobytes()).hexdigest(),
            "confidence_intervals": "pointwise 95%; no new significance claim",
        },
    }


def fmt(value):
    return "N/A" if value is None else f"{value:.4f}"


def markdown(payload):
    lines = [
        f"# {BENCH_NAMES[payload['benchmark']]}：固定子集多方法比较",
        "",
        f"每方法 {payload['requests']} 条请求，{payload['source_clusters']} 个源图簇。复用同一事前固定子集，不是完整测试集排行榜。",
        "",
        "Qwen-Image-2.1 与 SITEdit 的原生成、评分逐条核验复用；新方法不改样本、公开输入和评分配置。全部使用 seed 42、约 1MP 输入和冻结原生推理。无 API 调用。",
        "",
        "以下为各方法已有效评分的原生均值，覆盖率单独列出；不以虚构值补失败，不将失败样本移出应评分母。CompBench 按官方等权子任务聚合；Omni 保留官方面积权重。",
        "",
    ]
    grouped = defaultdict(list)
    for row in payload["analysis"]["rows"]:
        if row["main_endpoint"]:
            grouped[row["group"]].append(row)
    for group, rows in grouped.items():
        lines += [
            f"## {GROUP_NAMES.get(group, group)}",
            "",
            "| 方法 | 有效/应评 | "
            + " | ".join(r["metric"] + (" ↓" if r["direction"] == "lower" else " ↑") for r in rows)
            + " |",
            "|---|---:|" + "---:|" * len(rows),
        ]
        for model in payload["models"]:
            scored = {r["models"][model]["scored"] for r in rows}
            coverage = str(min(scored)) if len(scored) == 1 else f"{min(scored)}–{max(scored)}"
            lines.append(
                f"| {NAMES[model]} | {coverage}/{rows[0]['expected']} | "
                + " | ".join(fmt(r["models"][model]["mean"]) for r in rows)
                + " |"
            )
        lines.append("")
    if any(
        r["common_scored"] != r["expected"]
        for r in payload["analysis"]["rows"]
        if r["main_endpoint"]
    ):
        lines += [
            "## 所有方法共同有效请求：敏感性对比",
            "",
            "下面是同一交集上的重算结果；主表仍保留完整应评人口和各方法覆盖率。",
            "",
        ]
        for group, rows in grouped.items():
            lines += [
                f"### {GROUP_NAMES.get(group, group)}",
                "",
                "| 方法 | 共同有效/应评 | " + " | ".join(r["metric"] for r in rows) + " |",
                "|---|---:|" + "---:|" * len(rows),
            ]
            for model in payload["models"]:
                lines.append(
                    f"| {NAMES[model]} | {rows[0]['common_scored']}/{rows[0]['expected']} | "
                    + " | ".join(fmt(r["models"][model]["common_mean"]) for r in rows)
                    + " |"
                )
            lines.append("")
    lines += [
        "## 均值的 95% 区间",
        "",
        "同源图请求共同重采样，10,000 次，seed 20261109；全体方法共用抽样。以下为逐项区间，不能通过是否重叠替代配对差值检验。新增方法比较不复用原两方法 53 项 Holm 检验的显著性标签。",
        "",
        "| 组 | 指标 | 方法 | 均值 [95% CI] |",
        "|---|---|---|---:|",
    ]
    for row in payload["analysis"]["rows"]:
        if not row["main_endpoint"]:
            continue
        for model in payload["models"]:
            d = row["models"][model]
            ci = "N/A" if d["CI95"] is None else f"[{fmt(d['CI95'][0])}, {fmt(d['CI95'][1])}]"
            lines.append(
                f"| {GROUP_NAMES.get(row['group'], row['group'])} | {row['metric']} | {NAMES[model]} | {fmt(d['mean'])} {ci} |"
            )
    lines += [
        "",
        "## 失败和开销",
        "",
        "| 方法 | 阶段 | 状态计数 | 实测推理秒/条 | 推理 GPU 小时 | 峰值 allocated GiB |",
        "|---|---|---|---:|---:|---:|",
    ]
    for r in payload["audit"]["costs"]:
        lines.append(
            f"| {NAMES[r['model']]} | {r['stage']} | {r['status_counts']} | {fmt(r['mean_inference_seconds'])} | {fmt(r['recorded_inference_gpu_hours'])} | {fmt(r['peak_allocated_GiB'])} |"
        )
    lines += [
        "",
        "GPU 小时只累计原始记录中的模型推理时间，不包括加载、CPU 评分和等待；完整错误清单见 JSON audit.failures。",
        "",
        "## 协议与复现",
        "",
        "- CompBench：第二轮使用本方法第一轮输出，原生规划失败及依赖失败如实保留。",
        "- Inter-Edit：公开 mask 原生输入 MICE，作为附加图输入 FLUX.2/Base；SITEdit 原生编码。缺参考图的指标仍 N/A。",
        "- CompBench/Omni 的 MICE 使用原生无区域全局提示路径，不调用额外定位器。",
        "- Omni：QA/Overall 仍 N/A；官方 BG CLIP-I 单例特征与全图相同，聚合权重不同，保留原公式。",
        "",
        f"- 新计划：`{payload['plan_path']}`，digest `{payload['plan_digest']}`。",
        f"- 清单：`{payload['selection_path']}`。",
        f"- 原生报告：`{payload['native_report']}`。",
        f"- 生成和评分：`{payload['results_root']}`。",
        "- `COMPARISON.json` 包含所有指标、分组、均值区间、逐条来源和失败；`TABLES.csv` 可直接制表。",
        "",
    ]
    return "\n".join(lines)


def run(control, attempt):
    control = Path(control)
    plan = checked(control / "PLAN.json")
    done = read(control / "attempts" / attempt / "DONE.json")
    if done["plan_digest"] != plan["digest"] or not done["scientific_generation_complete"]:
        raise ValueError("Wait for generation and native scoring to finish")
    reports = []
    for entry in plan["benchmarks"]:
        path = Path(entry["selection"])
        if sha256_file(path) != entry["selection_sha256"]:
            raise ValueError("Selection changed")
        selection = checked(path)
        verify_selection(selection)
        native_path = Path(selection["results_root"]) / "native_reports" / attempt / "REPORT.json"
        native = read(native_path)
        audited = audit(selection, plan, native)
        analysis = analyze(selection, native)
        previous_path = Path(selection["reused_results_root"]) / "report/PAIRED_REPORT.json"
        previous = read(previous_path)
        old_rows = {(r["group"], r["metric"]): r for r in previous["analysis"]["rows"]}
        for row in analysis["rows"]:
            old = old_rows[row["group"], row["metric"]]
            for model in REUSED:
                a, b = row["models"][model], old["models"][model]
                if a["mean"] != b["mean"] or a["CI95"] != b["CI95"]:
                    raise ValueError(
                        "Original two-model means/intervals were not reproduced exactly"
                    )
        payload = {
            "schema": "external.comparison.report.v1",
            "benchmark": selection["benchmark"],
            "requests": len(selection["case_ids"]),
            "source_clusters": selection["independent_source_clusters"],
            "models": selection["models"],
            "case_ids": selection["case_ids"],
            "plan_path": str(control / "PLAN.json"),
            "plan_digest": plan["digest"],
            "generation_source_commit": plan["source_commit"],
            "selection_path": str(path),
            "selection_sha256": sha256_file(path),
            "native_report": str(native_path),
            "native_report_sha256": sha256_file(native_path),
            "reused_report": str(previous_path),
            "reused_report_sha256": sha256_file(previous_path),
            "original_two_model_means_and_ci_exact": True,
            "results_root": selection["results_root"],
            "analysis": analysis,
            "audit": audited,
            "source_sha256": {
                str(p.relative_to(Path(__file__).parents[3])): sha256_file(p)
                for p in [Path(__file__), Path(__file__).parents[1] / "external_pair/statistics.py"]
            },
        }
        output = Path(selection["results_root"]) / "report"
        immutable(output / "COMPARISON.json", payload)
        text = markdown(payload)
        md = output / "REPORT.md"
        if md.exists() and md.read_text() != text:
            raise ValueError("Existing comparison report differs")
        md.write_text(text)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "group",
                "metric",
                "direction",
                "model",
                "mean",
                "ci_low",
                "ci_high",
                "scored",
                "expected",
                "common_scored",
                "common_mean",
                "main_endpoint",
            ]
        )
        for row in analysis["rows"]:
            for model in selection["models"]:
                d = row["models"][model]
                writer.writerow(
                    [
                        row["group"],
                        row["metric"],
                        row["direction"],
                        model,
                        d["mean"],
                        *(d["CI95"] or [None, None]),
                        d["scored"],
                        row["expected"],
                        row["common_scored"],
                        d["common_mean"],
                        row["main_endpoint"],
                    ]
                )
        csv_path = output / "TABLES.csv"
        if csv_path.exists() and csv_path.read_text() != buffer.getvalue():
            raise ValueError("Existing comparison CSV differs")
        csv_path.write_text(buffer.getvalue())
        reports.append(
            {
                "benchmark": selection["benchmark"],
                "path": str(output / "COMPARISON.json"),
                "sha256": sha256_file(output / "COMPARISON.json"),
            }
        )
        print(f"Completed {selection['benchmark']}: {output}", flush=True)
    immutable(control / "SUMMARY.json", {"plan_digest": plan["digest"], "reports": reports})
    immutable(
        control / "COMPLETED.json",
        {
            "plan_digest": plan["digest"],
            "completed_utc": datetime.now(timezone.utc).isoformat(),
            "reports": reports,
            "paid_api_calls": 0,
        },
    )
