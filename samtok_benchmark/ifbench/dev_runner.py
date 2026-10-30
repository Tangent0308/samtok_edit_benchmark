"""Durable dev-only worker. One sample per effective request; never freezes or runs test."""

import argparse
import fcntl
import inspect
import json
import os
from pathlib import Path
import time
import traceback

from PIL import Image

from samtok_benchmark.io import digest, sha256_file, write_json
from .dev_plan import ROOT, SMOKE, MODELS, read
from .smoke_suite import load_request


class Qwen2511:
    def __init__(self, root):
        import torch
        from diffusers import QwenImageEditPlusPipeline
        from .smoke_suite import MODELS as weights

        self.pipe = QwenImageEditPlusPipeline.from_pretrained(
            str(weights / "Qwen-Image-Edit-2511"), torch_dtype=torch.bfloat16, local_files_only=True
        ).to("cuda")
        self.pipe.set_progress_bar_config(disable=True)
        self.transformers = [self.pipe.transformer]
        self.configuration = {
            "num_inference_steps": 40,
            "true_cfg_scale": 4.0,
            "guidance_scale": 1.0,
            "negative_prompt": " ",
            "num_images_per_prompt": 1,
            "max_sequence_length": 512,
        }

    def request(self, task, req, inputs, native, out):
        from .smoke_adapters import source_call

        call = source_call(req, native)
        call.update(inputs["forms"][task["form"]])
        call["parameters"] = self.configuration
        return call

    def generate(self, call, out):
        from .smoke_adapters import generator

        result = self.pipe(
            image=[Image.open(p).convert("RGB") for p in call["images"]],
            prompt=call["prompt"],
            generator=generator(),
            **call["parameters"],
        ).images[0]
        return result, {"inference_api_calls": 1}


def scientific_call(call):
    return {
        k: v
        for k, v in call.items()
        if k
        not in {
            "task",
            "plan_digest",
            "dev_plan_digest",
            "input_digest",
            "source",
            "seed",
            "planner_record",
            "scope",
            "condition_preprocessor_images",
        }
    }


def reuse_smoke(task, call, configuration):
    if task["component"]:
        return None
    path = SMOKE / task["model"] / "runs" / task["id"] / "result.json"
    if not path.exists():
        return None
    old = read(path)
    if old["status"] != "generated":
        return None
    previous = read(path.with_name("call.json"))
    if task["model"] == "qwen2511":
        same = (
            [item["path"] for item in previous["images"]] == call["images"]
            and all(
                sha256_file(Path(item["path"])) == item["sha256"] for item in previous["images"]
            )
            and previous["prompt"] == call["prompt"]
            and previous.get("parameters", previous.get("config")) == configuration
        )
    else:
        same = scientific_call(previous) == scientific_call(call)
    if not same or previous["seed"] != 42:
        raise ValueError(f"Smoke reuse mismatch; refuse resampling: {task['key']}")
    if sha256_file(Path(old["output_image"])) != old["output_sha256"]:
        raise ValueError("Smoke output bytes changed")
    return {**old, "reuse_record": str(path), "additional_inference_calls": 0}


def load_adapter(model, root):
    from .smoke_adapters import build_adapter

    adapter = Qwen2511(root) if model == "qwen2511" else build_adapter(model, root)
    if model == "mirage":
        from .ref_extract import extract_ref

        adapter.ref_extractor = extract_ref
    return adapter


def clear_mice(adapter):
    for module in adapter.pipe.transformer.modules():
        proc = getattr(module, "processor", None)
        if hasattr(proc, "clear_cached_masks"):
            proc.clear_cached_masks()


