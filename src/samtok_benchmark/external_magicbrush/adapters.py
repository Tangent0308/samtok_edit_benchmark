"""Reuse frozen RefEdit/IF-Bench native inference with MagicBrush's public mask track."""

from __future__ import annotations

from pathlib import Path
import time

import numpy as np
from PIL import Image

from samtok_benchmark.io import digest
from samtok_benchmark.external_refedit import adapters as ref
from .bundle import verify_public
from .data import immutable

DUAL = (
    "Image 1 is the clean source image to edit. Image 2 is the same image with a red outline and U1 label. "
    "The outline marks the supplied editable region in Image 1. Use it to locate the edit. "
    "Return only the edited Image 1, without marks or labels. Keep unrelated content unchanged.\n"
)
PLANNER = (
    "This is an annotated copy of the source image. The red outline and U1 label identify the supplied "
    "editable region. The marks are not scene objects. Plan the requested edit for the clean source "
    "image with the same dimensions and coordinates.\n"
)
HINT = "The supplied editable region is indicated by the red outline and U1 label."


def ref_public(public):
    """Compatibility view for the reused single-instruction adapter; no scoring metadata is accepted."""
    verify_public(public)
    value = {
        "schema": "refedit.public.v1",
        "case_id": public["case_id"],
        "source": public["source"],
        "instruction": public["instruction"],
    }
    value["input_digest"] = digest(value)
    return value


def native_request(model, public, config):
    request = ref.native_request(model, ref_public(public), config)
    request.update(
        configuration_id="magicbrush-native-v1", public_input_digest=public["input_digest"]
    )
    if public["track"] == "mask-free":
        return request
    clean = public["source"]["path"]
    marked = public["annotation"]["path"]
    instruction = public["instruction"]
    if model in {"qwen21", "qwen2511", "flux3", "flux2_klein9b"}:
        request.update(images=[clean, marked], prompt=DUAL + instruction)
        if model == "flux3":
            request["prompt"] = (
                "Reference <ref_image_1> is an annotated copy of <ref_image_0>. "
                "Its red outline and U1 label mark the supplied editable region. "
                "Do not reproduce marks, labels, or leader lines. Edit <ref_image_0>. "
                + instruction
                + " Keep everything else unchanged."
            )
    elif model == "replan":
        request.update(planner_image=marked, editor_image=clean, prompt=PLANNER + instruction)
    elif model == "mirage":
        request.update(grounding_image=marked, grounding_hints={"composite": HINT})
    elif model == "mice":
        if "$BREAKFLAG$" in instruction:
            raise ValueError("Instruction contains reserved MICE separator")
        unit = {
            "id": "U1",
            "instruction": instruction,
            "has_ref": True,
            "locator": "mask",
            "region": {k: public["mask"][k] for k in ["path", "sha256"]},
        }
        request.update(
            public_units=[unit],
            regional_units=[unit],
            global_unit_ids=[],
            prompt="Apply all edits. Keep everything else unchanged.$BREAKFLAG$" + instruction,
        )
    else:
        raise ValueError(model)
    return request


class Native(ref.Native):
    def run(self, public, out, previous=None):
        request = native_request(self.model, public, self.config)
        self.backend.reset()
        self.backend.preflight(request, public, out)
        raw, detail = self.backend.run(request, public, out, native_plan=previous)
        self.backend.synchronize()
        return raw, {
            "native": detail,
            "calls": dict(self.backend.metrics),
            "memory": self.backend.memory(),
            "environment": self.backend.environment(),
        }


class SITTokens(ref.SITTokens):
    def __init__(self, config):
        # Both tracks are in this worker's shard; load once, outside per-request timing.
        super().__init__(config)

    def run(self, public, out, previous=None):
        verify_public(public)
        if public["track"] == "mask-free":
            return super().run(ref_public(public), out, previous)
        image = Image.open(public["source"]["path"]).convert("RGBA")
        mask = np.asarray(Image.open(public["mask"]["path"]).convert("L")) > 0
        tick = time.monotonic()
        span = self.models.codec.encode(image, [mask])[0][0]
        encode_seconds = time.monotonic() - tick
        from samtok_edit21.pass1.protocol import valid_span

        if not valid_span(span):
            raise ValueError("Supplied-mask codec returned an invalid token span")
        # Diagnostic decoding does not enter generation.
        decoded = self.models.codec.decode_strict(image, span)[0] > 0
        Image.fromarray(decoded.astype(np.uint8) * 255).save(Path(out) / "U1.png")
        unit = {
            "id": "U1",
            "token": span,
            "source": "codec",
            "area": float(mask.mean()),
            "decoded_area": float(decoded.mean()),
            "roundtrip_iou": float((mask & decoded).sum() / max(1, (mask | decoded).sum())),
        }
        immutable(
            Path(out) / "call.json",
            {
                "source": public["source"],
                "mask": public["mask"],
                "grounder_called": False,
                "codec_encode": 1,
            },
        )
        return None, {
            "native": {"units": [unit], "fallback_units": 0, "encode_seconds": encode_seconds},
            "calls": {"grounder_requests": 0, "codec_encode": 1, "diagnostic_codec_decode": 1},
        }


class SITEditor(ref.SITEditor):
    def run(self, public, out, previous=None):
        return super().run(ref_public(public), out, previous)


class MirageEditor(ref.MirageEditor):
    """Keep the same native call with the frozen 0.4 ratio and an accurate saved call record."""

    def run(self, public, out, previous=None):
        # The preceding native planner already consumed the track's public spatial information.
        # Editing always receives the clean image, original text, and that saved native plan.
        return super().run(ref_public(public), out, previous)


def build(model, stage, config, root):
    if model == "sitedit":
        return SITTokens(config) if stage == "tokens" else SITEditor(config)
    if model == "mirage" and stage == "edit":
        return MirageEditor(model, stage, config, root)
    return Native(model, stage, config, root)
