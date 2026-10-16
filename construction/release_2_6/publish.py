"""Export a built 2.6.0 release's mask patch and before/after audit artifacts.

Run from the repository root after build.py. This does not generate edited images.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from samtok_benchmark.io import read_jsonl, sha256_file, write_json, write_jsonl  # noqa: E402

EXAMPLES = [
    ("v2-sa_3397098", "U1", "裤腿剪短：整条裤子 → 膝下区段"),
    ("v2-sa_5794853", "U1", "新增贴花：整车 → 侧窗下方实心侧板"),
    ("v2-sa_6720037", "U1", "移除车辆：保留前景细栅栏、门柱和门闩"),
    ("v2-sa_1254142", "U4", "排除斜包带，并明确长袖高领结构替换"),
    ("v2-sa_8917525", "U1", "改选目标：穿着足袋 → 独立松放白布"),
    ("v2-sa_5953627", "U3", "结构替换：浅圆容器 → 低直边长方木托盘"),
    ("v2-sa_9357354", "U1", "修复人物与衣物层级"),
    ("v2-sa_2176556", "U1", "车厢替换：排除悬挂架，明确双层结构"),
]


def load_mask(path):
    with Image.open(path) as im:
        return np.asarray(im.convert("L")) > 127


def box(mask):
    yy, xx = np.where(mask)
    return [int(xx.min()), int(yy.min()), int(xx.max()) + 1, int(yy.max()) + 1]


def example_image(old_case, old_unit, new_unit, root, output):
    with Image.open(root / old_case["source"]["image"]) as source:
        source = source.convert("RGB")
    old = load_mask(root / old_unit["target"]["mask"])
    new = load_mask(root / new_unit["target"]["mask"])
    bbox = box(old | new)
    pad = max(28, round(max(bbox[2] - bbox[0], bbox[3] - bbox[1]) * 0.16))
    region = (max(0, bbox[0] - pad), max(0, bbox[1] - pad),
              min(source.width, bbox[2] + pad), min(source.height, bbox[3] + pad))
    arr = np.asarray(source)
    panels = [source]
    for mask, color in [(old, [255, 45, 85]), (new, [0, 205, 115])]:
        overlay = arr.copy()
        overlay[mask] = (overlay[mask] * 0.45 + np.array(color) * 0.55).astype(np.uint8)
        panels.append(Image.fromarray(overlay).crop(region))
    canvas = Image.new("RGB", (1500, 470), "white")
    font = ImageFont.truetype("DejaVuSans.ttf", 20)
    draw = ImageDraw.Draw(canvas)
    for i, (panel, title) in enumerate(zip(panels, ["SOURCE", "2.5.0 BEFORE", "2.6.0 AFTER"])):
        panel.thumbnail((490, 420))
        canvas.paste(panel, (i * 500 + (490 - panel.width) // 2, 45 + (420 - panel.height) // 2))
        draw.text((i * 500 + 10, 10), title, fill="black", font=font)
    canvas.save(output, quality=91)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.dataset_root
    out = REPO / "data/v2_2.6.0"
    base = read_jsonl(REPO / "data/v2_1084/cases.jsonl")
    current = read_jsonl(out / "cases.jsonl")
    old_cases = {c["id"]: c for c in base}
    new_cases = {c["id"]: c for c in current}
    changes, patch = [], []
    counts = Counter()
    transitions = Counter()
    for case in current:
        old_case = old_cases[case["id"]]
        old_units = {u["id"]: u for u in old_case["units"]}
        for unit in case["units"]:
            old = old_units[unit["id"]]
            old_target, target = old["target"], unit["target"]
            mask_changed = target["mask"] != old_target["mask"]
            pixels_changed = mask_changed and not np.array_equal(
                load_mask(root / old_target["mask"]), load_mask(root / target["mask"]))
            ref_changed = old["instruction_ref"] != unit["instruction_ref"]
            no_ref_changed = old["instruction_noref"] != unit["instruction_noref"]
            operation_changed = old["operation"] != unit["operation"]
            counts.update({"ref_changed": int(ref_changed), "noref_changed": int(no_ref_changed),
                           "reviewed_v2_masks": int(mask_changed), "mask_pixels_changed": int(pixels_changed),
                           "operation_changed": int(operation_changed)})
            if operation_changed:
                transitions[old["operation"] + "->" + unit["operation"]] += 1
            changes.append({
                "case_id": case["id"], "unit_id": unit["id"],
                "ref_changed": ref_changed, "noref_changed": no_ref_changed,
                "mask_file_changed": mask_changed, "mask_pixels_changed": pixels_changed,
                "operation_changed": operation_changed,
                "before": {"operation": old["operation"], "ref": old["instruction_ref"],
                           "noref": old["instruction_noref"], "mask": old_target["mask"],
                           "box": old_target["box"], "point": old_target["point"]},
                "after": {"operation": unit["operation"], "ref": unit["instruction_ref"],
                          "noref": unit["instruction_noref"], "mask": target["mask"],
                          "box": target["box"], "point": target["point"]},
            })
            if mask_changed:
                source = root / target["mask"]
                dest = out / "mask_patch" / target["mask"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)
                recipe = root / "release_2_6_work" / case["id"] / (unit["id"] + "_v2.json")
                patch.append({"path": target["mask"], "sha256": sha256_file(dest),
                              "bytes": dest.stat().st_size, "case_id": case["id"], "unit_id": unit["id"],
                              "recipe": json.loads(recipe.read_text()) if recipe.exists() else None})
    write_jsonl(out / "unit_changes.jsonl", changes)
    write_jsonl(out / "mask_patch_manifest.jsonl", patch)
    status = json.loads((REPO / "construction/release_2_6/status.json").read_text())["summary"]
    round2 = [r for r in read_jsonl(REPO / "construction/release_2_6/logs/round2.jsonl")
              if r.get("event") == "round2_final_report"][-1]
    summary = {
        "base_release": "2.5.0", "release_version": "2.6.0",
        "before_manifest_sha256": sha256_file(REPO / "data/v2_1084/cases.jsonl"),
        "after_manifest_sha256": sha256_file(out / "cases.jsonl"),
        "cases": len(current), "units": sum(len(c["units"]) for c in current),
        "source_images_unchanged": all(c["source"]["sha256"] == old_cases[c["id"]]["source"]["sha256"]
                                       for c in current),
        "cases_removed": sorted(set(old_cases) - set(new_cases)),
        "units_removed": sum(len(c["units"]) for c in base) - sum(len(c["units"]) for c in current),
        **counts, "operation_transitions": dict(transitions),
        "mask_patch_files": len(patch), "mask_patch_bytes": sum(r["bytes"] for r in patch),
        "repair_status": status["status"], "open_findings": status["open_findings"],
        "open_part_mask_units": status["open_part_mask_units"],
        "round2": {k: round2[k] for k in ["completed_cases", "units_total", "unit_actions", "keep_mask_only",
                                         "accepted_v2_masks_in_assignment", "new_v2_mask_files"]},
        "independent_human_verified": False, "model_edit_outputs": 0,
    }
    write_json(out / "comparison_summary.json", summary)
    write_json(REPO / "data/current.json", {
        "release_version": "2.6.0", "manifest": "v2_2.6.0/cases.jsonl",
        "release": "v2_2.6.0/release.json", "statistics": "v2_2.6.0/statistics.json",
        "validation": "v2_2.6.0/validation.json", "comparison": "v2_2.6.0/comparison_summary.json",
        "historical_release": "v2_1084/release.json",
    })
    images = REPO / "docs/assets/release_2_6"
    images.mkdir(parents=True, exist_ok=True)
    lines = ["# Release 2.6.0 修复前后对比", "",
             "比较基线为冻结的2.5.0。图中红色为旧定位，绿色为新版定位；左右使用相同源图裁剪。"
             "这些是benchmark指令与源区域标注对比，**不是模型生成的编辑结果图**。", "",
             "## 全库变化", "", "| 项目 | 2.5.0 | 2.6.0 |", "|---|---:|---:|",
             f"| 源图 / 单元 | {len(base)} / {sum(len(c['units']) for c in base)} | {summary['cases']} / {summary['units']} |",
             "| 指令协议 / mask语义 | 1.0 / 1.1 | 2.0 / 2.0 |",
             f"| no-ref重渲染 | — | {counts['noref_changed']} |",
             f"| Ref内容改写 | — | {counts['ref_changed']} |",
             f"| 已复核v2 mask / 实际像素改变 | — | {len(patch)} / {counts['mask_pixels_changed']} |",
             f"| 删除case / 单元 | — | {len(summary['cases_removed'])} / {summary['units_removed']} |", "",
             "完整逐单元对比：[unit_changes.jsonl](../data/v2_2.6.0/unit_changes.jsonl)；"
             "[汇总JSON](../data/v2_2.6.0/comparison_summary.json)。", "",
             "## 最后一轮196例", "",
             "接续时608例完成，196例未完成（todo 182、partial 2、done_unlogged 12）；现在804例修复任务全部完成，"
             "另280例仅做统一协议迁移。最后一轮758单元：keep 450（含96个仅换mask）、revise 299、retarget 9、drop 0；"
             "确认229张v2 mask，其中新增224张、复核已有5张。", "",
             "发布合并补修：7184680 U4回看已审靴筒mask，改为标准部件移除，去掉未分类的结果从句；"
             "操作、mask及上述动作数不变。共享canonical协议文件沿用上游版本，历史1.0由兼容层分派。", "",
             "## 代表性样例", ""]
    overview = Image.new("RGB", (1500, 940), "white")
    for i, (cid, uid, title) in enumerate(EXAMPLES):
        old_case, new_case = old_cases[cid], new_cases[cid]
        old_unit = next(u for u in old_case["units"] if u["id"] == uid)
        new_unit = next(u for u in new_case["units"] if u["id"] == uid)
        filename = cid + "_" + uid + ".jpg"
        example_image(old_case, old_unit, new_unit, root, images / filename)
        lines += [f"### {i + 1}. {title} · {cid} {uid}", "",
                  f"![{title}](assets/release_2_6/{filename})", "",
                  "| 字段 | 修复前2.5.0 | 修复后2.6.0 |", "|---|---|---|",
                  f"| Ref | {old_unit['instruction_ref']} | {new_unit['instruction_ref']} |",
                  f"| No-ref | {old_unit['instruction_noref']} | {new_unit['instruction_noref']} |", ""]
        if i < 4:
            with Image.open(images / filename) as tile:
                tile = tile.crop((500, 0, 1500, 470)).resize((750, 470))
                overview.paste(tile, ((i % 2) * 750, (i // 2) * 470))
    overview.save(images / "overview.jpg", quality=91)
    lines += ["## 待人工复核的已接受判断", "",
              "AI目视修复和发布校验均已完成，尚无独立人工验收或模型编辑结果。"
              "以下是已接受但建议人工抽查的判断，不是未解决case。", "",
              "| Case | 判断 |", "|---|---|"]
    for record in round2["manual_review_recommended_accepted_judgments"]:
        lines.append(f"| {record['case_id']} | {'；'.join(record['judgments'])} |")
    lines += ["", "被否定或部分否定的审查、坐标证据及实际修复动作见"
              "[完整日志](../construction/release_2_6/logs/round2.jsonl)的 round2_final_report 事件；"
              "全库审查历史见[审查报告](BENCHMARK_AUDIT_20261015_ZH.md)。", ""]
    (REPO / "docs/RELEASE_2_6_BEFORE_AFTER_ZH.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
