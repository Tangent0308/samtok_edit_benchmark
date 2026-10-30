"""Resumable, instrumented Qwen-2511 smoke on approved public dev inputs only."""

from __future__ import annotations

import argparse
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import time
import traceback

from PIL import Image

from samtok_benchmark.io import digest, sha256_file, write_json
from . import GENERATION_SEED, SETTINGS
from .public import verify

MODEL_REVISION = "6f3ccc0b56e431dc6a0c2b2039706d7d26f22cb9"
DIFFUSERS_REVISION = "06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a"
MODEL_ROOT = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/Qwen-Image-Edit-2511"
)
SOURCE_ROOT = Path("/tmp/ifbench/protocol_review_20261027/sources/diffusers/src/diffusers")
PARAMETERS = {
    "num_inference_steps": 40,
    "true_cfg_scale": 4.0,
    "guidance_scale": 1.0,
    "negative_prompt": " ",
    "num_images_per_prompt": 1,
    "max_sequence_length": 512,
}


def load_task(task, shared):
    directory = shared / "requests" / task["setting"] / task["case_id"]
    request = json.loads((directory / "public.json").read_text())
    verify(request, assets=True)
    inputs = json.loads((directory / "inputs.json").read_text())
    if inputs["digest"] != digest({k: v for k, v in inputs.items() if k != "digest"}):
        raise ValueError("Approved input payload changed")
    if inputs["public_input_digest"] != request["input_digest"]:
        raise ValueError("Public/request binding mismatch")
    form = inputs["forms"][task["form"]]
    if (
        inputs["annotation"]
        and sha256_file(Path(inputs["annotation"]["path"])) != inputs["annotation"]["sha256"]
    ):
        raise ValueError("Approved annotation changed")
    return request, form


def semantic_key(task, shared):
    request, form = load_task(task, shared)
    return digest(
        {
            "images": [sha256_file(Path(p)) for p in form["images"]],
            "prompt": form["prompt"],
            "parameters": PARAMETERS,
            "seed": GENERATION_SEED,
            "model_revision": MODEL_REVISION,
            "diffusers_revision": DIFFUSERS_REVISION,
            "output_size": request["source"]["size"],
        }
    )


def prepare(shared, output):
    if not output.resolve().is_relative_to(Path("/tmp/ifbench")):
        raise ValueError("Smoke outputs must remain in /tmp/ifbench")
    gate = json.loads((shared / "gate.json").read_text())
    if gate["state"] != "approved":
        raise ValueError("Shared-input review has not been approved")
    split = json.loads((shared / "plan/splits.json").read_text())
    case_ids = json.loads((shared / "example_selection.json").read_text())["case_ids"]
    if not set(case_ids) <= set(split["dev"]):
        raise ValueError("Smoke may use only dev")
    tasks = []
    for cid in case_ids:
        for setting in SETTINGS:
            tasks.append(
                {
                    "id": f"{cid}--{setting}--dual",
                    "case_id": cid,
                    "setting": setting,
                    "form": "dual",
                }
            )
    for form in ("single", "coordinates"):
        for cid in case_ids:
            tasks.append(
                {
                    "id": f"{cid}--S3-mask--{form}",
                    "case_id": cid,
                    "setting": "S3-mask",
                    "form": form,
                }
            )
    aliases = []
    for cid in case_ids:
        source = next(t for t in tasks if t["case_id"] == cid and t["setting"] == "S1")
        for setting in ("S2-point", "S2-box", "S2-mask"):
            task = {
                "id": f"{cid}--{setting}--discard-region",
                "case_id": cid,
                "setting": setting,
                "form": "discard-region",
            }
            if semantic_key(task, shared) != semantic_key(source, shared):
                raise ValueError("S2 discard input is not actually identical to S1")
            aliases.append(
                {
                    **task,
                    "reuse_task": source["id"],
                    "reuse_reason": "identical image bytes, prompt, model, parameters and seed",
                    "semantic_key": semantic_key(task, shared),
                }
            )
    plan = {
        "model": "Qwen-Image-Edit-2511",
        "model_revision": MODEL_REVISION,
        "diffusers_revision": DIFFUSERS_REVISION,
        "shared_root": str(shared),
        "shared_split_digest": split["digest"],
        "parameters": PARAMETERS,
        "seed": GENERATION_SEED,
        "tasks": tasks,
        "aliases": aliases,
        "quality_selection": False,
        "purpose": "API, geometry and visible behavior smoke; no judge or candidate scoring",
    }
    plan["digest"] = digest(plan)
    path = output / "plan.json"
    if path.exists() and json.loads(path.read_text()) != plan:
        raise ValueError("Smoke plan differs; cannot overwrite an existing run")
    write_json(path, plan)
    return plan


