#!/usr/bin/env python3
"""Run RePlan on the frozen SAMTok 656-case, four-setting benchmark inputs."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.common import (  # noqa: E402
    BASELINE_VISUAL_PROTOCOL,
    BASE_SETTING_KEYS,
    DEFAULT_BASELINE_PREPARED_MANIFEST,
    DEFAULT_DATASET_ROOT,
    DEFAULT_EXPERIMENT_ROOT,
    DEFAULT_FLUX2,
    DEFAULT_QWEN_2511,
    EXPECTED_CASES,
)

DATASET_ROOT = DEFAULT_DATASET_ROOT
PREPARED_ROOT = DEFAULT_EXPERIMENT_ROOT
MANIFEST = DEFAULT_BASELINE_PREPARED_MANIFEST
OUTPUT_ROOT = Path("/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/replan_656")
PLANNER = Path("/mnt/bn/strategy-mllm-train/user/tanyue/models/posttrain_models/replan_qwen2_5_vl_7b")
REPLAN_REPO = Path("/opt/tiger/tanyue/RePlan")
# Frozen run_config.json from the completed run used the adapter in the method repo.
LEGACY_ADAPTER_SHA256 = "94d6a55132d4dcf9c8ef6f3ca7f1d44f7461412ffecaec9a2bcbdae29b9bf898"
# The exact RePlan pipeline used for the 5,248 published benchmark outputs.
REPLAN_PIPELINE_SHA256 = "3fa5d0e0d03001b8b01cb520c120a6a49011bd644843682b657cf95e802dacc0"
BACKBONES = {
    "qwen2511": (
        "qwen2511",
        DEFAULT_QWEN_2511,
    ),
    "flux2_klein4b": (
        "klein",
        DEFAULT_FLUX2,
    ),
}
SETTINGS = BASE_SETTING_KEYS
ROLES = {
    "text_only": ["clean_source_to_edit"],
    "mask_annotation": ["clean_source_to_edit", "mask_locator_only"],
    "box_annotation": ["clean_source_to_edit", "box_locator_only"],
    "point_annotation": ["clean_source_to_edit", "point_locator_only"],
}
PROTOCOL = BASELINE_VISUAL_PROTOCOL


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_image(path: Path, image: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + f".{os.getpid()}.tmp.png")
    image.save(tmp, format="PNG")
    os.replace(tmp, path)


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        size = image.size
        image.verify()
    return size


def official_size(size: tuple[int, int]) -> tuple[int, int]:
    ratio = size[0] / size[1]
    return (
        max(32, round(math.sqrt(1024 * 1024 * ratio) / 32) * 32),
        max(32, round(math.sqrt(1024 * 1024 / ratio) / 32) * 32),
    )


def load_rows(args: argparse.Namespace) -> list[dict]:
    rows = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line]
    if len(rows) != EXPECTED_CASES or [row.get("eval_index") for row in rows] != list(range(EXPECTED_CASES)):
        raise ValueError(f"Expected exactly {EXPECTED_CASES} benchmark rows with contiguous eval_index values")
    for row in rows:
        if row["prepared"].get("baseline_visual_protocol") != PROTOCOL:
            raise ValueError(f"Wrong frozen input protocol at {row['eval_index']}")
        source = (args.dataset_root / row["source_image"]).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        for setting in SETTINGS:
            item = row["prepared"]["baseline_inputs"][setting]
            paths = [Path(path).resolve() for path in item["images"]]
            if len(paths) != len(ROLES[setting]) or item["image_roles"] != ROLES[setting]:
                raise ValueError(f"Invalid image roles for {row['eval_index']}/{setting}")
            if paths[0] != source:
                raise ValueError(f"First input is not the clean source for {row['eval_index']}/{setting}")
            if setting != "text_only":
                expected = (args.prepared_root / row["prepared"][setting]).resolve()
                if paths[1] != expected:
                    raise ValueError(f"Locator path mismatch for {row['eval_index']}/{setting}")
            if not item["prompt"].strip() or "{region_" in item["prompt"]:
                raise ValueError(f"Invalid frozen prompt for {row['eval_index']}/{setting}")
            for path in paths:
                if not path.is_file():
                    raise FileNotFoundError(path)
            forbidden = [row["evaluation_mask"], row["target"]["reference_image"]]
            if any(value and value in item["images"] for value in forbidden):
                raise ValueError(f"Evaluation-only asset leaked for {row['eval_index']}/{setting}")
    if args.indices:
        selected = set(args.indices)
        if not selected.issubset(set(range(EXPECTED_CASES))):
            raise ValueError(f"--indices must be in [0, {EXPECTED_CASES - 1}]")
        rows = [row for row in rows if row["eval_index"] in selected]
    if args.max_cases is not None:
        rows = rows[: args.max_cases]
    return rows


def check_weights(args: argparse.Namespace) -> None:
    if not args.planner.joinpath("model.safetensors.index.json").is_file():
        raise FileNotFoundError(f"Planner checkpoint incomplete: {args.planner}")
    index = json.loads(args.planner.joinpath("model.safetensors.index.json").read_text())
    for name in set(index["weight_map"].values()):
        if not args.planner.joinpath(name).is_file():
            raise FileNotFoundError(args.planner / name)
    if not args.backbone.joinpath("model_index.json").is_file():
        raise FileNotFoundError(args.backbone / "model_index.json")


def check_method_source(args: argparse.Namespace) -> Path:
    """Require the RePlan implementation used by the validated run.

    The bundled compatibility patch adds ordered planner images, safe region
    parsing, generator forwarding, and an SDPA fallback. A different method
    revision needs a separately named experiment rather than silent resume.
    """
    source = args.replan_repo / "replan/pipelines/replan.py"
    if not source.is_file():
        raise FileNotFoundError(f"Missing RePlan pipeline: {source}")
    actual = sha256(source)
    if actual != REPLAN_PIPELINE_SHA256:
        raise ValueError(
            f"RePlan pipeline SHA256 {actual} differs from the validated "
            f"{REPLAN_PIPELINE_SHA256}; apply evaluation/replan/replan_pipeline_compat.patch "
            "to the pinned RePlan checkout or use a separately reviewed adapter"
        )
    return source


def output_paths(args: argparse.Namespace, setting: str, index: int) -> tuple[Path, Path]:
    root = args.output_root / "inference" / args.model / setting
    stem = f"{index:04d}"
    return root / f"{stem}.png", root / f"{stem}.json"


def is_complete(args: argparse.Namespace, row: dict, setting: str, size: tuple[int, int], manifest_sha: str) -> bool:
    image_path, sidecar_path = output_paths(args, setting, row["eval_index"])
    if not image_path.is_file() or not sidecar_path.is_file():
        return False
    try:
        record = json.loads(sidecar_path.read_text(encoding="utf-8"))
        frozen = row["prepared"]["baseline_inputs"][setting]
        return (
            record["case_id"] == row["id"]
            and record["model"] == args.model
            and record["setting"] == setting
            and record["manifest_sha256"] == manifest_sha
            and record["planner_input_images"] == frozen["images"]
            and record["planner_prompt"] == frozen["prompt"]
            and record["edit_input_image"] == frozen["images"][0]
            and image_size(image_path) == size
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False


def make_config(args: argparse.Namespace, rows: list[dict], manifest_sha: str) -> dict:
    return {
        "protocol": "replan_samtok_frozen_v1",
        "benchmark_input_protocol": PROTOCOL,
        "model": args.model,
        "pipeline_type": BACKBONES[args.model][0],
        "planner_checkpoint": str(args.planner.resolve()),
        "planner_revision": "518f82339520058d043c4fbc270481876d8463e4",
        "backbone_checkpoint": str(args.backbone.resolve()),
        "manifest": str(args.manifest.resolve()),
        "manifest_sha256": manifest_sha,
        "dataset_root": str(args.dataset_root.resolve()),
        "prepared_root": str(args.prepared_root.resolve()),
        "eval_indices": [row["eval_index"] for row in rows],
        "settings": args.settings,
        "world_size": args.world,
        "seed": args.seed,
        "dtype": "bfloat16",
        "planner_input": "frozen ordered clean source and optional locator; frozen prompt",
        "editor_input": "clean source only; RePlan VLM-generated boxes and hints",
        "expand_value": args.expand_value,
        "attention_switch_step": args.attention_switch_step,
        "steps": 40 if args.model == "qwen2511" else 4,
        "true_cfg_scale": 4.0 if args.model == "qwen2511" else None,
        "guidance_scale": 1.0 if args.model == "qwen2511" else 4.0,
        "enable_flex_attn": True,
        "stage_offload": args.stage_offload,
        "output_resolution": (
            "Qwen internal approximately 1024 squared; saved at source size"
            if args.model == "qwen2511" else
            "FLUX.2 native source resolution; saved at exact source size"
        ),
        "postprocessing": "Lanczos resize to source size only; no pasteback or marker removal",
        "adapter_sha256": sha256(Path(__file__)),
        "replan_pipeline_sha256": sha256(args.replan_repo / "replan/pipelines/replan.py"),
        "editor_pipeline_sha256": sha256(
            args.replan_repo / "replan/pipelines/"
            / ("qwen_image_plus.py" if args.model == "qwen2511" else "flux_klein.py")
        ),
        "torch_version": importlib.metadata.version("torch"),
        "transformers_version": importlib.metadata.version("transformers"),
        "diffusers_version": importlib.metadata.version("diffusers"),
    }


def configs_match(old: dict, current: dict) -> bool:
    if old == current:
        return True
    if old.get("adapter_sha256") != LEGACY_ADAPTER_SHA256:
        return False
    # The completed run used the same adapter before its move into this repo.
    # Every model, input, sampling, dependency and method-source field must match.
    return {k: v for k, v in old.items() if k != "adapter_sha256"} == {
        k: v for k, v in current.items() if k != "adapter_sha256"
    }


def check_run_config(args: argparse.Namespace, config: dict) -> None:
    path = args.output_root / "inference" / args.model / "run_config.json"
    if args.rank == 0:
        if path.is_file():
            old = json.loads(path.read_text(encoding="utf-8"))
            if not configs_match(old, config):
                raise ValueError(f"Run config mismatch: {path}")
        else:
            write_json(path, config)
    else:
        deadline = time.monotonic() + 120
        while not path.is_file() and time.monotonic() < deadline:
            time.sleep(0.2)
        if not path.is_file() or not configs_match(
            json.loads(path.read_text(encoding="utf-8")), config
        ):
            raise ValueError(f"Missing or mismatched run config: {path}")


def run(args: argparse.Namespace) -> None:
    rows = load_rows(args)
    check_weights(args)
    check_method_source(args)
    manifest_sha = sha256(args.manifest)
    check_run_config(args, make_config(args, rows, manifest_sha))

    worker_rows = rows[args.rank :: args.world]
    if args.resume and all(
        is_complete(args, row, setting, image_size(Path(row["prepared"]["baseline_inputs"][setting]["images"][0])), manifest_sha)
        for setting in args.settings for row in worker_rows
    ):
        print(f"[rank={args.rank}] all {len(worker_rows) * len(args.settings)} outputs already complete", flush=True)
        return

    sys.path.insert(0, str(args.replan_repo.resolve()))
    import torch
    from replan.pipelines.replan import RePlanPipeline

    torch.cuda.set_device(0)
    pipe = RePlanPipeline(
        vlm_ckpt_path=str(args.planner),
        diffusion_model_name=str(args.backbone),
        pipeline_type=BACKBONES[args.model][0],
        output_dir=str(args.output_root / "inference" / args.model),
        device="cuda:0",
        torch_dtype=torch.bfloat16,
        stage_offload=args.stage_offload,
    )
    torch.cuda.empty_cache()
    pipe.diffusion_pipe.set_progress_bar_config(disable=True)

    errors = 0
    completed = 0
    skipped = 0
    for setting in args.settings:
        progress = tqdm(worker_rows, desc=f"{args.model}/{setting} rank={args.rank}", file=sys.stdout,
                        dynamic_ncols=True, mininterval=2)
        for row in progress:
            index = row["eval_index"]
            frozen = row["prepared"]["baseline_inputs"][setting]
            source = Path(frozen["images"][0])
            source_size = image_size(source)
            image_path, sidecar_path = output_paths(args, setting, index)
            if args.resume and is_complete(args, row, setting, source_size, manifest_sha):
                skipped += 1
                continue
            try:
                start = time.perf_counter()
                response, _, vlm_s = pipe.get_vlm_response(
                    frozen["prompt"], frozen["images"], collect_latency=True
                )
                # Each task gets the same diffusion RNG seed. Planner decoding is greedy by default.
                torch.manual_seed(args.seed)
                torch.cuda.manual_seed_all(args.seed)
                generator = torch.Generator(device="cuda:0").manual_seed(args.seed)
                requested_size = official_size(source_size) if args.model == "qwen2511" else source_size
                generation_kwargs = {
                    "generator": generator,
                    "num_inference_steps": 40 if args.model == "qwen2511" else 4,
                    "guidance_scale": 1.0 if args.model == "qwen2511" else 4.0,
                }
                if args.model == "qwen2511":
                    generation_kwargs["true_cfg_scale"] = 4.0
                edited, _, result = pipe.region_edit_with_attention(
                    str(source), frozen["prompt"], response,
                    expand_value=args.expand_value,
                    attention_switch_step=args.attention_switch_step,
                    skip_save=True,
                    collect_latency=True,
                    pipeline_kwargs=generation_kwargs,
                )
                native_size = edited.size
                if native_size != source_size:
                    edited = edited.resize(source_size, Image.Resampling.LANCZOS)
                record = {
                    "case_id": row["id"],
                    "eval_index": index,
                    "source_dataset": row["source_dataset"],
                    "edit_type": row["edit_type"],
                    "model": args.model,
                    "setting": setting,
                    "worker_rank": args.rank,
                    "world_size": args.world,
                    "manifest_sha256": manifest_sha,
                    "planner_input_images": frozen["images"],
                    "planner_image_roles": frozen["image_roles"],
                    "planner_prompt": frozen["prompt"],
                    "planner_response": response,
                    "planner_attention_backend": pipe.vlm_attention_backend,
                    "edit_input_image": str(source),
                    "predicted_boxes": result["bbox_data"],
                    "region_guidance": result["region_guidance"],
                    "global_prompt": result["global_prompt"],
                    "seed": args.seed,
                    "source_size": list(source_size),
                    "requested_size": list(requested_size),
                    "native_size": list(native_size),
                    "saved_size": list(edited.size),
                    "vlm_seconds": vlm_s,
                    "diffusion_seconds": result.get("latency", {}).get("diffusion_s"),
                    "elapsed_seconds": time.perf_counter() - start,
                    "output_image": str(image_path),
                    "completed_at": utc_now(),
                }
                write_image(image_path, edited)
                write_json(sidecar_path, record)
                completed += 1
                progress.set_postfix(index=index, done=completed, errors=errors)
            except Exception:
                errors += 1
                err = {
                    "eval_index": index, "case_id": row["id"], "setting": setting,
                    "rank": args.rank, "timestamp": utc_now(), "traceback": traceback.format_exc(),
                }
                path = args.output_root / "logs" / f"{args.model}_rank{args.rank}_errors.jsonl"
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(err, ensure_ascii=False) + "\n")
                tqdm.write(f"ERROR {args.model}/{setting}/{index:04d}: {err['traceback']}", file=sys.stdout)
                if args.fail_fast:
                    raise
            finally:
                # Keep the small H100 headroom available across varying case shapes.
                torch.cuda.empty_cache()
    print(f"[rank={args.rank}] completed={completed} skipped={skipped} errors={errors}", flush=True)
    if errors:
        raise RuntimeError(f"{errors} cases failed; see per-rank error JSONL")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=BACKBONES, required=True)
    parser.add_argument("--settings", nargs="+", choices=SETTINGS, default=list(SETTINGS))
    parser.add_argument("--rank", type=int, default=0)
    parser.add_argument("--world", type=int, default=1)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--prepared-root", type=Path, default=PREPARED_ROOT)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--planner", type=Path, default=PLANNER)
    parser.add_argument("--replan-repo", type=Path, default=REPLAN_REPO)
    parser.add_argument("--backbone", type=Path)
    parser.add_argument("--indices", type=int, nargs="*")
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--expand-value", type=float, default=0.0)
    parser.add_argument("--attention-switch-step", type=float, default=0.5)
    parser.add_argument("--stage-offload", choices=("none", "cpu"), default="none")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.rank < args.world:
        parser.error("Require 0 <= rank < world")
    if not args.backbone:
        args.backbone = BACKBONES[args.model][1]
    if args.model == "flux2_klein4b" and args.attention_switch_step == 0.5:
        args.attention_switch_step = 0.05
        args.expand_value = 0.15
    return args


if __name__ == "__main__":
    arguments = parse_args()
    if arguments.dry_run:
        selected_rows = load_rows(arguments)
        check_weights(arguments)
        check_method_source(arguments)
        print(json.dumps({
            "status": "ready", "model": arguments.model,
            "cases": len(selected_rows), "settings": arguments.settings,
            "planned_images": len(selected_rows) * len(arguments.settings),
            "manifest_sha256": sha256(arguments.manifest),
            "replan_pipeline_sha256": REPLAN_PIPELINE_SHA256,
        }, indent=2))
    else:
        run(arguments)
