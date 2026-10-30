# ruff: noqa: E402
# Standalone entrypoint: configure CPU threads/import paths before dependent imports.
"""Durable, fixed two-case validation of the approved fairness revision.

This runner does not run a Judge, select by scores, freeze, or access test cases.
It keeps historical outputs immutable and reuses identical S1 computations.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import traceback

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from samtok_benchmark.io import digest, sha256_file
from samtok_benchmark.ifbench.public import verify
from evaluation.protocol_audit.fairness_flux3_replan import (
    CASES,
    SETTINGS,
    SHARED,
    SOURCES,
    request,
    Flux3FairnessRunner,
    ReplanPlannerOnlyRunner,
    ReplanEditorOnlyRunner,
)

ROOT = Path("/tmp/ifbench/fairness_v2_20261030")
RUN = ROOT / "flux3_replan"
OLD = Path("/tmp/ifbench/tiered_v1/dev_selection")
HELPER = Path(__file__).with_name("fairness_flux3_replan.py")


def read(path):
    return json.loads(Path(path).read_text())


def save(path, data, *, replace=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if replace:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        tmp.replace(path)
    elif path.exists():
        if read(path) != data:
            raise ValueError(f"Immutable record differs: {path}")
    else:
        with path.open("x") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")


def authorized():
    value = read(ROOT / "AUTHORIZATION.json")
    assert value["status"] == "approved"
    assert value["cases"] == list(CASES)
    assert not value["test_authorized"] and not value["freeze_authorized"]
    return value


def prepare():
    authorized()
    split = read(SHARED / "plan/splits.json")
    assert set(CASES) <= set(split["dev"]) and not set(CASES) & set(split["test"])
    for model in ("flux3", "replan"):
        tasks = []
        for cid in CASES:
            for setting in SETTINGS:
                call = request(model, cid, setting)
                call["images_sha256"] = [sha256_file(Path(p)) for p in call["images"]]
                call["call_digest"] = digest(call)
                path = RUN / model / "requests" / setting / cid / "call.json"
                save(path, call)
                tasks.append(
                    {
                        "case_id": cid,
                        "setting": setting,
                        "call": str(path),
                        "call_digest": call["call_digest"],
                    }
                )
        plan = {
            "schema": "ifbench-fairness-fixed-validation-v1",
            "model": model,
            "tasks": tasks,
            "cases": list(CASES),
            "settings": list(SETTINGS),
            "helper_sha256": sha256_file(HELPER),
            "split_digest": split["digest"],
            "authorization_sha256": sha256_file(ROOT / "AUTHORIZATION.json"),
            "seed": 42,
            "quality_search": False,
            "formal_test": False,
        }
        plan["digest"] = digest(plan)
        save(RUN / model / "plan.json", plan)
    print(json.dumps({"prepared": 40, "new_model_calls": 0}))


def check_call(call, plan):
    assert call["call_digest"] == digest({k: v for k, v in call.items() if k != "call_digest"})
    public = read(call["public_request"])
    verify(public, assets=True)
    assert public["input_digest"] == call["public_input_digest"]
    assert [sha256_file(Path(p)) for p in call["images"]] == call["images_sha256"]
    if call["model"] == "replan":
        assert (
            sha256_file(Path(call["planner_image"])) == call["image_sha256"][call["planner_image"]]
        )
        assert sha256_file(Path(call["editor_image"])) == call["image_sha256"][call["editor_image"]]
    return public


def reuse_s1(call, stage):
    if call["setting"] != "S1":
        return None
    model, cid = call["model"], call["case_id"]
    directory = OLD / "runs" / model / "native" / "S1" / cid
    prior_call = read(directory / "call.json")
    prior_result = read(directory / "result.json")
    assert prior_call["seed"] == call["seed"] == 42
    assert prior_call["input_digest"] == call["public_input_digest"]
    public = read(call["public_request"])
    assert prior_call["source"]["sha256"] == public["source"]["sha256"]
    assert prior_result["status"] == "generated"
    assert sha256_file(Path(prior_result["output_image"])) == prior_result["output_sha256"]
    evidence = {
        "previous_call": str(directory / "call.json"),
        "previous_call_sha256": sha256_file(directory / "call.json"),
        "previous_result": str(directory / "result.json"),
        "previous_result_sha256": sha256_file(directory / "result.json"),
    }
    if model == "flux3":
        for field in ("images", "prompt", "boxes", "parameters"):
            assert prior_call[field] == call[field], field
    else:
        old_plan = read(prior_call["planner_record"])
        assert old_plan["input_digest"] == call["public_input_digest"]
        assert old_plan["status"] == "planned" and len(old_plan["groups"]) == 1
        group = old_plan["groups"][0]
        assert group["instruction"] == call["prompt"]
        assert group["response"] == prior_call["response"]
        assert group["template"] == Path(call["planner_template"]).read_text()
        assert prior_call["images"] == [call["editor_image"]] == [call["planner_image"]]
        env = read("/tmp/ifbench/tiered_v1/smoke/replan/worker0.environment.json")
        assert all(env["configuration"][k] == v for k, v in call["parameters"].items())
        assert (
            env["configuration"]["source_revision"]
            == read(SOURCES / "replan/revision.json")["commit"]
        )
        evidence["previous_planner_record"] = prior_call["planner_record"]
        evidence["previous_planner_sha256"] = sha256_file(Path(prior_call["planner_record"]))
        if stage == "planner":
            return {
                "status": "native-response-returned",
                "response": group["response"],
                "prompt": call["prompt"],
                "seed": 42,
                "public_input_digest": call["public_input_digest"],
                "configuration_id": call["configuration_id"],
                "planner_image": call["planner_image"],
                "planner_image_sha256": call["image_sha256"][call["planner_image"]],
                "template_sha256": sha256_file(Path(call["planner_template"])),
                "native_planner_calls": 0,
                "reused_native_planner_calls": old_plan["extra_planner_calls"],
                "reused": True,
                "reuse_evidence": evidence,
            }
    return {
        "status": "generated",
        "reused": True,
        "reuse_evidence": evidence,
        "output_image": prior_result["output_image"],
        "output_sha256": prior_result["output_sha256"],
        "raw_size": prior_result["raw_size"],
        "inference_api_calls": 0,
        "reused_inference_api_calls": prior_result["inference_api_calls"],
        "actual_global_prompt": prior_result.get("actual_global_prompt"),
        "actual_region_guidance": prior_result.get("actual_region_guidance"),
    }


def run(args):
    authorized()
    plan = read(RUN / args.model / "plan.json")
    assert plan["digest"] == digest({k: v for k, v in plan.items() if k != "digest"})
    assert plan["helper_sha256"] == sha256_file(HELPER)
    assert plan["authorization_sha256"] == sha256_file(ROOT / "AUTHORIZATION.json")
    assert 0 <= args.shard < args.shards
    if args.stage == "planner" and args.model != "replan":
        raise ValueError("FLUX3 has no enabled planner")
    import torch

    torch.set_num_threads(4)
    worker = RUN / args.model / "workers" / f"{args.stage}-{args.shard}"
    worker.mkdir(parents=True, exist_ok=True)
    save(
        worker / "environment.json",
        {
            "python": sys.version,
            "torch": torch.__version__,
            "gpu": torch.cuda.get_device_name(),
            "visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "runner_sha256": sha256_file(Path(__file__)),
            "helper_sha256": sha256_file(HELPER),
            "plan_digest": plan["digest"],
        },
    )
    scratch = worker / "scratch"
    scratch.mkdir(exist_ok=True)
    os.chdir(scratch)
    runner = None
    loaded_at = None
    for task in plan["tasks"][args.shard :: args.shards]:
        call = read(task["call"])
        assert task["call_digest"] == call["call_digest"]
        public = check_call(call, plan)
        out = (
            RUN
            / args.model
            / ("planners" if args.stage == "planner" else "outputs")
            / call["setting"]
            / call["case_id"]
        )
        out.mkdir(parents=True, exist_ok=True)
        result_path = out / "result.json"
        binding = {
            "call_digest": call["call_digest"],
            "plan_digest": plan["digest"],
            "model": args.model,
            "setting": call["setting"],
            "case_id": call["case_id"],
            "stage": args.stage,
        }
        if result_path.exists():
            old = read(result_path)
            assert all(old[k] == v for k, v in binding.items())
            if old["status"] == "generated":
                assert sha256_file(Path(old["output_image"])) == old["output_sha256"]
            continue
        if (out / "started.json").exists():
            raise RuntimeError(f"Unresolved prior attempt; automatic retry forbidden: {out}")
        reused = reuse_s1(call, args.stage)
        if reused:
            save(result_path, {**binding, **reused})
            continue
        native_plan = None
        if args.model == "replan" and args.stage == "edit":
            p = RUN / "replan/planners" / call["setting"] / call["case_id"] / "result.json"
            native_plan = read(p)
            assert native_plan["call_digest"] == call["call_digest"]
            if native_plan["status"] != "native-response-returned":
                save(
                    result_path,
                    {
                        **binding,
                        "status": "failed-planner",
                        "inference_api_calls": 0,
                        "planner_record": str(p),
                    },
                )
                continue
        if runner is None:
            start = time.monotonic()
            runner = (
                Flux3FairnessRunner()
                if args.model == "flux3"
                else ReplanPlannerOnlyRunner()
                if args.stage == "planner"
                else ReplanEditorOnlyRunner()
            )
            loaded_at = time.monotonic() - start
        save(out / "started.json", {**binding, "pid": os.getpid(), "time": time.time(), "seed": 42})
        save(out / "call.json", call)
        result = {
            **binding,
            "reused": False,
            "inference_api_calls": 0,
            "native_planner_calls": 0,
            "load_seconds": loaded_at,
            "seed": 42,
        }
        started = time.monotonic()
        fatal = False
        torch.manual_seed(42)
        torch.cuda.reset_peak_memory_stats()
        print(json.dumps({**binding, "status": "started"}), flush=True)
        try:
            with torch.inference_mode():
                if args.stage == "planner":
                    result["native_planner_calls"] = 1
                    result.update(
                        runner.run(
                            call,
                            trace_callback=lambda trace: save(
                                out / "traces.json", trace, replace=True
                            ),
                        )
                    )
                else:
                    result["inference_api_calls"] = 1
                    raw, detail = (
                        runner.run(call) if args.model == "flux3" else runner.run(call, native_plan)
                    )
                    result.update(detail)
                    raw.save(out / "raw.png")
                    raw.convert("RGB").resize(
                        tuple(public["source"]["size"]), Image.Resampling.LANCZOS
                    ).save(out / "output.png")
                    result.update(
                        status="generated",
                        raw_size=list(raw.size),
                        output_image=str(out / "output.png"),
                        output_sha256=sha256_file(out / "output.png"),
                        raw_sha256=sha256_file(out / "raw.png"),
                    )
            torch.cuda.synchronize()
        except Exception as exc:
            result.update(status="failed", error=repr(exc), traceback=traceback.format_exc())
            fatal = any(
                x in str(exc).lower()
                for x in (
                    "device-side assert",
                    "illegal memory access",
                    "unspecified launch failure",
                )
            )
        finally:
            if args.stage == "planner" and hasattr(runner, "last_trace"):
                save(out / "traces.json", runner.last_trace, replace=True)
            result.update(
                wall_seconds=time.monotonic() - started,
                peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated(),
            )
            save(result_path, result)
            print(
                json.dumps(
                    {**binding, "status": result["status"], "seconds": result["wall_seconds"]}
                ),
                flush=True,
            )
        if fatal:
            raise RuntimeError(
                "Fatal CUDA state; saved current failure and left later requests unattempted"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "planner", "edit"])
    parser.add_argument("--model", choices=["flux3", "replan"], default="flux3")
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    args = parser.parse_args()
    prepare() if args.stage == "prepare" else run(args)