def worker(shared, output, shard, shards):
    import torch
    import diffusers
    import transformers
    from diffusers import QwenImageEditPlusPipeline
    from diffusers.pipelines.qwenimage.pipeline_qwenimage_edit_plus import (
        calculate_dimensions,
        CONDITION_IMAGE_SIZE,
    )

    torch.set_num_threads(4)
    plan = json.loads((output / "plan.json").read_text())
    if plan["digest"] != digest({k: v for k, v in plan.items() if k != "digest"}):
        raise ValueError("Smoke plan digest mismatch")
    pipeline_file = Path(inspect.getfile(QwenImageEditPlusPipeline))
    audited = SOURCE_ROOT / "pipelines/qwenimage/pipeline_qwenimage_edit_plus.py"
    if sha256_file(pipeline_file) != sha256_file(audited):
        raise ValueError("Installed pipeline differs from audited commit; stop before inference")
    if plan["parameters"] != PARAMETERS or plan["model_revision"] != MODEL_REVISION:
        raise ValueError("Prepared model configuration differs from this worker")
    tasks = plan["tasks"][shard::shards]
    env = {
        "python": os.sys.version,
        "torch": torch.__version__,
        "diffusers": diffusers.__version__,
        "transformers": transformers.__version__,
        "pipeline_sha256": sha256_file(pipeline_file),
        "pipeline_file": str(pipeline_file),
        "device": torch.cuda.get_device_name(0),
        "visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "worker_source_sha256": sha256_file(Path(__file__)),
        "diffusers_direct_url": importlib.metadata.distribution("diffusers").read_text(
            "direct_url.json"
        ),
    }
    write_json(output / f"worker{shard}.environment.json", env)
    load_start = time.monotonic()
    print(json.dumps({"worker": shard, "stage": "loading", "tasks": len(tasks)}), flush=True)
    pipe = QwenImageEditPlusPipeline.from_pretrained(
        str(MODEL_ROOT), torch_dtype=torch.bfloat16, local_files_only=True
    ).to("cuda")
    pipe.set_progress_bar_config(disable=True)
    torch.cuda.synchronize()
    write_json(
        output / f"worker{shard}.load.json",
        {
            "elapsed_seconds": time.monotonic() - load_start,
            "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        },
    )
    state = {}

    def transformer_hook(module, args, kwargs):
        state["transformer_forward_calls"] += 1
        if not state["transformer_shapes"]:
            state["transformer_shapes"] = {
                k: list(kwargs[k].shape)
                for k in ("hidden_states", "encoder_hidden_states")
                if k in kwargs
            }

    def text_hook(module, args, kwargs):
        state["text_encoder_forward_calls"] += 1
        state["encoded_token_lengths"].append(int(kwargs["input_ids"].shape[-1]))
        grid = kwargs.get("image_grid_thw")
        state["image_grid_thw"].append(grid.detach().cpu().tolist() if grid is not None else None)

    hooks = [
        pipe.transformer.register_forward_pre_hook(transformer_hook, with_kwargs=True),
        pipe.text_encoder.register_forward_pre_hook(text_hook, with_kwargs=True),
    ]
    for task in tasks:
        directory = output / "runs" / task["id"]
        directory.mkdir(parents=True, exist_ok=True)
        record_path = directory / "result.json"
        if record_path.exists():
            previous = json.loads(record_path.read_text())
            if previous.get("plan_digest") != plan["digest"]:
                raise ValueError("Existing result binding differs")
            if previous.get("status") == "generated":
                if sha256_file(Path(previous["output_image"])) != previous["output_sha256"]:
                    raise ValueError("Cached output changed")
                print(json.dumps({"id": task["id"], "stage": "reused-completed"}), flush=True)
                continue
            raise RuntimeError(
                "Previous failure requires explicit diagnosis; not automatically resampling"
            )
        request, form = load_task(task, shared)
        images = [Image.open(p).convert("RGB") for p in form["images"]]
        condition = []
        for i, im in enumerate(images):
            w, h = calculate_dimensions(CONDITION_IMAGE_SIZE, im.width / im.height)
            p = directory / f"condition_{i + 1}.png"
            pipe.image_processor.resize(im, h, w).save(p)
            condition.append(
                {
                    "path": str(p),
                    "size": [w, h],
                    "scope": "actual pipeline resize before the processor applies its patch-grid alignment",
                }
            )
        call = {
            "task": task,
            "plan_digest": plan["digest"],
            "input_digest": request["input_digest"],
            "images": [
                {"path": p, "sha256": sha256_file(Path(p)), "size": list(im.size)}
                for p, im in zip(form["images"], images, strict=True)
            ],
            "prompt": form["prompt"],
            "parameters": PARAMETERS,
            "seed": GENERATION_SEED,
            "height_width_policy": "official auto resolution/aspect; no custom crop or pad",
            "source_size": request["source"]["size"],
            "condition_preprocessor_images": condition,
        }
        write_json(directory / "call.json", call)
        (directory / "prompt.txt").write_text(form["prompt"] + "\n")
        state.clear()
        state.update(
            transformer_forward_calls=0,
            text_encoder_forward_calls=0,
            encoded_token_lengths=[],
            image_grid_thw=[],
            denoising_steps=0,
            transformer_shapes={},
        )

        def callback(pipeline, index, timestep, kwargs):
            state["denoising_steps"] += 1
            return kwargs

        torch.manual_seed(GENERATION_SEED)
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        started = time.monotonic()
        event_start = torch.cuda.Event(enable_timing=True)
        event_end = torch.cuda.Event(enable_timing=True)
        record = {
            "task": task,
            "plan_digest": plan["digest"],
            "worker": shard,
            "device": env["device"],
            "visible_devices": env["visible_devices"],
            "inference_api_calls": 0,
            "extra_component_calls": {
                "rewriter": 0,
                "planner": 0,
                "reflection": 0,
                "external_grounder": 0,
                "sam": 0,
            },
        }
        print(
            json.dumps({"id": task["id"], "stage": "inference-start", "images": len(images)}),
            flush=True,
        )
        try:
            event_start.record()
            record["inference_api_calls"] += 1
            with torch.inference_mode():
                raw = pipe(
                    image=images,
                    prompt=form["prompt"],
                    generator=torch.Generator("cuda").manual_seed(GENERATION_SEED),
                    callback_on_step_end=callback,
                    **PARAMETERS,
                ).images[0]
            event_end.record()
            torch.cuda.synchronize()
            record["pipeline_wall_seconds"] = time.monotonic() - started
            record["cuda_event_elapsed_seconds"] = event_start.elapsed_time(event_end) / 1000
            raw.save(directory / "raw.png")
            out = raw.convert("RGB").resize(
                tuple(request["source"]["size"]), Image.Resampling.LANCZOS
            )
            out.save(directory / "output.png")
            record.update(
                status="generated",
                raw_size=list(raw.size),
                output_size=list(out.size),
                output_image=str(directory / "output.png"),
                output_sha256=sha256_file(directory / "output.png"),
                raw_sha256=sha256_file(directory / "raw.png"),
                resize="PIL LANCZOS; no crop, pad, or paste-back",
            )
        except Exception as error:
            record.update(
                status="failed",
                error=repr(error),
                traceback=traceback.format_exc(),
                pipeline_wall_seconds=time.monotonic() - started,
            )
            traceback.print_exc()
        record.update(
            **state,
            peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated(),
            peak_gpu_reserved_bytes=torch.cuda.max_memory_reserved(),
        )
        write_json(record_path, record)
        print(
            json.dumps(
                {
                    "id": task["id"],
                    "stage": record["status"],
                    "seconds": record["pipeline_wall_seconds"],
                }
            ),
            flush=True,
        )
        if record["status"] != "generated":
            raise RuntimeError(
                "Smoke failed; stop this worker for diagnosis without changing protocol"
            )
    for hook in hooks:
        hook.remove()
    write_json(
        output / f"worker{shard}.total.json",
        {
            "worker_wall_seconds": time.monotonic() - load_start,
            "scope": "one-GPU worker: model load through final output save",
            "shard": shard,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "worker"])
    parser.add_argument(
        "--shared", type=Path, default=Path("/tmp/ifbench/tiered_v1/shared_inputs_20261027")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("/tmp/ifbench/tiered_v1/smoke/qwen2511")
    )
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=4)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(Path("/tmp/ifbench")):
        raise ValueError("Smoke artifacts must stay under /tmp/ifbench")
    if args.action == "prepare":
        p = prepare(args.shared.resolve(), args.output.resolve())
        print(
            json.dumps(
                {
                    "inference_requests": len(p["tasks"]),
                    "identical_input_aliases": len(p["aliases"]),
                    "digest": p["digest"],
                }
            )
        )
    else:
        worker(args.shared.resolve(), args.output.resolve(), args.shard, args.shards)


if __name__ == "__main__":
    main()
