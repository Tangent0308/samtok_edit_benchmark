#!/usr/bin/env python3
"""Run one benchmark model across its frozen five-setting protocol."""

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
    DEFAULT_DATASET_ROOT,
    DEFAULT_DIT_LORA,
    DEFAULT_EXPERIMENT_ROOT,
    DEFAULT_FLUX2,
    DEFAULT_MERGED_TE,
    DEFAULT_PREPARED_MANIFEST,
    DEFAULT_QWEN_2511,
    DEFAULT_SAMTOK_REPO,
    DEFAULT_SAMTOK_TE,
    DEFAULT_TE_LORA,
    FLUX2_MODEL_ID,
    FLUX2_REVISION,
    SettingSpec,
    annotated_prompt,
    atomic_write_json,
    atomic_write_jsonl,
    completed_record,
    distributed_context,
    distributed_rank0_call,
    load_prepared_manifest,
    official_output_size,
    output_paths,
    parse_settings,
    paste_back,
    resolve_path,
    setting_dicts,
    sha256_file,
    summarize_records,
    verify_image,
)


EXPECTED_TE_LORA_SHA256 = "9ce0ad749df5b8602d9b741d4fb95b3081cdd86cd1dbba4a590b210f171aa119"
EXPECTED_DIT_LORA_SHA256 = "b37743956d44704f0294d045d34b22217c8c17e294afba2de97693a98524d2b4"


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
    qwen_dit = sorted(Path(path) for path in glob(str(args.qwen_2511 / "transformer/*.safetensors")))
    samtok_te = sorted(Path(path) for path in glob(str(args.samtok_te / "model*.safetensors")))
    require_files(
        "SAMTokEdit model",
        qwen_dit
        + samtok_te
        + [
            args.qwen_2511 / "vae/diffusion_pytorch_model.safetensors",
            args.merged_te / "samtok_edit_manifest.json",
            args.te_lora,
            args.dit_lora,
        ],
    )
    te_hash, dit_hash = sha256_file(args.te_lora), sha256_file(args.dit_lora)
    if te_hash != EXPECTED_TE_LORA_SHA256:
        raise ValueError(f"Unexpected refined four-node TE LoRA SHA256: {te_hash}")
    if dit_hash != EXPECTED_DIT_LORA_SHA256:
        raise ValueError(f"Unexpected refined four-node DiT LoRA SHA256: {dit_hash}")
    from safetensors import safe_open

    checkpoint_schema = {}
    for name, path, prefix in (
        ("stage1_te", args.te_lora, "model.language_model."),
        ("stage2_dit", args.dit_lora, None),
    ):
        with safe_open(path, framework="pt", device="cpu") as handle:
            keys = list(handle.keys())
        count_a = sum(".lora_A." in key for key in keys)
        count_b = sum(".lora_B." in key for key in keys)
        if not keys or count_a != count_b or len(keys) != count_a + count_b:
            raise ValueError(f"Invalid LoRA-only checkpoint schema: {path}")
        if prefix and not all(key.startswith(prefix) for key in keys):
            raise ValueError(f"Stage-1 checkpoint contains non-TE keys: {path}")
        if name == "stage2_dit" and any(key.startswith("model.language_model.") for key in keys):
            raise ValueError(f"Stage-2 checkpoint unexpectedly contains TE keys: {path}")
        checkpoint_schema[name] = {"tensor_keys": len(keys), "lora_pairs": count_a}
    return {
        "name": "SAMTokEdit refined four-node",
        "base_model": "Qwen-Image-Edit-2511",
        "diffsynth_pipeline": "QwenImageSamtokPipeline",
        "qwen_2511_path": str(args.qwen_2511.resolve()),
        "samtok_te_path": str(args.samtok_te.resolve()),
        "merged_processor_path": str(args.merged_te.resolve()),
        "stage1_te_lora": str(args.te_lora.resolve()),
        "stage1_te_lora_sha256": te_hash,
        "stage2_dit_lora": str(args.dit_lora.resolve()),
        "stage2_dit_lora_sha256": dit_hash,
        "checkpoint_schema": checkpoint_schema,
    }


