"""Reproducible small-pilot summaries and all-case input/output contact sheets."""

import json
import math
from pathlib import Path
import statistics

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .data import load_bundle, immutable, read
from .scoring import bindings
from samtok_benchmark.io import sha256_file


def report(root, previews, title, metric_labels, notes, doc=None, weights=None):
    root, previews = Path(root), Path(previews)
    index = load_bundle(root / "bundle")
    rows = read(root / "bundle/private/evaluation.json")
    expected = {x["case_id"]: x for x in index["cases"]}
    verified = {(x["model"], x["row"]["case_id"]) for x in bindings(root / "bundle", root / "run")}
    models = {}
    for model in ("sitedit", "qwen21"):
        cases = []
        for row in rows:
            cid = row["case_id"]
            result_path = root / "run" / model / "edit" / cid / "result.json"
            result = read(result_path) if result_path.exists() else {"status": "missing"}
            if result["status"] == "completed" and (model, cid) not in verified:
                raise ValueError("Unverified output cannot enter the report")
            metrics, receipts = {}, {}
            for name in ("local.json", "judge/score.json"):
                path = root / "scores" / model / cid / name
                if path.exists():
                    score = read(path)
                    metrics.update(score["metrics"])
                    receipts[name] = sha256_file(path)
            cases.append({"case_id": cid, "category": row.get("category", row.get("task", "")),
                          "generation": result["status"], "error": result.get("error"), "metrics": metrics,
                          "score_receipts_sha256": receipts, "edit_seconds": result.get("inference_seconds"),
                          "peak_allocated_gib": result.get("peak_gpu_allocated_bytes", 0)/1024**3})
        def aggregate(selected):
            values = {}
            for key in metric_labels:
                weight_key = (weights or {}).get(key)
                pairs = [(r["metrics"].get(key), r["metrics"].get(weight_key) if weight_key else 1) for r in selected]
                valid = [(x, w) for x, w in pairs if isinstance(x, (int, float)) and math.isfinite(x)
                         and isinstance(w, (int, float)) and math.isfinite(w) and w >= 0]
                denominator = sum(w for _, w in valid)
                mean = sum(x*w for x, w in valid)/denominator if denominator else None
                values[key] = {"mean": mean, "count": len(valid), "total": len(selected),
                               "complete": len(valid) == len(selected), "weight": weight_key}
            return values
        metrics = aggregate(cases)
        times = [r["edit_seconds"] for r in cases if r["edit_seconds"] is not None]
        stages = {}
        for stage in ("tokens", "edit"):
            records = [read(p) for p in (root/"run"/model/stage).glob("*/result.json")]
            if records:
                stages[stage] = {"completed": sum(r["status"] == "completed" for r in records),
                    "measured_inference_seconds": sum(r.get("inference_seconds", 0) for r in records),
                    "measured_load_seconds": sum(r.get("load_seconds") or 0 for r in records),
                    "fallback_units": sum(r.get("native", {}).get("fallback_units", 0) for r in records)}
        models[model] = {"n": len(cases), "generated": sum(r["generation"] == "completed" for r in cases),
                         "groups": {k: aggregate([r for r in cases if r["category"] == k]) for k in ("low", "high")},
                         "metrics": metrics, "per_case": cases, "stages": stages,
                         "mean_edit_seconds": statistics.mean(times) if times else None,
                         "peak_allocated_gib": max(r["peak_allocated_gib"] for r in cases)}
    api = [read(p) for p in (root/"scores").glob("**/response.json")]
    usage = {"responses": len(api), **{k: sum((r.get("usage") or {}).get(k, 0) for r in api)
                                      for k in ("prompt_tokens", "completion_tokens", "total_tokens")}}
    payload = {"benchmark": title, "scope": "fixed stratified small pilot, not full benchmark",
               "bundle_digest": index["digest"], "metric_labels": metric_labels, "notes": notes,
               "models": models, "api_usage": usage}
    immutable(root / "report/REPORT.json", payload)
    lines = [f"# {title} 小子集结果", "", f"固定 {len(rows)} 条请求，两方法使用相同输入，每条 seed 42，仅生成一次。本页用于快速验证，不代表全量 benchmark 的排名。", ""]
    lines += ["| 方法 | 成功出图 | " + " | ".join(metric_labels.values()) + " |",
              "|---|---:|" + "---:|"*len(metric_labels)]
    for model, name in (("sitedit", "SITEdit"), ("qwen21", "Qwen-Image-2.1")):
        r = models[model]
        cells = []
        for key in metric_labels:
            v = r["metrics"][key]
            cells.append((f"{v['mean']:.4f}" + (f"（{v['count']}/{v['total']}）" if not v["complete"] else "")) if v["mean"] is not None else "N/A")
        lines.append(f"| {name} | {r['generated']}/{r['n']} | " + " | ".join(cells) + " |")
    lines += ["", "| 方法 / 尺度 | " + " | ".join(metric_labels.values()) + " |",
              "|---|" + "---:|"*len(metric_labels)]
    for model in models:
        for group, metrics in models[model]["groups"].items():
            cells = [f"{metrics[k]['mean']:.4f}" if metrics[k]["mean"] is not None else "N/A" for k in metric_labels]
            lines.append(f"| {model} / {group} | " + " | ".join(cells) + " |")
    lines += ["", *[f"- {x}" for x in notes], "", "评分缺失不填零；若某项未覆盖全部请求，上表会标有效数/总数。生成成功只表示正常出图，不表示正确完成指令。", "",
              "| 方法 | 平均编辑调用（秒） | 峰值 allocated（GiB） |", "|---|---:|---:|"]
    for model in models:
        r = models[model]
        seconds = f"{r['mean_edit_seconds']:.2f}" if r["mean_edit_seconds"] is not None else "N/A"
        lines.append(f"| {model} | {seconds} | {r['peak_allocated_gib']:.2f} |")
    lines += ["", "编辑用时不含加载；SITEdit 的额外定位/codec 阶段与实际 API 用量在 REPORT.json 中逐项保留。", "",
              f"- 原始结果、输入、评分与报告：`{root}`。", f"- 全部输入输出对比图：`{previews}`。", ""]
    if doc:
        Path(doc).write_text("\n".join(lines) + "\n")
    previews.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    lines += ["## 全部请求对比", ""]
    for row in rows:
        cid = row["case_id"]
        public = read(expected[cid]["public"])
        panels = [("Source (public canvas)", public["source"]["path"])]
        if public.get("mask"):
            panels.append(("Public mask", public["mask"]["path"]))
        for model, label in (("sitedit", "SITEdit"), ("qwen21", "Qwen-Image-2.1")):
            p = root / "run" / model / "edit" / cid / "output.png"
            panels.append((label, p if p.exists() else None))
        canvas = Image.new("RGB", (420*len(panels), 490), "white")
        draw = ImageDraw.Draw(canvas)
        for i, (label, path) in enumerate(panels):
            draw.text((i*420+10, 10), label, font=font, fill="black")
            if path:
                im = ImageOps.contain(Image.open(path).convert("RGB"), (400, 440))
                canvas.paste(im, (i*420+10+(400-im.width)//2, 40+(440-im.height)//2))
            else:
                draw.text((i*420+20, 200), "No output", font=font, fill="red")
        destination = previews / (cid + ".png")
        canvas.save(destination)
        lines += [f"### {cid}", "", row.get("instruction", ""), "",
                  f"![{cid} 输入和输出]({destination})", ""]
    md = "\n".join(lines) + "\n"
    (root / "report/REPORT.md").write_text(md)
    (previews / "REPORT.md").write_text(md)
    print(json.dumps({m: {k: v for k, v in r.items() if k != "per_case"} for m, r in models.items()}, indent=2))
