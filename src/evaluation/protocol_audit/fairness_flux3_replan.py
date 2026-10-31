"""Fairness review helpers; CPU contracts by default, GPU runners only on explicit use.

This module never changes the registered tiered_v1 runs or scores. CPU contracts
execute upstream function bodies with a spy in place of neural inference; they
are not image-generation or quality tests.
"""

from __future__ import annotations

import argparse
import ast
from contextlib import nullcontext
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageOps
from samtok_benchmark.paths import repository_root


REPO = repository_root()
SOURCES = Path("/tmp/ifbench/protocol_review_20261027/sources")
SHARED = Path("/tmp/ifbench/tiered_v1/shared_inputs_20261027")
OUT = Path("/tmp/ifbench/fairness_v2_20261030")
MODELS = Path("/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models")
CASES = ("v2-sa_10063996", "v2-sa_7414116")
SETTINGS = (
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
)
REPLAN_ANNOTATION_HEADER = (
    "This is an annotated copy of the source image. Use the colored marks and U labels only to identify the selected source regions. "
    "The marks, labels, and leader lines are not scene objects or editing targets. "
    "Plan the requested edits for the clean source image with the same dimensions and coordinates."
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def request(model, case_id, setting, *, shared_root=None):
    """Build one fixed mapping using only the approved public input forms."""
    if str(REPO / "src") not in sys.path:
        sys.path.insert(0, str(REPO / "src"))
    from samtok_benchmark.ifbench.public import verify
    from samtok_benchmark.io import digest

    directory = Path(shared_root or SHARED) / "requests" / setting / case_id
    public = json.loads((directory / "public.json").read_text())
    inputs = json.loads((directory / "inputs.json").read_text())
    verify(public, assets=True)
    assert inputs["digest"] == digest({k: v for k, v in inputs.items() if k != "digest"})
    assert inputs["public_input_digest"] == public["input_digest"]
    if inputs["annotation"]:
        annotation = inputs["annotation"]
        assert sha(annotation["path"]) == annotation["sha256"]
        assert annotation["transform"] == {"scale_xy": [1, 1], "offset_xy": [0, 0]}
        with Image.open(annotation["path"]) as image:
            assert list(image.size) == public["source"]["size"] == annotation["size"]
    form = inputs["forms"]["dual" if model == "flux3" else "single"]
    prompt = form["prompt"]
    if model == "flux3" and setting == "S1":
        # Preserve the already tested native S1 wording exactly, without boxes.
        prompt = (
            "Edit <ref_image_0>. "
            + " ".join(u["instruction"] for u in public["units"])
            + " Keep everything else unchanged."
        )
    if model == "replan" and setting != "S1":
        first_line, rest = prompt.split("\n", 1)
        assert (
            first_line
            == "Edit the supplied image using its colored marks and U labels to identify the selected regions. Remove all marks, labels, and leader lines from the final edited image."
        )
        prompt = REPLAN_ANNOTATION_HEADER + "\n" + rest
    common = {
        "model": model,
        "case_id": case_id,
        "setting": setting,
        "public_input_digest": public["input_digest"],
        "public_request": str(directory / "public.json"),
        "images": list(form["images"]),
        "prompt": prompt,
        "seed": 42,
        "provenance": "approved public source, public instructions and deterministic annotation only",
        "external_components": [],
        "quality_selection": False,
    }
    if model == "flux3":
        common.update(
            configuration_id="fairness-v2-dual-no-box-schema",
            boxes=None,
            parameters={
                "model": "distilled",
                "steps": 16,
                "guidance": None,
                "pup": False,
                "safety": False,
            },
            expected_component_calls={"planner": 0, "rewriter": 0, "diffusion_trajectory": 1},
        )
    elif model == "replan":
        planner_image, editor_image = form["images"][0], public["source"]["path"]
        common.update(
            configuration_id="fairness-v2-annotation-planner-clean-editor",
            images=list(dict.fromkeys([editor_image, planner_image])),
            planner_image=planner_image,
            editor_image=editor_image,
            image_sha256={p: sha(p) for p in dict.fromkeys([editor_image, planner_image])},
            parameters={
                "expand_value": 0.0,
                "attention_switch_step": 0.5,
                "num_inference_steps": 40,
                "true_cfg_scale": 4.0,
                "guidance_scale": 1.0,
                "negative_prompt": " ",
            },
            planner_template=str(SOURCES / "replan/replan/pipelines/prompt_template/replan.txt"),
            expected_component_calls={
                "native_planner": 1,
                "external_rewriter": 0,
                "diffusion_trajectory": 1,
            },
            planner_and_editor_receive_same_image=setting == "S1",
            image_routing="one annotated image to native planner; original clean image to native editor",
            annotation_header_only_replacement=setting != "S1",
        )
    else:
        raise ValueError(model)
    assert all(u["instruction"] in prompt for u in public["units"])
    return common


class Flux3FairnessRunner:
    """Official generate/Pipeline, no upsampler and no invented object table."""

    def __init__(self):
        os.environ["WEIGHTS_DIR"] = str(MODELS)
        sys.path.insert(0, str(SOURCES / "flux3/src"))
        from flux3.generate import generate
        from flux3.pipeline import Pipeline

        self.generate_fn = generate
        self.models = SimpleNamespace(
            upsampler=None,
            pipeline=Pipeline(
                {"distilled": str(MODELS / "flux-3-image-klein")},
                str(MODELS / "flux-3-image-klein/text_encoder"),
                str(MODELS / "flux-3-image-klein/ae.safetensors"),
            ),
        )

    def run(self, call):
        image, metadata = self.generate_fn(
            self.models,
            prompt=call["prompt"],
            images=[Image.open(p).convert("RGB") for p in call["images"]],
            boxes=None,
            seed=call["seed"],
            **call["parameters"],
        )
        return image, {
            "generation_metadata": metadata,
            "actual_component_calls": {"diffusion_trajectory": 1, "pup": 0},
        }


class ReplanFairnessRunner:
    """Official planning and editing APIs, with a clean image at the editor boundary.

    The subclass only loads the same planner weights with the available SDPA
    backend. It preserves native prompt construction, generate arguments, response
        parsing and editor execution. Unlike edit_single, the annotation is replaced
        by its same-coordinate clean source before editing. Stage CPU offload is an upstream
    option and avoids simultaneously holding both neural models on the GPU.
    """

    def __init__(self):
        import torch
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

        sys.path.insert(0, str(SOURCES / "replan"))
        from replan.pipelines.replan import RePlanPipeline

        class AvailableBackend(RePlanPipeline):
            def _init_vlm(self):
                if self.vlm_model is not None and self.processor is not None:
                    return
                self.vlm_model = (
                    Qwen2_5_VLForConditionalGeneration.from_pretrained(
                        self.vlm_ckpt_path,
                        torch_dtype=self.torch_dtype,
                        attn_implementation="sdpa",
                        local_files_only=True,
                    )
                    .to(self._target_device())
                    .eval()
                )
                self.processor = AutoProcessor.from_pretrained(
                    self.vlm_ckpt_path, local_files_only=True
                )

        self.pipe = AvailableBackend(
            vlm_ckpt_path="/tmp/ifbench/weights/RePlan-Qwen2.5-VL-7B",
            diffusion_model_name=str(MODELS / "Qwen-Image-Edit-2511"),
            pipeline_type="qwen2511",
            init_vlm=True,
            device="cuda",
            torch_dtype=torch.bfloat16,
            stage_offload="cpu",
            output_dir=None,
        )
        self.pipe.diffusion_pipe.set_progress_bar_config(disable=True)
        self.last_trace = []
        original = self.pipe.get_vlm_response

        def traced(instruction, image, collect_latency=False):
            entry = {"instruction": instruction, "status": "admitted"}
            self.last_trace.append(entry)
            result = original(instruction, image, collect_latency=collect_latency)
            entry.update(status="returned", response=result[0])
            return result

        self.pipe.get_vlm_response = traced

    def run(self, call):
        import torch

        self.last_trace = []
        torch.manual_seed(call["seed"])
        planner_image = Image.open(call["planner_image"]).convert("RGB")
        source = Image.open(call["editor_image"]).convert("RGB")
        assert planner_image.size == source.size
        response, _, planner_seconds = self.pipe.get_vlm_response(
            call["prompt"], planner_image, collect_latency=True
        )
        kwargs = dict(call["parameters"])
        expand = kwargs.pop("expand_value")
        switch = kwargs.pop("attention_switch_step")
        image, _, result = self.pipe.region_edit_with_attention(
            source,
            call["prompt"],
            response,
            skip_save=True,
            collect_latency=True,
            expand_value=expand,
            attention_switch_step=switch,
            pipeline_kwargs={
                "generator": torch.Generator("cuda").manual_seed(call["seed"]),
                **kwargs,
            },
        )
        result.pop("edited_image", None)
        return image, {
            "native_result": result,
            "planner_trace": self.last_trace,
            "native_planner_seconds": planner_seconds,
            "actual_component_calls": {
                "native_planner": len(self.last_trace),
                "diffusion_trajectory": 1,
            },
            "engineering_deviations": [
                "Planner full-attention backend SDPA replaces unavailable FlashAttention2; no numerical equivalence claim."
            ],
            "stage_offload": "cpu",
        }


class ReplanPlannerOnlyRunner:
    """Native planning API without loading editor weights; for a separate GPU phase."""

    def __init__(self):
        import torch
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

        sys.path.insert(0, str(SOURCES / "replan"))
        from replan.pipelines.replan import RePlanPipeline

        self.pipe = RePlanPipeline.__new__(RePlanPipeline)
        self.pipe.init_vlm = True
        self.pipe.stage_offload = "none"
        self.pipe.sync_cuda_for_timing = True
        self.pipe.device = "cuda"
        self.pipe.image_dir = None
        checkpoint = "/tmp/ifbench/weights/RePlan-Qwen2.5-VL-7B"
        self.pipe.vlm_model = (
            Qwen2_5_VLForConditionalGeneration.from_pretrained(
                checkpoint,
                torch_dtype=torch.bfloat16,
                attn_implementation="sdpa",
                local_files_only=True,
            )
            .to("cuda")
            .eval()
        )
        self.pipe.processor = AutoProcessor.from_pretrained(checkpoint, local_files_only=True)
        self.pipe.template = (
            SOURCES / "replan/replan/pipelines/prompt_template/replan.txt"
        ).read_text()
        self.last_trace = []
        self.trace_callback = None
        self.current_call = None
        original_messages = self.pipe.build_messages
        original_generate = self.pipe.vlm_model.generate

        def trace_messages(instruction, image):
            messages = original_messages(instruction, image)
            serial = []
            for message in messages:
                content = []
                for part in message["content"]:
                    if part["type"] == "image":
                        content.append(
                            {
                                "type": "image",
                                "image": self.current_call["planner_image"],
                                "sha256": sha(self.current_call["planner_image"]),
                                "size": list(image.size),
                            }
                        )
                    else:
                        content.append(dict(part))
                serial.append({"role": message["role"], "content": content})
            self.last_trace.append({"event": "messages", "messages": serial})
            self._emit()
            return messages

        def trace_generate(*args, **kwargs):
            entry = {
                "event": "native_generate",
                "status": "admitted",
                "seed": self.current_call["seed"],
                "max_new_tokens": kwargs.get("max_new_tokens"),
                "input_shapes": {
                    k: list(v.shape) for k, v in kwargs.items() if hasattr(v, "shape")
                },
            }
            self.last_trace.append(entry)
            self._emit()
            try:
                result = original_generate(*args, **kwargs)
                entry["status"] = "returned"
                self._emit()
                return result
            except Exception as error:
                entry.update(status="failed", error=repr(error))
                self._emit()
                raise

        self.pipe.build_messages = trace_messages
        self.pipe.vlm_model.generate = trace_generate

    def _emit(self):
        if self.trace_callback is not None:
            self.trace_callback(self.last_trace)

    def run(self, call, trace_callback=None):
        import torch

        self.last_trace = []
        self.trace_callback = trace_callback
        self.current_call = call
        torch.manual_seed(call["seed"])
        image = Image.open(call["planner_image"]).convert("RGB")
        try:
            response, _, seconds = self.pipe.get_vlm_response(
                call["prompt"], image, collect_latency=True
            )
        except Exception as error:
            self.last_trace.append({"event": "native_planner_failed", "error": repr(error)})
            self._emit()
            raise
        self.last_trace.append({"event": "decoded_response", "response": response})
        self._emit()
        # Preserve whatever the native method returns; do not impose K regions
        # or repair/retry the plan using GT or another language model.
        return {
            "status": "native-response-returned",
            "response": response,
            "public_input_digest": call["public_input_digest"],
            "prompt": call["prompt"],
            "configuration_id": call["configuration_id"],
            "seed": call["seed"],
            "planner_image": call["planner_image"],
            "planner_image_sha256": sha(call["planner_image"]),
            "template_sha256": sha(call["planner_template"]),
            "native_planner_seconds": seconds,
            "native_planner_calls": 1,
            "trace": self.last_trace,
            "engineering_deviations": [
                "SDPA instead of unavailable FlashAttention2; same planner weights and native generation options."
            ],
        }


class ReplanEditorOnlyRunner:
    """Native editor with an immutable, provenance-bound native planner response."""

    def __init__(self):
        import torch

        sys.path.insert(0, str(SOURCES / "replan"))
        from replan.pipelines.replan import RePlanPipeline

        self.pipe = RePlanPipeline(
            diffusion_model_name=str(MODELS / "Qwen-Image-Edit-2511"),
            pipeline_type="qwen2511",
            init_vlm=False,
            device="cuda",
            torch_dtype=torch.bfloat16,
            output_dir=None,
        )
        self.pipe.diffusion_pipe.set_progress_bar_config(disable=True)

    def run(self, call, plan):
        import torch

        assert plan["public_input_digest"] == call["public_input_digest"]
        assert plan["prompt"] == call["prompt"] and plan["seed"] == call["seed"]
        assert plan["configuration_id"] == call["configuration_id"]
        assert plan["planner_image_sha256"] == sha(call["planner_image"])
        assert plan["template_sha256"] == sha(call["planner_template"])
        source = Image.open(call["editor_image"]).convert("RGB")
        with Image.open(call["planner_image"]) as p:
            assert p.size == source.size
        torch.manual_seed(call["seed"])
        kwargs = dict(call["parameters"])
        expand = kwargs.pop("expand_value")
        switch = kwargs.pop("attention_switch_step")
        image, _, result = self.pipe.region_edit_with_attention(
            source,
            call["prompt"],
            plan["response"],
            skip_save=True,
            collect_latency=True,
            expand_value=expand,
            attention_switch_step=switch,
            pipeline_kwargs={
                "generator": torch.Generator("cuda").manual_seed(call["seed"]),
                **kwargs,
            },
        )
        result.pop("edited_image", None)
        return image, {
            "native_result": result,
            "native_planner_record": plan,
            "actual_component_calls": {
                "native_planner": 0,
                "cached_native_planner": 1,
                "diffusion_trajectory": 1,
            },
            "response_preserved": result["vlm_response"] == plan["response"],
        }


def _extract(path, function_names, namespace, class_methods=()):
    """Compile unmodified upstream AST function bodies, without neural imports."""
    tree = ast.parse(path.read_text())
    nodes = [
        n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in function_names
    ]
    if class_methods:
        original = next(
            n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RePlanPipeline"
        )
        nodes.append(
            ast.ClassDef(
                name="RePlanContract",
                bases=[],
                keywords=[],
                body=[
                    n
                    for n in original.body
                    if isinstance(n, ast.FunctionDef) and n.name in class_methods
                ],
                decorator_list=[],
            )
        )
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(module, str(path), "exec"), namespace)


