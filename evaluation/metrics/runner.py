"""Resumable offline vLLM judge. Run as python -m evaluation.metrics.runner."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
import time
import traceback
from pathlib import Path

from tqdm import tqdm

from evaluation.common import atomic_write_json, read_jsonl, sha256_file
from evaluation.metrics.protocol import VERSION, digest
from evaluation.metrics.views import conversation
from evaluation.metrics import simple

DEFAULT_MODEL = Path("/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/Qwen3.8-27B")
VARIANTS = {
    name: {"rubric": "two_image_v2", "whole": True, "repeat": repeat,
           "thinking": True, "effort": "low"}
    for name, repeat in (("pair_v2", 0), ("pair_v2_r1", 1))
}


def fingerprint(args):
    model = args.model
    # Config hashes + shard file identity: inexpensive, explicit local revision identity.
    # This is not a cryptographic checksum of all model weights.
    files = {p.name: {"size": p.stat().st_size, "mtime_ns": p.stat().st_mtime_ns}
             for p in sorted(model.glob("*.safetensors"))}
    if not files or not (model / "config.json").is_file():
        raise FileNotFoundError(f"model checkpoint is incomplete or not mounted: {model}")
    configs = {p.name: sha256_file(p) for p in sorted(model.glob("*.json"))}
    configs.update({p.name: sha256_file(p) for p in sorted(model.glob("*.jinja"))})
    code = {p.name: sha256_file(p) for p in sorted(Path(__file__).parent.glob("*.py"))}
    code["../common.py"] = sha256_file(Path(__file__).parent.parent / "common.py")
    return {"protocol_version": VERSION, "model": str(model.resolve()), "weights_stat": files,
            "config_sha256": configs, "code_sha256": code,
            "packages": {k: importlib.metadata.version(k) for k in ("vllm", "transformers", "torch", "Pillow")},
            "decode": {"temperature": 0.0, "seed": 0, "max_tokens": args.max_tokens,
                       "thinking": args.thinking, "reasoning_effort": args.reasoning_effort}, "max_pixels": args.max_pixels,
            "min_pixels": 65536, "max_model_len": args.max_model_len, "batch_size": args.batch_size,
            "gpu_memory_utilization": args.gpu_memory_utilization,
            "manifest_sha256": sha256_file(args.manifest)}


class Backend:
    def __init__(self, args):
        os.environ.setdefault("VLLM_WORKER_MULTIPROC_METHOD", "spawn")
        os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
        from transformers import AutoProcessor
        from vllm import LLM, SamplingParams
        self.args = args
        self.processor = AutoProcessor.from_pretrained(str(args.model), local_files_only=True)
        self.model = LLM(model=str(args.model), tensor_parallel_size=1, dtype="bfloat16", seed=0,
                         gpu_memory_utilization=args.gpu_memory_utilization,
                         max_model_len=args.max_model_len, max_num_seqs=args.batch_size,
                         limit_mm_per_prompt={"image": 2},
                         mm_processor_kwargs={"min_pixels": 65536, "max_pixels": args.max_pixels},
                         generation_config="vllm", disable_log_stats=True)
        self.sampling = SamplingParams(temperature=0, top_p=1, top_k=-1, seed=0,
                                       max_tokens=args.max_tokens)

    def generate(self, conversations, thinking=None, effort=None):
        requests = []
        for conv in conversations:
            images = [part["image"] for m in conv if isinstance(m["content"], list)
                      for part in m["content"] if part["type"] == "image"]
            requests.append({"prompt": self.processor.apply_chat_template(
                conv, tokenize=False, add_generation_prompt=True,
                enable_thinking=self.args.thinking if thinking is None else thinking,
                reasoning_effort=effort or self.args.reasoning_effort),
                "multi_modal_data": {"image": images},
                "mm_processor_kwargs": {"min_pixels": 65536, "max_pixels": self.args.max_pixels}})
        outputs = self.model.generate(requests, self.sampling, use_tqdm=False)
        if len(outputs) != len(conversations):
            raise RuntimeError("vLLM result count mismatch")
        return [{"text": o.outputs[0].text, "finish_reason": o.outputs[0].finish_reason,
                 "prompt_tokens": len(o.prompt_token_ids), "output_tokens": len(o.outputs[0].token_ids)}
                for o in outputs]


def verify_assets(rows):
    seen = {}
    for row in rows:
        pairs = [(row["source_image"], row["source_sha256"])]
        if row["delivery_status"] == "available":
            pairs.append((row["output_image"], row["output_sha256"]))
        pairs.extend((r["mask"], r["mask_sha256"]) for r in row["regions"])
        for path, expected in pairs:
            if path not in seen:
                seen[path] = sha256_file(Path(path))
            if seen[path] != expected:
                raise ValueError(f"asset changed since manifest creation: {path}")


def run(args):
    if not 0 <= args.rank < args.world_size or args.batch_size < 1:
        raise ValueError("invalid rank/world size/batch size")
    if args.max_pixels < 65536 or not 0 < args.max_tokens < args.max_model_len:
        raise ValueError("invalid image/context budget")
    if len(args.variants) != len(set(args.variants)):
        raise ValueError("duplicate variant would reuse the same cache; use a named repeat variant")
    rows = read_jsonl(args.manifest)
    if args.split != "all":
        rows = [r for r in rows if r["split"] == args.split]
    if args.limit is not None:
        rows = rows[:args.limit]
    config = fingerprint(args)
    config["variants"] = {k: VARIANTS[k] for k in args.variants}
    config["variant_decode"] = {k: {**config["decode"],
                                    "thinking": VARIANTS[k].get("thinking", args.thinking),
                                    "reasoning_effort": VARIANTS[k].get("effort", args.reasoning_effort)}
                                for k in args.variants}
    config["selected_sample_ids"] = [r["sample_id"] for r in rows]
    run_id = digest(config)
    # Separate variants/repeats never share response cache entries.
    jobs = [(r, variant) for variant in args.variants for r in rows]
    # Repeat tests shift replicas to expose device/runtime variation as well as repeated decoding.
    jobs = [j for i, j in enumerate(jobs)
            if (i + VARIANTS[j[1]]["repeat"]) % args.world_size == args.rank]
    verify_assets([r for r, _ in jobs])
    args.output.mkdir(parents=True, exist_ok=True)
    atomic_write_json(args.output / f"config.rank{args.rank}.json", {**config, "run_id": run_id})
    backend = None
    failures = 0
    progress_label = f"judge shard{args.rank} GPU{os.environ.get('CUDA_VISIBLE_DEVICES', 'default')}"
    for row, variant_name in tqdm(jobs, desc=progress_label, mininterval=5):
        variant = VARIANTS[variant_name]
        regions = [None]  # One joint assessment for all requested targets.
        def task_prompt(region):
            return simple.prompt(row, variant["rubric"])
        def task_views(region):
            return simple.make_views(row, args.max_pixels)
        key = digest({"run_id": run_id, "input": row["input_digest"], "variant": variant_name})
        path = args.output / "records" / f"{key}.json"
        if path.exists():
            previous = json.loads(path.read_text())
            if previous["status"] in {"ok", "missing_output", "annotation_conflict"}:
                continue
        record = {"key": key, "run_id": run_id, "sample_id": row["sample_id"], "variant": variant_name,
                  "sample": row, "passes": [], "started_at": time.time(),
                  "worker_rank": args.rank, "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES")}
        if row["delivery_status"] != "available":
            record["status"] = "missing_output"
        elif row["annotation_status"] == "conflict_review_required":
            record["status"] = "annotation_conflict"
        elif args.dry_run:
            # Build every actual prompt and view without initializing CUDA.
            for region in regions:
                v = task_views(region)
                task_prompt(region)
                if len(v) != 2 or any(min(image.size) < 1 for _, image in v):
                    raise ValueError("invalid image views")
            continue
        else:
            if backend is None:
                backend = Backend(args)
            try:
                # All targets are assessed together with the same two images.
                for start in range(0, len(regions), args.batch_size):
                    group = regions[start:start+args.batch_size]
                    conversations = [conversation(task_views(r), task_prompt(r)) for r in group]
                    outputs = backend.generate(conversations, thinking=variant.get("thinking"), effort=variant.get("effort"))
                    for region, conv, output in zip(group, conversations, outputs):
                        attempts = []
                        value = None
                        for attempt in range(2):
                            attempt_record = dict(output)
                            try:
                                if output["finish_reason"] == "length":
                                    raise ValueError("truncated model response")
                                value = simple.parse(output["text"])
                                attempt_record["parse_ok"] = True
                            except (ValueError, TypeError) as error:
                                attempt_record.update(parse_ok=False, error=str(error))
                            attempts.append(attempt_record)
                            if value is not None or attempt == 1:
                                break
                            # Retry format only; do not request a better score or change images.
                            retry = conv + [{"role": "assistant", "content": output["text"]},
                                           {"role": "user", "content": "Schema error: " + attempts[-1]["error"] + ". Return the requested JSON object with all required keys, non-empty evidence strings, and valid values. Keep the same visual assessment; no markdown."}]
                            # generation helper accepts text-only follow-up content too.
                            output = backend.generate([retry], thinking=variant.get("thinking"), effort=variant.get("effort"))[0]
                        record["passes"].append({"region": region, "value": value, "attempts": attempts,
                                                 "prompt": task_prompt(region)})
                if any(p["value"] is None for p in record["passes"]):
                    record["status"] = "judge_parse_error"
                    failures += 1
                else:
                    global_ = next(p["value"] for p in record["passes"] if p["region"] is None)
                    record.update(status="ok", scores=simple.derive(global_))
            except Exception as error:
                record.update(status="judge_runtime_error", error=str(error), traceback=traceback.format_exc())
                failures += 1
                atomic_write_json(path, record)
                # Infrastructure errors must not silently produce a full table of model failures.
                raise
        record["completed_at"] = time.time()
        atomic_write_json(path, record)
    print(json.dumps({"rank": args.rank, "jobs": len(jobs), "judge_errors": failures,
                      "dry_run": args.dry_run, "run_id": run_id}), flush=True)
    return 2 if failures else 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    p.add_argument("--variants", nargs="+", choices=list(VARIANTS), default=["pair_v2"])
    p.add_argument("--rank", type=int, default=0)
    p.add_argument("--world-size", type=int, default=1)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--max-pixels", type=int, default=1024*1024)
    p.add_argument("--max-tokens", type=int, default=4096)
    p.add_argument("--max-model-len", type=int, default=16384)
    p.add_argument("--gpu-memory-utilization", type=float, default=0.85)
    p.add_argument("--thinking", action="store_true")
    p.add_argument("--reasoning-effort", choices=["low", "medium", "xhigh"], default="xhigh")
    p.add_argument("--split", choices=["all", "dev", "holdout"], default="all")
    p.add_argument("--limit", type=int)
    p.add_argument("--dry-run", action="store_true")
    sys.exit(run(p.parse_args()))


if __name__ == "__main__":
    main()
