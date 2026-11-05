"""Coverage-first Chinese report, shared session bootstrap and measured smoke extrapolation."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import statistics

import numpy as np

from samtok_benchmark.io import digest, sha256_file, write_json
from . import MODELS, TRACKS
from .bundle import load_bundle, requests
from .data import read
from .metrics import METRICS
from .worker import result_path, stages

BOOTSTRAP_SEED = 20261105
BOOTSTRAP_DRAWS = 10000


def mean(values):
    return statistics.fmean(values) if values else None


def bootstrap(sums, counts, indices):
    """Resample sessions; retain all available turns, so this equals official per-image means."""
    values = []
    for block in np.array_split(indices, max(1, len(indices) // 200)):
        numerator = sums[block].sum(axis=1)
        denominator = counts[block].sum(axis=1)
        values.append(numerator / denominator[:, None])
    return np.concatenate(values)


def collect(output):
    output = Path(output)
    plan = read(output / "RUN.json")
    index = load_bundle(plan["bundle"])
    items = requests(index, plan["session_ids"], plan["scope"] == "smoke")
    methods = []
    results = {}
    scorer_identities = set()
    for model in plan["models"]:
        stages_summary = {}
        for stage in stages(model):

            def checked(item):
                p = result_path(output, model, stage, item["key"])
                if p.exists():
                    r = read(p)
                    if (
                        r["identity"]["source_code"] != plan["source_code"]
                        or r["identity"]["config_digest"] != plan["config_digest"]
                        or r["identity"]["bundle_digest"] != plan["bundle_digest"]
                    ):
                        raise ValueError(f"Receipt identity mismatch: {p}")
                    for k in ["raw", "output"]:
                        if r.get(k + "_image") and sha256_file(r[k + "_image"]) != r[k + "_sha256"]:
                            raise ValueError("Output changed after generation")
                    if stage == "edit":
                        s = output / "scores" / model / item["key"] / "score.json"
                        scored = read(s) if s.exists() else None
                        if scored and scored["identity"][
                            "generation_receipt_sha256"
                        ] != sha256_file(p):
                            raise ValueError("Score/generation binding changed")
                        return item, r, scored
                    return item, r, None
                return None

            # Read and hash independent files concurrently, once; never rescan the full run per batch.
            with ThreadPoolExecutor(max_workers=16) as pool:
                checked_rows = [r for r in pool.map(checked, items) if r is not None]
            records = [(item, r) for item, r, _ in checked_rows]
            if stage == "edit":
                for item, r, scored in checked_rows:
                    results[(model, item["key"])] = {"generation": r, "score": scored}
                    if scored:
                        scorer_identities.add(digest(scored["identity"]["scorer"]))
            successful = [(i, r) for i, r in records if r["status"] == "completed"]
            stages_summary[stage] = {
                "status_counts": dict(Counter(r["status"] for _, r in records)),
                "wall_seconds_sum": sum(r["wall_seconds"] for _, r in records),
                "mean_seconds_by_track": {
                    t: mean([r["inference_seconds"] for i, r in successful if i["track"] == t])
                    for t in TRACKS
                },
                "mean_seconds": mean([r["inference_seconds"] for _, r in successful]),
                "load_seconds": [
                    r["load_seconds"] for _, r in records if r.get("load_seconds") is not None
                ],
                "peak_allocated_gib": max(
                    [r.get("peak_gpu_allocated_bytes", 0) / 2**30 for _, r in records], default=0
                ),
                "peak_reserved_gib": max(
                    [r.get("peak_gpu_reserved_bytes", 0) / 2**30 for _, r in records], default=0
                ),
            }
        status = Counter()
        errors = []
        scoring_seconds = []
        for item in items:
            r = results.get((model, item["key"]))
            if r is None:
                status["missing_generation"] += 1
            elif r["generation"]["status"] != "completed":
                status["generation_failed"] += 1
                errors.append({"key": item["key"], "error": r["generation"].get("error")})
            elif not r["score"]:
                status["unscored"] += 1
            else:
                status[r["score"]["status"]] += 1
                scoring_seconds.append(r["score"]["wall_seconds"])
        methods.append(
            {
                "model": model,
                "requests": len(items),
                "status": dict(status),
                "stages": stages_summary,
                "errors": errors,
                "scoring_mean_seconds": mean(scoring_seconds),
            }
        )
    if len(scorer_identities) > 1:
        raise ValueError("Scores from different metric configurations/devices cannot be pooled")
    return plan, index, items, methods, results


def estimate(output, destination):
    plan, index, items, methods, _ = collect(output)
    if plan["scope"] != "smoke":
        raise ValueError("Runtime extrapolation must come from bounded smoke results")
    full = requests(index, index["sessions"])
    counts = Counter(i["track"] for i in full)
    rows = []
    for method in methods:
        m = method["model"]
        complete = method["status"].get("scored", 0) == 3
        hours = 0.0
        valid = True
        for summary in method["stages"].values():
            for track, count in counts.items():
                value = summary["mean_seconds_by_track"][track]
                if value is None:
                    valid = False
                else:
                    hours += value * count / 3600
        rows.append(
            {
                "model": m,
                "smoke_passed": complete,
                "samples": method["requests"],
                "generation_gpu_hours_estimate": hours if valid else None,
                "generation_seconds_mean": hours * 3600 / len(full) if valid else None,
                "scoring_seconds_mean": method["scoring_mean_seconds"],
                "stages": method["stages"],
            }
        )
    all_passed = set(plan["models"]) == set(MODELS) and all(r["smoke_passed"] for r in rows)
    total = sum(r["generation_gpu_hours_estimate"] or 0 for r in rows)
    value = {
        "schema": "magicbrush.estimate.v1",
        "all_methods_smoke_passed": all_passed,
        "source_code": plan["source_code"],
        "bundle_digest": plan["bundle_digest"],
        "smoke_run": str(Path(output).resolve()),
        "methods": rows,
        "requests_per_method": len(full),
        "total_gpu_hours_estimate": total if all_passed else None,
        "ideal_hours_4gpu": total / 4 if all_passed else None,
        "ideal_hours_8gpu": total / 8 if all_passed else None,
        "note": "Extrapolation from three requests per method, equally weighted mask tracks. Excludes cold loads, I/O, scoring and scheduling overhead; not a measured formal runtime.",
    }
    write_json(destination, value)
    return value


def report(output, overlap_path, destination):
    output, destination = Path(output), Path(destination)
    plan, index, items, methods, results = collect(output)
    audit = read(overlap_path)
    excluded = set(audit["excluded_sessions"])
    rows, bootstraps = [], {}
    sessions = plan["session_ids"]
    last = {s: max(i["turn"] for i in index["cases"] if i["session_id"] == s) for s in sessions}
    for subset in ["full", "no_known_corpus_overlap"]:
        selected = [s for s in sessions if subset == "full" or s not in excluded]
        if not selected:
            continue
        rng = np.random.default_rng(BOOTSTRAP_SEED)
        draws = rng.integers(
            0, len(selected), size=(BOOTSTRAP_DRAWS, len(selected)), dtype=np.int32
        )
        bootstraps[subset] = {
            "sessions": selected,
            "indices_sha256": hashlib.sha256(draws.tobytes()).hexdigest(),
        }
        sid_index = {s: n for n, s in enumerate(selected)}
        for track in TRACKS:
            for mode in ["single-turn", "multi-turn"]:
                wanted = [
                    i
                    for i in items
                    if i["track"] == track
                    and i["session_id"] in sid_index
                    and (
                        i["mode"] == "independent"
                        if mode == "single-turn"
                        else i["turn"] == last[i["session_id"]]
                        and i["mode"] == ("independent" if i["turn"] == 1 else "iterative")
                    )
                ]
                for model in plan["models"]:
                    sums = np.zeros((len(selected), len(METRICS)))
                    counts = np.zeros(len(selected), dtype=np.int64)
                    per_case = []
                    for item in wanted:
                        r = results.get((model, item["key"]), {})
                        score = r.get("score")
                        status = (
                            "scored"
                            if score and score["status"] == "scored"
                            else r.get("generation", {}).get("status", "missing")
                        )
                        record = {
                            "key": item["key"],
                            "session_id": item["session_id"],
                            "status": status,
                        }
                        if score and score["status"] == "scored":
                            record["metrics"] = {k: score["metrics"][k] for k in METRICS}
                            n = sid_index[item["session_id"]]
                            sums[n] += np.array(list(record["metrics"].values()))
                            counts[n] += 1
                        per_case.append(record)
                    complete = len(wanted) > 0 and int(counts.sum()) == len(wanted)
                    # A smoke subset is never presented as a complete full-benchmark row.
                    means = (
                        dict(zip(METRICS, (sums.sum(axis=0) / counts.sum()).tolist()))
                        if counts.sum()
                        else None
                    )
                    ci = None
                    if complete and plan["scope"] == "full":
                        distribution = bootstrap(sums, counts, draws)
                        ci = dict(
                            zip(
                                METRICS, np.percentile(distribution, [2.5, 97.5], axis=0).T.tolist()
                            )
                        )
                    rows.append(
                        {
                            "model": model,
                            "track": track,
                            "mode": mode,
                            "subset": subset,
                            "target_count": len(wanted),
                            "scored_count": int(counts.sum()),
                            "complete": complete,
                            "metrics": means if complete else None,
                            "available_only_means": means,
                            "CI95": ci,
                            "per_case": per_case,
                        }
                    )
    value = {
        "schema": "magicbrush.report.v1",
        "scope": plan["scope"],
        "rows": rows,
        "methods": methods,
        "bootstrap": {"seed": BOOTSTRAP_SEED, "draws": BOOTSTRAP_DRAWS, "subsets": bootstraps},
        "overlap": {
            "path": str(Path(overlap_path).resolve()),
            "sha256": sha256_file(overlap_path),
            "confirmed_finetuning_sessions": len(audit["confirmed_finetuning_overlap"]),
            "known_corpus_sessions": len(audit["known_samtok_corpus_overlap"]),
            "excluded_sessions": len(excluded),
            "clean_sessions": len(audit["clean_sessions"]),
            "clean_turns": audit["clean_turns"],
            "limits": audit["limits"],
        },
        "run_digest": digest(plan),
        "statistics_code_sha256": sha256_file(Path(__file__)),
        "time": datetime.now(timezone.utc).isoformat(),
    }
    destination.mkdir(parents=True, exist_ok=True)
    write_json(destination / "REPORT.json", value)
    title = (
        "MagicBrush 正式评测"
        if plan["scope"] == "full"
        else "MagicBrush 冒烟验证（不是基准性能结论）"
    )
    text = [
        f"# {title}",
        "",
        "## 训练数据重合",
        "",
        f"已确认微调重合 {len(audit['confirmed_finetuning_overlap'])}/535 会话；已知 SAMTok 训练语料重合 {len(audit['known_samtok_corpus_overlap'])}/535。"
        f"统一排除其并集 {len(excluded)} 会话，保留 {len(audit['clean_sessions'])} 会话／{audit['clean_turns']} 独立轮次。",
        "",
        audit["limits"],
        "",
        "## 执行状态",
        "",
        "| 方法 | 请求数 | 已评分 | 其他状态 |",
        "|---|---:|---:|---|",
    ]
    for m in methods:
        text.append(
            f"| {m['model']} | {m['requests']} | {m['status'].get('scored', 0)} | {m['status']} |"
        )
    if plan["scope"] == "smoke":
        text += [
            "",
            "## 逐请求端到端检查",
            "",
            "以下仅为三个固定请求的评分诊断。连续编辑样例是三轮会话的第二轮，不是官方最终轮；"
            "因此不据此报告 single-turn / multi-turn 基准均分或方法排名。",
            "",
            "| 方法 | 请求 | 状态 | L1 ↓ | L2 ↓ | CLIP-I ↑ | DINO ↑ | CLIP-T ↑ |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ]
        for model in plan["models"]:
            for item in items:
                record = results.get((model, item["key"]), {})
                score = record.get("score")
                status = (
                    score["status"]
                    if score
                    else record.get("generation", {}).get("status", "missing")
                )
                values = [
                    f"{score['metrics'][k]:.4f}"
                    if score and score["status"] == "scored"
                    else "未计分"
                    for k in METRICS
                ]
                text.append(f"| {model} | {item['key']} | {status} | " + " | ".join(values) + " |")
    for subset in ["full", "no_known_corpus_overlap"] if plan["scope"] == "full" else []:
        for track in TRACKS:
            for mode in ["single-turn", "multi-turn"]:
                selected_rows = [
                    r for r in rows if (r["subset"], r["track"], r["mode"]) == (subset, track, mode)
                ]
                text += [
                    "",
                    f"## {subset} / {track} / {mode}",
                    "",
                    "| 方法 | 计分/目标 | L1 ↓ | L2 ↓ | CLIP-I ↑ | DINO ↑ | CLIP-T ↑ |",
                    "|---|---:|---:|---:|---:|---:|---:|",
                ]
                for r in selected_rows:
                    values = [
                        f"{r['metrics'][k]:.4f}" if r["metrics"] else "待完成" for k in METRICS
                    ]
                    text.append(
                        f"| {r['model']} | {r['scored_count']}/{r['target_count']} | "
                        + " | ".join(values)
                        + " |"
                    )
    text += [
        "",
        "95% 区间和逐图记录见 REPORT.json。单轮按全部轮次均值；多轮只评会话最终图；"
        "两输入轨道分表。缺失不填零。smoke 不计算总体置信区间，不与已发表数字排名。",
        "",
    ]
    (destination / "REPORT.md").write_text("\n".join(text))
    return {"scope": plan["scope"], "report": str(destination / "REPORT.json"), "methods": methods}
