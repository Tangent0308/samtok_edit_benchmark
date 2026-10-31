"""Mirror a validated release into the canonical dataset root, preserving 2.5.0."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from samtok_benchmark.paths import repository_root
import re
import shutil
import sys

REPO = repository_root()
sys.path.insert(0, str(REPO / "src"))
from samtok_benchmark.io import sha256_file, write_json  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.dataset_root
    release = REPO / "data/v2_2.6.0"
    meta = json.loads((release / "release.json").read_text())
    validation = json.loads((release / "validation.json").read_text())
    if validation["status"] != "passed" or validation["manifest_sha256"] != meta["manifest_sha256"]:
        raise ValueError("release must pass full validation before mirroring")
    # Resolve every document before any dataset write; archival sources moved in src-layout.
    docs = ["RELEASE_2_6_0_ZH.md", "RELEASE_2_6_BEFORE_AFTER_ZH.md",
            "RELEASE_2_6_REPAIR_STATUS_ZH.md", "RELEASE_2_6_REMAINING_CASES_ZH.md",
            "INSTRUCTION_PROTOCOL_ZH.md", "INSTRUCTION_PROTOCOL_1.0_ZH.md",
            "07_SAMTokEdit_Qwen21_指令协议2.0_noref改为盲指代.md"]
    docs_root = REPO / "docs/archive/previous/archive"
    images_root = REPO / "docs/archive/previous/assets/release_2_6"
    guide_path = REPO / "data/provenance/construction/release_2_6/DATA_ROOT_README_ZH.md"
    for source in [guide_path, images_root, *(docs_root / name for name in docs)]:
        if not source.exists():
            raise FileNotFoundError(source)
    current = root / "benchmark"
    previous = root / "benchmark_history/2.5.0"
    old_sha = sha256_file(current / "cases.jsonl")
    if old_sha not in {meta["base_manifest_sha256"], meta["manifest_sha256"]}:
        raise ValueError("unrecognized current dataset manifest; refusing replacement")
    if old_sha == meta["base_manifest_sha256"]:
        previous.mkdir(parents=True, exist_ok=True)
        for source in current.iterdir():
            if source.is_file():
                dest = previous / source.name
                if dest.exists() and sha256_file(dest) != sha256_file(source):
                    raise FileExistsError(f"different historical file already exists: {dest}")
                if not dest.exists():
                    shutil.copyfile(source, dest)
        for name in ["README.md", "BENCHMARK_V2_ZH.md", "storage.json"]:
            source, dest = root / name, previous / ("data_root_" + name)
            if source.exists() and not dest.exists():
                shutil.copyfile(source, dest)
    if sha256_file(previous / "cases.jsonl") != meta["base_manifest_sha256"]:
        raise ValueError("historical 2.5.0 manifest backup missing or changed")
    receipt = []
    for source in sorted(release.iterdir()):
        if source.is_file() and source.name != "data_root_sync.json":
            dest = current / source.name
            shutil.copyfile(source, dest)
            receipt.append({"path": str(dest.relative_to(root)), "sha256": sha256_file(dest)})
    # These are 2.5.0 publication receipts, preserved in history, not current receipts.
    for name in ["review_package.json", "lark_publication.json", "progress.json"]:
        source = current / name
        if source.exists():
            if sha256_file(source) != sha256_file(previous / name):
                raise ValueError(f"historical receipt changed: {source}")
            source.unlink()
    write_json(root / "storage.json", {
        "schema_version": "1.0", "release_version": "2.6.0", "root": str(root),
        "cases": meta["cases"], "units": meta["units"],
        "assets": validation["inventory_checked"], "images": validation["unique_sources"],
        "manifest_sha256": meta["manifest_sha256"],
        "instruction_protocol_version": "2.0", "mask_semantics_version": "2.0",
        "relative_paths": {"manifest": "benchmark/cases.jsonl", "assets": "assets/",
                           "validation": "benchmark/validation.json", "statistics": "benchmark/statistics.json",
                           "comparison": "benchmark/comparison_summary.json",
                           "historical_metadata": "benchmark_history/2.5.0/",
                           "historical_audit_archive": "audit/samtok_edit_benchmark_v2_review_1084_20261015.zip",
                           "historical_audit_pdf": "audit/benchmark_all_1084_cases.pdf"},
        "independent_human_verified": False, "semantic_signoff": False,
        "path_policy": "Current metadata is mirrored from repository data/v2_2.6.0; old audit cards/ZIP/PDF remain 2.5.0 evidence.",
    })
    guide = guide_path.read_text()
    for name in ["README.md", "BENCHMARK_V2_ZH.md"]:
        (root / name).write_text(guide, encoding="utf-8")
    for name in docs:
        source = docs_root / name
        text = source.read_text()
        # Repo-relative prose links resolve on GitHub; visual example images stay local.
        def link(match):
            target = match.group(2)
            if "://" in target or target.startswith(("#", "/")):
                return match.group(0)
            path, sep, anchor = target.partition("#")
            relative = (source.parent / path).resolve().relative_to(REPO)
            return f"[{match.group(1)}](https://github.com/Tangent0308/samtok_edit_benchmark/blob/v2branch/{relative}{sep}{anchor})"
        text = re.sub(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)", link, text)
        dest = root / "docs" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    shutil.copytree(images_root, root / "docs/assets/release_2_6", dirs_exist_ok=True)
    write_json(release / "data_root_sync.json", {
        "status": "synced", "dataset_root": str(root), "release_version": "2.6.0",
        "manifest_sha256": meta["manifest_sha256"],
        "preserved_base_manifest_sha256": sha256_file(previous / "cases.jsonl"),
        "historical_metadata": "benchmark_history/2.5.0", "mirrored_files": receipt,
    })
    shutil.copyfile(release / "data_root_sync.json", current / "data_root_sync.json")
    print(json.dumps({"status": "synced", "release_version": "2.6.0", "manifest": str(current / "cases.jsonl"),
                      "manifest_sha256": sha256_file(current / "cases.jsonl")}))


if __name__ == "__main__":
    main()
