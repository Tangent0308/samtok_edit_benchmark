"""Verify four source-owned shards and compute a single whole-release paired report."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import time

from PIL import Image, ImageDraw, ImageFont, ImageOps

from samtok_benchmark.io import atomic_text, digest, sha256_file, write_json
from .full_plan import load_plan, NODES
from .fairness_dev_judge import (
    load_plan as judge_context,
    collect,
    Cache,
    paths,
    verify_effective,
    verify_admissions,
    read,
)
from .fairness_dev_report import (
    Bootstrap,
    make_row,
    derived,
    setting_comparisons,
    show_rate,
    input_route,
    example,
    calls_ledger,
    SEED,
    REPLICATES,
)


def verified_node(plan_path, node):
    context = judge_context(plan_path, node_id=node)
    cache = Cache(context["plan"]["cache_index"], context["config"])
    if cache.index_sha256 != context["plan"]["cache_index_sha256"]:
        raise ValueError("Frozen Judge cache index changed")
    bindings, jobs = collect(context)
    from .fairness_dev_judge import FAILURES

    if any(
        b["generation_status"] not in FAILURES | {"generated", "not-applicable"} for b in bindings
    ):
        raise ValueError(f"Node {node} has unattempted generation")
    directory, raws, effectives, admissions = paths(context)
    verify_admissions(context, jobs)
    expected_keys = set(jobs)
    for folder in (raws, effectives, admissions):
        if {p.stem for p in folder.glob("*.json")} - expected_keys:
            raise ValueError(f"Node {node} has unregistered Judge artifacts")
    effective = {}
    for key, job in jobs.items():
        path = effectives / f"{key}.json"
        if not path.exists():
            raise ValueError(f"Node {node} has unattempted Judge key: {key}")
        value = read(path)
        verify_effective(value, job, context, cache)
        effective[key] = value
    return context, bindings, jobs, effective


def verify_node(plan_path, node):
    context, bindings, jobs, effective = verified_node(plan_path, node)
    result = {
        "node": node,
        "plan_digest": context["plan"]["digest"],
        "logical_requests": len(bindings),
        "unique_judge_keys": len(jobs),
        "generation_statuses": dict(Counter(b["generation_status"] for b in bindings)),
        "judge_statuses": dict(Counter(v["status"] for v in effective.values())),
        "all_generation_terminal": True,
        "all_judge_terminal": True,
        "missing_judge_scores": sum(v["status"] != "scored" for v in effective.values()),
        "checked_at_epoch": time.time(),
    }
    write_json(context["root"] / "VERIFICATION.json", result)
    return result


def merge_verified(parts, plan):
    """Reject missing, duplicate or foreign source ownership; never select a score."""
    bound, jobs, effective = {}, {}, {}
    owners = {cid: int(n) for n, ids in plan["node_assignments"].items() for cid in ids}
    seen_nodes = set()
    for node, bindings, node_jobs, node_effective in parts:
        if node in seen_nodes:
            raise ValueError("A node was merged twice")
        seen_nodes.add(node)
        for b in bindings:
            key = (b["model"], b["setting"], b["case_id"])
            if key in bound or owners.get(b["case_id"]) != node:
                raise ValueError("Duplicate logical request or wrong source owner")
            bound[key] = b
        for key, job in node_jobs.items():
            if key in jobs or owners.get(job["case_id"]) != node:
                raise ValueError("Cross-node Judge-key collision or wrong canonical source owner")
            jobs[key] = job
        if set(node_effective) != set(node_jobs):
            raise ValueError("Node effective records do not cover its exact generated key set")
        effective.update(node_effective)
    expected = {(t["model"], t["setting"], t["case_id"]) for t in plan["tasks"]}
    if seen_nodes != set(range(NODES)) or set(bound) != expected:
        raise ValueError("Four-node merge does not cover the full frozen Cartesian product")
    return bound, jobs, effective


def execution_history(root, plan, code_sha):
    """Keep all stopped/resumed controller costs; never invent SIGKILL duration."""
    records = []
    for node in range(NODES):
        directory = root / "nodes" / f"node-{node}"
        completed = read(directory / "COMPLETED.json")
        found_completion = False
        for path in sorted((directory / "executions").glob("*/receipt.json")):
            value = read(path)
            if (
                value.get("node") != node
                or value.get("plan_digest") != plan["digest"]
                or value.get("code_manifest_sha256") != code_sha
                or value.get("execution_id") != path.parent.name
            ):
                raise ValueError("Node execution receipt identity differs from frozen plan")
            if value == completed:
                found_completion = True
            seconds = value.get("wall_seconds")
            if seconds is not None and (type(seconds) not in (int, float) or seconds < 0):
                raise ValueError("Invalid measured controller duration")
            records.append({"receipt_path": str(path), **value})
        if not found_completion:
            raise ValueError("Node completion has no matching original execution receipt")
    return records


def heatmap(rows, models, settings, metric, path):
    width, height = 1450, 720
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    draw.text((20, 12), f"IF-Bench | all 1084 sources | {metric} (%)", fill="black", font=font)
    names = ["Qwen2511", "Qwen2.1", "FLUX3", "RePlan", "MIRAGE", "MICE", "FLUX2-9B"]
    for x, label in enumerate(names):
        draw.text((160 + x * 180, 55), label, font=font, fill="black")
    for y, setting in enumerate(settings):
        draw.text((15, 100 + y * 55), setting, font=font, fill="black")
        for x, model in enumerate(models):
            value = rows[model, setting][metric]
            color = (
                (225, 225, 225)
                if value is None
                else (int(238 - 180 * value), int(245 - 125 * value), int(250 - 60 * value))
            )
            left, top = 150 + x * 180, 88 + y * 55
            draw.rectangle((left, top, left + 174, top + 51), fill=color)
            label = "missing" if value is None else f"{100 * value:.2f}"
            draw.text((left + 50, top + 15), label, font=font, fill="black")
    draw.text(
        (20, 680),
        "One fixed 0-100% scale; missing scores are not zeros. Paired 95% CIs are in the tables.",
        font=small,
        fill="#444444",
    )
    canvas.save(path)


def gallery(context, bound, directory):
    plan = context["plan"]
    selected = set(plan["audit_case_ids"])
    examples = []
    for task in plan["tasks"]:
        if task["case_id"] in selected:
            b = bound[task["model"], task["setting"], task["case_id"]]
            examples.append(
                example(
                    context, task, b, directory, selection_label="frozen whole-release audit sample"
                )
            )
    md = [
        "# 全量评测固定人工抽检材料",
        "",
        f"每模型×setting使用相同10张图；seed={plan['audit_seed']}，按源图ID哈希排序，名单在推理前冻结。共{len(examples)}组；不按分数挑图。",
        "",
        "这是待人工检查的材料，不冒称人工残留率或κ已完成。原生区域字段、最终prompt及实际调用路径保留。",
        "",
    ]
    for item in examples:
        relative = Path(item["figure"]).relative_to(directory)
        md += [
            f"## {item['model']} / {item['setting']} / {item['case_id']}",
            "",
            f"![实际输入输出]({relative})",
            "",
            "```text",
            item["prompt"] or "(see native request)",
            "```",
            "",
            f"请求：`{item['request_path']}`；调用：`{item['call_path']}`；状态：{item['status']}",
            "",
        ]
        if any(
            item[k]
            for k in (
                "native_local_inputs",
                "planner_inputs",
                "actual_editor_global_prompt",
                "actual_editor_region_guidance",
            )
        ):
            md += [
                "```json",
                json.dumps(
                    {
                        "native_inputs": item["native_local_inputs"],
                        "planner_inputs": item["planner_inputs"],
                        "actual_editor_global_prompt": item["actual_editor_global_prompt"],
                        "actual_editor_region_guidance": item["actual_editor_region_guidance"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "```",
                "",
            ]
    atomic_text(directory / "AUDIT_GALLERY.md", "\n".join(md) + "\n")
    return examples


def comparisons(context, bound, directory):
    plan = context["plan"]
    cid = plan["audit_case_ids"][0]
    case = context["cases"][cid]
    source = Path(plan["dataset_root"]) / case["source"]["image"]
    tasks = {(t["model"], t["setting"], t["case_id"]): t for t in plan["tasks"]}
    result = {}
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    for setting in plan["settings"]:
        request = read(tasks["qwen21", setting, cid]["request_path"])
        panels = [
            ("Clean source", source),
            ("Public annotation / source", Path(request["images"][-1])),
        ]
        for model in plan["model_order"]:
            b = bound[model, setting, cid]
            panels.append(
                (
                    model + " | " + b["generation_status"],
                    Path(b["output_image"]) if b.get("output_image") else None,
                )
            )
        canvas = Image.new("RGB", (1560, 1440), "white")
        draw = ImageDraw.Draw(canvas)
        for i, (label, path) in enumerate(panels):
            x, y = (i % 3) * 520, (i // 3) * 480
            draw.text((x + 7, y + 8), label, font=font, fill="black")
            if path:
                with Image.open(path) as im:
                    tile = ImageOps.contain(im.convert("RGB"), (508, 430))
                canvas.paste(tile, (x + (520 - tile.width) // 2, y + 44 + (430 - tile.height) // 2))
        path = directory / "comparisons" / f"{setting}__{cid}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(path, quality=89)
        result[setting] = str(path.relative_to(directory))
    return result


def markdown(report):
    md = [
        "# IF-Bench 全量评测结果",
        "",
        "**所有1,084张图合并报告，不分别列dev/test成绩。** 每模型×setting的完整分母为1,084张源图、3,872个编辑单元。",
        "本总结果包含曾用于开发验证的数据；历史划分与暴露记录保留，因此不将其称为独立未见测试集估计。",
        "",
        "UnitPass：E=4且P/Q≥3的编辑单元比例。JointPass：同图全部单元通过且全局P/Q≥3的源图比例。95%区间按全部源图做配对bootstrap，10,000次、seed20261027；不平均四机分数或区间。",
        "生成/原生规划/输入超限失败保留分母；Judge缺分保留缺失，不补零。N/A不补结果。",
        "",
        f"完整分数行：{sum(r['complete'] for r in report['rows'])}/70；生成状态：`{json.dumps(report['generation_counts'], ensure_ascii=False)}`。",
        "",
        "![UnitPass](unitpass_heatmap.png)",
        "",
        "![JointPass](jointpass_heatmap.png)",
        "",
    ]
    md += setting_comparisons(report)
    md += ["## 固定推理方式", "", "| 模型 | Setting | 实际输入方式 |", "|---|---|---|"]
    for r in report["rows"]:
        md.append(f"| {r['model']} | {r['setting']} | {input_route(r['model'], r['setting'])} |")
    md += ["", "## 派生指标", "", "| 模型 | 口径 | 指标 | 值 [95% CI] |", "|---|---|---|---|"]
    for model, values in report["derived"].items():
        for value in values:
            shown = (
                str(value["unavailable_reason"])
                if value["value"] is None
                else f"{value['value']:.6f} {value['bootstrap']['CI95']}"
            )
            md.append(f"| {model} | {value['metric']} | {value['diagnostic']} | {shown} |")
    md += [
        "",
        "Δ_lang=S2−S3；G_region=S2−S1；R_mod=min(S3)/max(S3)；C_mix=mean(S3)−S4-noref。差值为比例点；分母为0时比值为N/A。",
        "",
        "## 按目标数K的JointPass",
        "",
        "| 模型 | Setting | K2 | K3 | K4 | K5 |",
        "|---|---|---|---|---|---|",
    ]
    for row in report["rows"]:
        md.append(
            f"| {row['model']} | {row['setting']} | "
            + " | ".join(show_rate(row["by_K"][str(k)], "JointPass") for k in range(2, 6))
            + " |"
        )
    md += [
        "",
        "## S2丢弃区域补充",
        "",
        "精确复用S1；不替换主行，不按结果择优，不新增采样。",
        "",
        "| 模型 | S2 setting | UP [95% CI] | JP [95% CI] |",
        "|---|---|---|---|",
    ]
    for r in report["s2_discard_supplement"]:
        md.append(
            f"| {r['model']} | {r['setting']} | {show_rate(r, 'UnitPass')} | {show_rate(r, 'JointPass')} |"
        )
    md += [
        "",
        "## 固定同例比较",
        "",
        f"同一冻结抽检case `{report['comparison_case']}`，仅缩略显示真实输出。左上清图、上中公开标注，其余七模型；各模型实际输入/原生区域与完整prompt见[抽检图册](AUDIT_GALLERY.md)。",
        "",
    ]
    for unit in report["comparison_tasks"]:
        md.append(f"- {unit['id']}: {unit['instruction']}")
    for setting, path in report["comparison_figures"].items():
        md += ["", f"### {setting}", "", f"![{setting}七模型对比]({path})"]
    md += [
        "",
        "## 复现与运行记录",
        "",
        f"全局plan：`{report['plan_path']}`；SHA256：`{report['plan_sha256']}`。",
        f"运行代码commit：`{report['source_commit']}`；采样seed：{report['seed']}。",
        "所有权重版本、原生配置、额外planner调用、旧结果复用链、失败和实际耗时在REPORT.json、CALLS.json及各node的执行回执中。缓存不计新增调用。",
        "统计与图册生成不调用编辑模型或Judge。人工标记残留率、κ、GT selector paste-back诊断和另行协议消融未由这轮主表执行器自动完成；不编造其数字。",
        "",
    ]
    return "\n".join(md)


def aggregate_if_ready(bundle):
    bundle = Path(bundle).resolve()
    plan_path = bundle / "plan.json"
    plan = load_plan(plan_path)
    ready = read(bundle / "READY.json")
    if ready["plan_sha256"] != sha256_file(plan_path) or ready[
        "code_manifest_sha256"
    ] != sha256_file(bundle / "code_manifest.json"):
        raise ValueError("Full report requires the unchanged published plan/source manifest")
    root = Path(plan["results_root"])
    directory = root / "report"
    if (directory / "COMPLETED.json").exists():
        completed = read(directory / "COMPLETED.json")
        if completed["plan_digest"] != plan["digest"] or completed["report_sha256"] != sha256_file(
            directory / "REPORT.json"
        ):
            raise ValueError("Completed report identity changed")
        return completed
    receipts = []
    for node in range(NODES):
        path = root / "nodes" / f"node-{node}" / "COMPLETED.json"
        if not path.exists():
            return {"status": "waiting-for-nodes", "missing_node": node, "new_inference_calls": 0}
        receipt = read(path)
        if (
            receipt["plan_digest"] != plan["digest"]
            or receipt["status"] != "completed"
            or receipt.get("node") != node
            or receipt.get("code_manifest_sha256") != sha256_file(bundle / "code_manifest.json")
        ):
            raise ValueError("Node completion does not belong to this global plan")
        receipts.append(receipt)
    directory.mkdir(parents=True, exist_ok=True)
    claim = directory / "ACTIVE"
    try:
        claim.mkdir()
    except FileExistsError:
        return {"status": "aggregation-already-claimed", "claim": str(claim)}
    write_json(
        claim / "owner.json",
        {"host": socket.gethostname(), "pid": os.getpid(), "time": time.time()},
    )
    try:
        parts = []
        contexts = []
        ledgers = []
        for node in range(NODES):
            print(f"Verifying node {node} before full-release aggregation.", flush=True)
            context, bindings, jobs, effective = verified_node(plan_path, node)
            contexts.append(context)
            parts.append((node, bindings, jobs, effective))
            ledgers.append(calls_ledger(context))
        bound, jobs, effective = merge_verified(parts, plan)
        executions = execution_history(root, plan, sha256_file(bundle / "code_manifest.json"))
        context = {
            **contexts[0],
            "root": root,
            "tasks": plan["tasks"],
            "case_ids": plan["case_ids"],
            "cases": {cid: c for ctx in contexts for cid, c in ctx["cases"].items()},
            "node_id": None,
        }
        boot = Bootstrap([len(context["cases"][cid]["units"]) for cid in context["case_ids"]])
        rows = []
        derived_values = {}
        for model in plan["model_order"]:
            model_rows = {}
            distributions = {}
            for setting in plan["settings"]:
                row, dist = make_row(model, setting, context, bound, effective, boot)
                rows.append(row)
                model_rows[setting] = row
                distributions[setting] = dist
            derived_values[model] = derived(model_rows, distributions)
        by_row = {(r["model"], r["setting"]): r for r in rows}
        for metric in ("UnitPass", "JointPass"):
            heatmap(
                by_row,
                plan["model_order"],
                plan["settings"],
                metric,
                directory / f"{metric.lower()}_heatmap.png",
            )
        examples = gallery(context, bound, directory)
        figures = comparisons(context, bound, directory)
        supplements = [
            {**r, "setting": s, "source_setting": "S1", "role": "supplement-only", "new_calls": 0}
            for r in rows
            if r["setting"] == "S1"
            for s in ("S2-point", "S2-box", "S2-mask")
        ]
        report = {
            "schema": "ifbench-full-release-report-v1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "plan_path": str(plan_path),
            "plan_sha256": sha256_file(plan_path),
            "plan_digest": plan["digest"],
            "source_commit": ready["source_commit"],
            "code_manifest_sha256": ready["code_manifest_sha256"],
            "seed": plan["seed"],
            "configuration_reference_sha256": plan["configuration_reference_sha256"],
            "assignments_sha256": plan["assignments_sha256"],
            "renderer_sha256": plan["renderer_sha256"],
            "protocol_revision": plan["protocol_revision"],
            "report_scope": "all-1084",
            "source_count": len(plan["case_ids"]),
            "units_per_model_setting": int(boot.ks.sum()),
            "case_ids": plan["case_ids"],
            "model_order": plan["model_order"],
            "settings": plan["settings"],
            "model_specifications": plan["model_specifications"],
            "judge_config": plan["judge_config"],
            "rows": rows,
            "derived": derived_values,
            "K_counts": dict(Counter(map(int, boot.ks))),
            "s2_discard_supplement": supplements,
            "generation_counts": dict(Counter(b["generation_status"] for b in bound.values())),
            "bootstrap": {
                "seed": SEED,
                "replicates": REPLICATES,
                "shared_indices_sha256": digest(boot.indices.tolist()),
                "cluster": "source image",
                "scope": "global 1084 sources; identical indices across all model/settings",
            },
            "judge_bindings": {
                "unique_output_keys": len(jobs),
                "statuses": dict(Counter(v["status"] for v in effective.values())),
            },
            "node_execution_receipts": receipts,
            "all_node_execution_receipts": executions,
            "audit_case_ids": plan["audit_case_ids"],
            "examples": examples,
            "comparison_case": plan["audit_case_ids"][0],
            "comparison_figures": figures,
            "comparison_tasks": [
                {"id": u["id"], "instruction": u["instruction_ref"]}
                for u in context["cases"][plan["audit_case_ids"][0]]["units"]
            ],
            "ready_for_review": all(r["complete"] or r["not_applicable"] for r in rows),
            "historical_exposure": read(plan["historical_exposure"]),
            "frozen": True,
            "new_model_calls_by_report": 0,
            "population_marker_residual_rate": None,
            "human_kappa": None,
            "pasteback_diagnostic": "not executed",
            "node_controller_reserved_gpu_hours": sum(
                r["wall_seconds"] * 8 / 3600 for r in executions if "wall_seconds" in r
            ),
            "controller_executions_with_unknown_duration": [
                r["receipt_path"] for r in executions if "wall_seconds" not in r
            ],
            "timing_scope": "All recorded stopped/resumed controller wall durations x 8; unknown SIGKILL durations remain missing; excludes bootstrap/platform queue and is not kernel-active GPU time",
        }
        write_json(directory / "REPORT.json", report)
        write_json(directory / "CALLS.json", {"nodes": ledgers, "history": plan["parent_run"]})
        atomic_text(directory / "REPORT.md", markdown(report))
        result = {
            "status": "completed"
            if report["ready_for_review"]
            else "completed-with-missing-judge-scores",
            "plan_digest": plan["digest"],
            "report": str(directory / "REPORT.md"),
            "report_sha256": sha256_file(directory / "REPORT.json"),
            "complete_rows": sum(r["complete"] for r in rows),
            "sources": len(plan["case_ids"]),
            "logical_requests": len(bound),
            "new_inference_calls": 0,
        }
        write_json(directory / "COMPLETED.json", result)
        return result
    except BaseException as error:
        write_json(
            directory / "ERROR.json",
            {"error": repr(error), "plan_digest": plan["digest"], "time": time.time()},
        )
        raise
    finally:
        (claim / "owner.json").unlink()
        claim.rmdir()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(aggregate_if_ready(a.bundle), ensure_ascii=False), flush=True)
