"""Frozen scene-paired formulas, with explicit input records for an overlay.

Statistics body is copied without changing its formulas from vlm_judge/report.py
at d518998. Every run verifies the original report before applying the overlay.
"""

from samtok_benchmark.external_compbench.vlm_judge.report import METRICS


def aggregate(per_case, plan):
    import numpy as np

    cases = plan["cases"]
    rows, differences, bootstrap = [], [], {}
    for task in ("all", "multi_object_add", "multi_object_remove"):
        selected = [c for c in cases if task == "all" or c["task"] == task]
        ids = [c["case_id"] for c in selected]
        clusters = sorted({c["cluster"] for c in selected})
        if not selected:
            continue
        group = np.array([clusters.index(c["cluster"]) for c in selected])
        rng = np.random.default_rng(plan["bootstrap"]["seed"])
        samples = rng.integers(len(clusters), size=(plan["bootstrap"]["replicates"], len(clusters)))
        weights = np.array([np.bincount(s, minlength=len(clusters)) for s in samples])[:, group]
        bootstrap[task] = {
            "clusters": len(clusters),
            "samples_sha256": __import__("hashlib")
            .sha256(samples.astype("<i8").tobytes())
            .hexdigest(),
        }
        arrays = {}
        for model in plan["models"]:
            entries = {
                p["case_id"]: p for p in per_case if p["model"] == model and p["case_id"] in ids
            }
            valid = [entries[c] for c in ids if entries[c]["status"] == "scored"]
            row = {
                "model": model,
                "task": task,
                "total": len(ids),
                "scored": len(valid),
                "complete": len(valid) == len(ids),
                "mean": None,
                "CI95": None,
            }
            if valid:
                row["scored_subset_mean"] = {
                    m: float(np.mean([v["metrics"][m] for v in valid])) for m in METRICS
                }
            if row["complete"]:
                array = np.array([[entries[c]["metrics"][m] for m in METRICS] for c in ids])
                arrays[model] = array
                row["mean"] = dict(zip(METRICS, array.mean(axis=0).tolist()))
                dist = weights @ array / weights.sum(axis=1)[:, None]
                row["CI95"] = dict(
                    zip(METRICS, np.quantile(dist, [0.025, 0.975], axis=0).T.tolist())
                )
            rows.append(row)
        if "sitedit" in arrays:
            for model in plan["models"]:
                if model == "sitedit" or model not in arrays:
                    continue
                delta = arrays["sitedit"] - arrays[model]
                dist = weights @ delta / weights.sum(axis=1)[:, None]
                differences.append(
                    {
                        "task": task,
                        "comparison": f"sitedit - {model}",
                        "mean": dict(zip(METRICS, delta.mean(axis=0).tolist())),
                        "CI95": dict(
                            zip(METRICS, np.quantile(dist, [0.025, 0.975], axis=0).T.tolist())
                        ),
                    }
                )
    return {
        "rows": rows,
        "paired_differences": differences,
        "bootstrap": {**plan["bootstrap"], "groups": bootstrap},
    }
