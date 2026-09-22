"""Freeze existing editor outputs for judging; never rerun an image editor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from PIL import Image
from tqdm import tqdm

from evaluation.common import (BASE_SETTING_KEYS, DEFAULT_DATASET_ROOT,
                               DEFAULT_BASELINE_PREPARED_MANIFEST, REPO_ROOT,
                               atomic_write_json, atomic_write_jsonl, read_jsonl, sha256_file)
from evaluation.metrics.protocol import VERSION, digest

EXPERIMENTS = Path("/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit")
ROOTS = {
    "replan_qwen": (EXPERIMENTS / "replan_656/inference/qwen2511"),
    "replan_flux": (EXPERIMENTS / "replan_656/inference/flux2_klein4b"),
    "qwen": (EXPERIMENTS / "referential_finegrained_edit_benchmark_656_two_image_locator/inference/qwen"),
    "flux": (EXPERIMENTS / "referential_finegrained_edit_benchmark_656_two_image_locator/inference/flux2"),
    "qwen21": EXPERIMENTS / "qwen21_656/inference/qwen21",
}
DEFAULT_METHODS = ["qwen", "flux", "qwen21", "replan_qwen", "replan_flux"]
# Source-level split; deterministic and shared across models/settings/controls.
DEV = [483, 488, 533, 539, 550, 586, 597, 611, 632, 635, 642, 650]
HOLDOUT = [150, 181, 345, 475, 514, 543, 544, 548, 553, 555, 608, 641]


def prepare(args):
    rows = read_jsonl(args.manifest)
    prepared = read_jsonl(args.prepared_manifest)
    if [r["id"] for r in rows] != [r["id"] for r in prepared]:
        raise ValueError("benchmark/prepared order mismatch")
    for original, frozen in zip(rows, prepared):
        if any(frozen.get(k) != v for k, v in original.items()):
            raise ValueError(f"benchmark differs from frozen generation data: {original['id']}")
    frozen_hash = sha256_file(args.prepared_manifest)
    hash_cache = {}
    size_cache = {}

    def file_hash(p):
        p = Path(p)
        if p not in hash_cache:
            hash_cache[p] = sha256_file(p)
        return hash_cache[p]

    jobs = []
    def add(index, method, setting, output):
        row = rows[index]
        source = args.dataset_root / row["source_image"]
        if source not in size_cache:
            with Image.open(source) as im:
                size_cache[source] = list(im.size)
        size = size_cache[source]
        regions = []
        for region in row["regions"]:
            mask = args.dataset_root / region["mask"]
            regions.append({"box": region["box"], "point": region["point"],
                            "mask": str(mask), "mask_sha256": file_hash(mask)})
        exists = output.is_file()
        if exists:
            sidecar = output.with_suffix(".json")
            record = json.loads(sidecar.read_text())
            if record.get("case_id") != row["id"]:
                raise ValueError(f"generation case mismatch: {sidecar}")
            # Bare-model outputs must match the exact declared generation prompt.
            if method in ("qwen", "flux", "qwen21"):
                origin = prepared[index]
                frozen_input = origin["prepared"]["baseline_inputs"][setting]
                if record.get("conditioned_prompt") != frozen_input["prompt"]:
                    raise ValueError(f"generation prompt mismatch: {sidecar}")
                if record.get("model_input_images") != frozen_input["images"]:
                    raise ValueError(f"generation image inputs mismatch: {sidecar}")
            elif method.startswith("replan"):
                if record.get("manifest_sha256") != frozen_hash:
                    raise ValueError(f"RePlan generation manifest differs: {sidecar}")
                frozen_input = prepared[index]["prepared"]["baseline_inputs"][setting]
                if record.get("planner_prompt") != frozen_input["prompt"] or record.get("planner_input_images") != frozen_input["images"]:
                    raise ValueError(f"RePlan planner inputs differ: {sidecar}")
        job = {"sample_id": f"{index:04d}/{method}/{setting}",
               "case_id": row["id"], "eval_index": index, "method": method, "setting": setting,
               "source_dataset": row["source_dataset"], "edit_type": row["edit_type"],
               "source_image": str(source), "source_sha256": file_hash(source), "source_size": size,
               "output_image": str(output), "output_sha256": file_hash(output) if exists else None,
               "instruction": row["instruction"]["with_location_reference"],
               "region_instruction": row["instruction"]["region_only"], "regions": regions,
               "annotation_status": "conflict_review_required" if index == 321 else "imported_not_human_calibrated",
               "protocol": "baseline_two_image_locator_inputs_v2",
               "prepared_sha256": frozen_hash,
               "cohort": "full656",
               "split": "dev" if index in DEV else "holdout" if index in HOLDOUT else "unassigned",
               "control": None, "expected": {},
               "label_provenance": "unlabeled",
               "delivery_status": "available" if exists else "missing_output"}
        job["input_digest"] = digest(job)
        jobs.append(job)

    with ThreadPoolExecutor(max_workers=args.io_workers) as pool:
        for method in args.methods:
            for setting in BASE_SETTING_KEYS:
                def freeze(index):
                    add(index, method, setting, ROOTS[method] / setting / f"{index:04d}.png")
                list(tqdm(pool.map(freeze, range(len(rows))), total=len(rows),
                          desc=f"freeze {method}/{setting}"))
    jobs.sort(key=lambda j: (args.methods.index(j["method"]), BASE_SETTING_KEYS.index(j["setting"]), j["eval_index"]))
    if len({j["sample_id"] for j in jobs}) != len(jobs):
        raise ValueError("duplicate sample ids")
    if args.require_complete and any(j["delivery_status"] != "available" for j in jobs):
        raise ValueError("Full evaluation requires all editor outputs before freezing the manifest")
    atomic_write_jsonl(args.output, jobs)
    summary = {"version": VERSION, "manifest": str(args.output), "sha256": sha256_file(args.output),
               "samples": len(jobs), "missing": sum(j["delivery_status"] != "available" for j in jobs),
               "cases": len({j["case_id"] for j in jobs}),
               "note": "All methods use the same frozen 656-case benchmark. Judge scores are not human gold."}
    atomic_write_json(args.output.with_suffix(".summary.json"), summary)
    print(json.dumps(summary, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, default=REPO_ROOT / "benchmark/benchmark.jsonl")
    p.add_argument("--prepared-manifest", type=Path, default=DEFAULT_BASELINE_PREPARED_MANIFEST)
    p.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--require-complete", action="store_true")
    p.add_argument("--io-workers", type=int, default=8)
    p.add_argument("--methods", nargs="+", choices=list(ROOTS), default=DEFAULT_METHODS)
    prepare(p.parse_args())


if __name__ == "__main__":
    main()
