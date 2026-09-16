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
    "referential_finegrained_edit_benchmark_656_two_image_locator"
)
DEFAULT_BASELINE_PREPARED_MANIFEST = (
    DEFAULT_EXPERIMENT_ROOT / "prepared/benchmark_baseline_eval_inputs.jsonl"
)
DEFAULT_SAMTOK_REPO = Path("/opt/tiger/tanyue/samtok_edit")
DEFAULT_QWEN_2511 = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/"
    "Qwen-Image-Edit-2511"
)
DEFAULT_FLUX2 = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/"
    "FLUX.2-klein-4B"
)
FLUX2_MODEL_ID = "black-forest-labs/FLUX.2-klein-4B"
FLUX2_REVISION = "e7b7dc27f91deacad38e78976d1f2b499d76a294"
EXPECTED_CASES = 656
BASELINE_VISUAL_PROTOCOL = "baseline_two_image_locator_inputs_v2"

REGION_COLORS = ((235, 50, 45), (45, 180, 70), (45, 105, 230))
REGION_COLOR_NAMES = ("red", "green", "blue")
PLACEHOLDER_RE = re.compile(r"\{region_(\d+)\}")


@dataclass(frozen=True)
class SettingSpec:
    # The final three always remain null/false for the four baseline settings.
    # They preserve resume compatibility with the active frozen run config.
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
)


def settings_for_model(model: str) -> list[SettingSpec]:
    if model in {"qwen", "flux2"}:
        return [
            SettingSpec(model, "text_only", "source", "with_location_reference"),
            SettingSpec(model, "mask_annotation", "mask_annotation", "region_only"),
            SettingSpec(model, "box_annotation", "box_annotation", "region_only"),
            SettingSpec(model, "point_annotation", "point_annotation", "region_only"),
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
    return [by_key[key] for key in requested]


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
    if len(rows) != EXPECTED_CASES:
        raise ValueError(f"Expected {EXPECTED_CASES} benchmark rows, found {len(rows)}")
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


def load_prepared_manifest(
    path: Path,
    experiment_root: Path,
) -> tuple[list[dict], dict]:
    rows = read_jsonl(path)
    if len(rows) != EXPECTED_CASES:
        raise ValueError(f"Expected {EXPECTED_CASES} prepared rows, found {len(rows)}")
    asset_paths: set[Path] = set()
    for index, row in enumerate(rows):
        if row.get("eval_index") != index:
            raise ValueError(f"prepared row {index}: non-contiguous eval_index")
        prepared = row.get("prepared", {})
        for field in ("mask_annotation", "box_annotation", "point_annotation"):
            asset_paths.add(resolve_path(prepared[field], experiment_root))
        if prepared.get("baseline_visual_protocol") != BASELINE_VISUAL_PROTOCOL:
            raise ValueError(f"prepared row {index}: wrong baseline visual protocol")
        baseline_inputs = prepared.get("baseline_inputs", {})
        expected_keys = set(BASE_SETTING_KEYS)
        if set(baseline_inputs) != expected_keys:
            raise ValueError(f"prepared row {index}: baseline input keys mismatch")
        for key, item in baseline_inputs.items():
            if set(item) != {"images", "image_roles", "prompt"} or not item["prompt"].strip():
                raise ValueError(f"prepared row {index}: invalid frozen baseline input {key}")
            expected_roles = (
                ["clean_source_to_edit"]
                if key == "text_only"
                else ["clean_source_to_edit", f"{key.removesuffix('_annotation')}_locator_only"]
            )
            if item["image_roles"] != expected_roles or len(item["images"]) != len(expected_roles):
                raise ValueError(f"prepared row {index}: invalid image roles for {key}")
            for image_path in item["images"]:
                asset_paths.add(Path(image_path))
    with ThreadPoolExecutor(max_workers=32) as pool:
        list(pool.map(verify_image, sorted(asset_paths)))
    report = {
        "prepared_manifest": str(path.resolve()),
        "prepared_manifest_sha256": sha256_file(path),
        "rows": len(rows),
        "prepared_assets_verified": len(asset_paths),
        "profile": "visual_baselines_only",
        "baseline_visual_protocol": BASELINE_VISUAL_PROTOCOL,
    }
    return rows, report


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
    # Keep the point visually simple: one moderately sized colored dot with a
    # thin white outline. It remains legible after resizing without dominating
    # the target object. The annotated xy is always the dot center.
    point_radius = max(10, round(short_side * 0.018))
    point_outline_width = max(3, round(short_side * 0.005))
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
                fill=(*color, 255),
                outline=(255, 255, 255, 255),
                width=point_outline_width * scale,
            )
            label_xy = (
                (x + point_radius + 3) * scale,
                max(0, (y - point_radius - 18) * scale),
            )
        if len(regions) > 1:
            _label(draw, label_xy, f"R{index + 1}", color, scale)
    overlay = overlay.resize(source.size, Image.Resampling.LANCZOS)
    return Image.alpha_composite(base, overlay).convert("RGB")


def two_image_locator_prompt(
    region_only: str,
    region_count: int,
    modality: str = "mask",
) -> str:
    """Bind an edit to a second locator image with a concise direct prompt."""

    if modality not in {"mask", "box", "point"}:
        raise ValueError(modality)
    prompt = region_only
    if region_count == 1:
        reference = {
            "mask": "the region marked by the red mask in Image 2",
            "box": "the region inside the red box in Image 2",
            "point": (
                "the object or location at the center of the red point in Image 2"
            ),
        }[modality]
        prompt = prompt.replace("{region_1}", reference)
    else:
        for index in range(region_count):
            color = REGION_COLOR_NAMES[index]
            if modality == "point":
                reference = (
                    f"the object or location at the center of R{index + 1} "
                    f"({color} point) in Image 2"
                )
            else:
                noun = "mask" if modality == "mask" else "box"
                reference = f"R{index + 1} ({color} {noun}) in Image 2"
            prompt = prompt.replace(f"{{region_{index + 1}}}", reference)
    if PLACEHOLDER_RE.search(prompt):
        raise ValueError(f"Unresolved region placeholder: {prompt}")
    return (
        f"Edit Image 1. {prompt} Keep everything else unchanged. "
        "Return only the edited Image 1 without any markers from Image 2."
    )


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
    return {
        "count": len(records),
        "elapsed_seconds_total": sum(float(row.get("elapsed_seconds", 0.0)) for row in records),
        "edit_types": dict(sorted(Counter(row["edit_type"] for row in records).items())),
        "source_datasets": dict(sorted(Counter(row["source_dataset"] for row in records).items())),
        "derived_outputs": sum(row.get("derived_from_output") is not None for row in records),
    }


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
