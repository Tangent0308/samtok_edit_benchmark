#!/usr/bin/env python3
"""Measured smoke cost/coverage and real input/output contact sheets; never infer missing timings."""

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import sys
import textwrap

from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main(bundle, run, selection, output):
    from samtok_benchmark.external_compbench.full import MODELS
    from samtok_benchmark.external_compbench.full.launch import select_cases
    from samtok_benchmark.external_compbench.full.worker import stages
    from samtok_benchmark.external_refedit.data import read

    run, output = Path(run), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    cases = select_cases(read(Path(bundle) / "index.json"), read(selection)["case_ids"])
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font = ImageFont.truetype(font_path, 16) if Path(font_path).exists() else ImageFont.load_default()
    rows = []
    for model in MODELS:
        receipts, edits = [], []
        per_request = []
        for item in cases:
            current = []
            for stage in stages(model):
                path = run / model / stage / item["case_id"] / "result.json"
                if path.exists():
                    receipt = read(path)
                    current.append(receipt)
                    receipts.append(receipt)
                    if stage == "edit":
                        edits.append(receipt)
            if len(current) == len(stages(model)) and all(x["status"] == "completed" for x in current):
                per_request.append(sum(x["inference_seconds"] for x in current))
        measured = statistics.fmean(per_request) if per_request else None
        rows.append({"model": model, "expected": len(cases), "status_counts": dict(Counter(x["status"] for x in edits)),
                     "completed_timed_requests": len(per_request), "mean_total_inference_seconds": measured,
                     "measured_load_seconds": sum(x.get("load_seconds", 0) for x in receipts),
                     "peak_allocated_gib": max((x.get("peak_gpu_allocated_bytes", 0) for x in receipts), default=0) / 2**30,
                     "peak_reserved_gib": max((x.get("peak_gpu_reserved_bytes", 0) for x in receipts), default=0) / 2**30,
                     "extrapolated_3481_gpu_hours": measured * 3481 / 3600 if measured is not None else None})
    lines = ["# CompBench 全量入口冒烟", "", "固定三条 / 方法；本页验证可运行性，不作 benchmark 排名。", "",
             "GPU 小时为本轮实测完整请求耗时 × 3,481 的估算，不包含模型加载、排队、NAS 等待和评分。", "",
             "| 方法 | 成功 / 应测 | 秒 / 请求 | 峰值 allocated GiB | 峰值 reserved GiB | 预计全量 GPU 小时 |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in rows:
        seconds = row["mean_total_inference_seconds"]
        gpu_hours = row["extrapolated_3481_gpu_hours"]
        timing = f"{seconds:.1f}" if seconds is not None else "N/A"
        hours = f"{gpu_hours:.1f}" if gpu_hours is not None else "N/A"
        lines.append(f"| {row['model']} | {row['status_counts'].get('completed', 0)} / {row['expected']} | {timing} | "
                     f"{row['peak_allocated_gib']:.2f} | {row['peak_reserved_gib']:.2f} | {hours} |")
    lines += ["", "每个模型卡片左侧为其实际输入，右侧为实际输出；连续第二轮的输入因方法而异。"]
    for item in cases:
        tile_w, tile_h = 516, 310
        canvas = Image.new("RGB", (tile_w * 2, tile_h * 4 + 110), "white")
        draw = ImageDraw.Draw(canvas)
        draw.text((12, 8), item["case_id"], font=font, fill="black")
        draw.multiline_text((12, 34), "\n".join(textwrap.wrap(item["instruction"], 112)), font=font, fill="black")
        for i, model in enumerate(MODELS):
            x, y = (i % 2) * tile_w, 110 + (i // 2) * tile_h
            draw.text((x + 8, y + 3), f"{model}  |  actual input / output", font=font, fill="black")
            public_path = (run / model / "inputs" / item["case_id"] / "public.json") if item["turn"] == 2 else Path(item["public"])
            result_path = run / model / "edit" / item["case_id"] / "result.json"
            result = read(result_path) if result_path.exists() else {}
            paths = [read(public_path)["source"]["path"] if public_path.exists() else None,
                     result.get("output_image")]
            for column, path in enumerate(paths):
                if path:
                    with Image.open(path) as image:
                        thumb = ImageOps.contain(image.convert("RGB"), (250, 250))
                    canvas.paste(thumb, (x + 4 + column * 258, y + 32))
                else:
                    draw.text((x + 8 + column * 258, y + 100), result.get("status", "pending"), font=font, fill="gray")
        filename = item["case_id"] + ".png"
        canvas.save(output / filename)
        lines += ["", f"## {item['case_id']}", "", item["instruction"], "", f"![实际输入输出]({filename})"]
    (output / "SMOKE.json").write_text(json.dumps({"rows": rows, "selection": read(selection)}, indent=2) + "\n")
    (output / "SMOKE.md").write_text("\n".join(lines) + "\n")
    print(output / "SMOKE.md")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("bundle", "run", "selection", "output"):
        p.add_argument("--" + name, required=True)
    main(**vars(p.parse_args()))
