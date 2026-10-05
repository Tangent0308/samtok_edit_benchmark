"""Coverage-aware reports; preserve unknowns and separate human/VLM judgments."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from samtok_benchmark.io import read_jsonl, sha256_file, write_json, write_jsonl
from samtok_benchmark.judge.rubric import derive, parse


def summarize(records: list[dict]) -> dict:
    n = len(records)
    result = {"n": n, "status": dict(Counter(r["status"] for r in records))}
    for key in ("all_edits_success", "strict_success"):
        values = [
            False if r["status"] == "missing_output" else r.get("scores", {}).get(key)
            for r in records
        ]
        yes, no = sum(v is True for v in values), sum(v is False for v in values)
        unknown = n - yes - no
        result[key] = {
            "success": yes,
            "failure": no,
            "unknown": unknown,
            "coverage": (yes + no) / n if n else None,
            "rate_on_decidable": yes / (yes + no) if yes + no else None,
            "lower_bound": yes / n if n else None,
            "upper_bound": (yes + unknown) / n if n else None,
        }
    for key in ("edit", "preservation", "quality"):
        values = [r.get("scores", {}).get(key) for r in records]
        valid = [v for v in values if v is not None]
        result[key] = {
            "mean_on_decidable": sum(valid) / len(valid) if valid else None,
            "distribution": dict(Counter(valid)),
            "decidable": len(valid),
            "unknown": n - len(valid),
        }
    return result


def report(manifest: Path, run: Path, output: Path, human_scores: Path | None = None) -> dict:
    config = json.loads((run / "config.rank0.json").read_text())
    if sha256_file(manifest) != config["manifest_sha256"]:
        raise ValueError("report manifest differs from judge run")
    jobs = {j["sample_id"]: j for j in read_jsonl(manifest)}
    selected = config["selected_sample_ids"]
    if len(selected) != len(set(selected)) or not set(selected).issubset(jobs):
        raise ValueError("invalid selected sample cohort")
    run_id = config["run_id"]
    actual = {}
    for path in sorted((run / "records").glob("*.json")):
        r = json.loads(path.read_text())
        if r["run_id"] != run_id:
            continue
        key = (r["sample_id"], r["variant"])
        if key in actual or key[0] not in selected or key[1] not in config["variants"]:
            raise ValueError("duplicate or unexpected judge result")
        if r.get("sample", {}).get("input_digest") != jobs[key[0]]["input_digest"]:
            raise ValueError("judge result contains different frozen inputs")
        actual[key] = r
    records = []
    for variant in config["variants"]:
        for sid in selected:
            job = jobs[sid]
            # Absent image generation counts as failure even before a judge worker handles it.
            fallback = "missing_output" if job["delivery_status"] != "available" else "pending"
            records.append(
                actual.get(
                    (sid, variant),
                    {"sample_id": sid, "variant": variant, "sample": job, "status": fallback},
                )
            )
    groups = defaultdict(list)
    for r in records:
        j = r["sample"]
        groups[(r["variant"], j["method"], j["protocol"], j["setting"])].append(r)
    tables = [
        {
            "variant": k[0],
            "method": k[1],
            "protocol": k[2],
            "setting": k[3],
            **summarize(v),
            "by_source": {
                d: summarize([r for r in v if r["sample"]["source_dataset"] == d])
                for d in sorted({r["sample"]["source_dataset"] for r in v})
            },
            "by_operation": {
                d: summarize([r for r in v if r["sample"]["edit_type"] == d])
                for d in sorted({r["sample"]["edit_type"] for r in v})
            },
        }
        for k, v in sorted(groups.items())
    ]
    result = {
        "run_id": run_id,
        "manifest_sha256": config["manifest_sha256"],
        "expected_records": len(records),
        "completed_records": len(actual),
        "status": dict(Counter(r["status"] for r in records)),
        "groups": tables,
        "score_provenance": "VLM judgments; not independently verified human gold",
    }
    if human_scores:
        humans = read_jsonl(human_scores)
        seen = set()
        paired = defaultdict(list)
        for h in humans:
            sid, reviewer = h["sample_id"], h["reviewer"]
            if not isinstance(reviewer, str) or not reviewer.strip() or (sid, reviewer) in seen:
                raise ValueError("human reviewer missing or duplicate reviewer/sample")
            seen.add((sid, reviewer))
            if sid not in jobs or h.get("input_digest") != jobs[sid]["input_digest"]:
                raise ValueError("human record belongs to another sample/instruction/output")
            parse(json.dumps(h))
            for variant in config["variants"]:
                vlm = actual.get((sid, variant))
                if vlm and vlm["status"] == "ok":
                    paired[(reviewer, variant)].append((h, vlm))
        agreement = []
        for (reviewer, variant), pairs in sorted(paired.items()):
            item = {"reviewer": reviewer, "variant": variant, "paired_records": len(pairs)}
            for axis in ("edit", "preservation", "quality", "strict_success"):
                vals = [
                    (derive(h)[axis] if axis == "strict_success" else h[axis], v["scores"][axis])
                    for h, v in pairs
                ]
                vals = [(a, b) for a, b in vals if a is not None and b is not None]
                item[axis] = {
                    "decidable_pairs": len(vals),
                    "exact_agreement": sum(a == b for a, b in vals) / len(vals) if vals else None,
                    "mean_absolute_error": (
                        sum(abs(a - b) for a, b in vals) / len(vals)
                        if vals and axis != "strict_success"
                        else None
                    ),
                }
            agreement.append(item)
        result["human_review"] = {
            "records": len(humans),
            "reviewers": sorted({h["reviewer"] for h in humans}),
            "agreement": agreement,
            "policy": "Human records stay separate; adjudication is not automatic.",
        }
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "summary.json", result)
    write_jsonl(output / "records.jsonl", records)
    md = [
        "# v1 evaluation report",
        "",
        f"Completed: {len(actual)}/{len(records)}",
        "",
        "VLM scores are independent of the dataset pass/discard decisions.",
        "",
        "| Method | Input protocol | Setting | N | Strict success | Unknown | Lower–upper |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for g in tables:
        s = g["strict_success"]
        md.append(
            f"| {g['method']} | {g['protocol']} | {g['setting']} | {g['n']} | "
            f"{s['success']} | {s['unknown']} | {s['lower_bound']:.3f}–{s['upper_bound']:.3f} |"
        )
    (output / "REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return result
