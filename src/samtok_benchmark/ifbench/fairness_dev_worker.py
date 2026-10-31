"""One GPU worker for the approved fixed-method, 20-image fairness dev run.

The plan module owns scientific identity and exact historical-cache validation.
This worker owns durable attempts, native generation, traces, and accounting.
It never builds prompts, selects candidates, calls a Judge, freezes, or retries
an admitted request without a terminal record. Imports of GPU libraries are
delayed until the first uncached request that actually needs inference.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import importlib
import inspect
import json
import os
from pathlib import Path
import sys
import time
import traceback

from PIL import Image

from samtok_benchmark.io import digest, sha256_file, write_json

MODELS = ("qwen2511", "qwen21", "flux3", "replan", "mirage", "mice", "flux2_klein9b")
PLANNERS = {"replan", "mirage"}
TERMINAL = {"generated", "planned", "native-response-returned", "failed", "failed-planner"}
COUNT_KEYS = (
    "inference_api_calls",
    "native_planner_calls",
    "extra_planner_api_calls",
    "extra_planner_batch_items",
    "transformer_forward_calls",
)


class UnresolvedAttempt(RuntimeError):
    """An earlier process may already have sampled; automatic retry is forbidden."""


class MissingDependency(RuntimeError):
    """The native planner phase has not supplied a terminal record yet."""


def read(path):
    return json.loads(Path(path).read_text())


def immutable(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if read(path) != value:
            raise ValueError(f"Immutable record differs: {path}")
        return
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def fatal_cuda_error(error):
    return any(
        s in str(error).lower()
        for s in (
            "device-side assert",
            "illegal memory access",
            "misaligned address",
            "unspecified launch failure",
            "cuda error:",
            "cublas_status_execution_failed",
        )
    )


@contextmanager
def task_lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "worker.lock").open("a+") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise UnresolvedAttempt(f"Another worker owns this request: {directory}") from error
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def binding(plan, task, stage):
    return {
        "plan_digest": plan["digest"],
        "task_id": task.get("task_id", task["key"]),
        "key": task["key"],
        "model": task["model"],
        "case_id": task["case_id"],
        "setting": task["setting"],
        "stage": stage,
        "seed": plan["seed"],
        "scientific_digest": task["scientific_digest"],
        "request_sha256": task["request_sha256"],
        "public_digest": task["public_digest"],
    }


def verify_existing(result, expected):
    for key, value in expected.items():
        if result.get(key) != value:
            raise ValueError(f"Existing result binding mismatch: {key}")
    if result.get("status") not in TERMINAL:
        raise UnresolvedAttempt("Existing result is not a recognized terminal state")
    for key, hash_key in (
        ("output_image", "output_sha256"),
        ("raw_image", "raw_sha256"),
        ("traces", "traces_sha256"),
    ):
        if result.get(key) and result.get(hash_key):
            if sha256_file(Path(result[key])) != result[hash_key]:
                raise ValueError(f"Existing artifact changed: {key}")
    if result["status"] == "generated" and not result.get("output_sha256"):
        raise ValueError("Generated record has no output hash")


def reused_result(payload, expected, receipt):
    """Keep historical cost separate from this run's zero new model calls."""
    if payload.get("status") not in TERMINAL:
        raise ValueError("Cache verifier returned a nonterminal payload")
    old_cost = {
        k: payload.get("reuse_original_metrics", {}).get(
            k, payload.get("reused_" + k, payload.get(k))
        )
        for k in COUNT_KEYS
        if k in payload or "reused_" + k in payload
    }
    value = {
        **payload,
        **expected,
        "reused": True,
        "cache_receipt": str(receipt),
        "reuse_original_metrics": old_cost,
        "additional_inference_calls": 0,
        "wall_seconds": 0.0,
        "load_seconds": 0.0,
    }
    value.update({k: 0 for k in COUNT_KEYS})
    return value


def planner_dependency(plan, task):
    path = Path(task["planner_dir"]) / "result.json"
    if not path.exists():
        raise MissingDependency(f"Native planner has not completed: {path}")
    result = read(path)
    verify_existing(result, binding(plan, task, "planner"))
    return result, path


