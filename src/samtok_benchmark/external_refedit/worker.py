"""A single native stage over a shard of cases, with immutable admissions and no automatic resampling."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import traceback

from PIL import Image

from samtok_benchmark.io import digest, sha256_file
from samtok_benchmark.ifbench.canvas import restore_output
from . import METHOD_COMMIT, MODELS
from .data import immutable, read, load_bundle

# Only code that can change a generated image is part of a request's scientific identity; scoring, reporting and
# launch code may change without invalidating finished outputs.
GENERATION_FILES = ("__init__.py", "adapters.py", "data.py", "placement.py", "worker.py")
FROZEN_FILES = ("samtok_benchmark/io.py", "samtok_benchmark/ifbench/canvas.py",
                "samtok_benchmark/ifbench/fairness_dev_worker.py", "samtok_benchmark/ifbench/fairness_dev_revision.py",
                "samtok_benchmark/ifbench/dev_runner.py", "samtok_benchmark/ifbench/smoke_suite.py",
                "samtok_benchmark/ifbench/smoke_adapters.py", "evaluation/protocol_audit/fairness_flux3_replan.py")
MAIN_ROW = {"steps": 40, "token_guidance": 2.0, "seed": 42, "pass1_max_new_tokens": 512,
            "pass1_max_pixels": 2097152,
            "pass1_adapter": "/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/"
                             "pass1_localization_lora_formal_20261030_0939/runs/formal/step_2000",
            "dit_adapter": "/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/"
                           "qwen21_v3/runs/s2_4n_001/train/adapter_16000"}
FATAL_TERMS = ("device-side assert", "illegal memory access", "cuda error", "out of memory", "nvlink", "xid")


def source_identity():
    directory = Path(__file__).parent
    source = directory.parents[1]
    paths = [directory / name for name in GENERATION_FILES] + [source / name for name in FROZEN_FILES]
    return {str(p.relative_to(source)): sha256_file(p) for p in sorted(paths)}


def verify_config(config):
    if config["schema"] != "refedit.config.v1" or config["seed"] != 42:
        raise ValueError("Unknown configuration or seed")
    method = config["sitedit"]
    if any(method[key] != value for key, value in MAIN_ROW.items()):
        raise ValueError("Changed SITEdit main-row configuration")
    source = Path(config["paths"]["sitedit_source"])
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if commit != METHOD_COMMIT:
        raise ValueError("SITEdit code revision mismatch")
    if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True).strip():
        raise ValueError("SITEdit dependency checkout is dirty")
    main_row = read(source / "configs/ifbench/main_row.json")
    if {k: v for k, v in main_row.items() if k != "name"} != {k: v for k, v in method.items() if k != "name"}:
        raise ValueError("SITEdit configuration differs from the method's frozen main_row.json")


def stages(model):
    if model == "sitedit":
        return ("tokens", "edit")
    return ("plan", "edit") if model in {"replan", "mirage"} else ("edit",)


def _admit(out, identity):
    """Exclusive claim; False when an earlier claim exists without a terminal record (never resampled)."""
    out.mkdir(parents=True, exist_ok=True)
    try:
        with (out / "ADMITTED.json").open("x") as stream:
            json.dump({"identity": identity, "pid": os.getpid(), "host": socket.gethostname(),
                       "gpu": os.environ.get("CUDA_VISIBLE_DEVICES"),
                       "time": datetime.now(timezone.utc).isoformat()}, stream)
        return True
    except FileExistsError:
        return False


def run(bundle, config_path, output, model, stage, case_ids, shard=0, shards=1):
    if model not in MODELS or stage not in stages(model) or not 0 <= shard < shards:
        raise ValueError("Invalid model, stage, or shard")
    config, index = read(config_path), load_bundle(bundle, case_ids)
    verify_config(config)
    if index.get("dryrun") and Path(output).resolve().is_relative_to(Path(config["formal_results_root"]).resolve()):
        raise ValueError("A dry-run bundle (substitute images) must never write into the formal results root")
    selected = [i for i in index["cases"] if i["case_id"] in case_ids]
    if len(selected) != len(case_ids):
        raise ValueError("Unknown or duplicated case IDs")
    selected = selected[shard::shards]
    base = Path(output) / model
    backend = None
    counts = {"completed": 0, "failed": 0, "reused": 0, "unknown": 0, "missing_previous": 0}
    code = source_identity()
    for item in selected:
        out = base / stage / item["case_id"]
        public = read(item["public"])
        previous_path = None
        if stage == "edit" and len(stages(model)) == 2:
            previous_path = base / stages(model)[0] / item["case_id"] / "result.json"
            if not previous_path.exists():
                counts["missing_previous"] += 1
                print(f"{model}/{stage}/{item['case_id']}: no earlier-stage receipt; not started", flush=True)
                continue
        identity = {"schema": "refedit.result.v1", "model": model, "stage": stage,
                    "case_id": item["case_id"], "public_sha256": item["public_sha256"],
                    "bundle_digest": index["digest"], "config_digest": digest(config),
                    "geometry": item["geometry"], "source_code": code,
                    "previous_sha256": sha256_file(previous_path) if previous_path else None}
        identity["digest"] = digest(identity)
        result_path = out / "result.json"
        if result_path.exists():
            result = read(result_path)
            if result["identity"] != identity:
                raise ValueError(f"Cannot reuse changed scientific input: {out}")
            if result.get("output_image") and sha256_file(result["output_image"]) != result["output_sha256"]:
                raise ValueError("Existing output was modified")
            counts["reused"] += 1
            continue
        previous = read(previous_path) if previous_path else None
        upstream_failed = bool(previous and previous["status"] != "completed")
        if (out / "ADMITTED.json").exists():
            counts["unknown"] += 1
            print(f"{model}/{stage}/{item['case_id']}: admitted earlier without a terminal record; "
                  "left for inspection, not resampled", flush=True)
            continue
        if backend is None and not upstream_failed:
            # Load before any admission: a load failure samples nothing and leaves no per-case record.
            import torch
            from .adapters import build
            load_tick = time.monotonic()
            try:
                backend = build(model, stage, config, base)
                torch.cuda.synchronize()
            except Exception as error:
                failure = {"model": model, "stage": stage, "shard": [shard, shards], "error": repr(error),
                           "traceback": traceback.format_exc(), "host": socket.gethostname(),
                           "gpu": os.environ.get("CUDA_VISIBLE_DEVICES"),
                           "time": datetime.now(timezone.utc).isoformat()}
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                immutable(base / stage / "_load_failures" / f"{stamp}-{os.getpid()}.json", failure)
                print(f"{model}/{stage}: model load failed: {error!r}", flush=True)
                counts["fatal"] = True
                break
            load_seconds = time.monotonic() - load_tick
        else:
            load_seconds = None
        if not _admit(out, identity):
            counts["unknown"] += 1
            continue
        tick = time.monotonic()
        result = {"identity": identity, "status": "failed", "host": socket.gethostname(),
                  "gpu": os.environ.get("CUDA_VISIBLE_DEVICES"),
                  "started": datetime.now(timezone.utc).isoformat()}
        if load_seconds is not None:
            result["load_seconds"] = load_seconds
        fatal = False
        try:
            if upstream_failed:
                raise RuntimeError("Previous native stage failed; no editor call made")
            if previous and (previous["identity"]["config_digest"] != digest(config) or
                             previous["identity"]["public_sha256"] != item["public_sha256"]):
                raise ValueError("Previous stage belongs to a different input or configuration")
            import torch
            torch.manual_seed(42)
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
            inference_tick = time.monotonic()
            raw, detail = backend.run(public, out, previous["native"] if previous else None)
            torch.cuda.synchronize()
            result["inference_seconds"] = time.monotonic() - inference_tick
            result.update(detail)
            result["peak_gpu_allocated_bytes"] = torch.cuda.max_memory_allocated()
            result["peak_gpu_reserved_bytes"] = torch.cuda.max_memory_reserved()
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
            fatal = any(term in str(error).lower() for term in FATAL_TERMS)
            result["fatal"] = fatal
        result["wall_seconds"] = time.monotonic() - tick
        result["packages"] = {k: importlib.metadata.version(k) for k in ("torch", "transformers", "Pillow")}
        immutable(result_path, result)
        print(f"{model}/{stage}/{item['case_id']}: {result['status']} {result['wall_seconds']:.1f}s "
              f"{result.get('error', '')}", flush=True)
        if fatal:
            counts["fatal"] = True
            break
    return counts
