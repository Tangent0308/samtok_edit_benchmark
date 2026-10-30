"""Measured Qwen-2511 smoke summary with inline actual input/output images."""

from __future__ import annotations

import argparse
import base64
from collections import Counter
import html
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from samtok_benchmark.io import sha256_file, write_json
from . import SETTINGS
from .render import FONT
from .validate_smoke import validate


def comparison(tasks, records, root, dest):
    width, row_height = 1800, 480
    image = Image.new("RGB", (width, 50 + row_height * len(tasks)), "#f1f5f9")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(str(FONT), 20)
    font = ImageFont.truetype(str(FONT), 17)
    draw.text(
        (15, 12),
        f"Qwen-Image-Edit-2511 | {dest.stem} | actual inputs / resized output",
        font=title_font,
        fill="black",
    )
    for index, t in enumerate(tasks):
        record = records[t["id"]]
        call = json.loads((root / "runs" / t["id"] / "call.json").read_text())
        y = 50 + index * row_height
        draw.text(
            (15, y + 4),
            f"{t['case_id']} | {t['setting']} | {t['form']} | {record['status']}",
            font=font,
            fill="black",
        )
        # Source context is clearly distinguished from the actual single-image input.
        shared = Path(json.loads((root / "plan.json").read_text())["shared_root"])
        req = json.loads(
            (shared / "requests" / t["setting"] / t["case_id"] / "public.json").read_text()
        )
        paths = [
            (
                "SOURCE (context)" if t["form"] == "single" else "SOURCE (input 1)",
                req["source"]["path"],
            )
        ]
        if t["form"] == "single":
            paths.append(("ACTUAL SINGLE INPUT", call["images"][0]["path"]))
        elif len(call["images"]) > 1:
            paths.append(("ANNOTATION (input 2)", call["images"][1]["path"]))
        else:
            paths.append(("NO ANNOTATION INPUT", None))
        paths.append(("OUTPUT (resized to source)", record.get("output_image")))
        for col, (label, path) in enumerate(paths):
            x = 15 + col * 600
            draw.text((x, y + 32), label, font=font, fill="black")
            if path:
                with Image.open(path) as im:
                    preview = im.convert("RGB")
                preview.thumbnail((570, 410))
                image.paste(
                    preview, (x + (570 - preview.width) // 2, y + 60 + (410 - preview.height) // 2)
                )
            else:
                draw.text(
                    (x + 40, y + 220), "Not supplied / unavailable", font=font, fill="#64748b"
                )
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, quality=94)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    validation = validate(root)
    if validation["errors"]:
        raise SystemExit("Smoke integrity validation failed; see validation.json")
    plan = json.loads((root / "plan.json").read_text())
    records = {}
    missing = []
    for task in plan["tasks"]:
        p = root / "runs" / task["id"] / "result.json"
        if not p.exists():
            missing.append(task["id"])
            continue
        record = json.loads(p.read_text())
        assert record["plan_digest"] == plan["digest"]
        if record["status"] == "generated":
            assert sha256_file(Path(record["output_image"])) == record["output_sha256"]
            with Image.open(record["output_image"]) as im:
                assert im.mode == "RGB" and list(im.size) == record["output_size"]
        records[task["id"]] = record
    if missing:
        write_json(root / "incomplete.json", {"missing": missing})
        raise SystemExit("Incomplete smoke: no final success report produced")
    aliases = []
    for alias in plan["aliases"]:
        src = records[alias["reuse_task"]]
        aliases.append(
            {
                **alias,
                "status": "reused-identical-input"
                if src["status"] == "generated"
                else "failed-source",
                "output_image": src.get("output_image"),
                "output_sha256": src.get("output_sha256"),
                "additional_inference_api_calls": 0,
            }
        )
    write_json(root / "aliases.json", aliases)
    success = [r for r in records.values() if r["status"] == "generated"]
    failures = [r for r in records.values() if r["status"] != "generated"]
    weights = json.loads((root / "weight_inventory.json").read_text())
    summary = {
        "model": plan["model"],
        "status": "smoke_completed" if not failures else "smoke_has_failures",
        "case_ids": sorted({t["case_id"] for t in plan["tasks"]}),
        "model_revision": plan["model_revision"],
        "diffusers_revision": plan["diffusers_revision"],
        "parameters": plan["parameters"],
        "seed": plan["seed"],
        "plan_digest": plan["digest"],
        "inference_requests": len(records),
        "generated": len(success),
        "failed": len(failures),
        "identical_input_reuses": len(aliases),
        "judge_calls": 0,
        "candidate_scores_computed": False,
        "actual_denoising_steps": dict(Counter(str(r["denoising_steps"]) for r in success)),
        "actual_transformer_forward_calls": dict(
            Counter(str(r["transformer_forward_calls"]) for r in success)
        ),
        "actual_text_encoder_forward_calls": dict(
            Counter(str(r["text_encoder_forward_calls"]) for r in success)
        ),
        "total_transformer_forward_calls": sum(
            r["transformer_forward_calls"] for r in records.values()
        ),
        "extra_component_calls": {
            k: sum(r["extra_component_calls"][k] for r in records.values())
            for k in ("rewriter", "planner", "reflection", "external_grounder", "sam")
        },
        "sum_pipeline_wall_seconds": sum(r["pipeline_wall_seconds"] for r in records.values()),
        "sum_cuda_event_seconds": sum(
            r.get("cuda_event_elapsed_seconds", 0) for r in records.values()
        ),
        "peak_gpu_allocated_bytes": max(r["peak_gpu_allocated_bytes"] for r in records.values()),
        "weight_files_verified": len(weights["files"]),
        "raw_output_sizes": sorted({tuple(r["raw_size"]) for r in success}),
        "encoded_token_lengths": sorted({n for r in success for n in r["encoded_token_lengths"]}),
        "failures": [{"id": r["task"]["id"], "error": r.get("error")} for r in failures],
        "gpu_timing_note": "Measured pipeline wall/CUDA-event intervals, not summed GPU kernel active time. No speed ranking.",
    }
    totals = [json.loads(p.read_text()) for p in root.glob("worker*.total.json")]
    summary["completed_worker_wall_seconds"] = sum(r["worker_wall_seconds"] for r in totals)
    summary["worker_total_records"] = len(totals)
    write_json(root / "summary.json", summary)
    galleries = []
    for setting in SETTINGS:
        tasks = [t for t in plan["tasks"] if t["setting"] == setting and t["form"] == "dual"]
        path = root / "comparisons" / f"{setting}.jpg"
        comparison(tasks, records, root, path)
        galleries.append((setting, tasks, path))
    for form in ("single", "coordinates"):
        tasks = [t for t in plan["tasks"] if t["form"] == form]
        path = root / "comparisons" / f"S3-mask-{form}.jpg"
        comparison(tasks, records, root, path)
        galleries.append((f"S3-mask / {form}", tasks, path))
    audit_code = (
        "https://github.com/huggingface/diffusers/blob/"
        + plan["diffusers_revision"]
        + "/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py"
    )
    report = f"""# 节点2 / Qwen-Image-Edit-2511 冒烟报告

**结论：{len(success)}/{len(records)}个预注册推理请求生成输出，失败{len(failures)}个。用户已取消逐模型暂停，当前结果汇入全模型报告。未运行Judge、dev选型或test。生成成功不等于编辑通过。**

|汇报项|结论|证据|
|---|---|---|
|做了什么|沿用已审核的3个dev case，主路径覆盖全部10个settings（S1只输入源图，其余为双图）；S3-mask补查单图和坐标文本。S2丢区域与S1输入完全相同的{len(aliases)}个请求复用S1结果，没有重复采样|plan.json、runs/*/call.json、aliases.json；下方直接嵌入输入/输出图|
|问题与偏差|目视发现标记残留、疑似目标关联错误和额外背景改动，详见下方具体样例；未因这些现象修改prompt、步数、seed或重新采样。本轮未发现需要临时改变协议的接口冲突|observations.json、下方输入/输出对照；summary.json及每请求result.json|
|阻塞项|本模型适用路径均完成；编辑质量与标记可读性需结合下面图像审核，不把连通性当正式分数|没有UnitPass/JointPass或候选排名|
|下一步|统一报告问题与推荐；之后按dev JointPass选型，冻结前仍等待确认|上级目录SUMMARY_REPORT.html、gate.json|

**推荐：保留双图基线，单图和坐标路径进入同预算dev比较。冒烟观察不代表编辑通过，也不冻结输入配置。**

## 固定调用与实测记录

|项目|实际记录|
|---|---|
|权重revision|`{plan["model_revision"]}`；{len(weights["files"])}个本地文件逐文件与HF缓存etag核验一致|
|Diffusers revision|`{plan["diffusers_revision"]}`；已安装pipeline源码hash与审计快照相同|
|步数/CFG/负面提示/seed|40 / true_cfg_scale=4 / 单个空格 / 42；每请求1张输出|
|guidance_scale说明|按官方示例传1；该非guidance-distilled骨干忽略此参数，实际CFG由true_cfg_scale控制，见[固定源码]({audit_code}#L777-L859)|
|实际去噪步数分布|`{summary["actual_denoising_steps"]}`（步数→请求数）|
|实际transformer调用分布|`{summary["actual_transformer_forward_calls"]}`（次数→请求数；含CFG正负两路）|
|实际文本编码器调用分布|`{summary["actual_text_encoder_forward_calls"]}`（次数→请求数）|
|附加组件调用|`{summary["extra_component_calls"]}`|
|观测峰值allocated显存|{summary["peak_gpu_allocated_bytes"] / 2**30:.3f} GiB；不是最低显存需求|
|pipeline wall总秒数|{summary["sum_pipeline_wall_seconds"]:.3f}；各单卡请求实测值求和|
|CUDA事件区间总秒数|{summary["sum_cuda_event_seconds"]:.3f}；含等待区间，不等于纯kernel执行时间|
|完成worker的wall总秒数|{summary["completed_worker_wall_seconds"]:.3f}；包括各worker模型载入到最后输出落盘，不作速度排名|
|原生输出尺寸集合|`{summary["raw_output_sizes"]}`；保留raw.png，再以LANCZOS缩放回各源图尺寸保存output.png|
|Judge/质量分数|未运行、未计算|
|完整性验证|[validation.json]({root / "validation.json"})：输入绑定、参数、seed、输出hash与源图尺寸、S2复用一致性均通过|

候选路径是连通性检查，不是dev选型：本次只固定展示这些输入下的输出，没有据此改prompt或挑选最佳图。每个实际请求只采样一次，S2复用项有逐字prompt和输入文件hash一致性证明。单图/坐标这里只展示S3-mask的同三张图，不声称其他settings的这两种候选均已端到端验证。坐标路径把mask确定性转为外接框，会丢失轮廓形状；这是已审定的有损候选，不能将其解释为完整mask的原生输入。

## 实际输入与输出

图中左列是干净源图，中列是标记输入（没有则注明），右列是缩放回源图大小的实际输出。单图候选的左列仅供对照，实际只输入中列。可点击查看大图；完整prompt和调用参数在各请求链接中。这里没有对输出做GT回贴。
"""
    observations_path = root / "observations.json"
    if observations_path.exists():
        observed = json.loads(observations_path.read_text())
        report += "\n## 本轮直接观察到的问题（不评分）\n\n"
        for item in observed["observations"]:
            report += f"- `{item['task_id']}`：{item['finding']} [图像证据]({item['image']})。{item['scope']}\n"
        report += "\n观察者为助手图像检查，不冒称独立人工审查；没有据此修改候选或重新采样。\n"
    extra_html = []
    for name, tasks, path in galleries:
        report += f"\n### {name}\n\n[![{name}：三个dev输入输出对照]({path})]({path})\n\n"
        for task in tasks:
            d = root / "runs" / task["id"]
            call = json.loads((d / "call.json").read_text())
            r = records[task["id"]]
            report += f"**{task['case_id']} · {task['form']}** — {r['status']}。 [原始输出]({d / 'raw.png'}) · [评测尺寸输出]({d / 'output.png'}) · [调用参数]({d / 'call.json'}) · [实际网络调用记录]({d / 'result.json'})\n\n```text\n{call['prompt']}\n```\n\n"
            if len(call["condition_preprocessor_images"]) > 1:
                condition = call["condition_preprocessor_images"][1]
                extra_html.append(
                    f'<details><summary>{html.escape(task["id"])}：pipeline给标记图的第一次条件缩放，{condition["size"]}；processor随后继续按patch对齐</summary><img src="{condition["path"]}"></details>'
                )
    report += "\n## 解释边界\n\n本报告不提供手填分数或模型排名。模型内部条件图比源图小，标签/轮廓的有效可见性需结合实际输出继续分析；记录的image_grid_thw来自真实文本编码器调用。`max_sequence_length=512`按原接口传入，但此固定版本的encode_prompt没有据此截断嵌入，不能据参数名声称只看到了512 token；真实input token长度已保存。官方内部模板未替换，最终共享prompt原样传入。\n\n所有材料位于/tmp/ifbench；experiments2中没有新增正式结果。\n"
    (root / "REPORT.md").write_text(report)
    from markdown_it import MarkdownIt

    rendered = MarkdownIt("commonmark", {"html": False}).enable("table").render(report)
    rendered += "<h2>实际条件图缩放诊断</h2>" + "".join(extra_html)
    for _, _, p in galleries:
        uri = "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()
        rendered = rendered.replace(f'src="{p}"', f'src="{uri}"')
    for task in plan["tasks"]:
        call = json.loads((root / "runs" / task["id"] / "call.json").read_text())
        for item in call["condition_preprocessor_images"]:
            p = Path(item["path"])
            uri = "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()
            rendered = rendered.replace(f'src="{p}"', f'src="{uri}"')
    style = "body{font:17px/1.65 system-ui,sans-serif;color:#172033;max-width:1750px;margin:32px auto;padding:20px}img{display:block;max-width:100%;height:auto;margin:20px auto}table{border-collapse:collapse;width:100%}td,th{border:1px solid #cbd5e1;padding:10px;text-align:left;vertical-align:top}th,pre{background:#f1f5f9}pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:18px}h3{margin-top:45px;border-top:2px solid #cbd5e1;padding-top:20px}a{color:#1d4ed8}"
    (root / "REPORT.html").write_text(
        '<!doctype html><html lang="zh"><meta charset="utf-8"><title>Qwen-2511 冒烟报告</title><style>'
        + style
        + "</style><body>"
        + rendered
        + "</body></html>"
    )
    # Rendering a report must not overwrite the user's recorded approval in gate.json.
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
