#!/usr/bin/env python3
"""Run Qwen-Image-Edit-2511 or FLUX.2 on the frozen benchmark inputs."""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from glob import glob
from pathlib import Path

import torch
from PIL import Image

from common import (
    DEFAULT_BASELINE_PREPARED_MANIFEST,
    DEFAULT_DATASET_ROOT,
    DEFAULT_EXPERIMENT_ROOT,
    DEFAULT_FLUX2,
    DEFAULT_QWEN_2511,
    DEFAULT_SAMTOK_REPO,
    FLUX2_MODEL_ID,
    FLUX2_REVISION,
    SettingSpec,
    atomic_write_json,
    atomic_write_jsonl,
    completed_record,
    distributed_context,
    distributed_rank0_call,
    load_prepared_manifest,
    official_output_size,
    output_paths,
    parse_settings,
    resolve_path,
    setting_dicts,
    sha256_file,
    summarize_records,
    verify_image,
)


def require_files(label: str, paths: list[Path]) -> None:
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing {label}: {missing[:5]}")


def validate_model_artifacts(args: argparse.Namespace) -> dict:
    if args.model == "qwen":
        model_index_path = args.qwen_2511 / "model_index.json"
        require_files("Qwen model index", [model_index_path])
        model_index = json.loads(model_index_path.read_text(encoding="utf-8"))
        if model_index.get("_class_name") != "QwenImageEditPlusPipeline":
            raise ValueError(f"Not a Qwen-Image-Edit-2511 checkpoint: {model_index_path}")
        qwen_dit = sorted(Path(path) for path in glob(str(args.qwen_2511 / "transformer/*.safetensors")))
        qwen_te = sorted(Path(path) for path in glob(str(args.qwen_2511 / "text_encoder/*.safetensors")))
        qwen_vae = args.qwen_2511 / "vae/diffusion_pytorch_model.safetensors"
        require_files("Qwen-Image-Edit-2511", qwen_dit + qwen_te + [qwen_vae])
        return {
            "name": "Qwen-Image-Edit-2511",
            "path": str(args.qwen_2511.resolve()),
            "diffsynth_pipeline": "QwenImagePipeline",
            "model_index_sha256": sha256_file(model_index_path),
            "dit_shards": len(qwen_dit),
            "text_encoder_shards": len(qwen_te),
        }
    if args.model == "flux2":
        model_index_path = args.flux2 / "model_index.json"
        require_files("FLUX model index", [model_index_path])
        model_index = json.loads(model_index_path.read_text(encoding="utf-8"))
        flux_dit = sorted(Path(path) for path in glob(str(args.flux2 / "transformer/*.safetensors")))
        flux_te = sorted(Path(path) for path in glob(str(args.flux2 / "text_encoder/*.safetensors")))
        flux_vae = args.flux2 / "vae/diffusion_pytorch_model.safetensors"
        require_files(
            "FLUX.2-klein-4B",
            flux_dit + flux_te + [flux_vae, args.flux2 / "tokenizer/tokenizer_config.json"],
        )
        return {
            "name": FLUX2_MODEL_ID,
            "revision": FLUX2_REVISION,
            "path": str(args.flux2.resolve()),
            "diffsynth_pipeline": "Flux2ImagePipeline",
            "model_index_class": model_index.get("_class_name"),
            "model_index_sha256": sha256_file(model_index_path),
            "dit_shards": len(flux_dit),
            "text_encoder_shards": len(flux_te),
            "fallback_reason": (
                "FLUX.2-dev is gated and the configured Hugging Face account did not have access; "
                "the benchmark plan explicitly permits the Klein variant"
            ),
        }
    raise ValueError(args.model)


