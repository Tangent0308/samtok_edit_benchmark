"""Both editors receive the public mask; native SITEdit codec, base source+mask images."""

import time
import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageOps

from samtok_benchmark.external_refedit import adapters as ref
from samtok_benchmark.external_refedit.data import immutable
from samtok_benchmark.io import digest, sha256_file
from .mask_public import verify_public

MASK_PROMPT = (
    "Image 1 is the source image to edit. Image 2 is a binary mask at the same coordinates: "
    "white marks the selected region and black marks the remaining image. "
    "Use this mask to locate the requested edit. Return the edited Image 1.\n"
)


def ref_public(public):
    verify_public(public)
    result = {
        "schema": "refedit.public.v1",
        **{k: public[k] for k in ("case_id", "source", "instruction")},
    }
    result["input_digest"] = digest(result)
    return result


class Native(ref.Native):
    def run(self, public, out, previous=None):
        request = native_request(self.model, public, self.config, out)
        self.backend.reset()
        self.backend.preflight(request, public, out)
        result, detail = self.backend.run(request, public, out, native_plan=previous)
        self.backend.synchronize()
        return result, {
            "native": detail,
            "calls": dict(self.backend.metrics),
            "memory": self.backend.memory(),
            "environment": self.backend.environment(),
        }


def annotated(public, out):
    """Exact public binary-mask inside contours, including holes; no external locator."""
    image = Image.open(public["source"]["path"]).convert("RGB")
    mask = Image.open(public["mask"]["path"]).convert("L")
    w, h = image.size
    width = max(1, round(min(w, h) * 0.004))
    eroded = ImageOps.expand(mask, border=width, fill=0).filter(
        ImageFilter.MinFilter(2 * width + 1)
    )
    eroded = eroded.crop((width, width, w + width, h + width))
    image.paste((255, 0, 0), mask=ImageChops.subtract(mask, eroded))
    path = out / "public-mask-contour.png"
    image.save(path)
    return str(path)


def native_request(model, public, config, out):
    request = ref.native_request(model, ref_public(public), config)
    source, mask = public["source"]["path"], public["mask"]["path"]
    request.update(
        public_input_digest=public["input_digest"], configuration_id="interedit-public-mask-v1"
    )
    if model in {"qwen21", "qwen2511", "flux2_klein9b", "flux3"}:
        request.update(images=[source, mask], prompt=MASK_PROMPT + public["instruction"])
        if model == "flux3":
            request["prompt"] = (
                "Edit <ref_image_0>. <ref_image_1> is a binary mask at the same coordinates: "
                "white marks the selected region and black marks the remaining image. "
                "Use this mask to locate the requested edit. Return the edited <ref_image_0>.\n"
                + public["instruction"]
            )
    elif model == "mice":
        from samtok_benchmark.ifbench.inputs import BASE

        unit = {
            "id": "U1",
            "instruction": public["instruction"],
            "has_ref": True,
            "locator": "mask",
            "region": {k: public["mask"][k] for k in ("path", "sha256")},
        }
        request.update(
            public_units=[unit],
            global_unit_ids=[],
            regional_units=[unit],
            prompt=BASE + "$BREAKFLAG$" + public["instruction"],
        )
    elif model in {"replan", "mirage"}:
        annotation = annotated(public, out)
        hint = (
            "The red mask contours indicate the publicly selected source region for this edit. "
            "The red contours are input annotations, not objects to edit or reproduce. "
            "For an addition, the region selects its attachment or support location. "
        )
        if model == "replan":
            request.update(
                planner_image=annotation,
                editor_image=source,
                images=[source, annotation],
                prompt=hint + public["instruction"],
            )
        else:
            request.update(grounding_image=annotation, grounding_hints={"composite": hint})
        request["public_annotation"] = {
            "path": annotation,
            "sha256": sha256_file(annotation),
            "source_mask_sha256": public["mask"]["sha256"],
            "policy": "red-inside-contour-min-side-0.004-v1",
        }
    else:
        raise ValueError(model)
    return request


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
        elapsed = time.monotonic() - start
        decoded = self.models.codec.decode_strict(image, span)[0] > 0
        Image.fromarray(decoded.astype(np.uint8) * 255).save(out / "U1.png")
        immutable(
            out / "call.json",
            {"source": public["source"], "mask": public["mask"], "grounder_called": False},
        )
        unit = {
            "id": "U1",
            "token": span,
            "source": "codec",
            "area": float(mask.mean()),
            "roundtrip_iou": float((mask & decoded).sum() / max(1, (mask | decoded).sum())),
        }
        return None, {
            "native": {"units": [unit], "fallback_units": 0, "encode_seconds": elapsed},
            "calls": {"grounder_requests": 0, "codec_encode": 1, "diagnostic_codec_decode": 1},
        }


class Editor(ref.SITEditor):
    def run(self, public, out, previous=None):
        return super().run(ref_public(public), out, previous)


def build(model, stage, config, root):
    if model == "sitedit":
        return MaskTokens(config) if stage == "tokens" else Editor(config)
    return Native(model, stage, config, root)
