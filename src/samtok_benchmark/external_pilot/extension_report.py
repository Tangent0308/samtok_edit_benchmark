"""Merge old/new immutable per-case records with provenance checks, never means of means."""

from collections import Counter
import json
import math
from pathlib import Path
import statistics

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .data import immutable, load_bundle, read
from .worker import source_identity
from samtok_benchmark.io import digest, sha256_file

WEIGHTS = {"BG_LPIPS": "_BG_Weight", "BG_CLIP_I": "_BG_Weight", "FG_LPIPS": "_FG_Weight"}
GIE_LABELS = {"accuracy": "编辑正确率 ↑", "rest_clip_sim": "区域外 CLIP ↑",
              "ssim_similarity_outside_mask": "区域外 SSIM ↑", "aligned_mse_diff": "官方 MSE ↓",
              "aligned_psnr": "官方 PSNR ↑"}


def current_notes(benchmark, selection, prior_notes):
    """Keep metric definitions, but derive sample-scope prose from this selection."""
    notes = []
    for note in prior_notes:
        if benchmark == "complex_edit" and note.startswith("real/syn 各"):
            sources = {x["case_id"].rsplit("-k", 1)[0] for x in selection["selected"]}
            counts = Counter(x.split("-", 1)[0] for x in sources)
            notes.append(f"real {counts['real']} 张、syn {counts['syn']} 张原图，在 K=1/2/4/8 的原始复合指令上评测；共 {selection['total']} 条请求、{len(sources)} 张独立源图。")
        elif benchmark == "gedit" and note.startswith("英文 11 类各"):
            counts = Counter(x["task_type"] for x in selection["selected"])
            if len(set(counts.values())) != 1:
                raise ValueError("GEdit expansion is no longer category-balanced")
            notes.append(f"英文 {len(counts)} 类各 {next(iter(counts.values()))} 条，使用 input_image_raw 与原始公开指令。")
        elif not any(t in note for t in ("共 8", "共8", "四个完整", "各 2 条", "各抽 1", "八条")):
            notes.append(note)
    return notes


def aggregate(cases, labels, weights):
    result = {}
    for metric in labels:
        weight = weights.get(metric)
        pairs = [(x["metrics"].get(metric), x["metrics"].get(weight) if weight else 1) for x in cases]
        valid = [(v, w) for v, w in pairs if isinstance(v, (float, int)) and math.isfinite(v)
                 and isinstance(w, (float, int)) and math.isfinite(w) and w >= 0]
        denominator = sum(w for _, w in valid)
        result[metric] = {"mean": sum(v*w for v, w in valid)/denominator if denominator else None,
                          "count": len(valid), "total": len(cases), "complete": len(valid) == len(cases),
                          "weight": weight}
    return result


