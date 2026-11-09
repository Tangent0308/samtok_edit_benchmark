"""Source-paired uncertainty with each benchmark's unchanged aggregation rules."""

from dataclasses import dataclass
import hashlib
import math

import numpy as np

from samtok_benchmark.external_full.metrics import LABELS, WEIGHTS
from samtok_benchmark.external_full.report import GROUPS
from samtok_benchmark.external_full.score import METRICS
from . import MODELS, SEED

LOWER = {"LPIPS", "FG_LPIPS", "BG_LPIPS", "S_global_LPIPS", "BSS_Laplacian"}


@dataclass(frozen=True)
class Endpoint:
    group: str
    metric: str
    tasks: tuple = ()
    language: str | None = None
    macro: bool = False
    main: bool = True


def task(row):
    return row["task"] + (f"/turn{row['turn']}" if row.get("turn") else "")


def endpoints(bench, rows):
    if bench == "compbench":
        main = [
            Endpoint(group, key, tasks, macro=True)
            for group, tasks in list(GROUPS.items())[:5]
            for key in METRICS
        ]
        return main + [
            Endpoint(t, key, (t,), main=False)
            for t in sorted({task(r) for r in rows})
            for key in METRICS
        ]
    if bench == "interedit":
        return (
            [Endpoint("all", key) for key in LABELS[bench]]
            + [
                Endpoint("task/" + t, key, (t,), main=False)
                for t in sorted({r["task"] for r in rows})
                for key in LABELS[bench]
            ]
            + [
                Endpoint("language/" + lang, key, language=lang, main=False)
                for lang in sorted({r["language"] for r in rows})
                for key in LABELS[bench]
            ]
        )
    return [
        Endpoint(group, key, (group[5:],) if group.startswith("task/") else ())
        for group in ("all", "task/low", "task/high")
        for key in LABELS[bench]
    ]


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def interval(values):
    values = values[np.isfinite(values)]
    return list(map(float, np.quantile(values, [0.025, 0.975]))) if len(values) else None


def aggregate(values, weights, group_ids, counts=None):
    """Mean of subtask weighted means (one group for ordinary micro averages)."""
    means = []
    for group in sorted(set(group_ids)):
        valid = (group_ids == group) & np.isfinite(values) & (weights > 0)
        w = weights[valid]
        v = values[valid]
        if counts is None:
            denominator = w.sum()
            means.append(float(v @ w / denominator) if denominator else float("nan"))
        else:
            denominator = counts[:, valid] @ w
            numerator = counts[:, valid] @ (v * w)
            means.append(
                np.divide(
                    numerator, denominator, out=np.full(len(counts), np.nan), where=denominator > 0
                )
            )
    return np.mean(means, axis=0)


def holm(pvalues):
    """Keep unavailable endpoints in the predeclared family, conservatively as p=1."""
    values = np.array([1.0 if p is None else p for p in pvalues])
    order = np.argsort(values, kind="stable")
    adjusted = np.minimum(1.0, np.maximum.accumulate(values[order] * np.arange(len(values), 0, -1)))
    result = np.empty(len(values))
    result[order] = adjusted
    return list(map(float, result))


