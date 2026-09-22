#!/usr/bin/env python3
"""Render one case as inputs plus five methods across all four settings."""

from __future__ import annotations

import argparse
import html
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from evaluation.metrics.protocol import digest


METHODS = ("qwen", "flux", "qwen21", "replan_qwen", "replan_flux")
METHOD_NAMES = {
    "qwen": "Qwen-2511",
    "flux": "FLUX.2",
    "qwen21": "Qwen-2.1",
    "replan_qwen": "RePlan + Qwen",
    "replan_flux": "RePlan + FLUX",
}
SETTINGS = ("text_only", "mask_annotation", "box_annotation", "point_annotation")
SETTING_NAMES = ("Text", "Mask", "Box", "Point")


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def font(size: int, bold: bool = False):
    suffix = "-Bold" if bold else ""
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/DejaVuSans{suffix}.ttf", size)


def fitted(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as image:
        return ImageOps.contain(image.convert("RGB"), size, Image.Resampling.LANCZOS)


def render_case(index: int, jobs: dict, prepared: dict, records: Path, run_id: str,
                output: Path) -> dict:
    sample = jobs[index, METHODS[0], SETTINGS[0]]
    cell_w, image_h, label_h = 310, 270, 45
    left, top = 190, 135
    row_h = image_h + label_h
    board = Image.new("RGB", (left + cell_w * 4, top + row_h * 6 + 20), "#f5f7fa")
    draw = ImageDraw.Draw(board)
    draw.text((18, 12), f"Case {index:04d} · {sample['source_dataset']} · {sample['edit_type']}",
              font=font(25, True), fill="#162231")
    title = "\n".join(textwrap.wrap(sample["instruction"], width=105))
    draw.text((18, 48), title, font=font(19), fill="#24374b", spacing=5)
    for col, name in enumerate(SETTING_NAMES):
        draw.text((left + col * cell_w + 8, top - 34), name, font=font(21, True), fill="#20344a")
    prepared_inputs = prepared[index]["prepared"]["baseline_inputs"]
    input_paths = [Path(prepared_inputs["text_only"]["images"][0])] + [
        Path(prepared_inputs[key]["images"][1]) for key in SETTINGS[1:]
    ]
    row_names = ["INPUT / locator"] + [METHOD_NAMES[m] for m in METHODS]
    for row, row_name in enumerate(row_names):
        y = top + row * row_h
        draw.text((14, y + 10), row_name, font=font(18, True), fill="#20344a")
        if row == 0:
            draw.multiline_text((14, y + 46), "Interactive modes\nactually receive\nclean source +\nthis locator.",
                                font=font(14), fill="#566a7d", spacing=4)
        for col, setting in enumerate(SETTINGS):
            x = left + col * cell_w
            if row == 0:
                path = input_paths[col]
                label = "clean source" if col == 0 else f"{SETTING_NAMES[col].lower()} locator"
                color = "#8a99a8"
            else:
                method = METHODS[row - 1]
                job = jobs[index, method, setting]
                path = Path(job["output_image"])
                key = digest({"run_id": run_id, "input": job["input_digest"], "variant": "pair_v2"})
                record = json.loads((records / f"{key}.json").read_text())
                scores = record.get("scores", {})
                label = "E/P/Q " + "/".join(str(scores.get(axis, "?")) for axis in
                                               ("edit", "preservation", "quality"))
                edit = scores.get("edit")
                color = "#2f8f59" if edit == 4 else "#d18b25" if edit in (2, 3) else "#c24747"
            thumb = fitted(path, (cell_w - 16, image_h - 12))
            px = x + (cell_w - thumb.width) // 2
            py = y + label_h + (image_h - thumb.height) // 2
            board.paste(thumb, (px, py))
            draw.rectangle((x + 4, y + label_h, x + cell_w - 5, y + row_h - 5),
                           outline=color, width=4)
            draw.text((x + 10, y + 10), label, font=font(17, True), fill=color)
    output.parent.mkdir(parents=True, exist_ok=True)
    board.save(output, quality=94, subsampling=0)
    return {"index": index, "instruction": sample["instruction"], "file": output.name}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("indices", nargs="+", type=int)
    parser.add_argument("--judge-root", type=Path, default=Path(
        "/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/metrics_qwen38_all_models_pair_v2"))
    parser.add_argument("--prepared-manifest", type=Path, default=Path(
        "/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/"
        "referential_finegrained_edit_benchmark_656_two_image_locator/prepared/"
        "benchmark_baseline_eval_inputs.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("docs/assets/setting_case_study"))
    args = parser.parse_args()
    selected = set(args.indices)
    jobs = {(r["eval_index"], r["method"], r["setting"]): r
            for r in read_jsonl(args.judge_root / "pilot.jsonl") if r["eval_index"] in selected}
    prepared = {r["eval_index"]: r for r in read_jsonl(args.prepared_manifest)
                if r["eval_index"] in selected}
    config = json.loads((args.judge_root / "all/config.rank0.json").read_text())
    expected = len(selected) * len(METHODS) * len(SETTINGS)
    if len(jobs) != expected or set(prepared) != selected:
        raise ValueError(f"Expected {expected} jobs and {len(selected)} prepared rows")
    args.output.mkdir(parents=True, exist_ok=True)
    final_names = {f"case_{index:04d}.jpg" for index in selected}
    for stale in args.output.glob("case_*.jpg"):
        if stale.name not in final_names:
            stale.unlink()
    results = [render_case(i, jobs, prepared, args.judge_root / "all/records",
                           config["run_id"], args.output / f"case_{i:04d}.jpg")
               for i in args.indices]
    page = "<!doctype html><meta charset='utf-8'><title>Setting case study</title>" \
           "<style>body{max-width:1500px;margin:24px auto;font-family:sans-serif;background:#eef2f5}" \
           "article{background:white;padding:20px;margin:20px 0}img{width:100%;height:auto}</style>"
    for item in results:
        page += f"<article><h2>Case {item['index']:04d}</h2><p>{html.escape(item['instruction'])}</p>" \
                f"<a href='{item['file']}'><img loading='lazy' src='{item['file']}'></a></article>"
    (args.output / "index.html").write_text(page, encoding="utf-8")
    summary = args.output.parent / "RESULTS.md"
    if summary.is_file():
        figures = sorted(args.output.parent.glob("*.png"))
        root_page = "<!doctype html><meta charset='utf-8'><title>Benchmark results</title>" \
                    "<style>body{max-width:1500px;margin:24px auto;font-family:sans-serif}" \
                    "img{max-width:100%;height:auto}pre{white-space:pre-wrap}</style>" \
                    "<h1>Benchmark results</h1><pre>" + html.escape(summary.read_text()) + "</pre>"
        root_page += "<h2><a href='setting_case_study/index.html'>Representative setting case study</a></h2>"
        root_page += "".join(
            f"<h2>{item.name}</h2><a href='{item.name}'><img loading='lazy' src='{item.name}'></a>"
            for item in figures
        )
        (args.output.parent / "index.html").write_text(root_page, encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
