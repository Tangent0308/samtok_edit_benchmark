"""A single native stage, with immutable admissions and no automatic resampling."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.metadata
import os
from pathlib import Path
import subprocess
import time
import traceback

from PIL import Image

from samtok_benchmark.io import digest, sha256_file
from samtok_benchmark.ifbench.canvas import restore_output
from . import METHOD_COMMIT, MODELS
from .data import immutable, read, load_bundle


def source_identity():
    directory = Path(__file__).parent
    source = directory.parents[1]
    paths = list(directory.glob("*.py"))
    # These frozen IF-Bench modules implement the shared canvas and native baseline calls.
    for relative in ("samtok_benchmark/io.py", "samtok_benchmark/ifbench/canvas.py",
                     "samtok_benchmark/ifbench/fairness_dev_worker.py",
                     "samtok_benchmark/ifbench/dev_runner.py",
                     "samtok_benchmark/ifbench/smoke_suite.py",
                     "samtok_benchmark/ifbench/smoke_adapters.py",
                     "evaluation/protocol_audit/fairness_flux3_replan.py"):
        paths.append(source / relative)
    return {str(p.relative_to(source)): sha256_file(p) for p in sorted(paths)}


def verify_config(config):
    if config["schema"] != "mira.config.v1" or config["seed"] != 42:
        raise ValueError("Unknown configuration or seed")
    method = config["sitedit"]
    if (method["steps"], method["token_guidance"], method["pass1_max_new_tokens"]) != (40, 2.0, 512):
        raise ValueError("Changed SITEdit main-row configuration")
    source = Path(config["paths"]["sitedit_source"])
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if commit != METHOD_COMMIT:
        raise ValueError("SITEdit code revision mismatch")
    if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True).strip():
        raise ValueError("SITEdit dependency checkout is dirty")


def stages(model):
    if model == "sitedit":
        return ("tokens", "edit")
    return ("plan", "edit") if model in {"replan", "mirage"} else ("edit",)


def run(bundle, config_path, output, model, stage, case_ids, shard=0, shards=1):
    if model not in MODELS or stage not in stages(model) or not 0 <= shard < shards:
        raise ValueError("Invalid model, stage, or shard")
    config, index = read(config_path), load_bundle(bundle, case_ids)
    verify_config(config)
    selected = [i for i in index["cases"] if i["case_id"] in case_ids]
    if len(selected) != len(case_ids):
        raise ValueError("Unknown or duplicated case IDs")
    selected = selected[shard::shards]
    base = Path(output) / model
    backend = None
    counts = {"completed": 0, "failed": 0, "reused": 0}
    for item in selected:
        out = base / stage / item["case_id"]
        public = read(item["public"])
        previous_path = None
        if stage == "edit" and len(stages(model)) == 2:
            previous_path = base / stages(model)[0] / item["case_id"] / "result.json"
        identity = {"schema": "mira.result.v1", "model": model, "stage": stage,
                    "case_id": item["case_id"], "public_sha256": item["public_sha256"],
                    "bundle_digest": index["digest"], "config_digest": digest(config),
                    "geometry": item["geometry"], "source_code": source_identity(),
                    "previous_sha256": sha256_file(previous_path)
                    if previous_path and previous_path.exists() else None}
        identity["digest"] = digest(identity)
        result_path = out / "result.json"
        if result_path.exists():
            result = read(result_path)
            if result["identity"] != identity:
                raise ValueError(f"Cannot reuse changed scientific input: {out}")
            if result.get("output_image") and sha256_file(result["output_image"]) != result["output_sha256"]:
                raise ValueError("Existing output was modified")
            counts["reused"] += 1
            counts["failed"] += result["status"] == "failed"
            if result.get("fatal"):
                counts["fatal"] = True
                break
            continue
        out.mkdir(parents=True, exist_ok=True)
        # A claim without a terminal receipt requires inspection; never silently sample again.
        with (out / "ADMITTED.json").open("x") as f:
            import json
            json.dump({"identity": identity, "pid": os.getpid(),
                       "time": datetime.now(timezone.utc).isoformat()}, f)
        tick = time.monotonic()
        result = {"identity": identity, "status": "failed"}
        loading = False
        fatal = False
        try:
            previous = read(previous_path) if previous_path else None
            if previous and previous["status"] != "completed":
                raise RuntimeError("Previous native stage failed; no editor call made")
            if previous and (previous["identity"]["config_digest"] != digest(config) or
                             previous["identity"]["public_sha256"] != item["public_sha256"]):
                raise ValueError("Previous stage belongs to a different input or configuration")
            if backend is None:
                from .adapters import build
                load_tick = time.monotonic()
                loading = True
                backend = build(model, stage, config, base)
                loading = False
                result["load_seconds"] = time.monotonic() - load_tick
            import torch
            torch.manual_seed(42)
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
            inference_tick = time.monotonic()
            raw, detail = backend.run(public, out, previous["native"] if previous else None)
            torch.cuda.synchronize()
            result.update(detail)
            result["inference_seconds"] = time.monotonic() - inference_tick
            result["peak_gpu_allocated_bytes"] = torch.cuda.max_memory_allocated()
            if stage == "edit":
                if not isinstance(raw, Image.Image):
                    raise ValueError("Native editor returned no image")
                raw.save(out / "raw.png")
                restored = restore_output(raw, item["geometry"])
                restored.save(out / "output.png")
                result.update(raw_image=str(out / "raw.png"), raw_sha256=sha256_file(out / "raw.png"),
                              raw_size=list(raw.size), output_image=str(out / "output.png"),
                              output_sha256=sha256_file(out / "output.png"), output_size=list(restored.size))
            result["status"] = "completed"
            counts["completed"] += 1
        except Exception as error:
            result.update(error=repr(error), traceback=traceback.format_exc())
            counts["failed"] += 1
            fatal = loading or any(term in str(error).lower() for term in (
                "device-side assert", "illegal memory access", "cuda error", "out of memory"))
            result["fatal"] = fatal
        result["wall_seconds"] = time.monotonic() - tick
        result["packages"] = {k: importlib.metadata.version(k) for k in ("torch", "transformers", "Pillow")}
        immutable(result_path, result)
        print(f"{model}/{stage}/{item['case_id']}: {result['status']} "
              f"{result['wall_seconds']:.1f}s {result.get('error', '')}", flush=True)
        if fatal:
            counts["fatal"] = True
            break
    return counts
