"""Archive the portable package, update both existing HF download names, verify remote bytes."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from huggingface_hub import HfApi, CommitOperationAdd, hf_hub_download, hf_hub_url
from huggingface_hub.utils import disable_progress_bars

REPO = Path(__file__).resolve().parents[1]
REMOTE_NAMES = [
    "samtok_edit_benchmark_v2_review_20261010.zip",
    "sa1b_source_selection_200cases_review_20261010.zip",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    a = parser.parse_args()
    disable_progress_bars()
    meta = json.loads((a.package / "package_metadata.json").read_text())
    release = json.loads((REPO / "data/v2/release.json").read_text())
    assert meta["cases"] == release["cases"] and meta["units"] == release["units"]
    assert meta["instruction_version"] == release["release_version"]
    assert meta["manifest_sha256"] == release["manifest_sha256"]
    pdf = a.package / "benchmark_all_200_cases.pdf"
    assert pdf.is_file(), "Build the self-contained PDF before publishing"
    assert not (a.package / "reviews").exists(), (
        "Never publish local user review records by accident"
    )
    temporary = a.zip.with_suffix(".zip.tmp")
    with zipfile.ZipFile(
        temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        for p in sorted(a.package.rglob("*")):
            if p.is_file():
                archive.write(p, str(Path(a.package.name) / p.relative_to(a.package)))
    with zipfile.ZipFile(temporary) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert not any("/reviews/" in n or "__pycache__" in n for n in names)
    temporary.replace(a.zip)
    with a.zip.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    size = a.zip.stat().st_size
    a.zip.with_suffix(".zip.sha256").write_text(f"{sha}  {a.zip.name}\n")
    receipt = {
        "status": "upload_pending",
        "release_version": release["release_version"],
        "instruction_protocol_version": release["instruction_protocol_version"],
        "package": str(a.package),
        "archive": str(a.zip),
        "repo_id": "TTangenty/samtok_edit",
        "remote_names": REMOTE_NAMES,
        "size_bytes": size,
        "sha256": sha,
        "manifest_sha256": meta["manifest_sha256"],
        "cases": 200,
        "units": 785,
        "unit_operations": meta["unit_operations"],
        "independent_human_verified": False,
        "same_content_compatibility_alias": True,
        "download_url": hf_hub_url("TTangenty/samtok_edit", REMOTE_NAMES[0], repo_type="dataset"),
    }
    local_receipt = a.zip.with_suffix(".json")
    local_receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    api = HfApi()
    before = api.repo_info(receipt["repo_id"], repo_type="dataset", files_metadata=True)
    previous = {f.rfilename: f for f in before.siblings}
    operations = []
    for name in REMOTE_NAMES:
        operations.extend(
            [
                CommitOperationAdd(path_in_repo=name, path_or_fileobj=str(a.zip)),
                CommitOperationAdd(
                    path_in_repo=name + ".sha256", path_or_fileobj=f"{sha}  {name}\n".encode()
                ),
            ]
        )
    readme = (
        (REPO / "README.md")
        .read_text()
        .replace(
            "(docs/assets/",
            "(https://raw.githubusercontent.com/Tangent0308/samtok_edit_benchmark/v2branch/docs/assets/",
        )
    )
    readme = (
        "---\npretty_name: SAMTok Benchmark v2 - SA-1B 200\nlanguage:\n  - en\n  - zh\n---\n\n"
        + readme
    )
    operations.append(CommitOperationAdd(path_in_repo="README.md", path_or_fileobj=readme.encode()))
    pdf_name = "samtok_edit_benchmark_v2_all_200_cases.pdf"
    pdf_sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    receipt.update(pdf_name=pdf_name, pdf_sha256=pdf_sha, pdf_size_bytes=pdf.stat().st_size)
    operations.append(CommitOperationAdd(path_in_repo=pdf_name, path_or_fileobj=str(pdf)))
    public_meta = {k: v for k, v in receipt.items() if k not in {"status", "package", "archive"}}
    operations.append(
        CommitOperationAdd(
            path_in_repo="samtok_edit_benchmark_v2_review_20261010.json",
            path_or_fileobj=(json.dumps(public_meta, ensure_ascii=False, indent=2) + "\n").encode(),
        )
    )
    print(f"Uploading {size} bytes; SHA256 {sha}", flush=True)
    result = api.create_commit(
        repo_id=receipt["repo_id"],
        repo_type="dataset",
        parent_commit=before.sha,
        commit_message=f"feat: publish benchmark {release['release_version']} with instruction protocol 1.0",
        commit_description="Replace both existing review downloads atomically. Includes 200 sources, 785 tasks, protocol migration, offline full-case PDF and browser-verified mixed interactions.",
        operations=operations,
    )
    after = api.repo_info(receipt["repo_id"], repo_type="dataset", files_metadata=True)
    files = {f.rfilename: f for f in after.siblings}
    changed = {op.path_in_repo for op in operations}
    for name in REMOTE_NAMES:
        f = files[name]
        assert f.size == size and f.lfs and f.lfs.sha256 == sha, name
    assert files[pdf_name].lfs.sha256 == pdf_sha
    assert files[pdf_name].size == pdf.stat().st_size
    for name, old in previous.items():
        if name not in changed:
            if name == ".gitattributes" and files[name].blob_id != old.blob_id:
                # HF can append an exact-path LFS rule when adding the first PDF.
                old_text = Path(hf_hub_download(receipt["repo_id"], name, repo_type="dataset", revision=before.sha)).read_text()
                new_text = Path(hf_hub_download(receipt["repo_id"], name, repo_type="dataset", revision=after.sha)).read_text()
                assert new_text == old_text + f"{pdf_name} filter=lfs diff=lfs merge=lfs -text\n"
                receipt["automatic_pdf_lfs_rule_verified"] = True
                continue
            assert files[name].blob_id == old.blob_id and files[name].size == old.size, name
    receipt.update(
        status="passed",
        hf_revision=after.sha,
        hf_commit_url=result.commit_url,
        remote_sha256_verified=True,
        unrelated_remote_files_unchanged=True,
        remote_updated=True,
        pdf_remote_sha256_verified=True,
    )
    for p in [
        local_receipt,
        REPO / "data/v2/review_package.json",
        a.dataset_root / "benchmark/review_package.json",
    ]:
        p.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
