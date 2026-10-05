"""Freeze clean-source and locator/native inputs without reference-answer leakage."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from samtok_benchmark.dataset import load_cases
from samtok_benchmark.io import asset_path, digest, sha256_file, write_jsonl

SETTINGS = ("text_only", "mask_annotation", "box_annotation", "point_annotation")
PROTOCOLS = ("visual_locator_v1", "native_regions_v1")
COLORS = ((235, 50, 45), (45, 180, 70))
COLOR_NAMES = ("red", "green")


def annotate(source: Image.Image, regions: list[dict], root: Path, mode: str) -> Image.Image:
    """Draw only original region masks, or their inherited boxes/points."""
    image = source.convert("RGB").copy()
    width = max(2, round(min(image.size) * 0.005))
    for i, region in enumerate(regions):
        color = COLORS[i]
        if mode == "mask_annotation":
            with Image.open(asset_path(root, region["mask"])) as raw:
                mask = raw.convert("L").point(lambda x: 255 if x else 0)
            if mask.size != image.size:
                raise ValueError("region mask geometry mismatch")
            fill = mask.point(lambda x: 55 if x else 0)
            image = Image.composite(Image.new("RGB", image.size, color), image, fill)
            edge = ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(2 * width + 1)), mask)
            image.paste(color, mask=edge)
        elif mode == "box_annotation":
            x1, y1, x2, y2 = region["box"]
            ImageDraw.Draw(image).rectangle((x1, y1, x2 - 1, y2 - 1), outline=color, width=width)
        elif mode == "point_annotation":
            x, y = region["point"]
            radius = max(6, round(min(image.size) * 0.018))
            ImageDraw.Draw(image).ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=color,
                outline="white",
                width=width,
            )
        else:
            raise ValueError(mode)
        if len(regions) > 1:
            x, y = region["box"][:2]
            font = ImageFont.load_default(size=max(12, round(min(image.size) * 0.018)))
            ImageDraw.Draw(image).text(
                (x, max(0, y - 22)),
                f"R{i + 1}",
                font=font,
                fill=color,
                stroke_width=1,
                stroke_fill="black",
            )
    return image


def locator_prompt(case: dict, setting: str, protocol: str) -> str:
    if setting == "text_only":
        return case["instruction"]
    mode = setting.removesuffix("_annotation")
    text = case["region_instruction"]
    references = []
    for i in range(len(case["regions"])):
        reference = (
            f"R{i + 1} ({COLOR_NAMES[i]} {mode}) in Image 2"
            if protocol == "visual_locator_v1"
            else f"R{i + 1}"
        )
        text = text.replace(f"{{region_{i + 1}}}", reference)
        references.append(reference)
    if protocol == "visual_locator_v1":
        return (
            f"Edit Image 1. {text} The target regions are {', '.join(references)}. "
            "Keep everything else unchanged. Return only the edited Image 1 without "
            "any markers from Image 2."
        )
    return f"{text} The supplied regions identify the targets. Keep everything else unchanged."


def prepare(
    manifest: Path, root: Path, output: Path, settings=SETTINGS, protocol: str = "visual_locator_v1"
) -> list[dict]:
    if protocol not in PROTOCOLS or not settings or any(s not in SETTINGS for s in settings):
        raise ValueError("unknown input protocol or settings")
    if len(settings) != len(set(settings)):
        raise ValueError("duplicate settings")
    cases = load_cases(manifest)
    manifest_hash = sha256_file(manifest)
    output.mkdir(parents=True, exist_ok=True)
    jobs = []
    for index, case in enumerate(cases):
        source = asset_path(root, case["source_image"])
        with Image.open(source) as im:
            im.load()
            size = list(im.size)
            for setting in settings:
                images = [str(source)]
                roles = ["clean_source_to_edit"]
                controls = []
                if setting != "text_only":
                    if protocol == "visual_locator_v1":
                        locator = output / "locators" / setting / f"{index:04d}.png"
                        locator.parent.mkdir(parents=True, exist_ok=True)
                        annotate(im, case["regions"], root, setting).save(locator)
                        images.append(str(locator.resolve()))
                        roles.append(f"{setting}_locator_only")
                    else:
                        field = {
                            "mask_annotation": "mask",
                            "box_annotation": "box",
                            "point_annotation": "point",
                        }[setting]
                        for i, region in enumerate(case["regions"]):
                            value = (
                                str(asset_path(root, region[field]))
                                if field == "mask"
                                else region[field]
                            )
                            control = {"region": f"R{i + 1}", field: value}
                            if field == "mask":
                                control["mask_sha256"] = sha256_file(Path(value))
                            controls.append(control)
                job = {
                    "case_id": case["id"],
                    "eval_index": index,
                    "setting": setting,
                    "protocol": protocol,
                    "manifest_sha256": manifest_hash,
                    "instruction_revision": case["instruction_revision"],
                    "prompt": locator_prompt(case, setting, protocol),
                    "images": images,
                    "image_roles": roles,
                    "source_size": size,
                    "image_sha256": [sha256_file(Path(p)) for p in images],
                    "controls": controls,
                }
                job["input_digest"] = digest(job)
                jobs.append(job)
    write_jsonl(output / "inputs.jsonl", jobs)
    return jobs


def verify_job(job: dict) -> None:
    original = {k: v for k, v in job.items() if k != "input_digest"}
    if digest(original) != job["input_digest"]:
        raise ValueError(f"input metadata changed: {job['case_id']}")
    for p, expected in zip(job["images"], job["image_sha256"]):
        if sha256_file(Path(p)) != expected:
            raise ValueError(f"input image changed: {p}")
    for control in job["controls"]:
        if "mask" in control and sha256_file(Path(control["mask"])) != control["mask_sha256"]:
            raise ValueError(f"native mask changed: {control['mask']}")
