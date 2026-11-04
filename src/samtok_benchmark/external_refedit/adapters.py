"""Thin adapters to pinned native methods. No scoring annotation (mask, single-object instruction, category) is
accepted here: every method receives the shared ~1MP canvas and the original ``editing_instruction`` only."""

from __future__ import annotations

from pathlib import Path
import time

import numpy as np
from PIL import Image

from .data import immutable, verify_public

POLICY = "ifbench.canvas.1mp.v1"
# FLUX.3 refers to its input image by name; IF-Bench's frozen FLUX.3 requests use the same prefix.
FLUX3_PREFIX = "Edit <ref_image_0>. "


def native_request(model, public, config):
    verify_public(public)
    image = public["source"]["path"]
    prompt = public["instruction"]
    spec = config["model_specifications"][model]
    params = dict(spec["parameters"])
    width, height = public["source"]["size"]
    common = {"source": public["source"], "images": [image], "prompt": prompt, "seed": 42,
              "public_input_digest": public["input_digest"], "configuration_id": "refedit-native-text-v1",
              "parameters": params}
    if model in {"qwen2511", "qwen21"}:
        common["resolution_policy"] = POLICY
        params.update(width=width, height=height)
    elif model == "replan":
        # These configure the native planner/seed, rather than diffusion pipeline kwargs.
        params.pop("seed", None)
        params.pop("native_planner_max_new_tokens", None)
        common.update(planner_image=image, editor_image=image,
                      planner_template=str(Path(config["paths"]["sources"]) /
                                           "replan/replan/pipelines/prompt_template/replan.txt"))
    elif model == "mirage":
        # One whole original instruction; the native parser decides its own split.
        common.update(parser_inputs=[prompt], public_units=[{"id": "composite"}],
                      grounding_image=image, grounding_hints={"composite": ""},
                      edit_image=image, global_original_prompt=prompt)
    elif model == "flux3":
        common.update(prompt=FLUX3_PREFIX + prompt, boxes=None, resolution_policy=POLICY,
                      external_components=[], quality_selection=False)
        params.update(width=width, height=height)
    elif model == "flux2_klein9b":
        common.update(weight_revision=spec["weight_revision"], resolution_policy=POLICY)
        params.update(width=width, height=height)
    elif model == "mice":
        # Text-only RefEdit request: one global unit and no regional binding (IF-Bench S1 form).
        unit = {"id": "U1", "instruction": prompt, "has_ref": True, "locator": "none", "region": None}
        common.update(image=image, public_units=[unit], global_unit_ids=["U1"], regional_units=[],
                      global_original_prompt=prompt, annotation=None, model_size=[width, height],
                      resolution_policy=POLICY)
    else:
        raise ValueError(model)
    return common


class Native:
    def __init__(self, model, stage, config, root):
        from samtok_benchmark.ifbench.fairness_dev_worker import NativeBackend

        self.model = model
        self.config = config
        self.backend = NativeBackend(model, "planner" if stage == "plan" else "edit", config, root)

    def run(self, public, out, previous=None):
        request = native_request(self.model, public, self.config)
        self.backend.reset()
        self.backend.preflight(request, public, out)
        result, detail = self.backend.run(request, public, out, native_plan=previous)
        self.backend.synchronize()
        return result, {"native": detail, "calls": dict(self.backend.metrics),
                        "memory": self.backend.memory(), "environment": self.backend.environment()}


class MirageEditor(Native):
    """The frozen IF-Bench backend fixes MIRA's patch ratio 0.4; RefEdit-Bench uses the authors' 0.2 (pinned README).
    Everything else is the backend's native call: original instruction as global prompt, native local prompts and
    boxes from the saved plan, Qwen2511, 40 steps, true CFG 4, seed 42."""

    def run(self, public, out, previous=None):
        import torch

        request = native_request("mirage", public, self.config)
        params = self.config["model_specifications"]["mirage"]["parameters"]
        backend = self.backend
        backend.reset()
        regions = previous["regions"]
        call = {"image": request["edit_image"], "prompt": request["global_original_prompt"],
                "sub_prompts": [backend.qwen_prompt(r) for r in regions], "bboxes": [r["bbox"] for r in regions],
                "num_inference_steps": params["num_inference_steps"], "true_cfg_scale": params["true_cfg_scale"],
                "patch_ratio": params["patch_ratio"], "seed": 42}
        immutable(out / "call.json", call)
        backend.metrics["inference_api_calls"] = 1
        with torch.inference_mode():
            raw = backend.run_qwen_image_edit(
                backend.pipe, Image.open(call["image"]).convert("RGB"), call["prompt"], call["sub_prompts"],
                call["bboxes"], num_inference_steps=call["num_inference_steps"],
                true_cfg_scale=call["true_cfg_scale"], patch_ratio=call["patch_ratio"],
                generator=torch.Generator("cuda").manual_seed(42))
        backend.synchronize()
        return raw, {"native": {"regions": len(regions)}, "calls": dict(backend.metrics),
                     "memory": backend.memory(), "environment": backend.environment()}


