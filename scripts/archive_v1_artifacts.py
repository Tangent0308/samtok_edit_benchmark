"""Copy recorded v1 artifacts to persistent storage with per-file SHA256 checks.

Default is a read-only plan. Existing destinations are verified, never replaced.
Frozen records keep their original content; path_map.json locates archived copies.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def selected_files(artifact: dict) -> list[tuple[Path, str]]:
    source = Path(artifact["source"])
    if source.is_file():
        return [(source, source.name)]
    if not source.is_dir():
        raise FileNotFoundError(source)
    result = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source).as_posix()
        includes = artifact.get("include", ["*"])
        excludes = artifact.get("exclude", [])
        if not any(fnmatch.fnmatchcase(relative, item) for item in includes):
            continue
        if any(fnmatch.fnmatchcase(relative, item) for item in excludes):
            continue
        if path.is_symlink():
            raise ValueError(f"symlink requires an explicit archival policy: {path}")
        destination = artifact.get("rename", {}).get(relative, relative)
        if Path(destination).is_absolute() or ".." in Path(destination).parts:
            raise ValueError(f"unsafe destination: {destination}")
        result.append((path, destination))
    if len({relative for _, relative in result}) != len(result):
        raise ValueError(f"duplicate destinations in {artifact['id']}")
    return result


def archive(artifact: dict, workers: int, apply: bool) -> dict:
    files = selected_files(artifact)
    destination = Path(artifact["destination"])
    single = Path(artifact["source"]).is_file()
    size = sum(path.stat().st_size for path, _ in files)
    if not apply:
        return {"id": artifact["id"], "files": len(files), "bytes": size}
    destination.parent.mkdir(parents=True, exist_ok=True)
    if single:
        source = files[0][0]
        expected = digest(source)
        if artifact.get("sha256", expected) != expected:
            raise ValueError(f"source archive hash mismatch: {source}")
        if destination.exists():
            if digest(destination) != expected:
                raise ValueError(f"existing destination differs: {destination}")
        else:
            fd, name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
            os.close(fd)
            staging = Path(name)
            try:
                shutil.copyfile(source, staging)
                if digest(staging) != expected:
                    raise ValueError(f"copy hash mismatch: {source}")
                if destination.exists():
                    raise FileExistsError(destination)
                os.rename(staging, destination)
            finally:
                staging.unlink(missing_ok=True)
        return {"id": artifact["id"], "files": 1, "bytes": size, "sha256": expected}

    existing = destination.exists()
    if existing and not (destination / "ARCHIVE_MANIFEST.jsonl").is_file():
        raise FileExistsError(f"unmanaged existing directory: {destination}")
    staging = destination if existing else Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )

    def copy_and_check(item: tuple[Path, str]) -> dict:
        source, relative = item
        target = staging / relative
        expected = digest(source)
        if not existing:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        if not target.is_file() or digest(target) != expected:
            raise ValueError(f"archival hash mismatch: {target}")
        return {"source": str(source), "path": relative,
                "bytes": source.stat().st_size, "sha256": expected}

    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            records = list(executor.map(copy_and_check, files))
        serialized = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
        manifest = staging / "ARCHIVE_MANIFEST.jsonl"
        if existing:
            if manifest.read_text() != serialized:
                raise ValueError(f"existing archive manifest differs: {destination}")
        else:
            manifest.write_text(serialized)
            (staging / "ARCHIVE_INFO.json").write_text(json.dumps({
                "artifact_id": artifact["id"], "source": artifact["source"],
                "destination": str(destination), "files": len(files), "bytes": size,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "records_policy": "copied byte-for-byte; historical absolute paths preserved",
            }, ensure_ascii=False, indent=2) + "\n")
            if destination.exists():
                raise FileExistsError(destination)
            os.rename(staging, destination)
        return {"id": artifact["id"], "files": len(files), "bytes": size,
                "manifest_sha256": digest(destination / "ARCHIVE_MANIFEST.jsonl")}
    finally:
        if not existing and staging.exists():
            shutil.rmtree(staging)


def verify_archive(artifact: dict, workers: int) -> dict:
    """Verify persistent files without depending on the old temporary sources."""
    destination = Path(artifact["destination"])
    if destination.is_file():
        actual = digest(destination)
        if actual != artifact["sha256"]:
            raise ValueError(f"archive checksum mismatch: {destination}")
        return {"id": artifact["id"], "files": 1,
                "bytes": destination.stat().st_size, "sha256": actual}
    manifest = destination / "ARCHIVE_MANIFEST.jsonl"
    records = [json.loads(line) for line in manifest.read_text().splitlines()]

    def check(record: dict) -> None:
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe archive entry: {relative}")
        target = destination / relative
        if target.stat().st_size != record["bytes"] or digest(target) != record["sha256"]:
            raise ValueError(f"archive checksum mismatch: {target}")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(check, records))
    return {"id": artifact["id"], "files": len(records),
            "bytes": sum(record["bytes"] for record in records),
            "manifest_sha256": digest(manifest)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("data/v1/artifacts.json"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="copy and verify; default only lists")
    mode.add_argument("--verify-only", action="store_true", help="check copies without old sources")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--artifact", action="append", help="limit to a registry artifact ID")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    registry = json.loads(args.registry.read_text())
    if args.artifact:
        unknown = set(args.artifact) - {item["id"] for item in registry["artifacts"]}
        if unknown:
            parser.error(f"unknown artifact IDs: {sorted(unknown)}")
    results = []
    for artifact in registry["artifacts"]:
        if args.artifact and artifact["id"] not in args.artifact:
            continue
        verb = "Verifying" if args.verify_only else "Archiving" if args.apply else "Planning"
        print(f"{verb} {artifact['id']}", flush=True)
        result = (verify_archive(artifact, args.workers) if args.verify_only
                  else archive(artifact, args.workers, args.apply))
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({
            "status": "verified" if args.apply or args.verify_only else "plan",
            "registry_sha256": digest(args.registry), "artifacts": results,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
