"""Model-independent adapter runner with exact input/output provenance."""

from __future__ import annotations

import importlib
from pathlib import Path

from PIL import Image

from samtok_benchmark.inputs import SETTINGS, verify_job
from samtok_benchmark.io import digest, read_jsonl, sha256_file, write_jsonl


def run_editor(
    inputs: Path,
    output: Path,
    adapter: str,
    method: str,
    seed: int = 0,
    settings=SETTINGS,
    adapter_config: dict | None = None,
) -> list[dict]:
    module_name, sep, function_name = adapter.partition(":")
    if not sep:
        raise ValueError("adapter must be importable_module:function")
    edit = getattr(importlib.import_module(module_name), function_name)
    jobs = [j for j in read_jsonl(inputs) if j["setting"] in settings]
    if not jobs:
        raise ValueError("no selected jobs")
    output.mkdir(parents=True, exist_ok=True)
    registry = output / "outputs.jsonl"
    previous = {}
    if registry.exists():
        previous = {(r["case_id"], r["setting"]): r for r in read_jsonl(registry)}
        if len(previous) != len(read_jsonl(registry)):
            raise ValueError("duplicate output registry entries")
    records = dict(previous)
    try:
        for job in jobs:
            verify_job(job)
            key = (job["case_id"], job["setting"])
            run_key = digest(
                {
                    "input": job["input_digest"],
                    "method": method,
                    "adapter": adapter,
                    "config": adapter_config or {},
                    "seed": seed,
                }
            )
            old = records.get(key)
            if old:
                if old.get("run_key") != run_key:
                    raise ValueError(
                        "existing outputs use different inputs/config; use a new output directory"
                    )
                if (
                    old["status"] == "ok"
                    and sha256_file(Path(old["output_image"])) == old["output_sha256"]
                ):
                    continue
            record = {
                "case_id": job["case_id"],
                "setting": job["setting"],
                "method": method,
                "protocol": job["protocol"],
                "input_digest": job["input_digest"],
                "manifest_sha256": job["manifest_sha256"],
                "seed": seed,
                "adapter": adapter,
                "adapter_config": adapter_config or {},
                "run_key": run_key,
            }
            try:
                image = edit(job=job, seed=seed, config=adapter_config or {})
                if not isinstance(image, Image.Image) or list(image.size) != job["source_size"]:
                    raise ValueError("adapter must return a PIL image at the original source size")
                if image.mode != "RGB":
                    raise ValueError("adapter must explicitly composite/convert its output to RGB")
                path = output / "images" / job["setting"] / f"{job['eval_index']:04d}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                image.save(path)
                record.update(
                    status="ok", output_image=str(path.resolve()), output_sha256=sha256_file(path)
                )
            except Exception as exc:
                record.update(status="generation_error", error=f"{type(exc).__name__}: {exc}")
                records[key] = record
                raise
            records[key] = record
    finally:
        write_jsonl(registry, sorted(records.values(), key=lambda r: (r["setting"], r["case_id"])))
    return list(records.values())