class SITTokens:
    """Pass1: one grounder request for the single public unit U1."""

    def __init__(self, config):
        from samtok_edit21.evaluation.ifbench import Pass1Models

        self.method = config["sitedit"]
        self.models = Pass1Models(self.method)
        self.models.grounder, self.models.codec   # load now, so that load time is not charged to the first case

    def run(self, public, out, previous=None):
        from samtok_edit21.pass1.protocol import VERSION, valid_span, validate_request

        verify_public(public)
        request = {"protocol": VERSION, "coordinate_system": "normalized_0_1000",
                   "targets": [{"label": "U1", "instruction": public["instruction"], "has_ref": True,
                                "locator": "none"}]}
        validate_request(request)
        image = Image.open(public["source"]["path"]).convert("RGB")
        tick = time.monotonic()
        answer = self.models.grounder.ground(image, request, max_new_tokens=self.method["pass1_max_new_tokens"])
        ground_seconds = time.monotonic() - tick
        span = answer["parsed"]["spans"].get("U1")
        valid = bool(span and valid_span(span))
        tick = time.monotonic()
        decoded_area = None
        if valid:
            # Offline diagnostics only. These pixels are not consumed by SITEdit's editor.
            decoded = self.models.codec.decode_strict(image.convert("RGBA"), span)[0] > 0
            decoded_area = float(decoded.mean())
            Image.fromarray(np.asarray(decoded, dtype=np.uint8) * 255).save(out / "U1.png")
        unit = {"id": "U1", "token": span if valid else None, "source": "pass1" if valid else "fallback_text",
                "decoded_area": decoded_area}
        return None, {"native": {"units": [unit], "request": request, "raw": answer["raw"],
                                  "parsed": answer["parsed"], "ground_seconds": ground_seconds,
                                  "diagnostic_decode_seconds": time.monotonic() - tick,
                                  "fallback_units": int(not valid)},
                      "calls": {"grounder_requests": 1, "codec_encode": 0, "diagnostic_codec_decode": int(valid)}}


def sitedit_prompt(public, tokens):
    """Training's single-target form: the bare sentence with its token (round2.py: multi_edit_prompt only for >1)."""
    from .placement import place

    unit = tokens["units"][0]
    if unit["token"]:
        prompt, placement = place(public["instruction"], unit["token"])
        return prompt, placement, True
    return public["instruction"], None, False


class SITEditor:
    def __init__(self, config):
        from samtok_edit21.models.adapters import load_grounding_adapter
        from samtok_edit21.models.codec import load_codec
        from samtok_edit21.models.pipeline import load_pipeline

        self.method = config["sitedit"]
        self.pipe = load_pipeline(self.method["qwen"], self.method["samtok"], device="cuda")
        codec = load_codec(self.method["samtok"], "cuda")
        load_grounding_adapter(self.pipe, codec, self.method["dit_adapter"])
        self.pipe.eval()

    def run(self, public, out, previous=None):
        import torch
        from samtok_edit21.data.protocol import strip_tokens
        from samtok_edit21.models.pipeline import edit

        verify_public(public)
        prompt, placement, guided = sitedit_prompt(public, previous)
        guided = guided and self.method["token_guidance"] != 1.0
        width, height = public["source"]["size"]
        params = {"num_inference_steps": self.method["steps"], "seed": 42,
                  "width": width, "height": height, "use_kv_cache": True,
                  "cfg_scale": self.method["token_guidance"] if guided else 1.0,
                  "mode": "inline" if placement else "direct", "pass2_te": "raw"}
        if guided:
            params["negative_prompt"] = strip_tokens(prompt)
        immutable(out / "call.json", {"images": [public["source"]], "prompt": prompt, "parameters": params,
                                       "placement": placement, "fallback_units": previous["fallback_units"],
                                       "dit_adapter": self.method["dit_adapter"]})
        image = Image.open(public["source"]["path"]).convert("RGBA")
        # Fresh compile state per request: the FlexAttention kernels depend on the shapes this process has seen.
        torch._dynamo.reset()
        with torch.inference_mode():
            raw, report = edit(self.pipe, prompt, [image], **params)
        if raw.size != (width, height):
            raise ValueError("SITEdit returned an unexpected canvas size")
        return raw, {"native": report, "fallback_units": previous["fallback_units"], "placement": placement,
                     "calls": {"inference_api_calls": 1,
                               "expected_dit_forwards": self.method["steps"] * (2 if guided else 1)}}


def build(model, stage, config, root):
    if model == "sitedit":
        return SITTokens(config) if stage == "tokens" else SITEditor(config)
    if model == "mirage" and stage == "edit":
        return MirageEditor(model, stage, config, root)
    return Native(model, stage, config, root)
