"""Immutable per-request stages with explicit recurrent-image dependencies and GPU ownership gates."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import traceback

from PIL import Image

from samtok_benchmark.io import digest, sha256_file
from samtok_benchmark.ifbench.canvas import restore_output
from samtok_benchmark.external_refedit.worker import (
    FATAL_TERMS,
    FROZEN_FILES,
    stages,
    verify_config as verify_ref_config,
)
from . import MODELS
from .bundle import asset, load_bundle, make_public, requests, verify_public
from .data import immutable, read

REPO = Path(__file__).resolve().parents[3]
STOP = False


def on_stop(signum, frame):
    global STOP
    STOP = True


def verify_config(config):
    if config["schema"] != "magicbrush.config.v1":
        raise ValueError("Wrong evaluation configuration")
    verify_ref_config({**config, "schema": "refedit.config.v1"})
    frozen = read(REPO / "configs/external/magicbrush.json")
    for key in ["seed", "sitedit", "model_specifications", "local_gpu_policy", "metrics"]:
        if config[key] != frozen[key]:
            raise ValueError(f"Frozen configuration changed: {key}")


def gpu_gate(config, cards, *, check_memory=True):
    policy = config["local_gpu_policy"]
    local = socket.gethostname() == policy["restricted_host"]
    if local:
        if not set(cards) <= set(policy["allowed"]):
            raise ValueError("Local GPUs 0–3 are forbidden")
        if datetime.now(timezone.utc) < datetime.fromisoformat(policy["not_before_utc"]):
            raise ValueError("Local GPU use is forbidden before 2026-11-05 19:00 UTC")
        limit = policy["max_existing_used_mib"]
    else:
        if os.environ.get("ARNOLD_WORKER_NUM") != "1":
            raise ValueError(
                "Only an explicitly configured single-node ARNOLD job is supported remotely"
            )
        limit = 8192
    if not check_memory:
        return
    for card in cards:
        line = (
            subprocess.check_output(
                [
                    "nvidia-smi",
                    "-i",
                    str(card),
                    "--query-gpu=memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=20,
            )
            .strip()
            .split(",")
        )
        used, total = map(int, line)
        if used > limit or total - used < 70000:
            raise ValueError(
                f"GPU {card} is occupied: {used} MiB; existing jobs will not be touched"
            )


def source_identity():
    names = ["__init__.py", "adapters.py", "bundle.py", "worker.py"]
    paths = [Path(__file__).parent / n for n in names]
    paths += [REPO / "src" / n for n in FROZEN_FILES]
    paths += [
        REPO / "src/samtok_benchmark/external_refedit" / n
        for n in ["adapters.py", "placement.py", "data.py"]
    ]
    return {str(p.relative_to(REPO)): sha256_file(p) for p in sorted(set(paths))}


def result_path(output, model, stage, key):
    return Path(output) / "runs" / model / stage / key / "result.json"


def resolve_public(item, output, model):
    if item["mode"] == "independent":
        if sha256_file(item["public"]) != item["public_sha256"]:
            raise ValueError("Independent public request changed")
        public = read(item["public"])
        verify_public(public)
        return public, item["geometry"], None
    previous_path = result_path(output, model, "edit", item["previous_key"])
    if not previous_path.exists():
        return None, None, {"status": "pending_dependency", "path": str(previous_path)}
    previous = read(previous_path)
    dependency = {
        "path": str(previous_path),
        "sha256": sha256_file(previous_path),
        "status": previous["status"],
    }
    if previous["status"] != "completed":
        return None, None, dependency
    if sha256_file(previous["output_image"]) != previous["output_sha256"]:
        raise ValueError("Previous generated image changed")
    public_row = {k: item[k] for k in ("case_id", "session_id", "turn", "instruction")}
    directory = Path(output) / "public_recurrent" / model / item["key"]
    if (directory / "public.json").exists():
        binding = read(directory / "DEPENDENCY.json")
        if binding != dependency:
            raise ValueError("Recurrent source dependency changed")
        public = read(directory / "public.json")
        verify_public(public)
        return public, read(directory / "geometry.json"), dependency
    p = make_public(
        public_row,
        asset(previous["output_image"]),
        item["track"],
        directory,
        item["canonical_mask"],
    )
    immutable(directory / "DEPENDENCY.json", dependency)
    return read(p["public"]), p["geometry"], dependency


def run_stage(bundle, config_path, output, model, stage, session_ids, wave, smoke=False):
    if model not in MODELS or stage not in stages(model):
        raise ValueError("Invalid native stage")
    config = read(config_path)
    verify_config(config)
    cards = [int(x) for x in os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",") if x]
    if len(cards) != 1:
        raise ValueError("A native worker must see exactly one assigned GPU")
    # Before importing any native model; never relies solely on a launcher-side check.
    gpu_gate(config, cards)
    signal.signal(signal.SIGUSR1, on_stop)
    signal.signal(signal.SIGTERM, on_stop)
    index = load_bundle(bundle)
    selected = [
        i
        for i in requests(index, session_ids, smoke)
        if wave == -1 or (0 if i["mode"] == "independent" else i["turn"]) == wave
    ]
    codes = source_identity()
    counts = {"completed": 0, "reused": 0, "failed": 0, "unknown": 0, "pending_dependency": 0}
    backend = None
    for item in selected:
        if STOP:
            break
        public, geometry, dependency = resolve_public(item, output, model)
        if dependency and dependency["status"] == "pending_dependency":
            counts["pending_dependency"] += 1
            continue
        prior_path = None
        if stage == "edit" and len(stages(model)) == 2:
            prior_path = result_path(output, model, stages(model)[0], item["key"])
            if not prior_path.exists():
                counts["pending_dependency"] += 1
                continue
        prior = read(prior_path) if prior_path else None
        if prior and (
            prior["identity"]["config_digest"] != digest(config)
            or prior["identity"]["source_code"] != codes
            or prior["identity"]["public_digest"] != (public["input_digest"] if public else None)
            or prior["identity"]["bundle_digest"] != index["digest"]
        ):
            raise ValueError(
                "Prior stage belongs to a different public input or frozen configuration"
            )
        identity = {
            "schema": "magicbrush.result.v1",
            "model": model,
            "stage": stage,
            "key": item["key"],
            "case_id": item["case_id"],
            "bundle_digest": index["digest"],
            "config_digest": digest(config),
            "public_digest": public["input_digest"] if public else None,
            "geometry": geometry,
            "source_code": codes,
            "recurrent_dependency": dependency,
            "previous_stage_sha256": sha256_file(prior_path) if prior_path else None,
        }
        identity["digest"] = digest(identity)
        path = result_path(output, model, stage, item["key"])
        out = path.parent
        if path.exists():
            result = read(path)
            if result["identity"] != identity:
                raise ValueError(f"Completed request input changed: {path}")
            for kind in ["raw", "output"]:
                if (
                    result.get(kind + "_image")
                    and sha256_file(result[kind + "_image"]) != result[kind + "_sha256"]
                ):
                    raise ValueError("Completed image bytes changed")
            counts["reused"] += 1
            continue
        if (out / "ADMITTED.json").exists():
            counts["unknown"] += 1
            continue
        upstream_failed = (prior and prior["status"] != "completed") or (
            dependency and dependency["status"] != "completed"
        )
        load_seconds = None
        if backend is None and not upstream_failed:
            import torch
            from .adapters import build

            tick = time.monotonic()
            try:
                backend = build(model, stage, config, Path(output) / "runs" / model)
                torch.cuda.synchronize()
            except Exception as error:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                immutable(
                    Path(output) / "load_failures" / f"{model}-{stage}-{stamp}-{os.getpid()}.json",
                    {
                        "model": model,
                        "stage": stage,
                        "error": repr(error),
                        "traceback": traceback.format_exc(),
                        "gpu": cards,
                        "host": socket.gethostname(),
                        "no_request_admitted": True,
                    },
                )
                counts["fatal"] = True
                break
            load_seconds = time.monotonic() - tick
        if STOP:
            break
        out.mkdir(parents=True, exist_ok=True)
        try:
            with (out / "ADMITTED.json").open("x") as f:
                json.dump(
                    {
                        "identity": identity,
                        "host": socket.gethostname(),
                        "pid": os.getpid(),
                        "gpu": cards,
                        "time": datetime.now(timezone.utc).isoformat(),
                    },
                    f,
                )
        except FileExistsError:
            counts["unknown"] += 1
            continue
        tick = time.monotonic()
        result = {
            "identity": identity,
            "status": "failed",
            "host": socket.gethostname(),
            "gpu": cards,
            "started": datetime.now(timezone.utc).isoformat(),
            "load_seconds": load_seconds,
        }
        try:
            if upstream_failed:
                raise RuntimeError(
                    "Native prior stage or recurrent generation failed; no GT substitution"
                )
            import torch

            torch.manual_seed(42)
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
            inference_tick = time.monotonic()
            raw, detail = backend.run(public, out, prior["native"] if prior else None)
            torch.cuda.synchronize()
            result.update(inference_seconds=time.monotonic() - inference_tick, **detail)
            result["peak_gpu_allocated_bytes"] = torch.cuda.max_memory_allocated()
            result["peak_gpu_reserved_bytes"] = torch.cuda.max_memory_reserved()
            if stage == "edit":
                if not isinstance(raw, Image.Image):
                    raise ValueError("Editor returned no image")
                raw.save(out / "raw.png")
                restored = restore_output(raw, geometry)
                restored.save(out / "output.png")
                result.update(
                    raw_image=str(out / "raw.png"),
                    raw_sha256=sha256_file(out / "raw.png"),
                    raw_size=list(raw.size),
                    output_image=str(out / "output.png"),
                    output_sha256=sha256_file(out / "output.png"),
                    output_size=list(restored.size),
                )
            result["status"] = "completed"
            counts["completed"] += 1
        except Exception as error:
            result.update(
                error=repr(error),
                traceback=traceback.format_exc(),
                fatal=any(t in str(error).lower() for t in FATAL_TERMS),
            )
            counts["failed"] += 1
        result["wall_seconds"] = time.monotonic() - tick
        result["packages"] = {
            k: importlib.metadata.version(k) for k in ["torch", "transformers", "Pillow"]
        }
        immutable(path, result)
        print(
            f"{model}/{stage}/{item['key']}: {result['status']} {result['wall_seconds']:.2f}s {result.get('error', '')}",
            flush=True,
        )
        if result.get("fatal"):
            counts["fatal"] = True
            break
    counts["stopped"] = STOP
    return counts
