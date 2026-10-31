"""Cache official PE/PUP on public dev inputs only, with original sampling defaults."""

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import time

from PIL import Image

from samtok_benchmark.io import digest, sha256_file, write_json
from .dev_plan import ROOT, read
from .smoke_suite import SOURCES, MODELS, load_request


def run(model):
    os.environ.setdefault("VLLM_WORKER_MULTIPROC_METHOD", "spawn")
    for name in ("GLOO_SOCKET_IFNAME", "TP_SOCKET_IFNAME", "NVSHMEM_BOOTSTRAP_UID_SOCK_IFNAME"):
        interface = os.environ.get(name)
        if interface and not Path("/sys/class/net", interface).exists():
            os.environ.pop(name, None)
    root = ROOT / "components" / model
    root.mkdir(parents=True, exist_ok=True)
    tasks = [t for t in read(ROOT / "plan.json")["tasks"] if t["model"] == model and t["component"]]
    pending = [t for t in tasks if not (root / f"{t['case_id']}--{t['setting']}.json").exists()]
    if not pending:
        return
    start = time.monotonic()
    if model == "qwen21":
        from vllm import LLM, SamplingParams

        sys.path.insert(0, str(SOURCES / "qwen21/prompt_rewrite"))
        import pe_core as core
        from run_vllm import image_to_data_uri

        receipt = read(ROOT / "pe_weights.json")
        if receipt["status"] != "downloaded":
            raise ValueError("Official PE weights not ready")
        checkpoint = receipt["path"]
        profile = core.get_profile("edit")
        system = core.load_system_prompt(None, checkpoint)
        engine = LLM(
            model=checkpoint,
            dtype="bfloat16",
            tensor_parallel_size=1,
            max_model_len=24576,
            limit_mm_per_prompt={"image": 10},
            gpu_memory_utilization=0.85,
            max_num_seqs=32,
            enable_prefix_caching=False,
            seed=42,
            trust_remote_code=True,
        )
        sampling = SamplingParams(
            temperature=profile.temperature,
            top_p=profile.top_p,
            top_k=profile.top_k,
            min_p=profile.min_p,
            presence_penalty=profile.presence_penalty,
            max_tokens=profile.max_new_tokens,
            seed=42,
        )
        write_json(
            root / "configuration.json",
            {
                "revision": receipt["revision"],
                "system_prompt_sha256": sha256_file(Path(checkpoint) / "system_prompt.txt"),
                "profile": asdict(profile),
                "thinking": True,
                "seed": 42,
                "load_seconds": time.monotonic() - start,
            },
        )
        for i in range(0, len(pending), 16):
            batch = pending[i : i + 16]
            requests = []
            conversations = []
            for t in batch:
                req, inputs, _ = load_request(t)
                form = inputs["forms"]["dual"]
                public = {
                    "id": f"{t['case_id']}--{t['setting']}",
                    "prompt": form["prompt"],
                    "input_images": form["images"],
                }
                requests.append((req, public))
                conversations.append(
                    core.build_messages(
                        system,
                        public["prompt"],
                        [
                            image_to_data_uri(Path(p), profile.image_max_pixels)
                            for p in public["input_images"]
                        ],
                    )
                )
            tick = time.monotonic()
            batch_id = digest([req["input_digest"] for req, _ in requests])
            outputs = engine.chat(
                conversations,
                sampling_params=sampling,
                chat_template_kwargs={"enable_thinking": True},
            )
            elapsed = time.monotonic() - tick
            for t, (req, public), output in zip(batch, requests, outputs, strict=True):
                thinking, answer = core.split_thinking(output.outputs[0].text)
                parsed = core.build_record(public, thinking, answer, profile)
                record = {
                    "status": "ok" if parsed["positive_prompt"] else "failed",
                    "input_digest": req["input_digest"],
                    "public_input": public,
                    "rewritten_prompt": parsed["positive_prompt"],
                    "official_record": parsed,
                    "native_parse_fallback_used": not parsed["parse_ok"],
                    "finish_reason": output.outputs[0].finish_reason,
                    "inference_requests": 1,
                    "api_invocation_ids": [batch_id],
                    "batch_api_calls": 1,
                    "call_count_note": "One batched LLM.chat invocation; deduplicate api_invocation_ids across records, do not sum repeated batch_api_calls.",
                    "batch_wall_seconds": elapsed,
                    "batch_size": len(batch),
                }
                write_json(root / f"{t['case_id']}--{t['setting']}.json", record)
            print(
                json.dumps(
                    {
                        "component": model,
                        "done": min(i + len(batch), len(pending)),
                        "total": len(pending),
                    }
                ),
                flush=True,
            )
    else:
        os.environ["WEIGHTS_DIR"] = str(MODELS)
        sys.path.insert(0, str(SOURCES / "flux3/src"))
        from flux3.pup import Upsampler
        from .smoke_adapters import Flux3

        adapter = object.__new__(Flux3)
        adapter.configuration = {
            "model": "distilled",
            "steps": 16,
            "guidance": None,
            "pup": False,
            "safety": False,
        }
        upsampler = Upsampler(str(MODELS / "flux-3-image-klein-pup"), memory=0.85)
        generate = upsampler.llm.generate
        actual_calls = [0]

        def counted_generate(*args, **kwargs):
            actual_calls[0] += 1
            return generate(*args, **kwargs)

        upsampler.llm.generate = counted_generate
        write_json(
            root / "configuration.json",
            {
                "source_revision": read(SOURCES / "flux3/revision.json")["commit"],
                "weight_path": str(MODELS / "flux-3-image-klein-pup"),
                "source_sha256": sha256_file(SOURCES / "flux3/src/flux3/pup.py"),
                "load_seconds": time.monotonic() - start,
                "parameters": "Official Upsampler defaults; GPU memory fraction changed only for standalone caching",
            },
        )
        for i, t in enumerate(pending):
            req, inputs, native = load_request(t)
            call = adapter.request(t, req, inputs, native, root)
            tick = time.monotonic()
            actual_calls[0] = 0
            record = {
                "input_digest": req["input_digest"],
                "public_input": call,
                "inference_api_calls": 0,
                "marks": ["§"],
            }
            try:
                caption = upsampler(
                    call["prompt"],
                    [Image.open(p).convert("RGB") for p in call["images"]],
                    call["boxes"],
                )
                record.update(status="ok", rewritten_prompt=caption)
            except Exception as exc:
                record.update(status="failed", error=repr(exc))
            record["wall_seconds"] = time.monotonic() - tick
            record["inference_api_calls"] = actual_calls[0]
            write_json(root / f"{t['case_id']}--{t['setting']}.json", record)
            print(
                json.dumps(
                    {
                        "component": model,
                        "done": i + 1,
                        "total": len(pending),
                        "status": record["status"],
                    }
                ),
                flush=True,
            )
            if record["status"] != "ok":
                break
    write_json(root / "total.json", {"worker_wall_seconds": time.monotonic() - start})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("model", choices=("qwen21", "flux3"))
    run(p.parse_args().model)
