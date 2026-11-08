"""Full release micro/group means with original Omni area weights and explicit coverage."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import math
from pathlib import Path

from samtok_benchmark.external_refedit.data import read, immutable
from samtok_benchmark.io import digest, sha256_file
from .metrics import LABELS, WEIGHTS
from .launch import select_cases


def aggregate(rows, labels, weights):
    metrics = {}
    for key in labels:
        weight = weights.get(key)
        values = [
            (r["metrics"][key], r["metrics"][weight] if weight else 1)
            for r in rows
            if r["status"] == "completed" and r.get("metrics") and key in r["metrics"]
        ]
        denominator = math.fsum(w for _, w in values)
        metrics[key] = {
            "mean": math.fsum(v * w for v, w in values) / denominator if denominator else None,
            "scored": len(values),
            "expected": len(rows),
            "complete": len(values) == len(rows),
            "weight": weight,
        }
    return {
        "expected": len(rows),
        "status_counts": dict(Counter(r["status"] for r in rows)),
        "metrics": metrics,
    }


def report(bundle, run, scores, output, models, case_ids=None):
    index = read(Path(bundle) / "index.json")
    if index["digest"] != digest({k: v for k, v in index.items() if k != "digest"}):
        raise ValueError("Bundle changed")
    private_path = Path(bundle) / "private/evaluation.json"
    if sha256_file(private_path) != index["provenance"]["private_sha256"]:
        raise ValueError("Scoring annotations changed")
    private = {r["case_id"]: r for r in read(private_path)}
    cases = select_cases(index, case_ids)
    bench = index["benchmark"]
    labels = LABELS[bench]
    weights = WEIGHTS if bench == "omni_iie" else {}

    def inspect(job):
        model, item = job
        cid = item["case_id"]
        p = Path(run) / model / "edit" / cid / "result.json"
        row = {
            "model": model,
            "case_id": cid,
            "task": item["task"],
            "status": "not_generated",
            "metrics": None,
        }
        row.update({k: private[cid][k] for k in ("language", "pair") if k in private[cid]})
        if item.get("input_error"):
            if p.exists():
                raise ValueError("Unexpected inference for a case marked as invalid input")
            row.update(status="data_input_invalid", input_error=item["input_error"])
            return row
        if not p.exists():
            return row
        result = read(p)
        if (
            result["identity"]["model"] != model
            or result["identity"]["case_id"] != cid
            or result["identity"]["bundle_digest"] != index["digest"]
            or read(p.with_name("ADMITTED.json"))["identity"] != result["identity"]
        ):
            raise ValueError("Invalid generation binding")
        row.update(
            generation_status=result["status"],
            generation_record=str(p),
            status="score_missing" if result["status"] == "completed" else result["status"],
        )
        if (
            result["status"] == "completed"
            and sha256_file(result["output_image"]) != result["output_sha256"]
        ):
            raise ValueError("Generated output changed")
        s = Path(scores) / model / cid / "local.json"
        if s.exists():
            score = read(s)
            identity = score["identity"]
            if any(
                identity[k] != v
                for k, v in {
                    "model": model,
                    "case_id": cid,
                    "bundle_digest": index["digest"],
                    "result_sha256": sha256_file(p),
                    "output_sha256": result.get("output_sha256"),
                    "private_row_digest": digest(private[cid]),
                }.items()
            ):
                raise ValueError("Score/output binding mismatch")
            row.update(status=score["status"], metrics=score.get("metrics"), score_record=str(s))
        return row

    with ThreadPoolExecutor(max_workers=16) as pool:
        per_case = list(pool.map(inspect, ((m, c) for m in models for c in cases)))
    rows = {}
    for model in models:
        selected = [r for r in per_case if r["model"] == model]
        groups = {"all": aggregate(selected, labels, weights)}
        for task in sorted({r["task"] for r in selected}):
            groups["task/" + task] = aggregate(
                [r for r in selected if r["task"] == task], labels, weights
            )
        for lang in sorted({r["language"] for r in selected if "language" in r}):
            groups["language/" + lang] = aggregate(
                [r for r in selected if r.get("language") == lang], labels, weights
            )
        rows[model] = groups
    payload = {
        "schema": "external.full.report.v1",
        "benchmark": bench,
        "bundle_digest": index["digest"],
        "scope": "full" if len(cases) == len(index["cases"]) else "bounded-smoke",
        "case_ids": [r["case_id"] for r in cases],
        "models": list(models),
        "labels": labels,
        "not_available": ["S_ref_AlphaCLIP", "VLM"] if bench == "interedit" else ["QA", "Overall"],
        "failure_policy": "Retain all expected cases; no fabricated scores; report valid means with coverage",
        "rows": rows,
        "per_case": per_case,
    }
    output = Path(output)
    immutable(output / "REPORT.json", payload)
    lines = [
        f"# {bench} 全量评测结果",
        "",
        f"范围：{payload['scope']}；每方法 {len(cases)} 条请求。",
        "",
        "有效均值必须与覆盖率同时阅读；缺分不补零、不移除请求。",
        "",
    ]
    for group in rows[models[0]]:
        lines += [
            f"## {group}",
            "",
            "| 方法 | 有效 / 应评 | " + " | ".join(labels.values()) + " |",
            "|---|---:|" + "---:|" * len(labels),
        ]
        for model in models:
            r = rows[model][group]
            scoreset = r["metrics"]
            values = [
                "N/A" if scoreset[k]["mean"] is None else f"{scoreset[k]['mean']:.4f}"
                for k in labels
            ]
            lines.append(
                f"| {model} | {min(v['scored'] for v in scoreset.values())} / {r['expected']} | "
                + " | ".join(values)
                + " |"
            )
        lines.append("")
    (output / "REPORT.md").write_text("\n".join(lines).rstrip() + "\n")
    print(f"Report: {output / 'REPORT.md'}", flush=True)
    return payload
