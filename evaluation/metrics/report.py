"""Coverage-aware score tables, control checks, stability comparisons, and audit gallery."""
from __future__ import annotations

import argparse
import html
import json
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from evaluation.common import atomic_write_json, read_jsonl, sha256_file
from evaluation.metrics.protocol import digest


def summarize(records):
    n = len(records)
    result = {"n": n, "status": dict(Counter(r["status"] for r in records))}
    for key in ("all_edits_success", "strict_success"):
        values = [r.get("scores", {}).get(key) for r in records]
        # Generation failures are failures; judge failures/pending/annotation issues remain unknown.
        values = [False if r["status"] == "missing_output" else v for r, v in zip(records, values)]
        yes = sum(v is True for v in values)
        no = sum(v is False for v in values)
        unknown = n - yes - no
        result[key] = {"success": yes, "failure": no, "unknown": unknown,
                       "coverage": (yes+no)/n if n else None,
                       "rate_on_decidable": yes/(yes+no) if yes+no else None,
                       "lower_bound": yes/n if n else None,
                       "upper_bound": (yes+unknown)/n if n else None}
    for key in (["edit"] if any("edit" in r.get("scores", {}) for r in records) else []) + ["preservation", "quality"]:
        values = [r.get("scores", {}).get(key) for r in records]
        valid = [v for v in values if v is not None]
        result[key] = {"mean_on_decidable": sum(valid)/len(valid) if valid else None,
                       "distribution": dict(Counter(valid)),
                       "decidable": len(valid), "unknown": n-len(valid)}
    return result


def signature(record):
    if record["status"] != "ok":
        return None
    return record["scores"]


def make_report(args):
    config_path = args.run / "config.rank0.json"
    if not config_path.exists():
        raise FileNotFoundError("run config not yet created; judge may still be waiting for GPUs")
    config = json.loads(config_path.read_text())
    if sha256_file(Path(args.manifest)) != config["manifest_sha256"]:
        raise ValueError("report manifest differs from the frozen judge manifest")
    run_id = config["run_id"]
    rows = {r["sample_id"]: r for r in read_jsonl(Path(args.manifest))
            if r["sample_id"] in set(config["selected_sample_ids"])}
    if len(rows) != len(config["selected_sample_ids"]):
        raise ValueError("missing or duplicate selected samples")
    actual = {}
    for path in sorted((args.run / "records").glob("*.json")):
        r = json.loads(path.read_text())
        if r["run_id"] == run_id:
            key = (r["sample_id"], r["variant"])
            if key in actual:
                raise ValueError(f"duplicate result: {key}")
            actual[key] = r
    records = []
    for variant in config["variants"]:
        for sample_id, row in rows.items():
            records.append(actual.get((sample_id, variant), {
                "sample_id": sample_id, "variant": variant, "sample": row, "status": "pending"}))
    groups = defaultdict(list)
    for r in records:
        s = r["sample"]
        # Never mix generation protocols, variants, cohorts, or splits in rankings.
        groups[(r["variant"], s["method"], s["setting"], s["split"], s["source_dataset"])].append(r)
    tables = [{"variant": k[0], "method": k[1], "setting": k[2], "split": k[3],
               "source_dataset": k[4], **summarize(v)} for k, v in sorted(groups.items())]
    stability = []
    reference = next(iter(config["variants"]))
    for other in config["variants"]:
        if other == reference:
            continue
        pairs = [(actual.get((s, reference)), actual.get((s, other))) for s in rows]
        valid = [(a, b) for a, b in pairs if a and b and a["status"] == b["status"] == "ok"]
        changed = [a["sample_id"] for a, b in valid if signature(a) != signature(b)]
        strict_changed = [a["sample_id"] for a, b in valid
                          if a["scores"]["strict_success"] != b["scores"]["strict_success"]]
        stability.append({"reference": reference, "variant": other, "paired_parsed": len(valid),
                          "unpaired_or_error": len(rows)-len(valid), "any_axis_changed": len(changed),
                          "strict_changed": len(strict_changed), "changed_sample_ids": changed,
                          "strict_changed_sample_ids": strict_changed})
    checks = []
    check_counts = defaultdict(Counter)
    for r in records:
        expected = r["sample"]["expected"]
        if expected:
            counts = check_counts[(r["variant"], r["sample"]["label_provenance"])]
            counts["total"] += 1
            expected_success = expected.get("all_edits_success")
            actual_success = r.get("scores", {}).get("all_edits_success")
            if expected_success is not None:
                counts["binary_labeled"] += 1
            if expected_success is not None and actual_success is None:
                counts["unresolved"] += 1
            elif expected_success is True:
                counts["true_positive" if actual_success else "false_negative"] += 1
            elif expected_success is False:
                counts["false_positive" if actual_success else "true_negative"] += 1
            disagreements = {k: {"expected": v, "actual": r.get("scores", {}).get(k)}
                             for k, v in expected.items() if r.get("scores", {}).get(k) != v
                             and k in {"edit", "preservation", "quality", "all_edits_success", "strict_success"}}
            for key, (low, high) in r["sample"].get("expected_ranges", {}).items():
                actual_value = r.get("scores", {}).get(key)
                if actual_value is None or not low <= actual_value <= high:
                    disagreements[key] = {"expected_range": [low, high], "actual": actual_value}
            checks.append({"sample_id": r["sample_id"], "variant": r["variant"], "status": r["status"],
                             "label_provenance": r["sample"]["label_provenance"],
                             "disagreements": disagreements})
    report = {"run_id": run_id, "expected_records": len(records), "completed_records": len(actual),
              "status": dict(Counter(r["status"] for r in records)), "groups": tables,
              "stability": stability, "checks": checks,
              "check_counts": [{"variant": k[0], "provenance": k[1], **dict(v)}
                               for k, v in sorted(check_counts.items())],
              "limitations": ["Report cohorts separately; development stress samples do not estimate full benchmark performance.",
                              "Non-control samples have no independent human gold; stability is not accuracy.",
                              "No automatic promotion to a calibrated official metric."]}
    args.output.mkdir(parents=True, exist_ok=True)
    atomic_write_json(args.output / "summary.json", report)
    failures = [r for r in checks if r["disagreements"]]
    md = ["# Qwen3.8 judge coverage report", "", f"Completed: {len(actual)}/{len(records)}",
          "", "These are model judgments, not independent human gold. Compare matched cohorts only.", "",
          f"Control/agent-review records requiring inspection: {len(failures)}/{len(checks)}", "",
          f"| Comparison vs {reference} | Parsed pairs | Any axis changed | Strict verdict changed |",
          "|---|---:|---:|---:|"]
    for s in stability:
        md.append(f"| {s['variant']} | {s['paired_parsed']} | {s['any_axis_changed']} | {s['strict_changed']} |")
    (args.output / "REPORT.md").write_text("\n".join(md)+"\n")
    if args.gallery:
        gallery(records, args.output, config)
    print(json.dumps({k: report[k] for k in ("expected_records", "completed_records", "status")}, indent=2))


