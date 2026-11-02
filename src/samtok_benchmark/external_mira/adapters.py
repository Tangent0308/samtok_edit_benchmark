"""Thin adapters to pinned native methods. No evaluation annotations are accepted here."""

from __future__ import annotations

from pathlib import Path
import time

import numpy as np
from PIL import Image

from samtok_benchmark.ifbench.fairness_dev_worker import NativeBackend
from .data import immutable, verify_public


def native_request(model, public, config):
    verify_public(public)
    image = public["source"]["path"]
    prompt = public["original_instruction"]
    params = dict(config["model_specifications"][model]["parameters"])
    common = {"source": public["source"], "images": [image], "prompt": prompt,
              "seed": 42, "public_input_digest": public["input_digest"],
              "configuration_id": "mira-native-text-v1", "parameters": params}
    if model in {"qwen2511", "qwen21"}:
        common["resolution_policy"] = "ifbench.canvas.1mp.v1"
        params.update(zip(("width", "height"), public["source"]["size"]))
    elif model == "replan":
        # These configure the native planner/seed, rather than diffusion pipeline kwargs.
        params.pop("seed", None)
        params.pop("native_planner_max_new_tokens", None)
        common.update(planner_image=image, editor_image=image,
                      planner_template=str(Path(config["paths"]["sources"]) /
                                           "replan/replan/pipelines/prompt_template/replan.txt"))
    elif model == "mirage":
        # One whole original instruction, as in native MIRA inference. The parser decides its own split.
        common.update(parser_inputs=[prompt], public_units=[{"id": "composite"}],
                      grounding_image=image, grounding_hints={"composite": ""},
                      edit_image=image, global_original_prompt=prompt)
    else:
        raise ValueError(model)
    return common


class Native:
    def __init__(self, model, stage, config, root):
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


class SITTokens:
    def __init__(self, config):
        from samtok_edit21.evaluation.ifbench import Pass1Models

        self.method = config["sitedit"]
        self.models = Pass1Models(self.method)

    def run(self, public, out, previous=None):
        from samtok_edit21.pass1.protocol import VERSION, valid_span, validate_request

        verify_public(public)
        request = {"protocol": VERSION, "coordinate_system": "normalized_0_1000",
                   "targets": [{"label": u["id"], "instruction": u["instruction"],
                                "has_ref": True, "locator": "none"} for u in public["units"]]}
        validate_request(request)
        image = Image.open(public["source"]["path"]).convert("RGB")
        tick = time.monotonic()
        answer = self.models.grounder.ground(image, request,
                                             max_new_tokens=self.method["pass1_max_new_tokens"])
        ground_seconds = time.monotonic() - tick
        units = []
        tick = time.monotonic()
        for unit in public["units"]:
            span = answer["parsed"]["spans"].get(unit["id"])
            valid = bool(span and valid_span(span))
            units.append({"id": unit["id"], "token": span if valid else None,
                          "source": "pass1" if valid else "fallback_text"})
            if valid:
                # Offline diagnostics only. These pixels are not consumed by SITEdit's editor.
                decoded = self.models.codec.decode_strict(image.convert("RGBA"), span)[0] > 0
                Image.fromarray(np.asarray(decoded, dtype=np.uint8) * 255).save(out / f"{unit['id']}.png")
        return None, {"native": {"units": units, "request": request, "raw": answer["raw"],
                                  "parsed": answer["parsed"], "ground_seconds": ground_seconds,
                                  "diagnostic_decode_seconds": time.monotonic() - tick,
                                  "fallback_units": sum(u["token"] is None for u in units)},
                      "calls": {"grounder_requests": 1, "codec_encode": 0,
                                "diagnostic_codec_decode": sum(u["token"] is not None for u in units)}}


def token_prompt(public, tokens):
    from samtok_edit21.evaluation.ifbench import place_token
    from samtok_edit21.preparation.round2_data import multi_edit_prompt

    spans = {u["id"]: u["token"] for u in tokens["units"] if u["token"]}
    # Original public text is retained. "Wrap ... around <source>" uses the source-at-end add rule.
    sentences = [place_token(u["instruction"], u["operation"], True, spans[u["id"]])
                 if u["id"] in spans else u["instruction"] for u in public["units"]]
    return multi_edit_prompt(sentences), bool(spans)


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
        from samtok_edit21.models.pipeline import edit
        from samtok_edit21.data.protocol import strip_tokens

        verify_public(public)
        prompt, guided = token_prompt(public, previous)
        width, height = public["source"]["size"]
        params = {"num_inference_steps": self.method["steps"], "seed": 42,
                  "width": width, "height": height, "use_kv_cache": True,
                  "cfg_scale": self.method["token_guidance"] if guided else 1.0,
                  "mode": "inline" if guided else "direct", "pass2_te": "raw"}
        if guided:
            params["negative_prompt"] = strip_tokens(prompt)
        immutable(out / "call.json", {"images": [public["source"]], "prompt": prompt,
                                       "parameters": params, "fallback_units": previous["fallback_units"]})
        image = Image.open(public["source"]["path"]).convert("RGBA")
        torch._dynamo.reset()
        with torch.inference_mode():
            raw, report = edit(self.pipe, prompt, [image], **params)
        if raw.size != (width, height):
            raise ValueError("SITEdit returned an unexpected canvas size")
        return raw, {"native": report, "fallback_units": previous["fallback_units"],
                     "calls": {"inference_api_calls": 1,
                               "expected_dit_forwards": self.method["steps"] * (2 if guided else 1)}}


def build(model, stage, config, root):
    if model == "sitedit":
        return SITTokens(config) if stage == "tokens" else SITEditor(config)
    return Native(model, stage, config, root)
