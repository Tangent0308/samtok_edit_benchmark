#!/usr/bin/env python3
"""Verify saved MIRA scores and reproduce the six-row table without GPU/API calls."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path

import numpy as np

import report_mira_audited as audited
import run_mira_r2_full as run

LABELS = {
    "qwen2511": "Qwen-Image-Edit-2511", "qwen21": "Qwen-Image-2.1",
    "replan": "RePlan", "mirage": "MIRAGE", "sitedit_v4": "SITEdit v4 / S2@16000",
    "sitedit": "SITEdit R2@1000",
}


def equal_numbers(actual, expected, name):
    """Compare nested records without silently dropping coverage or identity fields."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise ValueError(f"Different fields: {name}")
        for key in expected:
            equal_numbers(actual[key], expected[key], f"{name}.{key}")
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError(f"Different list coverage: {name}")
        for i, (a, e) in enumerate(zip(actual, expected)):
            equal_numbers(a, e, f"{name}[{i}]")
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not np.isclose(actual, expected, atol=1e-12, rtol=0):
            raise ValueError(f"Different numeric result: {name}")
    elif actual != expected:
        raise ValueError(f"Different record: {name}")


def check_image(task):
    result_path, binding = task
    result = run.read(result_path)
    if result["status"] != "completed" or run.sha256_file(result_path) != binding["result_sha256"]:
        raise ValueError(f"Changed generation receipt: {result_path}")
    for label in ("raw", "output"):
        if run.sha256_file(result[f"{label}_image"]) != result[f"{label}_sha256"]:
            raise ValueError(f"Changed {label} image: {result_path}")
    if result["output_sha256"] != binding["output_sha256"]:
        raise ValueError(f"Changed Judge image binding: {result_path}")
    return True


def load_r2(root, report, reference_job, verify_images=False):
    values, image_tasks = {}, []
    references = {Path(b["image"]).stem: b for b in reference_job["bindings"]}
    partitions = run.batch_cases(report["case_ids"])
    if set(partitions) != set(report["batches"]):
        raise ValueError("Different R2 scoring partition")
    for batch, expected in partitions.items():
        directory = root / "scores_gpt54" / batch / "sitedit"
        score_path = directory / "scores/per_image_results.jsonl"
        job = run.read(directory / "JOB.json")
        judge = run.read(directory / "JUDGE.json")
        evidence = {"job_sha256": run.sha256_file(directory / "JOB.json"),
                    "scores_sha256": run.sha256_file(score_path)}
        if evidence != report["batches"][batch] or judge["job_sha256"] != evidence["job_sha256"]:
            raise ValueError(f"Changed Judge evidence: {batch}")
        if any(job[key] != reference_job[key] for key in
               ("canonical_sha256", "evaluator", "evaluator_source")):
            raise ValueError("R2 and v4 use different canonical data or Judge configuration")
        bindings = {Path(b["image"]).stem: b for b in job["bindings"]}
        if (set(bindings) != set(expected) or len(job["bindings"]) != len(expected)
                or job["unscorable"] or job["total"] != len(expected)
                or job["valid_outputs"] != len(expected)
                or not run.judge_complete(directory, expected)):
            raise ValueError(f"Incomplete or inconsistent R2 batch: {batch}")
        for row in run.read_rows(score_path):
            case = Path(row["image"]).stem
            if case in values or row["num_crops"] != 5:
                raise ValueError("Duplicate R2 source or incorrect edit count")
            if bindings[case]["source_sha256"] != references[case]["source_sha256"]:
                raise ValueError("R2 and v4 used different source images")
            values[case] = [row[k] for k in run.FIELDS]
            image_tasks.append((root / "run_001/sitedit/edit" / case / "result.json", bindings[case]))
    if verify_images:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(check_image, image_tasks))
    return values


