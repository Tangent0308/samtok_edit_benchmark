"""Install the Git-tracked 2.6.0 mask patch into a dataset or repair work directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from samtok_benchmark.io import read_jsonl, sha256_file  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--restore-work", action="store_true", help="restore inputs for build.py replay")
    args = parser.parse_args()
    release = REPO / "data/v2_2.6.0"
    rows = read_jsonl(release / "mask_patch_manifest.jsonl")
    for row in rows:
        rel = Path(row["path"])
        if rel.is_absolute() or ".." in rel.parts or rel.parts[0] != "assets":
            raise ValueError(f"invalid patch path: {rel}")
        source = release / "mask_patch" / rel
        if source.stat().st_size != row["bytes"] or sha256_file(source) != row["sha256"]:
            raise ValueError(f"patch checksum mismatch: {source}")
        dest = (args.dataset_root / "release_2_6_work" / row["case_id"] / rel.name
                if args.restore_work else args.dataset_root / rel)
        if dest.exists() and sha256_file(dest) != row["sha256"]:
            raise FileExistsError(f"refusing to overwrite a different existing mask: {dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copyfile(source, dest)
        if args.restore_work and row.get("recipe") is not None:
            recipe = dest.with_suffix(".json")
            if not recipe.exists():
                recipe.write_text(json.dumps(row["recipe"], ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": "materialized", "masks": len(rows),
                      "destination": "repair_work" if args.restore_work else "release_assets"}))


if __name__ == "__main__":
    main()
