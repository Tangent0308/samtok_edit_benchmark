"""Public-input-only adapters; upstream inference implementations remain unchanged."""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

from PIL import Image

from samtok_benchmark.io import sha256_file
from .smoke_suite import MODELS, SOURCES


def generator(seed=42):
    import torch

    return torch.Generator("cuda").manual_seed(seed)


def source_call(req, native):
    return {
        "images": [req["source"]["path"]],
        "prompt": native["global_prompt"],
        "native": native,
        "extra_component_calls": {
            "rewriter": 0,
            "planner": 0,
            "reflection": 0,
            "external_grounder": 0,
            "sam": 0,
        },
    }


class Qwen21:
    def __init__(self, root):
        import torch
        from diffusers import QwenImage21Pipeline

        actual = Path(inspect.getfile(QwenImage21Pipeline))
        audited = SOURCES / "diffusers/src/diffusers/pipelines/qwenimage21/pipeline_qwenimage21.py"
        assert sha256_file(actual) == sha256_file(audited)
        self.pipe = QwenImage21Pipeline.from_pretrained(
            str(MODELS / "Qwen-Image-2.1"), torch_dtype=torch.bfloat16, local_files_only=True
        ).to("cuda")
        self.pipe.set_progress_bar_config(disable=True)
        self.transformers = [self.pipe.transformer]
        self.configuration = {
            "num_inference_steps": 40,
            "true_cfg_scale": 1.0,
            "output_resolution": 1024,
            "use_kv_cache": True,
            "prompt_enhancer": False,
            "diffusers_revision": "06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a",
            "weight_cache_revision": "b3179ad355be050328e483a9dfdd9e60cd62adfa",
            "audited_equivalent_weight_revision": "d26bb61231c349cf6b7896fa83353113880e1ba3",
            "pipeline_sha256": sha256_file(actual),
        }

    def request(self, task, req, inputs, native, out):
        call = source_call(req, native)
        call.update(inputs["forms"][task["form"]])
        call["parameters"] = {
            k: self.configuration[k]
            for k in ("num_inference_steps", "true_cfg_scale", "output_resolution", "use_kv_cache")
        }
        return call

    def generate(self, call, out):
        steps = []

        def callback(pipe, index, timestep, kw):
            steps.append(index)
            return kw

        result = self.pipe(
            image=[Image.open(p).convert("RGB") for p in call["images"]],
            prompt=call["prompt"],
            generator=generator(),
            callback_on_step_end=callback,
            **call["parameters"],
        ).images[0]
        return result, {"inference_api_calls": 1, "denoising_steps": len(steps)}


class Flux3:
    def __init__(self, root):
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
        self.transformers = list(self.models.pipeline.dits.values())
        self.configuration = {
            "model": "distilled",
            "steps": 16,
            "guidance": None,
            "pup": False,
            "safety": False,
            "source_revision": json.loads((SOURCES / "flux3/revision.json").read_text())["commit"],
            "loader": "official Pipeline + generate; optional eager unused classifier not loaded",
        }

    def request(self, task, req, inputs, native, out):
        call = source_call(req, native)
        boxes = []
        parts = []
        for idx, u in enumerate(native["units"]):
            box = u["box_yxyx_normalized"]
            if box is not None:
                tag = f"obj_{idx + 1}"
                boxes.append(
                    {
                        "id": tag,
                        "from": "ref_image_0",
                        "src_bbox": box,
                        "tgt_bbox": box,
                        "desc": "the selected source region",
                    }
                )
                parts.append(f"For <{tag}>, {u['instruction']}")
            else:
                parts.append(u["instruction"])
        call["prompt"] = (
            "Edit <ref_image_0>. " + " ".join(parts) + " Keep everything else unchanged."
        )
        if task["form"] == "native-annotation":
            call["images"].append(inputs["annotation"]["path"])
            call["prompt"] = (
                "Reference <ref_image_1> is an annotated copy of <ref_image_0>. Use its colored contours and U labels to identify the source regions. Do not reproduce marks, labels, or leader lines. "
                + call["prompt"]
            )
        call["boxes"] = boxes or None
        call["parameters"] = {
            k: self.configuration[k] for k in ("model", "steps", "guidance", "pup", "safety")
        }
        return call

    def generate(self, call, out):
        image, metadata = self.generate_fn(
            self.models,
            prompt=call["prompt"],
            images=[Image.open(p).convert("RGB") for p in call["images"]],
            boxes=call["boxes"],
            seed=42,
            **call["parameters"],
        )
        return image, {
            "inference_api_calls": 1,
            "generation_metadata": metadata,
            "final_prompt": metadata["prompt"],
        }


