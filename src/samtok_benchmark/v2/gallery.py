"""Portable file:// gallery with inline metadata and dataset-relative images."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from samtok_benchmark.io import asset_path, read_jsonl, sha256_file, atomic_text, write_json
from samtok_benchmark.v2.dataset import load_cases, validate
from samtok_benchmark.v2.inputs import COLORS, render_locators, verify_job


def fit(image, size):
    im = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, "#f0f2f4")
    canvas.paste(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2))
    return canvas


def final_card(case, root, path):
    """Final U IDs only; the raw first-pass candidate card is kept separately."""
    units = copy.deepcopy(case["units"])
    for u in units:
        u["interaction"] = {"has_ref": True, "locator": "mask"}
    overlay_path = path.with_name("gold_overlay.png")
    render_locators(case, units, root, overlay_path)
    source = Image.open(asset_path(root, case["source"]["image"])).convert("RGB")
    overlay = Image.open(overlay_path).convert("RGB")
    canvas = Image.new("RGB", (1440, 880), "white")
    canvas.paste(fit(source, (720, 450)), (0, 38))
    canvas.paste(fit(overlay, (720, 450)), (720, 38))
    d = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=18)
    small = ImageFont.load_default(size=15)
    d.text(
        (10, 8), case["id"] + " | PRIVATE GOLD REVIEW | not model input", font=font, fill="black"
    )
    width = 1440 // len(units)
    for i, u in enumerate(units):
        x = i * width
        x1, y1, x2, y2 = u["target"]["box"]
        pad = max(12, round(max(x2 - x1, y2 - y1) * 0.16))
        box = (
            max(0, x1 - pad),
            max(0, y1 - pad),
            min(source.width, x2 + pad),
            min(source.height, y2 + pad),
        )
        canvas.paste(fit(source.crop(box), (width // 2 - 4, 270)), (x + 2, 545))
        canvas.paste(fit(overlay.crop(box), (width // 2 - 4, 270)), (x + width // 2 + 2, 545))
        d.text((x + 6, 496), u["id"] + " | " + u["target"]["category"], font=small, fill=COLORS[i])
        interaction = case["units"][i]["interaction"]
        d.text(
            (x + 6, 519),
            u["operation"]
            + " | "
            + ("ref+" if interaction["has_ref"] else "noref+")
            + interaction["locator"],
            font=small,
            fill="black",
        )
        d.text(
            (x + 6, 829),
            "mask area: {:.2%}".format(u["target"]["geometry"]["area_fraction"]),
            font=small,
            fill="black",
        )
        d.text(
            (x + 6, 853), "parent: " + u["target"]["parent_instance_id"], font=small, fill="black"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, quality=90)
    overlay_path.unlink()


def build(manifest: Path, root: Path, inputs: Path):
    root = root.resolve()
    stats = validate(manifest, root)
    mixed = [j for j in read_jsonl(inputs) if j["variant"] == "mixed"]
    jobs = {j["case_id"]: j for j in mixed}
    if len(jobs) != len(mixed) or any(j["protocol"] != "visual_locator_v2" for j in mixed):
        raise ValueError("gallery requires one visual-locator mixed job per case")
    cases = load_cases(manifest)
    if set(jobs) != {c["id"] for c in cases}:
        raise ValueError("gallery requires exactly all mixed release jobs")
    rows = []
    for c in cases:
        job = jobs[c["id"]]
        verify_job(job)
        path = asset_path(root, c["source"]["image"]).with_name("final_review.jpg")
        final_card(c, root, path)
        row = copy.deepcopy(c)
        row["public_prompt"] = job["prompt"]
        row["public_units"] = job["units"]
        row["public_locator_image"] = str(Path(job["images"][-1]).relative_to(root))
        row["final_review"] = str(path.relative_to(root))
        rows.append(row)
    template = Path(__file__).with_name("gallery_template.html").read_text()
    payload = json.dumps(
        {"cases": rows, "stats": stats, "manifest_sha256": sha256_file(manifest)},
        ensure_ascii=False,
    ).replace("<", "\\u003c")
    atomic_text(root / "index.html", template.replace("__PAYLOAD__", payload))
    write_json(
        root / "gallery_build.json",
        {
            "cases": len(rows),
            "manifest_sha256": sha256_file(manifest),
            "offline": True,
            "private_gold_in_reviewer_page_only": True,
            "image_references": "dataset-relative; copy/unzip the complete folder",
        },
    )
    return root / "index.html"
