"""CPU-only post-validation and gallery for immutable FLUX.2 fairness smoke.

Reads, but never changes, prepared inputs, runtime records or model outputs.
No model loading, GPU operation, scoring, selection or inference is performed.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

from samtok_benchmark.ifbench import SETTINGS
from samtok_benchmark.ifbench.inputs import visual_prompt
from samtok_benchmark.ifbench.public import verify


BASE = Path("/tmp/ifbench/fairness_v2_20261030")
ROOT = BASE / "qwen_flux2"
OUTPUTS = BASE / "flux2_smoke"
PREPARED = ROOT / "FLUX2_PREPARED_REQUESTS.json"
CASES = ["v2-sa_10063996", "v2-sa_7414116"]
REVISION = "92196c8e11f7b6cf2b7493e037d8c5345c559216"
PIPELINE_REVISION = "06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a"
PINNED_RUNNER_SHA = "bd1f6b668760d2f883a4baf6afe04d8b348bb344eb158df2df40dcae21948caa"
PARAMETERS = {"num_inference_steps": 4, "guidance_scale": 1.0, "max_sequence_length": 512}
COMPONENTS = {"rewriter": 0, "external_grounder": 0, "sam": 0, "planner": 0, "reflection": 0}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def gallery(setting, rows):
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    canvas = Image.new("RGB", (1500, len(rows) * 425), "white")
    draw = ImageDraw.Draw(canvas)
    for n, row in enumerate(rows):
        y = n * 425
        draw.text(
            (8, y + 4),
            f"FLUX.2 Klein-9B | {setting} | {row['case_id']} | new 4-step output",
            font=font,
            fill="black",
        )
        labels = [
            "Image 1: clean source",
            "Image 2: locator annotation" if len(row["images"]) > 1 else "S1: no second image",
            "Actual model output (source size)",
        ]
        paths = [
            row["images"][0],
            row["images"][1] if len(row["images"]) > 1 else None,
            row.get("output_image"),
        ]
        for i, (path, label) in enumerate(zip(paths, labels)):
            x = i * 500
            draw.text((x + 8, y + 32), label, font=small, fill="black")
            if path:
                with Image.open(path) as picture:
                    fitted = ImageOps.contain(picture.convert("RGB"), (490, 365))
                canvas.paste(
                    fitted, (x + (500 - fitted.width) // 2, y + 56 + (365 - fitted.height) // 2)
                )
            elif i == 2:
                draw.text((x + 8, y + 90), "FAILED: no generated image", font=font, fill="red")
    path = ROOT / "figures" / f"flux2_klein_9b__{setting}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, quality=90)
    return str(path)


def main():
    # Only native tokenizer and CPU preprocessing are imported. No pipeline is
    # instantiated and no device or weight loading code occurs in this script.
    from transformers import AutoTokenizer
    from diffusers.pipelines.flux2.image_processor import Flux2ImageProcessor

    rows = read(PREPARED)
    assert len(rows) == 20
    keys = [(x["setting"], x["case_id"]) for x in rows]
    assert len(set(keys)) == 20
    assert set(keys) == {(s, c) for s in SETTINGS for c in CASES}
    result_paths = {
        (p.parent.parent.name, p.parent.name): p for p in OUTPUTS.glob("*/*/result.json")
    }
    assert set(result_paths) == set(keys), "Exact 20 terminal requests required"
    split = read("/tmp/ifbench/tiered_v1/shared_inputs_20261027/plan/splits.json")
    assert set(CASES) <= set(split["dev"]) and not (set(CASES) & set(split["test"]))

    receipt_path = BASE / "flux2_download.json"
    receipt = read(receipt_path)
    assert receipt["status"] == "complete" and receipt["revision"] == REVISION
    assert len(receipt["files"]) == len(receipt["expected_files"]) == 24
    assert sum(x["size"] for x in receipt["files"]) == receipt["expected_bytes"]
    assert all(
        x["size_verified"] and (x["lfs_sha256"] is None or x["lfs_hash_verified"])
        for x in receipt["files"]
    )
    model_root = Path(receipt["destination"])
    for file in receipt["files"]:
        assert (model_root / file["path"]).stat().st_size == file["size"]
        if file["lfs_sha256"] is None:
            assert sha(model_root / file["path"]) == file["sha256"]
    model_index = read(model_root / "model_index.json")
    assert (
        model_index["_class_name"] == "Flux2KleinPipeline" and model_index["is_distilled"] is True
    )
    vae_config = read(model_root / "vae/config.json")
    multiple_of = 2 ** (len(vae_config["block_out_channels"]) - 1) * 2
    tokenizer = AutoTokenizer.from_pretrained(model_root / "tokenizer", local_files_only=True)
    pipeline = Path(
        "/tmp/ifbench/protocol_review_20261027/sources/diffusers/src/diffusers/pipelines/flux2/pipeline_flux2_klein.py"
    )
    runner = Path(__file__).with_name("fairness_qwen_flux2_smoke.py")
    assert sha(runner) == PINNED_RUNNER_SHA, "Runtime source changed after launch"

    audited, workers = [], defaultdict(list)
    for index, prepared in enumerate(rows):
        key = prepared["setting"], prepared["case_id"]
        directory = result_paths[key].parent
        call = read(directory / "call.json")
        result = read(directory / "result.json")
        started = read(directory / "started.json")
        request = read(prepared["public_request"])
        verify(request, assets=True)
        inputs = read(Path(prepared["public_request"]).with_name("inputs.json"))
        form = inputs["forms"]["dual"]
        assert prepared["public_digest"] == request["input_digest"]
        assert prepared["images"] == form["images"]
        assert prepared["prompt"] == form["prompt"] == visual_prompt(request, "dual")
        assert not form["discard_region"] and not form["lossy_mask_to_box"]
        assert all(unit["instruction"] in prepared["prompt"] for unit in request["units"])
        for name in [
            "model",
            "setting",
            "case_id",
            "public_request",
            "public_digest",
            "images",
            "prompt",
            "parameters",
            "seed",
            "weight_revision",
        ]:
            assert call[name] == prepared[name], (key, name)
        assert (
            call["parameters"] == PARAMETERS
            and call["seed"] == result["seed"] == started["seed"] == 42
        )
        assert call["weight_revision"] == result["weight_revision"] == REVISION
        assert result["pipeline_revision"] == PIPELINE_REVISION
        assert call["pipeline_sha256"] == sha(pipeline)
        assert call["model_root"] == str(model_root)
        assert call["model_index_sha256"] == sha(model_root / "model_index.json")
        assert call["extra_component_calls"] == COMPONENTS
        assert call["images_sha256"] == [sha(path) for path in prepared["images"]]
        assert (directory / "prompt.txt").read_text() == prepared["prompt"] + "\n"
        if len(prepared["images"]) == 2:
            assert sha(prepared["images"][1]) == inputs["annotation"]["sha256"]
        token_text = tokenizer.apply_chat_template(
            [{"role": "user", "content": call["prompt"]}],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        count = len(tokenizer(token_text, add_special_tokens=True, truncation=False)["input_ids"])
        assert call["input_token_count_before_padding"] == count <= 512
        assert result["inference_api_calls"] == 1

        with Image.open(prepared["images"][0]) as source:
            source_size = list(source.size)
            scaled = source.copy()
        assert source_size == request["source"]["size"]
        if scaled.width * scaled.height > 1024 * 1024:
            scaled = Flux2ImageProcessor._resize_to_target_area(scaled, 1024 * 1024)
        expected_raw_size = [
            scaled.width // multiple_of * multiple_of,
            scaled.height // multiple_of * multiple_of,
        ]
        entry = {
            k: call[k]
            for k in [
                "model",
                "setting",
                "case_id",
                "images",
                "prompt",
                "parameters",
                "public_digest",
                "weight_revision",
                "seed",
                "extra_component_calls",
            ]
        }
        entry.update(
            status=result["status"],
            K=len(request["units"]),
            call=str(directory / "call.json"),
            result=str(directory / "result.json"),
            public_request=prepared["public_request"],
            images_sha256=call["images_sha256"],
            input_token_count=count,
            source_size=source_size,
            expected_raw_size=expected_raw_size,
            inference_api_calls=1,
            transformer_forward_calls=result["transformer_forward_calls"],
            seconds=result["seconds"],
            worker_pid=started["pid"],
            shard=index % 2,
            started_unix=started["unix_time"],
            load_seconds=result["load_seconds"],
            peak_memory_allocated=result["peak_memory_allocated"],
            peak_memory_reserved=result["peak_memory_reserved"],
        )
        if result["status"] == "generated":
            assert result["transformer_forward_calls"] == 4
            assert result["raw_size"] == expected_raw_size
            raw_path, output_path = directory / "raw.png", directory / "output.png"
            assert result["output_image"] == str(output_path)
            assert (
                sha(raw_path) == result["raw_sha256"]
                and sha(output_path) == result["output_sha256"]
            )
            with Image.open(raw_path) as raw, Image.open(output_path) as output:
                raw.load()
                output.load()
                assert list(raw.size) == expected_raw_size and list(output.size) == source_size
                resized = raw.convert("RGB").resize(tuple(source_size), Image.Resampling.LANCZOS)
                assert ImageChops.difference(resized, output.convert("RGB")).getbbox() is None
            entry.update(
                output_image=str(output_path),
                output_sha256=result["output_sha256"],
                raw_image=str(raw_path),
                raw_sha256=result["raw_sha256"],
                raw_size=result["raw_size"],
            )
        else:
            assert result["status"] == "failed"
            entry.update(
                error_type=result.get("error_type"),
                error=result.get("error"),
                traceback=result.get("traceback"),
            )
        audited.append(entry)
        workers[started["pid"]].append(entry)

    worker_summary = []
    for pid, group in workers.items():
        loads = {row["load_seconds"] for row in group}
        assert len(loads) == 1
        worker_summary.append(
            {
                "pid": pid,
                "shards": sorted({row["shard"] for row in group}),
                "requests": len(group),
                "inference_record_seconds": sum(row["seconds"] for row in group),
                "load_seconds_once": next(iter(loads)),
                "first_call_unix": min(row["started_unix"] for row in group),
                "last_call_end_approx_unix": max(
                    row["started_unix"] + row["seconds"] for row in group
                ),
            }
        )

    example_md = [
        "# FLUX.2 Klein-9B：固定 2 个 dev 案例 × 10 settings",
        "",
        "本页是本轮真实新生成结果。每张图上行是 K=2，下行是 K=5；左列原图，中列实际区域标注输入（S1 无第二图），右列模型输出。",
        "",
        "案例固定为旧 smoke 的第 1、3 个案例，没有按输出选择。所有请求只采样一次，seed=42，原生 4 步 / guidance=1；PE、外部定位器、SAM、外部规划与 reflection 均为 0。尚未 Judge，不提供或推测 UnitPass / JointPass。",
        "",
    ]
    galleries = {}
    for setting in SETTINGS:
        selected = [
            next(row for row in audited if row["setting"] == setting and row["case_id"] == case)
            for case in CASES
        ]
        galleries[setting] = gallery(setting, selected)
        example_md += [
            f"## {setting}",
            "",
            f"![FLUX.2 Klein-9B {setting}](figures/{Path(galleries[setting]).name})",
            "",
        ]
        for row in selected:
            example_md += [
                f"**{row['case_id']} · K={row['K']} · {row['status']} · 输入 {row['input_token_count']} tokens**",
                "",
                "```text",
                row["prompt"],
                "```",
                "",
                f"[实际调用]({row['call']}) · [真实结果]({row['result']}) · [原始输出]({row.get('output_image', row['result'])})",
                "",
            ]
    (ROOT / "flux2_EXAMPLES.md").write_text("\n".join(example_md))

    old = read(ROOT / "CPU_AUDIT.json")
    reused = old["selected"]
    assert len(reused) == 40
    for row in reused:
        assert sha(row["output_image"]) == row["output_sha256"]

    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "fixed two-dev-case, one-scheme interface validation; no new Judge or score selection",
        "fixed_cases": CASES,
        "settings": list(SETTINGS),
        "new_model_calls_by_validator": 0,
        "judge_calls": 0,
        "freeze_or_test": False,
        "qwen_reused": {
            "qwen2511": 20,
            "qwen21": 20,
            "output_sha256_rechecked": 40,
            "new_generation_calls": 0,
            "evidence": str(ROOT / "CPU_AUDIT.json"),
        },
        "flux2": {
            "expected_requests": 20,
            "terminal_requests": len(audited),
            "statuses": dict(Counter(row["status"] for row in audited)),
            "inference_api_calls": sum(row["inference_api_calls"] for row in audited),
            "transformer_forward_calls": sum(row["transformer_forward_calls"] for row in audited),
            "parameters": PARAMETERS,
            "extra_component_calls": COMPONENTS,
            "input_token_count_min": min(row["input_token_count"] for row in audited),
            "input_token_count_max": max(row["input_token_count"] for row in audited),
            "inference_record_seconds_sum": sum(row["seconds"] for row in audited),
            "workers": worker_summary,
            "raw_sizes": [
                list(size)
                for size in sorted(
                    {tuple(row["raw_size"]) for row in audited if row["status"] == "generated"}
                )
            ],
            "source_sizes": [
                list(size) for size in sorted({tuple(row["source_size"]) for row in audited})
            ],
            "weight_revision": REVISION,
            "pipeline_revision": PIPELINE_REVISION,
            "runner_sha256": sha(runner),
            "prepared_sha256": sha(PREPARED),
            "gallery": galleries,
            "requests": audited,
        },
        "weights": {
            "receipt": str(receipt_path),
            "receipt_sha256": sha(receipt_path),
            "files": len(receipt["files"]),
            "bytes": receipt["expected_bytes"],
            "download_seconds": receipt["wall_seconds"],
            "receipt_status": receipt["status"],
            "large_lfs_hashes_verified_by_download_receipt": 8,
            "post_validation_recheck": "24 local sizes plus 16 non-LFS file hashes; 8 large weight hashes use completed root receipt, not redundantly re-read",
        },
        "verified": [
            "exact fixed dev cases/settings and no test overlap",
            "public schema, assets and input digest",
            "prepared/call prompt-image-parameter-seed-revision binding",
            "dual image order and annotation SHA",
            "complete original instructions, no region discard",
            "native tokenizer count <=512 without truncation",
            "native 4-step parameters and 4 transformer forwards",
            "zero optional/external component calls",
            "raw/output SHA and actual decoded sizes",
            "output pixels exactly native raw resized to source with LANCZOS",
            "pinned runtime source unchanged",
            "Qwen 40 reused output SHA unchanged",
        ],
        "metadata_caveat": "call.json copied new_inference_calls=0 from prepared metadata; result.json inference_api_calls=1 is actual. Total actual FLUX2 generation calls=20. Original records not changed.",
        "observations": read(ROOT / "FLUX2_VISUAL_OBSERVATIONS.json")
        if (ROOT / "FLUX2_VISUAL_OBSERVATIONS.json").exists()
        else [],
        "limitations": [
            "Two fixed cases validate interfaces and show failure modes; not a benchmark score or representative rate.",
            "Visual locator input is not a native hard mask. Successful generation does not establish instruction success.",
            "Inference-record seconds include output serialization; sum over two simultaneous workers is not elapsed wall time.",
            "This revision does not freeze configurations or authorize test.",
        ],
    }
    dump(ROOT / "POST_VALIDATION.json", report)
    generate_report(report)
    print(
        json.dumps(
            {
                "status": "CPU checks complete",
                "flux2_statuses": report["flux2"]["statuses"],
                "generation_calls": report["flux2"]["inference_api_calls"],
                "forwards": report["flux2"]["transformer_forward_calls"],
                "tokens": [
                    report["flux2"]["input_token_count_min"],
                    report["flux2"]["input_token_count_max"],
                ],
                "gallery": str(ROOT / "flux2_EXAMPLES.md"),
                "json": str(ROOT / "POST_VALIDATION.json"),
            },
            ensure_ascii=False,
        )
    )


def generate_report(report):
    f = report["flux2"]
    md = [
        "# Qwen / FLUX.2：公平性方案验证结果",
        "",
        "结论：Qwen 两版本的固定 dual 输入可精确复用既有 40 份真实输出；新增 FLUX.2 Klein-9B 的 20 个固定请求全部出图。它们均使用原生图文推理，未调用额外增强组件。出图成功不等于任务完成；FLUX.2 的实图明确显示标记残留和部分目标绑定错误，需要如实保留这些结果。",
        "",
        "这是一轮已获批准的固定方案接口验证，不是新的候选搜索、dev 排名、冻结或 test；本轮未调用 Judge，也没有 UnitPass / JointPass 分数。案例固定为旧 smoke 的第 1、3 例，未按输出质量选图。",
        "",
        "| 模型 | 固定案例 × settings | 本轮新生成 | 实际配置 | 证据 |",
        "|---|---:|---:|---|---|",
        "| Qwen-Image-Edit-2511 | 2 × 10；20 份既有输出 SHA 复核 | 0 | S1 原图；其余清图 + 标注图；40 步 / true CFG 4 / guidance 1 / seed 42 | [完整实图与 prompt](qwen2511_EXAMPLES.md) |",
        "| Qwen-Image-2.1 | 2 × 10；20 份既有输出 SHA 复核 | 0 | 同一图文呈现；40 步 / CFG 1 / 1024 级 / seed 42；PE 关闭 | [完整实图与 prompt](qwen21_EXAMPLES.md) |",
        "| FLUX.2 Klein-9B distilled | 2 × 10；20 成功 / 0 失败 | 20 | 同一图文呈现；4 步 / guidance 1 / seed 42；max length 512 | [完整实图与 prompt](flux2_EXAMPLES.md) |",
        "",
        "Qwen 的 single 与 dual 都可以是合规输入。此次固定 dual 的理由是同时保留清晰源图与公开区域图，不是因为它比分数搜索选中的 single 更高分。原 dev 的 JP 搜索及 single 提案保持历史记录，此次变更作为已明确授权的新公平性呈现规则记录。",
        "",
        "## 做了什么与核验结论",
        "",
        "| 核验项 | 结果 |",
        "|---|---|",
        "| 输入 | 20/20 与冻结前准备清单的图序、最终 prompt、参数、seed、public digest、权重 revision 完全一致；逐条 public schema 和资产 SHA 通过 |",
        "| 公开信息 | S1 为清图 + ref；其他 setting 为清图 + 相同画布的公开标注图 + 原指令。无丢弃区域，无隐藏对象名，无 point→硬 mask |",
        f"| 原生步骤与调用 | 20 次 pipeline 调用；实际 {f['transformer_forward_calls']} 次 transformer forward，即每请求 4 次；guidance=1 |",
        "| 额外组件 | 改写器、外部 grounder、SAM、外部 planner、reflection 均为 0。模型本身的 Qwen3 文本编码器与 VAE 属于 checkpoint 原生组成 |",
        f"| 文本 | 原生 tokenizer 复算 {f['input_token_count_min']}–{f['input_token_count_max']} tokens，均未超过 512，无截断 |",
        "| 图像尺寸 | 两源图分别 2250×1500、2241×1500；官方预处理均得到 1248×832。全部 raw/output SHA 正确，输出像素逐一等于 raw 经 LANCZOS 回源图尺寸 |",
        "| 权重与源代码 | 固定 9B distilled revision；24 文件、34,722,801,212 bytes 下载完成。8 个 LFS 文件使用下载 receipt 的 SHA 核验结论；本次复核 24 个大小及 16 个非 LFS 文件 SHA。运行脚本 SHA 未变 |",
        f"| 耗时与显存 | 两 worker 各 10 请求，逐请求记录耗时合计 {f['inference_record_seconds_sum']:.2f} 秒；这是并行 worker 耗时之和，含保存，不是总墙钟。单 worker 加载分别 "
        + " / ".join(f"{w['load_seconds_once']:.2f}" for w in f["workers"])
        + " 秒，仅各计一次；峰值 allocated "
        + f"{max(r['peak_memory_allocated'] for r in f['requests']) / 1024**3:.2f} GiB"
        + " |",
        "",
        f"权重：`{REVISION}`。Diffusers pipeline：`{PIPELINE_REVISION}`。原生 4 步 / guidance=1 来自 [固定 model card 示例](https://huggingface.co/black-forest-labs/FLUX.2-klein-9B/blob/{REVISION}/README.md#L65)。图像面积限制及 16 像素整除沿用 [固定原生预处理](https://github.com/huggingface/diffusers/blob/{PIPELINE_REVISION}/src/diffusers/pipelines/flux2/pipeline_flux2_klein.py#L762)。",
        "",
        f"[逐请求审计 JSON](POST_VALIDATION.json) · [下载 receipt]({BASE / 'flux2_download.json'}) · [输入与官方接口核对](FINAL_METHODS.md)",
        "",
        "## 发现的问题、偏差与限制",
        "",
        "FLUX.2 确实接受多图，但图文提示没有建立硬性的“只编辑第一张图、第二张图仅作定位”约束。多张实图保留了点、框、轮廓或 U 标签；no-ref 条件下还出现目标混淆。这些是当前固定呈现规则下的模型表现，不以它们为理由追加模型、人工去标、改 prompt 或重采样。双图保持原图信息完整的公平性理由仍成立，但不能宣传为已经消除了标记干扰或充分证明所有区域均被理解。",
        "",
        "记录口径有一项需要明确：call.json 中的 `new_inference_calls=0` 沿用了准备清单的静态字段，不代表实际没有运行。实际调用以 result.json 的 `inference_api_calls=1` 为准，本轮 FLUX.2 总计 20 次新生成；原始记录保持不改。",
        "",
        "以下仅是对固定实图的目视描述，不是人工评分、统计残留率或 UnitPass / JointPass。小目标和细节应看原图链接；没有看到明显标记也不能当作残留率为零。",
        "",
        "| Setting | K=2 固定例目视观察 | K=5 固定例目视观察 |",
        "|---|---|---|",
    ]
    for obs in report["observations"]:
        md.append(f"| {obs['setting']} | {obs['K2']} | {obs['K5']} |")
    md += [
        "",
        "## FLUX.2：全部 settings 的直接实图",
        "",
        "每图上行为 `v2-sa_10063996`（K=2），下行为 `v2-sa_7414116`（K=5）。左原图，中实际第二图（S1 为空），右真实输出；全部最终 prompt 与逐次调用链接见 [完整图册](flux2_EXAMPLES.md)。",
        "",
    ]
    for setting in SETTINGS:
        md += [
            f"### {setting}",
            "",
            f"![FLUX.2 Klein-9B {setting}](figures/{Path(f['gallery'][setting]).name})",
            "",
        ]
    md += [
        "## 阻塞项与下一步",
        "",
        "本轮接口验证没有剩余下载或生成阻塞。正式评测方式仍需结合其他方法的统一报告确认，然后再决定是否冻结并启动正式评测。当前不新增 GPU 或 Judge 调用，不通过小样例结果换方案。",
        "",
        "完整 Qwen 证据保持可复用：[Qwen-2511 20 例](qwen2511_EXAMPLES.md)、[Qwen-2.1 20 例](qwen21_EXAMPLES.md)。本次再次核对 40 份历史输出 SHA，未改变旧分数或输入。",
        "",
    ]
    (ROOT / "POST_VALIDATION.md").write_text("\n".join(md))


if __name__ == "__main__":
    main()
