"""One resident stage per GPU; no Judge and no modifications to scored outputs."""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
from pathlib import Path
import signal
import socket
import sys
import tempfile
import time
import traceback

from .common import (
    cached_reads,
    identity,
    jobs,
    load_plan,
    read,
    result_dir,
    save,
    sha,
    stages,
    terminal,
)


class SitTokens:
    """Same native Pass1/codec calls, excluding visualization-only mask decoding."""

    def __init__(self, config, setting):
        from samtok_edit21.evaluation.ifbench import Pass1Models

        self.config, self.setting = config, setting
        self.models = Pass1Models(config)
        if setting == "S1":
            self.models.grounder
        else:
            self.models.codec

    def run(self, public, directory, previous=None):
        import numpy as np
        from PIL import Image
        from samtok_edit21.pass1.evaluation.ifbench import adapt
        from samtok_edit21.pass1.protocol import valid_span

        image = Image.open(public["source"]["path"]).convert("RGB")
        cache, units = {}, {}
        calls = {"grounder_requests": 0, "codec_encode": 0, "diagnostic_decode": 0}
        for u in public["units"]:
            units[u["id"]] = {"id": u["id"], "token": None, "source": None}
            if u["locator"] == "mask":
                mask = np.asarray(Image.open(u["region"]["path"]).convert("L")) > 0
                span = self.models.codec.encode(image.convert("RGBA"), [mask])[0][0]
                cache[(public["source"]["sha256"], u["region"]["sha256"])] = span
                units[u["id"]].update(token=span, source="codec")
                calls["codec_encode"] += 1
        answer = None
        if any(u["locator"] != "mask" for u in public["units"]):
            request = adapt(public, cache)
            answer = self.models.grounder.ground(
                image, request, max_new_tokens=self.config["pass1_max_new_tokens"]
            )
            calls["grounder_requests"] = 1
            for u in public["units"]:
                if u["locator"] == "mask":
                    continue
                span = answer["parsed"]["spans"].get(u["id"])
                valid = bool(span and valid_span(span))
                units[u["id"]].update(
                    token=span if valid else None, source="pass1" if valid else "fallback_text"
                )
        result = {
            "units": list(units.values()),
            "answer": answer,
            "fallback_units": sum(u["token"] is None for u in units.values()),
        }
        return None, result, calls


class SitEditor:
    def __init__(self, config):
        from samtok_edit21.models.adapters import load_grounding_adapter
        from samtok_edit21.models.codec import load_codec
        from samtok_edit21.models.pipeline import load_pipeline

        self.config = config
        self.pipe = load_pipeline(config["qwen"], config["samtok"], device="cuda")
        self.codec = load_codec(config["samtok"], "cuda")
        load_grounding_adapter(self.pipe, self.codec, config["dit_adapter"])
        self.pipe.eval()

    def run(self, public, directory, previous=None):
        import torch
        from PIL import Image
        from samtok_edit21.data.protocol import strip_tokens
        from samtok_edit21.evaluation.ifbench import pass2_prompt
        from samtok_edit21.models.pipeline import edit

        spans = {u["id"]: u["token"] for u in previous["units"] if u["token"]}
        prompt = pass2_prompt(public, spans)
        guided = bool(spans) and self.config["token_guidance"] != 1.0
        w, h = public["source"]["size"]
        kwargs = dict(
            num_inference_steps=self.config["steps"],
            seed=42,
            width=w,
            height=h,
            cfg_scale=self.config["token_guidance"] if guided else 1.0,
            use_kv_cache=True,
            pass2_te="raw",
            mode="inline" if spans else "direct",
        )
        if guided:
            kwargs["negative_prompt"] = strip_tokens(prompt)
        image = Image.open(public["source"]["path"]).convert("RGBA")
        torch._dynamo.reset()  # Required by the frozen request semantics; included in timing.
        raw, detail = edit(self.pipe, prompt, [image], **kwargs)
        return (
            raw,
            {"prompt": prompt, "parameters": kwargs, "native": detail},
            {
                "inference_api_calls": 1,
                "expected_dit_forwards": self.config["steps"] * (2 if guided else 1),
            },
        )