def gallery(records, output, config=None):
    grouped = defaultdict(list)
    for r in records:
        grouped[r["sample_id"]].append(r)
    cards = []
    assets = output / "images"
    assets.mkdir(exist_ok=True)
    for sample_id, rs in grouped.items():
        sample = rs[0]["sample"]
        canvas = Image.new("RGB", (1200, 630), "white")
        draw = ImageDraw.Draw(canvas)
        pair_inputs = None
        if (config and config["variants"][rs[0]["variant"]].get("whole")
                and Path(sample["source_image"]).exists() and Path(sample["output_image"]).exists()):
            from evaluation.metrics.simple import make_views as make_pair
            pair_inputs = make_pair(sample, config["max_pixels"])
        for i, (label, key) in enumerate((("SOURCE", "source_image"), ("OUTPUT", "output_image"))):
            path = Path(sample[key])
            draw.text((i*600+10, 8), label + (" + evaluator mask contours" if pair_inputs else ""), fill="black")
            if path.exists():
                if pair_inputs:
                    thumb = ImageOps.contain(pair_inputs[i][1], (590, 590))
                else:
                    with Image.open(path) as im:
                        thumb = ImageOps.contain(im.convert("RGB"), (590, 590))
                canvas.paste(thumb, (i*600+(600-thumb.width)//2, 30+(590-thumb.height)//2))
        name = digest(sample_id)[:16]+".jpg"
        canvas.save(assets / name, quality=92)
        verdicts = [{"variant": r["variant"], "status": r["status"], "scores": r.get("scores"),
                     "passes": [{"region": p["region"], "value": p["value"]} for p in r.get("passes", [])]}
                    for r in rs]
        if pair_inputs:
            verdicts = [{"variant": r["variant"], "status": r["status"],
                         "scores": {k: r.get("scores", {}).get(k) for k in ("edit", "preservation", "quality")},
                         "assessment": next((p["value"] for p in r.get("passes", [])), None)} for r in rs]
        cards.append(f"<section><h2>{html.escape(sample_id)}</h2><p>{html.escape(sample['instruction'])}</p>"
                     f"<img loading='lazy' width='1200' src='images/{name}'><pre>"
                     +html.escape(json.dumps(verdicts, ensure_ascii=False, indent=2))+"</pre></section>")
    (output / "index.html").write_text("<!doctype html><meta charset='utf-8'><title>Judge audit</title>"
        "<style>body{font-family:sans-serif;max-width:1240px;margin:auto}img{max-width:100%}"
        "pre{white-space:pre-wrap;background:#eee;padding:1em}section{border-bottom:2px solid #aaa}</style>"
        "<h1>Qwen3.8 judge audit</h1>"+"\n".join(cards))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--gallery", action="store_true")
    make_report(p.parse_args())


if __name__ == "__main__":
    main()
