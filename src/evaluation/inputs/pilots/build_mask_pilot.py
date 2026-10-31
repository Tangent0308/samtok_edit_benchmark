"""Build a small region-input pilot without changing the frozen benchmark inputs.

The pilot keeps the v2 public job schema and replaces the photographic locator with either
one binary mask (single-unit jobs) or a monochrome gray-level map (mixed jobs).  The existing
full visual-locator inputs are never modified.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
from pathlib import Path

from PIL import Image

from samtok_benchmark.io import digest, sha256_file, write_jsonl


GRAY = {"U1": 51, "U2": 102, "U3": 153, "U4": 204, "U5": 255}


def load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_region_image(job, manifest_case, units, path: Path, single: bool):
    source_path = Path(job["images"][0])
    with Image.open(source_path) as source:
        size = source.size
    out = Image.new("L", size, 0)
    by_id = {u["id"]: u for u in manifest_case["units"]}
    for unit in units:
        uid = unit["id"]
        target = by_id[uid]["target"]
        mask_path = Path(job["images"][0]).parents[1] / target["mask"]
        # The dataset root is not derivable from every source path, so the caller replaces
        # this path before invoking the function.
        if not mask_path.exists():
            raise FileNotFoundError(mask_path)
        with Image.open(mask_path) as mask:
            mask = mask.convert("L")
            if mask.size != size:
                raise ValueError(f"mask/source size mismatch for {job['case_id']} {uid}")
            value = 255 if single else GRAY[uid]
            out.paste(value, mask=mask.point(lambda v: 255 if v else 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(path)


def build_prompt(units, single: bool) -> str:
    source = "{SOURCE}"
    region = "{REGION}"
    lines = [
        "[SAMTOK_MASK_PILOT_V1]",
        f"{source} is the clean photo to edit. {region} is a spatial mask image, not a photo or reference image.",
        "Use the mask only to locate the corresponding source region. Never copy the mask, its grayscale values, its shape, or any annotation into the output.",
        "Output only the complete edited photo and preserve all unrequested content.",
    ]
    if single:
        lines.append("White pixels in the mask identify the target region; black pixels are background.")
    else:
        lines.append("The mask image is a label map: U1=gray 51, U2=gray 102, U3=gray 153, U4=gray 204, U5=gray 255; black is background.")
    for u in units:
        uid = u["id"]
        if u["locator"] == "none":
            where = "identified from the textual description only"
        elif single:
            where = "the white region in Image 2"
        else:
            where = f"the gray-{GRAY[uid]} region in Image 2"
        lines.append(f"{uid} ({where}): {u['instruction']}")
    return "\n\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=Path, required=True, help="frozen visual_locator_v2 jobs")
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--dataset-root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--single-per-mode", type=int, default=12)
    ap.add_argument("--mixed", type=int, default=12)
    ap.add_argument("--seed", type=int, default=2600)
    args = ap.parse_args()

    jobs = load_jsonl(args.jobs)
    cases = {c["id"]: c for c in load_jsonl(args.manifest)}
    rng = random.Random(args.seed)

    candidates = {mode: [] for mode in ("point", "box", "mask")}
    mixed_candidates = []
    for job in jobs:
        case = cases[job["case_id"]]
        units_by_id = {u["id"]: u for u in job["units"]}
        locators = [u["locator"] for u in job["units"] if u["locator"] != "none"]
        if len(job["units"]) >= 3 and locators:
            mixed_candidates.append(job)
        for u in job["units"]:
            if u["locator"] in candidates:
                candidates[u["locator"]].append((job, u["id"], case, units_by_id))

    selected = []
    # Deterministic sampling with a shuffle inside each bucket prevents the first manifest
    # entries from dominating while keeping the seed recorded in the output metadata.
    for mode in ("point", "box", "mask"):
        bucket = candidates[mode][:]
        rng.shuffle(bucket)
        selected.extend(("single", job, [units_by_id[uid]], case) for job, uid, case, units_by_id in bucket[: args.single_per_mode])
    rng.shuffle(mixed_candidates)
    for job in mixed_candidates[: args.mixed]:
        case = cases[job["case_id"]]
        selected.append(("mixed", job, copy.deepcopy(job["units"]), case))

    out_dir = args.output
    mask_dir = out_dir / "masks"
    out_dir.mkdir(parents=True, exist_ok=True)
    pilot_jobs = []
    seen = set()
    for kind, original, units, case in selected:
        suffix = "single-" + units[0]["id"] if kind == "single" else "mixed"
        job_id = f"{case['id']}--maskpilot-{suffix}"
        if job_id in seen:
            continue
        seen.add(job_id)
        source = Path(original["images"][0])
        # Resolve target masks from the explicit dataset root, never from the public job.
        case_units = {u["id"]: u for u in case["units"]}
        region = Image.new("L", tuple(original["source_size"]), 0)
        for unit in units:
            if unit["locator"] == "none":
                continue
            mask_path = args.dataset_root / case_units[unit["id"]]["target"]["mask"]
            with Image.open(mask_path) as mask:
                mask = mask.convert("L")
                if list(mask.size) != original["source_size"]:
                    raise ValueError(f"mask/source size mismatch: {job_id}")
                value = 255 if kind == "single" else GRAY[unit["id"]]
                region.paste(value, mask=mask.point(lambda v: 255 if v else 0))
        region_path = mask_dir / f"{job_id}.png"
        region_path.parent.mkdir(parents=True, exist_ok=True)
        region.save(region_path)

        job = copy.deepcopy(original)
        job["job_id"] = job_id
        job["variant"] = "single" if kind == "single" else "mixed"
        job["unit_ids"] = [u["id"] for u in units]
        job["units"] = units
        job["images"] = [str(source), str(region_path.resolve())]
        job["input_files"] = [
            {"path": str(source), "sha256": sha256_file(source), "role": "clean_source"},
            {"path": str(region_path.resolve()), "sha256": sha256_file(region_path), "role": "user_region_mask"},
        ]
        job["prompt"] = build_prompt(units, single=(kind == "single"))
        job["input_digest"] = digest({k: v for k, v in job.items() if k != "input_digest"})
        pilot_jobs.append(job)

    pilot_jobs.sort(key=lambda j: j["job_id"])
    write_jsonl(out_dir / "jobs.jsonl", pilot_jobs)
    meta = {
        "pilot": "mask_input_v1",
        "seed": args.seed,
        "single_per_mode": args.single_per_mode,
        "mixed": args.mixed,
        "jobs": len(pilot_jobs),
        "counts": {"single": sum(j["variant"] == "single" for j in pilot_jobs), "mixed": sum(j["variant"] == "mixed" for j in pilot_jobs)},
        "gray_map": GRAY,
        "source_jobs": str(args.jobs),
        "manifest": str(args.manifest),
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
