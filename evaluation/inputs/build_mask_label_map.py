"""Build full-release grayscale label-map inputs from public v2 jobs.

The source job list stays unchanged. Each locator-bearing unit is represented by a stable
8-bit value in a second image (U1=51, ..., U5=255); ref+none units remain text-only. The
label map is an input locator, never a gold evaluator asset, and its digest is recorded in
the public job inventory.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from PIL import Image

from samtok_benchmark.io import digest, sha256_file, write_jsonl
from samtok_benchmark.v2.inputs import verify_job

GRAY = {"U1": 51, "U2": 102, "U3": 153, "U4": 204, "U5": 255}


def rows(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def build_label_map(job: dict, case: dict, dataset_root: Path, path: Path):
    image_path = Path(job["images"][0])
    with Image.open(image_path) as source:
        size = source.size
    image = Image.new("L", size, 0)
    by_id = {u["id"]: u for u in case["units"]}
    for unit in job["units"]:
        if unit["locator"] == "none":
            continue
        target = by_id[unit["id"]]["target"]
        mask_path = dataset_root / target["mask"]
        with Image.open(mask_path) as mask:
            mask = mask.convert("L")
            if mask.size != size:
                raise ValueError(f"mask/source size mismatch: {job['job_id']} {unit['id']}")
            binary = mask.point(lambda value: 255 if value else 0)
            image.paste(GRAY[unit["id"]], mask=binary)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def build(source_jobs: Path, manifest: Path, dataset_root: Path, output: Path):
    jobs = rows(source_jobs)
    cases = {case["id"]: case for case in rows(manifest)}
    output.mkdir(parents=True, exist_ok=True)
    maps = output / "label_maps"
    result = []
    for original in jobs:
        case = cases[original["case_id"]]
        if not any(u["locator"] != "none" for u in original["units"]):
            # A text-only job is already valid and needs no second image.
            result.append(copy.deepcopy(original))
            continue
        label_path = maps / f"{original['job_id']}.png"
        build_label_map(original, case, dataset_root, label_path)
        job = copy.deepcopy(original)
        job["job_id"] = original["job_id"] + "--labelmap"
        job["images"] = [original["images"][0], str(label_path.resolve())]
        job["input_files"] = [
            {"path": original["images"][0], "sha256": sha256_file(Path(original["images"][0])), "role": "clean_source"},
            {"path": str(label_path.resolve()), "sha256": sha256_file(label_path), "role": "user_region_label_map"},
        ]
        lines = [
            "[SAMTOK_LABEL_MAP_V1]",
            "Edit {SOURCE} and output the complete edited photo at its original size.",
            "{REGION} is a grayscale label map for locating source regions; it is not a photo.",
            "Use only the labeled regions to locate targets. Never copy grayscale values, boundaries, or annotations into the output.",
            "Black is background; U1=gray 51, U2=gray 102, U3=gray 153, U4=gray 204, U5=gray 255.",
            "Perform all instructions together and preserve unrequested content.",
        ]
        for unit in job["units"]:
            where = f"the gray-{GRAY[unit['id']]} region in {{REGION}}" if unit["locator"] != "none" else "identified from the text only"
            lines.append(f"{unit['id']} ({where}): {unit['instruction']}")
        job["prompt"] = "\n\n".join(lines)
        job["input_digest"] = digest({k: v for k, v in job.items() if k != "input_digest"})
        verify_job(job, verify_assets=False)
        result.append(job)
    write_jsonl(output / "jobs.jsonl", sorted(result, key=lambda row: row["job_id"]))
    metadata = {
        "mode": "grayscale_label_map_v1",
        "source_jobs": str(source_jobs),
        "manifest": str(manifest),
        "jobs": len(result),
        "jobs_with_label_map": sum(len(job["images"]) == 2 for job in result),
        "gray_map": GRAY,
    }
    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-jobs", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source_jobs, args.manifest, args.dataset_root, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
