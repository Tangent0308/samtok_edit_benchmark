"""Official model, CFG and Euler ancestral code; only safe/offline loading is adapted."""

from __future__ import annotations

import importlib.util
import importlib.metadata
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageOps

from samtok_benchmark.io import sha256_file
from samtok_benchmark.external_magicbrush.bundle import verify_public
from samtok_benchmark.external_magicbrush.data import immutable, read

from .common import TEMP


class _CheckpointMetadata:
    """Inert replacement for the callback class used as a training-metadata key."""


def load_tensors(checkpoint):
    import torch

    # HIVE retains optimizer/callback metadata. No callback code is needed for inference.
    allowed = {
        "numpy.core.multiarray.scalar",
        "numpy.dtype",
        "pytorch_lightning.callbacks.model_checkpoint.ModelCheckpoint",
    }
    unknown = set(torch.serialization.get_unsafe_globals_in_checkpoint(checkpoint)) - allowed
    if unknown:
        raise ValueError(f"Unreviewed checkpoint globals: {sorted(unknown)}")
    with torch.serialization.safe_globals(
        [
            (np._core.multiarray.scalar, "numpy.core.multiarray.scalar"),
            np.dtype,
            type(np.dtype(np.float64)),
            type(np.dtype(np.float32)),
            (_CheckpointMetadata, "pytorch_lightning.callbacks.model_checkpoint.ModelCheckpoint"),
        ]
    ):
        record = torch.load(checkpoint, map_location="cpu", weights_only=True, mmap=True)
    state = record["state_dict"]
    if not isinstance(state, dict) or not all(isinstance(v, torch.Tensor) for v in state.values()):
        raise ValueError("The model state must contain tensors only")
    return state


def native_size(width, height, resolution=512):
    factor = resolution / max(width, height)
    factor = math.ceil(min(width, height) * factor / 64) * 64 / min(width, height)
    return int((width * factor) // 64) * 64, int((height * factor) // 64) * 64


class OfficialEditor:
    def __init__(self, model, config):
        import torch
        from omegaconf import OmegaConf

        self.torch, self.spec = torch, config["models"][model]
        for name, version in config["native_packages"].items():
            if importlib.metadata.version(name) != version:
                raise ValueError(f"Native runtime package changed: {name}")
        root = Path(self.spec["source"])
        loaded_ldm = sys.modules.get("ldm.models.diffusion.ddpm_edit")
        if loaded_ldm is not None and not Path(loaded_ldm.__file__).is_relative_to(root):
            raise ValueError("Each official repository requires its own worker process")
        manifest = root / "SOURCE.json"
        if sha256_file(manifest) != self.spec["source_manifest_sha256"]:
            raise ValueError("Official source manifest changed")
        for entry in read(manifest)["files"]:
            if sha256_file(root / entry["path"]) != entry["sha256"]:
                raise ValueError("Official source changed")
        for folder, expected in config["dependency_manifest_sha256s"].items():
            metadata = Path(folder) / "SOURCE.json"
            if sha256_file(metadata) != expected:
                raise ValueError("Dependency manifest changed")
            for entry in read(metadata)["files"]:
                if (
                    entry["path"].endswith(".py")
                    and sha256_file(Path(folder) / entry["path"]) != entry["sha256"]
                ):
                    raise ValueError("Dependency Python source changed")
        for entry in config["text_init_files"]:
            if sha256_file(Path(config["text_init"]) / entry["name"]) != entry["sha256"]:
                raise ValueError("Offline text initialization/tokenizer changed")
        for p in [*config["deps"].values(), str(root), str(root / "stable_diffusion")]:
            sys.path.insert(0, p)
        import k_diffusion as K
        from stable_diffusion.ldm.util import instantiate_from_config

        spec = importlib.util.spec_from_file_location(
            "ifbench_official_editor", root / "edit_cli.py"
        )
        native = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(native)
        model_config = OmegaConf.load(root / "configs/generate.yaml")
        # Offline initialization only; the complete checkpoint overwrites all learned tensors.
        model_config.model.params.cond_stage_config.params = {"version": config["text_init"]}
        weight = self.spec["checkpoint"]
        local = TEMP / "downloads" / weight["relative"]
        checkpoint = local if local.exists() else Path(weight["path"])
        if sha256_file(checkpoint) != weight["sha256"]:
            raise ValueError("Official weight bytes changed")
        # Do not execute arbitrary pickle globals from a downloaded checkpoint.
        state = load_tensors(checkpoint)
        self.model = instantiate_from_config(model_config.model)
        missing, unexpected = self.model.load_state_dict(state, strict=False)
        if missing or unexpected:
            raise ValueError(
                f"Native checkpoint mismatch: missing={missing}, unexpected={unexpected}"
            )
        del state
        self.model.eval().cuda()
        self.wrapper = K.external.CompVisDenoiser(self.model)
        self.cfg = native.CFGDenoiser(self.wrapper)
        self.sample = K.sampling.sample_euler_ancestral
        with torch.no_grad():
            self.null = self.model.get_learned_conditioning([""])

    def run(self, public, directory):
        verify_public(public)
        if public["track"] != "mask-free" or public["mask"] is not None:
            raise ValueError("Classic additions receive no masks or annotations")
        torch, spec = self.torch, self.spec
        with Image.open(public["source"]["path"]) as source:
            image = source.convert("RGB")
        size = native_size(*image.size, spec["resolution"])
        image = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
        image.save(Path(directory) / "actual_input.png")
        immutable(
            Path(directory) / "call.json",
            {
                "source": public["source"],
                "instruction": public["instruction"],
                "actual_input_size": list(size),
                "parameters": spec,
                "actual_input_sha256": sha256_file(Path(directory) / "actual_input.png"),
                "native_calls": 1,
                "external_components": 0,
            },
        )
        torch.cuda.reset_peak_memory_stats()
        with torch.no_grad(), torch.autocast("cuda"), self.model.ema_scope():
            cond = {"c_crossattn": [self.model.get_learned_conditioning([public["instruction"]])]}
            tensor = 2 * torch.tensor(np.array(image)).float() / 255 - 1
            tensor = tensor.permute(2, 0, 1).unsqueeze(0).to(self.model.device)
            cond["c_concat"] = [self.model.encode_first_stage(tensor).mode()]
            uncond = {
                "c_crossattn": [self.null],
                "c_concat": [torch.zeros_like(cond["c_concat"][0])],
            }
            sigmas = self.wrapper.get_sigmas(spec["steps"])
            args = {
                "cond": cond,
                "uncond": uncond,
                "text_cfg_scale": spec["text_cfg"],
                "image_cfg_scale": spec["image_cfg"],
            }
            torch.manual_seed(spec["seed"])
            z = torch.randn_like(cond["c_concat"][0]) * sigmas[0]
            z = self.sample(self.cfg, z, sigmas, extra_args=args, disable=True)
            x = torch.clamp((self.model.decode_first_stage(z) + 1) / 2, 0, 1)
            pixels = (255 * x.squeeze(0).permute(1, 2, 0)).to(torch.uint8).cpu().numpy()
        torch.cuda.synchronize()
        path = Path(directory) / "raw.png"
        Image.fromarray(pixels).save(path)
        return path
