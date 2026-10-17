"""DiffSynth-Studio editor adapters for the SAMTok v2 runner (`samtok-benchmark-v2 run-editor`).

Each adapter follows the model's official DiffSynth example: the clean source and, when any unit
has a locator, the locator image are passed together as the `edit_image` list. The model output
(about 1 MP at the source aspect ratio, as in the official pipelines) is resized to the source
size with Lanczos, as the runner requires. Sampling settings live in `config` so they are bound
to the run key; device placement (VRAM offload) only changes memory use and comes from the
environment.

Environment:
  SAMTOK_MODEL_ROOT        directory holding the local model folders
  SAMTOK_DIFFSYNTH_OFFLOAD auto | none | cpu | official (default: auto)
  SAMTOK_VRAM_LIMIT_GB     optional; overrides the official per-GPU VRAM limit
"""

from __future__ import annotations

import glob
import math
import os
from pathlib import Path

import torch
from PIL import Image

from prompt import PROMPT_VERSION, build_prompt

MODEL_ROOT = Path(
    os.environ.get(
        "SAMTOK_MODEL_ROOT", "/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models"
    )
)

DEFAULTS = {
    "qwen_image_edit_2511": {
        "model_dir": "Qwen-Image-Edit-2511",
        "num_inference_steps": 40,
        "cfg_scale": 4.0,
        "zero_cond_t": True,
        "edit_image_auto_resize": True,
        "target_area": 1024 * 1024,
        "height_division_factor": 16,
        "width_division_factor": 16,
        "image_names": "picture",
    },
    "qwen_image_21": {
        "model_dir": "Qwen-Image-2.1",
        "num_inference_steps": 40,
        "cfg_scale": 1.0,
        "target_area": 1024 * 1024,
        "height_division_factor": 32,
        "width_division_factor": 32,
        "image_names": "image",
    },
    "flux2_dev": {
        "model_dir": "FLUX.2-dev-modelscope",
        "num_inference_steps": 50,
        "embedded_guidance": 2.5,
        "target_area": 1024 * 1024,
        "height_division_factor": 16,
        "width_division_factor": 16,
        "image_names": "image",
    },
}

_PIPES = {}


def default_config(name: str) -> dict:
    return {"model": name, "prompt_version": PROMPT_VERSION, **DEFAULTS[name]}


def output_size(
    width: int,
    height: int,
    target_area: int,
    width_division_factor: int,
    height_division_factor: int,
) -> tuple[int, int]:
    # Keep the source aspect ratio and use each official pipeline's latent grid.
    ratio = width / height
    w = math.sqrt(target_area * ratio)
    out_w = max(width_division_factor, round(w / width_division_factor) * width_division_factor)
    out_h = max(height_division_factor, round(w / ratio / height_division_factor) * height_division_factor)
    return out_w, out_h


def _files(directory: Path, pattern: str) -> list[str]:
    files = sorted(glob.glob(str(directory / pattern)))
    if not files:
        raise FileNotFoundError(f"no model files match {directory / pattern}")
    return files


def _vram(model: str):
    mode = os.environ.get("SAMTOK_DIFFSYNTH_OFFLOAD", "auto").lower()
    if mode == "auto":
        if not torch.cuda.is_available():
            raise RuntimeError("DiffSynth generation requires CUDA")
        free_gb = torch.cuda.mem_get_info("cuda")[1] / (1024 ** 3)
        # Qwen-Image and Qwen-Image-Edit fit on an 80 GB H100 with the official
        # regular examples. FLUX.2-dev still uses the official CPU offload there.
        if model in {"qwen_image_edit_2511", "qwen_image_21"} and free_gb >= 60:
            return {}, None
        mode = "cpu" if model == "flux2_dev" else "official"
    if mode == "none":
        return {}, None
    if mode == "cpu":
        config = {
            "offload_dtype": torch.bfloat16,
            "offload_device": "cpu",
            "onload_dtype": torch.bfloat16,
            "onload_device": "cuda",
            "preparing_dtype": torch.bfloat16,
            "preparing_device": "cuda",
            "computation_dtype": torch.bfloat16,
            "computation_device": "cuda",
        }
        limit = os.environ.get("SAMTOK_VRAM_LIMIT_GB")
        return config, float(limit) if limit else None
    if mode != "official":
        raise ValueError("SAMTOK_DIFFSYNTH_OFFLOAD must be none, cpu, or official")

    # These settings are copied from DiffSynth-Studio's official low-VRAM examples.
    if model == "qwen_image_21":
        config = {
            "offload_dtype": "disk",
            "offload_device": "disk",
            "onload_dtype": "disk",
            "onload_device": "disk",
            "preparing_dtype": torch.bfloat16,
            "preparing_device": "cuda",
            "computation_dtype": torch.bfloat16,
            "computation_device": "cuda",
        }
    else:
        config = {
            "offload_dtype": "disk",
            "offload_device": "disk",
            "onload_dtype": torch.float8_e4m3fn,
            "onload_device": "cpu",
            "preparing_dtype": torch.float8_e4m3fn,
            "preparing_device": "cuda",
            "computation_dtype": torch.bfloat16,
            "computation_device": "cuda",
        }
    limit = os.environ.get("SAMTOK_VRAM_LIMIT_GB")
    if limit:
        return config, float(limit)
    if not torch.cuda.is_available():
        raise RuntimeError("DiffSynth generation requires CUDA")
    return config, torch.cuda.mem_get_info("cuda")[1] / (1024 ** 3) - 0.5


