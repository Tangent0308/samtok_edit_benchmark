"""All-case statistics and a separate merge, with no changes to original records."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import statistics

import numpy as np

from samtok_benchmark.io import sha256_file
from samtok_benchmark.external_magicbrush.data import immutable, read
from samtok_benchmark.external_magicbrush.metrics import METRICS
from samtok_benchmark.external_magicbrush.report import bootstrap
from samtok_benchmark.external_magicbrush.worker import result_path

from . import NAMES
from .common import FORMAL, SOURCE_REPORT, SOURCE_REPORT_SHA, load_run, select_requests

PENALTY = {k: 1.0 if k in {"L1", "L2"} else -1.0 for k in METRICS}
DISPLAY_MODELS = (
    "instructpix2pix",
    "hive",
    "qwen21",
    "flux2_klein9b",
    "replan",
    "mirage",
    "mice",
    "sitedit",
)
DISPLAY_NAMES = {
    **NAMES,
    "qwen21": "Qwen-Image-2.1",
    "flux2_klein9b": "FLUX.2 Klein-9B",
    "replan": "RePlan",
    "mirage": "MIRAGE",
    "mice": "MICE",
    "sitedit": "SITEdit",
}


def collect(output):
    output = Path(output)
    plan, cfg, index = load_run(output)
    items = select_requests(index, plan["session_ids"])
    old_score = read(FORMAL / "run_001/scores/qwen21/mask-free/independent/30-1/score.json")
    expected_scorer = old_score["identity"]["scorer"]

    def check(pair):
        model, item = pair
        path = result_path(output, model, "edit", item["key"])
        if not path.exists():
            return model, item, None, None
        r = read(path)
        for field in ("source_code", "config_digest", "bundle_digest"):
            if r["identity"][field] != plan[field]:
                raise ValueError("Generation identity changed")
        for kind in ("raw", "output"):
            if r.get(kind + "_image") and sha256_file(r[kind + "_image"]) != r[kind + "_sha256"]:
                raise ValueError("Generated image changed")
        score_path = output / "scores" / model / item["key"] / "score.json"
        s = read(score_path) if score_path.exists() else None
        if s:
            if s["identity"]["scorer"] != expected_scorer:
                raise ValueError("New scores use a different scorer identity")
            if s["identity"]["generation_receipt_sha256"] != sha256_file(path):
                raise ValueError("Score/generation receipt binding differs")
            if s["identity"]["output_sha256"] != r["output_sha256"]:
                raise ValueError("Score/output binding differs")
        return model, item, r, s

    pairs = [(m, i) for m in plan["models"] for i in items]
    with ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(check, pairs))
    return plan, cfg, index, items, records


def estimate(output):
    plan, _, _, items, records = collect(output)
    if plan["scope"] != "classic-smoke":
        raise ValueError("Only bounded smoke evidence can determine the estimate")
    methods = []
    for model in plan["models"]:
        selected = [(r, s) for m, _, r, s in records if m == model]
        passed = len(selected) == 3 and all(
            r and r["status"] == "completed" and s and s["status"] == "scored" for r, s in selected
        )
        rtime = [r["inference_seconds"] for r, _ in selected if r and r["status"] == "completed"]
        stime = [s["wall_seconds"] for _, s in selected if s and s["status"] == "scored"]
        mean_gen = statistics.fmean(rtime) if rtime else None
        mean_score = statistics.fmean(stime) if stime else None
        methods.append(
            {
                "model": model,
                "passed": passed,
                "requests": len(items),
                "generation_seconds_mean": mean_gen,
                "scoring_seconds_mean": mean_score,
                "generation_gpu_hours": mean_gen * 1571 / 3600 if passed else None,
                "scoring_gpu_hours": mean_score * 1571 / 3600 if passed else None,
                "peak_allocated_gib": max(
                    [r.get("peak_gpu_allocated_bytes", 0) / 2**30 for r, _ in selected if r] or [0]
                ),
                "load_seconds": [
                    r["load_seconds"] for r, _ in selected if r and r.get("load_seconds")
                ],
            }
        )
    passed = all(r["passed"] for r in methods)
    result = {
        "schema": "magicbrush.classic.estimate.v1",
        "all_passed": passed,
        "source_code": plan["source_code"],
        "config_digest": plan["config_digest"],
        "bundle_digest": plan["bundle_digest"],
        "methods": methods,
        "total_gpu_hours": sum(r["generation_gpu_hours"] + r["scoring_gpu_hours"] for r in methods)
        if passed
        else None,
        "note": "Measured smoke extrapolation; cold model loads and filesystem overhead are additional.",
    }
    immutable(Path(output) / "ESTIMATE.json", result)
    return result


def summarise(model, mode, selected, sessions, indices):
    mapping = {sid: i for i, sid in enumerate(sessions)}
    sums = np.zeros((len(sessions), len(METRICS)))
    counts = np.zeros(len(sessions), dtype=np.int64)
    per_case = []
    status = Counter()
    for item, generation, score in selected:
        if generation is None:
            raise ValueError("Missing generation cannot be counted as a model failure")
        row = {"key": item["key"], "session_id": item["session_id"]}
        if generation["status"] == "failed":
            value = PENALTY
            row.update(
                status="failed",
                assigned_penalty=PENALTY,
                contribution_kind="generation_failure_penalty",
            )
            status["failed"] += 1
        elif generation["status"] == "completed" and score and score["status"] == "scored":
            value = score["metrics"]
            row.update(status="scored", metrics=value, contribution_kind="measured")
            status["measured"] += 1
        else:
            raise ValueError("Scoring is incomplete; do not invent a score")
        if set(value) != set(METRICS) or not all(np.isfinite(value[k]) for k in METRICS):
            raise ValueError("Invalid metric vector")
        n = mapping[item["session_id"]]
        sums[n] += [value[k] for k in METRICS]
        counts[n] += 1
        per_case.append(row)
    dist = bootstrap(sums, counts, indices)
    average = sums.sum(axis=0) / counts.sum()
    ci = np.percentile(dist, [2.5, 97.5], axis=0).T
    return {
        "model": model,
        "track": "mask-free",
        "subset": "full",
        "mode": mode,
        "complete": True,
        "target_count": len(selected),
        "measured_count": status["measured"],
        "generation_failed_count": status["failed"],
        "unresolved_count": 0,
        "metrics": dict(zip(METRICS, average.tolist())),
        "CI95": dict(zip(METRICS, ci.tolist())),
        "per_case": per_case,
    }


def report(output):
    output = Path(output)
    plan, _, _, items, records = collect(output)
    if plan["scope"] != "full" or len(plan["session_ids"]) != 535 or len(items) != 1571:
        raise ValueError("Final report requires every test session/request")
    if sha256_file(SOURCE_REPORT) != SOURCE_REPORT_SHA:
        raise ValueError("Existing report changed")
    source = read(SOURCE_REPORT)
    sessions = plan["session_ids"]
    indices = np.random.default_rng(20261105).integers(
        0, len(sessions), size=(10000, len(sessions)), dtype=np.int32
    )
    import hashlib

    if (
        hashlib.sha256(indices.tobytes()).hexdigest()
        != source["bootstrap"]["subsets"]["full"]["indices_sha256"]
    ):
        raise ValueError("Shared bootstrap indices differ")
    last = {sid: max(i["turn"] for i in items if i["session_id"] == sid) for sid in sessions}
    rows, methods = [], []
    for model in plan["models"]:
        chosen = [(i, r, s) for m, i, r, s in records if m == model]
        for mode in ("single-turn", "multi-turn"):
            panel = [
                (i, r, s)
                for i, r, s in chosen
                if (
                    i["mode"] == "independent"
                    if mode == "single-turn"
                    else i["turn"] == last[i["session_id"]]
                    and i["mode"] == ("independent" if i["turn"] == 1 else "iterative")
                )
            ]
            if len(panel) != (1053 if mode == "single-turn" else 535):
                raise ValueError("Final score denominator differs from full test set")
            rows.append(summarise(model, mode, panel, sessions, indices))
        successful = [r for _, r, _ in chosen if r and r["status"] == "completed"]
        methods.append(
            {
                "model": model,
                "generation_status": dict(
                    Counter(r["status"] if r else "missing" for _, r, _ in chosen)
                ),
                "mean_inference_seconds": statistics.fmean(
                    r["inference_seconds"] for r in successful
                )
                if successful
                else None,
                "inference_gpu_hours": sum(r["inference_seconds"] for r in successful) / 3600,
                "peak_allocated_gib": max(
                    (r["peak_gpu_allocated_bytes"] for r in successful), default=0
                )
                / 2**30,
            }
        )
    old_rows = [
        r
        for r in source["rows"]
        if r["model"] in DISPLAY_MODELS and r["track"] == "mask-free" and r["subset"] == "full"
    ]
    if len(old_rows) != 12:
        raise ValueError("Unexpected existing six-method row coverage")
    result = {
        "schema": "magicbrush.classic.merged.v1",
        "created": datetime.now(timezone.utc).isoformat(),
        "existing_report": {"path": str(SOURCE_REPORT), "sha256": SOURCE_REPORT_SHA},
        "addition_run": str(output),
        "models": list(DISPLAY_MODELS),
        "track": "mask-free",
        "subset": "full",
        "excluded_cases": [],
        "sessions": 535,
        "independent_turns": 1053,
        "bootstrap": source["bootstrap"],
        "policy": source["policy"],
        "new_methods": methods,
        "rows": old_rows + rows,
    }
    destination = output / "report"
    if (destination / "MERGED_REPORT.json").exists():
        result["created"] = read(destination / "MERGED_REPORT.json")["created"]
    immutable(destination / "MERGED_REPORT.json", result)
    lines = [
        "# MagicBrush 无 mask 全量结果：八方法",
        "",
        "完整 535 会话、1,053 个独立编辑轮次；全部样本均纳入。",
        "",
        "新增 InstructPix2Pix 和 HIVE 使用官方原生 512 分辨率，其余六方法沿用冻结的约 1MP 配置；统一回源与五项评分。",
        "",
    ]
    for mode, title in [
        ("single-turn", "独立单轮：1,053 轮"),
        ("multi-turn", "连续多轮最终图：535 会话"),
    ]:
        panel = {r["model"]: r for r in result["rows"] if r["mode"] == mode}
        lines += [
            f"## {title}",
            "",
            "| 方法 | L1 ↓ | L2 ↓ | CLIP-I ↑ | DINO ↑ | CLIP-T ↑ |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for model in DISPLAY_MODELS:
            values = []
            for metric in METRICS:
                best = (min if metric in ("L1", "L2") else max)(
                    r["metrics"][metric] for r in panel.values()
                )
                value = panel[model]["metrics"][metric]
                cell = f"{value:.4f}"
                values.append(f"**{cell}**" if value == best else cell)
            lines.append("| " + DISPLAY_NAMES[model] + " | " + " | ".join(values) + " |")
        lines.append("")
    lines += [
        "L2 为均方误差，不开根号；相似度不是百分数。生成失败按既定规则赋 L1/L2=1、相似度=−1，全部计入分母。",
        "",
        "95% 区间、逐例贡献和可追溯来源见同目录 MERGED_REPORT.json；原始实验记录未改动。",
        "",
    ]
    path = destination / "MERGED_REPORT.md"
    if path.exists() and path.read_text() != "\n".join(lines):
        raise ValueError("Existing report text differs")
    path.write_text("\n".join(lines))
    return {"report": str(destination), "rows": len(result["rows"]), "methods": methods}