def analyze(bench, selection, report, repetitions=10000):
    rows = selection["rows"]
    if sorted(report["case_ids"]) != sorted(selection["case_ids"]) or set(report["models"]) != set(
        MODELS
    ):
        raise ValueError("Native report does not cover the fixed two-model cohort")
    records = {(r["model"], r["case_id"]): r for r in report["per_case"]}
    if len(records) != 2 * len(rows) or len(report["per_case"]) != len(records):
        raise ValueError("Native report has missing or duplicate records")
    clusters = sorted({r["cluster"] for r in rows})
    cluster_index = {c: i for i, c in enumerate(clusters)}
    n = len(clusters)
    rng = np.random.default_rng(SEED)
    draws = rng.multinomial(n, np.ones(n) / n, size=repetitions).astype(np.int32)
    flips = (
        np.random.default_rng(SEED + 1).integers(0, 2, size=(repetitions, n), dtype=np.int8) * 2 - 1
    )
    sampling = {
        "seed": SEED,
        "repetitions": repetitions,
        "unit": "canonical source cluster",
        "source_clusters": n,
        "cluster_order": clusters,
        "shared_bootstrap_counts_sha256": hashlib.sha256(draws.tobytes()).hexdigest(),
        "shared_permutation_signs_sha256": hashlib.sha256(flips.tobytes()).hexdigest(),
        "confidence_intervals": "pointwise 95%; not simultaneous",
        "permutation": "one-sided paired source-cluster model-label swap; +1 Monte Carlo correction",
    }
    output = []
    for ep in endpoints(bench, rows):
        selected = [
            r
            for r in rows
            if (not ep.tasks or task(r) in ep.tasks)
            and (ep.language is None or r.get("language") == ep.language)
        ]
        idx = np.array([cluster_index[r["cluster"]] for r in selected])
        weights = np.ones(len(selected))
        values = np.full((2, len(selected)), np.nan)
        weight_key = WEIGHTS.get(ep.metric) if bench == "omni_iie" else None
        for j, row in enumerate(selected):
            observed_weights = []
            for m, model in enumerate(MODELS):
                record = records[model, row["case_id"]]
                metric = (record.get("metrics") or {}).get(ep.metric)
                if record["status"] == "completed" and finite(metric):
                    values[m, j] = metric
                    if weight_key:
                        w = record["metrics"].get(weight_key)
                        if not finite(w) or w < 0:
                            raise ValueError("Invalid native region weight")
                        observed_weights.append(w)
            if observed_weights:
                if any(abs(w - observed_weights[0]) > 1e-12 for w in observed_weights):
                    raise ValueError("Native weights differ across methods for the same request")
                weights[j] = observed_weights[0]
        group_ids = np.array([task(r) if ep.macro else "all" for r in selected])
        counts = draws[:, idx]
        points = [float(aggregate(v, weights, group_ids)) for v in values]
        model_ci = [interval(aggregate(v, weights, group_ids, counts)) for v in values]
        joint = np.isfinite(values).all(axis=0)
        paired = values.copy()
        paired[:, ~joint] = np.nan
        direction = -1 if ep.metric in LOWER else 1
        paired_points = [float(aggregate(v, weights, group_ids)) for v in paired]
        effect = direction * (paired_points[0] - paired_points[1])
        boot_delta = direction * (
            aggregate(paired[0], weights, group_ids, counts)
            - aggregate(paired[1], weights, group_ids, counts)
        )
        # A source-cluster flip applies to all its requests and both autoregressive turns.
        contributions = np.zeros(n)
        for group in sorted(set(group_ids)):
            valid = joint & (group_ids == group) & (weights > 0)
            denominator = weights[valid].sum()
            if not denominator:
                contributions[:] = np.nan
                break
            np.add.at(
                contributions,
                idx[valid],
                direction
                * weights[valid]
                * (paired[0, valid] - paired[1, valid])
                / denominator
                / len(set(group_ids)),
            )
        if finite(effect) and np.isfinite(contributions).all():
            if not np.isclose(contributions.sum(), effect, atol=1e-10):
                raise ValueError("Permutation statistic differs from the native aggregation")
            null = flips @ contributions
            pvalue = float((1 + np.count_nonzero(null >= effect - 1e-12)) / (repetitions + 1))
        else:
            pvalue = None
        native = []
        for model in MODELS:
            if bench == "compbench":
                section, field = ("groups", "group") if ep.main else ("tasks", "task")
                native.append(
                    next(r for r in report["rows"][model][section] if r[field] == ep.group)[
                        "valid_mean"
                    ][ep.metric]
                )
            else:
                native.append(report["rows"][model][ep.group]["metrics"][ep.metric]["mean"])
        for actual, original in zip(points, native):
            if original is not None and (not finite(actual) or abs(actual - original) > 1e-10):
                raise ValueError(f"Native aggregate mismatch: {bench}/{ep.group}/{ep.metric}")

        def clean(value):
            return float(value) if finite(value) else None

        output.append(
            {
                "group": ep.group,
                "metric": ep.metric,
                "main_endpoint": ep.main,
                "direction": "lower" if direction < 0 else "higher",
                "weight": weight_key,
                "aggregation": "equal subtask means"
                if ep.macro
                else "native weighted mean"
                if weight_key
                else "micro mean",
                "expected": len(selected),
                "paired_scored": int(joint.sum()),
                "paired_source_clusters": len(set(idx[joint])),
                "models": {
                    model: {
                        "mean": clean(points[i]),
                        "CI95": model_ci[i],
                        "scored": int(np.isfinite(values[i]).sum()),
                        "paired_mean": clean(paired_points[i]),
                    }
                    for i, model in enumerate(MODELS)
                },
                "benefit_delta": clean(effect),
                "benefit_CI95": interval(boot_delta),
                "valid_bootstrap_replicates": int(np.isfinite(boot_delta).sum()),
                "p_one_sided": pvalue,
            }
        )
    return {
        "benchmark": bench,
        "sampling": sampling,
        "rows": output,
        "native_aggregates_verified": True,
    }
