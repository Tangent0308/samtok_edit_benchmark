"""Prepare blinded local output inspection; export human ratings separately."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from PIL import Image

from samtok_benchmark.io import digest, read_jsonl, sha256_file, write_json
from samtok_benchmark.judge.rubric import RUBRIC, RUBRIC_ID, outlined
from samtok_benchmark.judge.protocol import VERSION


def package_human_review(manifest: Path, output: Path, reviewer: str) -> dict:
    if not reviewer.strip():
        raise ValueError("reviewer identity is required")
    jobs = read_jsonl(manifest)
    if any(j.get("judge_protocol") != VERSION for j in jobs):
        raise ValueError(
            "wrong judge protocol; re-prepare before applying the current human rubric"
        )
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("choose a new directory for independent human review")
    output.mkdir(parents=True, exist_ok=True)
    for name in ("human.html", "human.js", "style.css"):
        dest = "index.html" if name == "human.html" else name
        (output / dest).write_bytes(
            files("samtok_benchmark.review").joinpath("static", name).read_bytes()
        )
    samples = []
    (output / "rubric.txt").write_text(RUBRIC, encoding="utf-8")
    # Shuffle by opaque digest to reduce ordering clues about methods/settings.
    for index, j in enumerate(sorted(jobs, key=lambda r: digest(r["sample_id"]))):
        if j["delivery_status"] != "available":
            continue
        sample = {
            "sample_id": j["sample_id"],
            "input_digest": j["input_digest"],
            "instruction": j["instruction"],
            "reviewer": reviewer,
            "index": index,
        }
        for label, key, hashkey in (
            ("before", "source_image", "source_sha256"),
            ("after", "output_image", "output_sha256"),
        ):
            if sha256_file(Path(j[key])) != j[hashkey]:
                raise ValueError(f"review image changed: {j[key]}")
            for region in j["regions"]:
                if sha256_file(Path(region["mask"])) != region["mask_sha256"]:
                    raise ValueError("region mask changed")
            with Image.open(j[key]) as im:
                im = im.convert("RGB")
                folder = output / "images" / f"{index:04d}"
                folder.mkdir(parents=True, exist_ok=True)
                for suffix, image in (
                    ("clean", im),
                    ("contours", outlined(im, j["regions"], im.width * im.height)),
                ):
                    path = folder / f"{label}_{suffix}.png"
                    image.save(path)
                    sample[f"{label}_{suffix}"] = path.relative_to(output).as_posix()
        samples.append(sample)
    if not samples:
        raise ValueError("no available outputs for human review")
    write_json(output / "samples.json", samples)
    write_json(
        output / "review_metadata.json",
        {
            "judge_manifest_sha256": sha256_file(manifest),
            "judge_protocol": VERSION,
            "rubric": RUBRIC_ID,
            "rubric_sha256": sha256_file(output / "rubric.txt"),
            "reviewer": reviewer,
            "available_outputs": len(samples),
            "unavailable_outputs": len(jobs) - len(samples),
        },
    )
    (output / "README.md").write_text(
        "Run `python -m http.server 8766 --bind 127.0.0.1` in this directory and open "
        "http://127.0.0.1:8766. Rate edit/preservation/quality from 0 to 4, or unknown. "
        "Use the included rubric.txt and anchored score options; inspect clean images and contours. "
        "Method names and VLM scores are hidden. Decisions persist in browser localStorage; "
        "download human_scores.jsonl before moving machines or clearing browser storage.\n",
        encoding="utf-8",
    )
    return {
        "available_outputs": len(samples),
        "output": str(output.resolve()),
        "reviewer": reviewer,
    }