def add_diffsynth_paths(samtok_repo: Path) -> None:
    path = samtok_repo / "DiffSynth-Studio"
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def load_pipeline(args: argparse.Namespace, device: str):
    add_diffsynth_paths(args.samtok_repo)
    if args.model == "qwen":
        from diffsynth.pipelines.qwen_image import ModelConfig, QwenImagePipeline

        return QwenImagePipeline.from_pretrained(
            torch_dtype=torch.bfloat16,
            device=device,
            model_configs=[
                ModelConfig(
                    path=sorted(
                        glob(
                            str(
                                args.qwen_2511
                                / "transformer/diffusion_pytorch_model*.safetensors"
                            )
                        )
                    )
                ),
                ModelConfig(
                    path=sorted(
                        glob(str(args.qwen_2511 / "text_encoder/model*.safetensors"))
                    )
                ),
                ModelConfig(
                    path=str(
                        args.qwen_2511 / "vae/diffusion_pytorch_model.safetensors"
                    )
                ),
            ],
            tokenizer_config=ModelConfig(path=str(args.qwen_2511 / "tokenizer")),
            processor_config=ModelConfig(path=str(args.qwen_2511 / "processor")),
        )
    from diffsynth.pipelines.flux2_image import Flux2ImagePipeline, ModelConfig

    return Flux2ImagePipeline.from_pretrained(
        torch_dtype=torch.bfloat16,
        device=device,
        model_configs=[
            ModelConfig(path=sorted(glob(str(args.flux2 / "text_encoder/*.safetensors")))),
            ModelConfig(path=sorted(glob(str(args.flux2 / "transformer/*.safetensors")))),
            ModelConfig(path=str(args.flux2 / "vae/diffusion_pytorch_model.safetensors")),
        ],
        tokenizer_config=ModelConfig(path=str(args.flux2 / "tokenizer")),
    )


def model_generation_config(args: argparse.Namespace) -> dict:
    if args.model == "flux2":
        return {
            "num_inference_steps": args.flux_steps,
            "cfg_scale": 1.0,
            "embedded_guidance": 4.0,
            "rand_device": "worker CUDA device",
        }
    return {
        "num_inference_steps": args.qwen_steps,
        "cfg_scale": args.qwen_cfg_scale,
        "zero_cond_t": True,
        # Kept in the frozen config for compatibility with the in-progress run.
        "samtok_max_new_tokens": None,
    }


def run_config(
    args: argparse.Namespace,
    settings: list[SettingSpec],
    prepared_report: dict,
    model_report: dict,
    world_size: int,
    selected_rows: list[dict],
) -> dict:
    selected_indices = [row["eval_index"] for row in selected_rows]
    return {
        "protocol": "samtok_finegrained_edit_benchmark_inference_v2",
        "model": args.model,
        "model_artifacts": model_report,
        "settings": setting_dicts(settings),
        "data": prepared_report,
        "selection": {
            "count": len(selected_rows),
            "eval_indices": selected_indices,
            "contiguous": selected_indices
            == list(range(selected_indices[0], selected_indices[-1] + 1)),
        },
        "generation": {
            "seed_rule": f"constant seed={args.seed} for every case and setting",
            "native_size": "source aspect ratio at approximately 1024*1024 pixels, rounded to /32",
            "saved_size": "resized back to exact source width and height with Lanczos",
            "edit_image_auto_resize": True,
            **model_generation_config(args),
        },
        "reference_image_policy": {
            "text_only": ["clean_source_to_edit"],
            "mask_box_point": ["clean_source_to_edit", "annotated_locator_only"],
            "ordered_edit_image_list": True,
        },
        # The last two null-control descriptions remain metadata-only so the
        # active Qwen run can be resumed against its already-written config.
        # There is no paste-back setting or implementation in this repository.
        "fairness": {
            "target_fields_used_as_model_input": False,
            "evaluation_mask_used_during_generation": False,
            "evaluation_mask_exception": (
                "mask_annotation_pasteback is an explicitly named oracle post-processing control"
            ),
            "pasteback_sampling": (
                "deterministically derived from the exact mask_annotation output; no second generation"
            ),
        },
        "parallelism": {
            "world_size": world_size,
            "partition": "selected_rows[rank::world_size]",
            "pipeline_loads_per_worker": 1,
        },
        "prepared_root": str(args.prepared_root.resolve()),
        "output_root": str(args.experiment_root.resolve()),
    }