def _load(config: dict):
    key = (config["model"], config["model_dir"])
    if key in _PIPES:
        return _PIPES[key]
    root = MODEL_ROOT / config["model_dir"]
    vram, limit = _vram(config["model"])
    if config["model"] == "qwen_image_edit_2511":
        from diffsynth.pipelines.qwen_image import ModelConfig, QwenImagePipeline

        pipe = QwenImagePipeline.from_pretrained(
            torch_dtype=torch.bfloat16,
            device="cuda",
            model_configs=[
                ModelConfig(path=_files(root, "transformer/diffusion_pytorch_model*.safetensors"), **vram),
                ModelConfig(path=_files(root, "text_encoder/model*.safetensors"), **vram),
                ModelConfig(path=_files(root, "vae/diffusion_pytorch_model.safetensors"), **vram),
            ],
            tokenizer_config=ModelConfig(path=str(root / "tokenizer")),
            processor_config=ModelConfig(path=str(root / "processor")),
            vram_limit=limit,
        )
    elif config["model"] == "qwen_image_21":
        from diffsynth.pipelines.qwen_image_21 import ModelConfig, QwenImage21Pipeline

        pipe = QwenImage21Pipeline.from_pretrained(
            torch_dtype=torch.bfloat16,
            device="cuda",
            model_configs=[
                ModelConfig(path=_files(root, "transformer/diffusion_pytorch_model*.safetensors"), **vram),
                ModelConfig(path=_files(root, "text_encoder/model*.safetensors"), **vram),
                ModelConfig(path=_files(root, "vae/diffusion_pytorch_model*.safetensors"), **vram),
            ],
            processor_config=ModelConfig(path=str(root / "processor")),
            vram_limit=limit,
        )
    elif config["model"] == "flux2_dev":
        from diffsynth.pipelines.flux2_image import Flux2ImagePipeline, ModelConfig

        pipe = Flux2ImagePipeline.from_pretrained(
            torch_dtype=torch.bfloat16,
            device="cuda",
            model_configs=[
                ModelConfig(path=_files(root, "text_encoder/*.safetensors"), **vram),
                ModelConfig(path=_files(root, "transformer/*.safetensors"), **vram),
                ModelConfig(path=_files(root, "vae/diffusion_pytorch_model.safetensors")),
            ],
            tokenizer_config=ModelConfig(path=str(root / "tokenizer")),
            vram_limit=limit,
        )
    else:
        raise ValueError(f"unknown model {config['model']}")
    _PIPES[key] = pipe
    return pipe


def _to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGBA":
        # Qwen-Image-2.1 returns RGBA; an edited photo should be opaque. Composite any
        # transparency over white, the background its vision encoder was trained with.
        background = Image.new("RGBA", image.size, (255, 255, 255, 255))
        image = Image.alpha_composite(background, image)
    return image.convert("RGB")


def edit(*, job: dict, seed: int, config: dict) -> Image.Image:
    pipe = _load(config)
    images = []
    for path in job["images"]:
        with Image.open(path) as im:
            images.append(im.convert("RGB"))
    source_w, source_h = job["source_size"]
    width, height = output_size(
        source_w,
        source_h,
        config["target_area"],
        config["width_division_factor"],
        config["height_division_factor"],
    )
    prompt = build_prompt(job, config["image_names"])
    if config["model"] == "qwen_image_edit_2511":
        result = pipe(
            prompt,
            edit_image=images,
            seed=seed,
            num_inference_steps=config["num_inference_steps"],
            cfg_scale=config["cfg_scale"],
            height=height,
            width=width,
            edit_image_auto_resize=config["edit_image_auto_resize"],
            zero_cond_t=config["zero_cond_t"],
        )
    elif config["model"] == "qwen_image_21":
        result = pipe(
            prompt,
            edit_image=images,
            seed=seed,
            num_inference_steps=config["num_inference_steps"],
            cfg_scale=config["cfg_scale"],
            height=height,
            width=width,
        )
    else:
        result = pipe(
            prompt,
            edit_image=images,
            seed=seed,
            rand_device="cuda",
            num_inference_steps=config["num_inference_steps"],
            embedded_guidance=config["embedded_guidance"],
            height=height,
            width=width,
        )
    result = _to_rgb(result)
    if result.size != (source_w, source_h):
        result = result.resize((source_w, source_h), Image.Resampling.LANCZOS)
    return result
