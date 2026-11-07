"""Use the original public newline-separated instructions as native joint SITEdit units."""

import time

import numpy as np
from PIL import Image

from samtok_benchmark.external_refedit.adapters import Native, SITEditor, SITTokens
from samtok_benchmark.external_refedit.data import immutable, verify_public
from samtok_benchmark.external_refedit.placement import place


def public_units(public):
    verify_public(public)
    lines = [x.strip() for x in public["instruction"].splitlines() if x.strip()]
    if not 1 <= len(lines) <= 8:
        raise ValueError("Invalid public instruction line count")
    return [{"label": f"U{i+1}", "instruction": text, "has_ref": True, "locator": "none"}
            for i, text in enumerate(lines)]


class JointTokens(SITTokens):
    def run(self, public, out, previous=None):
        from samtok_edit21.pass1.protocol import VERSION, valid_span, validate_request

        request = {"protocol": VERSION, "coordinate_system": "normalized_0_1000",
                   "targets": public_units(public)}
        validate_request(request)
        image = Image.open(public["source"]["path"]).convert("RGB")
        start = time.monotonic()
        answer = self.models.grounder.ground(image, request, max_new_tokens=self.method["pass1_max_new_tokens"])
        ground_seconds = time.monotonic() - start
        units = []
        for target in request["targets"]:
            span = answer["parsed"]["spans"].get(target["label"])
            valid = bool(span and valid_span(span))
            area = None
            if valid:
                decoded = self.models.codec.decode_strict(image.convert("RGBA"), span)[0] > 0
                area = float(decoded.mean())
                Image.fromarray(np.asarray(decoded, dtype=np.uint8)*255).save(out / (target["label"] + ".png"))
            units.append({"id": target["label"], "instruction": target["instruction"],
                          "token": span if valid else None, "source": "pass1" if valid else "fallback_text",
                          "decoded_area": area})
        return None, {"native": {"units": units, "request": request, "raw": answer["raw"],
                     "parsed": answer["parsed"], "ground_seconds": ground_seconds,
                     "fallback_units": sum(x["token"] is None for x in units)},
                     "calls": {"grounder_requests": 1, "codec_encode": 0,
                               "diagnostic_codec_decode": sum(x["token"] is not None for x in units)}}


class JointEditor(SITEditor):
    def run(self, public, out, previous=None):
        import torch
        from samtok_edit21.data.protocol import strip_tokens
        from samtok_edit21.models.pipeline import edit
        from samtok_edit21.preparation.round2_data import multi_edit_prompt

        targets = public_units(public)
        if [t["instruction"] for t in targets] != [t["instruction"] for t in previous["units"]]:
            raise ValueError("Native token cache belongs to another instruction")
        sentences, placements = [], []
        for unit in previous["units"]:
            sentence, placement = place(unit["instruction"], unit["token"]) if unit["token"] else (unit["instruction"], None)
            sentences.append(sentence)
            placements.append(placement)
        prompt = multi_edit_prompt(sentences) if len(sentences) > 1 else sentences[0]
        guided = any(x is not None for x in placements)
        width, height = public["source"]["size"]
        params = {"num_inference_steps": self.method["steps"], "seed": 42, "width": width, "height": height,
                  "use_kv_cache": True, "cfg_scale": self.method["token_guidance"] if guided else 1.0,
                  "mode": "inline" if guided else "direct", "pass2_te": "raw"}
        if guided:
            params["negative_prompt"] = strip_tokens(prompt)
        immutable(out / "call.json", {"images": [public["source"]], "prompt": prompt, "parameters": params,
                  "placements": placements, "fallback_units": previous["fallback_units"],
                  "dit_adapter": self.method["dit_adapter"]})
        torch._dynamo.reset()
        with torch.inference_mode():
            raw, detail = edit(self.pipe, prompt, [Image.open(public["source"]["path"]).convert("RGBA")], **params)
        if raw.size != (width, height):
            raise ValueError("Unexpected SITEdit canvas size")
        return raw, {"native": detail, "fallback_units": previous["fallback_units"],
                     "calls": {"inference_api_calls": 1, "expected_dit_forwards": 40*(2 if guided else 1)}}


def build(model, stage, config, root):
    if model == "sitedit":
        return JointTokens(config) if stage == "tokens" else JointEditor(config)
    return Native(model, stage, config, root)
