#!/usr/bin/env python3
"""Render fixed diagnostic cases, with complete unmodified model outputs and hash provenance."""

import argparse
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from samtok_benchmark.external_magicbrush.data import immutable, read
from samtok_benchmark.postprocessing.magicbrush_mirage_recovery import BUNDLE, OLD, check, proof

CASES = ["30-1", "2886-2", "3661-2", "47294-1", "300994-2"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    destination = args.destination
    destination.mkdir(parents=True, exist_ok=True)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font = ImageFont.truetype(font_path, 18)
    title_font = ImageFont.truetype(font_path, 22)
    reference = {r["case_id"]: r for r in read(BUNDLE / "private/evaluation.json")}
    provenance = []
    for case in CASES:
        public = read(BUNDLE / f"public/mask-free/{case}/public.json")
        recovered = read(args.root / "edit" / case / "result.json")
        if recovered["status"] != "completed":
            continue
        assets = [("Source", public["source"])]
        for name, label in [
            ("replan", "RePlan"),
            ("mirage", "MIRAGE (recovered)"),
            ("mice", "MICE"),
            ("sitedit", "SITEdit (final)"),
        ]:
            if name == "mirage":
                asset = recovered["output"]
            else:
                root = OLD if name != "sitedit" else OLD.parent / "r2_20261110"
                result = read(root / f"runs/{name}/edit/mask-free/independent/{case}/result.json")
                asset = {"path": result["output_image"], "sha256": result["output_sha256"]}
            assets.append((label, asset))
        assets.append(("Human reference", reference[case]["target"]))
        width, height = 1920, 398
        canvas = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(canvas)
        draw.text((8, 8), case + " | " + public["instruction"], font=title_font, fill="black")
        for index, (label, asset) in enumerate(assets):
            check(asset)
            image = Image.open(asset["path"]).convert("RGB")
            image.thumbnail((312, 312), Image.Resampling.LANCZOS)
            x = index * 320 + (320 - image.width) // 2
            canvas.paste(image, (x, 74))
            draw.text((index * 320 + 6, 48), label, font=font, fill="black")
        high = destination / f"{case}-full.png"
        low = destination / f"{case}.png"
        if high.exists() or low.exists():
            raise ValueError("Preview destination already contains this case")
        canvas.save(high)
        canvas.resize((960, 199), Image.Resampling.LANCZOS).save(low)
        provenance.append(
            {
                "case_id": case,
                "selection": "fixed functional smoke cases, not score selection",
                "inputs": [{"label": label, **asset} for label, asset in assets],
                "preview": proof(low),
                "full": proof(high),
            }
        )
    immutable(destination / "PROVENANCE.json", provenance)
    print(destination)


if __name__ == "__main__":
    main()
