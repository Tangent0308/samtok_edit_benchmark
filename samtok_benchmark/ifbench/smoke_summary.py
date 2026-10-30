"""Consolidate measured smoke records and illustrated, provisional recommendations."""

import base64
from collections import Counter
import json
from pathlib import Path
import re

from markdown_it import MarkdownIt

from samtok_benchmark.io import write_json
from . import SETTINGS
from .smoke_suite import ROOT, SHARED, NAMES


MODELS = ["qwen2511", "qwen21", "flux3", "replan", "mirage", "mice", "maskflow"]
DISPLAY = {"qwen2511": "Qwen-Image-Edit-2511", **NAMES}
REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs/protocol/if-bench-v1"

# These are qualitative recommendations, never selected/frozen configurations.
RECOMMENDATIONS = {
    "qwen2511": (
        "保留原图+标记图作为基线；单标记图、坐标文本进入dev对照。40步 / true CFG4。",
        "双图仍有U标签/轮廓残留、跨目标编辑；当前没有足够证据直接选单图或坐标。",
    ),
    "qwen21": (
        "优先比较单标记图与原图+标记图；40步 / CFG1 / 1024 / PE关闭的受控主行。",
        "单图在衣袖样例减少明显标签，但K=5仍有轮廓残留；只能作为优先测试建议。PE推荐流程另报。",
    ),
    "flux3": (
        "原图+原生bbox作为首选适配；16步 / distilled / PUP关闭。标记副图保留为dev候选。",
        "无ref时有目标错绑。mask转框损失轮廓；加第二张图还改变官方预处理分辨率，不能把差异只归因于标记。",
    ),
    "replan": (
        "给定区域直接注入原生box；仅S1及S5缺区域单元启用专用planner。40步 / CFG4 / expand0 / switch0.5。",
        "原生planner可能把新增锚点框到其他对象；编辑器也有跨目标改动。预测框与给定框必须分别记录。",
    ),
    "mirage": (
        "原生box+显式10px padding；有ref时按已确认规则取公开原文短语，无ref用selected region。40步 / CFG4 / patch0.4。",
        "字段缺口已解决；无ref仍有颜色改到包等错绑。S1/S5缺区域维持原生Qwen3.5 planner，禁止私有标注补语义。",
    ),
    "mice": (
        "原生二值mask+$BREAKFLAG$局部指令；4步 / CFG1。S1用global-only；S5把无区域指令放global并保留全部局部单元。",
        "接口已跑通完整S5，但部分要求未落实、人物面部被额外改动。global+regions是适配扩展，不宣称官方已验证完整S5质量。",
    ),
    "maskflow": (
        "原生mask，U1…UK串行；50步 / text CFG4 / mask CFG1，保留原生融合。S1、S5保持N/A。",
        "point小mask会限制可编辑范围；add可能受锚点mask限制。不要用隐藏整对象mask扩大编辑区，也不要补骨干输出冒充本方法。",
    ),
}


def read(path):
    return json.loads(path.read_text())


def collect():
    stats = {}
    starts_report = {}
    for model in MODELS:
        root = ROOT / model
        plan = read(root / "plan.json")
        records = [read(root / "runs" / t["id"] / "result.json") for t in plan["tasks"]]
        assert read(root / "validation.json")["status"] == "passed", model
        main = [r for r in records if r["task"]["form"] in ("native", "dual")]
        alt = [r for r in records if r["task"]["form"] not in ("native", "dual")]
        planners = [read(p) for p in sorted((ROOT / "planners" / model).glob("*--*.json"))]
        assert all(p["status"] == "planned" for p in planners)
        starts = []
        for path in sorted(root.rglob("worker*.log")):
            for line in path.read_text(errors="replace").splitlines():
                if '"stage": "inference-start"' in line:
                    match = re.search(r'\{"id":.*?\}', line)
                    if match:
                        starts.append({"id": json.loads(match[0])["id"], "log": str(path)})
        counter = Counter(s["id"] for s in starts)
        duplicates = {k: v for k, v in counter.items() if v > 1}
        expected = {r["task"]["id"] for r in records if r["status"] == "generated"}
        assert not duplicates and set(counter) == expected, (model, duplicates)
        starts_report[model] = {"starts": starts, "duplicates": duplicates, "verified": True}
        aliases = read(root / "aliases.json")
        totals = [read(p) for p in sorted(root.rglob("worker*.total.json"))]
        stats[model] = {
            "main_statuses": dict(Counter(r["status"] for r in main)),
            "alternate_statuses": dict(Counter(r["status"] for r in alt)),
            "statuses": dict(Counter(r["status"] for r in records)),
            "settings": {
                s: dict(Counter(r["status"] for r in main if r["task"]["setting"] == s))
                for s in SETTINGS
            },
            "actual_diffusion_api_calls": sum(r["inference_api_calls"] for r in records),
            "transformer_forward_calls": sum(
                r.get("transformer_forward_calls", 0) for r in records
            ),
            "native_planner_api_calls": sum(p["extra_planner_calls"] for p in planners),
            "native_planner_request_wall_seconds": sum(p["wall_seconds"] for p in planners),
            "pipeline_wall_seconds": sum(r.get("pipeline_wall_seconds", 0) for r in records),
            "worker_wall_seconds_including_load": sum(t["worker_wall_seconds"] for t in totals),
            "worker_records": len(totals),
            "aliases": len(aliases),
            "peak_gpu_allocated_bytes": max(r.get("peak_gpu_allocated_bytes", 0) for r in records),
            "actual_raw_sizes": sorted(
                {tuple(r["raw_size"]) for r in records if r["status"] == "generated"}
            ),
            "validation": str(root / "validation.json"),
        }
    write_json(
        ROOT / "duplicate_check.json",
        {
            "scope": "All worker logs, including archived zero-inference protocol blockers; serial unit coverage checked by validate_suite.",
            "models": starts_report,
        },
    )
    write_json(
        ROOT / "SUMMARY.json", {"models": stats, "quality_scores_computed": False, "judge_calls": 0}
    )
    return stats