class NativeBackend:
    """The already verified native calls, with paths injected by the bundle."""

    def __init__(self, model, stage, plan, worker_dir):
        import torch

        self.torch = torch
        torch.set_num_threads(4)
        self.model, self.stage = model, stage
        self.sources = Path(plan["paths"]["sources"])
        self.weights = Path(plan["paths"]["models"])
        self.worker_dir = Path(worker_dir)
        self.metrics = {}
        self.partial_detail = {}
        self.last_trace = []
        self.trace_out = None
        self.hooks = []
        self.transformers = []
        self.configuration = {}
        if model in {"flux3", "replan"}:
            helper = importlib.import_module("evaluation.protocol_audit.fairness_flux3_replan")
            helper.SOURCES, helper.MODELS = self.sources, self.weights
            if model == "flux3":
                self.runner = helper.Flux3FairnessRunner()
                self.transformers = list(self.runner.models.pipeline.dits.values())
            elif stage == "planner":
                alias = Path("/tmp/ifbench/weights/RePlan-Qwen2.5-VL-7B")
                expected = Path(plan["paths"]["replan_planner_weights"])
                if alias.resolve() != expected.resolve():
                    raise ValueError(
                        "RePlan native helper's checkpoint alias differs from the plan"
                    )
                self.runner = helper.ReplanPlannerOnlyRunner()
            else:
                self.runner = helper.ReplanEditorOnlyRunner()
                self.transformers = [self.runner.pipe.diffusion_pipe.transformer]
        elif model in {"qwen2511", "qwen21", "mice"}:
            suite = importlib.import_module("samtok_benchmark.ifbench.smoke_suite")
            adapters = importlib.import_module("samtok_benchmark.ifbench.smoke_adapters")
            suite.MODELS, suite.SOURCES = self.weights, self.sources
            adapters.MODELS, adapters.SOURCES = self.weights, self.sources
            if model == "qwen2511":
                old = importlib.import_module("samtok_benchmark.ifbench.dev_runner")
                self.adapter = old.Qwen2511(worker_dir)
            elif model == "qwen21":
                execution = plan["model_specifications"][model].get("execution", {})
                self.adapter = adapters.Qwen21(
                    worker_dir, memory_policy=execution.get("memory_policy", "resident")
                )
            else:
                self.adapter = adapters.Mice(worker_dir)
            self.pipe = self.adapter.pipe
            self.transformers = list(self.adapter.transformers)
            self.configuration = self.adapter.configuration
            if model == "qwen21":
                # The actual call already forwards request parameters. Keep
                # the load/configuration ledger aligned with that fixed plan.
                self.configuration.update(plan["model_specifications"][model]["parameters"])
            if model == "mice":
                from .fairness_dev_revision import verify_mice_native_defaults

                verify_mice_native_defaults(self.pipe)
                utils = importlib.import_module("flux2.pipeline_utils")
                self.create_position_mask_list, self.resize_mask = (
                    utils.create_position_mask_list,
                    utils.resize_mask,
                )
        elif model == "flux2_klein9b":
            from diffusers import Flux2KleinPipeline

            pinned = (
                self.sources / "diffusers/src/diffusers/pipelines/flux2/pipeline_flux2_klein.py"
            )
            installed = Path(inspect.getfile(Flux2KleinPipeline))
            if sha256_file(installed) != sha256_file(pinned):
                raise ValueError("FLUX2 pipeline differs from the audited source")
            checkpoint = self.weights / "FLUX.2-klein-9B"
            index = read(checkpoint / "model_index.json")
            if (
                index.get("_class_name") != "Flux2KleinPipeline"
                or index.get("is_distilled") is not True
            ):
                raise ValueError("FLUX2 requires the approved distilled 9B weights")
            self.pipe = Flux2KleinPipeline.from_pretrained(
                str(checkpoint), torch_dtype=torch.bfloat16, local_files_only=True
            ).to("cuda")
            self.pipe.set_progress_bar_config(disable=True)
            self.transformers = [self.pipe.transformer]
            self.configuration = {
                "pipeline_sha256": sha256_file(installed),
                "model_index_sha256": sha256_file(checkpoint / "model_index.json"),
            }
        elif model == "mirage":
            sys.path.insert(0, str(self.sources / "mirage"))
            if stage == "planner":
                native = importlib.import_module("mirage.vlm")
                self.parse_instructions, self.to_pixels = (
                    native.parse_instructions,
                    native.to_pixels,
                )
                self.vlm = native.load_vlm(
                    "qwen35", str(self.weights / "Qwen3.5-9B"), "cuda", torch.bfloat16
                )
                self._trace_mirage()
            else:
                from diffusers import QwenImageEditPlusPipeline

                native = importlib.import_module("mirage.qwen_image_edit")
                self.run_qwen_image_edit = native.run_qwen_image_edit
                self.qwen_prompt = importlib.import_module("inference").qwen_prompt
                self.pipe = QwenImageEditPlusPipeline.from_pretrained(
                    str(self.weights / "Qwen-Image-Edit-2511"),
                    torch_dtype=torch.bfloat16,
                    local_files_only=True,
                ).to("cuda")
                self.pipe.set_progress_bar_config(disable=True)
                self.transformers = [self.pipe.transformer]
        else:
            raise ValueError(model)
        for module in self.transformers:
            self.hooks.append(module.register_forward_pre_hook(self._count))

    def _count(self, *_):
        self.metrics["transformer_forward_calls"] = (
            self.metrics.get("transformer_forward_calls", 0) + 1
        )

    def environment(self):
        return {
            "torch": self.torch.__version__,
            "gpu": self.torch.cuda.get_device_name(),
            "configuration": self.configuration,
        }

    def reset(self):
        self.metrics = {k: 0 for k in COUNT_KEYS}
        self.partial_detail = {}
        self.last_trace = []
        self.torch.manual_seed(42)
        self.torch.cuda.reset_peak_memory_stats()
        self.torch.cuda.synchronize()

    def memory(self):
        try:
            return {
                "peak_gpu_allocated_bytes": self.torch.cuda.max_memory_allocated(),
                "peak_gpu_reserved_bytes": self.torch.cuda.max_memory_reserved(),
            }
        except Exception as error:
            return {
                "peak_gpu_allocated_bytes": None,
                "peak_gpu_reserved_bytes": None,
                "memory_measurement_error": repr(error),
            }

    def synchronize(self):
        self.torch.cuda.synchronize()

    def close(self):
        for hook in self.hooks:
            hook.remove()

    def _trace_mirage(self):
        native_chat, native_messages = self.vlm.chat, self.vlm.grounding_messages

        def messages(image, phrase, mode):
            result = native_messages(image, phrase, mode)
            hint = image.info.get("ifbench_spatial_hint", "")
            if hint:
                result[-1]["content"].append({"type": "text", "text": hint})
            return result

        def serialize(value, number):
            if isinstance(value, Image.Image):
                path = (
                    self.trace_out
                    / "trace_images"
                    / f"call{number:03d}-image{self.image_index:03d}.png"
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                value.save(path)
                self.image_index += 1
                return {
                    "path": str(path),
                    "sha256": sha256_file(path),
                    "size": list(value.size),
                    "public_hint": value.info.get("ifbench_spatial_hint", ""),
                }
            if isinstance(value, list):
                return [serialize(item, number) for item in value]
            if isinstance(value, dict):
                return {key: serialize(item, number) for key, item in value.items()}
            return value

        def chat(batch, max_new_tokens=512):
            number = len(self.last_trace)
            trace = {
                "index": number,
                "messages": serialize(batch, number),
                "max_new_tokens": max_new_tokens,
                "do_sample": False,
                "status": "started",
                "started_at_unix": time.time(),
            }
            self.last_trace.append(trace)
            self.metrics["extra_planner_api_calls"] += 1
            self.metrics["extra_planner_batch_items"] += len(batch)
            self.metrics["native_planner_calls"] += 1
            write_json(self.trace_out / "traces.json", self.last_trace)
            try:
                response = native_chat(batch, max_new_tokens)
                trace.update(status="returned", response=response)
                return response
            except Exception as error:
                trace.update(status="failed", error=repr(error))
                raise
            finally:
                trace["finished_at_unix"] = time.time()
                write_json(self.trace_out / "traces.json", self.last_trace)

        self.vlm.grounding_messages, self.vlm.chat = messages, chat

    def _mirage_plan(self, request, out):
        self.trace_out, self.image_index = out, 0
        pairs = self.parse_instructions(self.vlm, request["parser_inputs"])
        source = Image.open(request["grounding_image"]).convert("RGB")
        flat, images = [], []
        for unit, items in zip(request["public_units"], pairs, strict=True):
            for refer, instruction in items:
                image = source.copy()
                image.info["ifbench_spatial_hint"] = request["grounding_hints"][unit["id"]]
                flat.append((unit["id"], refer, instruction))
                images.append(image)
        record = {
            "parser_pairs_by_unit": dict(
                zip([u["id"] for u in request["public_units"]], pairs, strict=True)
            ),
            "regions": [],
        }
        self.partial_detail = record
        # Preserve all native decompositions; no equality-to-benchmark-K guard.
        boxes = self.vlm.locate(images, [refer for _, refer, _ in flat]) if flat else []
        for (unit_id, refer, instruction), box in zip(flat, boxes, strict=True):
            if box is None:
                raise ValueError(f"Native locator returned no box for unit {unit_id}: {refer}")
            pixels = self.to_pixels(box, tuple(request["source"]["size"]), padding=10)
            record["regions"].append(
                {
                    "unit_id": unit_id,
                    "refer_object": refer,
                    "new_instruction": instruction,
                    "bbox_normalized_xyxy": box,
                    "bbox": dict(zip(("x1", "y1", "x2", "y2"), pixels)),
                }
            )
        return None, {**record, "status": "planned"}

    def preflight(self, request, public, out):
        """Validate text before admitting any potentially sampled attempt."""
        if self.model == "qwen21":
            for name, value in request["parameters"].items():
                if request.get("resolution_policy") and name in {"width", "height"}:
                    continue  # verified against the public canvas by the plan contract
                if self.configuration.get(name) != value:
                    raise ValueError(f"Qwen21 request differs from fixed configuration: {name}")
        if self.model != "mice":
            return
        from .fairness_dev_revision import mice_text_audit, MiceTextOverflow

        if self.adapter.cfg.prompt_settings != "outer_local_prompts":
            raise ValueError("MICE requires the approved native outer_local_prompts flow")
        try:
            text_check = mice_text_audit(
                self.pipe.tokenizer, request["prompt"], 1 + len(request["regional_units"])
            )
        except MiceTextOverflow as error:
            immutable(out / "text_condition_check.json", error.audit)
            self.partial_detail = {"text_condition_check": error.audit}
            raise
        immutable(out / "text_condition_check.json", text_check)

    def _mice_edit(self, request, out):
        import numpy as np

        text_check = read(out / "text_condition_check.json")
        if text_check["prompt_digest"] != digest(request["prompt"]):
            raise ValueError("MICE prompt changed after input preflight")

        torch = self.torch
        for module in self.pipe.transformer.modules():
            processor = getattr(module, "processor", None)
            if hasattr(processor, "clear_cached_masks"):
                processor.clear_cached_masks()
        w, h = request["model_size"]
        sw, sh = request["source"]["size"]
        image = Image.open(request["image"]).convert("RGB").resize((w, h), Image.Resampling.LANCZOS)
        image.save(out / "actual_source.png")
        regional, specs = request["regional_units"], []
        if regional and all(unit["locator"] == "box" for unit in regional):
            boxes = [
                [
                    value / denominator
                    for value, denominator in zip(unit["region"]["coordinates"], (sw, sh, sw, sh))
                ]
                for unit in regional
            ]
            kwargs = {"instance_bboxes_xyxy_normalized": boxes}
            masks = self.create_position_mask_list(boxes, h, w, 8)
        else:
            masks = []
            for unit in regional:
                if unit["locator"] == "box":
                    box = [
                        value / denominator
                        for value, denominator in zip(
                            unit["region"]["coordinates"], (sw, sh, sw, sh)
                        )
                    ]
                    mask = self.create_position_mask_list([box], h, w, 8)[0]
                else:
                    source = torch.from_numpy(
                        np.array(Image.open(unit["region"]["path"]).convert("L")) > 127
                    ).float()
                    mask = self.resize_mask(source, h // 16, w // 16)
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
            "configuration": self.adapter.configuration,
            "text_condition_check": text_check,
        }
        immutable(out / "call.json", call)
        c = self.adapter.cfg
        self.metrics["inference_api_calls"] = 1
        raw = self.pipe(
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
            generator=torch.Generator("cuda").manual_seed(42),
            hard_masking_steps=c.masking_steps,
            relaxed_timesteps=c.relaxed_timesteps,
            attention_kwargs={"smooth_P_L": c.smooth_P_L},
            free_latent=c.free_latent,
            free_context=c.free_context,
            free_LC=c.free_LC,
            **kwargs,
        ).images[0]
        return raw, {}

    def run(self, request, public, out, native_plan=None):
        torch = self.torch
        with torch.inference_mode():
            if self.model == "mirage" and self.stage == "planner":
                immutable(out / "call.json", request)
                return self._mirage_plan(request, out)
            if self.model == "replan" and self.stage == "planner":
                immutable(out / "call.json", request)

                def trace_callback(trace):
                    self.last_trace = trace
                    calls = sum(t.get("event") == "native_generate" for t in trace)
                    self.metrics.update(
                        native_planner_calls=calls,
                        extra_planner_api_calls=calls,
                        extra_planner_batch_items=calls,
                    )
                    write_json(out / "traces.json", trace)

                detail = self.runner.run(request, trace_callback=trace_callback)
                return None, detail
            if self.model == "mice":
                return self._mice_edit(request, out)
            if self.model == "mirage":
                regions = native_plan["regions"]
                call = {
                    "image": request["edit_image"],
                    "prompt": request["global_original_prompt"],
                    "sub_prompts": [self.qwen_prompt(r) for r in regions],
                    "bboxes": [r["bbox"] for r in regions],
                    "planner_record": str(
                        Path(out).parents[2]
                        / "planners"
                        / out.parent.name
                        / out.name
                        / "result.json"
                    ),
                }
                immutable(out / "call.json", call)
                self.metrics["inference_api_calls"] = 1
                raw = self.run_qwen_image_edit(
                    self.pipe,
                    Image.open(call["image"]).convert("RGB"),
                    call["prompt"],
                    call["sub_prompts"],
                    call["bboxes"],
                    num_inference_steps=40,
                    true_cfg_scale=4.0,
                    patch_ratio=0.4,
                    generator=torch.Generator("cuda").manual_seed(42),
                )
                return raw, {}
            if self.model == "flux2_klein9b":
                expected = {
                    "num_inference_steps": 4,
                    "guidance_scale": 1.0,
                    "max_sequence_length": 512,
                }
                if request.get("resolution_policy"):
                    expected.update(zip(("width", "height"), public["source"]["size"]))
                if (
                    request["parameters"] != expected
                    or request["weight_revision"] != "92196c8e11f7b6cf2b7493e037d8c5345c559216"
                ):
                    raise ValueError(
                        "FLUX2 scientific configuration differs from the approved probe"
                    )
                text = self.pipe.tokenizer.apply_chat_template(
                    [{"role": "user", "content": request["prompt"]}],
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=False,
                )
                tokens = self.pipe.tokenizer(text, add_special_tokens=True, truncation=False)[
                    "input_ids"
                ]
                if len(tokens) > 512:
                    raise ValueError(
                        "Complete task exceeds the native 512-token limit; no inference was called"
                    )
                call = {
                    **request,
                    "images_sha256": [sha256_file(Path(p)) for p in request["images"]],
                    "input_token_count_before_padding": len(tokens),
                    **self.configuration,
                }
                immutable(out / "call.json", call)
                self.metrics["inference_api_calls"] = 1
                raw = self.pipe(
                    image=[Image.open(p).convert("RGB") for p in request["images"]],
                    prompt=request["prompt"],
                    generator=torch.Generator("cuda").manual_seed(42),
                    **request["parameters"],
                ).images[0]
                return raw, {}
            immutable(out / "call.json", request)
            self.metrics["inference_api_calls"] = 1
            if self.model in {"qwen2511", "qwen21"}:
                return self.adapter.generate(request, out)
            if self.model == "replan":
                return self.runner.run(request, native_plan)
            return self.runner.run(request)


def run_worker(plan_path, model, stage, shard=0, shards=1, *, plan_api=None, backend_factory=None, node_id=None):
    """Run one fixed shard; injection is only for CPU durability/contract tests."""
    if model not in MODELS or stage not in {"planner", "edit"}:
        raise ValueError("Unknown model or stage")
    if stage == "planner" and model not in PLANNERS:
        raise ValueError(f"{model} has no enabled native planner")
    if not 0 <= shard < shards:
        raise ValueError("Invalid shard")
    api = plan_api or importlib.import_module("samtok_benchmark.ifbench.fairness_dev_plan")
    plan = api.load_plan(Path(plan_path))
    if plan["seed"] != 42:
        raise ValueError("The approved seed is 42")
    tasks = plan["tasks"]
    if node_id is not None:
        from .full_plan import SCHEMA as FULL_SCHEMA, node_tasks
        if plan.get("schema") != FULL_SCHEMA:
            raise ValueError("Node selection is permitted only by a whole-release plan")
        tasks = node_tasks(plan, node_id)
    selected = [task for task in tasks if task["model"] == model][shard::shards]
    if any(task["case_id"] not in plan["case_ids"] for task in selected):
        raise ValueError("Task outside the registered evaluation source set")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + f"-{os.getpid()}"
    worker = (
        (Path(plan["results_root"]) / "nodes" / f"node-{node_id}" if node_id is not None else Path(plan["results_root"]))
        / "workers"
        / model
        / stage
        / f"shard-{shard}-of-{shards}"
        / run_id
    )
    worker.mkdir(parents=True, exist_ok=False)
    scratch = worker / "scratch"
    scratch.mkdir()
    previous_cwd = Path.cwd()
    os.chdir(scratch)
    worker_state = {
        "plan_digest": plan["digest"],
        "model": model,
        "stage": stage,
        "shard": shard,
        "shards": shards,
        "pid": os.getpid(),
        "python": sys.version,
        "visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "runner_sha256": sha256_file(Path(__file__)),
        "selected": len(selected),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "completed": 0,
        "reused": 0,
        "already_terminal": 0,
        "failed": 0,
        "status": "running",
        "model_loads": 0,
    }
    write_json(worker / "environment.json", worker_state)
    write_json(worker / "status.json", worker_state)
    runtime, load_seconds, load_record = None, 0.0, None
    factory = backend_factory or NativeBackend
    worker_start = time.monotonic()
    try:
        for task in selected:
            request, public = api.verify_task(plan, task)
            out = Path(task["planner_dir"] if stage == "planner" else task["output_dir"])
            expected = binding(plan, task, stage)
            with task_lock(out):
                target = out / "result.json"
                if target.exists():
                    verify_existing(read(target), expected)
                    worker_state["already_terminal"] += 1
                    write_json(worker / "status.json", worker_state)
                    continue
                if (out / "started.json").exists():
                    raise UnresolvedAttempt(
                        f"Prior attempt lacks a terminal result; no automatic retry: {out}"
                    )
                cached = api.verify_cache(plan, task, stage)
                if cached is not None:
                    value = reused_result(cached, expected, task.get("cache", {}).get(stage))
                    verify_existing(value, expected)
                    immutable(target, value)
                    worker_state["reused"] += 1
                    worker_state["completed"] += 1
                    write_json(worker / "status.json", worker_state)
                    continue
                native_plan, planner_path = None, None
                if model in PLANNERS and stage == "edit":
                    native_plan, planner_path = planner_dependency(plan, task)
                    success = "planned" if model == "mirage" else "native-response-returned"
                    if native_plan["status"] != success:
                        immutable(
                            target,
                            {
                                **expected,
                                "status": "failed-planner",
                                "reused": False,
                                "planner_record": str(planner_path),
                                "planner_result_sha256": sha256_file(planner_path),
                                "error": native_plan.get("error", "Native planner did not succeed"),
                                **{k: 0 for k in COUNT_KEYS},
                                "wall_seconds": 0.0,
                            },
                        )
                        worker_state["failed"] += 1
                        worker_state["completed"] += 1
                        write_json(worker / "status.json", worker_state)
                        continue
                if runtime is None:
                    loading = time.monotonic()
                    load_record = worker / "load.json"
                    write_json(load_record, {"status": "loading", "started_at_unix": time.time()})
                    try:
                        runtime = factory(model, stage, plan, worker)
                        runtime.synchronize()
                    except Exception as error:
                        write_json(
                            load_record,
                            {
                                "status": "failed",
                                "seconds": time.monotonic() - loading,
                                "error": repr(error),
                                "traceback": traceback.format_exc(),
                                "inference_api_calls": 0,
                            },
                        )
                        raise
                    load_seconds = time.monotonic() - loading
                    worker_state["model_loads"] = 1
                    write_json(
                        load_record,
                        {
                            "status": "loaded",
                            "seconds": load_seconds,
                            **runtime.environment(),
                            **runtime.memory(),
                        },
                    )
                    write_json(worker / "status.json", worker_state)
                if hasattr(runtime, "preflight"):
                    try:
                        runtime.preflight(request, public, out)
                    except Exception as error:
                        immutable(
                            target,
                            {
                                **expected,
                                "status": "failed",
                                "reused": False,
                                "parameters": request.get("parameters", {}),
                                "request_path": task["request_path"],
                                "failure_stage": "input_preflight",
                                "attempt_admitted": False,
                                "error": repr(error),
                                "error_type": type(error).__name__,
                                "traceback": traceback.format_exc(),
                                "text_condition_check": getattr(error, "audit", None),
                                "load_record": str(load_record),
                                "load_seconds": load_seconds,
                                "wall_seconds": 0.0,
                                **{k: 0 for k in COUNT_KEYS},
                            },
                        )
                        worker_state["failed"] += 1
                        worker_state["completed"] += 1
                        write_json(worker / "status.json", worker_state)
                        continue
                immutable(
                    out / "started.json",
                    {
                        **expected,
                        "pid": os.getpid(),
                        "time": time.time(),
                        "worker_directory": str(worker),
                    },
                )
                result = {
                    **expected,
                    "reused": False,
                    "parameters": request.get("parameters", {}),
                    "request_path": task["request_path"],
                    "load_seconds": load_seconds,
                    "load_record": str(load_record),
                    **{k: 0 for k in COUNT_KEYS},
                }
                if task.get("repair_of"):
                    result["repair_of"] = task["repair_of"]
                if planner_path:
                    result.update(
                        planner_record=str(planner_path),
                        planner_result_sha256=sha256_file(planner_path),
                    )
                tick, fatal = time.monotonic(), False
                try:
                    runtime.reset()
                    raw, detail = runtime.run(request, public, out, native_plan)
                    result.update(detail)
                    runtime.synchronize()
                    if stage == "edit":
                        raw.save(out / "raw.png")
                        if plan.get("canvas_policy"):
                            from .canvas import restore_output

                            transform = read(task["canvas_transform"])
                            output = restore_output(raw, transform)
                            result.update(canvas_transform=transform, input_size=public["source"]["size"])
                        else:
                            output = raw.convert("RGB").resize(
                                tuple(public["source"]["size"]), Image.Resampling.LANCZOS
                            )
                        output.save(out / "output.png")
                        result.update(
                            status="generated",
                            raw_size=list(raw.size),
                            raw_image=str(out / "raw.png"),
                            raw_sha256=sha256_file(out / "raw.png"),
                            output_image=str(out / "output.png"),
                            output_sha256=sha256_file(out / "output.png"),
                        )
                    if result.get("status") not in TERMINAL:
                        raise RuntimeError("Native method returned no terminal state")
                except Exception as error:
                    fatal = fatal_cuda_error(error)
                    result.update(
                        status="failed",
                        error=repr(error),
                        error_type=type(error).__name__,
                        traceback=traceback.format_exc(),
                        fatal_cuda_error=fatal,
                    )
                finally:
                    if result.get("status") == "failed":
                        result.update(getattr(runtime, "partial_detail", {}))
                    result.update(runtime.metrics)
                    result.update(runtime.memory())
                    result["wall_seconds"] = time.monotonic() - tick
                    if (out / "traces.json").exists():
                        result.update(
                            traces=str(out / "traces.json"),
                            traces_sha256=sha256_file(out / "traces.json"),
                        )
                    immutable(target, result)
                    worker_state["completed"] += 1
                    if result["status"].startswith("failed"):
                        worker_state["failed"] += 1
                    worker_state["last_task"] = task["key"]
                    write_json(worker / "status.json", worker_state)
                    print(
                        json.dumps(
                            {
                                "task": task["key"],
                                "stage": stage,
                                "status": result["status"],
                                "seconds": result["wall_seconds"],
                            }
                        ),
                        flush=True,
                    )
                if fatal:
                    raise RuntimeError(
                        "Fatal CUDA state; current failure saved and later requests unattempted"
                    )
        worker_state["status"] = "complete"
    except Exception as error:
        worker_state.update(
            status="blocked"
            if isinstance(error, (UnresolvedAttempt, MissingDependency))
            else "failed",
            error=repr(error),
            traceback=traceback.format_exc(),
        )
        raise
    finally:
        worker_state.update(
            wall_seconds=time.monotonic() - worker_start,
            finished_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        write_json(worker / "status.json", worker_state)
        try:
            if runtime is not None:
                runtime.close()
        finally:
            os.chdir(previous_cwd)
    return worker_state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--stage", choices=("planner", "edit"), required=True)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    args = parser.parse_args()
    state = run_worker(args.plan, args.model, args.stage, args.shard, args.shards)
    print(json.dumps(state, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
