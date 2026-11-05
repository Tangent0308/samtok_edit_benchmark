#!/usr/bin/env python3
"""CPU verification of the official DINO checkpoint conversion and original forward equations.

This independently written check loads only tensors (weights_only=True). It does not import or execute downloaded
Python, torch.hub code or TorchScript. The equations follow facebookresearch/dino's Apache-2.0 vision transformer.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
if not sys.flags.isolated or os.environ.get("CUDA_VISIBLE_DEVICES") != "":
    raise SystemExit("Run with CUDA_VISIBLE_DEVICES='' python -I")
sys.path.insert(0, str(REPO / "src"))

import torch  # noqa: E402
import torch.nn.functional as F  # noqa: E402
from PIL import Image  # noqa: E402
from samtok_benchmark.external_magicbrush.metrics import Features, cosine  # noqa: E402
from samtok_benchmark.io import sha256_file  # noqa: E402


def original_features(pixels, state):
    """Original ViT-S/16: patch projection, 12 pre-norm blocks, final normalized CLS."""
    x = F.conv2d(
        pixels, state["patch_embed.proj.weight"], state["patch_embed.proj.bias"], stride=16
    )
    x = x.flatten(2).transpose(1, 2)
    x = torch.cat([state["cls_token"].expand(x.shape[0], -1, -1), x], dim=1) + state["pos_embed"]

    def linear(x, key):
        return F.linear(x, state[key + ".weight"], state[key + ".bias"])

    def norm(x, key):
        return F.layer_norm(x, (384,), state[key + ".weight"], state[key + ".bias"], eps=1e-6)

    for layer in range(12):
        key = f"blocks.{layer}"
        normalized = norm(x, key + ".norm1")
        qkv = linear(normalized, key + ".attn.qkv").reshape(x.shape[0], x.shape[1], 3, 6, 64)
        q, k, v = qkv.permute(2, 0, 3, 1, 4).unbind(0)
        attention = ((q @ k.transpose(-1, -2)) * (64**-0.5)).softmax(dim=-1)
        context = (attention @ v).transpose(1, 2).reshape(x.shape)
        x = x + linear(context, key + ".attn.proj")
        hidden = F.gelu(linear(norm(x, key + ".norm2"), key + ".mlp.fc1"))
        x = x + linear(hidden, key + ".mlp.fc2")
    return norm(x, "norm")[:, 0]


def mapping():
    pairs = {"cls_token": "embeddings.cls_token", "pos_embed": "embeddings.position_embeddings"}
    for suffix in ["weight", "bias"]:
        pairs[f"patch_embed.proj.{suffix}"] = f"embeddings.patch_embeddings.projection.{suffix}"
        pairs[f"norm.{suffix}"] = f"layernorm.{suffix}"
        for layer in range(12):
            prefix = f"layers.{layer}."
            for old, new in [
                ("norm1", "layernorm_before"),
                ("norm2", "layernorm_after"),
                ("attn.proj", "attention.o_proj"),
                ("mlp.fc1", "mlp.fc1"),
                ("mlp.fc2", "mlp.fc2"),
            ]:
                pairs[f"blocks.{layer}.{old}.{suffix}"] = prefix + new + "." + suffix
    return pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--images", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cache", required=True)
    args = parser.parse_args()
    torch.set_num_threads(4)
    config = json.loads(Path(args.config).read_text())
    root = Path(config["metrics"]["root"])
    proof = json.loads((root / "dino_original/SOURCE.json").read_text())
    checkpoint = root / "dino_original/dino_deitsmall16_pretrain.pth"
    if sha256_file(checkpoint) != proof["sha256"]:
        raise ValueError("Original checkpoint bytes changed")
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    features = Features(config, args.cache, "cpu")
    converted = features.dino.state_dict()
    checked = set()
    for old, new in mapping().items():
        assert torch.equal(state[old], converted[new]), (old, new)
        checked.add(new)
    for layer in range(12):
        for suffix in ["weight", "bias"]:
            chunks = state[f"blocks.{layer}.attn.qkv.{suffix}"].chunk(3, dim=0)
            for part, name in zip(chunks, ["q_proj", "k_proj", "v_proj"]):
                key = f"layers.{layer}.attention.{name}.{suffix}"
                assert torch.equal(part, converted[key]), key
                checked.add(key)
    assert checked == set(converted), set(converted) - checked
    rows = []
    for path in args.images:
        with Image.open(path) as im:
            pixels = features.transforms["dino"](im.convert("RGB")).unsqueeze(0)
        with torch.inference_mode():
            reference = original_features(pixels, state)[0]
            actual = features.dino(pixel_values=pixels).last_hidden_state[0, 0]
        similarity = cosine(reference.numpy(), actual.numpy())
        error = float((reference - actual).abs().max())
        assert similarity > 1 - 1e-6 and error < 1e-3, (path, similarity, error)
        rows.append(
            {
                "path": str(Path(path).resolve()),
                "sha256": sha256_file(path),
                "feature_cosine": similarity,
                "maximum_absolute_error": error,
            }
        )
    report = {
        "original_checkpoint": proof,
        "hf_tensors_exactly_matching": len(checked),
        "original_layer_norm_eps": 1e-6,
        "scorer_identity": features.identity,
        "images": rows,
        "check_script_sha256": sha256_file(__file__),
        "method": "Exact tensor conversion comparison; independent CPU evaluation of original transformer equations. No downloaded source executed.",
    }
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"tensors_matching": len(checked), "images": rows}, indent=2))


if __name__ == "__main__":
    main()
