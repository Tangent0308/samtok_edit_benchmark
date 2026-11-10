"""Coverage-aware paired scene-cluster statistics for supplementary scores."""

from pathlib import Path

from .bundle import load
from .common import digest, read, save
from .worker import effective

METRICS = ["E", "P", "Q", "E_pass", "P_pass", "Q_pass", "all_edit_pass"]


def report(bundle, output, destination):
    import numpy as np

    plan = load(bundle, verify_assets=False)
    output, destination = Path(output), Path(destination)
    config = read(output / "CONFIGURATION.json")
    if config["plan_digest"] != plan["digest"]:
        raise ValueError("Report plan differs")
    available = {}
    for p in (output / "effective").glob("*.json"):
        value = read(p)
        raw = read(output / "raw" / p.name)
        admission = read(output / "admissions" / p.name)
        if admission["identity"] != config["identity"] or admission["request_key"] != p.stem:
            raise ValueError(f"Wrong admission: {p}")
        if raw["identity"] != config["identity"] or raw["request_key"] != p.stem:
            raise ValueError(f"Wrong raw binding: {p}")
        if value != effective(raw, config["identity"], p.stem):
            raise ValueError(f"Raw/effective mismatch: {p}")
        available[p.stem] = value
    cases = [
        c for c in plan["cases"] if not config["smoke"] or c["case_id"] in plan["smoke_case_ids"]
    ]
    by_case = {c["case_id"]: c for c in cases}
    per_case = []
    for b in plan["bindings"]:
        if b["case_id"] not in by_case:
            continue
        value = available.get(b["request_key"], {"status": "missing"})
        item = {
            "model": b["model"],
            "case_id": b["case_id"],
            "task": by_case[b["case_id"]]["task"],
            "status": value["status"],
            "request_key": b["request_key"],
        }
        if value["status"] == "scored":
            scores = value["scores"]
            item["metrics"] = {k: scores[k]["score"] for k in ("E", "P", "Q")}
            item["metrics"].update(
                {
                    f"{k}_pass": int(scores[k]["score"] >= t)
                    for k, t in (("E", 4), ("P", 3), ("Q", 3))
                }
            )
            item["metrics"]["all_edit_pass"] = int(scores["all_edit_pass"])
            item["evidence"] = {k: scores[k]["evidence"] for k in ("E", "P", "Q")}
        per_case.append(item)
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
    result = {
        "protocol": plan["configuration"]["rubric"]["protocol"],
        "plan_digest": plan["digest"],
        "identity": config["identity"],
        "smoke": config["smoke"],
        "rows": rows,
        "paired_differences": differences,
        "per_case": per_case,
        "bootstrap": {**plan["bootstrap"], "groups": bootstrap},
    }
    result["digest"] = digest(result)
    destination.mkdir(parents=True, exist_ok=True)
    save(destination / "REPORT.json", result, immutable=True)
    lines = [
        "# CompBench 多目标补充 E/P/Q 结果",
        "",
        "本表是独立补充诊断，不替代 CompBench 官方客观指标；整条通过要求 E=4、P≥3、Q≥3。",
        "分数为 0–4，通过率为百分比；缺分不补零。"
        + (" **本次仅为 TP4 流程验证，不作为正式结果。**" if config["smoke"] else ""),
        "",
    ]
    for task in ("all", "multi_object_add", "multi_object_remove"):
        lines += [
            f"## {task}",
            "",
            "| 方法 | 已判/总数 | E ↑ | P ↑ | Q ↑ | E 通过 % | 整条通过 % [95% CI] |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for r in rows:
            if r["task"] != task:
                continue
            m = r["mean"]
            if m is None:
                values = "— | — | — | — | 缺分"
            else:
                ci = r["CI95"]["all_edit_pass"]
                values = (
                    f"{m['E']:.3f} | {m['P']:.3f} | {m['Q']:.3f} | "
                    f"{100 * m['E_pass']:.1f} | {100 * m['all_edit_pass']:.1f} "
                    f"[{100 * ci[0]:.1f}, {100 * ci[1]:.1f}]"
                )
            lines.append(f"| {r['model']} | {r['scored']}/{r['total']} | {values} |")
        lines.append("")
    md = destination / "REPORT.md"
    content = "\n".join(lines) + "\n"
    if md.exists() and md.read_text() != content:
        raise ValueError("Refusing to overwrite a different report")
    md.write_text(content)
    return {
        "report": str(destination / "REPORT.json"),
        "complete_rows": sum(r["complete"] for r in rows),
        "scored": sum(p["status"] == "scored" for p in per_case),
        "total": len(per_case),
    }
