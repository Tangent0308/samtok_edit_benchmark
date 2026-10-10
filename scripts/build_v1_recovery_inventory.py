"""Index persistent v1 contents; archived payloads retain their certified hashes."""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from verify_v1_recovery import DEFAULT_NAS, digest, rows


def build(nas: Path) -> dict:
    nas = nas.resolve()
    data = nas / "datasets/samtok_edit_benchmark_v1"
    experiments = nas / "experiments/SAMTokEdit/benchmark_v1"
    recovery = experiments / "recovery"
    configuration = json.loads((data / "benchmark/recovery.json").read_text())
    original_nas = Path(configuration["nas_user_root"])
    expected = {}
    paths = []
    for root in (data, experiments):
        for parent, directories, files in os.walk(root, followlinks=False):
            for name in directories:
                directory = Path(parent) / name
                if directory.is_symlink():
                    raise ValueError(f"directory links require an explicit inventory: {directory}")
            paths.extend(Path(parent) / name for name in files)
    print(f"Indexing {len(paths)} NAS files", flush=True)
    for manifest in paths:
        if manifest.name == "ARCHIVE_MANIFEST.jsonl":
            for record in rows(manifest):
                expected[str(manifest.parent / record["path"])] = record["sha256"]
    for record in rows(data / "benchmark/asset_manifest.jsonl"):
        expected[str(data / record["local_path"])] = record["sha256"]
    models = json.loads((recovery / "models/verification.json").read_text())
    weights = {
        str((nas / Path(item["path"]).relative_to(original_nas)).resolve()): item
        for item in models["weights"]
    }
    def entry(path: Path) -> dict | None:
        if path in (recovery / "manifest.jsonl", recovery / "index.json"):
            return None
        if path.is_relative_to(recovery / "verification"):
            return None
        resolved = path.resolve(strict=True) if path.is_symlink() else path
        if not resolved.is_relative_to(nas):
            raise ValueError(f"persistent namespace has an external link: {path}")
        weight = weights.get(str(resolved))
        checksum = (weight["sha256"] if weight else
                    expected.get(str(path)) or digest(path))
        record = {"path": str(path.relative_to(nas)),
                  "bytes": path.stat().st_size, "sha256": checksum}
        if weight:
            record["model_weight"] = True
        if path.is_symlink():
            record["link_target"] = str(resolved.relative_to(nas))
        return record

    records = []
    with ThreadPoolExecutor(max_workers=12) as executor:
        for position, record in enumerate(executor.map(entry, sorted(paths)), 1):
            if record is not None:
                records.append(record)
            if position % 5000 == 0:
                print(f"Indexed {position}/{len(paths)} files", flush=True)
    if len({record["path"] for record in records}) != len(records):
        raise ValueError("duplicate inventory paths")
    manifest = recovery / "manifest.jsonl"
    manifest.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n"
                                for record in records))
    index = {
        "schema_version": "1.0", "original_nas_root": str(original_nas),
        "manifest_sha256": digest(manifest), "files": len(records),
        "bytes": sum(record["bytes"] for record in records),
        "model_weight_links": sum(record.get("model_weight", False) for record in records),
        "formal_sha256": digest(data / "benchmark/cases.jsonl"),
        "policy": "Archive-certified hashes are preserved; unknown files are hashed on NAS. "
                  "Run verify_v1_recovery.py to verify actual content. "
                  "Inventory/index and subsequently generated recovery verification reports "
                  "are excluded to avoid circular checksums.",
    }
    (recovery / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nas-root", type=Path, default=DEFAULT_NAS)
    args = parser.parse_args()
    print(json.dumps(build(args.nas_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
