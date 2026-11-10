"""Replace only the complete fixed correction cohort; never choose old versus new by score."""

from collections import Counter
from pathlib import Path

from samtok_benchmark.external_full.report import aggregate, mean, METRICS
from samtok_benchmark.external_refedit.data import immutable, read
from samtok_benchmark.io import sha256_file
from .plan import load


def combine(plan, original, correction):
    corrected = [r for r in correction["per_case"] if r["model"] == "sitedit"]
    by_id = {r["case_id"]: r for r in corrected}
    expected = set(plan["case_ids"])
    if set(by_id) != expected or len(corrected) != len(expected):
        raise ValueError("Correction must cover all planned requests, including failures")
    records = []
    for row in original["per_case"]:
        if row["task"] in {"action", "location", "view"}:
            continue
        replacement = row["model"] == "sitedit" and row["case_id"] in expected
        records.append(
            {
                **(by_id[row["case_id"]] if replacement else row),
                "provenance": "multitarget_correction" if replacement else "original_full_run",
            }
        )
    rows = {}
    for model in original["models"]:
        selected = [r for r in records if r["model"] == model]
        if len(selected) != 3285:
            raise ValueError("The full objective denominator changed")
        tasks = []
        for task in sorted({r["task"] for r in selected}):
            items = [r for r in selected if r["task"] == task]
            valid = [r["metrics"] for r in items if r["status"] == "completed" and r["metrics"]]
            tasks.append(
                {
                    "task": task,
                    "expected": len(items),
                    "scored": len(valid),
                    "complete": len(valid) == len(items),
                    "status_counts": dict(Counter(r["status"] for r in items)),
                    "valid_mean": {k: mean([v[k] for v in valid]) for k in METRICS},
                }
            )
        rows[model] = {"tasks": tasks, "groups": aggregate(tasks)}
    return {
        "schema": "compbench.sitedit.multitarget.merged.v1",
        "plan_digest": plan["digest"],
        "scope": "all_3285_official_objective_requests_per_method",
        "models": original["models"],
        "rows": rows,
        "per_case": records,
        "replaced_case_ids": plan["case_ids"],
        "failure_policy": "No old-output substitution; keep failures and missing scores explicit",
        "original_report": plan["original_report"],
        "original_report_sha256": plan["original_report_sha256"],
    }


def render(merged):
    names = {
        "sitedit": "SITEdit（逐目标修正）",
        "qwen21": "Qwen-Image-2.1",
        "replan": "RePlan",
        "mice": "MICE",
        "flux2_klein9b": "FLUX.2 Klein-9B",
    }
    groups = {
        "Local Editing": "局部编辑",
        "Multi-object Editing": "多目标编辑",
        "Implicit Reasoning": "隐式推理",
        "Multi-turn (Turn 1)": "连续编辑第一轮",
        "Multi-turn (Turn 2)": "连续编辑第二轮",
    }
    lines = [
        "# CompBench：SITEdit 逐目标协议修正结果",
        "",
        "多目标添加/删除共 144 条全部采用修正后的结果，不按得分选择旧输出。其余请求和基线只读复用原始正式记录。",
        "GT mask/caption 仅用于官方客观评分。每方法仍为全部 3,285 条客观请求。",
        "",
    ]
    for group, label in groups.items():
        lines += [
            f"## {label}",
            "",
            "| 方法 | 已评分/应评 | LC-T ↑ | LC-I ↑ | PSNR ↑ | SSIM ↑ | LPIPS ↓ |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for model in merged["models"]:
            row = next(g for g in merged["rows"][model]["groups"] if g["group"] == group)
            numbers = [f"{row['valid_mean'][k]:.4f}" if row["complete"] else "N/A" for k in METRICS]
            lines.append(
                f"| {names.get(model, model)} | {row['scored']}/{row['expected']} | "
                + " | ".join(numbers)
                + " |"
            )
        lines.append("")
    return "\n".join(lines)


def report(control, results_root, output):
    from samtok_benchmark.external_full.report import report as official_report

    plan, _ = load(control)
    root, output = Path(results_root), Path(output)
    if sha256_file(plan["original_report"]) != plan["original_report_sha256"]:
        raise ValueError("Original report changed")
    correction = official_report(
        plan["bundle"],
        root / "run",
        root / "scores",
        output / "correction",
        ["sitedit"],
        plan["case_ids"],
    )
    # Some official entry versions return a path; the immutable file is authoritative.
    correction = read(output / "correction/REPORT.json")
    merged = combine(plan, read(plan["original_report"]), correction)
    merged["correction_report"] = str(output / "correction/REPORT.json")
    merged["correction_report_sha256"] = sha256_file(output / "correction/REPORT.json")
    stages = {
        stage: [read(root / "run/sitedit" / stage / c / "result.json") for c in plan["case_ids"]]
        for stage in ("tokens", "edit")
    }
    merged["correction_execution"] = {
        "stages": {
            stage: dict(Counter(r["status"] for r in records)) for stage, records in stages.items()
        },
        "inference_gpu_seconds": sum(
            r.get("inference_seconds", 0) for records in stages.values() for r in records
        ),
        "additional_native_enumeration_answers": sum(
            (root / "run/sitedit/tokens" / c / "enumeration.json").is_file()
            for c in plan["case_ids"]
        ),
        "normal_pass1_answers": sum(
            (root / "run/sitedit/tokens" / c / "answer.json").is_file() for c in plan["case_ids"]
        ),
        "fallback_units": sum(
            r.get("native", {}).get("fallback_units", 0) for r in stages["tokens"]
        ),
        "unit_count_distribution": dict(
            Counter(
                len(r["native"]["units"]) for r in stages["tokens"] if r["status"] == "completed"
            )
        ),
    }
    immutable(output / "MERGED_REPORT.json", merged)
    path = output / "MERGED_REPORT.md"
    text = render(merged)
    if path.exists() and path.read_text() != text:
        raise ValueError("Existing merged report differs")
    path.write_text(text)
    return merged
