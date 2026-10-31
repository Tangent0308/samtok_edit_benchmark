"""Two authorized local diagnostic calls, separate from benchmark outcomes.

Launch only through the resource gate after the local training processes exit.
The first call is an existing S1 control; the second is the same image's failed
dual-image S2-point request. Stop at the first failure, never resample or Judge.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import inspect
import os
from pathlib import Path
import socket
import time
import traceback

from PIL import Image

from samtok_benchmark.io import sha256_file, write_json
from samtok_benchmark.ifbench.fairness_dev_plan import load_plan, read, verify_task

KEYS = ("qwen21/S1/v2-sa_607902", "qwen21/S2-point/v2-sa_607902")


def utc():
    return datetime.now(timezone.utc).isoformat()


def run(probe_plan):
    config = read(probe_plan)
    out = Path(config["output_directory"])
    if socket.gethostname() != config["hostname"]:
        raise ValueError("This diagnostic is authorized only on the specified local host")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != config["gpu_uuid"]:
        raise ValueError("Diagnostic GPU differs from the resource-gated GPU")
    grant = read(out.parent / "RESOURCE_GRANTED.json")
    if grant["probe_plan_sha256"] != sha256_file(Path(probe_plan)):
        raise ValueError("Resource grant belongs to another diagnostic plan")
    if grant.get("status") != "ready" or grant.get("training_pids_remaining"):
        raise ValueError("Training resources have not been released")
    if time.time() - grant["checked_at_epoch"] > 120:
        raise ValueError("Resource grant expired before diagnostic startup")
    for path, expected in config["source_sha256"].items():
        if sha256_file(Path(path)) != expected:
            raise ValueError(f"Diagnostic source changed: {path}")
    for path, expected in config["baseline_sha256"].items():
        if sha256_file(Path(path)) != expected:
            raise ValueError(f"Registered diagnostic baseline changed: {path}")
    if out.exists():
        raise ValueError("Never overwrite or automatically resume a diagnostic attempt")
    parent_path = Path(config["parent_plan"])
    if sha256_file(parent_path) != config["parent_plan_sha256"]:
        raise ValueError("Parent plan changed")
    parent = load_plan(parent_path, helper_root=parent_path.parent / "repo")
    tasks = {t["key"]: t for t in parent["tasks"]}
    prepared = []
    for key in KEYS:
        task = tasks[key]
        request, public = verify_task(parent, task)
        if (
            request["parameters"]
            != {
                "num_inference_steps": 40,
                "true_cfg_scale": 1.0,
                "output_resolution": 2048,
                "use_kv_cache": True,
            }
            or request["seed"] != 42
        ):
            raise ValueError("The approved native request parameters changed")
        prepared.append((task, request, public))
    out.mkdir(parents=True)
    write_json(
        out / "STARTED.json",
        {
            "time": utc(),
            "hostname": socket.gethostname(),
            "pid": os.getpid(),
            "scope": "local engineering diagnosis only; no benchmark replacement or Judge",
            "keys": list(KEYS),
            "maximum_new_inference_calls": 2,
            "probe_plan_sha256": sha256_file(Path(probe_plan)),
        },
    )

    import torch
    from samtok_benchmark.ifbench import smoke_adapters as adapters

    torch.set_num_threads(4)
    adapters.MODELS = Path(parent["paths"]["models"])
    adapters.SOURCES = Path(parent["paths"]["sources"])
    load_start = time.monotonic()
    write_json(out / "status.json", {"status": "loading", "time": utc(), "new_inference_calls": 0})
    adapter = None
    hooks = []
    results = []
    observations = []
    counters = {"transformer": 0, "vae_decoder": 0}
    admitted_calls = 0
    try:
        adapter = adapters.Qwen21(out, memory_policy="model_cpu_offload")
        adapter.configuration.update(prepared[0][1]["parameters"])
        pipe = adapter.pipe

        def memory(stage):
            torch.cuda.synchronize()
            return {
                "stage": stage,
                "time": utc(),
                "gpu_allocated_bytes": torch.cuda.memory_allocated(),
                "gpu_reserved_bytes": torch.cuda.memory_reserved(),
                "component_devices": {
                    name: str(next(getattr(pipe, name).parameters()).device)
                    for name in ("text_encoder", "transformer", "vae")
                },
            }

        def after_transformer(module, args, output):
            counters["transformer"] += 1
            if counters["transformer"] in (1, 40):
                observations.append(memory(f"after_transformer_{counters['transformer']}"))

        def before_decoder(module, args):
            counters["vae_decoder"] += 1
            # This child module executes after the native VAE decode hook has
            # offloaded its predecessor. Hooks only record metadata, no tensors.
            observations.append(memory("vae_decoder_entry"))

        hooks.append(pipe.transformer.register_forward_hook(after_transformer))
        hooks.append(pipe.vae.decoder.register_forward_pre_hook(before_decoder))
        write_json(
            out / "load.json",
            {
                "status": "loaded",
                "seconds": time.monotonic() - load_start,
                "configuration": adapter.configuration,
                "pipeline_file": inspect.getfile(type(pipe)),
                "torch": torch.__version__,
                "gpu": torch.cuda.get_device_name(0),
            },
        )
        for task, request, public in prepared:
            case = out / task["setting"] / task["case_id"]
            case.mkdir(parents=True)
            write_json(case / "request.json", request)
            write_json(case / "started.json", {"time": utc(), "key": task["key"], "seed": 42})
            counters.update(transformer=0, vae_decoder=0)
            observations.clear()
            torch.cuda.reset_peak_memory_stats()
            started = time.monotonic()
            result = {
                "key": task["key"],
                "diagnostic_only": True,
                "request_sha256": task["request_sha256"],
                "inference_api_calls": 1,
                "memory_policy": "model_cpu_offload",
                "parameters": request["parameters"],
            }
            try:
                admitted_calls += 1
                raw, detail = adapter.generate(request, case)
                raw.save(case / "raw.png")
                raw.convert("RGB").resize(
                    tuple(public["source"]["size"]), Image.Resampling.LANCZOS
                ).save(case / "output.png")
                result.update(
                    **detail,
                    status="generated",
                    raw_size=list(raw.size),
                    raw_image=str(case / "raw.png"),
                    raw_sha256=sha256_file(case / "raw.png"),
                    output_image=str(case / "output.png"),
                    output_sha256=sha256_file(case / "output.png"),
                )
                previous = read(task["result_path"])
                if task["setting"] == "S1":
                    if previous["status"] != "generated":
                        raise ValueError("S1 control no longer has the registered native output")
                    import numpy as np

                    with Image.open(previous["raw_image"]) as baseline:
                        a = np.asarray(baseline.convert("RGB"), dtype=np.int16)
                    c = np.asarray(raw.convert("RGB"), dtype=np.int16)
                    same_shape = a.shape == c.shape
                    result["control_comparison"] = {
                        "baseline_result": task["result_path"],
                        "same_shape": same_shape,
                        "identical_png_sha": result["raw_sha256"] == previous["raw_sha256"],
                        "pixel_identical": bool(np.array_equal(a, c)),
                        "max_abs_pixel_difference": int(np.abs(a - c).max())
                        if same_shape
                        else None,
                        "mean_abs_pixel_difference": float(np.abs(a - c).mean())
                        if same_shape
                        else None,
                    }
            except Exception as error:
                result.update(status="failed", error=repr(error), traceback=traceback.format_exc())
            finally:
                result.update(
                    wall_seconds=time.monotonic() - started,
                    peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated(),
                    peak_gpu_reserved_bytes=torch.cuda.max_memory_reserved(),
                    transformer_forward_calls=counters["transformer"],
                    vae_decoder_calls=counters["vae_decoder"],
                    observations=list(observations),
                )
                write_json(case / "result.json", result)
                results.append(result)
                write_json(
                    out / "status.json",
                    {
                        "time": utc(),
                        "status": "running",
                        "completed": len(results),
                        "last_key": task["key"],
                        "last_status": result["status"],
                    },
                )
            if result["status"] != "generated":
                break  # Failed native cache/hook state must never be reused for another sample.
        success = len(results) == 2 and all(r["status"] == "generated" for r in results)
        write_json(
            out / "PROBE_FINISHED.json",
            {
                "time": utc(),
                "status": "completed" if success else "failed",
                "diagnostic_only": True,
                "new_inference_calls": admitted_calls,
                "outcomes": [
                    {k: r.get(k) for k in ("key", "status", "error", "control_comparison")}
                    for r in results
                ],
                "formal_results_replaced": False,
                "judge_calls": 0,
            },
        )
        return 0 if success else 1
    except Exception as error:
        write_json(
            out / "PROBE_FINISHED.json",
            {
                "time": utc(),
                "status": "failed",
                "error": repr(error),
                "traceback": traceback.format_exc(),
                "new_inference_calls": admitted_calls,
                "formal_results_replaced": False,
                "judge_calls": 0,
            },
        )
        return 1
    finally:
        for hook in hooks:
            hook.remove()
        # The process exits after this run. In particular, a decoder OOM is
        # never followed by another sample using residual native feature caches.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    raise SystemExit(run(parser.parse_args().plan))
