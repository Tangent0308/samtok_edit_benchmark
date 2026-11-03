#!/usr/bin/env python3
"""Recompute MIRA component differences and render fixed, provenance-checked examples on CPU.

This post-hoc tool never imports a model, calls a Judge, or changes a formal run.
The reviewed case list is an explicit input, not a new score-based selection.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_mira_audited import FIELDS, MODELS, load_scores, read, sha

NAMES = {"qwen2511": "Qwen-Image-Edit-2511", "qwen21": "Qwen-Image-2.1",
         "replan": "RePlan", "mirage": "MIRAGE", "sitedit": "SITEdit"}


def checked_file(path, expected=None):
    path = Path(path)
    actual = sha(path)
    if expected is not None and actual != expected:
        raise ValueError(f"Evidence hash mismatch: {path}")
    return {"path": str(path.resolve()), "sha256": actual}


def components(values, cases, replicates=10000, seed=20261103):
    """Paired differences on the complete selected set; no silent intersection or imputation."""
    keys = sorted(cases)
    if not keys or len(set(keys)) != len(keys) or replicates < 1:
        raise ValueError("Unique nonempty source IDs and positive replicates are required")
    arrays = {}
    for model in ("sitedit", "qwen21"):
        if not set(keys) <= set(values[model]):
            raise ValueError(f"Missing selected sources for {model}")
        a = np.asarray([values[model][key] for key in keys], dtype=float)
        if a.shape != (len(keys), 3) or not np.isfinite(a).all() or not ((0 <= a) & (a <= 10)).all():
            raise ValueError("Expected finite PF/Cons/PQ scores in [0, 10]")
        arrays[model] = a
    draws = np.random.default_rng(seed).integers(0, len(keys), size=(replicates, len(keys)))
    result = {}
    for index, field in enumerate(FIELDS):
        ours, baseline = (arrays[model][:, index] for model in ("sitedit", "qwen21"))
        delta = ours - baseline
        result[field] = {
            "sitedit_mean": float(ours.mean()), "qwen21_mean": float(baseline.mean()),
            "paired_mean_difference": float(delta.mean()),
            "difference_ci95": np.quantile(delta[draws].mean(axis=1), [.025, .975]).tolist(),
            "sitedit_lower_count": int((delta < -1e-8).sum()),
            "tie_count": int((np.abs(delta) <= 1e-8).sum()),
            "sitedit_higher_count": int((delta > 1e-8).sum()),
            "median_difference": float(np.median(delta)),
        }
    return {"source_ids": keys, "n": len(keys), "metrics": result,
            "bootstrap": {"unit": "source image, paired", "replicates": replicates, "seed": seed,
                          "interval": "percentile 95%", "scope": "Existing single generation and Judge score; does not include repeated-generation or repeated-Judge variance."}}


def polygon_mask(polygons, size):
    if not isinstance(polygons, list) or not polygons:
        raise ValueError("Missing polygons")
    parts = [polygons] if isinstance(polygons[0], (int, float)) else polygons
    image = Image.new("L", tuple(size))
    draw = ImageDraw.Draw(image)
    for polygon in parts:
        points = np.asarray(polygon, dtype=float)
        if points.ndim != 1 or len(points) < 6 or len(points) % 2 or not np.isfinite(points).all():
            raise ValueError("Invalid polygon coordinates")
        draw.polygon(points.tolist(), fill=255)
    return image


def region_iou(mask, polygons, geometry):
    if list(mask.size) != geometry["canvas_size"]:
        raise ValueError("Cached mask differs from its recorded canvas")
    x1, y1, x2, y2 = geometry["content_box"]
    if not (0 <= x1 < x2 <= mask.width and 0 <= y1 < y2 <= mask.height):
        raise ValueError("Invalid content crop")
    restored = mask.convert("L").crop((x1, y1, x2, y2)).resize(
        tuple(geometry["source_size"]), Image.Resampling.NEAREST)
    predicted = np.asarray(restored) > 0
    target = np.asarray(polygon_mask(polygons, geometry["source_size"])) > 0
    union = int((predicted | target).sum())
    if not target.any() or not union:
        raise ValueError("Empty diagnostic target")
    return float((predicted & target).sum() / union)


def bound_token(tokens, call, unit_id):
    units = tokens["native"]["units"]
    if len({u["id"] for u in units}) != len(units):
        raise ValueError("Duplicate token unit IDs")
    selected = [u for u in units if u["id"] == unit_id]
    lines = [line for line in call["prompt"].splitlines() if line.startswith(unit_id + ":")]
    if len(selected) != 1 or len(lines) != 1:
        raise ValueError("Missing or duplicate instruction binding")
    token = selected[0]["token"]
    if not token or lines[0].count(token) != 1:
        raise ValueError("Saved token is not bound to the corresponding instruction")
    return lines[0]


def fresh_destination(path, formal_root):
    path, formal_root = Path(path).resolve(), Path(formal_root).resolve()
    if path.is_relative_to(formal_root) or formal_root.is_relative_to(path):
        raise ValueError("Diagnostic output must stay outside the formal run")
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError(f"Preserve existing artifacts; use a new directory: {path}")
    return path


def wrap(text, font, width):
    lines, current = [], ""
    for word in text.split():
        candidate = (current + " " + word).strip()
        if current and font.getlength(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    return lines + ([current] if current else [])


def draw_sheet(path, title, instruction, images, labels, font_path, footer):
    font = ImageFont.truetype(str(font_path), 22)
    heading = ImageFont.truetype(str(font_path), 30)
    width = max(1920, 500 * len(images))
    cell_width = width // len(images)
    lines = wrap(instruction, font, width - 40)
    top = 70 + 28 * len(lines)
    image_top, image_height = top + 82, 400
    notes = wrap(footer, font, width - 40)
    sheet = Image.new("RGB", (width, image_top + image_height + 30 + 28 * len(notes)), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((20, 12), title, font=heading, fill="black")
    for i, line in enumerate(lines):
        draw.text((20, 58 + i * 28), line, font=font, fill="black")
    for i, (image, label) in enumerate(zip(images, labels, strict=True)):
        x = i * cell_width + 12
        for j, line in enumerate(label.splitlines()):
            draw.text((x, top + j * 28), line, font=font, fill="black")
        thumbnail = ImageOps.contain(image.convert("RGB"), (cell_width - 24, image_height),
                                     Image.Resampling.LANCZOS)
        sheet.paste(thumbnail, (x + (cell_width - 24 - thumbnail.width) // 2,
                               image_top + (image_height - thumbnail.height) // 2))
    for i, line in enumerate(notes):
        draw.text((20, image_top + image_height + 12 + i * 28), line, font=font, fill="black")
    with Path(path).open("xb") as stream:
        sheet.save(stream, format="JPEG", quality=94)


def collect_case(root, canonical, public_item, case, values):
    cid = case["case_id"]
    source = Path(canonical["source"]["path"])
    files = [checked_file(source, canonical["source"]["sha256"])]
    paths = {"source": str(source)}
    scores = {}
    for model in MODELS:
        directory = root / "scores_gpt54_001" / model
        job_path = directory / "JOB.json"
        job = read(job_path)
        binding = next(b for b in job["bindings"] if Path(b["image"]).stem == cid)
        result_path = root / "run_001" / model / "edit" / cid / "result.json"
        files += [checked_file(job_path), checked_file(result_path, binding["result_sha256"])]
        result = read(result_path)
        if (result["status"] != "completed" or result["identity"]["case_id"] != cid
                or result["identity"]["public_sha256"] != public_item["public_sha256"]
                or binding["source_sha256"] != canonical["source"]["sha256"]):
            raise ValueError(f"Image does not belong to the scored request: {model}/{cid}")
        output = Path(result["output_image"])
        files.append(checked_file(output, binding["output_sha256"]))
        if result["output_sha256"] != binding["output_sha256"]:
            raise ValueError("Generation/Judge image mismatch")
        paths[model] = str(output)
        scores[model] = dict(zip(FIELDS, values[model][cid]))
    return {**case, "instruction": canonical["editing_instruction"], "image_paths": paths,
            "scores": scores, "evidence": files}


def collect_region(root, bundle, canonical, item, spec):
    cid, uid = spec["case_id"], spec["unit_id"]
    tokens_path = root / "run_001/sitedit/tokens" / cid / "result.json"
    result_path = root / "run_001/sitedit/edit" / cid / "result.json"
    result = read(result_path)
    evidence = [checked_file(tokens_path, result["identity"]["previous_sha256"])]
    call_path = result_path.with_name("call.json")
    call, tokens = read(call_path), read(tokens_path)
    line = bound_token(tokens, call, uid)
    public_path = Path(item["public"])
    public = read(public_path)
    if call["images"] != [public["source"]] or tokens["identity"]["public_sha256"] != item["public_sha256"]:
        raise ValueError("Region diagnostic differs from the public model input")
    source = Path(public["source"]["path"])
    mask_path = tokens_path.with_name(f"{uid}.png")
    evidence += [checked_file(call_path), checked_file(public_path, item["public_sha256"]),
                 checked_file(source, public["source"]["sha256"]), checked_file(mask_path),
                 checked_file(bundle / "private/evaluation.json")]
    with Image.open(mask_path) as mask:
        iou = region_iou(mask, canonical["mask"][int(uid[1:]) - 1], item["geometry"])
    return {**spec, "iou": iou, "actual_instruction_line": line, "saved_token_binding_verified": True,
            "instruction": public["units"][int(uid[1:]) - 1]["instruction"],
            "source_path": str(source), "mask_path": str(mask_path),
            "output_path": result["output_image"], "geometry": item["geometry"], "evidence": evidence,
            "policy": "PIL polygon union; crop cached mask to recorded content_box, then NEAREST resize to canonical source_size. Offline diagnostic only; decoded masks and GT are not editor inputs."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New temporary metadata directory")
    parser.add_argument("--preview-dir", type=Path, required=True, help="New user-facing visualization directory")
    parser.add_argument("--cases", type=Path, default=Path(__file__).resolve().parents[1] /
                        "configs/analysis/mira_cases_20261103.json")
    parser.add_argument("--font", type=Path, default=Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    args = parser.parse_args()
    root, bundle = args.root.resolve(), args.bundle.resolve()
    output = fresh_destination(args.output, root)
    preview = fresh_destination(args.preview_dir, root)
    if output.is_relative_to(preview) or preview.is_relative_to(output):
        raise ValueError("Use separate metadata and preview directories")
    if read(root / "STATUS.json")["status"] not in ("complete", "finished_with_missing"):
        raise ValueError("Wait for the full run to finish")
    sets_path = root / "overlap_audit/SOURCE_SUBSETS.json"
    audit = read(root / "overlap_audit/REPORT.json")
    if audit["status"] != "complete":
        raise ValueError("Overlap adjudication is not complete")
    checked_file(sets_path, audit["source_subsets_sha256"])
    sets, run, index = read(sets_path), read(root / "run_001/RUN.json"), read(bundle / "index.json")
    if (sets["bundle_digest"] != run["bundle_digest"] or index["digest"] != run["bundle_digest"]
            or sorted(run["case_ids"]) != sets["official_200"]):
        raise ValueError("Source subset or bundle belongs to a different run")
    values, coverage, evidence = load_scores(root, sets["official_200"])
    fixed = read(args.cases)
    cases = fixed["cases"]
    ids = [case["case_id"] for case in cases]
    selected = sets["without_confirmed_overlap_198"]
    if len(set(ids)) != len(ids) or not set(ids) <= set(selected):
        raise ValueError("Case selection contains duplicates or excluded source IDs")
    canonical_path = bundle / "private/evaluation.json"
    for model in MODELS:
        checked_file(canonical_path, read(root / "scores_gpt54_001" / model / "JOB.json")["canonical_sha256"])
        if not set(ids) <= set(values[model]):
            raise ValueError(f"Cannot show missing outputs as scored images: {model}")
    canonical = {c["case_id"]: c for c in read(canonical_path)}
    items = {c["case_id"]: c for c in index["cases"]}
    gallery = [collect_case(root, canonical[c["case_id"]], items[c["case_id"]], c, values) for c in cases]
    regions = [collect_region(root, bundle, canonical[c["case_id"]], items[c["case_id"]], c)
               for c in fixed["region_checks"]]
    report = {"schema": "mira.posthoc.analysis.v1", "script": checked_file(__file__),
              "selection": checked_file(args.cases), "source_subsets": checked_file(sets_path),
              "score_evidence": evidence, "coverage": coverage,
              "components": components(values, selected), "cases": gallery, "region_checks": regions,
              "limits": "Purposive reviewed examples, not failure-frequency estimates. Existing scores only; no generation, Judge calls or formal-result modifications. Region checks do not establish a particular training or attention mechanism."}
    output.mkdir(parents=True, exist_ok=True)
    preview.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for case in gallery:
        images = [Image.open(case["image_paths"][m]).convert("RGB") for m in ("source", *MODELS)]
        labels = ["Source"] + [NAMES[m] + "\nPF %.2f | Cons %.2f | PQ %.2f" %
                                tuple(case["scores"][m][k] for k in FIELDS) for m in MODELS]
        path = preview / f"case_{case['case_id']}_all_models.jpg"
        draw_sheet(path, f"MIRA case {case['case_id']} | Original + five methods", case["instruction"],
                   images, labels, args.font, "Existing GPT-5.4 scores, 0-10. Purposive diagnostic example; not an all-edit success claim or failure-rate estimate.")
        artifacts.append(checked_file(path))
    for region in regions:
        source = Image.open(region["source_path"]).convert("RGB")
        mask = np.asarray(Image.open(region["mask_path"]).convert("L")) > 0
        pixels = np.asarray(source).astype(float)
        pixels[mask] = pixels[mask] * .55 + np.array([255, 30, 30]) * .45
        overlay = Image.fromarray(pixels.clip(0, 255).astype("uint8"))
        path = preview / f"{region['case_id']}_{region['unit_id']}_cached_region.jpg"
        draw_sheet(path, f"Case {region['case_id']} / {region['unit_id']} | Cached region check, IoU {region['iou']:.4f}",
                   region["instruction"], [source, overlay, Image.open(region["output_path"])],
                   ["Public source", "Decoded region code (red)", "SITEdit output"], args.font,
                   "Saved token bound to its corresponding instruction. Decoded mask and GT are offline diagnostics, not editor inputs.")
        artifacts.append(checked_file(path))
    report["artifacts"] = artifacts
    with (output / "REPORT.json").open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"Verified {len(gallery)} cases and {len(regions)} cached regions: {output / 'REPORT.json'}")


if __name__ == "__main__":
    main()