def add_samtok_paths(samtok_repo: Path) -> None:
    for path in (
        samtok_repo / "DiffSynth-Studio",
        samtok_repo / "scripts/inference",
        samtok_repo / "scripts/eval",
        samtok_repo / "scripts/data",
    ):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def load_pipeline(args: argparse.Namespace, device: str):
    add_samtok_paths(args.samtok_repo)
    if args.model == "qwen":
        # SAMTokEdit's evaluation entry points were consolidated from
        # ``run_stage1_eval.py`` into ``run_eval.py``.  Import the current
        # canonical loader; it is the same DiffSynth QwenImagePipeline loader
        # that produced the completed benchmark run.
        from run_eval import load_stock_pipeline

        return load_stock_pipeline(args.qwen_2511, device)
    if args.model == "samtok_edit":
        from infer_samtok_edit import build_pipeline

        return build_pipeline(
            args.qwen_2511,
            args.samtok_te,
            args.merged_te,
            te_lora=args.te_lora,
            dit_lora=args.dit_lora,
            device=device,
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
        "samtok_max_new_tokens": args.samtok_max_new_tokens if args.model == "samtok_edit" else None,
    }


def run_config(
    args: argparse.Namespace,
    settings: list[SettingSpec],
    prepared_report: dict,
    model_report: dict,
    world_size: int,
    selected_rows: list[dict],
) -> dict:
    return {
        "protocol": "samtok_finegrained_edit_benchmark_inference_v1",
        "model": args.model,
        "model_artifacts": model_report,
        "settings": setting_dicts(settings),
        "data": prepared_report,
        "selection": {
            "count": len(selected_rows),
            "eval_index_start": selected_rows[0]["eval_index"],
            "eval_index_stop_inclusive": selected_rows[-1]["eval_index"],
        },
        "generation": {
            "seed_rule": f"constant seed={args.seed} for every case and setting",
            "native_size": "source aspect ratio at approximately 1024*1024 pixels, rounded to /32",
            "saved_size": "resized back to exact source width and height with Lanczos",
            "edit_image_auto_resize": True,
            **model_generation_config(args),
        },
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
) -> tuple[Image.Image, Path, str, str | None]:
    prepared = row["prepared"]
    source_path = resolve_path(row["source_image"], dataset_root)
    if setting.input_mode == "source":
        input_path = source_path
    else:
        input_path = resolve_path(prepared[setting.input_mode], prepared_root)
    with Image.open(input_path) as image:
        model_input = image.convert("RGB")
    if setting.samtok_mode == "umt_mask":
        prompt = prepared["samtok_prompts"]["mask_umt"]
    elif setting.samtok_mode == "umt_box_sam2":
        prompt = prepared["samtok_prompts"]["box_sam2_umt"]
    elif setting.samtok_mode == "umt_point_sam2":
        prompt = prepared["samtok_prompts"]["point_sam2_umt"]
    elif setting.prompt_mode == "with_location_reference":
        prompt = row["instruction"]["with_location_reference"]
    else:
        prompt = annotated_prompt(
            row["instruction"]["region_only"],
            len(row["regions"]),
            setting.input_mode.removesuffix("_annotation"),
        )
    mt_cot = None
    if setting.samtok_mode == "mt_mask":
        mt_cot = prepared["mask_mt_cot"]
    return model_input, input_path, prompt, mt_cot