class Baseline:
    def __init__(self, model, stage, config, directory):
        from samtok_benchmark.ifbench.fairness_dev_worker import NativeBackend

        class ProfileBackend(NativeBackend):
            def _trace_mirage(self):
                # Preserve the original spatial hints and native chat arguments.
                # Only the diagnostic serialization of images/JSON is omitted.
                chat, messages = self.vlm.chat, self.vlm.grounding_messages

                def grounding(image, phrase, mode):
                    value = messages(image, phrase, mode)
                    hint = image.info.get("ifbench_spatial_hint", "")
                    if hint:
                        value[-1]["content"].append({"type": "text", "text": hint})
                    return value

                def recorded(batch, max_new_tokens=512):
                    self.metrics["extra_planner_api_calls"] += 1
                    self.metrics["extra_planner_batch_items"] += len(batch)
                    self.metrics["native_planner_calls"] += 1
                    response = chat(batch, max_new_tokens)
                    self.last_trace.append(
                        {
                            "batch_items": len(batch),
                            "response": response,
                            "max_new_tokens": max_new_tokens,
                        }
                    )
                    return response

                self.vlm.grounding_messages, self.vlm.chat = grounding, recorded

        self.native = ProfileBackend(model, stage, config, directory)

    def preflight(self, request, public, directory):
        self.native.preflight(request, public, directory)

    def run(self, request, public, directory, previous):
        self.native.reset()
        raw, detail = self.native.run(request, public, directory, native_plan=previous)
        if self.native.model == "mirage" and self.native.stage == "edit":
            detail = dict(detail, planned_regions=len(previous["regions"]))
        return raw, detail, dict(self.native.metrics)


def payload_reference(plan, model, setting, stage, request, task):
    if model == "sitedit":
        folder = "pass1" if stage == "tokens" else "outputs"
        return (
            Path(plan["sitedit_reference_run"])
            / folder
            / setting
            / request["case_id"]
            / "result.json"
        )
    return (
        Path(task["planner_dir"]) / "result.json"
        if stage == "planner"
        else Path(task["result_path"])
    )


