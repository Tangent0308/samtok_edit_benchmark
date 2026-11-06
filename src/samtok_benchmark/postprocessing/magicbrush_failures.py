"""User-authorized worst-bound generation-failure aggregation, outside the frozen evaluator."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

from samtok_benchmark.external_magicbrush import report as original
from samtok_benchmark.external_magicbrush.metrics import METRICS
from samtok_benchmark.io import sha256_file

PENALTIES = {"L1": 1.0, "L2": 1.0, "CLIP-I": -1.0, "DINO": -1.0, "CLIP-T": -1.0}
POLICY = {
    "id": "magicbrush.failed-generation.worst-bound.v1",
    "authorization_date_utc": "2026-11-06",
    "values": PENALTIES,
    "applies_to": "Terminal generation failures, including failed recurrent dependencies; all methods equally.",
    "unresolved": "Missing generation and missing/failed scoring are not generation failures and are not imputed.",
    "interpretation": "Assigned aggregation penalties, not measured image scores; separate from official metric reporting.",
}


def _means(sums, counts):
    if not int(counts.sum()):
        return None
    return dict(zip(METRICS, (sums.sum(axis=0) / counts.sum()).tolist()))


def _ci(sums, counts, indices):
    distribution = original.bootstrap(sums, counts, indices)
    return dict(zip(METRICS, np.percentile(distribution, [2.5, 97.5], axis=0).T.tolist()))


def _check_numbers(actual, expected, description):
    if actual is None or expected is None:
        if actual != expected:
            raise ValueError(f"{description}: missing value mismatch")
        return
    if set(actual) != set(expected) or not all(
        np.allclose(actual[k], expected[k], rtol=0, atol=1e-12) for k in actual
    ):
        raise ValueError(f"{description}: does not reproduce original report")


def build_report(source):
    """Recompute the original statistics first, then add explicitly labeled failure penalties."""
    if source.get("schema") != "magicbrush.report.v1" or source.get("scope") != "full":
        raise ValueError("Requires the full frozen MagicBrush report, not smoke results")
    if source["statistics_code_sha256"] != sha256_file(Path(original.__file__)):
        raise ValueError("Frozen original statistics implementation changed")
    boot = source["bootstrap"]
    if (boot["seed"], boot["draws"]) != (original.BOOTSTRAP_SEED, original.BOOTSTRAP_DRAWS):
        raise ValueError("Original bootstrap configuration changed")
    draws, session_maps = {}, {}
    for subset, spec in boot["subsets"].items():
        sessions = spec["sessions"]
        if not sessions or len(set(sessions)) != len(sessions):
            raise ValueError("Invalid bootstrap session population")
        indices = np.random.default_rng(boot["seed"]).integers(
            0, len(sessions), size=(boot["draws"], len(sessions)), dtype=np.int32
        )
        if hashlib.sha256(indices.tobytes()).hexdigest() != spec["indices_sha256"]:
            raise ValueError("Original shared bootstrap indices do not match")
        draws[subset] = indices
        session_maps[subset] = {s: n for n, s in enumerate(sessions)}
    rows, identities, cohorts = [], set(), {}
    for row in source["rows"]:
        identity = tuple(row[k] for k in ("model", "subset", "track", "mode"))
        if identity in identities:
            raise ValueError("Duplicate model/panel row")
        identities.add(identity)
        panel = identity[1:]
        cases = row["per_case"]
        cohort = {(c["key"], c["session_id"]) for c in cases}
        if not cases or len(cases) != row["target_count"] or len(cohort) != len(cases):
            raise ValueError("Invalid or duplicate request denominator")
        if panel in cohorts and cohort != cohorts[panel]:
            raise ValueError("Methods have different request populations")
        cohorts[panel] = cohort
        mapping = session_maps[row["subset"]]
        observed_sums = np.zeros((len(mapping), len(METRICS)))
        observed_counts = np.zeros(len(mapping), dtype=np.int64)
        penalty_sums = np.zeros_like(observed_sums)
        penalty_counts = np.zeros_like(observed_counts)
        records, statuses = [], Counter()
        for case in cases:
            record = deepcopy(case)
            n = mapping[case["session_id"]]
            if case["status"] == "scored":
                values = np.array([case["metrics"][m] for m in METRICS], dtype=float)
                lower = np.array([0.0, 0.0, -1.0, -1.0, -1.0])
                if (
                    not np.isfinite(values).all()
                    or (values < lower - 1e-6).any()
                    or (values > 1 + 1e-6).any()
                ):
                    raise ValueError("Measured metric outside its defined domain")
                observed_sums[n] += values
                observed_counts[n] += 1
                record["contribution_kind"] = "measured"
                statuses["measured"] += 1
            elif case["status"] == "failed":
                if "metrics" in case:
                    raise ValueError("A failed generation unexpectedly carries measured metrics")
                penalty_sums[n] += np.array([PENALTIES[m] for m in METRICS])
                penalty_counts[n] += 1
                record["contribution_kind"] = "generation_failure_penalty"
                record["assigned_penalty"] = dict(PENALTIES)
                statuses["penalized"] += 1
            else:
                record["contribution_kind"] = "unresolved"
                statuses["unresolved"] += 1
            records.append(record)
        if int(observed_counts.sum()) != row["scored_count"]:
            raise ValueError("Original scored count does not match per-request records")
        original_complete = int(observed_counts.sum()) == len(cases)
        if bool(row["complete"]) != original_complete:
            raise ValueError("Original completeness flag is inconsistent")
        means = _means(observed_sums, observed_counts)
        _check_numbers(means, row["available_only_means"], "Available-only mean")
        _check_numbers(means if original_complete else None, row["metrics"], "Original mean")
        if original_complete:
            _check_numbers(
                _ci(observed_sums, observed_counts, draws[row["subset"]]),
                row["CI95"],
                "Original CI",
            )
        elif row["CI95"] is not None:
            raise ValueError("Incomplete original row unexpectedly has a CI")
        sums, counts = observed_sums + penalty_sums, observed_counts + penalty_counts
        complete = int(counts.sum()) == len(cases)
        rows.append(
            {
                **{k: row[k] for k in ("model", "subset", "track", "mode", "target_count")},
                "measured_count": statuses["measured"],
                "generation_failed_count": statuses["penalized"],
                "unresolved_count": statuses["unresolved"],
                "included_count": int(counts.sum()),
                "generation_failure_fraction": statuses["penalized"] / len(cases),
                "complete": complete,
                "metrics": _means(sums, counts) if complete else None,
                "CI95": _ci(sums, counts, draws[row["subset"]]) if complete else None,
                "original_complete": original_complete,
                "per_case": records,
            }
        )
    if not rows:
        raise ValueError("No original report rows")
    return {
        "schema": "magicbrush.failure-inclusive-report.v1",
        "scope": "full",
        "policy": deepcopy(POLICY),
        "rows": rows,
        "complete": all(r["complete"] for r in rows),
        "bootstrap": deepcopy(boot),
        "overlap": deepcopy(source["overlap"]),
        "run_digest": source["run_digest"],
        "original_statistics_verified_rows": len(rows),
        "original_complete_verified_rows": sum(r["complete"] for r in source["rows"]),
        "original_statistics_code_sha256": source["statistics_code_sha256"],
    }


def markdown(report):
    lines = [
        "# MagicBrush：含失败惩罚的全量结果",
        "",
        "按用户于 2026-11-06 确认的规则，生成失败纳入完整分母：L1/L2=1，CLIP-I/DINO/CLIP-T=−1。",
        "这些是明确约定的失败惩罚，不是对不存在图像测得的分数。八个方法使用相同规则，连续编辑的上游失败也按请求计入。",
        "原始图像、生成记录、标准指标评分和原始报告均未修改。缺失生成、尚未评分或评分失败仍列为未解决项，不冒充生成失败。",
        "本表的汇总口径包含额外失败惩罚，与未采用相同规则的已发表数字不直接排名。",
        "",
        f"原始报告：`{report['original_report']['path']}`；SHA256：`{report['original_report']['sha256']}`。",
        f"逐项复核原始统计 {report['original_statistics_verified_rows']} 行，其中完整行 {report['original_complete_verified_rows']} 行。",
        "置信区间沿用原报告的会话级配对 bootstrap 抽样：seed 20261105，10,000 次；失败惩罚随所属会话一同重采样。",
        "",
        "## 训练重合审计",
        "",
        f"已知重合统一排除 {report['overlap']['excluded_sessions']} 个会话；去重合子集保留 {report['overlap']['clean_sessions']} 个会话、{report['overlap']['clean_turns']} 个独立轮次。",
        report["overlap"]["limits"],
    ]
    panels = list(
        dict.fromkeys(tuple(r[k] for k in ("subset", "track", "mode")) for r in report["rows"])
    )
    for subset, track, mode in panels:
        lines.extend(
            [
                "",
                f"## {subset} / {track} / {mode}",
                "",
                "单元格为均值 [95% CI]。失败/目标只计算该面板的请求；同一首轮可被独立、连续评测共用，不跨面板相加。",
                "",
                "| 方法 | 实测 | 失败/目标 | 未解决 | L1 ↓ | L2 ↓ | CLIP-I ↑ | DINO ↑ | CLIP-T ↑ |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in report["rows"]:
            if (row["subset"], row["track"], row["mode"]) != (subset, track, mode):
                continue
            values = []
            for metric in METRICS:
                if row["complete"]:
                    low, high = row["CI95"][metric]
                    values.append(f"{row['metrics'][metric]:.4f} [{low:.4f}, {high:.4f}]")
                else:
                    values.append("待解决缺项")
            cells = [
                row["model"],
                str(row["measured_count"]),
                f"{row['generation_failed_count']}/{row['target_count']}",
                str(row["unresolved_count"]),
                *values,
            ]
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def publish(source_path, destination):
    source_path, destination = Path(source_path).resolve(), Path(destination).resolve()
    if destination.exists() or destination.is_relative_to(source_path.parent):
        raise ValueError("Use a new directory outside the original report directory; no overwrites")
    source_bytes = source_path.read_bytes()
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    value = build_report(json.loads(source_bytes))
    value.update(
        {
            "original_report": {"path": str(source_path), "sha256": source_sha},
            "postprocessor_source_sha256": sha256_file(Path(__file__)),
            "time": datetime.now(timezone.utc).isoformat(),
        }
    )
    if sha256_file(source_path) != source_sha:
        raise ValueError("Original report changed during processing; retry after it is final")
    text = markdown(value)
    destination.mkdir(parents=True, exist_ok=False)
    with (destination / "REPORT.json").open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    with (destination / "REPORT.md").open("x", encoding="utf-8") as stream:
        stream.write(text)
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    result = publish(args.source_report, args.destination)
    print(
        json.dumps(
            {
                "destination": str(args.destination),
                "complete": result["complete"],
                "rows": len(result["rows"]),
            }
        )
    )
    return 0
