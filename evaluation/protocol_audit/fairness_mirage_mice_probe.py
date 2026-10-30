# ruff: noqa: E402
# Standalone entrypoint: configure CPU threads/import paths before dependent imports.
"""Isolated fixed-input fairness probes for MIRAGE and MICE.

No quality search, no Judge, no official test split. `prepare` is CPU-only.
GPU stages must be launched by the coordinating agent after allocation.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import traceback

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from samtok_benchmark.io import digest, sha256_file
from samtok_benchmark.ifbench.public import verify
from samtok_benchmark.ifbench.inputs import BASE, SINGLE, SELECTOR_NOTE, global_prompt
from samtok_benchmark.ifbench.render import COLOR_NAMES

SOURCES = Path("/tmp/ifbench/protocol_review_20261027/sources")
SHARED = Path("/tmp/ifbench/tiered_v1/shared_inputs_20261027")
MODELS = Path("/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models")
DEFAULT_ROOT = Path("/tmp/ifbench/fairness_v2_20261030/mirage_mice/probe")
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
VERSION = "fairness-public-native-flow-v1"


def fatal_cuda_error(exc):
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "device-side assert",
            "illegal memory access",
            "misaligned address",
            "unspecified launch failure",
            "cuda error:",
            "cublas_status_execution_failed",
        )
    )


def save(path, obj, immutable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if immutable and path.exists():
        if json.loads(path.read_text()) != obj:
            raise ValueError(f"Immutable record differs: {path}")
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def spatial_hint(unit):
    if unit["locator"] == "none":
        return ""
    color = COLOR_NAMES[int(unit["id"][1:]) - 1]
    shape = {"point": "point", "box": "box", "mask": "mask contour"}[unit["locator"]]
    return (
        f"Spatial input for this edit: the {color} {shape} labeled {unit['id']} "
        "indicates the selected source object, part, or anchor. "
        "The marks and labels are input annotations, not the target object. "
        "For an addition, the selection identifies the existing attachment or support location, "
        "not the outline of the new object."
    )


def payload(model, case, setting):
    directory = SHARED / "requests" / setting / case
    public = json.loads((directory / "public.json").read_text())
    verify(public, assets=True)
    inputs = json.loads((directory / "inputs.json").read_text())
    assert inputs["public_input_digest"] == public["input_digest"]
    annotation = inputs["annotation"]
    if annotation:
        assert sha256_file(Path(annotation["path"])) == annotation["sha256"]
        assert annotation["size"] == public["source"]["size"]
        assert annotation["transform"] == {"scale_xy": [1, 1], "offset_xy": [0, 0]}
    common = {
        "version": VERSION,
        "model": model,
        "case_id": case,
        "setting": setting,
        "source": public["source"],
        "public_input_digest": public["input_digest"],
        "public_units": public["units"],
        "seed": 42,
        "global_original_prompt": global_prompt(public),
        "annotation": annotation,
        "new_external_components": False,
    }
    if model == "mirage":
        common.update(
            parser_inputs=[u["instruction"] for u in public["units"]],
            grounding_hints={u["id"]: spatial_hint(u) for u in public["units"]},
            grounding_image=annotation["path"] if annotation else public["source"]["path"],
            edit_image=public["source"]["path"],
            parameters={
                "num_inference_steps": 40,
                "true_cfg_scale": 4.0,
                "patch_ratio": 0.4,
                "padding_pixels": 10,
            },
            parser_pair_count_policy="retain every native returned pair, grouped by public batch item; no equality-to-K guard",
            native_flow_adaptation="per-unit native parser batch; append public spatial hint after original grounding prompt; clean image for joint editing",
        )
    else:
        global_units = [u for u in public["units"] if u["locator"] in ("none", "point")]
        regional = [u for u in public["units"] if u["locator"] in ("box", "mask")]
        has_point = any(u["locator"] == "point" for u in public["units"])
        lines = []
        for u in global_units:
            mark = (
                f" [{COLOR_NAMES[int(u['id'][1:]) - 1]} point, label {u['id']}]"
                if u["locator"] == "point"
                else ""
            )
            lines.append(f"{u['id']}.{mark} {u['instruction']}")
        prefix = (SINGLE + "\n" + SELECTOR_NOTE + "\n") if has_point else ""
        global_text = prefix + BASE + ("\n" + "\n".join(lines) if lines else "")
        prompt = "$BREAKFLAG$".join([global_text] + [u["instruction"] for u in regional])
        w, h = public["source"]["size"]
        model_size = [
            round((1024**2 * w / h) ** 0.5) // 16 * 16,
            round((1024**2 * h / w) ** 0.5) // 16 * 16,
        ]
        common.update(
            image=annotation["path"] if has_point else public["source"]["path"],
            prompt=prompt,
            global_unit_ids=[u["id"] for u in global_units],
            regional_units=regional,
            model_size=model_size,
            parameters={"num_inference_steps": 4, "guidance_scale": 1.0},
            annotation_policy="reuse full shared annotation if point exists; native box/mask information is repeated visually, not augmented",
            region_policy="box-only: native normalized bbox API; otherwise native floor/ceil box grid and native nearest mask grid via mask API; point never made a region mask",
            scope="native attention unchanged; none/point tasks use global text, box/mask use native local bindings",
        )
    common["request_digest"] = digest(common)
    return common


def prepare(root):
    split = json.loads((SHARED / "plan/splits.json").read_text())
    assert set(CASES) <= set(split["dev"]) and not set(CASES) & set(split["test"])
    for model in ("mirage", "mice"):
        tasks = []
        for case in CASES:
            for setting in SETTINGS:
                request = payload(model, case, setting)
                out = root / model / "requests" / setting / case
                save(out / "request.json", request, immutable=True)
                tasks.append(
                    {
                        "case_id": case,
                        "setting": setting,
                        "request": str(out / "request.json"),
                        "request_digest": request["request_digest"],
                    }
                )
        plan = {
            "version": VERSION,
            "model": model,
            "seed": 42,
            "cases": CASES,
            "settings": SETTINGS,
            "split_digest": split["digest"],
            "tasks": tasks,
            "quality_selection": False,
            "formal_test": False,
            "external_enhancement": False,
            "freeze": False,
        }
        plan["digest"] = digest(plan)
        save(root / model / "plan.json", plan, immutable=True)


def tasks(args):
    plan = json.loads((args.root / args.model / "plan.json").read_text())
    assert plan["digest"] == digest({k: v for k, v in plan.items() if k != "digest"})
    result = []
    for task in plan["tasks"][args.shard :: args.shards]:
        request = json.loads(Path(task["request"]).read_text())
        assert request["request_digest"] == digest(
            {k: v for k, v in request.items() if k != "request_digest"}
        )
        assert request["request_digest"] == task["request_digest"]
        # Revalidate shared input assets immediately before inference.
        original = json.loads(
            (SHARED / "requests" / task["setting"] / task["case_id"] / "public.json").read_text()
        )
        verify(original, assets=True)
        assert original["input_digest"] == request["public_input_digest"]
        assert (
            original["source"] == request["source"] and original["units"] == request["public_units"]
        )
        annotation = request["annotation"]
        if annotation:
            annotation_path = Path(annotation["path"])
            assert sha256_file(annotation_path) == annotation["sha256"]
            assert annotation["size"] == request["source"]["size"]
            assert annotation["transform"] == {"scale_xy": [1, 1], "offset_xy": [0, 0]}
            with Image.open(annotation_path) as annotated:
                assert list(annotated.size) == request["source"]["size"]
        result.append((task, request))
    return plan, result


def stage_start(out, request, plan, stage):
    out.mkdir(parents=True, exist_ok=True)
    target = out / "result.json"
    if target.exists():
        old = json.loads(target.read_text())
        assert (
            old["request_digest"] == request["request_digest"]
            and old["plan_digest"] == plan["digest"]
        )
        if old.get("status") == "generated":
            assert sha256_file(Path(old["output_image"])) == old["output_sha256"]
            if old.get("raw_image"):
                assert sha256_file(Path(old["raw_image"])) == old["raw_sha256"]
        return False
    started = out / "started.json"
    if started.exists():
        save(
            target,
            {
                "status": "failed",
                "error": "Previous attempt started without terminal record; no automatic retry.",
                "request_digest": request["request_digest"],
                "plan_digest": plan["digest"],
                "stage": stage,
            },
        )
        return False
    save(
        started,
        {
            "request_digest": request["request_digest"],
            "plan_digest": plan["digest"],
            "stage": stage,
            "seed": 42,
            "started_at_unix": time.time(),
        },
        immutable=True,
    )
    return True


def plan_mirage(args):
    import torch

    sys.path.insert(0, str(SOURCES / "mirage"))
    from mirage.vlm import load_vlm, parse_instructions, to_pixels

    plan, selected = tasks(args)
    vlm = load_vlm("qwen35", str(MODELS / "Qwen3.5-9B"), "cuda", torch.bfloat16)
    native_chat = vlm.chat
    native_messages = vlm.grounding_messages
    active = {}

    def messages(image, phrase, mode):
        batch = native_messages(image, phrase, mode)
        hint = image.info.get("ifbench_spatial_hint", "")
        if hint:
            batch[-1]["content"].append({"type": "text", "text": hint})
        return batch

    vlm.grounding_messages = messages

    def serial(value, number):
        if isinstance(value, Image.Image):
            path = (
                active["out"]
                / "trace_images"
                / f"call{number:03d}-image{active['image_index']:03d}.png"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            value.save(path)
            active["image_index"] += 1
            return {
                "path": str(path),
                "sha256": sha256_file(path),
                "size": list(value.size),
                "public_hint": value.info.get("ifbench_spatial_hint", ""),
            }
        if isinstance(value, list):
            return [serial(v, number) for v in value]
        if isinstance(value, dict):
            return {k: serial(v, number) for k, v in value.items()}
        return value

    def chat(batch, max_new_tokens=512):
        number = len(active["traces"])
        trace = {
            "index": number,
            "messages": serial(batch, number),
            "max_new_tokens": max_new_tokens,
            "do_sample": False,
            "status": "started",
            "started_at_unix": time.time(),
        }
        active["traces"].append(trace)
        save(active["out"] / "traces.json", active["traces"])
        try:
            response = native_chat(batch, max_new_tokens)
            trace.update(status="returned", response=response)
            return response
        except Exception as exc:
            trace.update(status="failed", error=repr(exc))
            raise
        finally:
            trace["finished_at_unix"] = time.time()
            save(active["out"] / "traces.json", active["traces"])

    vlm.chat = chat
    for task, request in selected:
        out = args.root / "mirage" / "planners" / task["setting"] / task["case_id"]
        if not stage_start(out, request, plan, "planner"):
            continue
        active.update(out=out, traces=[], image_index=0)
        record = {
            "request_digest": request["request_digest"],
            "plan_digest": plan["digest"],
            "stage": "planner",
            "seed": 42,
            "parameters": request["parameters"],
            "regions": [],
        }
        started = time.monotonic()
        torch.manual_seed(42)
        fatal = False
        try:
            pairs = parse_instructions(vlm, request["parser_inputs"])
            source = Image.open(request["grounding_image"]).convert("RGB")
            # Each original public unit remains a distinct batch item. Native decomposition can yield any number of pairs.
            flat = []
            images = []
            for unit, items in zip(request["public_units"], pairs, strict=True):
                for ref, instruction in items:
                    image = source.copy()
                    image.info["ifbench_spatial_hint"] = request["grounding_hints"][unit["id"]]
                    flat.append((unit["id"], ref, instruction))
                    images.append(image)
            record["parser_pairs_by_unit"] = dict(
                zip([u["id"] for u in request["public_units"]], pairs, strict=True)
            )
            boxes = vlm.locate(images, [ref for _, ref, _ in flat]) if flat else []
            for (unit_id, ref, instruction), box in zip(flat, boxes, strict=True):
                if box is None:
                    raise ValueError(f"Native locator returned no box for unit {unit_id}: {ref}")
                pixels = to_pixels(box, tuple(request["source"]["size"]), padding=10)
                record["regions"].append(
                    {
                        "unit_id": unit_id,
                        "refer_object": ref,
                        "new_instruction": instruction,
                        "bbox_normalized_xyxy": box,
                        "bbox": dict(zip(("x1", "y1", "x2", "y2"), pixels)),
                    }
                )
            record["status"] = "planned"
        except Exception as exc:
            fatal = fatal_cuda_error(exc)
            record.update(
                status="failed",
                error=repr(exc),
                traceback=traceback.format_exc(),
                fatal_cuda_error=fatal,
            )
        record.update(
            extra_planner_api_calls=len(active["traces"]),
            extra_planner_batch_items=sum(len(t["messages"]) for t in active["traces"]),
            wall_seconds=time.monotonic() - started,
            traces=str(out / "traces.json"),
        )
        save(out / "result.json", record)
        print(
            json.dumps({"case": task, "status": record["status"], "calls": len(active["traces"])}),
            flush=True,
        )
        if fatal:
            raise SystemExit(
                "Stopped worker after CUDA failure; subsequent requests were not started."
            )


def edit(args):
    import numpy as np
    import torch

    plan, selected = tasks(args)
    scratch = args.root / args.model / f"edit-shard{args.shard}-scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    os.chdir(scratch)  # Upstream MICE debug PNG stays in a shard-specific temporary directory.
    if args.model == "mirage":
        sys.path.insert(0, str(SOURCES / "mirage"))
        from mirage.qwen_image_edit import run_qwen_image_edit
        from inference import qwen_prompt
        from diffusers import QwenImageEditPlusPipeline

        pipe = QwenImageEditPlusPipeline.from_pretrained(
            str(MODELS / "Qwen-Image-Edit-2511"), torch_dtype=torch.bfloat16, local_files_only=True
        ).to("cuda")
        transformer = pipe.transformer
    else:
        from samtok_benchmark.ifbench.smoke_adapters import Mice

        adapter = Mice(args.root / "mice")
        pipe = adapter.pipe
        transformer = pipe.transformer
        from flux2.pipeline_utils import create_position_mask_list, resize_mask
    pipe.set_progress_bar_config(disable=True)
    counts = {"transformer_forwards": 0}

    def count(_module, _inputs):
        counts["transformer_forwards"] += 1

    hook = transformer.register_forward_pre_hook(count)
    for task, request in selected:
        out = args.root / args.model / "outputs" / task["setting"] / task["case_id"]
        if not stage_start(out, request, plan, "editor"):
            continue
        record = {
            "request_digest": request["request_digest"],
            "plan_digest": plan["digest"],
            "stage": "editor",
            "seed": 42,
            "inference_api_calls": 0,
            "parameters": request["parameters"],
        }
        counts["transformer_forwards"] = 0
        started = time.monotonic()
        torch.manual_seed(42)
        fatal = False
        generator = torch.Generator("cuda").manual_seed(42)
        torch.cuda.reset_peak_memory_stats()
        try:
            if args.model == "mirage":
                prior = json.loads(
                    (
                        args.root
                        / "mirage"
                        / "planners"
                        / task["setting"]
                        / task["case_id"]
                        / "result.json"
                    ).read_text()
                )
                assert prior["request_digest"] == request["request_digest"]
                if prior["status"] != "planned":
                    raise ValueError(f"Native planning failed: {prior.get('error')}")
                regions = prior["regions"]
                call = {
                    "image": request["edit_image"],
                    "prompt": request["global_original_prompt"],
                    "sub_prompts": [qwen_prompt(r) for r in regions],
                    "bboxes": [r["bbox"] for r in regions],
                    "planner_record": str(
                        args.root
                        / "mirage"
                        / "planners"
                        / task["setting"]
                        / task["case_id"]
                        / "result.json"
                    ),
                }
                save(out / "call.json", call, immutable=True)
                record["inference_api_calls"] = 1
                with torch.inference_mode():
                    raw = run_qwen_image_edit(
                        pipe,
                        Image.open(call["image"]).convert("RGB"),
                        call["prompt"],
                        call["sub_prompts"],
                        call["bboxes"],
                        num_inference_steps=40,
                        true_cfg_scale=4.0,
                        patch_ratio=0.4,
                        generator=generator,
                    )
            else:
                for module in transformer.modules():
                    proc = getattr(module, "processor", None)
                    if hasattr(proc, "clear_cached_masks"):
                        proc.clear_cached_masks()
                w, h = request["model_size"]
                sw, sh = request["source"]["size"]
                image = (
                    Image.open(request["image"])
                    .convert("RGB")
                    .resize((w, h), Image.Resampling.LANCZOS)
                )
                image.save(out / "actual_source.png")
                regional = request["regional_units"]
                specs = []
                if regional and all(u["locator"] == "box" for u in regional):
                    boxes = [
                        [v / d for v, d in zip(u["region"]["coordinates"], (sw, sh, sw, sh))]
                        for u in regional
                    ]
                    kwargs = {"instance_bboxes_xyxy_normalized": boxes}
                    masks = create_position_mask_list(boxes, h, w, 8)
                else:
                    masks = []
                    for unit in regional:
                        if unit["locator"] == "box":
                            box = [
                                v / d
                                for v, d in zip(unit["region"]["coordinates"], (sw, sh, sw, sh))
                            ]
                            mask = create_position_mask_list([box], h, w, 8)[0]
                        else:
                            source_mask = torch.from_numpy(
                                np.array(Image.open(unit["region"]["path"]).convert("L")) > 127
                            ).float()
                            mask = resize_mask(source_mask, h // 16, w // 16)
                        masks.append(mask)
                    kwargs = {"instance_masks_yx": masks}
                for unit, mask in zip(regional, masks, strict=True):
                    path = out / f"binding-{unit['id']}.png"
                    Image.fromarray((mask.cpu().numpy() * 255).astype("uint8")).save(path)
                    specs.append(
                        {
                            "unit_id": unit["id"],
                            "public_modality": unit["locator"],
                            "latent_mask": str(path),
                            "latent_shape": list(mask.shape),
                            "selected_tokens": int(mask.sum()),
                            "sha256": sha256_file(path),
                        }
                    )
                call = {
                    "image": request["image"],
                    "actual_source": str(out / "actual_source.png"),
                    "prompt": request["prompt"],
                    "global_unit_ids": request["global_unit_ids"],
                    "regions": specs,
                    "api_region_argument": next(iter(kwargs)),
                    "model_size": [w, h],
                    "configuration": adapter.configuration,
                }
                save(out / "call.json", call, immutable=True)
                c = adapter.cfg
                record["inference_api_calls"] = 1
                with torch.inference_mode():
                    raw = pipe(
                        image=image,
                        prompt=call["prompt"],
                        height=h,
                        width=w,
                        num_inference_steps=4,
                        guidance_scale=1.0,
                        prompt_settings=c.prompt_settings,
                        attention_setting=c.attention_setting,
                        hard_image_attribute_binding_list_double=c.hard_image_attribute_binding_list_double,
                        hard_image_attribute_binding_list_single=c.hard_image_attribute_binding_list_single,
                        bring_area_to_1024_squared=c.bring_area_to_1024_squared,
                        generator=generator,
                        hard_masking_steps=c.masking_steps,
                        relaxed_timesteps=c.relaxed_timesteps,
                        attention_kwargs={"smooth_P_L": c.smooth_P_L},
                        free_latent=c.free_latent,
                        free_context=c.free_context,
                        free_LC=c.free_LC,
                        **kwargs,
                    ).images[0]
            torch.cuda.synchronize()
            raw.save(out / "raw.png")
            raw.convert("RGB").resize(
                tuple(request["source"]["size"]), Image.Resampling.LANCZOS
            ).save(out / "output.png")
            record.update(
                status="generated",
                raw_size=list(raw.size),
                raw_image=str(out / "raw.png"),
                raw_sha256=sha256_file(out / "raw.png"),
                output_image=str(out / "output.png"),
                output_sha256=sha256_file(out / "output.png"),
            )
        except Exception as exc:
            fatal = fatal_cuda_error(exc)
            record.update(
                status="failed",
                error=repr(exc),
                traceback=traceback.format_exc(),
                fatal_cuda_error=fatal,
            )
        try:
            peak_memory = torch.cuda.max_memory_allocated()
        except Exception as exc:
            peak_memory = None
            record["memory_measurement_error"] = repr(exc)
        record.update(
            transformer_forward_calls=counts["transformer_forwards"],
            wall_seconds=time.monotonic() - started,
            peak_gpu_allocated_bytes=peak_memory,
        )
        save(out / "result.json", record)
        print(
            json.dumps(
                {"case": task, "status": record["status"], "seconds": record["wall_seconds"]}
            ),
            flush=True,
        )
        if fatal:
            raise SystemExit(
                "Stopped worker after CUDA failure; subsequent requests were not started."
            )
    hook.remove()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "planner", "edit"])
    parser.add_argument("--model", choices=["mirage", "mice"], default="mirage")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    args = parser.parse_args()
    args.root = args.root.resolve()
    assert 0 <= args.shard < args.shards
    if args.stage == "prepare":
        prepare(args.root)
    else:
        import torch

        torch.set_num_threads(4)
        save(
            args.root / args.model / f"{args.stage}-shard{args.shard}-environment.json",
            {
                "python": sys.version,
                "torch": torch.__version__,
                "device": torch.cuda.get_device_name(),
                "visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
                "runner_sha256": sha256_file(Path(__file__)),
            },
        )
        if args.stage == "planner":
            if args.model != "mirage":
                raise ValueError("MICE has no native planner")
            plan_mirage(args)
        else:
            edit(args)


if __name__ == "__main__":
    main()