class Mice:
    def __init__(self, root):
        sys.path.insert(0, str(SOURCES / "mice"))
        import infer_flux2_mice as impl

        old = sys.argv
        sys.argv = ["infer_flux2_mice.py", "--exp_name", "ifbench-tiered-smoke"]
        try:
            self.cfg = impl.parse_args()
        finally:
            sys.argv = old
        self.cfg.pretrained_model_name_or_path = str(MODELS / "FLUX.2-klein-4B")
        self.pipe = impl.load_pipeline(self.cfg, "cuda")
        self.pipe.set_progress_bar_config(disable=True)
        proc = impl.get_attention_processors(
            impl.AttentionSetting(self.cfg.attention_setting.lower()),
            self.cfg.sigma_scale,
            self.cfg.kernel_size,
            self.cfg.temperature,
        )
        if isinstance(proc, tuple):
            for _, module in self.pipe.transformer.named_modules():
                if isinstance(module, impl.Flux2Attention):
                    module.set_processor(proc[0])
                elif isinstance(module, impl.Flux2ParallelSelfAttention):
                    module.set_processor(proc[1])
        else:
            self.pipe.transformer.set_attn_processor(proc)
        self.transformers = [self.pipe.transformer]
        self.configuration = {
            **vars(self.cfg),
            "source_revision": json.loads((SOURCES / "mice/revision.json").read_text())["commit"],
            "region_form": "native masks; point/box deterministic rasterization",
        }

    def request(self, task, req, inputs, native, out):
        call = source_call(req, native)
        regional = [u for u in native["units"] if u["mask"]]
        global_units = [u for u in native["units"] if not u["mask"]]
        global_text = "Apply all edits. Keep everything else unchanged. " + " ".join(
            u["instruction"] for u in global_units
        )
        call["prompt"] = "$BREAKFLAG$".join([global_text] + [u["instruction"] for u in regional])
        call["masks"] = [u["mask"]["path"] for u in regional]
        call["global_unit_ids"] = [u["unit_id"] for u in global_units]
        call["regional_unit_ids"] = [u["unit_id"] for u in regional]
        w, h = req["source"]["size"]
        call["model_size"] = [
            int((1024**2 * w / h) ** 0.5) // 16 * 16,
            int((1024**2 * h / w) ** 0.5) // 16 * 16,
        ]
        call["parameters"] = {"num_inference_steps": 4, "guidance_scale": 1.0}
        call["scope"] = (
            "S5 global-plus-regions extension under smoke verification; all units retained"
            if task["setting"] == "S5"
            else "native region binding; S1 global-only degeneration"
        )
        return call

    def generate(self, call, out):
        import numpy as np
        import torch

        c = self.cfg
        w, h = call["model_size"]
        masks = [
            torch.from_numpy(np.array(Image.open(p).convert("L")) > 127).float()
            for p in call["masks"]
        ]
        image = (
            Image.open(call["images"][0]).convert("RGB").resize((w, h), Image.Resampling.LANCZOS)
        )
        image.save(out / "actual_source.png")
        result = self.pipe(
            image=image,
            prompt=call["prompt"],
            height=h,
            width=w,
            **call["parameters"],
            prompt_settings=c.prompt_settings,
            attention_setting=c.attention_setting,
            hard_image_attribute_binding_list_double=c.hard_image_attribute_binding_list_double,
            hard_image_attribute_binding_list_single=c.hard_image_attribute_binding_list_single,
            bring_area_to_1024_squared=c.bring_area_to_1024_squared,
            generator=generator(),
            hard_masking_steps=c.masking_steps,
            relaxed_timesteps=c.relaxed_timesteps,
            attention_kwargs={"smooth_P_L": c.smooth_P_L},
            free_latent=c.free_latent,
            free_context=c.free_context,
            free_LC=c.free_LC,
            instance_masks_yx=masks,
        ).images[0]
        return result, {"inference_api_calls": 1}


def build_adapter(model, root):
    if model in ("qwen21", "flux3", "mice"):
        return {"qwen21": Qwen21, "flux3": Flux3, "mice": Mice}[model](root)
    from .smoke_native_adapters import build_native

    return build_native(model, root)
