"""Fixed dev-only smoke jobs for the remaining IF-Bench main-table methods."""

from __future__ import annotations

import argparse
import inspect
import json
import os
from pathlib import Path
import time
import traceback

from PIL import Image

from samtok_benchmark.io import digest, sha256_file, write_json
from . import SETTINGS
from .public import verify

ROOT = Path("/tmp/ifbench/tiered_v1/smoke")
SHARED = Path("/tmp/ifbench/tiered_v1/shared_inputs_20261027")
SOURCES = Path("/tmp/ifbench/protocol_review_20261027/sources")
MODELS = Path("/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models")
NAMES = {
    "qwen21": "Qwen-Image-2.1",
    "flux3": "FLUX.3 Klein",
    "mice": "MICE",
    "replan": "RePlan (Qwen-2511)",
    "mirage": "MIRAGE (Qwen-2511)",
    "maskflow": "MaskFlow",
}


def load_request(task):
    directory = SHARED / "requests" / task["setting"] / task["case_id"]
    request = json.loads((directory / "public.json").read_text())
    verify(request, assets=True)
    inputs = json.loads((directory / "inputs.json").read_text())
    if inputs["digest"] != digest({k: v for k, v in inputs.items() if k != "digest"}):
        raise ValueError("Approved input changed")
    if inputs["public_input_digest"] != request["input_digest"]:
        raise ValueError("Public binding mismatch")
    if (
        inputs["annotation"]
        and sha256_file(Path(inputs["annotation"]["path"])) != inputs["annotation"]["sha256"]
    ):
        raise ValueError("Annotation changed")
    native = json.loads((directory / "native.json").read_text())
    if native != inputs["native"]:
        raise ValueError("Native geometry differs from approved input payload")
    for unit in native["units"]:
        mask = unit["mask"]
        if mask and sha256_file(Path(mask["path"])) != mask["sha256"]:
            raise ValueError("Approved native mask changed")
    return request, inputs, native


def prepare(model):
    root = ROOT / model
    cases = json.loads((SHARED / "example_selection.json").read_text())["case_ids"]
    splits = json.loads((SHARED / "plan/splits.json").read_text())
    assert set(cases) <= set(splits["dev"])
    tasks = []
    main_form = "dual" if model == "qwen21" else "native"
    for cid in cases:
        for setting in SETTINGS:
            tasks.append(
                {
                    "id": f"{cid}--{setting}--{main_form}",
                    "case_id": cid,
                    "setting": setting,
                    "form": main_form,
                }
            )
    if model in ("qwen21", "flux3"):
        form = "single" if model == "qwen21" else "native-annotation"
        for cid in cases:
            tasks.append(
                {
                    "id": f"{cid}--S3-mask--{form}",
                    "case_id": cid,
                    "setting": "S3-mask",
                    "form": form,
                }
            )
    plan = {
        "schema": "ifbench.smoke-suite.v1",
        "model": model,
        "name": NAMES[model],
        "tasks": tasks,
        "seed": 42,
        "split_digest": splits["digest"],
        "shared_root": str(SHARED),
        "quality_selection": False,
        "test_inference": False,
        "candidate_budget_note": "Smoke probes only; native mapping and discard-region registered; no quality-based retuning. Qwen PE / FLUX PUP reserve one of at most four complete configurations.",
    }
    plan["digest"] = digest(plan)
    path = root / "plan.json"
    if path.exists() and json.loads(path.read_text()) != plan:
        raise ValueError("Immutable smoke plan differs")
    write_json(path, plan)
    return plan


