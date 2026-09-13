#!/usr/bin/env python3
"""Shared, model-free benchmark evaluation utilities."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, UnidentifiedImageError


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_ROOT = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark"
)
DEFAULT_MANIFEST = DEFAULT_DATASET_ROOT / "benchmark.jsonl"
DEFAULT_EXPERIMENT_ROOT = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/"
    "finegrained_edit_benchmark"
)
DEFAULT_PREPARED_MANIFEST = DEFAULT_EXPERIMENT_ROOT / "prepared/benchmark_eval_inputs.jsonl"
DEFAULT_SAMTOK_REPO = Path("/opt/tiger/tanyue/samtok_edit")
DEFAULT_QWEN_2511 = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/"
    "Qwen-Image-Edit-2511"
)
DEFAULT_FLUX2 = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/"
    "FLUX.2-klein-4B"
)
DEFAULT_SAMTOK_TE = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/models/SAMTok/"
    "Qwen2.5-VL-7B-SAMTok-gres-ft"
)
DEFAULT_MERGED_TE = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/"
    "artifacts/merged_samtok_te"
)
DEFAULT_TE_LORA = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/"
    "crispedit_refined_4node/crispedit-refined-4node-20260910-run2/"
    "stage1_te_lora/step-2648.safetensors"
)
DEFAULT_DIT_LORA = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/"
    "crispedit_refined_4node/crispedit-refined-4node-20260910-run2/"
    "stage2_dit_lora/step-5296.safetensors"
)
SAM2_MODEL_ID = "facebook/sam2.1-hiera-small"
SAM2_REVISION = "e07df6aa19f5c6545121551bf89957b7663ee715"
FLUX2_MODEL_ID = "black-forest-labs/FLUX.2-klein-4B"
FLUX2_REVISION = "e7b7dc27f91deacad38e78976d1f2b499d76a294"

REGION_COLORS = ((235, 50, 45), (45, 180, 70), (45, 105, 230))
REGION_COLOR_NAMES = ("red", "green", "blue")
PLACEHOLDER_RE = re.compile(r"\{region_(\d+)\}")
SAMTOK_SPAN_RE = re.compile(
    r"<\|mt_start\|><\|mt_(\d{4})\|><\|mt_(\d{4})\|><\|mt_end\|>"
)


@dataclass(frozen=True)
class SettingSpec:
    model: str
    key: str
    input_mode: str
    prompt_mode: str
    samtok_mode: str | None = None
    pasteback: bool = False
    derived_from: str | None = None


BASE_SETTING_KEYS = (
    "text_only",
    "mask_annotation",
    "box_annotation",
    "point_annotation",
    "mask_annotation_pasteback",
)
SAMTOK_SETTING_KEYS = (
    "online_cot",
    "mask_umt",
    "box_sam2_umt",
    "point_sam2_umt",
    "mask_mt",
)


def settings_for_model(model: str) -> list[SettingSpec]:
    if model in {"qwen", "flux2"}:
        return [
            SettingSpec(model, "text_only", "source", "with_location_reference"),
            SettingSpec(model, "mask_annotation", "mask_annotation", "region_only"),
            SettingSpec(model, "box_annotation", "box_annotation", "region_only"),
            SettingSpec(model, "point_annotation", "point_annotation", "region_only"),
            SettingSpec(
                model,
                "mask_annotation_pasteback",
                "mask_annotation",
                "region_only",
                pasteback=True,
                derived_from="mask_annotation",
            ),
        ]
    if model == "samtok_edit":
        return [
            SettingSpec(model, "online_cot", "source", "with_location_reference", "online"),
            SettingSpec(model, "mask_umt", "source", "region_only", "umt_mask"),
            SettingSpec(model, "box_sam2_umt", "source", "region_only", "umt_box_sam2"),
            SettingSpec(model, "point_sam2_umt", "source", "region_only", "umt_point_sam2"),
            SettingSpec(model, "mask_mt", "source", "with_location_reference", "mt_mask"),
        ]
    raise ValueError(f"Unknown model: {model!r}")


def parse_settings(model: str, values: list[str]) -> list[SettingSpec]:
    available = settings_for_model(model)
    if not values or values == ["all"]:
        return available
    requested: list[str] = []
    for value in values:
        for token in value.split(","):
            token = token.strip()
            if token and token not in requested:
                requested.append(token)
    by_key = {setting.key: setting for setting in available}
    unknown = [key for key in requested if key not in by_key]
    if unknown:
        raise ValueError(
            f"Unknown settings for {model}: {unknown}; available={sorted(by_key)}"
        )
    selected = [by_key[key] for key in requested]
    if any(setting.pasteback for setting in selected):
        source_key = next(setting.derived_from for setting in selected if setting.pasteback)
        if source_key not in requested:
            selected.insert(0, by_key[source_key])
    return selected


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def atomic_write_jsonl(path: Path, records: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    temporary.replace(path)


def resolve_path(reference: str | Path, root: Path) -> Path:
    path = Path(reference)
    return path if path.is_absolute() else root / path


def relative_to_root(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def verify_image(path: Path) -> tuple[int, int]:
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        with Image.open(path) as image:
            size = image.size
            image.verify()
            return size
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError(f"Not a decodable image: {path}") from error


def read_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from error
    return records


def load_benchmark(manifest: Path, dataset_root: Path, verify_assets: bool = True) -> tuple[list[dict], dict]:
    rows = read_jsonl(manifest)
    if len(rows) != 500:
        raise ValueError(f"Expected 500 benchmark rows, found {len(rows)}")
    ids: set[str] = set()
    sources: set[str] = set()
    region_counts = Counter()
    datasets = Counter()
    edit_types = Counter()
    for index, row in enumerate(rows):
        required = {
            "id", "source_dataset", "edit_type", "source_image", "instruction",
            "regions", "evaluation_mask", "target", "difficulty",
        }
        if set(row) != required:
            raise ValueError(f"row {index}: top-level schema mismatch")
        case_id = row["id"]
        if not isinstance(case_id, str) or not case_id or case_id in ids:
            raise ValueError(f"row {index}: invalid or duplicate id {case_id!r}")
        ids.add(case_id)
        source_ref = row["source_image"]
        if source_ref in sources:
            raise ValueError(f"row {index}: duplicate source_image {source_ref!r}")
        sources.add(source_ref)
        regions = row["regions"]
        if len(regions) not in {1, 2}:
            raise ValueError(f"row {index}: expected one or two regions")
        prompt = row["instruction"]["region_only"]
        expected_placeholders = [str(number) for number in range(1, len(regions) + 1)]
        if PLACEHOLDER_RE.findall(prompt) != expected_placeholders:
            raise ValueError(f"row {index}: region placeholders/order mismatch")
        if not row["instruction"]["with_location_reference"].strip():
            raise ValueError(f"row {index}: empty with-location instruction")
        if verify_assets:
            source_size = verify_image(resolve_path(source_ref, dataset_root))
            evaluation_size = verify_image(resolve_path(row["evaluation_mask"], dataset_root))
            if evaluation_size != source_size:
                raise ValueError(f"row {index}: evaluation mask geometry mismatch")
            for region_index, region in enumerate(regions):
                mask_size = verify_image(resolve_path(region["mask"], dataset_root))
                if mask_size != source_size:
                    raise ValueError(
                        f"row {index} region {region_index}: input mask geometry mismatch"
                    )
                x1, y1, x2, y2 = region["box"]
                px, py = region["point"]
                if not (0 <= x1 < x2 <= source_size[0] and 0 <= y1 < y2 <= source_size[1]):
                    raise ValueError(f"row {index} region {region_index}: invalid box")
                if not (0 <= px < source_size[0] and 0 <= py < source_size[1]):
                    raise ValueError(f"row {index} region {region_index}: invalid point")
        region_counts[len(regions)] += 1
        datasets[row["source_dataset"]] += 1
        edit_types[row["edit_type"]] += 1
        row["eval_index"] = index
    return rows, {
        "manifest": str(manifest.resolve()),
        "manifest_sha256": sha256_file(manifest),
        "dataset_root": str(dataset_root.resolve()),
        "rows": len(rows),
        "unique_ids": len(ids),
        "unique_source_images": len(sources),
        "datasets": dict(sorted(datasets.items())),
        "edit_types": dict(sorted(edit_types.items())),
        "region_counts": dict(sorted(region_counts.items())),
        "assets_verified": verify_assets,
    }


def load_prepared_manifest(path: Path, experiment_root: Path) -> tuple[list[dict], dict]:
    rows = read_jsonl(path)
    if len(rows) != 500:
        raise ValueError(f"Expected 500 prepared rows, found {len(rows)}")
    asset_paths: set[Path] = set()
    for index, row in enumerate(rows):
        if row.get("eval_index") != index:
            raise ValueError(f"prepared row {index}: non-contiguous eval_index")
        prepared = row.get("prepared", {})
        for field in ("mask_annotation", "box_annotation", "point_annotation"):
            asset_paths.add(resolve_path(prepared[field], experiment_root))
        for modality in ("mask", "box_sam2", "point_sam2"):
            spans = prepared["samtok_spans"][modality]
            if len(spans) != len(row["regions"]):
                raise ValueError(f"prepared row {index}: {modality} span count mismatch")
            for span in spans:
                match = SAMTOK_SPAN_RE.fullmatch(span)
                if not match or not (
                    0 <= int(match.group(1)) < 256
                    and 256 <= int(match.group(2)) < 512
                ):
                    raise ValueError(f"prepared row {index}: invalid SAMTok span {span!r}")
            prompt_key = {
                "mask": "mask_umt",
                "box_sam2": "box_sam2_umt",
                "point_sam2": "point_sam2_umt",
            }[modality]
            if SAMTOK_SPAN_RE.findall(prepared["samtok_prompts"][prompt_key]) != [
                SAMTOK_SPAN_RE.fullmatch(span).groups() for span in spans
            ]:
                raise ValueError(f"prepared row {index}: {prompt_key} span/order mismatch")
            if modality == "mask" and SAMTOK_SPAN_RE.findall(
                prepared["mask_mt_cot"]
            ) != [SAMTOK_SPAN_RE.fullmatch(span).groups() for span in spans]:
                raise ValueError(f"prepared row {index}: mask MT CoT span/order mismatch")
        for modality in ("box_sam2_masks", "point_sam2_masks"):
            paths = prepared[modality]
            if len(paths) != len(row["regions"]):
                raise ValueError(f"prepared row {index}: {modality} count mismatch")
            for item in paths:
                asset_paths.add(resolve_path(item, experiment_root))
    with ThreadPoolExecutor(max_workers=32) as pool:
        list(pool.map(verify_image, sorted(asset_paths)))
    return rows, {
        "prepared_manifest": str(path.resolve()),
        "prepared_manifest_sha256": sha256_file(path),
        "rows": len(rows),
        "prepared_assets_verified": len(asset_paths),
    }


def official_output_size(source: Image.Image, target_area: int = 1024 * 1024) -> tuple[int, int]:
    ratio = source.width / source.height
    width = round(math.sqrt(target_area * ratio) / 32) * 32
    height = round(math.sqrt(target_area / ratio) / 32) * 32
    return max(32, width), max(32, height)


def _font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ):
        if Path(path).is_file():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, color: tuple[int, int, int], scale: int) -> None:
    font = _font(15 * scale)
    padding = 3 * scale
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=max(1, scale // 2))
    width, height = bbox[2] - bbox[0] + 2 * padding, bbox[3] - bbox[1] + 2 * padding
    x, y = xy
    draw.rounded_rectangle(
        (x, y, x + width, y + height), radius=3 * scale, fill=(*color, 235)
    )
    draw.text(
        (x + padding, y + padding - bbox[1]), text, font=font, fill="white",
        stroke_width=max(1, scale // 2), stroke_fill=(0, 0, 0, 210),
    )


def render_annotation(
    source: Image.Image,
    regions: list[dict],
    dataset_root: Path,
    mode: str,
) -> Image.Image:
    """Render the frozen colored/numbered visual-prompt protocol."""

    if mode not in {"mask", "box", "point"}:
        raise ValueError(mode)
    base = source.convert("RGBA")
    short_side = min(source.size)
    line_width = max(3, round(short_side * 0.006))
    point_radius = max(7, round(short_side * 0.014))
    if mode == "mask":
        for index, region in enumerate(regions):
            color = REGION_COLORS[index]
            with Image.open(resolve_path(region["mask"], dataset_root)) as image:
                mask = image.convert("L")
            binary = mask.point(lambda value: 255 if value > 0 else 0)
            fill = Image.new("RGBA", source.size, (*color, 0))
            fill.putalpha(binary.point(lambda value: 70 if value > 0 else 0))
            base = Image.alpha_composite(base, fill)
            kernel = line_width * 2 + 1
            outer = binary.filter(ImageFilter.MaxFilter(kernel))
            inner = binary.filter(ImageFilter.MinFilter(kernel))
            edge = np.asarray(outer, dtype=np.uint8) > np.asarray(inner, dtype=np.uint8)
            edge_mask = Image.fromarray((edge * 255).astype(np.uint8), "L")
            base = Image.composite(Image.new("RGBA", source.size, (*color, 255)), base, edge_mask)

        # The frozen protocol numbers only multi-region inputs. A label on a
        # single target adds no disambiguating information and is an avoidable
        # text-residue failure mode for the baseline models.
        if len(regions) > 1:
            draw = ImageDraw.Draw(base, "RGBA")
            for index, region in enumerate(regions):
                x1, y1, _, _ = region["box"]
                _label(draw, (x1, max(0, y1 - 24)), f"R{index + 1}", REGION_COLORS[index], 1)
        return base.convert("RGB")

    # Draw vector primitives at 4x and downsample only the transparent overlay,
    # preserving source pixels while obtaining antialiased borders and markers.
    scale = 4
    overlay = Image.new("RGBA", (source.width * scale, source.height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    for index, region in enumerate(regions):
        color = REGION_COLORS[index]
        if mode == "box":
            x1, y1, x2, y2 = region["box"]
            draw.rectangle(
                (x1 * scale, y1 * scale, (x2 - 1) * scale, (y2 - 1) * scale),
                outline=(*color, 255), width=line_width * scale,
            )
            label_xy = (x1 * scale, max(0, y1 * scale - 24 * scale))
        else:
            x, y = region["point"]
            r = point_radius * scale
            draw.ellipse(
                (x * scale - r, y * scale - r, x * scale + r, y * scale + r),
                fill=(*color, 255), outline=(255, 255, 255, 255), width=max(2, line_width // 2) * scale,
            )
            label_xy = ((x + point_radius + 3) * scale, max(0, (y - point_radius - 18) * scale))
        if len(regions) > 1:
            _label(draw, label_xy, f"R{index + 1}", color, scale)
    overlay = overlay.resize(source.size, Image.Resampling.LANCZOS)
    return Image.alpha_composite(base, overlay).convert("RGB")


def annotated_prompt(region_only: str, region_count: int, modality: str = "mask") -> str:
    if modality not in {"mask", "box", "point"}:
        raise ValueError(modality)
    nouns = {
        "mask": ("highlighted area", "colored highlights and labels"),
        "box": ("colored box", "colored boxes and labels"),
        "point": ("colored point", "colored points and labels"),
    }
    noun, marks = nouns[modality]
    prompt = region_only
    if region_count == 1:
        single_references = {
            "mask": "the area highlighted in red",
            "box": "the region inside the red box",
            "point": "the location marked by the red point",
        }
        prompt = prompt.replace("{region_1}", single_references[modality])
        legend = {
            "mask": "the area highlighted in red marks the target region",
            "box": "the red box marks the target region",
            "point": "the red point marks the target region",
        }[modality]
        marks = {
            "mask": "red highlight",
            "box": "red box",
            "point": "red point",
        }[modality]
    else:
        for index in range(region_count):
            prompt = prompt.replace(
                f"{{region_{index + 1}}}",
                f"the region marked R{index + 1} in {REGION_COLOR_NAMES[index]}",
            )
        legend = "; ".join(
            f"R{index + 1} is the {noun} in {REGION_COLOR_NAMES[index]}"
            for index in range(region_count)
        )
    if PLACEHOLDER_RE.search(prompt):
        raise ValueError(f"Unresolved region placeholder: {prompt}")
    marker_instruction = (
        f"The {marks} is an instruction only; do not preserve, reproduce, or draw it in the result."
        if region_count == 1
        else f"The {marks} are instructions only; do not preserve, reproduce, or draw them in the result."
    )
    return (
        f"The image contains temporary visual markers: {legend}. {prompt} "
        "Change only the marked target region or regions and keep everything else exactly the same. "
        f"{marker_instruction}"
    )


def token_prompt(region_only: str, spans: list[str]) -> str:
    prompt = region_only
    for index, span in enumerate(spans, 1):
        prompt = prompt.replace(f"{{region_{index}}}", span)
    if PLACEHOLDER_RE.search(prompt):
        raise ValueError(f"Unresolved region placeholder: {prompt}")
    return prompt


def paste_back(source: Image.Image, generated: Image.Image, evaluation_mask: Image.Image) -> Image.Image:
    generated = generated.convert("RGB").resize(source.size, Image.Resampling.LANCZOS)
    mask = evaluation_mask.convert("L").resize(source.size, Image.Resampling.NEAREST)
    mask = mask.point(lambda value: 255 if value > 0 else 0)
    return Image.composite(generated, source.convert("RGB"), mask)


def output_paths(experiment_root: Path, model: str, setting: str, index: int) -> tuple[Path, Path]:
    root = experiment_root / "inference" / model / setting
    return root / f"{index:04d}.png", root / f"{index:04d}.json"


def completed_record(
    experiment_root: Path,
    model: str,
    setting: str,
    index: int,
    case_id: str,
    source_size: tuple[int, int],
) -> dict | None:
    image_path, json_path = output_paths(experiment_root, model, setting, index)
    if not image_path.is_file() or not json_path.is_file():
        return None
    try:
        record = json.loads(json_path.read_text(encoding="utf-8"))
        size = verify_image(image_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if (
        record.get("model") != model
        or record.get("setting") != setting
        or record.get("eval_index") != index
        or record.get("case_id") != case_id
        or size != source_size
    ):
        return None
    return record


def summarize_records(records: list[dict]) -> dict:
    summary = {
        "count": len(records),
        "elapsed_seconds_total": sum(float(row.get("elapsed_seconds", 0.0)) for row in records),
        "edit_types": dict(sorted(Counter(row["edit_type"] for row in records).items())),
        "source_datasets": dict(sorted(Counter(row["source_dataset"] for row in records).items())),
        "derived_outputs": sum(row.get("derived_from_output") is not None for row in records),
    }
    if any("parse_layer" in row for row in records):
        summary["parse_layers"] = dict(
            sorted(Counter(str(row.get("parse_layer")) for row in records).items())
        )
        summary["nonempty_conditioned_mt_cot"] = sum(
            bool(row.get("conditioned_mt_cot")) for row in records
        )
        # The pipeline emits an audit object for every SAMTok mode. Online CoT
        # and explicit MT correctly contain zero mask spans in the *user*
        # message, so only positive-span records are UMT tokenizer audits.
        audits = [
            row["user_mask_audit"]
            for row in records
            if (row.get("user_mask_audit") or {}).get("user_mask_span_count", 0) > 0
        ]
        if audits:
            summary["umt_tokenizer_audits"] = {
                "count": len(audits),
                "passed": sum(
                    audit.get("user_mask_spans_atomic") is True
                    and audit.get("user_mask_spans_in_template") is True
                    for audit in audits
                ),
            }
    return summary


def setting_dicts(settings: Iterable[SettingSpec]) -> list[dict]:
    return [asdict(setting) for setting in settings]


def distributed_context(device: str):
    """Initialize a lightweight Gloo control group and bind each worker GPU."""

    import torch

    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    rank = int(os.environ.get("RANK", "0"))
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    if world_size > 1:
        if not torch.cuda.is_available() or local_rank >= torch.cuda.device_count():
            raise RuntimeError("Invalid CUDA/distributed worker configuration")
        torch.cuda.set_device(local_rank)
        torch.distributed.init_process_group(backend="gloo")
        device = f"cuda:{local_rank}"
    return world_size, rank, local_rank, device


def distributed_rank0_call(world_size: int, rank: int, callback: Callable):
    import torch

    if world_size == 1:
        return callback()
    payload = [None]
    if rank == 0:
        try:
            payload[0] = {"ok": True, "value": callback()}
        except Exception as error:  # Propagate rank-0 preflight failures to every worker.
            payload[0] = {"ok": False, "error": f"{type(error).__name__}: {error}"}
    torch.distributed.broadcast_object_list(payload, src=0)
    if not payload[0]["ok"]:
        raise RuntimeError(payload[0]["error"])
    return payload[0]["value"]