def generate(
    pipe,
    args: argparse.Namespace,
    setting: SettingSpec,
    model_input: Image.Image,
    prompt: str,
    mt_cot: str | None,
    seed: int,
    native_size: tuple[int, int],
    device: str,
) -> tuple[Image.Image, dict]:
    width, height = native_size
    if args.model == "qwen":
        output = pipe(
            prompt,
            edit_image=[model_input],
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
            edit_image=[model_input],
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
    from infer_samtok_edit import run_edit

    output = run_edit(
        pipe,
        model_input,
        prompt,
        seed=seed,
        num_inference_steps=args.qwen_steps,
        cfg_scale=args.qwen_cfg_scale,
        mt_cot=mt_cot,
        enable_samtok_cot=setting.samtok_mode == "online",
        samtok_max_new_tokens=args.samtok_max_new_tokens,
        output_height=height,
        output_width=width,
    )
    telemetry = {
        "conditioned_mt_cot": getattr(pipe, "last_mt_cot", None),
        "pass1_raw": getattr(pipe, "last_pass1_raw", None),
        "parse_layer": getattr(pipe, "last_parse_layer", None),
        "user_mask_audit": getattr(pipe, "last_user_mask_audit", None),
    }
    if setting.samtok_mode and setting.samtok_mode.startswith("umt_"):
        audit = telemetry["user_mask_audit"] or {}
        expected = len(setting_prompt_spans(prompt))
        if not (
            expected > 0
            and audit.get("user_mask_span_count") == expected
            and audit.get("user_mask_spans_atomic") is True
            and audit.get("user_mask_spans_in_template") is True
        ):
            raise RuntimeError(f"SAMTok UMT tokenizer/template audit failed: {audit}")
    return output, telemetry


def setting_prompt_spans(prompt: str) -> list[str]:
    import re

    return re.findall(
        r"<\|mt_start\|><\|mt_\d{4}\|><\|mt_\d{4}\|><\|mt_end\|>", prompt
    )


def save_png_atomic(path: Path, image: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp.png")
    image.save(temporary)
    temporary.replace(path)


def build_record(
    args: argparse.Namespace,
    setting: SettingSpec,
    row: dict,
    input_path: Path,
    output_path: Path,
    prompt: str,
    seed: int,
    native_size: tuple[int, int],
    source_size: tuple[int, int],
    elapsed: float,
    telemetry: dict,
    derived_from_output: Path | None = None,
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
        "model_input_image": str(input_path.resolve()),
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
        "derived_from_output": str(derived_from_output.resolve()) if derived_from_output else None,
        "worker_rank": int(os.environ.get("RANK", "0")),
        "world_size": int(os.environ.get("WORLD_SIZE", "1")),
        **telemetry,
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
        model_input, input_path, prompt, mt_cot = input_and_prompt(
            row, setting, args.dataset_root, args.prepared_root
        )
        native_size = official_output_size(source)
        sample_seed = args.seed
        started = time.perf_counter()
        derived_from_output = None
        if setting.pasteback:
            if not setting.derived_from:
                raise RuntimeError("Paste-back setting has no source setting")
            derived_from_output, _ = output_paths(
                args.experiment_root, args.model, setting.derived_from, row["eval_index"]
            )
            if not derived_from_output.is_file():
                raise FileNotFoundError(
                    f"Paste-back requires the exact source generation: {derived_from_output}"
                )
            with Image.open(derived_from_output) as image:
                generated = image.convert("RGB")
            evaluation_mask_path = resolve_path(row["evaluation_mask"], args.dataset_root)
            with Image.open(evaluation_mask_path) as image:
                evaluation_mask = image.convert("L")
            output = paste_back(source, generated, evaluation_mask)
            telemetry = {"postprocess": "hard binary evaluation-mask paste-back"}
        else:
            native, telemetry = generate(
                pipe, args, setting, model_input, prompt, mt_cot, sample_seed, native_size, device
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
            input_path,
            output_path,
            prompt,
            sample_seed,
            native_size,
            source_size,
            elapsed,
            telemetry,
            derived_from_output,
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
    parser.add_argument("--model", choices=("qwen", "flux2", "samtok_edit"), required=True)
    parser.add_argument("--settings", nargs="+", default=["all"])
    parser.add_argument("--prepared_manifest", type=Path, default=DEFAULT_PREPARED_MANIFEST)
    parser.add_argument("--prepared_root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--dataset_root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--experiment_root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--samtok_repo", type=Path, default=DEFAULT_SAMTOK_REPO)
    parser.add_argument("--qwen_2511", type=Path, default=DEFAULT_QWEN_2511)
    parser.add_argument("--flux2", type=Path, default=DEFAULT_FLUX2)
    parser.add_argument("--samtok_te", type=Path, default=DEFAULT_SAMTOK_TE)
    parser.add_argument("--merged_te", type=Path, default=DEFAULT_MERGED_TE)
    parser.add_argument("--te_lora", type=Path, default=DEFAULT_TE_LORA)
    parser.add_argument("--dit_lora", type=Path, default=DEFAULT_DIT_LORA)
    parser.add_argument("--qwen_steps", type=int, default=40)
    parser.add_argument("--qwen_cfg_scale", type=float, default=4.0)
    parser.add_argument("--flux_steps", type=int, default=4)
    parser.add_argument("--samtok_max_new_tokens", type=int, default=128)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--start_index", type=int, default=0)
    parser.add_argument("--max_samples", type=int, default=None)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry_run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.qwen_steps <= 0 or args.flux_steps <= 0 or args.samtok_max_new_tokens <= 0:
        raise ValueError("Inference steps and max-new-tokens must be positive")
    if args.qwen_cfg_scale <= 0 or args.start_index < 0:
        raise ValueError("CFG scale must be positive and start index non-negative")
    world_size, rank, local_rank, device = distributed_context(args.device)
    try:
        settings = parse_settings(args.model, args.settings)

        def preflight():
            rows, prepared_report = load_prepared_manifest(
                args.prepared_manifest, args.prepared_root
            )
            stop = None if args.max_samples is None else args.start_index + args.max_samples
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
                            "planned_generations": len(rows) * sum(not x.pasteback for x in settings),
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
        # Paste-back is deterministic post-processing; a model is still loaded once
        # because its source setting is automatically included by parse_settings.
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
