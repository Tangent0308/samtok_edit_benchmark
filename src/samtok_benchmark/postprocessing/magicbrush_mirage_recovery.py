"""Separate, bounded recovery of failed MIRAGE plans; frozen records remain read-only.

This is an explicitly changed error-handling policy, not an upstream MIRAGE release.
Only public source pixels and the original instruction enter the native Qwen3.5 VLM.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

from samtok_benchmark.external_magicbrush.data import immutable, read
from samtok_benchmark.io import digest, sha256_file

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
OLD = NAS / "experiments2/SAMTokEdit/external_magicbrush/run_001"
BUNDLE = NAS / ".ifbench-tmp/magicbrush_20261105/bundle"
SOURCES = NAS / ".ifbench-tmp/fairness-v2-dev20-20261030/assets/sources"
REPO = Path(__file__).resolve().parents[3]
METRICS = ("L1", "L2", "CLIP-I", "DINO", "CLIP-T")
PROMPT = """You are MIRAGE's image-editing planner. Read the source image and the original
editing instruction. Return a nonempty list of paired local editing instructions and regions.
For each atomic edit, give exactly one record with refer_object, new_instruction, and bbox_2d.
refer_object describes the existing image region to edit; new_instruction is a complete
imperative retaining the requested action, objects, attributes, and relationships.
Use a plain-language phrase, never coordinate numbers, for refer_object.
Copy the original instruction when there is only one action. For multiple actions, split
only the existing requested actions. Preserve quantities and degree. Do not invent colors,
sizes, species, or extra requirements in new_instruction that the original does not request.
Do not lose any requested edit, add any unrequested edit, or split an action solely because
it mentions two interacting objects. Preserve qualifiers identifying the intended object.
For adding a new object, do NOT try to detect the nonexistent object. Select a plausible
placement region in the visible source scene, honoring any location in the instruction.
Include enough room for the new object, and describe that existing placement region in
refer_object. The new_instruction must still describe the requested new object.
For removal, replacement, or an attribute change, localize the existing target. For a
requested group, include the requested group. Prefer a localized editable region.
bbox_2d is [x_min, y_min, x_max, y_max], normalized to 0..1000 in this full source image.
Return ONLY valid JSON, no explanation, using this exact schema:
{"regions":[{"refer_object":"existing target or placement region",
"new_instruction":"complete edit instruction","bbox_2d":[100,100,500,500]}]}"""
POLICY = {
    "version": "magicbrush.mirage.recovery.v1",
    "scope": "mask-free independent single-turn; original terminal plan failures only",
    "paired_plan_prompt": PROMPT,
    "paired_plan_calls": 1,
    "max_new_tokens": 2048,
    "thinking": False,
    "do_sample": False,
    "truncated_locator": "reuse parsed pairs; repeat native locate with 2048 tokens",
    "editor": "unchanged frozen MirageEditor; 40 steps, CFG 4, patch ratio 0.4, seed 42",
    "selection": "all original failures; no quality/score selection or resampling",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def proof(path):
    return {"path": str(path), "sha256": sha256_file(path)}


def check(entry):
    if sha256_file(entry["path"]) != entry["sha256"]:
        raise ValueError(f"Changed artifact: {entry['path']}")


def decode(text):
    value = text.strip()
    if value.startswith("```") and value.endswith("```"):
        value = value.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(value)


def validate_regions(value):
    if not isinstance(value, dict) or set(value) != {"regions"}:
        raise ValueError("Recovery answer must contain only regions")
    rows = value["regions"]
    if not isinstance(rows, list) or not rows or len(rows) > 32:
        raise ValueError("Expected 1..32 paired edit regions")
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"refer_object", "new_instruction", "bbox_2d"}:
            raise ValueError("Unpaired edit or unknown fields")
        for key in ("refer_object", "new_instruction"):
            if not isinstance(row[key], str) or not row[key].strip():
                raise ValueError("Empty edit or target")
        box = row["bbox_2d"]
        if (
            not isinstance(box, list)
            or len(box) != 4
            or any(
                isinstance(v, bool)
                or not isinstance(v, (float, int))
                or not math.isfinite(v)
                or not 0 <= v <= 1000
                for v in box
            )
        ):
            raise ValueError("Box is not finite normalized XYXY")
        if not (box[0] < box[2] and box[1] < box[3]):
            raise ValueError("Box has nonpositive extent")
    return rows


def region_records(rows, size):
    from mirage.vlm import to_pixels

    return [
        {
            "unit_id": "composite",
            "refer_object": row["refer_object"],
            "new_instruction": row["new_instruction"],
            "bbox_normalized_xyxy": row["bbox_2d"],
            "bbox": dict(
                zip(
                    ("x1", "y1", "x2", "y2"),
                    to_pixels(row["bbox_2d"], size, padding=10),
                    strict=True,
                )
            ),
        }
        for row in validate_regions({"regions": rows})
    ]


def prepare(destination, audit, cases=None):
    from samtok_benchmark.external_magicbrush.worker import source_identity

    destination = Path(destination)
    records = read(audit)["records"]
    index = read(BUNDLE / "index.json")
    public_index = {r["case_id"]: r for r in index["cases"] if r["track"] == "mask-free"}
    if cases and not set(cases) <= {r["key"].split("/")[-1] for r in records}:
        raise ValueError("Smoke must select original failures")
    items = []
    for r in records:
        case = r["key"].split("/")[-1]
        if cases and case not in cases:
            continue
        old = read(r["result"])
        if old["status"] != "failed" or old["identity"]["stage"] != "plan":
            raise ValueError("Only terminal native planner failures can be recovered")
        if source_identity() != old["identity"]["source_code"]:
            raise ValueError("Frozen scientific code differs from original")
        item = public_index[case]
        public = read(item["public"])
        if public["input_digest"] != old["identity"]["public_digest"]:
            raise ValueError("Changed original public request")
        check({"path": item["public"], "sha256": item["public_sha256"]})
        check(public["source"])
        old_edit = OLD / "runs/mirage/edit" / r["key"] / "result.json"
        if read(old_edit)["status"] != "failed":
            raise ValueError("Refusing to replace an original successful generation")
        items.append(
            {
                "case_id": case,
                "key": r["key"],
                "session_id": item["session_id"],
                "public": proof(item["public"]),
                "geometry": item["geometry"],
                "original_plan": proof(r["result"]),
                "original_edit": proof(old_edit),
                "original_traces": proof(r["traces"]),
                "failure_category": r["category"],
                "strategy": "native_long_locator"
                if "JSONDecodeError" in r["category"]
                else "paired_visual_plan",
            }
        )
    config = read(OLD / "CONFIG.json")
    config["paths"]["sources"] = str(SOURCES)
    native = {
        str(p.relative_to(SOURCES / "mirage")): sha256_file(p)
        for p in sorted((SOURCES / "mirage").rglob("*.py"))
    }
    manifest = {
        "schema": "magicbrush.mirage.recovery.manifest.v1",
        "policy": POLICY,
        "items": items,
        "configuration_digest": digest(config),
        "original_configuration": proof(OLD / "CONFIG.json"),
        "frozen_source_code": source_identity(),
        "native_source_code": native,
        "recovery_code": proof(Path(__file__).resolve()),
        "bundle_index": proof(BUNDLE / "index.json"),
        "scope": "smoke" if cases else "full",
        "created": now(),
    }
    manifest["digest"] = digest(manifest)
    immutable(destination / "CONFIG.json", config)
    immutable(destination / "MANIFEST.json", manifest)
    return {"path": str(destination), "requests": len(items), "digest": manifest["digest"]}


def verify_manifest(root):
    manifest, config = read(root / "MANIFEST.json"), read(root / "CONFIG.json")
    if manifest["digest"] != digest({k: v for k, v in manifest.items() if k != "digest"}):
        raise ValueError("Manifest digest mismatch")
    if digest(config) != manifest["configuration_digest"] or manifest["policy"] != POLICY:
        raise ValueError("Recovery configuration/policy changed")
    check(manifest["recovery_code"])
    for name, sha in manifest["frozen_source_code"].items():
        check({"path": REPO / name, "sha256": sha})
    for name, sha in manifest["native_source_code"].items():
        check({"path": SOURCES / "mirage" / name, "sha256": sha})
    return manifest, config


def gpu_gate():
    value = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if value not in {"4", "5", "6", "7"}:
        raise ValueError("Recovery worker must see one of local GPUs 4..7")
    fields = (
        subprocess.check_output(
            [
                "nvidia-smi",
                "-i",
                value,
                "--query-gpu=memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            text=True,
        )
        .strip()
        .split(",")
    )
    used, free = map(int, fields)
    if used > 2300 or free < 70000:
        raise RuntimeError(f"GPU {value} occupied: {used} MiB; do not stop other processes")


def serial_messages(value, source):
    from PIL import Image

    if isinstance(value, Image.Image):
        # All new visual-plan messages use the public source. Native part crops are saved below.
        return {
            "public_source": source,
            "size": list(value.size),
            "rgb_sha256": hashlib.sha256(value.convert("RGB").tobytes()).hexdigest(),
        }
    if isinstance(value, list):
        return [serial_messages(v, source) for v in value]
    if isinstance(value, dict):
        return {k: serial_messages(v, source) for k, v in value.items()}
    return value


def recover_plan(vlm, public, item, out):
    from PIL import Image

    source = Image.open(public["source"]["path"]).convert("RGB")
    traces, original_chat = [], vlm.chat

    def chat(batch, max_new_tokens=2048):
        trace = {
            "messages": serial_messages(batch, public["source"]),
            "max_new_tokens": max_new_tokens,
            "do_sample": False,
            "started": now(),
        }
        tick = time.monotonic()
        try:
            response = original_chat(batch, max_new_tokens=max_new_tokens)
            trace.update(response=response, status="answered")
            return response
        except Exception as exc:
            trace.update(status="failed", error=repr(exc))
            raise
        finally:
            trace["seconds"] = time.monotonic() - tick
            traces.append(trace)

    vlm.chat = chat
    try:
        if item["strategy"] == "native_long_locator":
            from types import SimpleNamespace
            from mirage.vlm import parse_instructions

            parser_trace = read(item["original_traces"]["path"])[0]
            cached_parser = SimpleNamespace(chat=lambda *args, **kwargs: parser_trace["response"])
            pairs = parse_instructions(cached_parser, [public["instruction"]])[0]
            vlm.grounding_tokens = POLICY["max_new_tokens"]
            boxes = vlm.locate([source.copy() for _ in pairs], [r[0] for r in pairs])
            rows = [
                {"refer_object": pair[0], "new_instruction": pair[1], "bbox_2d": box}
                for pair, box in zip(pairs, boxes, strict=True)
            ]
        else:
            batch = [
                [
                    {"role": "system", "content": [{"type": "text", "text": PROMPT}]},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "image": source},
                            {"type": "text", "text": public["instruction"]},
                        ],
                    },
                ]
            ]
            rows = validate_regions(decode(vlm.chat(batch, POLICY["max_new_tokens"])[0]))
        return {"regions": region_records(rows, source.size), "additional_vlm_calls": len(traces)}
    finally:
        vlm.chat = original_chat
        immutable(out / "traces.json", traces)


def worker(root, stage, shard, shards, cache):
    root = Path(root)
    manifest, config = verify_manifest(root)
    if not 0 <= shard < shards:
        raise ValueError("Invalid shard")
    gpu_gate()
    import torch

    torch.set_num_threads(4)
    sys.path.insert(0, str(SOURCES / "mirage"))
    stop = []
    signal.signal(signal.SIGUSR1, lambda *_: stop.append(True))
    signal.signal(signal.SIGTERM, lambda *_: stop.append(True))
    engine, private, counts = None, None, Counter()
    for item in manifest["items"][shard::shards]:
        if stop:
            break
        case, key = item["case_id"], item["key"]
        out = root / stage / case
        path = out / "result.json"
        if path.exists():
            previous = read(path)
            if previous["manifest_digest"] != manifest["digest"]:
                raise ValueError("Existing terminal belongs to another manifest")
            if previous.get("output"):
                check(previous["output"])
            counts["reused"] += 1
            continue
        if (out / "ADMITTED.json").exists():
            raise RuntimeError(f"Unknown admission must be resolved explicitly: {out}")
        for field in ("public", "original_plan", "original_edit", "original_traces"):
            check(item[field])
        public = read(item["public"]["path"])
        from samtok_benchmark.external_magicbrush.bundle import verify_public

        verify_public(public)
        check(public["source"])
        if public["mask"] is not None or public["track"] != "mask-free":
            raise ValueError("Recovery accepts public mask-free inputs only")
        dependency = root / ("plan" if stage == "edit" else "edit") / case / "result.json"
        prior = read(dependency) if stage != "plan" else None
        if prior and prior["status"] != "completed":
            immutable(
                path,
                {
                    "status": "upstream_failed",
                    "case_id": case,
                    "manifest_digest": manifest["digest"],
                    "dependency": proof(dependency),
                },
            )
            counts["upstream_failed"] += 1
            continue
        if engine is None:
            tick = time.monotonic()
            if stage == "plan":
                from mirage.vlm import load_vlm

                engine = load_vlm(
                    "qwen35",
                    str(Path(config["paths"]["models"]) / "Qwen3.5-9B"),
                    "cuda",
                    torch.bfloat16,
                )
            elif stage == "edit":
                from samtok_benchmark.external_magicbrush.adapters import MirageEditor

                engine = MirageEditor("mirage", "edit", config, root / "native")
            else:
                from samtok_benchmark.external_magicbrush.metrics import Features

                private_path = BUNDLE / "private/evaluation.json"
                check(
                    {
                        "path": private_path,
                        "sha256": read(BUNDLE / "index.json")["evaluation_sha256"],
                    }
                )
                private = {r["case_id"]: r for r in read(private_path)}
                engine = Features(config, Path(cache) / f"shard-{shard}", "cuda")
                old_scorer = read(OLD / "scores/mirage/mask-free/independent/139-1/score.json")[
                    "identity"
                ]["scorer"]
                if engine.identity != old_scorer:
                    raise ValueError("Recovery scorer differs from original scorer")
            print(
                json.dumps({"stage": stage, "loaded_seconds": time.monotonic() - tick}), flush=True
            )
        identity = {
            "manifest_digest": manifest["digest"],
            "stage": stage,
            "case_id": case,
            "key": key,
            "public": item["public"],
            "gpu": os.environ["CUDA_VISIBLE_DEVICES"],
            "started": now(),
            "pid": os.getpid(),
            "dependency": proof(dependency) if prior else None,
        }
        immutable(out / "ADMITTED.json", identity)
        record, tick = dict(identity), time.monotonic()
        torch.cuda.reset_peak_memory_stats()
        try:
            if stage == "plan":
                with torch.inference_mode():
                    record["native"] = recover_plan(engine, public, item, out)
            elif stage == "edit":
                from samtok_benchmark.ifbench.canvas import restore_output

                raw, detail = engine.run(public, out, previous=prior["native"])
                raw.save(out / "raw.png")
                restore_output(raw, item["geometry"]).save(out / "output.png")
                record.update(
                    raw=proof(out / "raw.png"), output=proof(out / "output.png"), detail=detail
                )
            else:
                truth = private[case]
                check(prior["output"])
                check(truth["target"])
                record.update(
                    output=prior["output"],
                    target=truth["target"],
                    caption=truth["local_description"],
                    scorer=engine.identity,
                )
                record["metrics"] = engine.score(
                    prior["output"]["path"], truth["target"]["path"], truth["local_description"]
                )
            torch.cuda.synchronize()
            record["status"] = "completed"
        except Exception as exc:
            record.update(status="failed", error=repr(exc), traceback=traceback.format_exc())
        record.update(
            seconds=time.monotonic() - tick,
            finished=now(),
            peak_allocated_bytes=torch.cuda.max_memory_allocated(),
            peak_reserved_bytes=torch.cuda.max_memory_reserved(),
            packages={
                n: importlib.metadata.version(n) for n in ("torch", "transformers", "Pillow")
            },
        )
        immutable(path, record)
        counts[record["status"]] += 1
        print(
            json.dumps(
                {
                    "stage": stage,
                    "case": case,
                    "status": record["status"],
                    "seconds": record["seconds"],
                    "error": record.get("error"),
                }
            ),
            flush=True,
        )
        if record["status"] == "failed" and any(
            s in record.get("error", "").lower() for s in ("cuda", "out of memory", "nvlink")
        ):
            raise RuntimeError("Fatal GPU error; stop this worker")
    return dict(counts)


def report(root):
    import numpy as np
    from samtok_benchmark.external_magicbrush.report import bootstrap

    root = Path(root)
    manifest, _ = verify_manifest(root)
    if manifest["scope"] != "full" or len(manifest["items"]) != 138:
        raise ValueError("Full report requires the complete frozen set of original failures")
    recovered = {item["case_id"]: item for item in manifest["items"]}
    index = read(BUNDLE / "index.json")
    items = [r for r in index["cases"] if r["track"] == "mask-free"]
    sessions = read(OLD / "RUN.json")["session_ids"]
    sid_index = {s: i for i, s in enumerate(sessions)}
    old_scorer = read(OLD / "scores/mirage/mask-free/independent/139-1/score.json")["identity"][
        "scorer"
    ]

    def one(item):
        case = item["case_id"]
        key = f"mask-free/independent/{case}"
        if case in recovered:
            p = root / "score" / case / "result.json"
            row = read(p)
            if row["manifest_digest"] != manifest["digest"]:
                raise ValueError("Recovered score belongs to different policy")
            if row["status"] == "completed":
                if row["scorer"] != old_scorer:
                    raise ValueError("Scorers differ")
                check(row["output"])
                check(row["dependency"])
                metrics, kind = row["metrics"], "recovered_measured"
            else:
                gen = read(root / "edit" / case / "result.json")
                if gen["status"] == "completed":
                    raise ValueError(
                        "A scoring miss cannot be replaced by generation failure penalty"
                    )
                metrics = dict(zip(METRICS, (1, 1, -1, -1, -1), strict=True))
                kind = "generation_failure_penalty"
        else:
            p = OLD / "scores/mirage" / key / "score.json"
            row = read(p)
            gen_path = OLD / "runs/mirage/edit" / key / "result.json"
            gen = read(gen_path)
            if row["status"] != "scored" or gen["status"] != "completed":
                raise ValueError("Expected original successful output and score")
            if row["identity"]["generation_receipt_sha256"] != sha256_file(gen_path):
                raise ValueError("Original score binding changed")
            if row["identity"]["scorer"] != old_scorer:
                raise ValueError("Original scorer differs")
            check({"path": gen["output_image"], "sha256": row["identity"]["output_sha256"]})
            metrics, kind = row["metrics"], "original_measured"
        return {
            "case_id": case,
            "session_id": item["session_id"],
            "key": key,
            "metrics": {m: metrics[m] for m in METRICS},
            "contribution_kind": kind,
            "score_record": proof(p),
        }

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(one, items))
    if len(rows) != 1053 or len({r["case_id"] for r in rows}) != 1053:
        raise ValueError("Full coverage mismatch")
    sums, counts = np.zeros((len(sessions), 5)), np.zeros(len(sessions))
    for row in rows:
        i = sid_index[row["session_id"]]
        sums[i] += [row["metrics"][m] for m in METRICS]
        counts[i] += 1
    draws = np.random.default_rng(20261105).integers(
        0, len(sessions), (10000, len(sessions)), dtype=np.int32
    )
    values = bootstrap(sums, counts, draws)
    means = sums.sum(axis=0) / counts.sum()
    result = {
        "schema": "magicbrush.mirage.recovery.report.v1",
        "model": "mirage",
        "setting": "mask-free independent single-turn",
        "requests": len(rows),
        "manifest": proof(root / "MANIFEST.json"),
        "coverage": dict(Counter(r["contribution_kind"] for r in rows)),
        "metrics": {
            m: {"mean": float(means[i]), "CI95": np.quantile(values[:, i], [0.025, 0.975]).tolist()}
            for i, m in enumerate(METRICS)
        },
        "bootstrap": {
            "seed": 20261105,
            "draws": 10000,
            "sessions": sessions,
            "indices_sha256": hashlib.sha256(draws.tobytes()).hexdigest(),
        },
        "per_case": rows,
    }
    immutable(root / "REPORT.json", result)
    return {k: v for k, v in result.items() if k not in {"per_case", "bootstrap"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "plan", "edit", "score", "report"])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument(
        "--cache", type=Path, default=Path("/tmp/ifbench/magicbrush_mirage_recovery_metrics")
    )
    args = parser.parse_args()
    if args.action == "prepare":
        result = prepare(args.root, args.audit, args.cases)
    elif args.action == "report":
        result = report(args.root)
    else:
        result = worker(args.root, args.action, args.shard, args.shards, args.cache)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
