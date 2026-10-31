"""One-shot FLUX.2 Klein-9B interface smoke, explicitly launched by root only.

Uses prebuilt public dual-image requests; no prompt model, scoring or selection.
Unknown admitted calls cannot be retried. Existing terminal outputs are immutable.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
from pathlib import Path
import time
import traceback


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model-root", required=True, type=Path)
    p.add_argument(
        "--requests",
        type=Path,
        default=Path("/tmp/ifbench/fairness_v2_20261030/qwen_flux2/FLUX2_PREPARED_REQUESTS.json"),
    )
    p.add_argument(
        "--output", type=Path, default=Path("/tmp/ifbench/fairness_v2_20261030/flux2_smoke")
    )
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=1)
    args = p.parse_args()
    if not args.output.resolve().is_relative_to("/tmp/ifbench/fairness_v2_20261030"):
        raise ValueError("Smoke output must remain in new temporary audit directory")
    if not 0 <= args.shard < args.shards:
        raise ValueError("Bad shard")

    import torch
    from PIL import Image
    from diffusers import Flux2KleinPipeline
    from samtok_benchmark.ifbench.public import verify

    torch.set_num_threads(4)
    rows = json.loads(args.requests.read_text())[args.shard :: args.shards]
    pinned = Path(
        "/tmp/ifbench/protocol_review_20261027/sources/diffusers/src/diffusers/pipelines/flux2/pipeline_flux2_klein.py"
    )
    installed = Path(inspect.getfile(Flux2KleinPipeline))
    assert sha(installed) == sha(pinned), "Pipeline differs from audited 06a9cfb commit"
    model_index = json.loads((args.model_root / "model_index.json").read_text())
    assert model_index["_class_name"] == "Flux2KleinPipeline"
    assert model_index.get("is_distilled") is True, (
        "Do not run base model using distilled parameters"
    )
    for row in rows:
        assert row["weight_revision"] == "92196c8e11f7b6cf2b7493e037d8c5345c559216"
        assert row["parameters"] == {
            "num_inference_steps": 4,
            "guidance_scale": 1.0,
            "max_sequence_length": 512,
        }
        assert row["seed"] == 42
        out = args.output / row["setting"] / row["case_id"]
        if (out / "started.json").exists() and not (out / "result.json").exists():
            raise RuntimeError(f"Unresolved admitted call; no automatic retry: {out}")
    t = time.monotonic()
    pipe = Flux2KleinPipeline.from_pretrained(
        str(args.model_root), torch_dtype=torch.bfloat16, local_files_only=True
    ).to("cuda")
    load_seconds = time.monotonic() - t
    pipe.set_progress_bar_config(disable=True)
    forward_calls = 0

    def counted(*unused):
        nonlocal forward_calls
        forward_calls += 1

    hook = pipe.transformer.register_forward_pre_hook(counted)
    for row in rows:
        out = args.output / row["setting"] / row["case_id"]
        if (out / "result.json").exists():
            old_call = json.loads((out / "call.json").read_text())
            for key in [
                "images",
                "prompt",
                "parameters",
                "public_digest",
                "weight_revision",
                "seed",
            ]:
                assert old_call[key] == row[key], f"Existing call differs at {key}; refuse reuse"
            assert old_call["images_sha256"] == [sha(x) for x in row["images"]]
            old = json.loads((out / "result.json").read_text())
            if old["status"] == "generated":
                assert sha(old["output_image"]) == old["output_sha256"]
            continue
        request = json.loads(Path(row["public_request"]).read_text())
        verify(request, assets=True)
        assert request["input_digest"] == row["public_digest"]
        images = [Image.open(x).convert("RGB") for x in row["images"]]
        token_text = pipe.tokenizer.apply_chat_template(
            [{"role": "user", "content": row["prompt"]}],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        tokens = pipe.tokenizer(token_text, add_special_tokens=True, truncation=False)["input_ids"]
        if len(tokens) > 512:
            raise ValueError("Complete task exceeds native tokenizer length; stop before inference")
        call = {
            **row,
            "status": "prepared",
            "images_sha256": [sha(x) for x in row["images"]],
            "input_token_count_before_padding": len(tokens),
            "pipeline_sha256": sha(installed),
            "model_root": str(args.model_root),
            "model_index_sha256": sha(args.model_root / "model_index.json"),
            "extra_component_calls": {
                "rewriter": 0,
                "external_grounder": 0,
                "sam": 0,
                "planner": 0,
                "reflection": 0,
            },
        }
        write(out / "call.json", call)
        (out / "prompt.txt").write_text(row["prompt"] + "\n")
        write(out / "started.json", {"pid": os.getpid(), "unix_time": time.time(), "seed": 42})
        print(
            json.dumps({"stage": "started", "setting": row["setting"], "case_id": row["case_id"]}),
            flush=True,
        )
        forward_calls = 0
        torch.cuda.reset_peak_memory_stats()
        torch.manual_seed(42)
        torch.cuda.synchronize()
        t = time.monotonic()
        result = {
            "setting": row["setting"],
            "case_id": row["case_id"],
            "seed": 42,
            "inference_api_calls": 1,
            "weight_revision": row["weight_revision"],
            "pipeline_revision": "06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a",
            "load_seconds": load_seconds,
            "gpu": torch.cuda.get_device_name(),
            "status": "pending",
        }
        try:
            with torch.inference_mode():
                raw = pipe(
                    image=images,
                    prompt=row["prompt"],
                    generator=torch.Generator("cuda").manual_seed(42),
                    **row["parameters"],
                ).images[0]
            torch.cuda.synchronize()
            raw.save(out / "raw.png")
            output = raw.convert("RGB").resize(
                tuple(request["source"]["size"]), Image.Resampling.LANCZOS
            )
            output.save(out / "output.png")
            result.update(
                status="generated",
                raw_size=list(raw.size),
                output_image=str(out / "output.png"),
                output_sha256=sha(out / "output.png"),
                raw_sha256=sha(out / "raw.png"),
            )
        except Exception as exc:
            result.update(
                status="failed",
                error_type=type(exc).__name__,
                error=str(exc),
                traceback=traceback.format_exc(),
            )
        try:
            peak_allocated = torch.cuda.max_memory_allocated()
            peak_reserved = torch.cuda.max_memory_reserved()
        except Exception as exc:
            peak_allocated = peak_reserved = None
            result["memory_measurement_error"] = repr(exc)
        result.update(
            seconds=time.monotonic() - t,
            transformer_forward_calls=forward_calls,
            peak_memory_allocated=peak_allocated,
            peak_memory_reserved=peak_reserved,
        )
        write(out / "result.json", result)
        print(
            json.dumps(
                {
                    "stage": result["status"],
                    "setting": row["setting"],
                    "case_id": row["case_id"],
                    "seconds": result["seconds"],
                }
            ),
            flush=True,
        )
        if result["status"] == "failed":
            raise RuntimeError("Terminal generation failure preserved; stop this worker")
    hook.remove()


if __name__ == "__main__":
    main()
