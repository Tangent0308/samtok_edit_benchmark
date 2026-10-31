"""One-case interface smoke test. No judge, dev selection, or benchmark run."""

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path("/tmp/ifbench/protocol_review_20261027")
REPO = Path("/opt/tiger/tanyue/if-bench")
MODELS = Path("/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models")
DATA = Path("/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "model", choices=["qwen2511", "qwen21", "flux3", "mirage", "replan", "mice"]
    )
    parser.add_argument("--setting", choices=["region", "s1"], default="region")
    args = parser.parse_args()
    out = ROOT / "smoke" / (args.model if args.setting == "region" else args.model + "-s1")
    out.mkdir(parents=True, exist_ok=True)
    record = {
        "model": args.model,
        "phase": 1,
        "judge_run": False,
        "case_count": 1,
        "purpose": "interface connectivity only; not semantic validation or dev selection",
    }
    start = time.time()
    try:
        import numpy as np
        import torch

        torch.set_num_threads(4)
        from PIL import Image, ImageDraw

        case = json.loads((REPO / "data/v2_2.6.0/cases.jsonl").read_text().splitlines()[0])
        source = Image.open(DATA / case["source"]["image"]).convert("RGB")
        record.update(case_id=case["id"], torch=torch.__version__, seed=42)
        record["device"] = torch.cuda.get_device_name(0)
        marks = source.copy()
        draw = ImageDraw.Draw(marks)
        for i, unit in enumerate(case["units"]):
            draw.rectangle(unit["target"]["box"], outline=["red", "blue"][i], width=6)
            draw.text(
                tuple(unit["target"]["box"][:2]),
                str(i + 1),
                fill=["red", "blue"][i],
                stroke_width=1,
            )
        # Diagnostic marks only; this is not the final frozen IF-Bench renderer.
        prompt = (
            "Image 1 is the photo to edit. Image 2 is a copy with numbered colored boxes. "
            "Edit Image 1 only. Leave no marks in the output. Keep everything else unchanged.\n"
            + "\n".join(
                f"{i + 1}. [{['red', 'blue'][i]} mark #{i + 1}] {u['instruction_noref']}"
                for i, u in enumerate(case["units"])
            )
        )
        global_prompt = "Apply all edits. Keep everything else unchanged.\n" + "\n".join(
            f"{i + 1}. {u['instruction_noref']}" for i, u in enumerate(case["units"])
        )
        record["prompt"] = prompt
        generator = torch.Generator("cuda").manual_seed(42)
        if args.model in ["qwen2511", "qwen21", "mirage"]:
            from diffusers import QwenImageEditPlusPipeline, QwenImage21Pipeline

            cls = QwenImage21Pipeline if args.model == "qwen21" else QwenImageEditPlusPipeline
            model = MODELS / (
                "Qwen-Image-2.1" if args.model == "qwen21" else "Qwen-Image-Edit-2511"
            )
            pipe = cls.from_pretrained(
                str(model), torch_dtype=torch.bfloat16, local_files_only=True
            ).to("cuda")
            if args.model == "mirage":
                sys.path.insert(0, str(ROOT / "sources/mirage"))
                from mirage.qwen_image_edit import run_qwen_image_edit

                boxes = [
                    dict(zip(["x1", "y1", "x2", "y2"], u["target"]["box"])) for u in case["units"]
                ]
                sub = [
                    "Target: the selected region. Instruction: " + u["instruction_noref"]
                    for u in case["units"]
                ]
                result = run_qwen_image_edit(
                    pipe,
                    source,
                    global_prompt,
                    sub,
                    boxes,
                    num_inference_steps=40,
                    true_cfg_scale=4.0,
                    patch_ratio=0.4,
                    generator=generator,
                )
                record.update(steps=40, true_cfg_scale=4.0, patch_ratio=0.4, prompt=global_prompt)
            else:
                cfg = 1.0 if args.model == "qwen21" else 4.0
                kw = (
                    {"negative_prompt": " ", "guidance_scale": 1.0}
                    if args.model == "qwen2511"
                    else {}
                )
                result = pipe(
                    image=[source, marks],
                    prompt=prompt,
                    true_cfg_scale=cfg,
                    num_inference_steps=40,
                    generator=generator,
                    **kw,
                ).images[0]
                record.update(steps=40, true_cfg_scale=cfg, rewriter=False)
        elif args.model == "flux3":
            os.environ["WEIGHTS_DIR"] = str(MODELS)
            sys.path.insert(0, str(ROOT / "sources/flux3/src"))
            from flux3.generate import generate
            from flux3.pipeline import Pipeline
            from types import SimpleNamespace

            models = SimpleNamespace(
                upsampler=None,
                pipeline=Pipeline(
                    {"distilled": str(MODELS / "flux-3-image-klein")},
                    str(MODELS / "flux-3-image-klein/text_encoder"),
                    str(MODELS / "flux-3-image-klein/ae.safetensors"),
                ),
            )
            record["loader_note"] = (
                "Direct official Pipeline; generate safety=False as upstream default; avoids eager loading of unused optional classifier."
            )
            w, h = source.size
            boxes = []
            for i, u in enumerate(case["units"]):
                x1, y1, x2, y2 = u["target"]["box"]
                box = [y1 / h, x1 / w, y2 / h, x2 / w]
                boxes.append(
                    {
                        "id": f"obj_{i + 1}",
                        "from": "ref_image_0",
                        "src_bbox": box,
                        "tgt_bbox": box,
                        "desc": "the selected region",
                    }
                )
            caption = (
                "Edit <ref_image_0>. "
                + " ".join(
                    f"For <obj_{i + 1}>, {u['instruction_noref']}"
                    for i, u in enumerate(case["units"])
                )
                + " Keep everything else unchanged."
            )
            result, meta = generate(
                models, "distilled", caption, [source], boxes=boxes, pup=False, seed=42
            )
            record["generation_metadata"] = meta
        elif args.model == "replan":
            sys.path.insert(0, str(ROOT / "sources/replan"))
            from replan.pipelines.replan import RePlanPipeline

            pipe = RePlanPipeline(
                diffusion_model_name=str(MODELS / "Qwen-Image-Edit-2511"),
                pipeline_type="qwen2511",
                init_vlm=False,
                device="cuda",
                torch_dtype=torch.bfloat16,
                output_dir=str(out),
            )
            response = (
                "<gen_image>"
                + global_prompt
                + "</gen_image><region>"
                + json.dumps(
                    [
                        {"bbox_2d": u["target"]["box"], "hint": u["instruction_noref"]}
                        for u in case["units"]
                    ]
                )
                + "</region>"
            )
            response_out = pipe.region_edit_with_attention(
                source,
                "",
                response=response,
                expand_value=0.0,
                attention_switch_step=0.5,
                skip_save=True,
                pipeline_kwargs={"generator": generator, "num_inference_steps": 40},
            )
            result, _, details = response_out
            record["result_keys"] = list(details)
            record.update(steps=40, planner=False, prompt=global_prompt)
        elif args.model == "mice":
            sys.path.insert(0, str(ROOT / "sources/mice"))
            import infer_flux2_mice as impl

            sys.argv = [
                "infer_flux2_mice.py",
                "--exp_name",
                "ifbench_smoke",
                "--dataset_root",
                str(DATA),
            ]
            config = impl.parse_args()
            config.pretrained_model_name_or_path = str(MODELS / "FLUX.2-klein-4B")
            pipe = impl.load_pipeline(config, "cuda")
            processors = impl.get_attention_processors(
                impl.AttentionSetting(config.attention_setting.lower()),
                config.sigma_scale,
                config.kernel_size,
                config.temperature,
            )
            if isinstance(processors, tuple):
                for _, module in pipe.transformer.named_modules():
                    if isinstance(module, impl.Flux2Attention):
                        module.set_processor(processors[0])
                    elif isinstance(module, impl.Flux2ParallelSelfAttention):
                        module.set_processor(processors[1])
            else:
                pipe.transformer.set_attn_processor(processors)
            w, h = source.size
            rw = int((1024**2 * w / h) ** 0.5) // 16 * 16
            rh = int((1024**2 * h / w) ** 0.5) // 16 * 16
            masks = [
                torch.from_numpy(
                    np.array(Image.open(DATA / u["target"]["mask"]).convert("L")) > 127
                ).float()
                for u in case["units"]
            ]
            text = "$BREAKFLAG$".join(
                ["Keep everything else unchanged."]
                + [u["instruction_noref"] for u in case["units"]]
            )
            if args.setting == "s1":
                masks = []
                text = "Apply all edits. Keep everything else unchanged. " + " ".join(
                    u["instruction_ref"] for u in case["units"]
                )
                record["setting_note"] = (
                    "S1 global-only with empty instance_masks_yx list; not None and no localization."
                )
            result = pipe(
                image=source.resize((rw, rh)),
                prompt=text,
                height=rh,
                width=rw,
                num_inference_steps=4,
                guidance_scale=1.0,
                prompt_settings=config.prompt_settings,
                attention_setting=config.attention_setting,
                hard_image_attribute_binding_list_double=config.hard_image_attribute_binding_list_double,
                hard_image_attribute_binding_list_single=config.hard_image_attribute_binding_list_single,
                bring_area_to_1024_squared=config.bring_area_to_1024_squared,
                generator=generator,
                hard_masking_steps=config.masking_steps,
                relaxed_timesteps=config.relaxed_timesteps,
                attention_kwargs={"smooth_P_L": config.smooth_P_L},
                free_latent=config.free_latent,
                free_context=config.free_context,
                free_LC=config.free_LC,
                instance_masks_yx=masks,
            ).images[0]
            record.update(steps=4, guidance_scale=1.0, prompt=text)
        result.save(out / "output.png")
        record.update(
            status="generated",
            output_size=list(result.size),
            peak_gpu_bytes=torch.cuda.max_memory_allocated(),
        )
    except Exception as error:
        record.update(status="failed", error=repr(error), traceback=traceback.format_exc())
        traceback.print_exc()
    record["elapsed_seconds"] = time.time() - start
    (out / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {k: record[k] for k in ["model", "status", "elapsed_seconds"]}, ensure_ascii=False
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
