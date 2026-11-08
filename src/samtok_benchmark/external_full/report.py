"""Coverage-aware per-task tables and the official macro aggregation, without invented failure scores."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
import io
from pathlib import Path
import statistics

from samtok_benchmark.external_refedit.data import immutable, read
from samtok_benchmark.io import sha256_file
from . import VLM_TASKS
from .launch import select_cases
from .score import METRICS

GROUPS = {
    "Local Editing": ("add", "remove", "replace"),
    "Multi-object Editing": ("multi_object_add", "multi_object_remove"),
    "Implicit Reasoning": ("implicit_reasoning",),
    "Multi-turn (Turn 1)": ("multi_turn_add/turn1", "multi_turn_remove/turn1"),
    "Multi-turn (Turn 2)": ("multi_turn_add/turn2", "multi_turn_remove/turn2"),
    "Action": ("action",),
    "Location": ("location",),
    "Viewpoint": ("view",),
}
LABELS = {
    "LC-T": "LC-T ↑",
    "LC-I": "LC-I ↑",
    "PSNR": "PSNR (dB) ↑",
    "SSIM": "SSIM ↑",
    "LPIPS": "LPIPS ↓",
    "VLM": "GPT-5.4 (0–10) ↑",
}


def task_name(item):
    return item["task"] + (f"/turn{item['turn']}" if item["turn"] else "")


def mean(values):
    return statistics.fmean(values) if values else None


def aggregate(task_rows):
    by_task = {r["task"]: r for r in task_rows}
    groups = []
    for name, tasks in GROUPS.items():
        selected = [by_task[t] for t in tasks if t in by_task]
        if not selected:
            continue
        keys = ("VLM",) if tasks[0] in VLM_TASKS else METRICS
        complete = all(r["complete"] for r in selected) and len(selected) == len(tasks)
        means, official = {}, {}
        for key in keys:
            values = [
                r["valid_mean"][key] for r in selected if r["valid_mean"].get(key) is not None
            ]
            means[key] = mean(values) if len(values) == len(tasks) else None
            official[key] = (
                round(mean([round(v, 3) for v in values]), 3) if len(values) == len(tasks) else None
            )
        groups.append(
            {
                "group": name,
                "complete": complete,
                "aggregation": "equal-weight subtask means",
                "expected": sum(r["expected"] for r in selected),
                "scored": sum(r["scored"] for r in selected),
                "valid_mean": means,
                "official_rounded_mean": official,
            }
        )
    return groups


def report(bundle, run, scores, output, models, case_ids=None):
    index = read(Path(bundle) / "index.json")
    if index.get("benchmark") in {"interedit", "omni_iie"}:
        from .simple_report import report as simple_report

        return simple_report(bundle, run, scores, output, models, case_ids)
    cases = select_cases(index, case_ids)
    rows, per_case = {}, []

    def inspect(job):
        model, item = job
        cid, task = item["case_id"], task_name(item)
        generation = Path(run) / model / "edit" / cid / "result.json"
        score = (
            Path(scores) / model / cid / ("vlm.json" if item["task"] in VLM_TASKS else "local.json")
        )
        status = "not_generated"
        metrics = None
        result = None
        if generation.exists():
            result = read(generation)
            status = "score_missing" if result["status"] == "completed" else result["status"]
            if (
                result["status"] == "completed"
                and sha256_file(result["output_image"]) != result["output_sha256"]
            ):
                raise ValueError("Output changed before reporting")
            if score.exists():
                scored = read(score)
                if scored["identity"]["result_sha256"] != sha256_file(generation) or scored[
                    "identity"
                ]["output_sha256"] != result.get("output_sha256"):
                    raise ValueError("Score no longer binds to this output")
                status = scored["status"]
                metrics = scored.get("metrics")
        record = {
            "model": model,
            "case_id": cid,
            "task": task,
            "sequence_id": item["sequence_id"],
            "status": status,
            "metrics": metrics,
            "generation_status": result["status"] if result else "not_generated",
            "generation_record": str(generation) if result else None,
        }
        return record

    # Keep NAS verification bounded and parallel; do not serially re-read all 27,848 outputs.
    with ThreadPoolExecutor(max_workers=16) as pool:
        per_case = list(pool.map(inspect, ((m, x) for m in models for x in cases)))
    for model in models:
        tasks = {}
        for record in per_case:
            if record["model"] == model:
                tasks.setdefault(record["task"], []).append(record)
        task_rows = []
        for task, records in tasks.items():
            keys = ("VLM",) if task in VLM_TASKS else METRICS
            values = [
                r["metrics"]
                for r in records
                if r["status"] == "completed" and r["metrics"] is not None
            ]
            task_rows.append(
                {
                    "task": task,
                    "expected": len(records),
                    "scored": len(values),
                    "complete": len(values) == len(records),
                    "status_counts": dict(Counter(r["status"] for r in records)),
                    "valid_mean": {k: mean([r[k] for r in values]) for k in keys},
                }
            )
        rows[model] = {"tasks": task_rows, "groups": aggregate(task_rows)}
    result = {
        "schema": "compbench.full.report.v1",
        "bundle_digest": index["digest"],
        "scope": "full" if len(cases) == 3481 else "bounded-smoke",
        "case_ids": [x["case_id"] for x in cases],
        "models": list(models),
        "failure_policy": "No invented values; valid means and complete denominator/coverage reported together",
        "rows": rows,
        "per_case": per_case,
    }
    output = Path(output)
    immutable(output / "REPORT.json", result)
    lines = [
        "# CompBench 评测结果",
        "",
        f"范围：{result['scope']}，每方法 {len(cases)} 条请求。",
        "",
        "指标显示有效评分的均值，同时列出完整分母；覆盖不完整的行不代表完整全量成绩。",
        "",
    ]
    full = result["scope"] == "full"
    display_names = list(GROUPS) if full else sorted({task_name(x) for x in cases})
    for name in display_names:
        section, key = ("groups", "group") if full else ("tasks", "task")
        present = [
            (model, row) for model in models for row in rows[model][section] if row[key] == name
        ]
        if not present:
            continue
        keys = ("VLM",) if name in {"Action", "Location", "Viewpoint", *VLM_TASKS} else METRICS
        lines += [
            f"## {name}",
            "",
            "| 方法 | 已评分 / 应评 | " + " | ".join(LABELS[k] for k in keys) + " |",
            "|---|---:|" + "---:|" * len(keys),
        ]
        for model, row in present:
            values = [
                "N/A" if row["valid_mean"][k] is None else f"{row['valid_mean'][k]:.3f}"
                for k in keys
            ]
            lines.append(
                f"| {model} | {row['scored']} / {row['expected']} | " + " | ".join(values) + " |"
            )
        lines.append("")
    markdown = "\n".join(lines)
    path = output / "REPORT.md"
    if path.exists() and path.read_text() != markdown:
        raise ValueError("Use a fresh report directory after new results arrive")
    path.write_text(markdown)
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=["model", "task", "expected", "scored", *METRICS, "VLM"]
    )
    writer.writeheader()
    for model in models:
        for row in rows[model]["tasks"]:
            writer.writerow(
                {
                    "model": model,
                    "task": row["task"],
                    "expected": row["expected"],
                    "scored": row["scored"],
                    **row["valid_mean"],
                }
            )
    csv_path = output / "SUBTASKS.csv"
    if csv_path.exists() and csv_path.read_text() != buffer.getvalue():
        raise ValueError("Existing CSV differs")
    csv_path.write_text(buffer.getvalue())
    print(f"Report: {path}", flush=True)
    return result
