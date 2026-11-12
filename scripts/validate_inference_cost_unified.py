#!/usr/bin/env python3
"""CPU-only numerical and actual-checkpoint contracts for the Diffusers port."""

import argparse
import json
import os
from pathlib import Path
import sys


def validate(method, plan_path, codebook):
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    for path in (method / "src", method / "third_party/diffsynth", method / "third_party"):
        sys.path.insert(0, str(path))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    import torch
    from safetensors import safe_open
    from safetensors.torch import load_file
    from transformers import AutoTokenizer
    from diffusers import QwenImage21Transformer2DModel, FlowMatchEulerDiscreteScheduler
    from diffusers.models.transformers.transformer_qwenimage21 import QwenImage21KVCache
    from diffusers.pipelines.qwenimage21.pipeline_qwenimage21 import (
        calculate_dimensions,
        calculate_shift,
    )
    from diffsynth.models.qwen_image_21_dit import QwenImage21DiT
    from diffsynth.diffusion.flow_match import FlowMatchScheduler
    from diffsynth.pipelines.qwen_image_21 import QwenImage21Unit_EditImageEmbedder
    from samtok_edit21.models.adapters import add_adapter
    from samtok_edit21.models.code_injector import CodeInjector, load_code_injector
    from samtok_benchmark.inference_cost.common import read, sha
    from samtok_benchmark.inference_cost.unified import check_tensor

    torch.set_num_threads(4)
    plan = read(plan_path)
    config = plan["method"]
    assert (config["steps"], config["token_guidance"], config["seed"]) == (40, 2.0, 42)
    actual_config = read(Path(config["qwen"]) / "transformer/config.json")
    recipe = read(Path(config["dit_adapter"]) / "adapter.json")
    with torch.device("meta"):
        full = QwenImage21Transformer2DModel.from_config(actual_config)
        add_adapter(
            full,
            recipe["stage"],
            recipe["rank"],
            recipe["dropout"],
            alpha=recipe["alpha"],
            targets=recipe["target_modules"],
        )
    expected = {k: tuple(v.shape) for k, v in full.named_parameters() if v.requires_grad}
    with safe_open(
        str(Path(config["dit_adapter"]) / "adapter.safetensors"), framework="pt", device="cpu"
    ) as tensors:
        actual = {k: tuple(tensors.get_slice(k).get_shape()) for k in tensors.keys()}
    if expected != actual:
        raise ValueError(
            f"Adapter mapping differs: missing={set(expected) - set(actual)}, extra={set(actual) - set(expected)}"
        )
    del full
    tokenizer = AutoTokenizer.from_pretrained(config["samtok"], local_files_only=True)
    injector = CodeInjector(
        load_file(str(codebook))["codebook"],
        [tokenizer.convert_tokens_to_ids(f"<|mt_{i:04d}|>") for i in range(512)],
        tokenizer.convert_tokens_to_ids("<|mt_end|>"),
    )
    load_code_injector(injector, config["dit_adapter"])
    # Random tiny models test the complete architecture, including cache update
    # and sequence layout; actual trained adapter coverage is checked above.
    tiny = dict(
        patch_size=1,
        in_channels=4,
        out_channels=4,
        num_layers=2,
        attention_head_dim=64,
        num_attention_heads=1,
        context_in_dim=32,
        axes_dims_rope=(16, 24, 24),
        mlp_ratio=2,
        causal_condition=True,
    )
    torch.manual_seed(20261112)
    target = QwenImage21Transformer2DModel(**tiny).eval()
    original = QwenImage21DiT(**tiny).eval()
    original.load_state_dict(target.state_dict(), strict=True)
    mask = torch.tensor([[False] * 3 + [True] * 4 + [False] * 5 + [True] * 4])
    inputs = dict(
        hidden_states=torch.randn(1, 32, 4),
        encoder_hidden_states=torch.randn(1, 12, 32),
        timestep=torch.tensor([0.7]),
        encoder_hidden_states_mask=None,
        img_shapes=[[(1, 4, 4), (1, 4, 4)]],
        img_mask=mask,
    )
    cache, native_cache = QwenImage21KVCache(2), [{}, {}]
    checks = []
    # The pinned generation environment also contains GPU-only xFormers.
    # Select the mathematically equivalent CPU SDPA for this architecture test;
    # the real trained GPU check is run separately by each remote worker.
    from unittest.mock import patch
    import diffsynth.models.qwen_image_21_dit as native_module

    def cpu_attention(q, k, v, attn_mask=None, use_flex=False):
        return torch.nn.functional.scaled_dot_product_attention(
            q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2), attn_mask=attn_mask
        ).transpose(1, 2)

    with torch.no_grad(), patch.object(native_module, "_attention", cpu_attention):
        for name, mode in (("prefill", "extract"), ("cache", "cached")):
            a = original(**inputs, kv_cache=native_cache, use_flex_attention=False)
            b = target(**inputs, kv_cache=cache, kv_cache_mode=mode, return_dict=False)[0]
            checks.append(check_tensor(b, a, name=name))
        target_state = target.state_dict()
        with torch.device("meta"):
            meta = QwenImage21DiT(**tiny)
        meta.load_state_dict(target_state, strict=True, assign=True)
        assert all(not p.is_meta for p in meta.parameters())
    schedules, sizes = [], []
    for request in plan["requests"]:
        public = read(request["public"])
        w, h = public["source"]["size"]
        old = QwenImage21Unit_EditImageEmbedder.calculate_dimensions(w * h, w / h)
        new = calculate_dimensions((w * h) ** 0.5 * (w * h) ** 0.5, w / h)[:2]
        if tuple(old) != tuple(new):
            raise ValueError(f"Native SITEdit condition geometry changed: {public['case_id']}")
        sizes.append([w, h])
        if [w, h] in sizes[:-1]:
            continue
        scheduler = FlowMatchEulerDiscreteScheduler.from_pretrained(
            config["qwen"], subfolder="scheduler", local_files_only=True
        )
        native = FlowMatchScheduler("Qwen-Image")
        length = (w // 16) * (h // 16)
        native.set_timesteps(40, dynamic_shift_len=length)
        import numpy as np

        mu = calculate_shift(length, 256, 8192, 0.5, 0.9)
        scheduler.set_timesteps(40, sigmas=np.linspace(1, 1 / 40, 40), mu=mu, device="cpu")
        schedules.append(
            check_tensor(
                scheduler.sigmas[:-1], native.sigmas, name=f"schedule_{w}_{h}", rtol=1e-5, atol=1e-6
            )
        )
    assert not torch.cuda.is_initialized()
    return {
        "status": "passed",
        "gpu_executed": False,
        "adapter_tensor_count": len(actual),
        "adapter_names_shapes_exact": True,
        "codebook_sha256": sha(codebook),
        "codebook_binding_fingerprint": injector.fingerprint(),
        "tiny_dit_checks": checks,
        "scheduler_checks": schedules,
        "native_condition_geometries_checked": len(sizes),
        "bf16_bitwise_equivalence_claimed": False,
        "quality_equivalence_claimed": False,
        "source_files": {
            str(p): sha(p)
            for p in [
                Path(__file__),
                Path(__file__).resolve().parents[1]
                / "src/samtok_benchmark/inference_cost/unified.py",
            ]
        },
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("method", "plan", "codebook", "output", "extra"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    sys.path.insert(0, str(a.extra))
    result = validate(a.method, a.plan, a.codebook)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
