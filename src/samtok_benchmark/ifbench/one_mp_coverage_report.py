"""Render verified one-image setting diagnostics, never a population estimate."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from PIL import Image

from samtok_benchmark.io import sha256_file, write_json
from samtok_benchmark.paths import repository_root
from .fairness_dev_plan import MODELS, SETTINGS, check_hash, read, verify_task
from .fairness_dev_worker import binding, verify_existing
from .one_mp_probe import load_plan as load_probe
from .one_mp_coverage import load_plan as load_coverage
from .one_mp_report import sheet


def verified_diagnostic(directory, probe, coverage):
    """Read and independently verify the frozen ledger without rewriting scores."""
    from . import one_mp_judge as diagnostic_api
    from . import fairness_dev_judge as judge_api

    directory = Path(directory).resolve()
    context = diagnostic_api.load_plan(directory / "plan.json", helper_root=directory / "repo")
    for name, bundle in (("probe", probe), ("coverage", coverage)):
        if context["source_contexts"][name]["plan_path"] != Path(bundle).resolve() / "plan.json":
            raise ValueError("Judge report belongs to different generation source plans")
    report_path = directory / "results/REPORT.json"
    completion = read(directory / "results/COMPLETED.json")
    if (
        completion.get("scope") != diagnostic_api.SCOPE
        or completion.get("formal_test") is not False
        or completion.get("plan_sha256") != context["plan_sha256"]
    ):
        raise ValueError("Diagnostic completion belongs to a different plan/scope")
    check_hash(report_path, completion["summary_report_sha256"])
    detail_path = directory / "results/DIAGNOSTIC.json"
    check_hash(detail_path, completion["report_sha256"])
    report = read(report_path)
    if (
        report.get("schema") != diagnostic_api.SCHEMA
        or report.get("scope") != diagnostic_api.SCOPE
        or report.get("case_ids") != context["case_ids"]
        or report.get("model_order") != MODELS
        or report.get("settings") != SETTINGS
        or report.get("ready_for_report") is not True
        or report.get("formal_test") is not False
        or report.get("population_estimate") is not False
        or report.get("confidence_intervals") is not None
        or report.get("plan_sha256") != context["plan_sha256"]
        or report.get("run_id") != context["run_id"]
        or report.get("diagnostic_path") != str(detail_path)
        or report.get("diagnostic_sha256") != completion["report_sha256"]
    ):
        raise ValueError("Diagnostic report is not the completed fixed one-source ledger")
    bindings, jobs = diagnostic_api.collect(context)
    cache = judge_api.Cache(context["plan"]["cache_index"], context["config"])
    diagnostic_api.verify_records(context, jobs, cache)
    _, raws, effectives, admitted = judge_api.paths(context)
    values = {}
    for key in jobs:
        path = effectives / f"{key}.json"
        if not path.exists():
            raise ValueError("Completed diagnostic has an unscored/unattempted generated output")
        values[key] = read(path)
    if len(report["rows"]) != len(bindings) or len(bindings) != 70:
        raise ValueError("Diagnostics must contain exactly 70 logical rows")
    for row, bound in zip(report["rows"], bindings, strict=True):
        if any(row.get(key) != value for key, value in bound.items()):
            raise ValueError("Diagnostic row differs from the original generation binding")
        if type(row.get("unit_count")) is not int or row["unit_count"] != 5:
            raise ValueError("Diagnostic unit denominator must be exactly five")
        generated = bound["generation_status"] == "generated"
        value = values.get(bound["judge_key"])
        if generated:
            key = bound["judge_key"]
            effective_path = effectives / f"{key}.json"
            raw_path = raws / f"{key}.json"
            expected_raw = str(raw_path) if raw_path.exists() else None
            if (
                row.get("effective_path") != str(effective_path)
                or row.get("effective_sha256") != sha256_file(effective_path)
                or row.get("raw_path") != expected_raw
                or row.get("raw_sha256") != (sha256_file(raw_path) if expected_raw else None)
                or row.get("judge_status") != value["status"]
                or row.get("scores") != value.get("scores")
                or value["key"] != key
                or value["run_id"] != context["run_id"]
                or value["output_sha256"] != bound["output_sha256"]
            ):
                raise ValueError("Diagnostic row differs from the verified raw/effective answer")
        else:
            if bound["generation_status"] not in judge_api.FAILURES:
                raise ValueError("Completed diagnostic contains nonterminal generation or N/A")
            if row.get("judge_status") != bound["generation_status"] or any(
                row.get(key) is not None
                for key in (
                    "judge_key",
                    "effective_path",
                    "effective_sha256",
                    "raw_path",
                    "raw_sha256",
                    "scores",
                )
            ):
                raise ValueError("Generation failures cannot acquire a synthetic Judge answer")
        if not generated:
            units, joint = 0, False
        elif value["status"] == "judge-failed":
            units = joint = None
            if row.get("scores") is not None:
                raise ValueError("Judge failures cannot carry scored atoms")
        elif value["status"] == "scored":
            scores = value["scores"]
            units = sum(all(unit[d]["pass"] for d in "EPQ") for unit in scores["units"])
            joint = units == 5 and all(scores["global_" + d]["pass"] for d in "PQ")
        else:
            raise ValueError("Diagnostic Judge status is not terminal")
        if (
            row.get("unit_pass_count") != units
            or type(row.get("unit_pass_count")) is not type(units)
            or row.get("joint_pass") != joint
            or type(row.get("joint_pass")) is not type(joint)
            or row.get("judge_missing") is not (units is None)
        ):
            raise ValueError("Pass counts differ from verified scores/failure/missing policy")
    rows = report["rows"]
    summary = {
        "logical_requests": len(bindings),
        "unique_generated_keys": len(jobs),
        "new_admitted_calls": len(list(admitted.glob("*.json"))),
        "new_raw_answers": len(list(raws.glob("*.json"))),
        "reused_effective_keys": sum("cache_reuse" in value for value in values.values()),
        "deterministic_repairs": sum(
            value.get("deterministic_repair_used", False) and "cache_reuse" not in value
            for value in values.values()
        ),
        "scored_logical": sum(row["judge_status"] == "scored" for row in rows),
        "judge_failed_logical": sum(row["judge_status"] == "judge-failed" for row in rows),
        "judge_pending_logical": 0,
        "generation_failed_logical": sum(
            row["generation_status"] in judge_api.FAILURES for row in rows
        ),
        "generation_pending_logical": 0,
        "missing_logical": sum(row["judge_missing"] for row in rows),
        "unique_effective_statuses": dict(Counter(value["status"] for value in values.values())),
        "source_logical_counts": dict(Counter(row["generation_source"] for row in bindings)),
    }
    all_scored = all(value["status"] == "scored" for value in values.values())
    if (
        report["summary"] != summary
        or report.get("all_generated_outputs_scored") is not all_scored
        or completion.get("all_generated_outputs_scored") is not all_scored
        or completion.get("logical_requests") != len(bindings)
        or completion.get("unique_judge_keys") != len(jobs)
    ):
        raise ValueError("Diagnostic summary/completion counts differ from actual verified records")
    return report


def obsolete_output_thumbnails(provenance, docs):
    """Validate every deletion before touching any derived image."""
    docs = Path(docs).resolve()
    assets = docs / "assets/current"
    if not assets.resolve().is_relative_to(docs):
        raise ValueError("Thumbnail directory escapes documentation root")
    deletions = []
    for item in provenance["figures"]:
        relative = Path(item["path"])
        if not relative.name.startswith("outputs-"):
            continue
        path = docs / relative
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or path.suffix != ".jpg"
            or path.is_symlink()
            or path.resolve().parent != assets.resolve()
        ):
            raise ValueError("Refusing to delete a file outside registered output thumbnails")
        if path.exists():
            check_hash(path, item["sha256"])
            deletions.append(path)
    return deletions


def render(probe, coverage, judge, docs=None):
    probe, coverage, judge = [Path(p).resolve() for p in (probe, coverage, judge)]
    docs = Path(docs) if docs else repository_root() / "docs"
    assets = docs / "assets/current"
    plans = [
        load_probe(probe / "plan.json", helper_root=probe / "repo"),
        load_coverage(coverage / "plan.json", helper_root=coverage / "repo"),
    ]
    cid = plans[1]["case_ids"][0]
    records, tasks = {}, {}
    counts = {m: Counter() for m in MODELS}
    for plan in plans:
        for task in plan["tasks"]:
            verify_task(plan, task)
            record = read(task["result_path"])
            verify_existing(record, binding(plan, task, "edit"))
            if task["key"] in records:
                raise ValueError("Overlapping generation requests cannot be counted twice")
            if record["status"] == "generated":
                with Image.open(record["output_image"]) as im:
                    if list(im.size) != read(task["canvas_transform"])["source_size"]:
                        raise ValueError("Output is not on the canonical canvas")
            records[task["key"]] = record
            tasks[task["key"]] = task
            counts[task["model"]][record["status"]] += 1
    diagnostic_path = judge / "results/REPORT.json"
    diagnostic = verified_diagnostic(judge, probe, coverage)
    rows = {(r["model"], r["setting"], r["case_id"]): r for r in diagnostic["rows"]}
    expected = {(m, s, cid) for m in MODELS for s in SETTINGS}
    if len(rows) != 70 or set(rows) != expected or len(diagnostic["rows"]) != 70:
        raise ValueError("Diagnostics must cover each fixed model/setting exactly once")
    summary = diagnostic["summary"]
    md = [
        "# 当前评测结果与分析",
        "",
        "**统一约1MP；以下为极小规模端到端验证。正式全量结果仍待评测。**",
        "",
        f"固定K=5 dev图 `{cid}` 覆盖七模型×十种setting，共70个组合。另有固定K=2图在S1/S3-point/S5下的21个生成请求，合计91条固定生成请求；本轮补齐其中尚未执行的49条请求。输入、prompt、权重、原生参数和seed42保持冻结，不按分数择优或重采样。",
        "",
        "Judge只评分上述同一张K=5图的70个组合。调用使用原始源图、canonical ref、GT selector及回源输出，不提供setting或模型实际输入形式。每个组合只有一张图，因此结果仅用于核对链路和样例表现，不给总体排名、全量通过率或置信区间。",
        "",
        "## 执行状态",
        "",
        "| 模型 | 成功出图 / 13 | 生成或原生规划失败 | 已评分 / 10 | Judge失败或缺分 |",
        "|---|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        group = [r for r in rows.values() if r["model"] == model]
        scored = sum(r["judge_status"] == "scored" for r in group)
        missing = sum(
            r["generation_status"] == "generated" and r["judge_status"] != "scored" for r in group
        )
        failed = sum(v for status, v in counts[model].items() if status != "generated")
        md.append(
            f"| {model} | {counts[model]['generated']}/13 | {failed} | {scored}/10 | {missing} |"
        )
    md += [
        "",
        f"{summary['logical_requests']}条逻辑请求对应{summary['unique_generated_keys']}个独立评分key；"
        f"实际新增{summary['new_admitted_calls']}次Judge调用，保存{summary['new_raw_answers']}份原始响应，"
        f"{summary['scored_logical']}条逻辑请求获得有效评分。确定性JSON恢复{summary['deterministic_repairs']}条，"
        "不产生额外推理。生成失败与Judge缺分分开记录；缺分不能补0。",
        "",
        "## 每个 setting 的完整链路",
        "",
        "单元格依次表示“生成状态 / Judge状态”；成功出图不代表编辑正确。",
        "",
        "| Setting | " + " | ".join(MODELS) + " |",
        "|---|" + "---|" * len(MODELS),
    ]
    for setting in SETTINGS:
        cells = []
        for model in MODELS:
            r = rows[model, setting, cid]
            cells.append(
                ("已出图" if r["generation_status"] == "generated" else r["generation_status"])
                + " / "
                + ("已评分" if r["judge_status"] == "scored" else r["judge_status"])
            )
        md.append(f"| {setting} | " + " | ".join(cells) + " |")
    md += [
        "",
        "## 固定单图的评分诊断",
        "",
        "每格为 **通过单元数/5；整图是否通过**。单元通过要求E=4且P/Q≥3；整图通过还要求五个单元全部通过、全局P/Q≥3。它们分别对应此样例的UnitPass和JointPass判定，不能当作全数据成绩。",
        "",
        "| Setting | " + " | ".join(MODELS) + " |",
        "|---|" + "---|" * len(MODELS),
    ]
    for setting in SETTINGS:
        cells = []
        for model in MODELS:
            r = rows[model, setting, cid]
            if r["unit_pass_count"] is None:
                cells.append("缺分")
            else:
                cells.append(
                    f"{r['unit_pass_count']}/{r['unit_count']}；"
                    + ("通过" if r["joint_pass"] else "未通过")
                )
        md.append(f"| {setting} | " + " | ".join(cells) + " |")
    md += [
        "",
        "## 全量主结果",
        "",
        "全量1,084图、3,872单元的UnitPass / JointPass及95%配对bootstrap置信区间均待评测。",
        "",
        "| Setting | " + " | ".join(MODELS) + " |",
        "|---|" + "---|" * len(MODELS),
    ]
    md += [f"| {s} | " + " | ".join(["待评测"] * len(MODELS)) + " |" for s in SETTINGS]
    md += [
        "",
        "## 十种 setting 的实际输入和七模型输出",
        "",
        "每组展示共同清图I、公开标注图A和七模型回源输出。不同方法实际采用I/A及原生区域的方式见[详细用法](USAGE.md)，最终公开prompt见[输入样例](INPUT_EXAMPLES.md)。",
        "",
    ]
    provenance_path = assets / "PROVENANCE.json"
    old = read(provenance_path)
    obsolete = obsolete_output_thumbnails(old, docs)
    figures = [item for item in old["figures"] if Path(item["path"]).name.startswith("inputs-")]
    for setting in SETTINGS:
        task = tasks[f"qwen21/{setting}/{cid}"]
        public = read(task["public_request"])
        inputs = read(Path(task["public_request"]).with_name("inputs.json"))
        items = [
            ("Clean source I / 1MP", public["source"]["path"]),
            (
                "Annotation A" if inputs["annotation"] else "S1 / no region annotation",
                inputs["annotation"]["path"] if inputs["annotation"] else public["source"]["path"],
            ),
        ]
        for model in MODELS:
            record = records[f"{model}/{setting}/{cid}"]
            items.append(
                (
                    model + " / " + record["status"],
                    record.get("output_image") if record["status"] == "generated" else None,
                )
            )
        path = assets / f"comparison-{setting}-{cid}.jpg"
        sheet(items, path, columns=3, cell=(520, 400))
        figures.append(
            {
                "path": str(path.relative_to(docs)),
                "sha256": sha256_file(path),
                "sources": [{"path": p, "sha256": sha256_file(Path(p))} for _, p in items if p],
            }
        )
        md += [
            f"### {setting}",
            "",
            f"![{setting} 实际输入和七模型输出](assets/current/{path.name})",
            "",
        ]
    md += [
        "## 结论与边界",
        "",
        "- 全部七模型×十种setting均有固定样例进入生成与评分核验；具体原生失败或缺分以表中实际状态为准。",
        "- 成功出图、Judge返回有效分数、编辑任务通过是三个独立结论。标记残留、漏编辑或原生定位错误均保留，不据诊断结果修改prompt或模型配置。",
        "- RePlan/MIRAGE保留原生近1MP输出网格，全部输出按冻结几何回到源图尺寸；Judge口径未改变。",
        "- MICE极小mask的原生绑定量化限制见[使用说明](USAGE.md)；不使用膨胀、GT修复或外部组件提高表现。",
        "- 单图不能说明模型总体能力或稳定性；正式成绩需要全量执行。人工标记残留率、κ及GT selector paste-back诊断仍待单独完成。",
        "",
        "## 结果与复现",
        "",
        f"- 共享输入和首批42输出：`{probe}`。",
        f"- 补齐49请求与输出：`{coverage}`。",
        f"- 70组合Judge计划、原始响应和有效评分：`{judge}`。",
        f"- 单图诊断记录：`{diagnostic_path}`；SHA256 `{sha256_file(diagnostic_path)}`。",
        "- 记录、raw/effective响应和缩略图均来自真实文件；源SHA见[PROVENANCE.json](assets/current/PROVENANCE.json)。",
        "- 正式运行入口及待发布状态见[FULL_RUN.md](FULL_RUN.md)。",
        "",
    ]
    # Remove only previously registered output thumbnails, never actual results.
    for path in obsolete:
        path.unlink()
    write_json(
        provenance_path,
        {
            "generation_plans": [
                {"path": str(b / "plan.json"), "sha256": sha256_file(b / "plan.json")}
                for b in (probe, coverage)
            ],
            "judge_report": {"path": str(diagnostic_path), "sha256": sha256_file(diagnostic_path)},
            "figures": figures,
        },
    )
    (docs / "RESULTS.md").write_text("\n".join(md))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--judge", type=Path, required=True)
    parser.add_argument("--docs", type=Path)
    args = parser.parse_args()
    render(args.probe, args.coverage, args.judge, args.docs)


if __name__ == "__main__":
    main()