def input_and_prompt(
    row: dict,
    setting: SettingSpec,
    dataset_root: Path,
    prepared_root: Path,
) -> tuple[list[Image.Image], list[Path], list[str], str]:
    del dataset_root, prepared_root  # Paths are frozen as absolute paths in the manifest.
    frozen = row["prepared"]["baseline_inputs"][setting.key]
    input_paths = [Path(path) for path in frozen["images"]]
    model_inputs = []
    for input_path in input_paths:
        with Image.open(input_path) as image:
            model_inputs.append(image.convert("RGB"))
    return model_inputs, input_paths, list(frozen["image_roles"]), frozen["prompt"]


def generate(
    pipe,
    args: argparse.Namespace,
    model_inputs: list[Image.Image],
    prompt: str,
    seed: int,
    native_size: tuple[int, int],
    device: str,
) -> tuple[Image.Image, dict]:
    width, height = native_size
    if args.model == "qwen":
        output = pipe(
            prompt,
            edit_image=model_inputs,
            seed=seed,
            num_inference_steps=args.qwen_steps,
            cfg_scale=args.qwen_cfg_scale,
            height=height,
            width=width,
            edit_image_auto_resize=True,
            zero_cond_t=True,
        )
        return output, {}
    if args.model == "flux2":
        output = pipe(
            prompt,
            edit_image=model_inputs,
            seed=seed,
            rand_device=device,
            num_inference_steps=args.flux_steps,
            cfg_scale=1.0,
            embedded_guidance=4.0,
            height=height,
            width=width,
            edit_image_auto_resize=True,
        )
        return output, {}
    raise ValueError(args.model)


