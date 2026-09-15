#!/usr/bin/env python3
"""Materialize selected CompBench, HumanEdit, and MIRAGE cases into one schema.

The source datasets remain immutable. This builder extracts portable PNG assets,
preserves the released masks, derives deterministic box/point interactions, and
writes the compact benchmark manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
import pyarrow.parquet as pq
from PIL import Image, ImageOps


REPO_ROOT = Path(__file__).resolve().parent
DATASET_ROOT = Path("/mnt/bn/strategy-mllm-train/user/tanyue/datasets")
EXPECTED_CASES = 656
DEFAULT_SELECTION = REPO_ROOT / "selection" / "selected_cases.jsonl"
DEFAULT_MIRAGE_SELECTION = REPO_ROOT / "selection" / "mirage_selected_regions.jsonl"
DEFAULT_OUTPUT = DATASET_ROOT / "samtok_edit_benchmark"
DEFAULT_REPO_MANIFEST_DIR = REPO_ROOT / "benchmark"
DEFAULT_MODEL_CACHE = DATASET_ROOT / "model_cache"

SAM2_MODEL_ID = "facebook/sam2.1-hiera-small"
SAM2_REVISION = "e07df6aa19f5c6545121551bf89957b7663ee715"
GROUNDING_MODEL_ID = "IDEA-Research/grounding-dino-tiny"
GROUNDING_REVISION = "a2bb814dd30d776dcf7e30523b00659f4f141c71"

COMP_TOUCHING_INSTANCE_QUERIES = {
    "cb_train-00006-of-00007_0351": ["grey bird", "yellow bird"],
}

DATASET_REVISIONS = {
    "compbench": {
        "repo": "BohanJia/CompBench",
        "revision": "a4c5a4d1854056d24aad43a494772dc90588d426",
    },
    "humanedit": {
        "repo": "BryanW/HumanEdit",
        "revision": "dbc60b9ba3c17adf59e1effd8a9d92bdf2f14041",
    },
    "mirage": {
        "repo": "ziqiangoodgood/MIRAGE",
        "revision": "11eff1e3f396e189e61bd1f0ca596286d8a0b183",
    },
}

TOP_LEVEL_FIELDS = {
    "id",
    "source_dataset",
    "edit_type",
    "source_image",
    "instruction",
    "regions",
    "evaluation_mask",
    "target",
    "difficulty",
}


# These cases have terse, ungrammatical, or non-imperative source instructions.
# Explicit model-neutral rewrites retain the requested content while binding the
# placement exclusively through {region_1}.
HUMAN_ADD_REWRITES = {
    "he_000000001319": "Add a white cat in {region_1}.",
    "he_0-frDDoQqUw": "Add a hat in {region_1}.",
    "he_000000000307": "Add a black dog with a white neck in {region_1}.",
    "he_000000093106": "Add a top hat in {region_1}.",
    "he_0CgpDVNOKgs": "Add a white hat in {region_1}.",
    "he_0E_vhMVqL9g": "Add a hat in {region_1}.",
    "he_0G9rZGQqGig": "Add a straw hat in {region_1}.",
    "he_0eKR4M2uuL8": "Add a pair of sunglasses in {region_1}.",
    "he_0fOAmzgZ5cA": "Add a water bottle in {region_1}.",
    "he_0jRQ-_fM0gM": "Add a white strawberry in {region_1}.",
    "he_0qEmA2h57Pk": "Add a bright moon in {region_1}.",
    "he_0qqWALcBFnY(1)": "Add a puppy in {region_1}.",
    "he_1kdIG_258bU": "Add a red boat with an orange-red bow light in {region_1}.",
    "he_2OX0bKvL1-I": "Add a spoon in {region_1}.",
    "he_2mSzfaseWvg": "Add a butterfly in {region_1}.",
    "he_3c1Jv1EXYtc": "Add a small hat in {region_1}.",
    "he_4Cjn0FDEud8": "Add a pink hat in {region_1}.",
    "he_4cNByrzzNik": "Add a brown hat in {region_1}.",
    "he_5Hwt59WvpqM": "Add an insect in {region_1}.",
    "he_5Ufu-tY-Txk": "Add brown clothing in {region_1}.",
    "he_8VPSh4Wj61Q": "Add a bee in {region_1}.",
    "he_8n-3h1WkaQk": "Add snow in {region_1}.",
    "he_8v2Dz6vfN80": "Add a butterfly in {region_1}.",
    "he_973wAyYLeL0": "Add a bee in {region_1}.",
    "he_A_HTot3y5XA": "Add bees in {region_1}.",
    "he_CQwFUfliJyU": "Add a striped hat in {region_1}.",
    "he_CnSIcPtMG7U": "Add a straw hat with a black ribbon in {region_1}.",
    "he_KJE--xk4AWE": "Add a white hat in {region_1}.",
    "he_NfWZ6RB7KAY": "Add a pink hat in {region_1}.",
    "he_OuYESbJjiW0": "Make {region_1} look like unpainted natural wood.",
    "he_Vw07IRhemag(1)": "Add a decorative hat in {region_1}.",
    "he__-HoZoogPgI": "Add glasses in {region_1}.",
    "he__3LvzSuueSM": "Add a milk bottle in {region_1}.",
    "he__Jsde7RXd3o": "Add a fly in {region_1}.",
    "he__oHRmhtvpWc": "Add dazzling lighting in {region_1}.",
    "he__vln5e2nOK0": "Add clothing in {region_1}.",
    "he_axoIDVk0ThE": "Add a hat in {region_1}.",
    "he_bgoE05DFF9U": "Add a hat in {region_1}.",
    "he_nDExp37E9bs": "Add a white hat with a black ribbon in {region_1}.",
    "he_oUoRl1xBRaM": "Add a walking person in {region_1}.",
    "he_oV4bR3YoR_s": "Add a blue kayak in {region_1}.",
    "he_ovlpqD8fb4M(1)": "Add a rainbow in {region_1}.",
    "he_ow87HfF-uG8": "Add a bee in {region_1}.",
}

HUMAN_REPLACE_REWRITES = {
    "he_4k8xEFW4_3Q": "Replace {region_1} with a red raspberry matching the other fruits.",
    "he_0l_PZ1mO_ZA": "Change {region_1} to red clothing.",
    "he_30AOxN5emxs": "Replace {region_1} with blue pants.",
    "he_3d853e9ZjPM": "Replace {region_1} with a black hat with a white chin strap.",
    "he_50uhRqRVJM8": "Replace {region_1} with a red halter dress with a pink dress behind it.",
    "he_5r7YLkOwwQg": "Replace {region_1} with blonde hair.",
    "he_6hkjCMStvQ0": "Replace {region_1} with a black cup.",
    "he_9vHPCKymSh0": "Replace {region_1} with a white skirt.",
    "he_ouDjrbw-fs0": "Replace {region_1} with red lipstick.",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--mirage-selection", type=Path, default=DEFAULT_MIRAGE_SELECTION)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--repo-manifest-dir", type=Path, default=DEFAULT_REPO_MANIFEST_DIR)
    parser.add_argument("--model-cache", type=Path, default=DEFAULT_MODEL_CACHE)
    parser.add_argument("--device", default="cuda:0")
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(value, encoding="utf-8")
    temp.replace(path)


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    atomic_text(path, "".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in records))


def decode(cell: dict[str, Any], mode: str) -> Image.Image:
    payload = cell.get("bytes") if isinstance(cell, dict) else None
    if not isinstance(payload, bytes):
        raise ValueError("embedded image cell has no bytes")
    with Image.open(io.BytesIO(payload)) as image:
        return image.convert(mode).copy()


def save_png(image: Image.Image, path: Path, mode: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert(mode).save(path, format="PNG", compress_level=6, optimize=False)


def dataset_slug(name: str) -> str:
    return {"CompBench": "compbench", "HumanEdit": "humanedit", "MIRAGE": "mirage"}[name]


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    suffix = hashlib.sha256(value.encode()).hexdigest()[:8]
    return f"{cleaned}-{suffix}"


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def binary_mask(image: Image.Image, size: tuple[int, int] | None = None) -> np.ndarray:
    if size is not None and image.size != size:
        image = image.resize(size, Image.Resampling.NEAREST)
    return np.asarray(image.convert("L")) >= 128


def mask_bbox(mask: np.ndarray) -> list[int]:
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise ValueError("empty mask")
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def padded_bbox(mask: np.ndarray, ratio: float = 0.02) -> list[int]:
    height, width = mask.shape
    x1, y1, x2, y2 = mask_bbox(mask)
    padding = max(1, round(min(height, width) * ratio))
    return [max(0, x1 - padding), max(0, y1 - padding), min(width, x2 + padding), min(height, y2 + padding)]


def innermost_point(mask: np.ndarray) -> list[int]:
    # OpenCV does not treat pixels outside the array as background. Without an
    # explicit zero border, a mask touching the canvas can incorrectly select a
    # point on the image edge, where a visual click is clipped. Padding makes
    # both the mask boundary and the image boundary participate in the distance
    # transform, then maps the result back to the original coordinates.
    padded = np.pad(mask.astype(np.uint8), 1, mode="constant", constant_values=0)
    distance = cv2.distanceTransform(padded, cv2.DIST_L2, 5)[1:-1, 1:-1]
    y, x = np.unravel_index(int(np.argmax(distance)), distance.shape)
    if not mask[y, x]:
        y, x = np.argwhere(mask)[0]
    return [int(x), int(y)]


def dilate_two_percent(mask: np.ndarray) -> np.ndarray:
    radius = max(1, round(min(mask.shape) * 0.02))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    return cv2.dilate(mask.astype(np.uint8), kernel, iterations=1).astype(bool)


def significant_components(mask: np.ndarray) -> list[np.ndarray]:
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    minimum = max(16, int(math.ceil(mask.size * 0.00005)))
    components = []
    for label in range(1, count):
        if int(stats[label, cv2.CC_STAT_AREA]) >= minimum:
            component = labels == label
            cx, cy = centroids[label]
            components.append((component, float(cx), float(cy), int(stats[label, cv2.CC_STAT_AREA])))
    components.sort(key=lambda x: (round(x[2] / max(1, mask.shape[0] * 0.15)), x[1], x[2]))
    return [x[0] for x in components]


def split_connected_region(mask: np.ndarray, pieces: int) -> list[np.ndarray]:
    """Split a touching multi-object union at its lowest-density spatial cut."""
    if pieces != 2:
        raise ValueError(f"automatic touching-instance split only supports two pieces, got {pieces}")
    ys, xs = np.nonzero(mask)
    best: tuple[float, np.ndarray, np.ndarray] | None = None
    for coordinate in (xs, ys):
        low, high = int(coordinate.min()), int(coordinate.max())
        span = high - low + 1
        if span < 4:
            continue
        histogram = np.bincount(coordinate - low, minlength=span)
        cumulative = np.cumsum(histogram)
        total = int(cumulative[-1])
        for offset in range(max(1, int(span * 0.15)), min(span - 1, int(span * 0.85))):
            left_area = int(cumulative[offset - 1])
            right_area = total - left_area
            if min(left_area, right_area) < total * 0.12:
                continue
            crossing = float(histogram[offset]) / max(1.0, float(histogram.max()))
            imbalance = abs(left_area - right_area) / total
            score = crossing + 0.18 * imbalance
            first = coordinate < low + offset
            a = np.zeros_like(mask)
            b = np.zeros_like(mask)
            a[ys[first], xs[first]] = True
            b[ys[~first], xs[~first]] = True
            if best is None or score < best[0]:
                best = (score, a, b)
    if best is None:
        raise ValueError("unable to split connected multi-object mask")
    return sort_regions([best[1], best[2]])


def sort_regions(regions: list[np.ndarray]) -> list[np.ndarray]:
    def key(mask: np.ndarray) -> tuple[float, float]:
        ys, xs = np.nonzero(mask)
        return float(xs.mean()), float(ys.mean())

    return sorted(regions, key=key)


def comp_regions(mask: np.ndarray, edit_type: str) -> list[np.ndarray]:
    if not edit_type.startswith("multi_object"):
        return [mask]
    components = significant_components(mask)
    if len(components) == 2:
        regions = sort_regions(components)
        residual = mask & ~np.logical_or.reduce(regions)
        if residual.any():
            distances = np.stack(
                [cv2.distanceTransform((~region).astype(np.uint8), cv2.DIST_L2, 5) for region in regions]
            )
            ys, xs = np.nonzero(residual)
            assignments = np.argmin(distances[:, ys, xs], axis=0)
            for index in range(len(regions)):
                chosen = assignments == index
                regions[index][ys[chosen], xs[chosen]] = True
        return regions
    if len(components) == 1:
        # A connected released union has no trustworthy instance boundary.
        # Keep it as one interaction region instead of inventing a split.
        return [mask]
    raise ValueError(f"expected one or two significant components for {edit_type}, got {len(components)}")


def human_source(source: Image.Image, size: tuple[int, int], transform: str) -> Image.Image:
    source = source.convert("RGB")
    if transform == "cover":
        return ImageOps.fit(source, size, method=Image.Resampling.BICUBIC, centering=(0.5, 0.5))
    if transform == "contain":
        ballot = ImageOps.contain(source, size, method=Image.Resampling.BICUBIC)
        canvas = Image.new("RGB", size, (0, 0, 0))
        canvas.paste(ballot, ((size[0] - ballot.width) // 2, (size[1] - ballot.height) // 2))
        return canvas
    return source.resize(size, Image.Resampling.BICUBIC)


def normalize_edit_type(record: dict[str, Any]) -> str:
    value = record["edit_type"]
    if value == "multi_object_add":
        return "add"
    if value == "multi_object_remove":
        return "remove"
    if value not in {"add", "remove", "replace", "mixed", "counting"}:
        raise ValueError(f"unsupported edit type: {record['candidate_id']} {value}")
    return value


def region_references(count: int) -> list[str]:
    return [f"{{region_{index}}}" for index in range(1, count + 1)]


def english_join(values: list[str]) -> str:
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return ", ".join(values[:-1]) + f", and {values[-1]}"


def replacement_target(instruction: str) -> str | None:
    patterns = [
        r"\breplace\b.+?\bwith\b\s+(.+?)\s*[.!]*$",
        r"\bswap\b.+?\bfor\b\s+(.+?)\s*[.!]*$",
        r"\b(?:change|turn|transform|convert)\b.+?\b(?:into|to)\b\s+(.+?)\s*[.!]*$",
        r"\breplaced\s+with\s+(.+?)\s*[.!]*$",
        r"\bturns\s+into\s+(.+?)\s*[.!]*$",
        r"\bswitch\s+to\s+(.+?)\s*[.!]*$",
    ]
    for pattern in patterns:
        match = re.search(pattern, instruction, flags=re.IGNORECASE)
        if match:
            return clean_text(match.group(1))
    return None


def comp_add_targets(record: dict[str, Any]) -> list[str]:
    return [text for value in record["local_caption"].split("|") if (text := clean_text(value))]


def region_only_instruction(record: dict[str, Any], region_count: int) -> str | None:
    dataset = record["source_dataset"]
    if dataset == "MIRAGE":
        instruction = clean_text(record.get("region_only_instruction"))
        if not instruction:
            raise ValueError(f"missing MIRAGE region-only instruction: {record['candidate_id']}")
        return instruction
    edit_type = normalize_edit_type(record)
    references = region_references(region_count)
    if edit_type == "counting" or record.get("requires_ref_instruction"):
        return None
    if edit_type == "remove":
        return f"Remove {english_join(references)}."
    if edit_type == "add":
        if dataset == "HumanEdit":
            if record["candidate_id"] not in HUMAN_ADD_REWRITES:
                raise ValueError(f"missing HumanEdit add rewrite: {record['candidate_id']}")
            return HUMAN_ADD_REWRITES[record["candidate_id"]]
        if record["edit_type"] == "add":
            # CompBench crop captions sometimes include nearby anchor instances
            # (for example "two fish") rather than only the new object. Preserve
            # the authoritative source instruction and make the visual region an
            # explicit placement constraint instead of changing edit semantics.
            original = clean_text(record["instruction_original"])
            if not original:
                raise ValueError(f"missing add instruction: {record['candidate_id']}")
            original = original[0].upper() + original[1:]
            original = original.rstrip(".")
            return f"Use {references[0]} as the exact placement region. {original}."
        captions = comp_add_targets(record)
        if not captions:
            raise ValueError(f"missing add target text: {record['candidate_id']}")
        if len(captions) == 1 and region_count > 1:
            captions *= region_count
        if len(captions) != region_count:
            raise ValueError(
                f"add caption/region mismatch: {record['candidate_id']} {len(captions)} != {region_count}"
            )
        edits = [f"{caption} in {reference}" for caption, reference in zip(captions, references)]
        return f"Add {english_join(edits)}."
    if edit_type == "replace":
        if record["candidate_id"] in HUMAN_REPLACE_REWRITES:
            return HUMAN_REPLACE_REWRITES[record["candidate_id"]]
        target = replacement_target(record["instruction_original"])
        if target:
            return f"Replace {references[0]} with {target}."
        local = clean_text(record["local_caption"])
        return f"Edit {references[0]} to match this expected result: {local}."
    raise AssertionError(edit_type)


def bbox_iou(a: list[float], b: list[int]) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return intersection / max(1e-9, area_a + area_b - intersection)


class GroundedSam2Segmenter:
    def __init__(self, device: str, cache_dir: Path):
        import torch
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor, Sam2Model, Sam2Processor

        self.torch = torch
        self.device = device
        self.grounding_processor = AutoProcessor.from_pretrained(
            GROUNDING_MODEL_ID, revision=GROUNDING_REVISION, cache_dir=cache_dir
        )
        self.grounding_model = AutoModelForZeroShotObjectDetection.from_pretrained(
            GROUNDING_MODEL_ID,
            revision=GROUNDING_REVISION,
            cache_dir=cache_dir,
            dtype=torch.float32,
        ).to(device).eval()
        self.sam_processor = Sam2Processor.from_pretrained(
            SAM2_MODEL_ID, revision=SAM2_REVISION, cache_dir=cache_dir
        )
        self.sam_model = Sam2Model.from_pretrained(
            SAM2_MODEL_ID,
            revision=SAM2_REVISION,
            cache_dir=cache_dir,
            dtype=torch.float32,
        ).to(device).eval()

    def _grounding_candidates(
        self, image: Image.Image, text: str, union_mask: np.ndarray
    ) -> list[tuple[float, float, list[float]]]:
        prompt = text.strip().rstrip(".") + "."
        inputs = self.grounding_processor(images=image, text=prompt, return_tensors="pt").to(self.device)
        with self.torch.inference_mode():
            outputs = self.grounding_model(**inputs)
        result = self.grounding_processor.post_process_grounded_object_detection(
            outputs,
            inputs.input_ids,
            threshold=0.05,
            text_threshold=0.05,
            target_sizes=[image.size[::-1]],
        )[0]
        union_box = mask_bbox(union_mask)
        candidates = []
        for score_tensor, box_tensor in zip(result["scores"], result["boxes"]):
            score = float(score_tensor)
            box = [float(x) for x in box_tensor.tolist()]
            x1, y1 = max(0, int(math.floor(box[0]))), max(0, int(math.floor(box[1])))
            x2 = min(union_mask.shape[1], int(math.ceil(box[2])))
            y2 = min(union_mask.shape[0], int(math.ceil(box[3])))
            coverage = float(union_mask[y1:y2, x1:x2].mean()) if x2 > x1 and y2 > y1 else 0.0
            overlap = bbox_iou(box, union_box)
            if coverage > 0.02 or overlap > 0.02:
                candidates.append((score + 0.35 * coverage + 0.10 * overlap, score, box))
        return sorted(candidates, reverse=True, key=lambda x: x[0])

    def segment_multiple(
        self, image: Image.Image, texts: list[str], union_mask: np.ndarray
    ) -> tuple[list[np.ndarray], dict[str, Any]]:
        """Recover touching instances while preserving the released union exactly."""
        count = len(texts)
        if count != 2:
            raise ValueError(f"touching-instance grounding requires two queries, got {count}")
        normalized = [x.strip().lower() for x in texts]
        boxes: list[list[float]] = []
        detection_scores: list[float] = []
        same_query = len(set(normalized)) == 1
        if same_query:
            candidates = self._grounding_candidates(image, texts[0], union_mask)
            for _, score, box in candidates:
                if all(bbox_iou(box, existing) < 0.65 for existing in boxes):
                    boxes.append(box)
                    detection_scores.append(score)
                if len(boxes) == count:
                    break
        else:
            per_query = [self._grounding_candidates(image, text, union_mask)[:10] for text in texts]
            combinations = []
            for first in per_query[0]:
                for second in per_query[1]:
                    overlap = bbox_iou(first[2], second[2])
                    if overlap < 0.75:
                        combinations.append((first[0] + second[0] - 0.15 * overlap, first, second))
            if combinations:
                _, first, second = max(combinations, key=lambda x: x[0])
                boxes = [first[2], second[2]]
                detection_scores = [first[1], second[1]]
        if len(boxes) != count:
            fallback = split_connected_region(union_mask, count)
            return fallback, {
                "id": None,
                "queries": texts,
                "method": "spatial_split_fallback",
                "detections": len(boxes),
            }

        sam_inputs = self.sam_processor(images=image, input_boxes=[boxes], return_tensors="pt").to(self.device)
        with self.torch.inference_mode():
            sam_outputs = self.sam_model(**sam_inputs, multimask_output=True)
        predictions = self.sam_processor.post_process_masks(
            sam_outputs.pred_masks.cpu(), sam_inputs["original_sizes"].cpu()
        )[0].numpy().astype(bool)
        sam_scores = sam_outputs.iou_scores[0].detach().cpu().numpy()
        instance_masks = []
        selected_indices = []
        for object_masks, object_scores in zip(predictions, sam_scores):
            index = int(np.argmax(object_scores))
            selected_indices.append(index)
            instance_masks.append(object_masks[index] & union_mask)

        # SAM instances can overlap and may omit thin antialiased boundary pixels.
        # Preserve unambiguous predictions, then assign every remaining union pixel
        # to the nearest detected instance center. This yields a disjoint partition
        # whose union is exactly the released annotation.
        stack = np.stack(instance_masks, axis=0)
        membership = stack.sum(axis=0)
        assigned = np.full(union_mask.shape, -1, dtype=np.int16)
        for index in range(count):
            assigned[(membership == 1) & stack[index]] = index
        ambiguous = union_mask & (assigned < 0)
        ys, xs = np.nonzero(ambiguous)
        if len(xs):
            distances = []
            for box in boxes:
                cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                sx, sy = max(1.0, box[2] - box[0]), max(1.0, box[3] - box[1])
                distances.append(((xs - cx) / sx) ** 2 + ((ys - cy) / sy) ** 2)
            choices = np.argmin(np.stack(distances, axis=0), axis=0)
            assigned[ys, xs] = choices
        regions = [(assigned == index) & union_mask for index in range(count)]
        if any(int(region.sum()) < 16 for region in regions):
            regions = split_connected_region(union_mask, count)
            method = "spatial_split_fallback_after_empty_partition"
        else:
            method = "grounding_dino_sam2_partition"
            if same_query:
                regions = sort_regions(regions)
        return regions, {
            "id": None,
            "queries": texts,
            "method": method,
            "detection_scores": [round(float(x), 6) for x in detection_scores],
            "boxes": [[round(float(x), 4) for x in box] for box in boxes],
            "sam2_selected_indices": selected_indices,
        }


def load_parquet_payloads(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record["source_dataset"] == "MIRAGE":
            continue
        groups[(record["source_dataset"], record["source_shard"])].append(record)
    for (dataset, shard_name), group in sorted(groups.items()):
        if dataset == "CompBench":
            columns = ["input_image", "edited_image", "mask"]
        else:
            columns = ["INPUT_IMG", "MASK_IMG", "OUTPUT_IMG"]
        table = pq.read_table(shard_name, columns=columns)
        for record in group:
            index = int(record["source_row"])
            row = {name: table[name][index].as_py() for name in columns}
            if dataset == "CompBench":
                source = decode(row["input_image"], "RGB")
                target = decode(row["edited_image"], "RGB")
                mask_image = decode(row["mask"], "L")
                if source.size != mask_image.size:
                    source = source.resize(mask_image.size, Image.Resampling.BICUBIC)
                if target.size != mask_image.size:
                    target = target.resize(mask_image.size, Image.Resampling.BICUBIC)
                mask = binary_mask(mask_image)
            else:
                canvas = decode(row["MASK_IMG"], "RGBA")
                alpha = np.asarray(canvas.getchannel("A"))
                mask = alpha < 128
                source = human_source(decode(row["INPUT_IMG"], "RGB"), canvas.size, record["alignment_transform"])
                target = decode(row["OUTPUT_IMG"], "RGB").resize(canvas.size, Image.Resampling.BICUBIC)
            payloads[record["candidate_id"]] = {"source": source, "target": target, "mask": mask}
        print(f"loaded {dataset} {Path(shard_name).name}: {len(group)} selected rows", flush=True)
    return payloads


def mirage_polygon_mask(value: list[Any], size: tuple[int, int]) -> np.ndarray:
    """Rasterize a released MIRAGE polygon exactly as its official metrics do."""
    from PIL import ImageDraw

    if len(value) == 1 and isinstance(value[0], list):
        value = value[0]
    if len(value) < 6 or len(value) % 2:
        raise ValueError("invalid MIRAGE polygon")
    points = [(float(value[index]), float(value[index + 1])) for index in range(0, len(value), 2)]
    canvas = Image.new("L", size, 0)
    ImageDraw.Draw(canvas).polygon(points, outline=255, fill=255)
    return np.asarray(canvas) == 255


def load_mirage_payloads(
    records: list[dict[str, Any]], dataset_root: Path
) -> dict[str, dict[str, Any]]:
    benchmark_root = dataset_root / "MIRAGE" / "benchmark"
    annotations = read_jsonl(benchmark_root / "annotations.jsonl")
    payloads: dict[str, dict[str, Any]] = {}
    for record in records:
        if record["source_dataset"] != "MIRAGE":
            continue
        source_row = int(record["source_row"])
        annotation = annotations[source_row]
        if annotation["image"] != record["source_record_id"]:
            raise ValueError(f"MIRAGE source identity mismatch: {record['candidate_id']}")
        with Image.open(benchmark_root / annotation["image"]) as handle:
            source = handle.convert("RGB").copy()
        indices = record["selected_region_indices"]
        masks = [mirage_polygon_mask(annotation["mask"][index - 1], source.size) for index in indices]
        if any(not mask.any() for mask in masks):
            raise ValueError(f"empty MIRAGE mask: {record['candidate_id']}")
        payloads[record["candidate_id"]] = {
            "source": source,
            "target": None,
            "masks": masks,
        }
    print(f"loaded MIRAGE: {len(payloads)} selected rows", flush=True)
    return payloads


def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def make_record(
    selected: dict[str, Any],
    source: Image.Image,
    target: Image.Image | None,
    masks: list[np.ndarray],
    evaluation_mask: np.ndarray,
    root: Path,
) -> dict[str, Any]:
    dataset = dataset_slug(selected["source_dataset"])
    case_name = safe_name(selected["candidate_id"])
    source_name = safe_name(selected["source_group_id"])
    source_path = root / "images" / "source" / dataset / f"{source_name}.png"
    save_png(source, source_path, "RGB")
    reference_path: Path | None = None
    if target is not None:
        reference_path = root / "images" / "target" / dataset / f"{case_name}.png"
        save_png(target, reference_path, "RGB")
    regions = []
    for index, mask in enumerate(masks, start=1):
        mask_path = root / "regions" / "input" / dataset / f"{case_name}_r{index:02d}.png"
        save_png(Image.fromarray(mask.astype(np.uint8) * 255, mode="L"), mask_path, "L")
        box = padded_bbox(mask)
        regions.append(
            {
                "mask": relative(mask_path, root),
                "box": [int(x) for x in box],
                "point": innermost_point(mask),
            }
        )
    evaluation_path = root / "regions" / "evaluation" / dataset / f"{case_name}.png"
    save_png(Image.fromarray(evaluation_mask.astype(np.uint8) * 255, mode="L"), evaluation_path, "L")
    local_text = clean_text(selected.get("local_caption"))
    if selected["source_dataset"] == "CompBench" and selected["edit_type"] == "multi_object_add":
        local_text = "; ".join(comp_add_targets(selected))
    elif local_text:
        local_text = local_text.replace("|", "; ")
    if not local_text:
        raise ValueError(f"missing target local content: {selected['candidate_id']}")
    return {
        "id": selected["candidate_id"],
        "source_dataset": dataset,
        "edit_type": normalize_edit_type(selected),
        "source_image": relative(source_path, root),
        "instruction": {
            "with_location_reference": clean_text(selected["instruction_original"]),
            "region_only": region_only_instruction(selected, len(masks)),
        },
        "regions": regions,
        "evaluation_mask": relative(evaluation_path, root),
        "target": {
            "reference_image": relative(reference_path, root) if reference_path is not None else None,
            "expected_local_content": local_text,
            "expected_global_description": clean_text(selected.get("target_prompt")),
        },
        "difficulty": {
            "same_class_multi_instance": bool(selected.get("same_class_multi_instance_proxy", True)),
            "multi_object_scene": bool(selected.get("multi_object_scene", True)),
        },
    }


def validate_records(records: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    errors: list[str] = []
    ids = [x["id"] for x in records]
    if len(records) != EXPECTED_CASES:
        errors.append(f"record count is {len(records)}, expected {EXPECTED_CASES}")
    if len(set(ids)) != len(ids):
        errors.append("duplicate case ids")
    path_cache: dict[str, tuple[tuple[int, int], str]] = {}

    def open_asset(path_value: str, expected_mask: bool) -> tuple[tuple[int, int], Image.Image]:
        path = root / path_value
        if not path.is_file():
            raise ValueError(f"missing asset: {path_value}")
        image = Image.open(path)
        if expected_mask:
            values = set(np.unique(np.asarray(image.convert("L"))).tolist())
            if not values <= {0, 255} or 255 not in values:
                raise ValueError(f"invalid binary mask: {path_value} values={sorted(values)}")
        path_cache[path_value] = (image.size, image.mode)
        return image.size, image

    for record in records:
        case_id = record.get("id", "<missing>")
        try:
            if set(record) != TOP_LEVEL_FIELDS:
                raise ValueError(f"top-level fields differ: {sorted(set(record) ^ TOP_LEVEL_FIELDS)}")
            if set(record["instruction"]) != {"with_location_reference", "region_only"}:
                raise ValueError("instruction fields differ from the compact schema")
            if set(record["target"]) != {
                "reference_image",
                "expected_local_content",
                "expected_global_description",
            }:
                raise ValueError("target fields differ from the compact schema")
            if set(record["difficulty"]) != {"same_class_multi_instance", "multi_object_scene"}:
                raise ValueError("difficulty fields differ from the compact schema")
            if not all(type(value) is bool for value in record["difficulty"].values()):
                raise ValueError("difficulty values must be booleans")
            if record["source_dataset"] not in DATASET_REVISIONS:
                raise ValueError("invalid source_dataset")
            if record["edit_type"] not in {"add", "remove", "replace", "mixed", "counting"}:
                raise ValueError("invalid edit_type")
            source_size, source_image = open_asset(record["source_image"], False)
            source_image.close()
            evaluation_size, evaluation_image = open_asset(record["evaluation_mask"], True)
            evaluation_image.close()
            if evaluation_size != source_size:
                raise ValueError("evaluation mask size differs from source")
            reference = record["target"]["reference_image"]
            if reference is None and record["source_dataset"] != "mirage":
                raise ValueError("CompBench and HumanEdit records require a target reference image")
            if reference is not None and record["source_dataset"] == "mirage":
                raise ValueError("MIRAGE records must not invent a target reference image")
            if reference is not None:
                reference_size, reference_image = open_asset(reference, False)
                reference_image.close()
                if reference_size != source_size:
                    raise ValueError("target reference image size differs from source")
            if not record["target"]["expected_local_content"]:
                raise ValueError("empty target expected_local_content")
            regions = record["regions"]
            if not 1 <= len(regions) <= 3:
                raise ValueError(f"invalid region count: {len(regions)}")
            expected_tokens = {f"{{region_{i}}}" for i in range(1, len(regions) + 1)}
            region_instruction = record["instruction"]["region_only"]
            if record["edit_type"] == "counting":
                if region_instruction is not None:
                    raise ValueError("counting instruction.region_only must be null")
            elif region_instruction is None or expected_tokens != set(
                re.findall(r"\{region_\d+\}", region_instruction)
            ):
                raise ValueError("region_only instruction does not reference every region")
            for region in regions:
                if set(region) != {"mask", "box", "point"}:
                    raise ValueError("region fields differ from the compact schema")
                mask_size, mask_image = open_asset(region["mask"], True)
                mask = np.asarray(mask_image.convert("L")) == 255
                mask_image.close()
                if mask_size != source_size:
                    raise ValueError("input mask size differs from source")
                x1, y1, x2, y2 = region["box"]
                width, height = source_size
                if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                    raise ValueError(f"invalid box: {region['box']} for {source_size}")
                x, y = region["point"]
                if not (0 <= x < width and 0 <= y < height and mask[y, x]):
                    raise ValueError(f"point is outside input mask: {region['point']}")
        except Exception as exc:
            errors.append(f"{case_id}: {exc}")
    reference_count = sum(x["target"]["reference_image"] is not None for x in records)
    region_count = sum(len(x["regions"]) for x in records)
    report = {
        "status": "passed" if not errors else "failed",
        "records": len(records),
        "unique_ids": len(set(ids)),
        "unique_source_images": len({x["source_image"] for x in records}),
        "target_reference_images": reference_count,
        "input_region_masks": region_count,
        "multi_region_cases": sum(len(x["regions"]) > 1 for x in records),
        "counts_by_region_count": dict(sorted(Counter(len(x["regions"]) for x in records).items())),
        "evaluation_masks": len(records),
        "region_only_instructions": sum(x["instruction"]["region_only"] is not None for x in records),
        "counts_by_dataset": dict(sorted(Counter(x["source_dataset"] for x in records).items())),
        "counts_by_edit_type": dict(sorted(Counter(x["edit_type"] for x in records).items())),
        "errors": errors,
    }
    if errors:
        raise ValueError(json.dumps(report, indent=2, ensure_ascii=False))
    return report


def build_metadata(records: list[dict[str, Any]]) -> dict[str, Any]:
    present_edit_types = {x["edit_type"] for x in records}
    return {
        "benchmark_name": "SAMTok Fine-Grained Interactive Edit Benchmark",
        "split": "test",
        "num_cases": len(records),
        "manifest": "benchmark.jsonl",
        "source_datasets": DATASET_REVISIONS,
        "schema": {
            "one_record_per_edit_case": True,
            "top_level_fields": sorted(TOP_LEVEL_FIELDS),
            "edit_types": [
                edit_type
                for edit_type in ("add", "remove", "replace", "mixed", "counting")
                if edit_type in present_edit_types
            ],
            "box_format": "pixel_xyxy_half_open",
            "point_format": "pixel_xy",
            "mask_format": "single_channel_png_0_or_255_source_resolution",
            "region_numbering": "regions_array_order_is_1_based",
            "region_placeholder": "{region_N}",
            "null_region_only_instruction": (
                "use with_location_reference; currently counting only"
                if any(x["instruction"]["region_only"] is None for x in records)
                else "none"
            ),
            "null_target_reference_image": "MIRAGE only; the release has no edited target reference image",
            "target_semantics": "all target fields describe the expected post-edit result and are evaluator-only",
        },
        "region_construction": {
            "compbench_mask": "released mask preserved exactly; disconnected multi-object unions become two regions, and one connected two-object union is semantically partitioned into two reviewed regions without changing the union",
            "humanedit_mask": "original human brush from MASK_IMG alpha < 128",
            "mirage_mask": "selected released polygon rasterized with PIL ImageDraw, matching the official metrics",
            "box": "input mask bounding box padded by 2% of the shorter image side",
            "point": (
                "maximum L2 distance-transform point after adding a one-pixel "
                "background border, so image edges are treated as mask boundaries"
            ),
        },
        "evaluation_region": {
            "compbench": "union of input masks dilated by 2% of the shorter image side",
            "humanedit": "union of input masks dilated by 2% of the shorter image side",
            "mirage": "union of the selected one or two released masks dilated by 2% of the shorter image side",
        },
        "models_used_for_derived_instance_masks": {
            "uses": ["semantic partition of a connected CompBench multi-object union"],
            "note": "The two derived regions are disjoint and their union exactly equals the released mask; no released mask pixels are added or removed.",
            "grounding": {"repo": GROUNDING_MODEL_ID, "revision": GROUNDING_REVISION},
            "segmentation": {"repo": SAM2_MODEL_ID, "revision": SAM2_REVISION},
        },
        "derived_groups": {
            "small_target": "derive from input mask area ratio < 0.02",
            "multi_target": "derive from len(regions) > 1",
        },
        "counts_by_dataset": dict(sorted(Counter(x["source_dataset"] for x in records).items())),
        "counts_by_edit_type": dict(sorted(Counter(x["edit_type"] for x in records).items())),
        "counts_by_region_count": {
            str(count): value
            for count, value in sorted(Counter(len(x["regions"]) for x in records).items())
        },
    }


def copy_manifest_files(output: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("benchmark.jsonl", "benchmark_meta.json", "validation_report.json"):
        atomic_text(destination / name, (output / name).read_text(encoding="utf-8"))


def main() -> None:
    args = parse_args()
    cv2.setNumThreads(1)
    selected_base = read_jsonl(args.selection)
    selected_mirage = read_jsonl(args.mirage_selection)
    if len(selected_base) != 556:
        raise ValueError(f"expected 556 CompBench/HumanEdit cases, got {len(selected_base)}")
    if len(selected_mirage) != 100:
        raise ValueError(f"expected 100 MIRAGE cases, got {len(selected_mirage)}")
    selected = selected_base + selected_mirage
    if len(selected) != EXPECTED_CASES:
        raise ValueError(f"expected {EXPECTED_CASES} selected cases, got {len(selected)}")
    invalid_datasets = sorted(
        {x["source_dataset"] for x in selected} - {"CompBench", "HumanEdit", "MIRAGE"}
    )
    if invalid_datasets:
        raise ValueError(f"unsupported source datasets in selection: {invalid_datasets}")
    args.output.mkdir(parents=True, exist_ok=True)
    payloads = load_parquet_payloads(selected)
    payloads.update(load_mirage_payloads(selected, args.dataset_root))
    records: list[dict[str, Any]] = []
    segmenter: GroundedSam2Segmenter | None = None
    comp_instance_diagnostics = []

    for index, item in enumerate(selected):
        payload = payloads[item["candidate_id"]]
        source = payload["source"]
        target = payload["target"]
        if item["source_dataset"] == "CompBench":
            mask = payload["mask"]
            if item["candidate_id"] in COMP_TOUCHING_INSTANCE_QUERIES:
                if segmenter is None:
                    print("loading Grounding DINO and SAM2 for one connected-union partition", flush=True)
                    segmenter = GroundedSam2Segmenter(args.device, args.model_cache)
                queries = COMP_TOUCHING_INSTANCE_QUERIES[item["candidate_id"]]
                segmentation_image = target if item["edit_type"] == "multi_object_add" else source
                masks, diagnostic = segmenter.segment_multiple(segmentation_image, queries, mask)
                diagnostic["id"] = item["candidate_id"]
                comp_instance_diagnostics.append(diagnostic)
            else:
                masks = comp_regions(mask, item["edit_type"])
        elif item["source_dataset"] == "HumanEdit":
            mask = payload["mask"]
            masks = [mask]
        else:
            masks = payload["masks"]
        evaluation = dilate_two_percent(np.logical_or.reduce(masks))
        records.append(make_record(item, source, target, masks, evaluation, args.output))
        if (index + 1) % 50 == 0:
            print(f"materialized cases: {index + 1}", flush=True)

    records.sort(key=lambda x: x["id"])
    write_jsonl(args.output / "benchmark.jsonl", records)
    metadata = build_metadata(records)
    atomic_text(args.output / "benchmark_meta.json", json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    validation = validate_records(records, args.output)
    atomic_text(args.output / "validation_report.json", json.dumps(validation, indent=2, ensure_ascii=False) + "\n")
    build_report = {
        "selection_manifest": str(args.selection),
        "mirage_selection_manifest": str(args.mirage_selection),
        "output_root": str(args.output),
        "mask_policy": "released source-dataset masks/polygons are preserved",
        "multi_object_policy": "use released connected components; one connected two-object union is semantically partitioned while preserving the exact released union",
        "comp_connected_union_partition_diagnostics": comp_instance_diagnostics,
    }
    atomic_text(args.output / "build_report.json", json.dumps(build_report, indent=2, ensure_ascii=False) + "\n")
    copy_manifest_files(args.output, args.repo_manifest_dir)
    print(json.dumps(validation, indent=2, ensure_ascii=False), flush=True)
    print(f"benchmark root: {args.output}", flush=True)
    print(f"repo manifests: {args.repo_manifest_dir}", flush=True)


if __name__ == "__main__":
    main()