def contracts():
    """No model weights, GPU or Judge calls; upstream data-flow contract checks."""
    OUT.mkdir(parents=True, exist_ok=True)
    splits = json.loads((SHARED / "plan/splits.json").read_text())
    assert set(CASES) <= set(splits["dev"])
    tasks = [request(m, c, s) for m in ("flux3", "replan") for c in CASES for s in SETTINGS]
    all_public_checks = []
    for model in ("flux3", "replan"):
        for cid in sorted(splits["dev"]):
            for setting in SETTINGS:
                call = request(model, cid, setting)
                assert all(Path(p).is_file() for p in call["images"])
                all_public_checks.append((model, cid, setting))

    ns = {
        "math": math,
        "np": np,
        "Image": Image,
        "ImageOps": ImageOps,
        "DOWNSAMPLING_RATIO": 16,
        "MATCH_MAX_PIXELS": 4 * 1024 * 1024,
        "MIN_SIDE": 64,
        "MAX_SIDE": 4096,
        "MULTI_REFERENCE_MAX_PIXELS": 1024 * 1024,
    }
    pipeline = SOURCES / "flux3/src/flux3/pipeline.py"
    _extract(
        pipeline,
        {
            "_ceil16",
            "reference_canvas",
            "prepare_reference",
            "prepare_multi_reference",
            "default_size",
        },
        ns,
    )
    box_ns = {"json": json, "re": re, "SCALE": 1000, "ID": re.compile(r"[A-Za-z][A-Za-z0-9_]*")}
    box_tree = ast.parse((SOURCES / "flux3/src/flux3/bbox.py").read_text())
    names = {n.name for n in box_tree.body if isinstance(n, ast.FunctionDef)}
    _extract(SOURCES / "flux3/src/flux3/bbox.py", names, box_ns)
    ns.update(
        json=json,
        hashlib=hashlib,
        MAX_REFERENCES=10,
        MODELS={"distilled": {"steps": 16, "guidance": None}},
        bbox=SimpleNamespace(**{k: v for k, v in box_ns.items() if callable(v)}),
    )
    _extract(SOURCES / "flux3/src/flux3/generate.py", {"generate"}, ns)
    flux_checks = []
    for call in (t for t in tasks if t["model"] == "flux3"):
        captured = {}

        def spy(model, caption, images, width, height, steps, guidance, seed):
            captured.update(
                caption=caption,
                image_sizes=[list(i.size) for i in images],
                width=width,
                height=height,
                steps=steps,
                guidance=guidance,
                seed=seed,
            )
            return images[0]  # CPU fixture only, not saved or represented as a model output.

        models = SimpleNamespace(upsampler=None, pipeline=SimpleNamespace(generate=spy))
        _, meta = ns["generate"](
            models,
            prompt=call["prompt"],
            images=[Image.open(p).convert("RGB") for p in call["images"]],
            boxes=None,
            seed=42,
            **call["parameters"],
        )
        assert captured["caption"] == call["prompt"]
        assert meta["boxes"] is None and meta["upsampled"] is False
        assert captured["steps"] == 16 and captured["guidance"] is None
        flux_checks.append(
            {
                "case_id": call["case_id"],
                "setting": call["setting"],
                "prompt_passed_unchanged": True,
                "boxes": None,
                "upsampled": False,
                "reference_sizes_after_official_preprocessing": captured["image_sizes"],
            }
        )

    rns = {
        "re": re,
        "json": json,
        "os": os,
        "time": time,
        "Image": Image,
        "torch": SimpleNamespace(manual_seed=lambda x: "cpu-contract-generator"),
        "datetime": __import__("datetime").datetime,
    }
    rpath = SOURCES / "replan/replan/pipelines/replan.py"
    _extract(
        rpath,
        {"expand_key_to_split", "generate_default_attention_rules"},
        rns,
        {
            "build_messages",
            "extract_bbox_from_response",
            "extract_gen_image_prompt",
            "expand_bbox",
            "region_edit_with_attention",
            "edit_single",
        },
    )
    obj = rns["RePlanContract"]()
    obj._ensure_vlm_initialized = lambda: None
    obj._stage_offload_enabled = lambda: False
    obj._time_block = lambda do_timing: nullcontext(None)
    obj.template = (SOURCES / "replan/replan/pipelines/prompt_template/replan.txt").read_text()
    obj.pipeline_type = "qwen2511"
    obj.empty_cuda_cache = False
    obj.output_dir = None
    replan_checks = []
    for call in (t for t in tasks if t["model"] == "replan"):
        source = Image.open(call["planner_image"]).convert("RGB")
        clean = Image.open(call["editor_image"]).convert("RGB")
        assert source.size == clean.size
        messages = obj.build_messages(call["prompt"], source)
        assert len(messages[0]["content"]) == 2
        assert messages[0]["content"][0]["image"] is source
        assert messages[0]["content"][1]["text"] == obj.template + "\n" + call["prompt"]
        # Reuse a real saved S1 planner answer as a parser/data-flow fixture;
        # this does not claim that the planner generated it for this setting.
        oldplan = json.loads(
            (
                SHARED.parent / "dev_selection/planners/replan" / (call["case_id"] + "--S1.json")
            ).read_text()
        )
        response = oldplan["groups"][0]["response"]
        captured = {}

        def planner_spy(instruction, image, collect_latency=False):
            captured["planner_image"] = image
            return response, image

        def editor_spy(**kwargs):
            captured["editor_image"] = kwargs["image"]
            captured["region_guidance"] = kwargs["region_guidance"]
            captured["global_prompt"] = kwargs["prompt"]
            return SimpleNamespace(images=[kwargs["image"]])

        obj.get_vlm_response = planner_spy
        obj.diffusion_pipe = editor_spy
        result = obj.edit_single(
            source,
            call["prompt"],
            skip_save=True,
            generator="contract-no-inference",
            **call["parameters"],
        )
        assert captured["planner_image"] is source
        assert captured["editor_image"].tobytes() == source.tobytes()
        assert captured["global_prompt"] == obj.extract_gen_image_prompt(response)
        assert result["vlm_response"] == response
        original_guidance = captured["region_guidance"]
        # Proposed two-stage route uses the identical native response and
        # parameters. Only the same-coordinate editor image is clean.
        response2, processed = obj.get_vlm_response(call["prompt"], source)
        kwargs = dict(call["parameters"])
        expand = kwargs.pop("expand_value")
        switch = kwargs.pop("attention_switch_step")
        _, _, separate = obj.region_edit_with_attention(
            clean,
            call["prompt"],
            response2,
            skip_save=True,
            expand_value=expand,
            attention_switch_step=switch,
            pipeline_kwargs={"generator": "contract-no-inference", **kwargs},
        )
        assert captured["editor_image"].tobytes() == clean.tobytes()
        assert separate["vlm_response"] == response
        assert captured["region_guidance"] == original_guidance
        replan_checks.append(
            {
                "case_id": call["case_id"],
                "setting": call["setting"],
                "message_image_count": 1,
                "official_edit_single_same_image_contract": True,
                "two_stage_clean_editor_pixels_confirmed": True,
                "two_stage_response_global_prompt_and_region_guidance_unchanged": True,
                "planner_and_editor_dimensions_identical": True,
                "native_template_preserved": True,
                "response_preserved": True,
                "fixture_only_not_current_planner_inference": True,
            }
        )

    artifact = {
        "schema": "ifbench-fairness-flux3-replan-cpu-contract-v1",
        "model_inference_calls": 0,
        "judge_calls": 0,
        "public_request_checks": len(all_public_checks),
        "tasks": tasks,
        "flux3_contracts": flux_checks,
        "replan_contracts": replan_checks,
        "source_sha256": {
            str(p): sha(p) for p in (pipeline, rpath, SOURCES / "flux3/src/flux3/generate.py")
        },
        "test_kind": "Unmodified upstream function bodies; neural boundaries replaced by explicit spies. No generated image artifacts.",
        "limits": [
            "Does not establish neural understanding of visual marks or output quality.",
            "New mappings are not old candidate score reuse, except separately verified S1.",
        ],
    }
    target = OUT / "flux3_replan_cpu_contracts.json"
    target.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "artifact": str(target),
                "public_checks": len(all_public_checks),
                "flux3_contracts": len(flux_checks),
                "replan_contracts": len(replan_checks),
                "model_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts", action="store_true", required=True)
    parser.parse_args()
    contracts()
