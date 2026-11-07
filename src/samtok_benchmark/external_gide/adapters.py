"""Public polygons use the native codec; boxes use native Pass1; text stays text."""

import time

import numpy as np
from PIL import Image, ImageDraw
import json
from .inputs import instructions, POLYGON, BOX

from samtok_benchmark.external_refedit.adapters import Native, SITEditor, SITTokens
from samtok_benchmark.external_refedit.data import immutable, verify_public
from samtok_benchmark.external_refedit.placement import place


def public_units(public):
    verify_public(public)
    lines = instructions(public["instruction"])
    if len(lines) != 2:
        raise ValueError("Invalid public instruction line count")
    return [{"label": f"U{i+1}", "instruction": text, "has_ref": True, "locator": "none"}
            for i, text in enumerate(lines)]


class JointTokens(SITTokens):
    def run(self, public, out, previous=None):
        from samtok_edit21.pass1.protocol import VERSION, valid_span, validate_request, box_normalized

        request = {"protocol": VERSION, "coordinate_system": "normalized_0_1000",
                   "targets": public_units(public)}
        image = Image.open(public["source"]["path"]).convert("RGB")
        first = request["targets"][0]
        supplied = None
        if match := POLYGON.search(first["instruction"]):
            mask = Image.new("L", image.size, 0)
            ImageDraw.Draw(mask).polygon([tuple(round(v) for v in p) for p in json.loads(match[1])], fill=255)
            mask.save(out / "U1-supplied.png")
            supplied = self.models.codec.encode(image.convert("RGBA"), [np.array(mask) > 0])[0][0]
            if not valid_span(supplied):
                raise ValueError("Polygon codec returned an invalid span")
            first.update(locator="mask", has_ref=False, region={"mask_2d": supplied})
        elif match := BOX.search(first["instruction"]):
            x, y, w, h = json.loads(match[1])
            box = box_normalized([x, y, x+w, y+h], image.size, continuous=True)
            first.update(locator="box", has_ref=False, region={"box": box})
        validate_request(request)
        start = time.monotonic()
        answer = self.models.grounder.ground(image, request, max_new_tokens=self.method["pass1_max_new_tokens"])
        ground_seconds = time.monotonic() - start
        units = []
        for target in request["targets"]:
            span = supplied if supplied and target["label"] == "U1" else answer["parsed"]["spans"].get(target["label"])
            valid = bool(span and valid_span(span))
            area = None
            if valid:
                decoded = self.models.codec.decode_strict(image.convert("RGBA"), span)[0] > 0
                area = float(decoded.mean())
                Image.fromarray(np.asarray(decoded, dtype=np.uint8)*255).save(out / (target["label"] + ".png"))
            units.append({"id": target["label"], "instruction": target["instruction"],
                          "token": span if valid else None, "source": ("codec" if supplied and target["label"] == "U1" else "pass1") if valid else "fallback_text",
                          "decoded_area": area})
        return None, {"native": {"units": units, "request": request, "raw": answer["raw"],
                     "parsed": answer["parsed"], "ground_seconds": ground_seconds,
                     "fallback_units": sum(x["token"] is None for x in units)},
                     "calls": {"grounder_requests": 1, "codec_encode": int(supplied is not None),
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