def report(benchmark, root, previews, old_config, new_config, doc=None):
    if benchmark == "gie":
        from samtok_benchmark.external_gie.score import bindings
    else:
        from .scoring import bindings
    root, previews = Path(root), Path(previews)
    selection = read(root / "SELECTION.json")
    prior = Path(selection["previous_root"])
    origins = [prior, root / "additional"]
    old_report = read(prior / "report/REPORT.json")
    labels = GIE_LABELS if benchmark == "gie" else old_report["metric_labels"]
    configs = [read(old_config), read(new_config)]
    stripped = [{k: v for k, v in config.items() if k != "formal_results_root"} for config in configs]
    if stripped[0] != stripped[1]:
        raise ValueError("The expansion changed the scientific configuration")
    code = source_identity()
    all_cases, datasets, api = {}, [], {"responses": 0, "choices": 0, "new_responses": 0,
                                        "new_choices": 0, "errors": 0, "unknown_admissions": 0}
    for origin, config in zip(origins, configs):
        index = load_bundle(origin / "bundle")
        expected = {x["case_id"]: x for x in index["cases"]}
        rows = read(origin / "bundle/private/evaluation.json")
        verified = {(x["model"], x["row"]["case_id"]): x for x in bindings(origin / "bundle", origin / "run")}
        evaluation_sha = sha256_file(origin / "bundle/private/evaluation.json")
        datasets.append({"root": str(origin), "bundle_digest": index["digest"], "evaluation_sha256": evaluation_sha})
        for row in rows:
            cid = row["case_id"]
            if cid in all_cases:
                raise ValueError("Original and additional requests overlap")
            all_cases[cid] = {"row": row, "public": read(expected[cid]["public"]), "models": {}}
            for model in ("sitedit", "qwen21"):
                path = origin / "run" / model / "edit" / cid / "result.json"
                r = read(path) if path.exists() else {"status": "missing"}
                metrics, score_provenance = {}, {}
                if path.exists():
                    identity = r["identity"]
                    if read(path.with_name("ADMITTED.json"))["identity"] != identity:
                        raise ValueError("Admission/result identity mismatch")
                    if (identity["config_digest"] != digest(config) or identity["source_code"] != code
                            or identity["public_sha256"] != expected[cid]["public_sha256"]
                            or identity["bundle_digest"] != index["digest"]):
                        raise ValueError(f"Changed scientific generation identity: {model}/{cid}")
                    if r["status"] == "completed" and (model, cid) not in verified:
                        raise ValueError("Unverified successful result")
                for score_name in ("local.json", "judge/score.json"):
                    score_path = origin / "scores" / model / cid / score_name
                    if not score_path.exists():
                        continue
                    score = read(score_path)
                    identities = score.get("identities", [score.get("identity")])
                    for identity in identities:
                        if not identity or any(identity[k] != v for k, v in verified[model, cid]["binding"].items()):
                            raise ValueError(f"Score is not bound to its actual output: {score_path}")
                    metrics.update(score.get("metrics", {}))
                    if benchmark == "gie" and score_name == "judge/score.json":
                        metrics["accuracy"] = int(score["correct"])
                    score_provenance[score_name] = {"path": str(score_path), "sha256": sha256_file(score_path)}
                all_cases[cid]["models"][model] = {
                    "case_id": cid, "category": row.get("canonical_category", row.get("category", row.get("task", ""))),
                    "origin": "previous" if origin == prior else "additional", "generation": r["status"],
                    "metrics": metrics, "result_path": str(path),
                    "result_sha256": sha256_file(path) if path.exists() else None,
                    "output_image": r.get("output_image"), "output_sha256": r.get("output_sha256"),
                    "edit_seconds": r.get("inference_seconds"), "error": r.get("error"),
                    "score_provenance": score_provenance}
        for path in (origin / "scores").glob("**/admitted.json"):
            response_path = path.with_name("response.json")
            if response_path.exists():
                response = read(response_path)
                n = len(response["choices"])
                api["responses"] += 1
                api["choices"] += n
                if origin != prior:
                    api["new_responses"] += 1
                    api["new_choices"] += n
            else:
                api["unknown_admissions"] += 1
            api["errors"] += path.with_name("error.json").exists()
    ids = [x["case_id"] for x in selection["selected"]]
    if set(ids) != set(all_cases) or len(ids) != selection["total"]:
        raise ValueError("The report does not cover the frozen combined selection")
    weights = WEIGHTS if benchmark == "omni_iie" else {}
    models = {}
    for model in ("sitedit", "qwen21"):
        values = [all_cases[cid]["models"][model] for cid in ids]
        groups = sorted({v["category"] for v in values})
        times = [v["edit_seconds"] for v in values if v["edit_seconds"] is not None]
        models[model] = {"n": len(values), "generated": sum(v["generation"] == "completed" for v in values),
                         "metrics": aggregate(values, labels, weights),
                         "groups": {g: aggregate([v for v in values if v["category"] == g], labels, weights) for g in groups},
                         "per_case": values, "mean_edit_seconds": statistics.mean(times) if times else None,
                         "previous_outputs": sum(v["origin"] == "previous" for v in values),
                         "additional_outputs": sum(v["origin"] == "additional" for v in values)}
    notes = current_notes(benchmark, selection, old_report.get("notes", []))
    if benchmark == "gie":
        notes.append(old_report["warning"])
    payload = {"benchmark": old_report["benchmark"], "scope": "fixed stratified expanded pilot; not a full-benchmark result",
               "selection_sha256": sha256_file(root / "SELECTION.json"), "origins": datasets,
               "metric_labels": labels, "notes": notes, "models": models, "api_usage": api,
               "comparison": "Same frozen scientific configuration; old per-case results reused without mutation or rerun"}
    immutable(root / "report/REPORT.json", payload)
    lines = [f"# {old_report['benchmark']} 扩展小样本结果", "",
             f"固定 {len(ids)} 条请求：保留上轮 {len(selection['previous_ids'])} 条，新增 {selection['additional']} 条。SITEdit 与 Qwen-Image-2.1 使用相同清单；旧结果逐条核验后复用，未重新生成或评分。", "",
             "方法、权重、输入映射、原生评分和 GPT-5.4 配置与前轮一致。抽样 seed 20261107，生成 seed 42。本结果是分层小样本观察，不作为全量排名或显著性结论。", "",
             "| 指标 | SITEdit | Qwen-Image-2.1 | 有效数（SITEdit / Base） |", "|---|---:|---:|---|"]
    for key, label in labels.items():
        a, b = (models[m]["metrics"][key] for m in ("sitedit", "qwen21"))
        def fmt(x):
            return f"{x['mean']:.4f}" if x["mean"] is not None else "N/A"
        lines.append(f"| {label} | {fmt(a)} | {fmt(b)} | {a['count']}/{a['total']}；{b['count']}/{b['total']} |")
    lines += ["", "生成完成仅表示正常出图。失败、缺分和受理未作答保留；没有填零，没有按分数筛选样例。", "",
              *["- "+x for x in notes], "", f"- 全部逐例记录及来源：`{root / 'report/REPORT.json'}`。",
              f"- 新增 API 响应：{api['new_responses']}；旧新合计响应：{api['responses']}；未作答受理：{api['unknown_admissions']}。", ""]
    if doc:
        Path(doc).write_text("\n".join(lines).rstrip() + "\n")
    previews.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    lines += ["## 全部请求对照", ""]
    for cid in ids:
        item = all_cases[cid]
        public = item["public"]
        panels = [("Public source", public["source"]["path"])]
        if public.get("mask"):
            panels.append(("Public mask", public["mask"]["path"]))
        panels += [(name, item["models"][m]["output_image"]) for m, name in
                   (("sitedit", "SITEdit"), ("qwen21", "Qwen-Image-2.1"))]
        sheet = Image.new("RGB", (420*len(panels), 490), "white")
        draw = ImageDraw.Draw(sheet)
        for i, (label, path) in enumerate(panels):
            draw.text((i*420+10, 10), label, font=font, fill="black")
            if path:
                with Image.open(path) as source:
                    im = ImageOps.contain(source.convert("RGB"), (400, 440))
                sheet.paste(im, (i*420+10+(400-im.width)//2, 40+(440-im.height)//2))
            else:
                draw.text((i*420+20, 200), "No output", font=font, fill="red")
        image_path = previews / (cid + ".png")
        sheet.save(image_path)
        lines += [f"### {cid}", "", public["instruction"], "", f"![{cid} 输入输出]({image_path})", ""]
    md = "\n".join(lines) + "\n"
    (previews / "REPORT.md").write_text(md)
    (root / "report/REPORT.md").write_text(md)
    print(json.dumps({"benchmark": benchmark, "requests": len(ids), "generations":
                      {m: Counter(x["generation"] for x in r["per_case"]) for m, r in models.items()},
                      "api": api}, ensure_ascii=False))
    return payload
