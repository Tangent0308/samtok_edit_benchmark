"""Editor adapter boundary and resumable, content-bound output registry."""

from __future__ import annotations

import copy
import importlib
from pathlib import Path

from PIL import Image

from samtok_benchmark.io import digest, read_jsonl, sha256_file, write_jsonl
from samtok_benchmark.v2.inputs import verify_job


def run_editor(inputs: Path, output: Path, adapter: str, method: str, seed=0, config=None):
    module, sep, function = adapter.partition(":")
    if not sep or not method:
        raise ValueError("provide module:function adapter and a nonempty method name")
    edit = getattr(importlib.import_module(module), function)
    jobs = read_jsonl(inputs)
    if not jobs or len({j["job_id"] for j in jobs}) != len(jobs):
        raise ValueError("empty/duplicate input jobs")
    output.mkdir(parents=True, exist_ok=True)
    registry = output / "outputs.jsonl"
    old_rows = read_jsonl(registry) if registry.exists() else []
    records = {r["job_id"]: r for r in old_rows}
    if len(records) != len(old_rows) or set(records) - {j["job_id"] for j in jobs}:
        raise ValueError("registry has duplicate or unrelated jobs")
    try:
        for job in jobs:
            verify_job(job)
            run_key = digest(
                {
                    "input": job["input_digest"],
                    "adapter": adapter,
                    "method": method,
                    "seed": seed,
                    "config": config or {},
                }
            )
            old = records.get(job["job_id"])
            if old:
                if old["run_key"] != run_key:
                    raise ValueError("changed input/model/config; use a new output directory")
                if old["status"] == "ok":
                    if sha256_file(Path(old["output_image"])) != old["output_sha256"]:
                        raise ValueError("recorded model output was modified")
                    continue
            record = {
                k: job[k]
                for k in (
                    "job_id",
                    "case_id",
                    "variant",
                    "unit_ids",
                    "protocol",
                    "input_digest",
                    "manifest_sha256",
                )
            }
            record.update(
                method=method, adapter=adapter, seed=seed, config=config or {}, run_key=run_key
            )
            try:
                # Only the public projection is passed, never a case/target/gold mask object.
                image = edit(job=copy.deepcopy(job), seed=seed, config=copy.deepcopy(config or {}))
                if (
                    not isinstance(image, Image.Image)
                    or image.mode != "RGB"
                    or list(image.size) != job["source_size"]
                ):
                    raise ValueError("adapter must return an RGB PIL image at original source size")
                path = (output / "images" / f"{digest(job['job_id'])[:24]}.png").resolve()
                path.parent.mkdir(parents=True, exist_ok=True)
                image.save(path)
                record.update(status="ok", output_image=str(path), output_sha256=sha256_file(path))
            except Exception as exc:
                record.update(status="generation_error", error=f"{type(exc).__name__}: {exc}")
                records[job["job_id"]] = record
                raise
            records[job["job_id"]] = record
    finally:
        write_jsonl(registry, sorted(records.values(), key=lambda r: r["job_id"]))
    return list(records.values())
