"""Explicit Diffusers execution variant; never replaces a frozen quality adapter.

Both Qwen-2.1 rows use the same pipeline, prompt feature extraction and attention
processor. SITEdit retains its tokenizer, raw text encoder, LoRA, CodeInjector,
negative prompt and CPU noise generator. Native planning remains unchanged.
"""

from pathlib import Path
from types import SimpleNamespace
import math

import torch
from diffusers import QwenImage21Pipeline
from diffusers.models.transformers.transformer_qwenimage21 import QwenImage21AttnProcessor


class UnifiedQwenPipeline(QwenImage21Pipeline):
    @torch.no_grad()
    def _get_qwen_prompt_embeds(self, prompt=None, image=None, device=None):
        # Use the trained raw template and pre-final-RMSNorm features for both
        # methods. Avoid computing discarded vocabulary logits for either row.
        device = device or self._execution_device
        prompts = [prompt] if isinstance(prompt, str) else prompt
        if len(prompts) != 1:
            raise ValueError("The controlled timing protocol fixes batch size to one")
        value = prompts[0] or " "
        kwargs = {"padding": True, "padding_side": "left", "return_tensors": "pt"}
        if image is None:
            kwargs["text"] = [self.prompt_template_t2i.format(value)]
        else:
            from PIL import Image

            prefix = " ".join(
                f"<image{i}><|vision_start|><|image_pad|><|vision_end|>"
                for i in range(1, len(image) + 1)
            )
            template = self.prompt_template_ti2i.replace(
                "<image1><|vision_start|><|image_pad|><|vision_end|>", prefix
            )
            kwargs["text"] = [template.format(value)]
            flattened = []
            for item in image:
                if item.mode == "RGBA":
                    white = Image.new("RGB", item.size, "white")
                    white.paste(item, mask=item.getchannel("A"))
                    item = white
                flattened.append(item)
            kwargs["images"] = flattened
        inputs = self.processor(**kwargs).to(device)
        text_count = int(
            ((inputs.input_ids != self._img_token_id) & inputs.attention_mask.bool()).sum()
        )
        image_shift = sum(max(i.size) // 16 for i in image or [])
        if text_count > 8192 - 1 - image_shift + self._drop_idx:
            raise ValueError(
                "Controlled inputs exceed the native text budget; no silent truncation"
            )
        forward = {"input_ids": inputs.input_ids, "attention_mask": inputs.attention_mask}
        for key in ("pixel_values", "image_grid_thw", "mm_token_type_ids"):
            if key in inputs:
                forward[key] = inputs[key]
        hidden = self._conditioner(**forward)
        keep = inputs.attention_mask[0].bool()
        embeds = hidden[0, keep][self._drop_idx :].unsqueeze(0)
        image_mask = (inputs.input_ids[0, keep] == self._img_token_id)[self._drop_idx :].unsqueeze(
            0
        )
        return embeds, None, image_mask


def load_pipeline(config, *, sit, codebook_path, device="cuda"):
    from transformers import Qwen3VLForConditionalGeneration
    from samtok_edit21.models.pipeline import SamtokTextEncoder, build_processor

    encoder = Qwen3VLForConditionalGeneration.from_pretrained(
        config["samtok"] if sit else str(Path(config["qwen"]) / "text_encoder"),
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        local_files_only=True,
    )
    pipe = UnifiedQwenPipeline.from_pretrained(
        config["qwen"], text_encoder=encoder, torch_dtype=torch.bfloat16, local_files_only=True
    ).to(device)
    pipe.processor = build_processor(config["qwen"], config["samtok"] if sit else None)
    message = [{"role": "system", "content": [{"type": "text", "text": pipe.sys_prompt}]}]
    ids = pipe.processor.apply_chat_template(message, tokenize=True, return_dict=False)
    pipe._drop_idx = len(ids) if not ids or isinstance(ids[0], int) else len(ids[0])
    pipe._img_token_id = pipe.processor.tokenizer.encode("<|image_pad|>")[0]
    pipe._conditioner = SamtokTextEncoder(pipe.text_encoder)
    pipe.transformer.set_attn_processor(QwenImage21AttnProcessor())
    pipe.transformer.set_attention_backend("native")
    if sit:
        from safetensors.torch import load_file
        from samtok_edit21.models.adapters import load_adapter
        from samtok_edit21.models.code_injector import CodeInjector, load_code_injector

        recipe = load_adapter(pipe.transformer, config["dit_adapter"])
        if recipe["rank"] != recipe.get("alpha", recipe["rank"]):
            raise ValueError("Expected the approved rank/alpha scaling at LoRA strength 1")
        book = load_file(str(codebook_path))["codebook"]
        tokenizer = pipe.processor.tokenizer
        injector = CodeInjector(
            book,
            [tokenizer.convert_tokens_to_ids(f"<|mt_{i:04d}|>") for i in range(512)],
            tokenizer.convert_tokens_to_ids("<|mt_end|>"),
        ).to(device)
        # Includes the exact codebook/token mapping fingerprint and strict keys.
        load_code_injector(injector, config["dit_adapter"])
        pipe._conditioner.code_injector = injector.requires_grad_(False)
    for module in (pipe.text_encoder, pipe.transformer, pipe.vae):
        module.eval().requires_grad_(False)
    pipe.set_progress_bar_config(disable=True)
    return pipe


def check_tensor(actual, expected, *, name, rtol=3e-4, atol=3e-5):
    if (
        actual.shape != expected.shape
        or not torch.isfinite(actual).all()
        or not torch.isfinite(expected).all()
    ):
        raise ValueError(f"Invalid {name} shape or nonfinite tensor")
    delta = (actual.float() - expected.float()).abs()
    torch.testing.assert_close(actual.float(), expected.float(), rtol=rtol, atol=atol, msg=name)
    return {
        "name": name,
        "shape": list(actual.shape),
        "max_abs": float(delta.max()),
        "rtol": rtol,
        "atol": atol,
    }


def prompt_gate(pipe, prompt, images):
    """Check the port against the frozen native prompt frontend on actual input."""
    from diffsynth.pipelines.qwen_image_21 import QwenImage21Unit_PromptEmbedder

    proxy = SimpleNamespace(
        device=pipe._execution_device,
        torch_dtype=torch.bfloat16,
        text_encoder=pipe._conditioner,
        processor=pipe.processor,
        load_models_to_device=lambda _: None,
    )
    with torch.no_grad():
        original = QwenImage21Unit_PromptEmbedder().process(proxy, prompt, images)
        actual, mask, image_mask = pipe._get_qwen_prompt_embeds(prompt, images)
    check = check_tensor(
        actual, original["prompt_embeds"], name="native_prompt_features", rtol=0, atol=0
    )
    if mask is not None or original["prompt_embeds_mask"] is not None:
        raise ValueError("Unexpected padding in batch-one frontend gate")
    if not torch.equal(image_mask, original["edit_image_pad_mask"]):
        raise ValueError("Image-token positions changed")
    return check


def transformer_gate(pipe, *, sit, recipe_path):
    """Compare full trained DiTs, sharing weights instead of allocating two copies.

    A short synthetic joint sequence tests both prefill and cache decoding. This
    is an implementation check, not a quality metric or a generated benchmark case.
    """
    from diffsynth.models.qwen_image_21_dit import QwenImage21DiT, QwenImage21Rope
    from diffusers.models.transformers.transformer_qwenimage21 import QwenImage21KVCache
    from .common import read

    config = dict(pipe.transformer.config)
    allowed = (
        "patch_size",
        "in_channels",
        "out_channels",
        "num_layers",
        "attention_head_dim",
        "num_attention_heads",
        "context_in_dim",
        "mlp_ratio",
        "axes_dims_rope",
        "eps",
        "causal_condition",
    )
    with torch.device("meta"):
        original = QwenImage21DiT(**{k: config[k] for k in allowed})
        if sit:
            from samtok_edit21.models.adapters import add_adapter

            recipe = read(recipe_path)
            add_adapter(
                original,
                recipe["stage"],
                recipe["rank"],
                recipe["dropout"],
                alpha=recipe["alpha"],
                targets=recipe["target_modules"],
            )
    original.load_state_dict(pipe.transformer.state_dict(), strict=True, assign=True)
    # This positional cache is intentionally not a persistent state-dict tensor.
    original.pos_embed = QwenImage21Rope(theta=10000, axes_dim=list(config["axes_dims_rope"]))
    original.eval().requires_grad_(False)
    if any(p.is_meta for p in original.parameters()):
        raise ValueError("Incomplete DiT state transfer")
    device, dtype = pipe.transformer.device, pipe.transformer.dtype
    rng = torch.Generator("cpu").manual_seed(20261112)
    hidden = torch.randn(1, 128, config["in_channels"], generator=rng).to(device, dtype)
    text = torch.randn(1, 24, config["context_in_dim"], generator=rng).to(device, dtype)
    mask = torch.tensor([[False] * 3 + [True] * 16 + [False] * 5 + [True] * 16], device=device)
    cache, native_cache = (
        QwenImage21KVCache(config["num_layers"]),
        [{} for _ in range(config["num_layers"])],
    )
    checks = []
    with torch.no_grad():
        for index, t in enumerate((0.7, 0.4)):
            kwargs = dict(
                hidden_states=hidden,
                encoder_hidden_states=text,
                timestep=torch.tensor([t], device=device, dtype=dtype),
                encoder_hidden_states_mask=None,
                img_shapes=[[(1, 8, 8), (1, 8, 8)]],
                img_mask=mask,
            )
            expected = original(**kwargs, kv_cache=native_cache, use_flex_attention=True)
            actual = pipe.transformer(
                **kwargs,
                kv_cache=cache,
                kv_cache_mode="extract" if index == 0 else "cached",
                return_dict=False,
            )[0]
            # BF16 implementations may tile/reorder equivalent operators. Check
            # normalized error as well as cosine, not per-element relative error
            # around zeros. Thresholds are fixed before any remote timing.
            x, y = actual.float().flatten(), expected.float().flatten()
            relative_rmse = float(
                torch.linalg.vector_norm(x - y) / torch.linalg.vector_norm(y).clamp_min(1e-12)
            )
            cosine = float(torch.nn.functional.cosine_similarity(x[None], y[None]))
            check = {
                "name": "trained_dit_prefill" if index == 0 else "trained_dit_cache",
                "relative_rmse": relative_rmse,
                "cosine": cosine,
                "max_relative_rmse": 0.02,
                "min_cosine": 0.999,
            }
            if (
                not torch.isfinite(x).all()
                or not torch.isfinite(y).all()
                or relative_rmse > 0.02
                or cosine < 0.999
            ):
                raise ValueError(f"DiT implementation validation failed: {check}")
            checks.append(check)
    del original, cache, native_cache
    return checks


class Editor:
    def __init__(self, config, controls, *, sit):
        self.config, self.controls, self.sit = config, controls, sit
        self.pipe = load_pipeline(config, sit=sit, codebook_path=controls["codebook_path"])
        self.gates = transformer_gate(
            self.pipe, sit=sit, recipe_path=Path(config["dit_adapter"]) / "adapter.json"
        )
        self._prompt_checked = False
        self.forward_calls = 0
        self.pipe.transformer.register_forward_hook(self._count)

    def _count(self, *args):
        self.forward_calls += 1

    def preflight(self, request, public, directory):
        if self.sit:
            return
        expected = {
            "num_inference_steps": 40,
            "true_cfg_scale": 1.0,
            "output_resolution": 1024,
            "use_kv_cache": True,
            "width": public["source"]["size"][0],
            "height": public["source"]["size"][1],
        }
        if request["parameters"] != expected or request["seed"] != 42:
            raise ValueError("Qwen request differs from frozen native configuration")

    def request(self, public, previous=None, native_request=None):
        from PIL import Image

        if self.sit:
            from samtok_edit21.data.protocol import strip_tokens
            from samtok_edit21.evaluation.ifbench import pass2_prompt

            spans = {u["id"]: u["token"] for u in previous["units"] if u["token"]}
            prompt = pass2_prompt(public, spans)
            guided = bool(spans) and self.config["token_guidance"] != 1.0
            negative = strip_tokens(prompt) if guided else None
            images = [Image.open(public["source"]["path"]).convert("RGBA")]
            w, h = public["source"]["size"]
            parameters = dict(
                num_inference_steps=40,
                true_cfg_scale=2.0 if guided else 1.0,
                width=w,
                height=h,
                use_kv_cache=True,
                # Retain native SITEdit's condition-image resize area.
                output_resolution=math.sqrt(w * h),
            )
            generator = torch.Generator("cpu").manual_seed(42)
        else:
            prompt, negative = native_request["prompt"], None
            images = [Image.open(p).convert("RGBA") for p in native_request["images"]]
            parameters = dict(native_request["parameters"])
            generator = torch.Generator("cuda").manual_seed(42)
        return prompt, negative, images, parameters, generator

    def validate_prompt(self, public, previous=None, native_request=None):
        prompt, negative, images, kwargs, _ = self.request(public, previous, native_request)
        from diffusers.pipelines.qwenimage21.pipeline_qwenimage21 import calculate_dimensions

        resized = []
        for im in images:
            w, h, _ = calculate_dimensions(kwargs["output_resolution"] ** 2, im.width / im.height)
            resized.append(self.pipe.image_processor.resize(im, width=w, height=h))
        checks = [prompt_gate(self.pipe, prompt, resized)]
        if negative is not None:
            checks.append(prompt_gate(self.pipe, negative, resized))
        self.gates.extend(checks)
        self._prompt_checked = True
        return self.gates

    def run(self, public, directory, previous=None, native_request=None):
        if not self._prompt_checked:
            raise RuntimeError("Prompt validation must precede measurement")
        prompt, negative, images, parameters, generator = self.request(
            public, previous, native_request
        )
        self.forward_calls = 0
        # Both Qwen rows receive the same request-local compiler-state policy.
        # Their common segmented-SDPA path does not compile a full model.
        torch._dynamo.reset()
        image = self.pipe(
            prompt=prompt, negative_prompt=negative, image=images, generator=generator, **parameters
        ).images[0]
        expected = 40 * (2 if negative is not None else 1)
        if self.forward_calls != expected:
            raise ValueError(f"Unexpected DiT forward count: {self.forward_calls} vs {expected}")
        return (
            image,
            {
                "prompt": prompt,
                "negative_prompt": negative,
                "parameters": parameters,
                "backend": "diffusers",
                "memory_policy": "resident",
                "quality_result_reuse": False,
            },
            {"inference_api_calls": 1, "transformer_forward_calls": self.forward_calls},
        )
