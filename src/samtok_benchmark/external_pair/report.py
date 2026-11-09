"""Chinese paired-validation report; no inference, scoring replacement, or outcome selection."""

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import statistics

from samtok_benchmark.external_full.data import immutable, read
from samtok_benchmark.io import digest, sha256_file
from . import MODELS
from .statistics import analyze, holm

NAMES = {"compbench": "CompBench", "interedit": "Inter-Edit", "omni_iie": "Omni IIE"}
METHODS = {"sitedit": "SITEdit", "qwen21": "Qwen-Image-2.1"}
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


def fmt(value):
    return "N/A" if value is None else f"{value:.4f}"


def ci(value):
    return "N/A" if value is None else f"[{fmt(value[0])}, {fmt(value[1])}]"


def costs(selection):
    root = Path(selection["results_root"]) / "run"
    jobs = [
        (model, stage, row["case_id"])
        for model in MODELS
        for stage in (("tokens", "edit") if model == "sitedit" else ("edit",))
        for row in selection["rows"]
    ]

    def inspect(job):
        model, stage, cid = job
        path = root / model / stage / cid / "result.json"
        if not path.exists():
            return model, stage, None
        record = read(path)
        return (
            model,
            stage,
            {
                k: record.get(k)
                for k in (
                    "status",
                    "inference_seconds",
                    "wall_seconds",
                    "load_seconds",
                    "peak_gpu_allocated_bytes",
                    "peak_gpu_reserved_bytes",
                )
            },
        )

    grouped = defaultdict(list)
    with ThreadPoolExecutor(max_workers=8) as pool:
        for model, stage, record in pool.map(inspect, jobs):
            grouped[model, stage].append(record)
    result = []
    for (model, stage), rows in grouped.items():
        inference = [
            r["inference_seconds"] for r in rows if r and r.get("inference_seconds") is not None
        ]
        result.append(
            {
                "model": model,
                "stage": stage,
                "expected": len(rows),
                "status_counts": dict(Counter(r["status"] if r else "missing" for r in rows)),
                "mean_recorded_inference_seconds": statistics.fmean(inference)
                if inference
                else None,
                "recorded_inference_gpu_hours": sum(inference) / 3600,
                "recorded_load_seconds": sum(r.get("load_seconds") or 0 for r in rows if r),
                "peak_allocated_GiB": max(
                    (r.get("peak_gpu_allocated_bytes") or 0 for r in rows if r), default=0
                )
                / 2**30,
                "peak_reserved_GiB": max(
                    (r.get("peak_gpu_reserved_bytes") or 0 for r in rows if r), default=0
                )
                / 2**30,
            }
        )
    return result


