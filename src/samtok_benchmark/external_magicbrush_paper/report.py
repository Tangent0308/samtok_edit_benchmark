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
from samtok_benchmark.external_magicbrush_classic.report import summarise
from samtok_benchmark.external_magicbrush.worker import result_path

from . import NAMES
from .common import FORMAL, load_run, select_requests

PENALTY = {k: 1.0 if k in {"L1", "L2"} else -1.0 for k in METRICS}
DISPLAY_MODELS = (
    "instructpix2pix",
    "hive",
    "instructpix2pix_magicbrush",
    "qwen21",
    "flux2_klein9b",
    "replan",
    "mirage",
    "mice",
    "sitedit",
)
DISPLAY_NAMES = {
    **NAMES,
    "instructpix2pix": "InstructPix2Pix",
    "hive": "HIVE",
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
    if plan["scope"] != "paper-smoke":
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
        "schema": "magicbrush.paper.estimate.v1",
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


EXISTING_REPORT = FORMAL / "classic_20261106/report/MERGED_REPORT.json"
EXISTING_REPORT_SHA = "fa29a095dca5b8f3b1f29eb89398f5178fcade6918bbd6f12605b4f3fe596eec"


def primary_score(score):
    """Select primary metrics in memory; original six-field records stay intact."""
    if score is None or score["status"] != "scored":
        return score
    values = score["metrics"]
    if not set(METRICS) <= set(values) or set(values) - set(METRICS) - {"GT-CLIP-T"}:
        raise ValueError("Unexpected scorer metric schema")
    return {**score, "metrics": {k: values[k] for k in METRICS}}


def report(output):
    import hashlib

    output = Path(output)
    plan, _, _, items, records = collect(output)
    if plan["scope"] != "full" or len(plan["session_ids"]) != 535 or len(items) != 1571:
        raise ValueError("Report requires all sessions and requests")
    if sha256_file(EXISTING_REPORT) != EXISTING_REPORT_SHA:
        raise ValueError("Previous eight-method report changed")
    previous = read(EXISTING_REPORT)
    sessions = plan["session_ids"]
    previous_bootstrap = previous["bootstrap"]["subsets"]["full"]
    if sessions != previous_bootstrap["sessions"]:
        raise ValueError("Previous report uses a different session order")
    indices = np.random.default_rng(20261105).integers(
        0, len(sessions), size=(10000, len(sessions)), dtype=np.int32
    )
    if hashlib.sha256(indices.tobytes()).hexdigest() != previous_bootstrap["indices_sha256"]:
        raise ValueError("Shared bootstrap indices differ")
    last = {sid: max(i["turn"] for i in items if i["session_id"] == sid) for sid in sessions}
    selected = [(i, r, primary_score(s)) for _, i, r, s in records]
    rows = list(previous["rows"])
    if len(rows) != 16 or set(r["model"] for r in rows) != set(DISPLAY_MODELS) - set(
        plan["models"]
    ):
        raise ValueError("Unexpected prior report coverage")
    for mode in ("single-turn", "multi-turn"):
        panel = [
            (i, r, s)
            for i, r, s in selected
            if (
                i["mode"] == "independent"
                if mode == "single-turn"
                else i["turn"] == last[i["session_id"]]
                and i["mode"] == ("independent" if i["turn"] == 1 else "iterative")
            )
        ]
        if len(panel) != (1053 if mode == "single-turn" else 535):
            raise ValueError("Incorrect full-cohort denominator")
        rows.append(summarise(plan["models"][0], mode, panel, sessions, indices))
    success = [r for _, r, _ in selected if r and r["status"] == "completed"]
    result = {
        "schema": "magicbrush.paper.merged.v1",
        "created": datetime.now(timezone.utc).isoformat(),
        "existing_report": {"path": str(EXISTING_REPORT), "sha256": EXISTING_REPORT_SHA},
        "addition_run": str(output),
        "models": list(DISPLAY_MODELS),
        "track": "mask-free",
        "subset": "full",
        "excluded_cases": [],
        "sessions": 535,
        "independent_turns": 1053,
        "bootstrap": previous["bootstrap"],
        "policy": previous["policy"],
        "rows": rows,
        "new_method": {
            "model": plan["models"][0],
            "training_status": "finetuned on MagicBrush train",
            "checkpoint_role": "publisher's paper checkpoint MagicBrush-epoch-000168.ckpt",
            "generation_status": dict(
                Counter(r["status"] if r else "missing" for _, r, _ in selected)
            ),
            "mean_inference_seconds": statistics.fmean(r["inference_seconds"] for r in success)
            if success
            else None,
            "inference_gpu_hours": sum(r["inference_seconds"] for r in success) / 3600,
            "peak_allocated_gib": max((r["peak_gpu_allocated_bytes"] for r in success), default=0)
            / 2**30,
        },
    }
    destination = output / "report"
    path = destination / "MERGED_REPORT.json"
    if path.exists():
        result["created"] = read(path)["created"]
    immutable(path, result)
    lines = [
        "# MagicBrush 无 mask 全量结果：九方法",
        "",
        "完整 535 会话、1,053 个独立编辑轮次；全部样本均纳入。",
        "",
        "新增 InstructPix2Pix-MagicBrush 使用官方论文检查点，在 MagicBrush 训练集微调。采用原生 512 配置、100 步、seed 42；统一回源、评分及失败惩罚。原八方法记录未改动。",
        "",
    ]
    for mode, title in [
        ("single-turn", "独立单轮：1,053 轮"),
        ("multi-turn", "连续多轮最终图：535 会话"),
    ]:
        panel = {r["model"]: r for r in rows if r["mode"] == mode}
        lines += [
            f"## {title}",
            "",
            "| 方法 | L1 ↓ | L2 ↓ | CLIP-I ↑ | DINO ↑ | CLIP-T ↑ |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for model in DISPLAY_MODELS:
            cells = []
            for metric in METRICS:
                value = panel[model]["metrics"][metric]
                best = (min if metric in {"L1", "L2"} else max)(
                    r["metrics"][metric] for r in panel.values()
                )
                cell = f"{value:.4f}"
                cells.append(f"**{cell}**" if value == best else cell)
            lines.append("| " + DISPLAY_NAMES[model] + " | " + " | ".join(cells) + " |")
        lines.append("")
    lines += ["L2 为 MSE；相似度不是百分数。95% 会话 bootstrap 区间及逐例贡献见 JSON。", ""]
    markdown = destination / "MERGED_REPORT.md"
    content = "\n".join(lines)
    if markdown.exists() and markdown.read_text() != content:
        raise ValueError("Existing Markdown report differs")
    markdown.write_text(content)
    return {"report": str(path), "rows": len(rows), "new_method": result["new_method"]}