def comparison(root, baseline, verify_images=False):
    report = run.read(root / "REPORT.json")
    cases = report["case_ids"]
    config = run.read(root / "run_001/CONFIG.json")
    original = run.read(baseline / "run_001/CONFIG.json")
    restored = deepcopy(config)
    restored["sitedit"]["dit_adapter"] = original["sitedit"]["dit_adapter"]
    if restored != original or config["sitedit"]["dit_adapter"] != str(run.ADAPTER):
        raise ValueError("The R2 experiment changes more than the designated checkpoint")
    if run.sha256_file(root / "run_001/CONFIG.json") != report["generation_config_sha256"]:
        raise ValueError("Changed R2 generation configuration")
    values, coverage, evidence = audited.load_scores(baseline, cases)
    published = run.read(baseline / "audited_report_v2/REPORT.json")
    equal_numbers(evidence, published["evidence"], "baseline evidence")
    equal_numbers(audited.summarize(values, cases), published["subsets"]["official_200"],
                  "baseline full table")
    old_job = run.read(baseline / "scores_gpt54_001/sitedit/JOB.json")
    for short, stored in (("job_sha256", "baseline_job_sha256"),
                          ("scores_sha256", "baseline_scores_sha256")):
        if evidence["sitedit"][short] != report[stored]:
            raise ValueError("Changed v4 reference in R2 report")
    new = load_r2(root, report, old_job, verify_images)
    for case in cases:
        equal_numbers({"v4": values["sitedit"][case], "R2": new[case]},
                      report["per_case"][case], f"per_case.{case}")
    recomputed = run.statistics(values["sitedit"], new, cases)
    for key in ("rows", "paired_R2_minus_v4", "bootstrap"):
        equal_numbers(recomputed[key], report[key], key)
    values["sitedit_v4"] = values.pop("sitedit")
    values["sitedit"] = new
    result = audited.summarize(values, cases)
    existing = root / "ALL_MODELS_COMPARISON.json"
    if existing.exists():
        saved = run.read(existing)
        for key in result:
            equal_numbers(result[key], saved[key], f"all_models.{key}")
    result.update(schema="mira.all_models_reproduction.v1",
                  source_report_sha256=run.sha256_file(root / "REPORT.json"),
                  baseline_evidence=evidence, coverage=coverage,
                  score_range=[0, 10], aggregation=report["aggregation"],
                  components_R2_minus_v4=recomputed["paired_R2_minus_v4"],
                  verified_images=len(cases) if verify_images else 0,
                  note="Saved scores only; no generation, API calls, resampling or imputation.")
    return result


def markdown(report):
    lines = ["# MIRA-Bench 全量对比", "", "全部指标为 0–10 分，越高越好。"
             "Overall = sqrt(min(mean(PF), mean(Cons)) × mean(PQ))。", "",
             "| 方法 | 已评分/200 | PF ↑ | Cons ↑ | PQ ↑ | Overall ↑ | Overall 95% CI |",
             "|---|---:|---:|---:|---:|---:|---|"]
    for row in report["rows"]:
        ci = row["Overall_CI95"]
        interval = f"[{ci[0]:.3f}, {ci[1]:.3f}]" if ci else "N/A（缺 1 张）"
        lines.append("| " + " | ".join([LABELS[row["model"]], f"{row['scored']}/{row['total']}",
                                         *[f"{row[k]:.3f}" for k in run.METRICS], interval]) + " |")
    lines += ["", "RePlan 的 199 张均值为可评分子集统计，缺失的 154 保留，未填零。", "",
              "| R2@1000 − 对照 | Overall 差值 | 配对 95% CI | 配对图数 |",
              "|---|---:|---:|---:|"]
    for pair in report["paired_sitedit_minus_baseline"]:
        ci = pair["CI95"]
        lines.append(f"| {LABELS[pair['baseline']]} | {pair['delta']:+.3f} | "
                     f"[{ci[0]:+.3f}, {ci[1]:+.3f}] | {pair['n_pairs']} |")
    lines += ["", "源图配对 bootstrap：10,000 次，seed 20261027。与 RePlan 的配对比较仅适用于双方共同"
              "可评分的 199 张。基线沿用保存的 Judge 回答，未重跑。", ""]
    return "\n".join(lines)


def write_new(output, files, protected):
    output = output.resolve()
    if any(output.is_relative_to(p.resolve()) for p in protected):
        raise ValueError("Write verification artifacts outside formal result roots")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Use a new, empty verification output directory")
    for name, content in files.items():
        with (output / name).open("x") as stream:
            stream.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path, default=run.BASE)
    parser.add_argument("--r2-root", type=Path, default=run.BASE / run.PROFILE["default_run_name"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-images", action="store_true")
    args = parser.parse_args()
    report = comparison(args.r2_root, args.baseline_root, args.verify_images)
    write_new(args.output, {"REPORT.json": json.dumps(report, indent=2) + "\n",
                            "TABLE.md": markdown(report)},
              (args.baseline_root, args.r2_root, run.NAS / "experiments2"))
    print(f"Verified 200 R2 scores and all five reference rows: {args.output / 'TABLE.md'}")


if __name__ == "__main__":
    main()
