"""CPU post-validation of fixed MIRAGE/MICE fairness probes.

Reads terminal artifacts, checks input fidelity, and makes honest image galleries.
No editor, planner, Judge, or score estimation is called here.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import torch

ROOT = Path("/tmp/ifbench/fairness_v2_20261030/mirage_mice")
PROBE = ROOT / "probe"
SOURCES = Path("/tmp/ifbench/protocol_review_20261027/sources")
CASES = ["v2-sa_10063996", "v2-sa_7414116"]
SETTINGS = [
    "S1",
    "S2-point",
    "S2-box",
    "S2-mask",
    "S3-point",
    "S3-box",
    "S3-mask",
    "S4-ref",
    "S4-noref",
    "S5",
]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
COMPONENTS = {
    "mirage": {
        "method_commit": "234a31968df307879a55675873a54258d6c0eae4",
        "components": [
            {
                "role": "native parser/locator",
                "repo": "Qwen/Qwen3.5-9B",
                "revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
            },
            {
                "role": "native joint editor backbone",
                "repo": "Qwen/Qwen-Image-Edit-2511",
                "revision": "6f3ccc0b56e431dc6a0c2b2039706d7d26f22cb9",
            },
        ],
        "external_enhancers": [],
        "prompt_adapter": "Append fixed public unit/color/selector hints to native grounding messages; not an unchanged official grounding prompt.",
    },
    "mice": {
        "method_commit": "43b289de84dfd184c0ee1b551b0e1bea02f6e92d",
        "components": [
            {
                "role": "native backbone with MICE attention",
                "repo": "black-forest-labs/FLUX.2-klein-4B",
                "revision": "e7b7dc27f91deacad38e78976d1f2b499d76a294",
            }
        ],
        "external_enhancers": [],
        "prompt_adapter": "Public none/point instructions in native global text; box/mask instructions in native local text. Exactly one reference image.",
    },
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def native_utils():
    spec = importlib.util.spec_from_file_location(
        "native_mice_pipeline_utils", SOURCES / "mice/flux2/pipeline_utils.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def image_equal(left, right):
    with Image.open(left) as a, Image.open(right) as b:
        a = a.convert("RGB")
        b = b.convert("RGB")
        return a.size == b.size and a.tobytes() == b.tobytes()


def public_tag(unit):
    colors = ["red", "blue", "green", "yellow", "magenta"]
    return f"[{colors[int(unit['id'][1:]) - 1]} point, label {unit['id']}]"


def audit_mice(request, call, result, out, utils):
    checks = []

    def add(name, passed, **details):
        checks.append({"name": name, "passed": bool(passed), **details})

    globals_ = [u for u in request["public_units"] if u["locator"] in ("none", "point")]
    regions = [u for u in request["public_units"] if u["locator"] in ("box", "mask")]
    add("global_unit_ids", call["global_unit_ids"] == [u["id"] for u in globals_])
    add("regional_unit_ids", [r["unit_id"] for r in call["regions"]] == [u["id"] for u in regions])
    add("actual_prompt_equals_registered_request", call["prompt"] == request["prompt"])
    blocks = call["prompt"].split("$BREAKFLAG$")
    add("native_local_texts_exactly_public", blocks[1:] == [u["instruction"] for u in regions])
    add(
        "point_and_none_tasks_present_in_global",
        all(u["instruction"] in blocks[0] for u in globals_),
    )
    add(
        "point_labels_present_in_global",
        all(public_tag(u) in blocks[0] for u in globals_ if u["locator"] == "point"),
    )
    add(
        "point_not_converted_to_binding_mask",
        not set(u["id"] for u in globals_ if u["locator"] == "point")
        & set(r["unit_id"] for r in call["regions"]),
    )
    w, h = request["model_size"]
    sw, sh = request["source"]["size"]
    source = Image.open(request["image"]).convert("RGB").resize((w, h), Image.Resampling.LANCZOS)
    actual = Image.open(call["actual_source"]).convert("RGB")
    add(
        "actual_single_source_pixels",
        actual.size == source.size and actual.tobytes() == source.tobytes(),
        size=list(actual.size),
        input_file=request["image"],
    )
    binding_rows = []
    for unit, saved in zip(regions, call["regions"], strict=True):
        if unit["locator"] == "box":
            box = [v / d for v, d in zip(unit["region"]["coordinates"], (sw, sh, sw, sh))]
            expected = utils.create_position_mask_list([box], h, w, 8)[0]
        else:
            m = torch.from_numpy(
                np.array(Image.open(unit["region"]["path"]).convert("L")) > 127
            ).float()
            expected = utils.resize_mask(m, h // 16, w // 16)
        actual = np.array(Image.open(saved["latent_mask"]).convert("L"))
        correct = np.array_equal(actual, (expected.numpy() * 255).astype("uint8"))
        add(
            "native_binding_grid_" + unit["id"],
            correct and sha(saved["latent_mask"]) == saved["sha256"],
            modality=unit["locator"],
            selected_tokens=int(expected.sum()),
        )
        binding_rows.append(
            {
                "unit_id": unit["id"],
                "public_modality": unit["locator"],
                "selected_tokens": int(expected.sum()),
                "native_grid_equal": bool(correct),
                "latent_mask": saved["latent_mask"],
            }
        )
    add("four_native_transformer_calls", result["transformer_forward_calls"] == 4)
    add(
        "native_strict_default", call["configuration"]["attention_setting"] == "apitasmkernelnonlap"
    )
    return {
        "checks": checks,
        "all_passed": all(c["passed"] for c in checks),
        "global_prompt": blocks[0],
        "local_prompts": blocks[1:],
        "binding_rows": binding_rows,
        "metadata_note": "Actual route from call/request supersedes old loader configuration.region_form text.",
    }


def audit_mirage(request, call, result, planner, planner_dir):
    checks = []

    def add(name, passed, **details):
        checks.append({"name": name, "passed": bool(passed), **details})

    traces = load(planner_dir / "traces.json") if (planner_dir / "traces.json").exists() else []
    add("planner_request_binding", planner["request_digest"] == request["request_digest"])
    add("native_api_call_count", planner.get("extra_planner_api_calls") == len(traces))
    add(
        "native_batch_item_count",
        planner.get("extra_planner_batch_items") == sum(len(t["messages"]) for t in traces),
    )
    if traces:
        parse = traces[0]
        parse_texts = [item[-1]["content"][-1]["text"] for item in parse["messages"]]
        add(
            "parser_inputs_exact_public_per_unit",
            parse_texts == [f"Input: <<<{s}>>>\nOutput:" for s in request["parser_inputs"]],
        )
    pairs = planner.get("parser_pairs_by_unit", {})
    counts = {k: len(v) for k, v in pairs.items()}
    if planner.get("status") == "planned":
        add("all_native_pairs_retained", len(planner["regions"]) == sum(counts.values()))
        actual_by_unit = {
            u["id"]: sum(r["unit_id"] == u["id"] for r in planner["regions"])
            for u in request["public_units"]
        }
        add("native_unit_binding", actual_by_unit == counts)
    grounding = []
    for trace in traces[1:]:
        for item in trace["messages"]:
            content = item[-1]["content"]
            images = [c["image"] for c in content if c["type"] == "image"]
            texts = [c["text"] for c in content if c["type"] == "text"]
            for image in images:
                hint = image.get("public_hint", "")
                matches = [u for u, h in request["grounding_hints"].items() if h == hint and h]
                hint_ok = (
                    (hint in texts and len(matches) == 1)
                    if hint
                    else all(h not in texts for h in request["grounding_hints"].values() if h)
                )
                pixel_ok = sha(image["path"]) == image["sha256"]
                if image["size"] == request["source"]["size"]:
                    pixel_ok = pixel_ok and image_equal(image["path"], request["grounding_image"])
                add(
                    "grounding_hint_call" + str(trace["index"]) + "_" + Path(image["path"]).stem,
                    hint_ok and pixel_ok,
                    unit_ids=matches,
                    crop=image["size"] != request["source"]["size"],
                )
                grounding.append(
                    {
                        "call_index": trace["index"],
                        "unit_ids": matches,
                        "hint": hint,
                        "texts": texts,
                        "image": image,
                        "hint_matches_public": hint_ok,
                    }
                )
    if call:
        add("editor_uses_clean_source", call["image"] == request["source"]["path"])
        add("original_global_prompt", call["prompt"] == request["global_original_prompt"])
        add(
            "native_predicted_boxes_passed",
            call["bboxes"] == [r["bbox"] for r in planner["regions"]],
        )
        expected = []
        for region in planner["regions"]:
            inst = region["new_instruction"].strip()
            if inst[-1] not in ".!?":
                inst += "."
            expected.append(
                f"Target: {region['refer_object'].strip().rstrip('.')}. Instruction: {inst}"
            )
        add("native_qwen_local_template", call["sub_prompts"] == expected)
        add(
            "joint_native_forward_count",
            result["transformer_forward_calls"] == 32 * len(planner["regions"]) + 48,
            expected=32 * len(planner["regions"]) + 48,
            actual=result["transformer_forward_calls"],
        )
    return {
        "checks": checks,
        "all_passed": all(c["passed"] for c in checks),
        "planner_api_calls": len(traces),
        "planner_batch_items": sum(len(t["messages"]) for t in traces),
        "pairs_per_unit": counts,
        "native_total_pairs": sum(counts.values()),
        "grounding_calls": grounding,
        "traces": str(planner_dir / "traces.json"),
    }


def panel(path, title, width=500, height=355):
    canvas = Image.new("RGB", (width, height), "#f2f2f2")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(FONT, 17)
    draw.text((10, 8), title, font=font, fill="black")
    if path and Path(path).is_file():
        im = Image.open(path).convert("RGB")
        im.thumbnail((width - 14, height - 43), Image.Resampling.LANCZOS)
        canvas.paste(im, ((width - im.width) // 2, 36 + (height - 43 - im.height) // 2))
    else:
        draw.text((25, 120), "No terminal output", font=font, fill="#9a2525")
    return canvas


def make_figure(row, destination):
    request = row["request"]
    model = row["model"]
    out = Path(row["output_dir"])
    result = row["result"]
    if model == "mirage":
        middle = request["grounding_image"]
        title = "Native locator input"
    else:
        middle = (
            str(out / "actual_source.png")
            if (out / "actual_source.png").exists()
            else request["image"]
        )
        title = "Single actual editor input"
    panels = [
        panel(request["source"]["path"], "Clean source / report context"),
        panel(middle, title),
        panel(result.get("output_image"), "Actual editor output"),
    ]
    regions = row.get("call", {}).get("regions", []) if model == "mice" and row.get("call") else []
    figure = Image.new("RGB", (1500, 577 if regions else 397), "white")
    d = ImageDraw.Draw(figure)
    d.text(
        (12, 8),
        f"{model.upper()} | {row['setting']} | {row['case_id']} | {result.get('status', 'pending')}",
        font=ImageFont.truetype(FONT, 22),
        fill="black",
    )
    for i, p in enumerate(panels):
        figure.paste(p, (i * 500, 42))
    if regions:
        d.text(
            (12, 403),
            "Native binding grids derived from supplied boxes/masks (not extra reference images)",
            font=ImageFont.truetype(FONT, 18),
            fill="black",
        )
        for i, region in enumerate(regions):
            x = 12 + i * 292
            d.text(
                (x, 431),
                f"{region['unit_id']} / {region['public_modality']} / {region['selected_tokens']} tokens",
                font=ImageFont.truetype(FONT, 16),
                fill="black",
            )
            grid = Image.open(region["latent_mask"]).convert("RGB")
            scale = min(270 / grid.width, 112 / grid.height)
            grid = grid.resize(
                (max(1, round(grid.width * scale)), max(1, round(grid.height * scale))),
                Image.Resampling.NEAREST,
            )
            figure.paste(grid, (x, 456))
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.save(destination, quality=92)
    return str(destination)


def overview(rows, path):
    canvas = Image.new("RGB", (1750, 590), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (10, 5),
        f"{rows[0]['model'].upper()} / {rows[0]['case_id']} : fixed outputs, not selected by quality",
        font=ImageFont.truetype(FONT, 22),
        fill="black",
    )
    for i, row in enumerate(rows):
        im = panel(
            row["result"].get("output_image"),
            row["setting"] + " / " + row["result"].get("status", "pending"),
            350,
            270,
        )
        canvas.paste(im, ((i % 5) * 350, 40 + (i // 5) * 270))
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, quality=93)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument(
        "--models", nargs="+", choices=["mice", "mirage"], default=["mice", "mirage"]
    )
    args = parser.parse_args()
    torch.set_num_threads(1)
    utils = native_utils()
    rows = []
    pending = []
    observations = (
        load(ROOT / "VISUAL_OBSERVATIONS.json")
        if (ROOT / "VISUAL_OBSERVATIONS.json").exists()
        else {}
    )
    for model in args.models:
        for case in CASES:
            for setting in SETTINGS:
                out = PROBE / model / "outputs" / setting / case
                req = load(PROBE / model / "requests" / setting / case / "request.json")
                if not (out / "result.json").exists():
                    pending.append(f"{model}/{setting}/{case}")
                    continue
                result = load(out / "result.json")
                assert result["request_digest"] == req["request_digest"]
                call = load(out / "call.json") if (out / "call.json").exists() else None
                if result["status"] == "generated":
                    assert sha(result["output_image"]) == result["output_sha256"]
                    assert sha(result["raw_image"]) == result["raw_sha256"]
                row = {
                    "model": model,
                    "case_id": case,
                    "setting": setting,
                    "request": req,
                    "result": result,
                    "call": call,
                    "output_dir": str(out),
                }
                if model == "mice" and call and result["status"] == "generated":
                    row["audit"] = audit_mice(req, call, result, out, utils)
                elif model == "mirage":
                    pdir = PROBE / model / "planners" / setting / case
                    if (pdir / "result.json").exists():
                        prior = load(pdir / "result.json")
                        row["planner"] = prior
                        row["audit"] = audit_mirage(req, call, result, prior, pdir)
                row["visual_observation"] = observations.get(f"{model}/{setting}/{case}")
                fig = ROOT / "figures" / model / f"{setting}__{case}.jpg"
                row["figure"] = make_figure(row, fig)
                rows.append(row)
    if pending and not args.allow_incomplete:
        raise SystemExit(
            f"{len(pending)} requests remain nonterminal; use --allow-incomplete only for explicitly partial preview."
        )
    summaries = {}
    for model in args.models:
        items = [r for r in rows if r["model"] == model]
        summaries[model] = {
            "terminal": len(items),
            "expected": 20,
            "generated": sum(r["result"]["status"] == "generated" for r in items),
            "failed": sum(r["result"]["status"] == "failed" for r in items),
            "editor_api_calls": sum(r["result"].get("inference_api_calls", 0) for r in items),
            "transformer_forward_calls": sum(
                r["result"].get("transformer_forward_calls", 0) for r in items
            ),
            "planner_api_calls": sum(
                r.get("planner", {}).get("extra_planner_api_calls", 0) for r in items
            ),
            "planner_batch_items": sum(
                r.get("planner", {}).get("extra_planner_batch_items", 0) for r in items
            ),
            "audit_passed_requests": sum(
                r.get("audit", {}).get("all_passed", False) for r in items
            ),
            "audit_checks": sum(len(r.get("audit", {}).get("checks", [])) for r in items),
            "audit_failed_checks": [
                {"case_id": r["case_id"], "setting": r["setting"], **c}
                for r in items
                for c in r.get("audit", {}).get("checks", [])
                if not c["passed"]
            ],
            "editor_wall_seconds_sum": sum(r["result"].get("wall_seconds", 0) for r in items),
            "planner_wall_seconds_sum": sum(
                r.get("planner", {}).get("wall_seconds", 0) for r in items
            ),
        }
        for case in CASES:
            subset = [r for r in items if r["case_id"] == case]
            if len(subset) == 10:
                overview(subset, ROOT / "figures" / model / f"overview__{case}.jpg")
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "fixed two dev images per model; no Judge, no quality score or selection",
        "summaries": summaries,
        "pending": pending,
        "components": {m: COMPONENTS[m] for m in args.models},
        "component_revision_evidence": "/opt/tiger/tanyue/if-bench/docs/protocol/if-bench-v1/SOURCE_INDEX.md",
        "rows": rows,
        "postprocessor_model_calls": 0,
        "postprocessor_judge_calls": 0,
    }
    name = (
        "POST_VALIDATION"
        if set(args.models) == {"mice", "mirage"}
        else "POST_VALIDATION_" + "_".join(args.models)
    )
    write(ROOT / (name + ".json"), report)
    md = [
        "# MIRAGE / MICE 公平性方案：固定样例验证",
        "",
        f"生成于 {report['generated_at_utc']}。只有固定两张 dev 图；没有调用 Judge，不报告或估计 UP/JP。",
        "",
        "|模型|已终态/应完成|出图|失败|编辑API|原生planner API / batch项|Transformer forwards|输入合约通过|",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model, s in summaries.items():
        md.append(
            f"|{model}|{s['terminal']}/{s['expected']}|{s['generated']}|{s['failed']}|{s['editor_api_calls']}|{s['planner_api_calls']} / {s['planner_batch_items']}|{s['transformer_forward_calls']}|{s['audit_passed_requests']}/{s['terminal']}|"
        )
    if pending:
        md += ["", f"**部分预览：仍有 {len(pending)} 个请求未终态，不能称完整验证。**"]
    md += [
        "",
        "记录以真实 call/result/traces 为准。左列清图是报告上下文，不表示 MICE point 模式额外得到清图；中列为其唯一编辑输入。MIRAGE 的中列是 native locator 输入，编辑器使用清图。",
        "",
        "图中标记残留/目标变化只作固定样例观察，不是全量残留率或质量分数。",
        "",
    ]
    md += [
        "本轮两种方法均使用生成前登记的一套映射；没有因输出好坏改 prompt、修正原生预测或再采样。新映射与旧候选不同，旧分数不能移植。完整输入方式及其官方证据见 [源码与接口审查](MIRAGE_MICE_FAIRNESS_REVIEW.md)。",
        "",
        "组件与推理成本：",
        "",
        "|方法|原生组件/固定 revision|本轮参数与边界|",
        "|---|---|---|",
    ]
    for model in args.models:
        component = "；".join(
            c["role"] + "：`" + c["repo"] + "@" + c["revision"] + "`"
            for c in COMPONENTS[model]["components"]
        )
        detail = (
            "40 步、true CFG 4、patch ratio 0.4、padding 10、seed 42；保留原生 parser/locator，grounding 消息追加公开标记说明"
            if model == "mirage"
            else "4 步、CFG 1、kernel 11、temperature 3、strict=False、seed 42；单图，point/none 走 global，box/mask 走原生 local binding"
        )
        md.append(f"|{model}|{component}|{detail}|")
    md += [
        "",
        "本表组件均属于命名方法；未加外部 SAM、定位器或 prompt 改写器。权重证据：[SOURCE_INDEX.md](/opt/tiger/tanyue/if-bench/docs/protocol/if-bench-v1/SOURCE_INDEX.md)。每请求 `wall_seconds` 是该次调用耗时，汇总不含权重加载，也不等同并行任务总墙钟或完整 GPU 占用时长。",
        "",
    ]
    if "mice" in args.models:
        md += [
            "MICE 的静态 loader `configuration.region_form` 沿用了旧描述；本轮真实路由以 `call.api_region_argument`、`global_unit_ids` 和 `regions` 为准。真实调用没有把 point 做成硬 mask。零实例模式可运行，但没有启用专门的点绑定；双图则被原生 attention 索引限制排除。",
            "",
        ]
    if "mirage" in args.models:
        md += [
            "MIRAGE 的 locator 预测错误原样保留；编辑器收到的是清图和预测框，因此没有可视标记残留不能解释成编辑器成功擦除了标记。公开点落在预测框内只是一项几何核查，也不能证明定位了完整对象。",
            "",
        ]
    for model in args.models:
        md += ["## " + model, ""]
        for setting in SETTINGS:
            md += ["### " + setting, ""]
            for row in [r for r in rows if r["model"] == model and r["setting"] == setting]:
                r = row["result"]
                req = row["request"]
                audit = row.get("audit", {})
                md += [
                    f"**{row['case_id']}**：{r['status']}；输入合约检查 {'通过' if audit.get('all_passed') else '待核/失败'}。",
                    "",
                    f"![{model} {setting} {row['case_id']}]({Path(row['figure']).relative_to(ROOT).as_posix()})",
                    "",
                ]
                if r["status"] == "failed":
                    md += ["失败原因：`" + r.get("error", "unknown") + "`", ""]
                if row["visual_observation"]:
                    md += ["目视观察：" + row["visual_observation"]["observation"], ""]
                else:
                    md += ["目视观察：待人工/agent查看，不由脚本推断编辑成败。", ""]
                if model == "mice" and row["call"]:
                    md += [
                        f"global 单元：{row['call']['global_unit_ids']}；native region 单元：{[x['unit_id'] for x in row['call']['regions']]}；区域参数：`{row['call']['api_region_argument']}`。",
                        "",
                        "实际最终 prompt：",
                        "```text",
                        row["call"]["prompt"],
                        "```",
                        "",
                    ]
                elif model == "mirage":
                    md += [
                        f"原生拆分：{audit.get('pairs_per_unit', {})}；planner API / batch项：{audit.get('planner_api_calls', 0)} / {audit.get('planner_batch_items', 0)}。",
                        "",
                        "原生 parser 输入（原文）：",
                        "```text",
                        "\n".join(f"{u['id']}: {u['instruction']}" for u in req["public_units"]),
                        "```",
                        "",
                    ]
                    hints = [
                        f"{unit_id}: {hint}"
                        for unit_id, hint in req["grounding_hints"].items()
                        if hint
                    ]
                    md += [
                        "实际追加到原生 grounding 消息的公开标记说明：",
                        "```text",
                        "\n".join(hints) if hints else "(none: no region hint supplied)",
                        "```",
                        "",
                    ]
                    if row["call"]:
                        md += [
                            "实际编辑 global / local prompts：",
                            "```text",
                            row["call"]["prompt"],
                            "\nLOCAL:",
                            *row["call"]["sub_prompts"],
                            "```",
                            "",
                        ]
                        md += [
                            "原生预测后实际传给编辑器的框（源图像素 xyxy）：",
                            "",
                            "|原始单元|原生 refer_object|x1,y1,x2,y2|",
                            "|---|---|---|",
                        ]
                        for region in row.get("planner", {}).get("regions", []):
                            box = region["bbox"]
                            coords = ",".join(str(box[k]) for k in ["x1", "y1", "x2", "y2"])
                            md.append(f"|{region['unit_id']}|{region['refer_object']}|{coords}|")
                        md.append("")
                    if audit.get("traces"):
                        md += [f"[实际 VLM 消息、raw回答与输入图]({audit['traces']})", ""]
                md += [
                    f"[请求]({PROBE / model / 'requests' / setting / row['case_id'] / 'request.json'}) · [运行记录]({Path(row['output_dir']) / 'result.json'})",
                    "",
                ]
    md += [
        "## 完整性与限制",
        "",
        "所有观察都限于预先固定样例；生成成功只说明流程跑通，不能替代正确性与质量评价。MIRAGE 原生 locator 是否稳定理解各类标记、MICE point/global 路由能否可靠绑定目标仍需结合完整方案审核，不能因两张图效果好坏临时改提示词。",
        "",
        f"机器记录：[{name}.json]({name}.json)。原完整 dev 评分保持不变；本轮结果不能冒充原候选或正式 test。",
        "",
    ]
    (ROOT / (name + ".md")).write_text("\n".join(md))
    print(
        json.dumps(
            {"report": str(ROOT / (name + ".md")), "summaries": summaries, "pending": len(pending)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