def generate():
    stats = collect()
    generated = sum(s["statuses"].get("generated", 0) for s in stats.values())
    main = sum(s["main_statuses"].get("generated", 0) for s in stats.values())
    na = sum(s["statuses"].get("not-applicable", 0) for s in stats.values())
    failed = sum(s["statuses"].get("failed", 0) for s in stats.values())
    api = sum(s["actual_diffusion_api_calls"] for s in stats.values())
    native = sum(s["native_planner_api_calls"] for s in stats.values())
    images = []
    md = "# IF-Bench：7个主表方法冒烟测试汇总\n\n"
    md += "**本轮完成全部主表方法的接口与行为测试。没有运行Judge、dev候选评分或test，也没有冻结模型输入方案。**\n\n"
    md += "|汇报项|结论|\n|---|---|\n"
    md += f"|做了什么|固定3个dev case、10个setting；生成{generated}张最终输出（主路径{main}、备选{generated - main}），{na}个N/A请求、{failed}个生成失败；实际扩散API调用{api}次，原生planner调用{native}次。|\n"
    md += "|发现的问题与偏差|标记残留、目标错绑、附带改动、区域范围限制均有具体样例；MIRAGE公开ref短语缺口按用户确认解决；环境/预处理差异见下表。|\n"
    md += "|阻塞项|本轮适用路径无未完成请求。MaskFlow的S1/S5按协议N/A。正式dev选型还需要候选清单、Judge及全dev公共短语预检查，当前没有质量分数可冻结。|\n"
    md += "|下一步计划|在每模型≤4个完整配置预算内做dev JointPass选择，保留S2丢区域对照；提交全部候选分数与推荐选择，等待冻结前确认，然后才进入test。|\n\n"
    md += "这里的“推荐setting”分两层：**所有模型继续保留协议的10个setting，主文重点仍是S1、S3-mask、S3-point、S5；下面推荐的是各模型如何接收这些输入。** 不因某模型在某个setting看起来更好就省略其余列。\n\n"
    md += "|模型|下一步最推荐的输入/配置|具体问题与推荐理由|\n|---|---|---|\n"
    for model in MODELS:
        recommendation, issue = RECOMMENDATIONS[model]
        md += f"|[{DISPLAY[model]}]({ROOT / model / 'REPORT.html'})|{recommendation}|{issue}|\n"
    md += "\n以上是工程与定性建议，**不是dev胜出结果**。现有3图不足以计算可信排名；不能据此声称哪个模型最好。S2丢区域与S1为相同完整输入路径时复用同一输出，不额外采样；MaskFlow不适用这条路径，记N/A。\n\n"
    md += "## 各setting实际完成状态\n\n3/3表示3个请求均生成，不表示3个编辑任务通过。这里只计主路径。\n\n"
    md += "|模型|" + "|".join(SETTINGS) + "|\n|---|" + "---|" * len(SETTINGS) + "\n"
    for model in MODELS:
        cells = []
        for setting in SETTINGS:
            counts = stats[model]["settings"][setting]
            cells.append(
                "N/A" if counts == {"not-applicable": 3} else f"{counts.get('generated', 0)}/3"
            )
        md += f"|{DISPLAY[model]}|" + "|".join(cells) + "|\n"
    md += "\n备选试跑：Qwen-2511的S3-mask单图/坐标各3图；Qwen2.1的S3-mask单图3图；FLUX.3的S3-mask原生框+标记副图3图。其余没有额外试跑候选。MIRAGE的selected-region有ref替代方案未运行。\n\n"
    md += "## 图片与问题（每模型固定同3个case）\n\n每组依次为源图、实际标记图或原生区域示意图、输出。**标为SCHEMATIC的彩框仅用于报告展示，没有作为额外图像输入模型。** 实际原生mask、最终prompt、JSON参数与逐单元记录在各模型报告内直接展示。\n\n"
    for model in MODELS:
        root = ROOT / model
        md += f"### {DISPLAY[model]}\n\n[全部10个setting、实际prompt和输入输出]({root / 'REPORT.html'}) · [Markdown]({root / 'REPORT.md'}) · [完整性检查]({root / 'validation.json'})\n\n"
        md += f"推荐：{RECOMMENDATIONS[model][0]}\n\n"
        p = root / "comparisons/S3-mask.jpg"
        images.append(p)
        md += f"![S3-mask三个固定样例]({p})\n\n"
        observations = read(root / "observations.json")
        # Qwen-2511 has a different historical schema; link its original full report.
        if isinstance(observations, dict) and "observations" in observations:
            for item in observations["observations"]:
                md += f"- `{item['task_id']}`：{item['finding']}\n"
            md += "\n"
        else:
            md += RECOMMENDATIONS[model][1] + "详见该模型完整报告的逐图观察。\n\n"
        if model in ("qwen21", "maskflow"):
            p = root / (
                "comparisons/alternative-S3-mask.jpg"
                if model == "qwen21"
                else "comparisons/S3-point.jpg"
            )
            images.append(p)
            md += f"![单图备选或点输入对照]({p})\n\n"
    md += "观察由助手查看图像完成，不冒称独立人工双人标注；未计算标记残留率、人工κ或paste-back诊断分数。\n\n"
    md += "## MIRAGE：已确认的字段修正\n\n"
    md += f"用户已确认“从公开指令确定性提取目标短语”。[确认记录]({ROOT / 'mirage_ref_policy.json'})与[9个单元的原文片段证据]({ROOT / 'PROPOSED_MIRAGE_REF_EXTRACTION.json'})一并保留；后者为确认前的历史提案，状态不覆盖确认记录。\n\n"
    md += "有ref且有给定区域时，只从当前公开instruction取连续原文片段；不读隐藏spec.ref。无ref仍用the selected region。S1及S5缺区域单元仍走原生planner。15个旧blocked-protocol记录未调用编辑模型，归档后补齐；之前成功输出没有重跑。当前固定样例均通过，但尚未证明这套有限语法覆盖全dev；无法明确提取的后续请求要待核，不能静默补词。\n\n"
    md += "## 配置偏差、可复现性与公平性边界\n\n|项目|实际执行、影响与后续处理|\n|---|---|\n"
    md += "|Qwen2.1 / FLUX.3|主受控路径关闭PE/PUP，符合已确认协议，但偏离官方推荐的完整增强流程；官方推荐流程尚未执行，需在同一4候选预算内另报。不能用本轮受控图宣称官方最佳性能。|\n"
    md += "|RePlan planner|缺少FlashAttention2，使用PyTorch SDPA；实际Transformers 5.19.0，与上游固定依赖不同。原生模板、专用权重和生成参数保留；没有验证逐位等价。原始及实际clamp后的框均留档。|\n"
    md += "|运行环境|全部编辑器使用Torch 2.8.0+cu128；FLUX.3上游依赖清单更高版本，当前环境已跑通但不称完全复现原环境。MaskFlow独立Python3.12，其余Python3.11。详细包版本及源码hash见各worker环境记录。|\n"
    md += "|FLUX.3多图|官方单图与多图参考预处理不同（单图最高约4MP，多图约1MP且对齐网格）；原生框+标记图候选改变的不止标记。最终prompt包括官方to_canvas追加文本，已保存。|\n"
    md += "|MICE|CLI默认配置中的use_masks=False属于数据加载开关；本适配器直接向pipeline传instance_masks_yx，实际接收的是mask。global+regions保留全部S5单元。上游调试图已移至临时目录；后续运行工作目录固定到临时目录。|\n"
    md += "|MaskFlow几何|保留官方bucket中心裁剪、膨胀/模糊和Poisson/pixel融合；每次串行输出先反裁剪回前一步完整画布，裁掉的边缘从前一步输入恢复，不使用GT mask回贴。native.png与恢复画布分别保存。|\n"
    md += "|MIRAGE区域文本|有ref给定区域使用已确认的连续原文短语；保留公开编辑指令。原生planner产生的指令保持其返回文本，句末标点以保存的sub_prompts为准。不能将adapter适配说成官方脚本逐字输出。|\n"
    md += "|权重|固定本地权重与来源revision；Qwen2.1本地b3179ad与审计d26bb61的权重/配置metadata hash一致，文档有差异。Qwen2511完成全文件hash核验；本报告不将其他权重的metadata检查冒称全文件内容重验。|\n"
    md += "|标记与补充行|本轮没有SAM、外置定位器或caption改写；原生planner单列调用。†/‡/§补充评测和GT selector paste-back诊断尚未执行。|\n\n"
    md += f"源码/权重固定版本：[来源索引]({DOCS / 'SOURCE_INDEX.md'})。实际调用与输入绑定：[机器汇总]({ROOT / 'SUMMARY.json'})、[无重复请求核对]({ROOT / 'duplicate_check.json'})。共享split/分配：[审核包]({SHARED / 'index.html'})。\n\n"
    md += f"[本机实际权重来源记录]({ROOT / 'weight_provenance.json'}) · [源码快照与hash]({ROOT / 'source_snapshot.json'}) · [Python3.11实际依赖]({ROOT / 'environment_clean311.json'}) · [MaskFlow实际依赖]({ROOT / 'environment_maskflow312.json'})。MIRAGE planner使用本机Qwen3.5-9B下载记录中的revision `c202236235762e1c871ad0ccb60c8ee5ba337b9a`，不是根据当前远程HEAD推定。\n\n"
    md += "## 实测资源与调用（包含冒烟备选）\n\n"
    md += "|模型|主路径输出|备选输出|扩散API调用|原生planner调用|Transformer forward|请求wall秒之和|峰值allocated GiB|\n|---|---:|---:|---:|---:|---:|---:|---:|\n"
    for model, s in stats.items():
        md += f"|{DISPLAY[model]}|{s['main_statuses'].get('generated', 0)}|{s['alternate_statuses'].get('generated', 0)}|{s['actual_diffusion_api_calls']}|{s['native_planner_api_calls']}|{s['transformer_forward_calls']}|{s['pipeline_wall_seconds']:.2f}|{s['peak_gpu_allocated_bytes'] / 2**30:.2f}|\n"
    md += "\n计时来自实际记录；并发任务的wall相加不是实际历时，也不是纯GPU kernel时长，不用于速度排名。worker占用时长（含加载）及planner请求时长另存SUMMARY.json；planner加载时间未采集，完整GPU时长不能补估。RePlan/MIRAGE规划输出在相同请求路径间缓存，未把复用当新增调用。MaskFlow每张输出K次API，Qwen/MIRAGE的CFG及区域分支反映在forward次数中。\n\n"
    md += "## 后续工作边界\n\n本轮仅完成主表7方法冒烟。可选FLUX.2 klein-9B、QwenImageEditInpaintPipeline未进入本批测试；附录仍按约定在主表正式评测完成后做。UnitPass / JointPass、95%CI、派生指标、K=2…5分桶、消融和每模型×setting随机10图人工材料均尚未生成，不能从这3张冒烟图推算。\n\n"
    md += "所有测试图、日志、报告均在/tmp/ifbench/。experiments2/IF-Bench保持空目录；下一节点是dev选型与冻结前汇报。\n"
    (ROOT / "SUMMARY_REPORT.md").write_text(md)
    body = MarkdownIt("commonmark", {"html": True}).enable("table").render(md)
    for p in images:
        uri = "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()
        body = body.replace(f'src="{p}"', f'src="{uri}"')
    style = "body{font:17px/1.65 system-ui;max-width:1800px;margin:auto;padding:25px;color:#172033}img{max-width:100%}table{border-collapse:collapse}td,th{border:1px solid #cbd5e1;padding:9px}pre{white-space:pre-wrap}a{color:#1d4ed8}h2{margin-top:40px}"
    (ROOT / "SUMMARY_REPORT.html").write_text(
        f'<!doctype html><html lang="zh"><meta charset="utf-8"><title>IF-Bench smoke summary</title><style>{style}</style><body>{body}</body></html>'
    )
    print(
        json.dumps(
            {
                "generated": generated,
                "main": main,
                "not_applicable": na,
                "failed": failed,
                "diffusion_api_calls": api,
                "planner_calls": native,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    generate()
