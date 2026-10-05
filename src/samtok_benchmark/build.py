"""Materialize the frozen v1 selection without rerunning subjective selection."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from samtok_benchmark.dataset import validate
from samtok_benchmark.io import asset_path, read_jsonl, sha256_file


def materialize(
    release: Path,
    output: Path,
    assets_root: Path | None = None,
    source_maps: list[str] | None = None,
) -> dict:
    """Copy exact released assets, checking checksums before publishing output.

    With assets_root, input files use release-relative paths. Otherwise use the
    recorded original paths, optionally translating old=new source prefixes.
    Selection and natural-language instructions are frozen artifacts, not an
    automatic claim that the subjective review can be reproduced from scores.
    """
    release = release.resolve()
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"output already exists; choose a new directory: {output}")
    maps = []
    for item in source_maps or []:
        old, sep, new = item.partition("=")
        if not sep:
            raise ValueError("--source-map must be OLD_PREFIX=NEW_PREFIX")
        maps.append((Path(old), Path(new)))
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        for asset in read_jsonl(release / "asset_manifest.jsonl"):
            if assets_root:
                src = asset_path(assets_root, asset["local_path"])
            else:
                src = Path(asset["original_path"])
                for old, new in maps:
                    if src.is_relative_to(old):
                        src = new / src.relative_to(old)
                        break
            if sha256_file(src) != asset["sha256"]:
                raise ValueError(f"source checksum mismatch: {src}")
            dest = asset_path(staging, asset["local_path"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        shutil.copytree(release, staging / "benchmark")
        report = validate(
            staging / "benchmark/cases.jsonl",
            staging,
            staging / "benchmark/asset_manifest.jsonl",
            expected_cases=450,
            output=staging / "benchmark/validation_report.json",
        )
        os.replace(staging, output)
        return report
    finally:
        if staging.exists():
            shutil.rmtree(staging)