def run(plan, output, phase_root, model, stage, setting, shard, smoke=False):
    profile = load_plan(plan)
    unified = profile.get("unified_execution")
    controlled_editor = bool(unified and stage == "edit" and model in {"sitedit", "qwen21"})
    variant = unified or {}
    if model == "sitedit" or controlled_editor:
        for p in ("src", "third_party/diffsynth", "third_party"):
            sys.path.insert(
                0, str(Path(os.environ.get("IFBENCH_COST_METHOD", profile["method_source"])) / p)
            )
    import torch
    from PIL import Image
    from samtok_benchmark.ifbench.public import verify

    if os.environ.get("CUDA_VISIBLE_DEVICES") != str(shard):
        raise ValueError("Each timing worker must own its assigned physical GPU")
    torch.set_num_threads(4)
    root, phase = Path(output), Path(phase_root)
    state_path = phase / f"worker-{shard}.json"
    state = {
        "status": "loading",
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "gpu": shard,
        "model": model,
        "stage": stage,
        "setting": setting,
        "completed": 0,
        "failed": 0,
        "blocked": 0,
        "cached": 0,
        "started_unix": time.time(),
    }
    worker_started = time.monotonic()
    stop = False

    def stopping(*args):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGUSR1, stopping)
    signal.signal(signal.SIGTERM, stopping)

    def progress(**fields):
        state.update(
            fields, updated=time.time(), worker_wall_seconds=time.monotonic() - worker_started
        )
        save(state_path, state)

    progress()
    assigned = list(jobs(profile, model, setting, shard))
    if smoke:
        assigned = assigned[:1]
    tasks = {(t["model"], t["setting"], t["case_id"]): t for t in profile["tasks"]}
    pending = []
    for request, repeat in assigned:
        dest = result_dir(root, model, setting, stage, request["case_id"], repeat)
        ident = identity(profile, model, setting, stage, request["case_id"], repeat)
        if terminal(dest / "result.json", ident):
            state["cached"] += 1
            continue
        if (dest / "ADMITTED.json").exists():
            raise RuntimeError(f"Unresolved admitted measurement: {dest}; inspect before release")
        previous = None
        if stage == "edit" and len(stages(model)) == 2:
            prior_path = (
                result_dir(root, model, setting, stages(model)[0], request["case_id"], repeat)
                / "result.json"
            )
            if not prior_path.exists():
                raise RuntimeError(f"Missing prerequisite measurement: {prior_path}")
            prior = read(prior_path)
            if prior["status"] != "completed":
                save(
                    dest / "result.json",
                    {
                        "identity": ident,
                        "status": "blocked_dependency",
                        "dependency": str(prior_path),
                    },
                    immutable=True,
                )
                state["blocked"] += 1
                continue
            previous = prior["native"]
        pending.append((request, repeat, dest, ident, previous))
    if not pending:
        progress(status="done")
        return
    with tempfile.TemporaryDirectory(prefix="ifbench-cost-", dir="/dev/shm") as temp:
        work = Path(temp)
        with cached_reads(profile["assets"]):
            for request, *_ in pending:
                verify(read(request["public"]), assets=True)
            start = time.perf_counter()
            try:
                if controlled_editor:
                    from .unified import Editor

                    backend = Editor(profile["method"], unified, sit=model == "sitedit")
                elif model == "sitedit":
                    backend = (
                        SitTokens(profile["method"], setting)
                        if stage == "tokens"
                        else SitEditor(profile["method"])
                    )
                else:
                    backend = Baseline(model, stage, profile["baseline_config"], work / "loader")
            except torch.cuda.OutOfMemoryError as error:
                if not profile.get("capacity_probe"):
                    raise
                evidence = {
                    "type": "gpu_out_of_memory",
                    "phase": "loading",
                    "error": repr(error),
                    "traceback": traceback.format_exc(),
                    "variant": variant,
                    "gpu": shard,
                    "host": socket.gethostname(),
                }
                save(phase / f"CAPACITY-{shard}.json", evidence, immutable=True)
                progress(
                    status="capacity_failed",
                    capacity_evidence=str(phase / f"CAPACITY-{shard}.json"),
                )
                return
            torch.cuda.synchronize()
            progress(
                load_seconds=time.perf_counter() - start,
                status="warming",
                gpu_name=torch.cuda.get_device_name(),
                packages={n: importlib.metadata.version(n) for n in ["torch", "transformers"]},
            )
            if controlled_editor:
                first, _, _, _, prior = pending[0]
                task = tasks.get((model, setting, first["case_id"]))
                checks = backend.validate_prompt(
                    read(first["public"]),
                    prior,
                    read(task["request_path"]) if task else None,
                )
                save(
                    phase / f"VALIDATION-{shard}.json",
                    {
                        "status": "passed",
                        "model": model,
                        "gpu": shard,
                        "checks": checks,
                        "quality_equivalence_claimed": False,
                        "validation_case": first["case_id"],
                    },
                    immutable=True,
                )
            if unified and stage == "edit":
                transformers = (
                    [backend.pipe.transformer] if controlled_editor else backend.native.transformers
                )
                devices = sorted({str(p.device) for m in transformers for p in m.parameters()})
                if devices != ["cuda:0"]:
                    raise ValueError(f"Unified editor is not GPU resident: {devices}")
                save(
                    phase / f"EXECUTION-{shard}.json",
                    {
                        "model": model,
                        "parameter_devices": devices,
                        "packages": {
                            n: importlib.metadata.version(n)
                            for n in ["torch", "transformers", "diffusers", "peft"]
                        },
                        "cuda": torch.version.cuda,
                        "pipeline": type(backend.pipe).__name__
                        if controlled_editor
                        else "native_method_pipeline",
                        "method_specific_attention_retained": model in {"replan", "mirage", "mice"},
                    },
                    immutable=True,
                )

            def execute(item, directory):
                request, repeat, dest, ident, previous = item
                public = read(request["public"])
                task = tasks.get((model, setting, request["case_id"]))
                native_request = read(task["request_path"]) if task else None
                directory.mkdir(parents=True, exist_ok=True)
                if model != "sitedit":
                    try:
                        backend.preflight(native_request, public, directory)
                    except Exception as error:
                        return {
                            "identity": ident,
                            "status": "failed",
                            "error": repr(error),
                            "traceback": traceback.format_exc(),
                            "native_seconds": 0.0,
                            "failure_phase": "native_input_preflight",
                            "fatal": False,
                        }, None
                torch.manual_seed(42)
                torch.cuda.synchronize()
                torch.cuda.reset_peak_memory_stats()
                tick = time.perf_counter()
                try:
                    # Preserve each method's own no_grad/inference_mode decorators.
                    if controlled_editor:
                        image, detail, calls = backend.run(
                            public, directory, previous, native_request
                        )
                    elif model == "sitedit":
                        image, detail, calls = backend.run(public, directory, previous)
                    else:
                        image, detail, calls = backend.run(
                            native_request, public, directory, previous
                        )
                    torch.cuda.synchronize()
                    seconds = time.perf_counter() - tick
                    peak = torch.cuda.max_memory_allocated()
                    reserved = torch.cuda.max_memory_reserved()
                    result = {
                        "identity": ident,
                        "status": "completed",
                        "native_seconds": seconds,
                        "peak_allocated_bytes": peak,
                        "peak_reserved_bytes": reserved,
                        "native": detail,
                        "calls": calls,
                        "gpu": shard,
                        "gpu_name": torch.cuda.get_device_name(),
                        "host": socket.gethostname(),
                    }
                    if variant:
                        result["execution_variant"] = variant
                    if model != "sitedit" and stage == "planner":
                        result["native_planner_trace"] = backend.native.last_trace
                    if image is not None:
                        result["raw_size"] = list(image.size)
                        result["raw_rgb_sha256"] = hashlib.sha256(
                            image.convert("RGB").tobytes()
                        ).hexdigest()
                    # Diagnostic parity checks happen after the timer. Errors here
                    # must not turn a successful model call into a model failure.
                    ref_path = payload_reference(profile, model, setting, stage, request, task)
                    try:
                        if ref_path.exists():
                            reference = read(ref_path)
                            result["reference_record"] = str(ref_path)
                            if image is not None and reference.get("raw_image"):
                                with Image.open(reference["raw_image"]) as ref:
                                    result["reference_rgb_equal"] = (
                                        image.size == ref.size
                                        and image.convert("RGB").tobytes()
                                        == ref.convert("RGB").tobytes()
                                    )
                            elif model == "sitedit" and stage == "tokens":
                                result["reference_tokens_equal"] = {
                                    u["id"]: u["token"] for u in detail["units"]
                                } == {u["id"]: u["token"] for u in reference["units"]}
                    except (OSError, ValueError, KeyError) as error:
                        result["reference_check_error"] = repr(error)
                    return result, image
                except Exception as error:
                    from samtok_benchmark.ifbench.fairness_dev_worker import fatal_cuda_error

                    failure = {
                        "identity": ident,
                        "status": "failed",
                        "error": repr(error),
                        "traceback": traceback.format_exc(),
                        "native_seconds": time.perf_counter() - tick,
                        "fatal": fatal_cuda_error(error)
                        or isinstance(error, torch.cuda.OutOfMemoryError),
                        "capacity_error": isinstance(error, torch.cuda.OutOfMemoryError),
                    }
                    if hasattr(backend, "native"):
                        failure.update(
                            calls=dict(backend.native.metrics),
                            native_partial_detail=backend.native.partial_detail,
                            native_planner_trace=backend.native.last_trace,
                        )
                    return failure, None

            for index, candidate in enumerate(pending):
                if stop:
                    progress(status="stopped")
                    return
                warm, warm_image = execute(candidate, work / f"warmup-{index}")
                if warm_image is not None:
                    preview = phase / f"warmup-{shard}-{index}.png"
                    warm_image.save(preview)
                    warm["preview"] = str(preview)
                    del warm_image
                save(phase / f"warmup-{shard}-{index}.json", warm)
                if warm.get("capacity_error") and profile.get("capacity_probe"):
                    evidence = dict(warm, type="gpu_out_of_memory", phase="warmup")
                    save(phase / f"CAPACITY-{shard}.json", evidence, immutable=True)
                    progress(
                        status="capacity_failed",
                        capacity_evidence=str(phase / f"CAPACITY-{shard}.json"),
                    )
                    return
                if warm.get("fatal"):
                    raise RuntimeError("Fatal CUDA error during warmup")
                if warm["status"] == "completed":
                    break
            if controlled_editor and warm["status"] != "completed":
                raise RuntimeError("Migrated editor did not produce a successful validation output")
            progress(status="ready", warmup_status=warm["status"], pending=len(pending))
            deadline = time.monotonic() + 7200
            while not (phase / "GO.json").exists():
                if stop or (phase / "STOP.json").exists() or time.monotonic() > deadline:
                    progress(status="stopped")
                    return
                time.sleep(1)
            progress(status="running")
            for item in pending:
                if stop or (phase / "STOP.json").exists():
                    progress(status="stopped")
                    return
                request, repeat, dest, ident, previous = item
                progress(current=f"{request['case_id']}/{repeat}")
                save(
                    dest / "ADMITTED.json",
                    {
                        "identity": ident,
                        "started": time.time(),
                        "pid": os.getpid(),
                        "host": socket.gethostname(),
                    },
                    immutable=True,
                )
                result, image = execute(item, work / request["case_id"] / str(repeat))
                if image is not None and repeat == 0:
                    dest.mkdir(parents=True, exist_ok=True)
                    image.save(dest / "raw.png")  # Never inside the timer.
                    result["raw_image"] = str(dest / "raw.png")
                    result["raw_file_sha256"] = sha(dest / "raw.png")
                save(dest / "result.json", result, immutable=True)
                state[result["status"]] += 1
                progress(last_native_seconds=result.get("native_seconds"))
                if result.get("capacity_error") and profile.get("capacity_probe"):
                    evidence = dict(result, type="gpu_out_of_memory", phase="measurement")
                    save(phase / f"CAPACITY-{shard}.json", evidence, immutable=True)
                    progress(
                        status="capacity_failed",
                        capacity_evidence=str(phase / f"CAPACITY-{shard}.json"),
                    )
                    return
                if result.get("fatal"):
                    raise RuntimeError(f"Fatal GPU error; preserved {dest}")
                if image is not None:
                    del image
            progress(status="done", current=None)
