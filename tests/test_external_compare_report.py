"""Native aggregation, shared uncertainty and failure denominators for added methods."""

import numpy as np

from samtok_benchmark.external_compare.report import analyze
from samtok_benchmark.external_full.metrics import LABELS


def test_same_cohort_and_failure_intersection():
    models = ["flux2_klein9b", "mice", "qwen21", "sitedit"]
    rows = [
        {"case_id": str(i), "task": "edit", "language": "en", "cluster": str(i)} for i in range(3)
    ]
    records, native_rows = [], {}
    for mi, model in enumerate(models):
        valid = []
        for i, row in enumerate(rows):
            failed = model == "mice" and i == 2
            metrics = None if failed else {k: float(mi + i) for k in LABELS["interedit"]}
            records.append(
                {
                    "model": model,
                    "case_id": row["case_id"],
                    "status": "failed" if failed else "completed",
                    "metrics": metrics,
                }
            )
            if not failed:
                valid.append(mi + i)
        group = {"metrics": {k: {"mean": float(np.mean(valid))} for k in LABELS["interedit"]}}
        native_rows[model] = {g: group for g in ["all", "task/edit", "language/en"]}
    selection = {"benchmark": "interedit", "models": models, "rows": rows}
    native = {"per_case": records, "rows": native_rows}
    result = analyze(selection, native, repetitions=200)
    first = result["rows"][0]
    assert first["expected"] == 3
    assert first["common_scored"] == 2
    assert first["models"]["mice"]["scored"] == 2
    assert first["models"]["qwen21"]["mean"] == 3
    assert first["models"]["qwen21"]["common_mean"] == 2.5
    assert result["bootstrap"]["unit"] == "canonical source cluster"
    assert analyze(selection, native, repetitions=200) == result
