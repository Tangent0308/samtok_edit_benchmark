"""Both editors receive the public mask; native SITEdit codec, base source+mask images."""

import time
import numpy as np
from PIL import Image

from samtok_benchmark.external_refedit import adapters as ref
from samtok_benchmark.external_refedit.data import immutable
from samtok_benchmark.io import digest
from .public import verify_public

MASK_PROMPT = ("Image 1 is the source image to edit. Image 2 is a binary mask at the same coordinates: "
               "white marks the selected region and black marks the remaining image. "
               "Use this mask to locate the requested edit. Return the edited Image 1.\n")


def ref_public(public):
    verify_public(public)
    result = {"schema": "refedit.public.v1", **{k: public[k] for k in ("case_id", "source", "instruction")}}
    result["input_digest"] = digest(result)
    return result


class Native(ref.Native):
    def run(self, public, out, previous=None):
        request = ref.native_request(self.model, ref_public(public), self.config)
        request.update(images=[public["source"]["path"], public["mask"]["path"]],
                       prompt=MASK_PROMPT + public["instruction"], public_input_digest=public["input_digest"],
                       configuration_id="interedit-public-mask-v1")
        self.backend.reset()
        self.backend.preflight(request, public, out)
        result, detail = self.backend.run(request, public, out)
        self.backend.synchronize()
        return result, {"native": detail, "calls": dict(self.backend.metrics),
                        "memory": self.backend.memory(), "environment": self.backend.environment()}


class MaskTokens:
    def __init__(self, config):
        from samtok_edit21.evaluation.ifbench import Pass1Models
        self.models = Pass1Models(config["sitedit"])
        self.models.codec  # No localization model is loaded or called for supplied masks.

    def run(self, public, out, previous=None):
        from samtok_edit21.pass1.protocol import valid_span
        verify_public(public)
        image = Image.open(public["source"]["path"]).convert("RGBA")
        mask = np.array(Image.open(public["mask"]["path"]).convert("L")) > 128
        start = time.monotonic()
        span = self.models.codec.encode(image, [mask])[0][0]
        if not valid_span(span):
            raise ValueError("Mask codec returned invalid span")
        elapsed = time.monotonic()-start
        decoded = self.models.codec.decode_strict(image, span)[0] > 0
        Image.fromarray(decoded.astype(np.uint8)*255).save(out / "U1.png")
        immutable(out / "call.json", {"source": public["source"], "mask": public["mask"], "grounder_called": False})
        unit = {"id": "U1", "token": span, "source": "codec", "area": float(mask.mean()),
                "roundtrip_iou": float((mask & decoded).sum()/max(1, (mask | decoded).sum()))}
        return None, {"native": {"units": [unit], "fallback_units": 0, "encode_seconds": elapsed},
                      "calls": {"grounder_requests": 0, "codec_encode": 1, "diagnostic_codec_decode": 1}}


class Editor(ref.SITEditor):
    def run(self, public, out, previous=None):
        return super().run(ref_public(public), out, previous)


def build(model, stage, config, root):
    if model == "sitedit":
        return MaskTokens(config) if stage == "tokens" else Editor(config)
    return Native(model, stage, config, root)