def markdown(payload):
    name = NAMES[payload["benchmark"]]
    lines = [
        f"# {name}：SITEdit 与 Qwen-Image-2.1 扩大样本配对验证",
        "",
        f"每方法固定 {payload['requests']} 条请求，来自 {payload['source_clusters']} 个独立源图簇。样本在生成前按 seed 20261109 固定，与已分析 pilot/冒烟的源图分离。本表只报告这批新样本，不是全量 benchmark 排名。",
        "",
        "SITEdit 固定 aa5a414 主行：Pass1 定位 LoRA + S2 DiT LoRA/CodeInjector、raw SAMTok TE、token guidance 2、40 步、seed 42。Base 保持官方 Qwen-Image-2.1 冻结配置、40 步、CFG 1、seed 42；两方法共用约 1MP 输入画布与恢复流程。",
        "",
        "仅使用官方客观指标，不调用 API。CompBench 第二轮输入各方法自己的第一轮输出；Inter-Edit 向两方法提供相同公开 mask（SITEdit 直接编码，Base 原生附加 mask 图）；Omni 保持完整 low/high 配对。",
        "",
        "## 结果",
        "",
        "均值复算已与原生报告逐项核对。置信区间为 10,000 次源图配对 bootstrap 的逐项 95% 区间；同源请求一起抽样。改善量 Δ 的正值表示 SITEdit 更好，低优指标用 Base − SITEdit，高优指标用 SITEdit − Base。主比较共 53 项，单侧源图配对置换检验采用 Holm 校正。分组诊断不加入新的显著性主张。",
        "",
    ]
    groups = defaultdict(list)
    for row in payload["analysis"]["rows"]:
        groups[row["group"]].append(row)
    for group, rows in groups.items():
        lines += [
            f"### {GROUP_NAMES.get(group, group)}",
            "",
            "| 指标 | SITEdit（95% CI） | Qwen-Image-2.1（95% CI） | 改善 Δ（95% CI） | 成对有效 / 应评 | Holm p |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for row in rows:
            a, b = (row["models"][m] for m in MODELS)
            direction = "↓" if row["direction"] == "lower" else "↑"
            lines.append(
                f"| {row['metric']} {direction} | {fmt(a['mean'])} {ci(a['CI95'])} | {fmt(b['mean'])} {ci(b['CI95'])} | {fmt(row['benefit_delta'])} {ci(row['benefit_CI95'])} | {row['paired_scored']} / {row['expected']} | {fmt(row.get('p_holm_53')) if row['main_endpoint'] else '诊断'} |"
            )
        lines.append("")
    main = [r for r in payload["analysis"]["rows"] if r["main_endpoint"]]
    better = [r for r in main if r["benefit_delta"] is not None and r["benefit_delta"] > 0]
    reliable = [
        r
        for r in better
        if r.get("p_holm_53", 1) < 0.05 and r["benefit_CI95"] and r["benefit_CI95"][0] > 0
    ]
    lines += [
        "## 统计结果摘要",
        "",
        f"- {len(main)} 个主比较中，{len(better)} 项的点估计朝 SITEdit 改善；其中 {len(reliable)} 项同时满足改善区间下界大于 0、Holm 校正 p < 0.05。这个计数用于完整陈述所有指标，不是新的综合分。",
        "- 固定样本覆盖率、单项区间和指标含义应一起阅读；相关指标不能当作独立重复实验。样本验证不替代全量评测。",
    ]
    if payload["benchmark"] == "omni_iie":
        lines += [
            "- Omni 官方 BG CLIP-I 的图像处理会转为 RGB，单例特征与全图 CLIP-I 相同，聚合采用背景面积权重；不能把它解释为独立的区域外语义指标。QA / Overall 保持 N/A。"
        ]
    if payload["benchmark"] == "interedit":
        lines += [
            "- 官方发布数据缺少 reference_image：S_ref_AlphaCLIP 与 VLM 仍为 N/A；四项可运行指标完整保留。BSS 测的是边界拉普拉斯连续性，不能单独代表指令完成度。"
        ]
    lines += [
        "",
        "## 覆盖率与运行开销",
        "",
        "| 方法 | 阶段 | 状态计数 | 实测推理秒/条 | 记录的推理 GPU 小时 | 峰值 allocated GiB |",
        "|---|---|---|---:|---:|---:|",
    ]
    for r in payload["costs"]:
        lines.append(
            f"| {METHODS[r['model']]} | {r['stage']} | {r['status_counts']} | {fmt(r['mean_recorded_inference_seconds'])} | {fmt(r['recorded_inference_gpu_hours'])} | {fmt(r['peak_allocated_GiB'])} |"
        )
    lines += [
        "",
        "开销为原始逐条记录的实测值；GPU 小时累加模型推理时间，不包含加载、文件核验、CPU 评分及卡间等待。没有为缺失耗时填估计值。失败保持完整分母，不填零；配对差值只用两方法均有有效分数的请求。",
        "",
        "## 文件与复现",
        "",
        f"- 事前清单：`{payload['selection_path']}`",
        f"- 原生分数：`{payload['native_report']}`",
        f"- 全部生成与逐条评分：`{payload['results_root']}`",
        f"- 配对统计：`{payload['results_root']}/report/PAIRED_REPORT.json`",
        f"- 生成源码：`{payload['generation_source_commit']}`；计划 digest：`{payload['plan_digest']}`。",
        "- 统计入口：`OPENBLAS_NUM_THREADS=1 <metrics-python> -I scripts/external_pair_report.py --control <control> --attempt <attempt>`。该命令只读取现有证据，不调用生成或 API。",
        "",
    ]
    return "\n".join(lines)


def run(control, attempt):
    control = Path(control)
    plan = read(control / "PLAN.json")
    if plan["digest"] != digest({k: v for k, v in plan.items() if k != "digest"}):
        raise ValueError("Plan changed")
    done = read(control / "attempts" / attempt / "DONE.json")
    if done["plan_digest"] != plan["digest"] or not done["scientific_generation_complete"]:
        raise ValueError("Generation and native metrics must finish first")
    reports = []
    for entry in plan["benchmarks"]:
        path = Path(entry["selection"])
        if sha256_file(path) != entry["selection_sha256"]:
            raise ValueError("Selection changed")
        selection = read(path)
        native_path = Path(selection["results_root"]) / "native_reports" / attempt / "REPORT.json"
        native = read(native_path)
        result = analyze(selection["benchmark"], selection, native)
        reports.append(
            {
                "schema": "external.paired.report.v1",
                "benchmark": selection["benchmark"],
                "requests": len(selection["case_ids"]),
                "source_clusters": selection["independent_source_clusters"],
                "selection_path": str(path),
                "selection_sha256": entry["selection_sha256"],
                "native_report": str(native_path),
                "native_report_sha256": sha256_file(native_path),
                "results_root": selection["results_root"],
                "generation_source_commit": plan["source_commit"],
                "analysis_source_sha256": {
                    name: sha256_file(Path(__file__).parent / name)
                    for name in ("statistics.py", "report.py")
                },
                "plan_digest": plan["digest"],
                "analysis": result,
                "costs": costs(selection),
            }
        )
    main = [r for report in reports for r in report["analysis"]["rows"] if r["main_endpoint"]]
    if len(main) != 53:
        raise ValueError("Predeclared main test family changed")
    for row, adjusted in zip(main, holm([r["p_one_sided"] for r in main])):
        row["p_holm_53"] = adjusted
    summary = {"schema": "external.paired.summary.v1", "plan_digest": plan["digest"], "reports": []}
    for payload in reports:
        out = Path(payload["results_root"]) / "report"
        immutable(out / "PAIRED_REPORT.json", payload)
        content = markdown(payload)
        path = out / "REPORT.md"
        if path.exists() and path.read_text() != content:
            raise ValueError("Never overwrite a different final report")
        path.write_text(content)
        summary["reports"].append(
            {
                "benchmark": payload["benchmark"],
                "path": str(out / "PAIRED_REPORT.json"),
                "sha256": sha256_file(out / "PAIRED_REPORT.json"),
            }
        )
        print(f"Verified paired report: {path}", flush=True)
    immutable(control / "SUMMARY.json", summary)
    return reports
