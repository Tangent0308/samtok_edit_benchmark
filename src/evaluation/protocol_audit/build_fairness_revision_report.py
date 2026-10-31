"""Read-only CPU consolidation of the fixed IF-Bench fairness revision.

The only writes are FINAL_EVALUATION_METHODS.md/json under the audit directory.
Run again to refresh runtime completion; no runners, requests, outputs or scores
are edited, and no model/Judge is loaded or called.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from PIL import Image


BASE = Path("/tmp/ifbench/fairness_v2_20261030")
REPO = Path("/opt/tiger/tanyue/if-bench")
SHARED = Path("/tmp/ifbench/tiered_v1/shared_inputs_20261027")
OLD = Path("/tmp/ifbench/tiered_v1/dev_selection")
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
MODELS = ["qwen2511", "qwen21", "flux3", "replan", "mirage", "mice", "flux2_klein_9b"]
NAMES = {
    "qwen2511": "Qwen-Image-Edit-2511",
    "qwen21": "Qwen-Image-2.1",
    "flux3": "FLUX.3 Klein distilled（PUP off）",
    "replan": "RePlan（Qwen-2511 骨干）",
    "mirage": "MIRAGE（Qwen-2511 骨干）",
    "mice": "MICE（Klein-4B 骨干）",
    "flux2_klein_9b": "FLUX.2 Klein-9B distilled",
}
DIFFUSERS = "06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a"
SNAPSHOTS = {}
HASH_CACHE = {}


def read(path, optional=False):
    path = Path(path)
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (FileNotFoundError, json.JSONDecodeError):
        if optional:
            return None
        raise
    SNAPSHOTS[str(path)] = hashlib.sha256(raw).hexdigest()
    return value


def sha(path):
    path = Path(path)
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key not in HASH_CACHE:
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                h.update(block)
        HASH_CACHE[key] = h.hexdigest()
    return HASH_CACHE[key]


def link(path, label=None):
    path = Path(path)
    target = str(path.relative_to(BASE)) if path.is_relative_to(BASE) else str(path)
    return f"[{label or path.name}]({target})"


def model_root(model):
    if model in ["flux3", "replan"]:
        return BASE / "flux3_replan" / model
    return BASE / "mirage_mice/probe" / model


def settings_specs(qwen, other, mm):
    result = {}
    for model in ["qwen2511", "qwen21", "flux2_klein_9b"]:
        result[model] = [
            {k: row[k] for k in ["setting", "input", "fairness_caveat"]}
            for row in qwen["models"][model]["settings"]
        ]
    result["flux3"] = [
        {**row, "input": row["input"] + "；boxes=None、PUP off"} for row in result["qwen2511"]
    ]
    result["replan"] = []
    for row in result["qwen2511"]:
        s = row["setting"]
        text = (
            "全部 ref"
            if s == "S1"
            else (
                "no-ref"
                if s.startswith("S3") or s == "S4-noref"
                else "冻结逐单元混合文本"
                if s == "S5"
                else "ref"
            )
        )
        image = "清图 I" if s == "S1" else "同一公开标注图 A"
        result["replan"].append(
            {
                "setting": s,
                "input": f"原生 planner：{image}＋{text}；原生 editor：清图 I＋原样 response",
                "fairness_caveat": "不手改原生计划；公开标注与清图同坐标；不另造点框或隐藏对象名",
            }
        )
    for model in ["mirage", "mice"]:
        result[model] = [
            {
                "setting": row["setting"],
                "input": row["input"],
                "fairness_caveat": (
                    "完整方法自身 parser/locator 决定区域；不补公开信息之外的目标；联合编辑"
                    if model == "mirage"
                    else "单参考图；point/none 走 global，box/mask 走原生 binding；不修原生 attention"
                ),
            }
            for row in mm["models"][model]
        ]
    assert all({x["setting"] for x in result[m]} == set(SETTINGS) for m in MODELS)
    return result


def specifications(qwen, other, mm):
    specs = {}
    for model in ["qwen2511", "qwen21", "flux2_klein_9b"]:
        source = qwen["models"][model]
        specs[model] = {
            "name": NAMES[model],
            "parameters": source["parameters"],
            "seed": source["seed"],
            "components": source["components"],
            "weight_revision": source["weight_revision"],
            "pipeline_revision": source["pipeline_revision"],
            "method_commit": source["pipeline_revision"],
            "repository": "https://github.com/huggingface/diffusers",
            "evidence": str(BASE / "qwen_flux2/FINAL_METHODS.md"),
        }
    specs["qwen21"]["method_commit"] = "ab96caa944157ca28a4f36b695c3047549f48f98"
    specs["qwen21"]["repository"] = "https://github.com/QwenLM/Qwen-Image-2.1"
    specs["qwen21"]["equivalent_weight_metadata_revision"] = qwen["models"]["qwen21"][
        "equivalent_weight_metadata_revision"
    ]
    specs["flux2_klein_9b"]["method_commit"] = "50fe5162777813d869182b139e83b10743caef15"
    specs["flux2_klein_9b"]["repository"] = "https://github.com/black-forest-labs/flux2"
    for model in ["flux3", "replan"]:
        source = other["models"][model]
        specs[model] = {
            "name": NAMES[model],
            "parameters": source["parameters"],
            "seed": 42,
            "components": source["native_components"],
            "weight_revision": source["weight_revision"],
            "method_commit": source["commit"],
            "repository": source["repository"],
            "evidence": str(BASE / "FLUX3_REPLAN_FAIRNESS_REVIEW.md"),
        }
        if "planner_weight_revision" in source:
            specs[model]["planner_weight_revision"] = source["planner_weight_revision"]
    for model in ["mirage", "mice"]:
        src = mm["sources"][model]
        request = read(model_root(model) / "requests/S1" / CASES[0] / "request.json")
        specs[model] = {
            "name": NAMES[model],
            "parameters": request["parameters"],
            "seed": 42,
            "method_commit": src["pinned_commit"],
            "repository": "https://github.com/" + src["repo"],
            "evidence": str(BASE / "mirage_mice/MIRAGE_MICE_FAIRNESS_REVIEW.md"),
        }
    specs["mirage"].update(
        weight_revision="6f3ccc0b56e431dc6a0c2b2039706d7d26f22cb9",
        planner_weight_revision="c202236235762e1c871ad0ccb60c8ee5ba337b9a",
        components=[
            "official Qwen3.5-9B parser and locator",
            "Qwen-Image-Edit-2511",
            "MIRAGE joint local/global denoising",
        ],
        planner_defaults={
            "thinking": False,
            "do_sample": False,
            "parse_max_new_tokens": 512,
            "grounding_max_new_tokens": 128,
        },
        negative_prompt=" ",
    )
    specs["mice"].update(
        weight_revision="e7b7dc27f91deacad38e78976d1f2b499d76a294",
        components=[
            "FLUX.2 Klein-4B distilled and native text encoder/VAE",
            "MICE instance attention binding",
        ],
        attention_defaults={
            "prompt_settings": "outer_local_prompts",
            "attention_setting": "apitasmkernelnonlap",
            "strict": False,
            "kernel_size": 11,
            "temperature": 3.0,
            "sigma_scale": 0.6,
            "masking_steps": [0, 1, 2, 3],
        },
    )
    return specs


def check(condition, errors, label):
    if not condition:
        errors.append(label)


def previous_reuse(result, errors):
    evidence = result.get("reuse_evidence", {})
    for path_key, hash_key in [
        ("previous_call", "previous_call_sha256"),
        ("previous_result", "previous_result_sha256"),
        ("previous_planner_record", "previous_planner_sha256"),
    ]:
        if path_key in evidence:
            check(
                Path(evidence[path_key]).is_file()
                and sha(evidence[path_key]) == evidence[hash_key],
                errors,
                f"reuse {path_key} SHA",
            )
    return evidence


def collect_requests(qwen_audit, prepared):
    selected = {(r["model"], r["setting"], r["case_id"]): r for r in qwen_audit["selected"]}
    flux2 = {(r["setting"], r["case_id"]): r for r in prepared}
    plans = {m: read(model_root(m) / "plan.json") for m in ["flux3", "replan", "mirage", "mice"]}
    tasks = {m: {(t["setting"], t["case_id"]): t for t in p["tasks"]} for m, p in plans.items()}
    expected_keys = {(s, c) for s in SETTINGS for c in CASES}
    assert set(flux2) == expected_keys and all(set(v) == expected_keys for v in tasks.values())
    rows = []
    for model in MODELS:
        for setting in SETTINGS:
            for case in CASES:
                public_path = SHARED / "requests" / setting / case / "public.json"
                public = read(public_path)
                errors = []
                check(
                    sha(public["source"]["path"]) == public["source"]["sha256"],
                    errors,
                    "source SHA",
                )
                if model in ["qwen2511", "qwen21"]:
                    old = selected[model, setting, case]
                    request_path = Path(old["call"])
                    request = read(request_path)
                    result_path = Path(old["result"])
                    directory = result_path.parent
                    reused = True
                    form = read(public_path.with_name("inputs.json"))["forms"]["dual"]
                    check(
                        request["images"] == form["images"] and request["prompt"] == form["prompt"],
                        errors,
                        "historical Qwen dual binding",
                    )
                    check(
                        old["public_digest"] == public["input_digest"],
                        errors,
                        "historical public digest",
                    )
                elif model == "flux2_klein_9b":
                    request = flux2[setting, case]
                    request_path = BASE / "qwen_flux2/FLUX2_PREPARED_REQUESTS.json"
                    directory = BASE / "flux2_smoke" / setting / case
                    result_path = directory / "result.json"
                    reused = False
                else:
                    task = tasks[model][setting, case]
                    request_path = Path(task.get("call", task.get("request")))
                    request = read(request_path)
                    directory = model_root(model) / "outputs" / setting / case
                    result_path = directory / "result.json"
                    reused = False
                    digest_key = "call_digest" if model in ["flux3", "replan"] else "request_digest"
                    check(request[digest_key] == task[digest_key], errors, "prepared task digest")
                result = read(result_path, optional=True)
                call_path = directory / "call.json"
                call = read(call_path, optional=True)
                started_path = directory / "started.json"
                entry = {
                    "model": model,
                    "setting": setting,
                    "case_id": case,
                    "K": len(public["units"]),
                    "public_input": str(public_path),
                    "public_digest": public["input_digest"],
                    "request_path": str(request_path),
                    "request_sha256": SNAPSHOTS[str(request_path)],
                    "actual_call_path": str(call_path) if call is not None else None,
                    "result_path": str(result_path),
                    "runtime_status": result["status"] if result else "pending",
                    "started_without_terminal_result": started_path.exists() and result is None,
                    "reused": reused,
                    "new_editor_api_calls_terminal_recorded": 0,
                    "output_verified": False,
                    "input_audit_errors": errors,
                    "parameters": request.get("parameters", {}),
                    "seed": request.get("seed"),
                }
                check(request.get("seed") == 42, errors, "fixed seed")
                if model not in ["qwen2511", "qwen21"]:
                    digest = request.get("public_digest", request.get("public_input_digest"))
                    check(digest == public["input_digest"], errors, "public input digest")
                if call and model == "flux2_klein_9b":
                    for k in [
                        "images",
                        "prompt",
                        "parameters",
                        "seed",
                        "weight_revision",
                        "public_digest",
                    ]:
                        check(call.get(k) == request.get(k), errors, "actual call " + k)
                    check(
                        all(v == 0 for v in call["extra_component_calls"].values()),
                        errors,
                        "extra components disabled",
                    )
                elif call and model in ["flux3", "replan"]:
                    check(call == request, errors, "actual call equals prepared request")
                for path, digest in zip(
                    request.get("images", []), call.get("images_sha256", []) if call else []
                ):
                    check(sha(path) == digest, errors, "input image SHA")
                if result is not None:
                    entry["result_sha256"] = SNAPSHOTS[str(result_path)]
                    if model in ["flux3", "replan", "mirage", "mice"]:
                        key = "call_digest" if model in ["flux3", "replan"] else "request_digest"
                        check(result.get(key) == request[key], errors, "terminal request digest")
                        check(
                            result.get("plan_digest") == plans[model]["digest"],
                            errors,
                            "terminal plan digest",
                        )
                    if model in ["flux3", "replan"]:
                        entry["reused"] = bool(result.get("reused", False))
                        if entry["reused"]:
                            check(setting == "S1", errors, "reuse only exact S1")
                            entry["reuse_evidence"] = previous_reuse(result, errors)
                    entry["new_editor_api_calls_terminal_recorded"] = (
                        0
                        if model in ["qwen2511", "qwen21"]
                        else result.get("inference_api_calls", 0)
                    )
                    entry["transformer_forward_calls"] = result.get("transformer_forward_calls")
                    entry["wall_seconds"] = (
                        None
                        if entry["reused"]
                        else result.get("wall_seconds", result.get("seconds"))
                    )
                    entry["native_component_calls"] = result.get(
                        "actual_component_calls",
                        call.get("extra_component_calls") if call else None,
                    )
                    if result["status"] == "generated":
                        output = Path(result["output_image"])
                        check(output.is_file(), errors, "output file exists")
                        if output.is_file():
                            check(sha(output) == result["output_sha256"], errors, "output SHA")
                            with Image.open(output) as image:
                                check(
                                    list(image.size) == public["source"]["size"],
                                    errors,
                                    "output source dimensions",
                                )
                        entry.update(
                            output_image=str(output),
                            output_sha256=result["output_sha256"],
                            raw_size=result.get("raw_size"),
                            output_verified=not errors,
                        )
                    else:
                        entry["failure"] = {
                            k: result[k]
                            for k in ["error", "error_type", "traceback"]
                            if k in result
                        }
                entry["final_prompt"] = (call or request).get(
                    "prompt", request.get("global_original_prompt")
                )
                if model == "mirage":
                    entry["planner_public_inputs"] = {
                        "parser_inputs": request["parser_inputs"],
                        "grounding_image": request["grounding_image"],
                        "grounding_hints": request["grounding_hints"],
                    }
                    entry["actual_local_prompts"] = call.get("sub_prompts") if call else None
                if model == "mice":
                    entry["actual_local_regions"] = call.get("regions") if call else None
                    entry["actual_global_unit_ids"] = call.get("global_unit_ids") if call else None
                if model == "replan" and result:
                    native = result.get("native_result", {})
                    entry["actual_global_prompt"] = native.get(
                        "global_prompt", result.get("actual_global_prompt")
                    )
                    entry["actual_region_guidance"] = native.get(
                        "region_guidance", result.get("actual_region_guidance")
                    )
                rows.append(entry)
    assert len(rows) == 140
    return rows, plans


def collect_planners(plans):
    rows = []
    for model in ["replan", "mirage"]:
        for setting in SETTINGS:
            for case in CASES:
                path = model_root(model) / "planners" / setting / case / "result.json"
                result = read(path, optional=True)
                entry = {
                    "model": model,
                    "setting": setting,
                    "case_id": case,
                    "path": str(path),
                    "status": result["status"] if result else "pending",
                    "new_api_calls": 0,
                    "reused_api_calls": 0,
                    "batch_items": 0,
                    "returned_pairs": 0,
                    "audit_errors": [],
                }
                if result:
                    entry["sha256"] = SNAPSHOTS[str(path)]
                    check(
                        result.get("plan_digest") == plans[model]["digest"],
                        entry["audit_errors"],
                        "planner plan digest",
                    )
                    if model == "replan":
                        entry["new_api_calls"] = result.get("native_planner_calls", 0)
                        entry["reused_api_calls"] = result.get("reused_native_planner_calls", 0)
                        entry["reused"] = bool(result.get("reused"))
                        if entry["reused"]:
                            previous_reuse(result, entry["audit_errors"])
                    else:
                        entry["new_api_calls"] = result.get("extra_planner_api_calls", 0)
                        entry["batch_items"] = result.get("extra_planner_batch_items", 0)
                        entry["returned_pairs"] = sum(
                            len(v) for v in result.get("parser_pairs_by_unit", {}).values()
                        )
                    entry["wall_seconds"] = result.get("wall_seconds")
                rows.append(entry)
    return rows


def gallery_info(model):
    if model in ["qwen2511", "qwen21", "flux2_klein_9b"]:
        short = "flux2" if model == "flux2_klein_9b" else model
        report = BASE / "qwen_flux2" / f"{short}_EXAMPLES.md"
        figure = BASE / "qwen_flux2/figures" / f"{model}__S3-point.jpg"
    elif model in ["flux3", "replan"]:
        report = BASE / "flux3_replan/POST_VALIDATION.md"
        figure = BASE / "flux3_replan/figures" / f"{model}__S3-point__{CASES[0]}.jpg"
    else:
        report = BASE / "mirage_mice" / f"POST_VALIDATION_{model}.md"
        figure = BASE / "mirage_mice/figures" / model / f"S3-point__{CASES[0]}.jpg"
    return {
        "report": str(report),
        "report_exists": report.exists(),
        "figure": str(figure),
        "figure_exists": figure.exists(),
        "fixed_figure_selection": "S3-point, first fixed case; Qwen/Flux2 existing two-row figures include both fixed cases",
    }


def post_review_state():
    paths = [
        BASE / "qwen_flux2/POST_VALIDATION.json",
        BASE / "flux3_replan/POST_VALIDATION.json",
        BASE / "mirage_mice/POST_VALIDATION_mirage.json",
        BASE / "mirage_mice/POST_VALIDATION_mice.json",
    ]
    result = {}
    for path in paths:
        content = read(path, optional=True)
        result[str(path)] = {"exists": content is not None}
        if content is not None:
            result[str(path)].update(
                sha256=SNAPSHOTS[str(path)],
                updated_at=content.get(
                    "updated_at_utc", content.get("generated_at_utc", content.get("created_utc"))
                ),
            )
            if "complete" in content:
                result[str(path)]["complete"] = content["complete"]
            if "summaries" in content:
                result[str(path)]["summaries"] = content["summaries"]
    return result


CHANGES = {
    "qwen2511": (
        "旧 dev-JP 推荐 single",
        "本轮固定 dual；S1 仍清图",
        "保留原图像素并统一区域呈现；single 仍合规，不将低分当作公平证据",
    ),
    "qwen21": (
        "旧 dev-JP 推荐 single；另有 PE 历史行",
        "固定 dual、PE 关；1024 级保持不变",
        "同一呈现规则；不增加独立 PE，不因潜在提分改 2K",
    ),
    "flux3": (
        "旧 native-annotation 仍把选择器写入 src/tgt 框表",
        "清图＋标注图，boxes=None、PUP 关",
        "源点/框/mask 不是预期输出对象布局；不用外部模型猜输出范围",
    ),
    "replan": (
        "区域 setting 有手工区域注入及局部任务重复 global",
        "全部走原生 planner；A 规划、I 编辑；response 原样传递",
        "保留完整方法的原生全局/局部分工，不手写更强的计划或固定点框",
    ),
    "mirage": (
        "区域直接注入；点变小框；局部文本未完整走 parser",
        "逐 unit 原生 parse，保留全部 pair；公开 hint 追加到原生定位；清图联合编辑",
        "区域范围由命名方法自己推理；不将点伪装成对象范围，不以 pair=K 修剪结果",
    ),
    "mice": (
        "点曾栅格化为局部编辑范围；框用源图 raster→nearest",
        "point/none 走单图/global；box/mask 原生绑定；框使用原生 floor/ceil",
        "不发明点范围；保持官方量化和 attention；双图原生越界故不改算法补能力",
    ),
    "flux2_klein_9b": (
        "此前可选模型，尚无这套输入的结果",
        "纳入 9B 蒸馏版，固定 dual，4 步/CFG1",
        "使用已授权固定权重；不替换为 4B/base，不加改写或定位组件",
    ),
}

PARAMETER_TEXT = {
    "qwen2511": '40 步；true CFG 4；guidance 1；negative=" "；max length 512',
    "qwen21": "40 步；true CFG 1；output_resolution=1024；KV cache 开；PE 关",
    "flux3": "distilled；16 步；无 CFG；PUP 关；boxes=None；safety=False（默认）",
    "replan": '40 步；true CFG 4；guidance 1；negative=" "；expand=0；switch=.5；planner 2048 tokens',
    "mirage": '40 步；true CFG 4；patch=.4；padding=10；negative=" "；native Qwen3.5 thinking 关/greedy，parse512、ground128',
    "mice": "4 步；guidance 1；outer_local_prompts；apitasmkernelnonlap；strict=False；kernel11/temp3/sigma.6；4 步均绑定",
    "flux2_klein_9b": "9B distilled；4 步；guidance 1；max length 512",
}

COMPONENT_TEXT = {
    "qwen2511": "checkpoint 内 Qwen2.5-VL 图文编码器、DiT、VAE、scheduler；无独立 planner",
    "qwen21": "checkpoint 内 Qwen3-VL 图文编码器、DiT、VAE、scheduler；独立 PE 关闭",
    "flux3": "原生文本编码器、DiT、VAE、scheduler；PUP 关闭",
    "replan": "官方 RePlan-Qwen2.5-VL-7B planner＋Qwen-2511 编辑器＋RePlan 区域 attention",
    "mirage": "官方 Qwen3.5-9B parser/locator＋Qwen-2511＋MIRAGE 局部/全局联合去噪",
    "mice": "Klein-4B 原生文本编码器/DiT/VAE＋MICE 实例 attention binding；不新增定位模型",
    "flux2_klein_9b": "checkpoint 内 Qwen3-8B 文本编码器、9B DiT、VAE、scheduler；无额外 VLM",
}

LIMITATIONS = {
    "qwen2511": "固定 S3-point 实图可见 U 标签/点残留和袖型目标错位。图文多图接口支持区域提示，不保证理解或去标成功。",
    "qwen21": "固定 S5 实图可见红点残留。1024 是固定 pipeline 默认；README 的 2048 级建议与本轮配置区别已披露，没有追加分辨率搜索。",
    "flux3": "标记可能进入输出。PUP-off 明确偏离官方增强器强推荐，属于当前裸编辑模型定义；不把关闭增强器的成绩冒称含 PUP 系统成绩。",
    "replan": "原生 planner 有把 U 标签附近小框当作任务区域、或绑定到错误对象的现象。保留原始 response，不放大 bbox、不改 hint、不重试。",
    "mirage": "原生定位仍可能把范围放错；公开标记并不保证自身 locator 正确。parser 逐 unit 批处理、grounding 追加固定公开 hint 是明确的输入编排变化，不能称官方 prompt 完全未改。",
    "mice": "官方 attention 在双参考图路径出现索引越界，保持单图。S1/纯 point 是零实例的 global 路径；mixed setting 保留原生 global/local 注意力限制，不将其伪装成所有目标均有局部绑定。",
    "flux2_klein_9b": "实际输出可见点/框/轮廓/U 标签残留，no-ref 样例可见目标混淆；20/20 出图不代表任务正确。保持固定方案，不按这些现象再调 prompt。",
}


def render(report):
    stats = report["summary"]
    complete = stats["all_140_outputs_verified"]
    state = (
        "140 个逻辑请求的输出均已生成并通过绑定核验"
        if complete
        else f"当前 {stats['generated']}/140 已出图，{stats['pending']} 项尚未终态"
    )
    md = [
        "# IF-Bench：公平性修订后的评测方式与固定样例验证",
        "",
        f"更新时间：{report['generated_at_utc']}。**{state}。本轮没有 Judge，不报告或推测 UnitPass / JointPass，也不从两张图估计总体标记残留率。**",
        "",
        "本轮固定的是每模型如何接收同一份公开信息、使用哪些原生组件，以及如何保留失败。不是把各模型调到最高分。用户已明确批准：每模型一套协议修订方案、同两张 dev 图 × 十个 setting、不按分数搜索，保留旧候选预算和计算记录。此前按 dev JointPass 搜索选型的口径在本轮被这项明确授权的固定规则取代；旧结果仍保留，不能给新输入套用旧分数。正式 freeze/test 尚未获准。",
        "",
        "授权凭据："
        + link(BASE / "AUTHORIZATION.json")
        + "。固定案例为 `v2-sa_10063996`（K=2）和 `v2-sa_7414116`（K=5，S5 含无区域单元），来自原 smoke 第 1、3 例，未按输出挑选。",
        "",
        "阅读全部图片与实际 prompt："
        + link(BASE / "ALL_MODELS_ALL_SETTINGS_GALLERY.md", "七模型全部 setting 图册")
        + "；"
        + link(BASE / "ALL_MODELS_ALL_SETTINGS_GALLERY.zip", "离线 Markdown＋图片包")
        + "。接口、范围和执行门的独立复核："
        + link(BASE / "qwen_flux2/FINAL_PROTOCOL_INDEPENDENT_REVIEW.md", "复核报告")
        + "。",
        "",
        "## 已完成的工作与当前状态",
        "",
        "| 模型 | 逻辑请求 | 已出图 | 失败 | 未终态 | 旧输出复用 | 本轮新编辑调用（已落盘） | 原生规划调用（新 / 复用） |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        s = report["models"][model]["runtime"]
        p = report["models"][model]["planner_summary"]
        md.append(
            f"| {NAMES[model]} | {s['expected']} | {s['generated']} | {s['failed']} | {s['pending']} | {s['reused']} | {s['new_editor_api_calls_terminal_recorded']} | {p['new_api_calls']} / {p['reused_api_calls']} |"
        )
    md += [
        "",
        f"总范围是 140 个逻辑请求。当前从记录核得旧输出复用 {stats['reused']} 个，新编辑调用已落盘 {stats['new_editor_api_calls_terminal_recorded']} 次；{stats['started_without_terminal_result']} 个编辑请求已经 started、尚无终态，不把它们当作成功或补写调用完成数。设计预期为 44 个精确旧复用、96 个新编辑，实际完成量始终按记录统计。",
        "",
        "MIRAGE 的成本按完整方法另列："
        + f"{report['models']['mirage']['planner_summary']['terminal']} 份规划终态，{report['models']['mirage']['planner_summary']['new_api_calls']} 次原生 API、{report['models']['mirage']['planner_summary']['batch_items']} 个 batch item，返回 {report['models']['mirage']['planner_summary']['returned_pairs']} 个 pair。batch item 是同一 API 批内项目，不能当作额外的独立 API。RePlan 新规划与旧 S1 规划分别计数，不与编辑阶段重复相加。",
        "",
        "报告生成器逐条读取当前 result、检查请求 digest/源图与输出 SHA/回源尺寸，复用记录还检查原 call/result 的 SHA；不是沿用早期 CPU 报告的 pending 文字或计划完成数。"
        + link(BASE / "FINAL_EVALUATION_METHODS.json", "逐请求绑定、检查和组件记录")
        + " 保存本次读取快照。出图成功不等于任务成功。",
        "",
        "## 共同执行规则",
        "",
        "同 setting 只提供同一公开源图、该 setting 的原指令和区域；允许编号、画点/框/完整轮廓、原生坐标/网格格式转换。point 不变成猜测的物体 mask；源选择器不冒充编辑后对象框。S4/S5 混合分配共用，S3/S4-noref 不补对象名、不丢区域；S5 的 none 单元保留。",
        "",
        "主比较不接外部 SAM、额外 grounder、caption 改写、PE 或 PUP。RePlan/MIRAGE 的原生 VLM 属于被评测命名方法的组成，明确列出版本和调用成本，不能称为裸 Qwen 骨干。所有编辑 seed=42、每请求一次采样；不按输出重试或选优。原生规划出现错位、漏项或额外拆分时照实记录，不人工修计划。所有输出回源图尺寸；以后 Judge 如获授权，仍只看 canonical ref 与 GT mask，不看模型输入形式。",
        "",
        "当前没有新增 N/A，也没有删除低分或失败行。MaskFlow 仍按此前用户指令暂不评测；本轮没有将串行适配重新加入。旧外部增强结果只保留历史，不纳入新公平主比较。GT selector paste-back 若后续执行，只称诊断，不称上界。",
        "",
        "## 各模型 × 各 setting 的完整输入",
        "",
        "`I` 表示清洁原图，`A` 表示同画布的共享标注副本。ref/no-ref、混合模态及缺区域状态由公开请求决定。表内两份“实际请求”链接固定对应 K=2、K=5；最终生成 prompt、原生 planner 结果及 local/global 文本另存于逐请求 JSON 和每模型图册。",
        "",
    ]
    for model in MODELS:
        m = report["models"][model]
        md += [
            f"### {NAMES[model]}",
            "",
            "| Setting | 固定输入与原生处理 | 当前两例状态 | 实际请求 |",
            "|---|---|---|---|",
        ]
        for s in m["settings"]:
            rows = [r for r in m["requests"] if r["setting"] == s["setting"]]
            labels = [
                "已出图"
                if r["runtime_status"] == "generated"
                else "失败"
                if r["runtime_status"] == "failed"
                else "未终态"
                for r in rows
            ]
            links = " / ".join(
                link(r["actual_call_path"] or r["request_path"], f"K={r['K']}") for r in rows
            )
            md.append(f"| {s['setting']} | {s['input']} | {' / '.join(labels)} | {links} |")
        md += ["", f"**保留的限制：** {LIMITATIONS[model]}", ""]
        g = m["gallery"]
        if g["figure_exists"]:
            target = Path(g["figure"]).relative_to(BASE)
            md += [f"![{NAMES[model]}，固定 S3-point 输入输出对照]({target})", ""]
        else:
            md += [
                "固定 S3-point 对照图尚未就绪；保留该预先固定案例，待真实输出与图册完成后刷新。",
                "",
            ]
        if g["report_exists"]:
            md += [
                link(g["report"], "全部十个 setting × 两例的实图、最终 prompt 与结果链接") + "。",
                "",
            ]
        else:
            md += ["全量图册尚待模型终态后生成；当前请求/结果已在逐请求 JSON 逐一列出。", ""]
    md += [
        "## 参数、原生组件与固定版本",
        "",
        "所有参数由已核实官方默认/推荐或此前明确批准的固定入口产生，本轮不搜索。文本编码器、VAE、scheduler 属于各 checkpoint 必要组成，不算额外增强模型。",
        "",
        "| 模型 | 固定参数 | 必要原生组成 |",
        "|---|---|---|",
    ]
    for model in MODELS:
        md.append(f"| {NAMES[model]} | {PARAMETER_TEXT[model]} | {COMPONENT_TEXT[model]} |")
    md += [
        "",
        "RePlan 的 expand=0、switch=.5 来自官方 CLI 的 qwen/qwen2511 分支默认，**不是**底层 API 的通用默认（.15/0）；planner 的 SDPA 替代不可用 FlashAttention2 是已披露工程差异，不宣称逐位等价。MIRAGE 保留原生 parent/part 定位、10 像素 padding 和局部/全局联合去噪；单个 API 内部的额外 forward 数按实际记录，不用“一个 API”掩盖成本。",
        "",
        "分辨率保持原生预处理：Qwen2511 视觉条件约 384² 面积、VAE 约 1024²；Qwen2.1 固定 1024 级，明确不同于 README 的 2048 级展示。FLUX3 单图约 4MP、多图每图约 1MP；FLUX2 超过 1024² 面积时缩小并对齐 16 像素；MICE 使用原生 round 到 16 的画布。标记缩小后的可读性是原生图文入口的实际限制，不为单个模型临时改标记或提高分辨率。",
        "",
        "| 模型 | 官方代码 commit | 权重 revision | 原生规划/特殊组成 |",
        "|---|---|---|---|",
    ]
    for model in MODELS:
        m = report["models"][model]["specification"]
        commit = m["method_commit"]
        code = f"[{commit[:12]}]({m['repository']}/tree/{commit})"
        weight = f"`{m['weight_revision']}`"
        planner = (
            f"planner `{m['planner_weight_revision']}`"
            if "planner_weight_revision" in m
            else "无独立 planner"
        )
        md.append(f"| {NAMES[model]} | {code} | {weight} | {planner} |")
    md += [
        "",
        f"Qwen 两版本及 FLUX2 使用固定 Diffusers `{DIFFUSERS}`；Qwen2.1 本地权重元数据 revision 与旧记录等价项详见分组核对。7 模型的全部原生组件、参数、代码来源和 SHA 在总 JSON；官方源码行号证据见 "
        + link(BASE / "qwen_flux2/FINAL_METHODS.md", "Qwen/FLUX2 核对")
        + "、"
        + link(BASE / "FLUX3_REPLAN_FAIRNESS_REVIEW.md", "FLUX3/RePlan 核对")
        + "、"
        + link(BASE / "mirage_mice/MIRAGE_MICE_FAIRNESS_REVIEW.md", "MIRAGE/MICE 核对")
        + "。这些早期核对文档中的历史执行状态以本报告实时记录和各 POST 报告为准。",
        "",
        "## 旧方式到新方式：改变什么、为什么改变",
        "",
        "| 模型 | 旧方式/问题 | 本轮固定修订 | 公平性理由 |",
        "|---|---|---|---|",
    ]
    for model in MODELS:
        old, new, why = CHANGES[model]
        md.append(f"| {NAMES[model]} | {old} | {new} | {why} |")
    md += [
        "",
        "MICE 有两项必须纠正的旧描述：源图 raster→nearest 的旧框路径出现过空域，原生 floor/ceil 框路径在相同 386 个 dev 单元 CPU 检查中没有这两个空域；这说明应忠实使用官方量化，不授权按结果扩大区域。旧“23 单元 overlap priority 缩减”来自 strict=True 的假设模拟，实际使用 strict=False，不能当成旧实验真实行为。原生 mask 的 nearest 量化边界仍保留。",
        "",
        "旧登记候选数由原 plan 读取，保留历史计算预算：",
        "",
        "| 模型 | 旧登记候选数 | 本轮方案数 |",
        "|---|---:|---:|",
    ]
    for model in MODELS:
        md.append(f"| {NAMES[model]} | {report['old_candidate_counts'].get(model, 0)} | 1 |")
    md += [
        "",
        "本轮是单独获准的协议修订验证，不能将它说成原四候选预算内又搜索出的赢家。未运行新 dev 排名；旧分数只属于当时实际输入配置。即使某些新输入低分或保留标记，也不据此继续加组件、改提示词或换方案。",
        "",
        "## 已发现的问题、阻塞项与下一步",
        "",
        "RePlan/MIRAGE 的定位误差属于完整方法在公开输入下的真实推理结果；FLUX/Qwen 的标记复制属于当前固定图文呈现下的真实行为。MICE 单图和 global/local 边界由官方实现决定。这些观察支持诚实披露限制，不能替代正式评分，也不能推导某种输入已达到模型所有可能能力。",
        "",
        "元数据的两处历史文字不覆盖实际调用：FLUX2 call.json 的 `new_inference_calls=0` 沿自准备清单，真实本轮调用见 result.json；MICE loader 的旧 `configuration.region_form` 不描述新 point/global 路由，应看 request.region_policy、call.global_unit_ids 和 call.regions。原记录均保留。",
        "",
    ]
    if stats["pending"]:
        md += [
            f"**当前阻塞：** 还有 {stats['pending']} 个编辑请求未终态；保持既定运行与样例，不补成功数。完成后复运行本生成器，更新结果及图册链接。",
            "",
        ]
    elif stats["failed"] or stats["audit_errors"]:
        md += [
            f"**当前阻塞：** 失败请求 {stats['failed']} 个，绑定核验错误 {stats['audit_errors']} 项；详情见 JSON，不能补零或隐去失败。",
            "",
        ]
    else:
        md += [
            "**生成与绑定核验：** 当前已齐全；各分组独立 post 审阅是否也齐全，见总 JSON 的 post_reviews，不能将出图齐全等同于完整 benchmark 已完成。",
            "",
        ]
    md += [
        "**下一步建议：** 用户确认固定方案后，再对完整 108-dev 运行同一配置和统一 Judge，不重新搜索；完整 dev 分数、输入及失败汇报后，仍按原约定停在 freeze/test 前等待确认。本轮两图验证授权不自动包含全 dev 或 test。报告刷新只读已有记录，不产生 GPU/Judge 调用。",
        "",
        "待确认协议："
        + link(REPO / "docs/protocol/if-bench-v1/PROTOCOL.fairness-v2.proposed.md")
        + "；"
        + link(REPO / "docs/protocol/if-bench-v1/FAIRNESS_V2_CHANGELOG_ZH.md", "逐条修订记录")
        + "。",
        "",
        "刷新入口：",
        "",
        "```bash",
        "cd /opt/tiger/tanyue/if-bench",
        "/tmp/ifbench-audit-clean311/bin/python src/evaluation/protocol_audit/build_fairness_revision_report.py",
        "```",
        "",
    ]
    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    authorization = read(BASE / "AUTHORIZATION.json")
    assert authorization["status"] == "approved" and authorization["cases"] == CASES
    split = read(SHARED / "plan/splits.json")
    assert set(CASES) <= set(split["dev"]) and not set(CASES) & set(split["test"])
    qwen = read(BASE / "qwen_flux2/FINAL_METHODS.json")
    other = read(BASE / "flux3_replan_fairness_review.json")
    mm = read(BASE / "mirage_mice/MIRAGE_MICE_FAIRNESS_REVIEW.json")
    specs = specifications(qwen, other, mm)
    mappings = settings_specs(qwen, other, mm)
    requests, plans = collect_requests(
        read(BASE / "qwen_flux2/CPU_AUDIT.json"),
        read(BASE / "qwen_flux2/FLUX2_PREPARED_REQUESTS.json"),
    )
    planners = collect_planners(plans)
    old_plan = read(OLD / "plan.json")
    models = {}
    for model in MODELS:
        rows = [r for r in requests if r["model"] == model]
        p_rows = [r for r in planners if r["model"] == model]
        generated = sum(r["runtime_status"] == "generated" for r in rows)
        failed = sum(r["runtime_status"] == "failed" for r in rows)
        runtime = {
            "expected": len(rows),
            "generated": generated,
            "failed": failed,
            "pending": len(rows) - generated - failed,
            "reused": sum(r["reused"] for r in rows),
            "output_verified": sum(r["output_verified"] for r in rows),
            "new_editor_api_calls_terminal_recorded": sum(
                r["new_editor_api_calls_terminal_recorded"] for r in rows
            ),
            "started_without_terminal_result": sum(
                r["started_without_terminal_result"] for r in rows
            ),
            "audit_errors": sum(len(r["input_audit_errors"]) for r in rows),
        }
        planner_summary = {
            "expected": len(p_rows),
            "terminal": sum(r["status"] != "pending" for r in p_rows),
            "new_api_calls": sum(r["new_api_calls"] for r in p_rows),
            "reused_api_calls": sum(r["reused_api_calls"] for r in p_rows),
            "batch_items": sum(r["batch_items"] for r in p_rows),
            "returned_pairs": sum(r["returned_pairs"] for r in p_rows),
        }
        models[model] = {
            "specification": specs[model],
            "settings": mappings[model],
            "runtime": runtime,
            "planner_summary": planner_summary,
            "requests": rows,
            "planners": p_rows,
            "gallery": gallery_info(model),
            "change": dict(zip(["previous", "revision", "fairness_reason"], CHANGES[model])),
            "limitation": LIMITATIONS[model],
        }
    summary = {
        k: sum(m["runtime"][k] for m in models.values())
        for k in [
            "expected",
            "generated",
            "failed",
            "pending",
            "reused",
            "output_verified",
            "new_editor_api_calls_terminal_recorded",
            "started_without_terminal_result",
            "audit_errors",
        ]
    }
    summary["all_140_outputs_verified"] = (
        summary["output_verified"] == 140 and summary["audit_errors"] == 0
    )
    summary["all_generation_attempts_terminal"] = summary["pending"] == 0
    summary["new_native_planner_api_calls"] = sum(
        m["planner_summary"]["new_api_calls"] for m in models.values()
    )
    summary["reused_native_planner_api_calls"] = sum(
        m["planner_summary"]["reused_api_calls"] for m in models.values()
    )
    report = {
        "schema": "ifbench-fairness-revision-consolidation-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "authorization": authorization,
        "fixed_cases": CASES,
        "settings": SETTINGS,
        "models": models,
        "summary": summary,
        "old_candidate_counts": {m: len(old_plan["candidates"].get(m, [])) for m in MODELS},
        "post_reviews": post_review_state(),
        "input_snapshots_sha256": SNAPSHOTS,
        "scientific_scope": "one predetermined public-input mapping per model; fixed two dev cases; no score search",
        "new_model_calls_by_report_builder": 0,
        "judge_calls_this_revision": 0,
        "scores": None,
        "marker_residual_population_rate": None,
        "freeze_authorized": False,
        "test_started": False,
        "historical_scores_preserved": True,
        "new_results_may_use_old_scores": False,
        "only_writes": ["FINAL_EVALUATION_METHODS.md", "FINAL_EVALUATION_METHODS.json"],
    }
    helper = REPO / "src/evaluation/protocol_audit/fairness_flux3_replan.py"
    assert sha(helper) == plans["flux3"]["helper_sha256"] == plans["replan"]["helper_sha256"]
    mm_runner = REPO / "src/evaluation/protocol_audit/fairness_mirage_mice_probe.py"
    mm_environment = read(model_root("mice") / "edit-shard0-environment.json")
    assert sha(mm_runner) == mm_environment["runner_sha256"]
    flux2_runner = REPO / "src/evaluation/protocol_audit/fairness_qwen_flux2_smoke.py"
    flux2_post = read(BASE / "qwen_flux2/POST_VALIDATION.json")
    assert sha(flux2_runner) == flux2_post["flux2"]["runner_sha256"]
    report["runtime_source_hashes_verified_against_execution_records"] = {
        str(p): sha(p) for p in [helper, mm_runner, flux2_runner]
    }
    scientific = {
        "specifications": specs,
        "input_mappings": mappings,
        "cases": CASES,
        "settings": SETTINGS,
        "request_artifacts": {r["request_path"]: r["request_sha256"] for r in requests},
        "runtime_sources": report["runtime_source_hashes_verified_against_execution_records"],
    }
    fingerprint = hashlib.sha256(
        json.dumps(scientific, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    report["scientific_configuration_sha256"] = fingerprint
    previous_path = BASE / "FINAL_EVALUATION_METHODS.json"
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else None
    if previous and "scientific_configuration_sha256" in previous:
        assert previous["scientific_configuration_sha256"] == fingerprint, (
            "Scientific configuration changed; refuse silent refresh"
        )
    (BASE / "FINAL_EVALUATION_METHODS.md").write_text(render(report))
    (BASE / "FINAL_EVALUATION_METHODS.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "summary": summary,
                "markdown": str(BASE / "FINAL_EVALUATION_METHODS.md"),
                "json": str(BASE / "FINAL_EVALUATION_METHODS.json"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
