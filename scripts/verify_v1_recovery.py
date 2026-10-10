"""Verify v1 using only a NAS namespace and the repository (standard library only)."""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


DEFAULT_NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def verify(nas: Path, metadata_only: bool, model_weights: bool, workers: int) -> dict:
    nas = nas.resolve()
    data = nas / "datasets/samtok_edit_benchmark_v1"
    experiments = nas / "experiments/SAMTokEdit/benchmark_v1"
    recovery = experiments / "recovery"
    index = json.loads((recovery / "index.json").read_text())
    inventory_path = recovery / "manifest.jsonl"
    if digest(inventory_path) != index["manifest_sha256"]:
        raise ValueError("recovery inventory identity mismatch")
    inventory = rows(inventory_path)
    parents = {}

    def contained(base: Path, relative: str) -> Path:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe relative path: {relative}")
        result = base / path
        parent = parents.get(result.parent)
        if parent is None:
            parent = result.parent.resolve(strict=True)
            parents[result.parent] = parent
        resolved = parent / result.name
        if resolved.is_symlink():
            resolved = resolved.resolve(strict=True)
        # NAS-only links are allowed, including checkpoint links to shared NAS weights.
        if not resolved.is_relative_to(nas):
            raise ValueError(f"dependency escapes NAS: {result}")
        return result

    def check(record: dict) -> None:
        path = contained(nas, record["path"])
        if path.stat().st_size != record["bytes"]:
            raise ValueError(f"size mismatch: {path}")
        if metadata_only or (record.get("model_weight") and not model_weights):
            return
        if digest(path) != record["sha256"]:
            raise ValueError(f"checksum mismatch: {path}")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(check, inventory))

    expected = {str(nas / record["path"]): record["sha256"] for record in inventory}
    formal = rows(data / "benchmark/cases.jsonl")
    if len(formal) != 450 or digest(data / "benchmark/cases.jsonl") != index["formal_sha256"]:
        raise ValueError("formal release identity mismatch")
    local_candidates = rows(data / "candidates/expansion_433_20261008/cases.local.jsonl")
    if len(local_candidates) != 433:
        raise ValueError("expansion candidate count mismatch")
    review_root = data / "reviews/qwen21_883_20261009"
    review = rows(review_root / "manifests/all_cases.jsonl")
    if len(review) != 883:
        raise ValueError("review pool count mismatch")
    for pool, base in [(formal, data),
                       (local_candidates, data / "candidates/expansion_433_20261008"),
                       (review, review_root)]:
        for case in pool:
            contained(base, case["source_image"])
            for region in case["regions"]:
                contained(base, region["mask"])
            if case.get("qwen21_output"):
                contained(base, case["qwen21_output"])

    mappings = json.loads((experiments / "path_map.json").read_text())["prefix_mappings"]
    mappings = sorted(mappings, key=lambda item: len(item["from"]), reverse=True)
    original_nas = Path(index["original_nas_root"])

    def relocated(value: str) -> Path:
        path = Path(value)
        if path.is_relative_to(original_nas):
            return contained(nas, str(path.relative_to(original_nas)))
        for mapping in mappings:
            prefix = Path(mapping["from"])
            if path.is_relative_to(prefix):
                target = Path(mapping["to"])
                if not target.is_relative_to(original_nas):
                    raise ValueError(f"mapping target is not persistent: {target}")
                relative = target.relative_to(original_nas) / path.relative_to(prefix)
                return contained(nas, str(relative))
        raise ValueError(f"unresolved historical dependency: {value}")

    input_jobs = 0
    for name in ["text_only_450_20261007", "expansion_433_20261008",
                 "judge_calibration_48_20261006"]:
        for job in rows(experiments / name / "inputs/inputs.jsonl"):
            input_jobs += 1
            for image, checksum in zip(job["images"], job["image_sha256"]):
                target = relocated(image)
                if expected.get(str(target)) != checksum:
                    raise ValueError(f"frozen input image identity mismatch: {image}")

    outputs = rows(experiments / "resolved_outputs.jsonl")
    if len(outputs) != 1717:
        raise ValueError("archived output count mismatch")
    for record in outputs:
        original = json.loads(contained(experiments, record["raw_record"]).read_text())
        for key, sha_key in [("output_image", "output_sha256"),
                             ("native_output", "native_sha256")]:
            path = contained(experiments, record[key])
            if expected.get(str(path)) != record[sha_key] or original[sha_key] != record[sha_key]:
                raise ValueError(f"output identity mismatch: {path}")
    return {
        "status": "passed", "nas_root": str(nas), "inventory_files": len(inventory),
        "formal_cases": 450, "candidate_cases": 433, "review_cases": 883,
        "frozen_input_jobs": input_jobs, "output_records": len(outputs),
        "checksum_mode": "metadata_only" if metadata_only else "sha256",
        "model_weight_sha256": model_weights and not metadata_only,
        "all_critical_references_resolve_to_nas": True,
        "historical_local_sources_opened": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nas-root", type=Path, default=DEFAULT_NAS)
    parser.add_argument("--metadata-only", action="store_true", help="check sizes and references")
    parser.add_argument("--with-model-weights", action="store_true", help="also hash model shards")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    result = verify(args.nas_root, args.metadata_only, args.with_model_weights, args.workers)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
