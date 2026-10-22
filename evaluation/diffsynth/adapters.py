"""DiffSynth-Studio editor adapters for the SAMTok v2 runner (`samtok-benchmark-v2 run-editor`).

Each adapter follows the model's official DiffSynth example: the clean source and, when any unit
has a locator, the locator image are passed together as the `edit_image` list. The model output
(usually about 1 MP; HiDream uses its official approximately 4 MP resolution buckets) is resized
to the source size with Lanczos, as the runner requires. Sampling settings live in `config` so they are bound
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
import sys
from pathlib import Path

import torch
from PIL import Image

from prompt import PROMPT_VERSION, build_prompt, build_single_image_locator_prompt

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
    "flux2_klein_4b": {
        "model_dir": "FLUX.2-klein-4B",
        # The released Klein checkpoint is distilled for the official 4-step path.
        "num_inference_steps": 4,
        "cfg_scale": 1.0,
        "embedded_guidance": 1.0,
        "target_area": 1024 * 1024,
        "height_division_factor": 16,
        "width_division_factor": 16,
        "image_names": "image",
    },
    "flux3_klein": {
        "model_dir": "flux-3-image-klein",
        "pup_dir": "flux-3-image-klein-pup",
        "num_inference_steps": 16,
        "target_area": 1024 * 1024,
        "height_division_factor": 16,
        "width_division_factor": 16,
        "image_names": "image",
        "pup_memory": 0.35,
        "offload": False,
    },
    "hunyuan_image_30_instruct": {
        # The official Distil checkpoint is the recommended 8-step deployment
        # variant for the HunyuanImage-3.0 family.
        "model_dir": "HunyuanImage-3.0-Instruct-Distil",
        "diff_infer_steps": 8,
        "image_size": "auto",
        "target_area": 1024 * 1024,
        "height_division_factor": 16,
        "width_division_factor": 16,
        "use_system_prompt": "en_unified",
        "bot_task": "think_recaption",
        # Preserve the official reasoning budget. A truncated smoke output
        # establishes connectivity, not benchmark-quality generation.
        "max_new_tokens": 2048,
        "image_names": "image",
        "multi_image": True,
    },
    "hidream_o1_image": {
        "model_dir": "HiDream-O1-Image",
        "num_inference_steps": 50,
        "cfg_scale": 4.0,
        "shift": 3.0,
        "noise_scale": 8.0,
        "model_type": "full",
        # HiDream's pixel-space generator collapses on the old 1 MP setting.
        # Match the original repository's multi-reference resolution selection.
        "target_area": 2048 * 2048,
        "resolution_policy": "hidream_official_2k_buckets_v1",
        "height_division_factor": 32,
        "width_division_factor": 32,
        "image_names": "image",
        "multi_image": True,
    },
    "step1x_edit": {
        "model_dir": "Step1X-Edit",
        "vlm_dir": "Qwen2.5-VL-7B-Instruct",
        "num_inference_steps": 28,
        "cfg_scale": 6.0,
        "target_area": 1024 * 1024,
        "height_division_factor": 16,
        "width_division_factor": 16,
        "image_names": "single",
        "multi_image": False,
    },
    "longcat_image_edit": {
        "model_dir": "LongCat-Image-Edit",
        "num_inference_steps": 50,
        "guidance_scale": 4.5,
        "target_area": 1024 * 1024,
        "height_division_factor": 16,
        "width_division_factor": 16,
        "image_names": "single",
        "multi_image": False,
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


def hidream_output_size(width: int, height: int) -> tuple[int, int]:
    """Official HiDream models/utils.py resolution buckets, in tie-break order.

    Source: HiDream-ai/HiDream-O1-Image, commit
    2c2d29ff729e48f33e41f49edfdbd81d5ac103b4. The original pipeline snaps
    multi-reference editing to these buckets; DiffSynth leaves this to callers.
    """
    resolutions = (
        (2048, 2048), (2304, 1728), (1728, 2304),
        (2560, 1440), (1440, 2560), (2496, 1664), (1664, 2496),
        (3104, 1312), (1312, 3104), (2304, 1792), (1792, 2304),
    )
    return min(resolutions, key=lambda size: abs(size[0] / size[1] - width / height))


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
        # Klein 4B plus its Qwen3 text encoder fits on an 80 GB GPU. Keep both
        # on GPU in the normal case; this is the fast path recommended by the
        # official DiffSynth example.
        if model == "flux2_klein_4b" and free_gb >= 30:
            return {}, None
        if model in {"hidream_o1_image", "step1x_edit"} and free_gb >= 30:
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
    elif model in {"hidream_o1_image", "step1x_edit"}:
        config = {
            "offload_dtype": torch.bfloat16,
            "offload_device": "cpu",
            "onload_dtype": torch.bfloat16,
            "onload_device": "cpu",
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
    configured_root = os.environ.get(
        f"SAMTOK_{config['model'].upper()}_ROOT",
        config["model_dir"],
    )
    root = Path(configured_root)
    if not root.is_absolute():
        root = MODEL_ROOT / root
    vram, limit = ({}, None) if config["model"] == "flux3_klein" else _vram(config["model"])
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
    elif config["model"] in {"flux2_dev", "flux2_klein_4b"}:
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
    elif config["model"] == "flux3_klein":
        # Use Black Forest Labs' reference implementation. It is kept outside the benchmark
        # checkout because it has its own release and dependency set. The adapter deliberately
        # uses the official prompt upsampler and distilled 16-step checkpoint; it does not
        # substitute a DiffSynth or ComfyUI implementation.
        code_root = Path(
            os.environ.get("SAMTOK_FLUX3_CODE", "/opt/tiger/envs/flux3-image-klein")
        )
        source = code_root / "src"
        if not source.is_dir():
            raise FileNotFoundError(f"FLUX.3 reference code is missing: {source}")
        if str(source) not in sys.path:
            sys.path.insert(0, str(source))
        os.environ.setdefault("WEIGHTS_DIR", str(MODEL_ROOT))
        from flux3.pipeline import Pipeline
        from flux3.pup import Upsampler

        root = MODEL_ROOT / config["model_dir"]
        pup = MODEL_ROOT / config["pup_dir"]
        dit = root / "model.safetensors"
        ae = root / "ae.safetensors"
        text_encoder = root / "text_encoder"
        for path in (dit, ae, text_encoder, pup):
            if not path.exists():
                raise FileNotFoundError(f"FLUX.3 weight path is missing: {path}")
        # The small wrapper supplies exactly the attributes consumed by the official generate()
        # function while avoiding its optional safety classifier, which is disabled for benchmark
        # generation and would add an unrelated model to every shard.
        class _OfficialModels:
            pass

        models = _OfficialModels()
        models.upsampler = Upsampler(str(pup), memory=config["pup_memory"])
        models.pipeline = Pipeline(
            {"distilled": str(dit)},
            str(text_encoder),
            str(ae),
            offload=config["offload"],
        )
        pipe = models
    elif config["model"] == "hidream_o1_image":
        from diffsynth.pipelines.hidream_o1_image import HiDreamO1ImagePipeline, ModelConfig

        pipe = HiDreamO1ImagePipeline.from_pretrained(
            torch_dtype=torch.bfloat16,
            device="cuda",
            model_configs=[
                ModelConfig(
                    path=_files(root, "model-*.safetensors"),
                    **vram,
                ),
            ],
            processor_config=ModelConfig(path=str(root)),
            vram_limit=limit,
        )
    elif config["model"] == "step1x_edit":
        from diffsynth.pipelines.flux_image import FluxImagePipeline, ModelConfig

        vlm_root = MODEL_ROOT / config["vlm_dir"]
        pipe = FluxImagePipeline.from_pretrained(
            torch_dtype=torch.bfloat16,
            device="cuda",
            model_configs=[
                ModelConfig(
                    path=_files(vlm_root, "model-*.safetensors"),
                    **vram,
                ),
                ModelConfig(
                    # DiffSynth-Studio's official loader registers the i1258
                    # checkpoint. The newer v1p1 file is kept out of this
                    # adapter until its model hash is supported upstream.
                    path=_files(root, "step1x-edit-i1258.safetensors"),
                    **vram,
                ),
                ModelConfig(path=_files(root, "vae.safetensors"), **vram),
            ],
            step1x_processor_config=ModelConfig(path=str(vlm_root)),
            vram_limit=limit,
        )
    elif config["model"] == "longcat_image_edit":
        from diffusers import LongCatImageEditPipeline

        pipe = LongCatImageEditPipeline.from_pretrained(
            str(root),
            torch_dtype=torch.bfloat16,
        )
        if os.environ.get("SAMTOK_LONGCAT_OFFLOAD", "1") != "0":
            pipe.enable_model_cpu_offload()
        else:
            pipe.to("cuda")
    elif config["model"] == "hunyuan_image_30_instruct":
        from transformers import AutoModelForCausalLM

        pipe = AutoModelForCausalLM.from_pretrained(
            str(root),
            trust_remote_code=True,
            torch_dtype="auto",
            device_map="auto",
            attn_implementation="sdpa",
            moe_impl=os.environ.get("SAMTOK_HUNYUAN_MOE_IMPL", "eager"),
            moe_drop_tokens=True,
        )
        # The January 2026 Instruct checkpoint omits this legacy field from
        # config.json, while the bundled remote tokenizer still reads it.
        # The tokenizer does not branch on the value; supplying the model
        # family name keeps the official loader compatible with the checkpoint.
        if not hasattr(pipe.config, "model_version"):
            pipe.config.model_version = "3.0"
        pipe.load_tokenizer(str(root))
        # ``generate_image`` reads the diffusion-step count from the model's
        # GenerationConfig (the kwarg is forwarded to text generation). Keep
        # the adapter setting authoritative for the image stage.
        pipe.generation_config.diff_infer_steps = config["diff_infer_steps"]
        # Hunyuan's bundled image_processor.py calls the SigLIP2 processor
        # without ``return_tensors`` and then assumes ``pixel_values`` is a
        # tensor.  Transformers 5.x correctly returns a list for the
        # variable-length NaFlex processor in that case.  Keep the official
        # preprocessing path, but request the tensor batch format it expects.
        vit_info = getattr(pipe.image_processor, "vit_info", None)
        if vit_info is not None and getattr(vit_info, "processor", None) is not None:
            original_processor = vit_info.processor

            class _TensorBatchProcessor:
                def __call__(self, image, *args, **kwargs):
                    kwargs.setdefault("return_tensors", "pt")
                    return original_processor(image, *args, **kwargs)

            vit_info.processor = _TensorBatchProcessor()
        # The checkpoint's custom HunyuanStaticCache was written against the
        # pre-5.x Transformers cache API, where lazy_initialization accepted
        # only key_states.  Transformers 5.x also passes value_states so the
        # value head dimension can be initialized.  This model uses equal key
        # and value head dimensions; supplying the key tensor preserves the
        # checkpoint's intended cache layout without modifying remote code.
        from transformers.cache_utils import StaticLayer

        if not getattr(StaticLayer, "_samtok_hunyuan_compat", False):
            original_lazy_init = StaticLayer.lazy_initialization

            def _compat_lazy_init(layer, key_states, value_states=None):
                if value_states is None:
                    value_states = key_states
                return original_lazy_init(layer, key_states, value_states)

            StaticLayer.lazy_initialization = _compat_lazy_init
            StaticLayer._samtok_hunyuan_compat = True
        # The bundled generation override also predates Transformers 5.x and
        # drops ``use_cache`` from the kwargs returned after the prefill.
        # Newer GenerationMixin reads that flag on every decode iteration.
        original_update_kwargs = pipe._update_model_kwargs_for_generation

        def _compat_update_kwargs(*args, **kwargs):
            model_kwargs = args[1] if len(args) > 1 else kwargs["model_kwargs"]
            updated = original_update_kwargs(*args, **kwargs)
            updated.setdefault("use_cache", model_kwargs.get("use_cache", True))
            return updated

        pipe._update_model_kwargs_for_generation = _compat_update_kwargs
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
    if config["model"] == "hidream_o1_image":
        policy = config.get("resolution_policy")
        if policy == "hidream_official_2k_buckets_v1":
            width, height = hidream_output_size(source_w, source_h)
        elif policy is not None:
            raise ValueError(f"unsupported HiDream resolution policy: {policy}")
        # A legacy config without a policy intentionally reproduces its old run.
    if config.get("multi_image", True):
        prompt = build_prompt(job, config["image_names"])
    else:
        prompt = build_single_image_locator_prompt(job)
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
    elif config["model"] in {"flux2_dev", "flux2_klein_4b"}:
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
    elif config["model"] == "hidream_o1_image":
        result = pipe(
            prompt=prompt,
            negative_prompt=" ",
            cfg_scale=config["cfg_scale"],
            height=height,
            width=width,
            seed=seed,
            rand_device="cuda",
            num_inference_steps=config["num_inference_steps"],
            model_type=config["model_type"],
            shift=config["shift"],
            noise_scale=config["noise_scale"],
            edit_image=images,
            keep_original_aspect=False,
        )
    elif config["model"] == "step1x_edit":
        reference = images[-1] if len(images) == 2 else images[0]
        reference = reference.resize((width, height), Image.Resampling.LANCZOS)
        result = pipe(
            prompt=prompt,
            step1x_reference_image=reference,
            width=width,
            height=height,
            cfg_scale=config["cfg_scale"],
            seed=seed,
            rand_device="cuda",
            num_inference_steps=config["num_inference_steps"],
        )
    elif config["model"] == "longcat_image_edit":
        reference = images[-1] if len(images) == 2 else images[0]
        result = pipe(
            reference,
            prompt,
            negative_prompt="",
            guidance_scale=config["guidance_scale"],
            num_inference_steps=config["num_inference_steps"],
            generator=torch.Generator("cpu").manual_seed(seed),
        ).images[0]
    elif config["model"] == "hunyuan_image_30_instruct":
        paths = job["images"]
        # Passing an explicit aligned HxW avoids spending the short generation
        # budget on Hunyuan's automatic ratio-token stage. It is still the
        # benchmark's 1MP aspect-preserving target size.
        image_size = config["image_size"]
        if image_size == "auto":
            image_size = f"{height}x{width}"
        _, samples = pipe.generate_image(
            prompt=prompt,
            image=paths,
            seed=seed,
            image_size=image_size,
            use_system_prompt=config["use_system_prompt"],
            bot_task=config["bot_task"],
            infer_align_image_size=True,
            diff_infer_steps=config["diff_infer_steps"],
            max_new_tokens=config["max_new_tokens"],
            use_cache=True,
            verbose=0,
        )
        result = samples[0]
    else:
        from flux3.generate import generate

        result, _ = generate(
            pipe,
            "distilled",
            prompt,
            images,
            width=width,
            height=height,
            steps=config["num_inference_steps"],
            seed=seed,
            pup=True,
            safety=False,
        )
    result = _to_rgb(result)
    if result.size != (source_w, source_h):
        result = result.resize((source_w, source_h), Image.Resampling.LANCZOS)
    return result