def worker(model, shard=0, shards=1, include_components=False, limit=None):
    import torch

    torch.set_num_threads(4)
    root = ROOT / model
    root.mkdir(parents=True, exist_ok=True)
    scratch = root / "debug" / f"worker{os.getpid()}-{shard}"
    scratch.mkdir(parents=True, exist_ok=True)
    os.chdir(scratch)  # Upstream diagnostic images must not land in the repo.
    plan = read(ROOT / "plan.json")
    assert plan["digest"] == digest({k: v for k, v in plan.items() if k != "digest"})
    from .dev_scope import active_plan

    if model not in active_plan()["candidates"]:
        return
    tasks = [
        t
        for t in plan["tasks"]
        if t["model"] == model and (include_components or not t["component"])
    ]
    tasks = tasks[shard::shards]
    if limit is not None:
        tasks = tasks[:limit]
    assert all(t["case_id"] in plan["case_ids"] for t in tasks)
    adapter = None
    started = time.monotonic()
    worker_id = f"{os.getpid()}-{shard}"
    state = {"transformer_forward_calls": 0}

    def count(module, args):
        state["transformer_forward_calls"] += 1

    completed = 0
    for task in tasks:
        if (root / "PAUSED.json").exists():
            break
        out = ROOT / "runs" / task["key"]
        out.mkdir(parents=True, exist_ok=True)
        lock = (out / "lock").open("a")
        try:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                continue
            if (out / "result.json").exists():
                old = read(out / "result.json")
                assert old["dev_plan_digest"] == plan["digest"]
                continue
            if (out / "started.json").exists():
                write_json(
                    out / "result.json",
                    {
                        "task": task,
                        "dev_plan_digest": plan["digest"],
                        "status": "failed-interrupted",
                        "reason": "Earlier inference started without a result; no automatic resampling",
                        "inference_api_calls": None,
                    },
                )
                continue
            req, inputs, native = load_request(task)
            if model == "maskflow" and task["setting"] in ("S1", "S5"):
                write_json(
                    out / "result.json",
                    {
                        "task": task,
                        "dev_plan_digest": plan["digest"],
                        "status": "not-applicable",
                        "reason": "Approved complete-setting N/A, no backbone fallback",
                        "inference_api_calls": 0,
                    },
                )
                continue
            if model in ("mirage", "replan") and native["missing_region_units"]:
                path = ROOT / "planners" / model / f"{req['case_id']}--{req['setting']}.json"
                if not path.exists():
                    continue  # A prerequisite, not a failed editor request.
                if read(path)["status"] != "planned":
                    write_json(
                        out / "result.json",
                        {
                            "task": task,
                            "dev_plan_digest": plan["digest"],
                            "status": "failed-planner",
                            "reason": read(path).get("error", "Native plan failed"),
                            "planner_record": str(path),
                            "inference_api_calls": 0,
                        },
                    )
                    continue
            component_path = (
                ROOT / "components" / model / f"{task['case_id']}--{task['setting']}.json"
            )
            if task["component"] and not component_path.exists():
                continue
            if adapter is None:
                load_start = time.monotonic()
                adapter = load_adapter(model, root)
                for module in adapter.transformers:
                    module.register_forward_pre_hook(count)
                write_json(
                    root / f"worker-{worker_id}.environment.json",
                    {
                        "python": os.sys.version,
                        "torch": torch.__version__,
                        "gpu": torch.cuda.get_device_name(),
                        "visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
                        "configuration": adapter.configuration,
                        "load_seconds": time.monotonic() - load_start,
                        "adapter_file": inspect.getfile(type(adapter)),
                        "adapter_sha256": sha256_file(Path(inspect.getfile(type(adapter)))),
                        "runner_sha256": sha256_file(Path(__file__)),
                        "dev_plan_digest": plan["digest"],
                    },
                )
            try:
                call = adapter.request(task, req, inputs, native, out)
            except ValueError as exc:
                write_json(
                    out / "result.json",
                    {
                        "task": task,
                        "dev_plan_digest": plan["digest"],
                        "status": "blocked-protocol",
                        "reason": str(exc),
                        "inference_api_calls": 0,
                    },
                )
                write_json(
                    root / "PAUSED.json",
                    {
                        "reason": "Protocol/input adaptation needs review",
                        "task": task,
                        "error": str(exc),
                    },
                )
                break
            call.update(
                task=task,
                dev_plan_digest=plan["digest"],
                source=req["source"],
                input_digest=req["input_digest"],
                seed=42,
            )
            if task["component"]:
                component = read(component_path)
                if component["input_digest"] != req["input_digest"]:
                    raise ValueError("Component cache input binding mismatch")
                if component["status"] != "ok":
                    write_json(
                        out / "result.json",
                        {
                            "task": task,
                            "dev_plan_digest": plan["digest"],
                            "status": "failed-component",
                            "reason": component.get("error", "Component failed"),
                            "inference_api_calls": 0,
                        },
                    )
                    continue
                call["component_record"] = str(component_path)
                if task["component"] == "pe":
                    call["prompt"] = component["rewritten_prompt"]
                else:

                    class CachedUpsampler:
                        def __call__(self, prompt, images, boxes):
                            return component["rewritten_prompt"]

                    adapter.models.upsampler = CachedUpsampler()
                    call["parameters"]["pup"] = True
            else:
                reused = reuse_smoke(task, call, adapter.configuration)
                if reused:
                    write_json(out / "call.json", call)
                    write_json(
                        out / "result.json",
                        {
                            **reused,
                            "task": task,
                            "dev_plan_digest": plan["digest"],
                            "status": "generated",
                            "reused": True,
                        },
                    )
                    completed += 1
                    continue
            write_json(out / "call.json", call)
            (out / "prompt.txt").write_text(call["prompt"] + "\n")
            if call.get("skip_status"):
                write_json(
                    out / "result.json",
                    {
                        "task": task,
                        "dev_plan_digest": plan["digest"],
                        "status": call["skip_status"],
                        "reason": call["reason"],
                        "inference_api_calls": 0,
                    },
                )
                continue
            if model == "mice":
                clear_mice(adapter)
            torch.manual_seed(42)
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
            state["transformer_forward_calls"] = 0
            write_json(out / "started.json", {"pid": os.getpid(), "time": time.time(), "seed": 42})
            print(json.dumps({"stage": "inference-start", "key": task["key"]}), flush=True)
            tick = time.monotonic()
            record = {
                "task": task,
                "dev_plan_digest": plan["digest"],
                "input_digest": req["input_digest"],
                "inference_api_calls": None,
                "status": "pending",
                "configuration": adapter.configuration,
            }
            try:
                with torch.inference_mode():
                    raw, details = adapter.generate(call, out)
                torch.cuda.synchronize()
                raw.save(out / "raw.png")
                output = raw.convert("RGB").resize(
                    tuple(req["source"]["size"]), Image.Resampling.LANCZOS
                )
                output.save(out / "output.png")
                record.update(
                    details,
                    status="generated",
                    raw_size=list(raw.size),
                    output_size=list(output.size),
                    output_image=str(out / "output.png"),
                    output_sha256=sha256_file(out / "output.png"),
                    raw_sha256=sha256_file(out / "raw.png"),
                )
            except Exception as exc:
                record.update(status="failed", error=repr(exc), traceback=traceback.format_exc())
                traceback.print_exc()
            record.update(
                pipeline_wall_seconds=time.monotonic() - tick,
                transformer_forward_calls=state["transformer_forward_calls"],
                peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated(),
            )
            write_json(out / "result.json", record)
            completed += 1
            print(
                json.dumps(
                    {
                        "stage": record["status"],
                        "key": task["key"],
                        "seconds": record["pipeline_wall_seconds"],
                    }
                ),
                flush=True,
            )
            if record["status"] == "failed":
                # Stop on a runtime error; do not waste the remaining budget or mask a systemic bug.
                write_json(
                    root / "PAUSED.json",
                    {
                        "reason": "Runtime error; inspect before continuing",
                        "task": task,
                        "error": record["error"],
                    },
                )
                break
        finally:
            lock.close()
    write_json(
        root / f"worker-{worker_id}.total.json",
        {
            "worker_wall_seconds": time.monotonic() - started,
            "completed": completed,
            "shard": shard,
            "shards": shards,
            "dev_plan_digest": plan["digest"],
        },
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("model", choices=MODELS)
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=1)
    p.add_argument("--include-components", action="store_true")
    p.add_argument("--limit", type=int)
    p.add_argument(
        "--exact-model", action="store_true", help="Internal worker: bypass GPU handoff balancing"
    )
    a = p.parse_args()
    if not a.exact_model and (ROOT / "engineering/balanced_queue/enabled.json").exists():
        if a.shard != 0 or a.shards != 1 or a.limit is not None:
            raise ValueError(
                "Explicit sharding/limits require --exact-model when balancing is enabled"
            )
        from .dev_balancer import run

        run(a.model)
        return
    worker(a.model, a.shard, a.shards, a.include_components, a.limit)


if __name__ == "__main__":
    main()