def worker(model, shard, shards):
    import torch
    from .smoke_adapters import build_adapter

    torch.set_num_threads(4)
    root = ROOT / model
    plan = json.loads((root / "plan.json").read_text())
    assert plan["digest"] == digest({k: v for k, v in plan.items() if k != "digest"})
    split = json.loads((SHARED / "plan/splits.json").read_text())
    assert plan["split_digest"] == split["digest"]
    assert all(t["case_id"] in split["dev"] for t in plan["tasks"])
    start = time.monotonic()
    adapter = build_adapter(model, root)
    write_json(
        root / f"worker{shard}.environment.json",
        {
            "python": os.sys.version,
            "torch": torch.__version__,
            "device": torch.cuda.get_device_name(),
            "visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "adapter_source_sha256": sha256_file(Path(inspect.getfile(type(adapter)))),
            "runner_source_sha256": sha256_file(Path(__file__)),
            "configuration": adapter.configuration,
        },
    )
    state = {"transformer_forward_calls": 0}

    def count(module, args):
        state["transformer_forward_calls"] += 1

    handles = [m.register_forward_pre_hook(count) for m in adapter.transformers]
    for task in plan["tasks"][shard::shards]:
        out = root / "runs" / task["id"]
        out.mkdir(parents=True, exist_ok=True)
        if (out / "result.json").exists():
            previous = json.loads((out / "result.json").read_text())
            assert previous["plan_digest"] == plan["digest"]
            if previous["status"] == "generated":
                assert sha256_file(Path(previous["output_image"])) == previous["output_sha256"]
            print(json.dumps({"id": task["id"], "stage": "existing-record-retained"}), flush=True)
            continue
        req, inputs, native = load_request(task)
        call = adapter.request(task, req, inputs, native, out)
        call.update(
            task=task,
            plan_digest=plan["digest"],
            input_digest=req["input_digest"],
            source=req["source"],
            seed=42,
        )
        write_json(out / "call.json", call)
        (out / "prompt.txt").write_text(call.get("prompt", "") + "\n")
        record = {
            "task": task,
            "plan_digest": plan["digest"],
            "inference_api_calls": 0,
            "transformer_forward_calls": 0,
            "extra_component_calls": call.get("extra_component_calls", {}),
            "status": "pending",
        }
        if call.get("skip_status"):
            record.update(status=call["skip_status"], reason=call["reason"])
            write_json(out / "result.json", record)
            continue
        state["transformer_forward_calls"] = 0
        torch.manual_seed(42)
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        started = time.monotonic()
        print(json.dumps({"id": task["id"], "stage": "inference-start"}), flush=True)
        try:
            with torch.inference_mode():
                raw, details = adapter.generate(call, out)
            torch.cuda.synchronize()
            record.update(details)
            raw.save(out / "raw.png")
            output = raw.convert("RGB").resize(
                tuple(req["source"]["size"]), Image.Resampling.LANCZOS
            )
            output.save(out / "output.png")
            record.update(
                status="generated",
                raw_size=list(raw.size),
                output_size=list(output.size),
                output_image=str(out / "output.png"),
                raw_sha256=sha256_file(out / "raw.png"),
                output_sha256=sha256_file(out / "output.png"),
            )
        except Exception as exc:
            record.update(status="failed", error=repr(exc), traceback=traceback.format_exc())
            traceback.print_exc()
        record.update(
            pipeline_wall_seconds=time.monotonic() - started,
            transformer_forward_calls=state["transformer_forward_calls"],
            peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated(),
        )
        write_json(out / "result.json", record)
        print(
            json.dumps(
                {
                    "id": task["id"],
                    "stage": record["status"],
                    "seconds": record["pipeline_wall_seconds"],
                }
            ),
            flush=True,
        )
        if record["status"] == "failed":
            # Continue independent requests once, without retries or changed parameters.
            torch.cuda.empty_cache()
    for handle in handles:
        handle.remove()
    write_json(
        root / f"worker{shard}.total.json",
        {"worker_wall_seconds": time.monotonic() - start, "shard": shard, "model": model},
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "worker"])
    parser.add_argument("model", choices=NAMES)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    args = parser.parse_args()
    if args.action == "prepare":
        print(json.dumps(prepare(args.model), ensure_ascii=False, indent=2))
    else:
        worker(args.model, args.shard, args.shards)


if __name__ == "__main__":
    main()