def save_png_atomic(path: Path, image: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp.png")
    image.save(temporary)
    temporary.replace(path)


def build_record(
    args: argparse.Namespace,
    setting: SettingSpec,
    row: dict,
    input_paths: list[Path],
    input_roles: list[str],
    output_path: Path,
    prompt: str,
    seed: int,
    native_size: tuple[int, int],
    source_size: tuple[int, int],
    elapsed: float,
) -> dict:
    target_ref = row["target"]["reference_image"]
    return {
        "eval_index": row["eval_index"],
        "case_id": row["id"],
        "model": args.model,
        "setting": setting.key,
        "source_dataset": row["source_dataset"],
        "edit_type": row["edit_type"],
        "region_count": len(row["regions"]),
        "source_image": str(resolve_path(row["source_image"], args.dataset_root).resolve()),
        "model_input_images": [str(path.resolve()) for path in input_paths],
        "model_input_roles": input_roles,
        "target_reference_image": (
            str(resolve_path(target_ref, args.dataset_root).resolve()) if target_ref else None
        ),
        "evaluation_mask": str(resolve_path(row["evaluation_mask"], args.dataset_root).resolve()),
        "output": str(output_path.resolve()),
        "with_location_instruction": row["instruction"]["with_location_reference"],
        "region_only_instruction": row["instruction"]["region_only"],
        "conditioned_prompt": prompt,
        "seed": seed,
        "native_generation_size": list(native_size),
        "saved_source_size": list(source_size),
        "elapsed_seconds": elapsed,
        "derived_from_output": None,
        "worker_rank": int(os.environ.get("RANK", "0")),
        "world_size": int(os.environ.get("WORLD_SIZE", "1")),
    }


def run_setting(
    pipe,
    args: argparse.Namespace,
    setting: SettingSpec,
    rows: list[dict],
    rank: int,
    world_size: int,
    device: str,
) -> list[dict]:
    records = []
    for position, row in enumerate(rows, 1):
        source_path = resolve_path(row["source_image"], args.dataset_root)
        with Image.open(source_path) as image:
            source = image.convert("RGB")
        source_size = source.size
        old = completed_record(
            args.experiment_root,
            args.model,
            setting.key,
            row["eval_index"],
            row["id"],
            source_size,
        ) if args.resume else None
        if old is not None:
            records.append(old)
            print(
                f"[{args.model}/{setting.key} rank={rank}] {position}/{len(rows)} "
                f"index={row['eval_index']} resumed",
                flush=True,
            )
            continue
        output_path, sidecar_path = output_paths(
            args.experiment_root, args.model, setting.key, row["eval_index"]
        )
        model_inputs, input_paths, input_roles, prompt = input_and_prompt(
            row, setting, args.dataset_root, args.prepared_root
        )
        if any(model_input.size != source_size for model_input in model_inputs):
            raise ValueError(
                f"Input geometry mismatch for {args.model}/{setting.key}/{row['eval_index']:04d}"
            )
        native_size = official_output_size(source)
        sample_seed = args.seed
        started = time.perf_counter()
        native, _ = generate(
            pipe, args, model_inputs, prompt, sample_seed, native_size, device
        )
        if native.size != native_size:
            raise RuntimeError(
                f"Unexpected native output size {native.size}; requested {native_size}"
            )
        output = native.convert("RGB").resize(source_size, Image.Resampling.LANCZOS)
        elapsed = time.perf_counter() - started
        save_png_atomic(output_path, output)
        record = build_record(
            args,
            setting,
            row,
            input_paths,
            input_roles,
            output_path,
            prompt,
            sample_seed,
            native_size,
            source_size,
            elapsed,
        )
        atomic_write_json(sidecar_path, record)
        records.append(record)
        print(
            f"[{args.model}/{setting.key} rank={rank}] {position}/{len(rows)} "
            f"index={row['eval_index']} seconds={elapsed:.2f}",
            flush=True,
        )
    return records


def collect_records(args: argparse.Namespace, setting: SettingSpec, rows: list[dict]) -> list[dict]:
    records, missing = [], []
    for row in rows:
        source_size = verify_image(resolve_path(row["source_image"], args.dataset_root))
        record = completed_record(
            args.experiment_root,
            args.model,
            setting.key,
            row["eval_index"],
            row["id"],
            source_size,
        )
        if record is None:
            missing.append(row["eval_index"])
        else:
            records.append(record)
    if missing:
        raise RuntimeError(f"{args.model}/{setting.key} missing outputs: {missing[:20]}")
    records.sort(key=lambda record: record["eval_index"])
    root = args.experiment_root / "inference" / args.model / setting.key
    atomic_write_jsonl(root / "results.jsonl", records)
    return records


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("qwen", "flux2"), required=True)
    parser.add_argument("--settings", nargs="+", default=["all"])
    parser.add_argument("--prepared_manifest", type=Path, default=None)
    parser.add_argument("--prepared_root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--dataset_root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--experiment_root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--samtok_repo", type=Path, default=DEFAULT_SAMTOK_REPO)
    parser.add_argument("--qwen_2511", type=Path, default=DEFAULT_QWEN_2511)
    parser.add_argument("--flux2", type=Path, default=DEFAULT_FLUX2)
    parser.add_argument("--qwen_steps", type=int, default=40)
    parser.add_argument("--qwen_cfg_scale", type=float, default=4.0)
    parser.add_argument("--flux_steps", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--start_index", type=int, default=0)
    parser.add_argument("--max_samples", type=int, default=None)
    parser.add_argument(
        "--eval_indices",
        nargs="+",
        type=int,
        default=None,
        help="Exact benchmark eval indices to run, in the requested order.",
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry_run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.prepared_manifest is None:
        args.prepared_manifest = DEFAULT_BASELINE_PREPARED_MANIFEST
    if args.qwen_steps <= 0 or args.flux_steps <= 0:
        raise ValueError("Inference steps must be positive")
    if args.qwen_cfg_scale <= 0 or args.start_index < 0:
        raise ValueError("CFG scale must be positive and start index non-negative")
    world_size, rank, local_rank, device = distributed_context(args.device)
    try:
        settings = parse_settings(args.model, args.settings)

        def preflight():
            rows, prepared_report = load_prepared_manifest(
                args.prepared_manifest, args.prepared_root
            )
            if args.eval_indices is not None:
                if args.start_index != 0 or args.max_samples is not None:
                    raise ValueError(
                        "--eval_indices cannot be combined with --start_index/--max_samples"
                    )
                if len(set(args.eval_indices)) != len(args.eval_indices):
                    raise ValueError("--eval_indices contains duplicates")
                invalid = [index for index in args.eval_indices if not 0 <= index < len(rows)]
                if invalid:
                    raise ValueError(f"Invalid --eval_indices: {invalid}")
                selected = [rows[index] for index in args.eval_indices]
            else:
                stop = (
                    None
                    if args.max_samples is None
                    else args.start_index + args.max_samples
                )
                selected = rows[args.start_index:stop]
            if not selected:
                raise ValueError("No rows selected")
            return selected, prepared_report, validate_model_artifacts(args)

        rows, prepared_report, model_report = distributed_rank0_call(
            world_size, rank, preflight
        )
        config = run_config(
            args, settings, prepared_report, model_report, world_size, rows
        )

        if args.dry_run:
            if rank == 0:
                print(
                    json.dumps(
                        {
                            "status": "ok",
                            "models_loaded": False,
                            "planned_result_rows": len(rows) * len(settings),
                            "planned_generations": len(rows) * len(settings),
                            "rows_per_rank": [len(rows[i::world_size]) for i in range(world_size)],
                            **config,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            return

        def prepare_output():
            root = args.experiment_root / "inference" / args.model
            config_path = root / "run_config.json"
            if root.exists() and any(root.iterdir()) and not args.resume:
                raise RuntimeError(f"Output model directory is not empty: {root}")
            root.mkdir(parents=True, exist_ok=True)
            if args.resume and any(root.iterdir()):
                if not config_path.is_file():
                    raise RuntimeError(
                        f"Refusing to resume outputs without an immutable run config: {root}"
                    )
                previous = json.loads(config_path.read_text(encoding="utf-8"))
                if previous != config:
                    raise RuntimeError(f"Resume config mismatch: {config_path}")
            else:
                atomic_write_json(config_path, config)
            return str(config_path)

        config_path = distributed_rank0_call(world_size, rank, prepare_output)

        if device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError(f"CUDA is unavailable: {device}")
        worker_rows = rows[rank::world_size]
        print(
            f"[worker] model={args.model} rank={rank}/{world_size} local_rank={local_rank} "
            f"device={device} rows={len(worker_rows)} settings={[x.key for x in settings]}",
            flush=True,
        )
        pipe = load_pipeline(args, device)
        for setting in settings:
            run_setting(pipe, args, setting, worker_rows, rank, world_size, device)
        del pipe
        gc.collect()
        torch.cuda.empty_cache()
        if world_size > 1:
            torch.distributed.barrier()

        def finalize():
            records_by_setting = {
                setting.key: collect_records(args, setting, rows) for setting in settings
            }
            report = {
                "status": "complete",
                "protocol": config["protocol"],
                "model": args.model,
                "settings": {
                    key: summarize_records(records) for key, records in records_by_setting.items()
                },
            }
            atomic_write_json(
                args.experiment_root / "inference" / args.model / "report.json", report
            )
            return report

        report = distributed_rank0_call(world_size, rank, finalize)
        if rank == 0:
            print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        if world_size > 1 and torch.distributed.is_initialized():
            torch.distributed.destroy_process_group()


if __name__ == "__main__":
    main()
