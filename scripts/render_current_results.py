#!/usr/bin/env python3
"""Render the latest approved IF-Bench dev20 aggregates; CPU only, no scoring."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil


SOURCE_SHA = "b162e196a726b2f59304956516fc27d3aa109895a57d2b5c053fa4785b5210d1"
MODELS = ["qwen2511", "qwen21", "flux3", "replan", "mirage", "mice", "flux2_klein9b"]
SETTINGS = [
    "S1",
    "S2-point",
    "S2-box",
    "S2-mask",
    "S3-point",
    "S3-box",
    "S3-mask",
    "S4-ref",
    "S4-noref",
    "S5",
]
SHORT = {
    "qwen2511": "Qwen2511",
    "qwen21": "Qwen2.1",
    "flux3": "FLUX3",
    "replan": "RePlan",
    "mirage": "MIRAGE",
    "mice": "MICE",
    "flux2_klein9b": "FLUX2-9B",
}
FULL = {
    "qwen2511": "Qwen-Image-Edit-2511",
    "qwen21": "Qwen-Image-2.1",
    "flux3": "FLUX.3 Klein distilled",
    "replan": "RePlan（Qwen-2511骨干）",
    "mirage": "MIRAGE（Qwen-2511骨干）",
    "mice": "MICE（Klein-4B骨干）",
    "flux2_klein9b": "FLUX.2 Klein-9B distilled",
}
ROW_FIELDS = [
    "model",
    "setting",
    "UnitPass",
    "JointPass",
    "bootstrap",
    "case_denominator",
    "unit_denominator",
    "known_pass_units",
    "known_joint_pass_cases",
    "status_counts",
    "generation_failed_cases",
    "scored_cases",
    "scored_unit_denominator",
    "missing_cases",
    "missing_units",
    "complete",
    "not_applicable",
    "by_K",
]


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    )


def require(value, message):
    if not value:
        raise ValueError(message)


def export_aggregate(source, root):
    """Allowlist aggregate fields; never copy per-case scores, prompts or masks."""
    require(sha(source) == SOURCE_SHA, "Expected the immutable latest repaired dev20 REPORT.json")
    report = read(source)
    require(
        report["ready_for_review"] and not report["frozen"] and not report["test_started"],
        "Expected completed, unfrozen dev20 only",
    )
    require(
        report["model_order"] == MODELS and report["settings"] == SETTINGS,
        "Unexpected model/setting population",
    )
    appendix = source.parent / "appendix"
    analysis = read(appendix / "ANALYSIS.json")
    statistics = read(appendix / "STATISTICAL_VALIDATION.json")
    generation = read(source.parent / "audit/FINAL_GENERATION_AUDIT.json")
    judge = read(source.parent / "audit/FINAL_JUDGE_AUDIT.json")
    require(
        statistics["status"] == "passed" and statistics["main_report_sha256"] == SOURCE_SHA,
        "Statistics validation mismatch",
    )
    require(generation["passed"] and judge["passed"], "Generation/Judge source audits must pass")
    bundle = source.parents[2]
    plan = read(bundle / "plan.json")
    require(sha(bundle / "plan.json") == report["plan_sha256"], "Plan SHA mismatch")
    figures = []
    selected_case = read(appendix / "AUDIT_SELECTION.json")["selected_case_ids"][0]
    for setting in SETTINGS:
        original = appendix / analysis["comparison_figures"][setting]
        relative = Path("assets/results/comparisons") / original.name
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)
        require(sha(destination) == sha(original), "Comparison figure copy changed")
        figures.append(
            {
                "setting": setting,
                "case_id": selected_case,
                "path": relative.as_posix(),
                "sha256": sha(original),
            }
        )
    execution = {}
    for model in MODELS:
        entries = [
            e for e in report["calls"]["editor_records"] if e["task_key"].split("/")[0] == model
        ]
        execution[model] = {
            "logical_requests": len(entries),
            "status_counts": dict(Counter(e["status"] for e in entries)),
            "terminal_reused": sum(bool(e["reused"]) for e in entries),
            "new_editor_api_calls": sum(e["new_editor_api_calls"] for e in entries),
        }
    files = {
        "REPORT.json": source,
        "plan.json": bundle / "plan.json",
        "STATISTICAL_VALIDATION.json": appendix / "STATISTICAL_VALIDATION.json",
        "FINAL_GENERATION_AUDIT.json": source.parent / "audit/FINAL_GENERATION_AUDIT.json",
        "FINAL_JUDGE_AUDIT.json": source.parent / "audit/FINAL_JUDGE_AUDIT.json",
        "AUDIT_SELECTION.json": appendix / "AUDIT_SELECTION.json",
    }
    return {
        "schema": "ifbench-current-dev20-aggregate-v1",
        "scope": "latest repaired dev20 only; formal test pending",
        "source_count": report["source_count"],
        "units_per_model_setting": report["units_per_model_setting"],
        "K_counts": report["K_counts"],
        "models": MODELS,
        "settings": SETTINGS,
        "rows": [{k: row[k] for k in ROW_FIELDS} for row in report["rows"]],
        "derived": report["derived"],
        "s2_discard_supplement": [
            {k: row[k] for k in ROW_FIELDS if k in row} for row in report["s2_discard_supplement"]
        ],
        "bootstrap": report["bootstrap"],
        "generation_counts": report["generation_counts"],
        "logical_scoring_statuses": statistics["logical_statuses"],
        "judge_bindings": report["judge_bindings"],
        "execution": execution,
        "qwen_execution": generation["qwen_counts"],
        "new_execution_cost": {
            k: generation["cost"][k]
            for k in [
                "new_request_wall_seconds_sum",
                "new_unique_load_seconds_sum",
                "qwen_phase_wall_seconds",
                "is_gpu_kernel_active_time_or_utilization",
            ]
        },
        "judge_counts": judge["counts"],
        "new_judge_phase_wall_seconds": judge["receipt"]["value"]["ended_at"]
        - judge["receipt"]["value"]["started_at"],
        "generation_seed": list({s["seed"] for s in report["model_specifications"].values()}),
        "statistical_checks": {k: statistics[k] for k in ["checks_total", "checks_passed"]},
        "figures": figures,
        "formal_results": "待评测",
        "human_kappa": None,
        "population_marker_residual_rate": None,
        "pasteback_diagnostic": "待评测",
        "ablations": "未完成",
        "provenance": {
            "report_generated_at_utc": report["generated_at_utc"],
            "plan_digest": report["plan_digest"],
            "source_files": {
                name: {"path": str(path), "sha256": sha(path)} for name, path in files.items()
            },
            "case_manifest": {
                "path": plan["case_manifest"],
                "sha256": plan["case_manifest_sha256"],
            },
            "run_root": str(bundle),
            "raw_outputs": str(bundle / "results/runs"),
            "canonical_scores": str(bundle / "results/judge"),
            "external_report": str(source.parent / "REPORT.md"),
            "external_gallery": str(appendix / "AUDIT_GALLERY.md"),
            "aggregate_excludes": [
                "per-case score records",
                "raw prompts",
                "GT masks",
                "raw Judge replies",
                "earlier score versions",
            ],
        },
    }


def validate(data, root):
    require(
        data["provenance"]["source_files"]["REPORT.json"]["sha256"] == SOURCE_SHA,
        "Aggregate source SHA mismatch",
    )
    require(
        data["models"] == MODELS and data["settings"] == SETTINGS and len(data["rows"]) == 70,
        "Expected only seven models and 70 current rows",
    )
    require(data["formal_results"] == "待评测", "Formal results must remain pending")
    rows = {(r["model"], r["setting"]): r for r in data["rows"]}
    require(set(rows) == {(m, s) for m in MODELS for s in SETTINGS}, "Incomplete current coverage")
    for row in rows.values():
        require(
            row["complete"] and row["missing_cases"] == 0 and row["missing_units"] == 0,
            "Unexpected missing scores",
        )
        require(
            row["unit_denominator"] == data["units_per_model_setting"]
            and row["case_denominator"] == data["source_count"],
            "Denominator mismatch",
        )
        require(
            abs(row["UnitPass"] - row["known_pass_units"] / row["unit_denominator"]) < 1e-12,
            "UP fraction mismatch",
        )
        require(
            abs(row["JointPass"] - row["known_joint_pass_cases"] / row["case_denominator"]) < 1e-12,
            "JP fraction mismatch",
        )
        for metric in ["UnitPass", "JointPass"]:
            low, high = row["bootstrap"][metric]["CI95"]
            require(0 <= low <= high <= 1, "Invalid pass-rate confidence interval")
    forbidden = {"per_case", "prompt", "raw_response", "masks", "ground_truth", "E", "P", "Q"}

    def walk(value):
        if isinstance(value, dict):
            require(
                not (set(value) & forbidden),
                "Private or unaggregated fields leaked into exported JSON",
            )
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data)
    for item in data["figures"]:
        require(sha(root / item["path"]) == item["sha256"], "Fixed comparison image changed")
    return rows


def percent(value):
    return f"{100 * value:.2f}"


def ci_text(values):
    return f"[{percent(values[0])}, {percent(values[1])}]"


def heatmaps(data, rows, root):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    matplotlib.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "svg.hashsalt": SOURCE_SHA,
            "svg.fonttype": "path",
        }
    )
    assets = root / "assets/results"
    for metric in ["UnitPass", "JointPass"]:
        values = np.array([[100 * rows[m, s][metric] for m in MODELS] for s in SETTINGS])
        fig, ax = plt.subplots(figsize=(10.4, 5.9), layout="constrained")
        im = ax.imshow(values, vmin=0, vmax=100, cmap="cividis", aspect="auto")
        ax.set_xticks(range(len(MODELS)), [SHORT[m] for m in MODELS])
        ax.set_yticks(range(len(SETTINGS)), SETTINGS)
        ax.tick_params(length=0, pad=7)
        for y in range(len(SETTINGS)):
            for x in range(len(MODELS)):
                ax.text(
                    x,
                    y,
                    f"{values[y, x]:.2f}",
                    va="center",
                    ha="center",
                    fontsize=10,
                    color="white" if values[y, x] < 50 else "#111111",
                )
        ax.set_xticks(np.arange(-0.5, len(MODELS), 1), minor=True)
        ax.set_yticks(np.arange(-0.5, len(SETTINGS), 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=0.9, alpha=0.8)
        ax.tick_params(which="minor", bottom=False, left=False)
        for spine in ax.spines.values():
            spine.set_visible(False)
        denominator = (
            f"{data['units_per_model_setting']} units"
            if metric == "UnitPass"
            else f"{data['source_count']} source images"
        )
        ax.set_title(
            f"{metric} (%) | fixed dev20 | {denominator} per row",
            loc="left",
            fontsize=13,
            fontweight="bold",
            pad=14,
        )
        colorbar = fig.colorbar(
            im, ax=ax, fraction=0.035, pad=0.025, ticks=[0, 20, 40, 60, 80, 100]
        )
        colorbar.set_label("Pass rate (%)")
        fig.supxlabel(
            "Fixed model order; point estimates only. See tables for paired-bootstrap 95% CIs.",
            fontsize=9,
            color="#444444",
        )
        for extension in ["png", "svg"]:
            metadata = (
                {"Software": "IF-Bench current-results renderer"}
                if extension == "png"
                else {"Date": None, "Creator": "IF-Bench current-results renderer"}
            )
            target = assets / f"{metric.lower()}_heatmap.{extension}"
            fig.savefig(target, dpi=180, metadata=metadata)
            if extension == "svg":
                target.write_text(
                    "\n".join(line.rstrip() for line in target.read_text().splitlines()) + "\n"
                )
        plt.close(fig)
    return {"matplotlib": matplotlib.__version__, "numpy": np.__version__}


def csv_table(data, path):
    fields = [
        "model",
        "setting",
        "known_pass_units",
        "unit_denominator",
        "UnitPass",
        "UnitPass_CI95_low",
        "UnitPass_CI95_high",
        "known_joint_pass_cases",
        "case_denominator",
        "JointPass",
        "JointPass_CI95_low",
        "JointPass_CI95_high",
        "generation_failed_cases",
        "missing_cases",
    ]
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in data["rows"]:
            flat = {key: row[key] for key in fields if key in row}
            for metric in ["UnitPass", "JointPass"]:
                flat[metric + "_CI95_low"], flat[metric + "_CI95_high"] = row["bootstrap"][metric][
                    "CI95"
                ]
            writer.writerow(flat)


def markdown(data, rows):
    n, u = data["source_count"], data["units_per_model_setting"]
    logical = sum(data["generation_counts"].values())
    scored = data["logical_scoring_statuses"]["scored"]
    unique = data["judge_bindings"]["unique_output_keys"]
    q = data["qwen_execution"]
    j = data["judge_counts"]
    p = data["provenance"]
    lines = [
        "# IF-Bench 当前结果",
        "",
        "**正式结果：待评测。** 本页仅展示最新修复完成的固定 dev20 结果；尚未确认正式冻结，也未启动 test。",
        "",
        f"当前范围为 {len(MODELS)} 个模型 × {len(SETTINGS)} 个 setting × {n} 张共享源图，共 {logical} 个逻辑请求。每条模型×setting结果含 **{u} 个编辑单元、{n} 张源图**。本页不包含早期分数或历史模型行。",
        "",
        "[聚合数据 JSON](assets/results/latest_dev20.json) · [70行分数 CSV](assets/results/latest_dev20.csv) · [生成脚本](../scripts/render_current_results.py)",
        "",
        "## 分数含义与评测口径",
        "",
        f"- **UnitPass（UP）**：通过的编辑单元数 ÷ {u}。单元执行 E=4、保护 P≥3、质量 Q≥3 才通过。",
        f"- **JointPass（JP）**：全部单元通过且全局保护/质量通过的源图数 ÷ {n}。它比UP要求更严格；两个百分数不是两个Judge的意见。",
        f"- **95% CI**：按源图成对 bootstrap，seed={data['bootstrap']['seed']}，{data['bootstrap']['replicates']:,}次，共用抽样索引。区间使用percentile方法；K桶在桶内重采样。某行JP全零时，经验bootstrap区间会退化为[0,0]；这不表示总体通过率确定为零。",
        "- 生成/原生规划失败保留在完整分母；Judge缺分不补零。本次已完成评分，没有Judge缺分。输出统一回到源图分辨率后评分。",
        "- 目标数分布："
        + "、".join(f"K{k}={v}图" for k, v in data["K_counts"].items())
        + "。尤其不能把K=5的极小样本当成稳定结论。",
        "",
        "所有模型共用相同公开文本和区域信息；只做确定性呈现/转换。使用原生方法流程，主结果不接外部SAM、定位器、caption改写器、PE或PUP。RePlan/MIRAGE保留其方法自带planner。每请求一次采样，seed="
        + ",".join(map(str, data["generation_seed"]))
        + "，不根据本页分数重新选输入。",
        "",
        "ref是指令中用于辨认目标的文字指称；no-ref去掉目标指称，保留编辑动作，并依靠该setting公开提供的区域信息。",
        "",
        "| Setting | 公开输入信息 |",
        "|---|---|",
        "| S1 | 语言ref＋编辑指令，无区域 |",
        "| S2-point / box / mask | 语言ref＋编辑指令＋指定区域形式 |",
        "| S3-point / box / mask | 不含语言ref的编辑指令＋指定区域形式 |",
        "| S4-ref | 语言ref＋编辑指令＋各目标共享冻结的混合区域形式 |",
        "| S4-noref | 不含语言ref的编辑指令＋共享冻结的混合区域形式 |",
        "| S5 | manifest冻结的ref/no-ref与none/point/box/mask组合；none必须有ref，不补区域 |",
        "",
        "| 表头简称 | 当前模型 |",
        "|---|---|",
    ]
    lines.extend(f"| {SHORT[m]} | {FULL[m]} |" for m in MODELS)
    for metric, explanation in [("UnitPass", "编辑单元通过率"), ("JointPass", "整图联合通过率")]:
        lines += [
            "",
            f"## {metric}：{explanation}（%）",
            "",
            "| Setting | " + " | ".join(SHORT[m] for m in MODELS) + " |",
            "|---|" + "---:|" * len(MODELS),
        ]
        for setting in SETTINGS:
            lines.append(
                "| "
                + setting
                + " | "
                + " | ".join(percent(rows[m, setting][metric]) for m in MODELS)
                + " |"
            )
        lines += [
            "",
            f"![{metric}固定dev20热图](assets/results/{metric.lower()}_heatmap.png)",
            "",
            f"[下载SVG](assets/results/{metric.lower()}_heatmap.svg)。两图均使用0–100%的同一色阶；仅展示点估计，不表示显著性排名。",
            "",
        ]
    metrics = {
        (m, item["metric"], item["diagnostic"]): item
        for m, items in data["derived"].items()
        for item in items
    }
    positive = sum(
        metrics[m, "UnitPass", "Delta_lang_" + form]["value"] > 0
        for m in MODELS
        for form in ["point", "box", "mask"]
    )
    qb, qm, qs, qp = [rows["qwen21", s] for s in ["S2-box", "S3-mask", "S1", "S2-point"]]
    gain_up, gain_jp = [
        metrics["qwen21", metric, "G_region_point"] for metric in ["UnitPass", "JointPass"]
    ]
    lang_mask = metrics["qwen21", "UnitPass", "Delta_lang_mask"]
    lines += [
        "## 结果说明",
        "",
        f"- **语言ref仍有作用，但强度不同。** {positive}/{len(MODELS) * 3}组S2−S3的UP点估计为正。Qwen2.1的mask差为{percent(lang_mask['value'])}个百分点，95% CI {ci_text(lang_mask['bootstrap']['CI95'])}个百分点，区间跨零；不能把全部正点估计概括为全部显著。",
        f"- **加入区域不保证提高分数。** Qwen2.1的S2-point为{qp['known_pass_units']}/{u}个单元通过，S1为{qs['known_pass_units']}/{u}；差{percent(gain_up['value'])}个百分点，95% CI {ci_text(gain_up['bootstrap']['CI95'])}。JP差{percent(gain_jp['value'])}个百分点，95% CI {ci_text(gain_jp['bootstrap']['CI95'])}，包含零。S2主行不因此改成discard。",
        f"- **应同时看单元完成与整图完成。** 例如Qwen2.1的S2-box为UP {qb['known_pass_units']}/{u}={percent(qb['UnitPass'])}%，JP {qb['known_joint_pass_cases']}/{n}={percent(qb['JointPass'])}%；S3-mask为UP {qm['known_pass_units']}/{u}={percent(qm['UnitPass'])}%，JP {qm['known_joint_pass_cases']}/{n}={percent(qm['JointPass'])}%。局部任务可完成，不代表同图全部任务及保护/质量同时通过。",
        "- **这不是模型最大能力或显著性排名。** 双图角色理解、标记残留、原生planner定位偏差、MICE的global/local路由均可能影响结果；低分不自动证明接口不公平，API能运行也不证明用法已覆盖最大能力。S2−S1还包含原生分辨率/流程变化（例如FLUX3单图与多图限制），不能称为区域信息的纯因果增益。固定输入、组件与参数边界应独立于分数审查。",
        f"- **补充行不参与选型。** {len(data['s2_discard_supplement'])}条S2 discard补充是同模型S1已评分输出的精确复用，不是新调用，不替代主行。完整派生指标、K桶与补充统计保存在当前聚合JSON。",
        "",
        "## 执行完成度与失败",
        "",
        f"已得到 **{scored}个可评分逻辑请求、{unique}个唯一输出评分键**。相同实际输出与canonical绑定可以被多个逻辑请求精确复用，因此两数不同。{data['logical_scoring_statuses'].get('failed-planner', 0)}个MIRAGE原生planner失败仍保留在S1分母；没有隐藏失败或补造输出。",
        "",
        "| 模型 | 逻辑请求 | 实际生成 | 原生规划失败 | 本轮新增编辑API | 精确复用终态 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        entry = data["execution"][model]
        lines.append(
            f"| {SHORT[model]} | {entry['logical_requests']} | {entry['status_counts'].get('generated', 0)} | {entry['status_counts'].get('failed-planner', 0)} | {entry['new_editor_api_calls']} | {entry['terminal_reused']} |"
        )
    lines += [
        "",
        f"Qwen2.1使用原生model CPU offload完成{q['new_offload']}个新请求，并精确复用{q['reused_resident']}个原resident成功输出；当前共{q['generated']}个有效生成。40步、CFG1、2K、KV cache、输入和seed保持固定。其余六模型复用既有终态，包括原生失败；缓存不计新调用。",
        "",
        f"本轮新增Judge调用{j['new_judge_request_calls']}次：{j['new_raw_statuses'].get('scored', 0)}份原始回答直接解析，{j['new_deterministic_repairs']}份仅经已授权的确定性JSON修复，额外推理调用={j['new_repair_inference_calls']}；原文和独立overlay均保留。复用{j['old_effective_keys_reused']}个已核验唯一评分键，不把旧分数绑定到新输出。",
        "",
        "| 本轮测得的执行量 | 实际值 |",
        "|---|---:|",
        f"| Qwen2.1新增编辑API / DiT forward | {q['new_inference_api_calls']} / {q['new_transformer_forward_calls']} |",
        f"| Qwen2.1编辑阶段墙钟 | {data['new_execution_cost']['qwen_phase_wall_seconds']:.2f}秒 |",
        f"| Qwen2.1逐请求墙钟之和 | {data['new_execution_cost']['new_request_wall_seconds_sum']:.2f}秒 |",
        f"| 本轮Judge执行墙钟 | {data['new_judge_phase_wall_seconds']:.2f}秒 |",
        "",
        "这些时间来自实际receipt，范围含加载、CPU/offload、序列化或等待；逐请求秒数之和不等于总墙钟，不能当成GPU内核活跃时长或完整七模型GPU-hours。历史成本与全部原始调用账本留在外部审计记录。",
        "",
        "## 固定样例：所有模型与setting的实际输出",
        "",
        f"以下使用统一随机抽检名单第一张`{data['figures'][0]['case_id']}`；抽样seed=20261031，名单在查看输出质量前已固定。所有setting使用同一例，未按结果挑选。每张图依次为清图、公开视觉条件、七个模型真实输出；各模型原生输入路由的完整prompt和证据留在外部图册。图中可见的标记残留或编辑错误未被修图去除。",
        "",
    ]
    lines += [
        "本组图的两条canonical任务如下；这是本图的目标说明，不是S3/S4-noref编辑器额外收到的文字：",
        "",
        "- **U1**：将粉蓝色立面的中层阳台栏杆改成白色。`Change the color of the middle-floor balcony railing on the pink-and-blue facade to white.`",
        "- **U2**：将201号门前的圆形绿植替换为红花天竺葵。`Replace the round leafy plant in front of door 201 with a red-flowering geranium plant.`",
        "",
    ]
    for item in data["figures"]:
        lines += [
            f"### {item['setting']}",
            "",
            f"![{item['setting']}：固定同例七模型实际输出]({item['path']})",
            "",
        ]
    lines += [
        "## 全部70行与95%置信区间",
        "",
        "单位均为%。每行保留实际分子/分母；MIRAGE S1的失败仍计入完整分母。",
        "",
        "<details>",
        "<summary>展开完整当前dev20统计表</summary>",
        "",
        "| 模型 | Setting | UP分子/分母 | UP | UP 95% CI | JP分子/分母 | JP | JP 95% CI | 生成/规划失败 | Judge缺分 |",
        "|---|---|---:|---:|---|---:|---:|---|---:|---:|",
    ]
    for model in MODELS:
        for setting in SETTINGS:
            r = rows[model, setting]
            lines.append(
                f"| {SHORT[model]} | {setting} | {r['known_pass_units']}/{r['unit_denominator']} | {percent(r['UnitPass'])} | {ci_text(r['bootstrap']['UnitPass']['CI95'])} | {r['known_joint_pass_cases']}/{r['case_denominator']} | {percent(r['JointPass'])} | {ci_text(r['bootstrap']['JointPass']['CI95'])} | {r['generation_failed_cases']} | {r['missing_cases']} |"
            )
    lines += [
        "",
        "</details>",
        "",
        "## 尚未完成",
        "",
        "| 项目 | 当前状态 |",
        "|---|---|",
        "| 正式冻结与test主结果 | **待评测；等待下一次确认** |",
        "| 人工标记残留率、独立双人一致性κ | **待评测**；已提供随机十例材料，AI目视不算人工标签 |",
        "| GT selector paste-back诊断 | **待评测**；不称上界，不替换主结果 |",
        "| 尚未执行的消融与扩展补充 | **待评测**；本页不填估计数字 |",
        "| 完整模型运行GPU-hours | 尚未汇总；不由请求秒数推算 |",
        "",
        "## 数据、原始结果与复现",
        "",
        "仓库只保存当前聚合统计、公开展示图和生成脚本；原始prompt、GT、逐请求评分与输出保留在外部挂载目录。",
        "",
        f"- 数据manifest：`{p['case_manifest']['path']}`",
        f"- 当前run：`{p['run_root']}`",
        f"- 原始模型输出：`{p['raw_outputs']}`",
        f"- canonical评分与overlay：`{p['canonical_scores']}`",
        f"- [外部完整报告]({p['external_report']}) · [700组抽检图册与最终prompt]({p['external_gallery']})",
        f"- 主报告SHA256：`{SOURCE_SHA}`",
        f"- 数据manifest SHA256：`{p['case_manifest']['sha256']}`",
        f"- 独立统计核验：{data['statistical_checks']['checks_passed']:,}/{data['statistical_checks']['checks_total']:,}项通过；源文件SHA、固定样例SHA见[聚合JSON](assets/results/latest_dev20.json)。",
        "",
        "在独立CPU环境重绘当前聚合结果，无需权重、GPU、Judge或原始私有数据：",
        "",
        "```bash",
        "python -m pip install -r scripts/results_plot_requirements.txt",
        "python scripts/render_current_results.py",
        "```",
        "",
        "脚本默认读取仓库中的当前聚合JSON，不重新计算评分。只有显式提供`--source-report`时，才从固定SHA的最新原始REPORT提取允许公开的聚合字段；不会写回原始结果。",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1] / "docs")
    parser.add_argument("--source-report", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    aggregate = root / "assets/results/latest_dev20.json"
    if args.source_report:
        write(aggregate, export_aggregate(args.source_report.resolve(), root))
    data = read(aggregate)
    rows = validate(data, root)
    versions = heatmaps(data, rows, root)
    csv_table(data, root / "assets/results/latest_dev20.csv")
    document = root / "RESULTS.md"
    write(document, markdown(data, rows))
    from PIL import Image

    checks = {
        "current_rows": len(rows),
        "derived_items": sum(map(len, data["derived"].values())),
        "K_buckets": sum(len(r["by_K"]) for r in rows.values()),
        "s2_supplements": len(data["s2_discard_supplement"]),
        "local_links": 0,
        "external_path_links": 0,
        "embedded_images": 0,
        "private_data_not_exported": True,
    }
    for match in re.finditer(r"(!?)\[[^\]]*\]\(([^)]+)\)", document.read_text()):
        target = match.group(2)
        if target.startswith(("http://", "https://", "#")):
            continue
        if Path(target).is_absolute():
            checks["external_path_links"] += 1
            continue  # A public aggregate-only replay need not mount private evidence.
        path = document.parent / target
        require(path.exists(), f"Broken result document link: {target}")
        checks["local_links"] += 1
        if match.group(1):
            with Image.open(path) as image:
                image.load()
            checks["embedded_images"] += 1
    with (root / "assets/results/latest_dev20.csv").open() as stream:
        csv_rows = list(csv.DictReader(stream))
    require(len(csv_rows) == len(rows), "CSV coverage mismatch")
    files = [
        document,
        aggregate,
        root / "assets/results/latest_dev20.csv",
        *sorted((root / "assets/results").glob("*_heatmap.*")),
        *(root / f["path"] for f in data["figures"]),
    ]
    receipt = {
        "status": "passed",
        "checks": checks,
        "source_report_sha256": SOURCE_SHA,
        "script_sha256": sha(__file__),
        "plotting_versions": versions,
        "artifacts": {str(p.relative_to(root)): sha(p) for p in files},
        "new_model_calls": 0,
        "new_judge_calls": 0,
        "raw_results_changed": False,
    }
    write(root / "assets/results/render_validation.json", receipt)
    print(
        json.dumps(
            {"status": receipt["status"], "root": str(root), "checks": checks}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
