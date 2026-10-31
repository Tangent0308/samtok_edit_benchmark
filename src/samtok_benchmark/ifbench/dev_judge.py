"""Canonical, input-format-blind dev Judge with immutable evidence/output binding."""

import argparse
import importlib.metadata
import json
from pathlib import Path
import time
from types import SimpleNamespace

from PIL import Image

from samtok_benchmark.io import digest, read_jsonl, sha256_file, write_json
from samtok_benchmark.v2.evaluation import RUBRIC as OLD_RUBRIC
from samtok_benchmark.v2.judge import Backend, OUTPUT_FORMAT, parse, _fit, _outlined
from samtok_benchmark.v2.inputs import COLORS
from .dev_plan import ROOT, SMOKE, read
from .smoke_suite import SHARED, MODELS
from . import MANIFEST_SHA256
from .dev_scope import active_plan

REPO = Path(__file__).resolve().parents[2]
DATA = Path("/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2")
MODEL = MODELS / "Qwen3.8-Flash-Next-FP8"
PROTOCOL = "ifbench.canonical-epq.v1"
RUBRIC = OLD_RUBRIC.replace(
    " A no-ref instruction still names a part type; its supplied locator chooses the instance.", ""
)
VIEWS_NOTE = """Images show the clean SOURCE and the actual OUTPUT, followed by fixed-coordinate
source/output detail crops for every canonical edit. Additional crops explicitly labeled with
EVALUATOR contour show the source selector mask; ignore these evaluator-drawn lines themselves.
The selector identifies an existing object, part or addition anchor, not the allowed output-difference
boundary. Use the canonical edit and its legal effect contract to judge completion and preservation.
The editor's input representation, model and configuration are intentionally not provided.
Unrequested labels, outlines, points or overlays visible in the plain OUTPUT are artifacts; evaluate
their preservation/quality impact from the image, without assuming how they were produced."""


def cases():
    path = REPO / "data/v2_2.6.0/cases.jsonl"
    assert sha256_file(path) == MANIFEST_SHA256
    dev = set(read(SHARED / "plan/splits.json")["dev"])
    return {c["id"]: c for c in read_jsonl(path) if c["id"] in dev}


def canonical(case):
    # Explicit whitelist; no editor request, variant, model, has_ref or locator.
    return {
        "units": [
            {
                "id": u["id"],
                "operation": u["operation"],
                "instruction": u["instruction_ref"],
                "completion_requirement": u["completion_requirement"],
                "edit_contract": u.get("edit_contract", {}),
                "preserve": u["preserve"],
            }
            for u in case["units"]
        ]
    }


def prompt(case):
    return (
        RUBRIC
        + "\n"
        + VIEWS_NOTE
        + "\n\nCANONICAL TASK:\n"
        + json.dumps(canonical(case), ensure_ascii=False)
        + "\n\n"
        + OUTPUT_FORMAT
    )


def evidence(case, output_path):
    source_path = DATA / case["source"]["image"]
    assert sha256_file(source_path) == case["source"]["sha256"]
    source = Image.open(source_path).convert("RGB")
    output = Image.open(output_path).convert("RGB")
    assert source.size == output.size == tuple(case["source"]["size"])
    images = [
        ("SOURCE: clean original (full)", _fit(source, 1024**2)),
        ("OUTPUT: actual edited result (full)", _fit(output, 1024**2)),
    ]
    w, h = source.size
    for u in case["units"]:
        mask = DATA / u["target"]["mask"]
        assert sha256_file(mask) == u["target"]["mask_sha256"]
        x1, y1, x2, y2 = u["target"]["box"]
        pad = max(12, round(max(x2 - x1, y2 - y1) * 0.25))
        box = (max(0, x1 - pad), max(0, y1 - pad), min(w, x2 + pad), min(h, y2 + pad))
        a, b = source.crop(box), output.crop(box)
        color = COLORS[int(u["id"][1:]) - 1]
        for label, image in [
            ("SOURCE", a),
            ("OUTPUT", b),
            ("SOURCE with EVALUATOR contour", _outlined(a, mask, box, color)),
            ("OUTPUT with EVALUATOR contour", _outlined(b, mask, box, color)),
        ]:
            images.append((f"{u['id']} fixed crop {box}: {label}", _fit(image, 512**2)))
    content = []
    for label, image in images:
        content += [{"type": "text", "text": label}, {"type": "image", "image": image}]
    content.append({"type": "text", "text": prompt(case)})
    return [{"role": "user", "content": content}]


def fingerprint():
    return {
        "protocol": PROTOCOL,
        "model": str(MODEL),
        "revision": read(MODEL / "download_record.json")["revision"],
        "packages": {
            k: importlib.metadata.version(k) for k in ("torch", "vllm", "transformers", "Pillow")
        },
        "prompt_digest": digest([RUBRIC, VIEWS_NOTE, OUTPUT_FORMAT]),
        "source_sha256": sha256_file(Path(__file__)),
        "views": {
            "full_max_pixels": 1024**2,
            "crop_max_pixels": 512**2,
            "crop_pad": ".25 longest selector-box side, minimum 12px",
            "contours": "same source-mask contour on source and output crops",
        },
        "decode": {"temperature": 0, "seed": 0, "max_tokens": 12288, "reasoning_effort": "low"},
        "engine": {
            "tensor_parallel_size": 8,
            "expert_parallel": True,
            "max_model_len": 49152,
            "batch_size": 16,
            "gpu_memory_utilization": 0.85,
        },
    }


def binding(case, output_sha, config):
    return digest(
        {
            "source_sha256": case["source"]["sha256"],
            "canonical": canonical(case),
            "masks": [u["target"]["mask_sha256"] for u in case["units"]],
            "output_sha256": output_sha,
            "judge_config": config,
        }
    )


def records(probe=False):
    if probe:
        selection = read(SHARED / "example_selection.json")["case_ids"]
        paths = [SMOKE / "qwen2511/runs" / f"{cid}--S3-mask--dual/result.json" for cid in selection]
    else:
        plan = active_plan()
        paths = [ROOT / "runs" / t["key"] / "result.json" for t in plan["tasks"]]
    for path in paths:
        if path.exists():
            r = read(path)
            if r["status"] == "generated":
                assert sha256_file(Path(r["output_image"])) == r["output_sha256"]
                yield path, r


def run(probe=False, limit=None, dry_run=False):
    config = fingerprint()
    run_id = digest(config)
    root = ROOT / "judge" / run_id
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "config.json", config)
    write_json(ROOT / "judge/current.json", {"run_id": run_id, "config": str(root / "config.json")})
    by_case = cases()
    pending = {}
    bindings = []
    for path, r in records(probe):
        case = by_case[r["task"]["case_id"]]
        key = binding(case, r["output_sha256"], config)
        bindings.append({"record": str(path), "key": key})
        if not (root / "records" / f"{key}.json").exists():
            pending[key] = (case, r)
    items = list(pending.items())
    if limit is not None:
        items = items[:limit]
    write_json(root / ("probe_bindings.json" if probe else "bindings.json"), bindings)
    if dry_run:
        for key, (case, r) in items:
            evidence(case, r["output_image"])
        print(json.dumps({"dry_run": True, "jobs": len(items), "run_id": run_id}), flush=True)
        return
    args = SimpleNamespace(
        model=MODEL, **config["engine"], max_tokens=12288, reasoning_effort="low"
    )
    backend = Backend(args, 22) if items else None
    for i in range(0, len(items), args.batch_size):
        batch = items[i : i + args.batch_size]
        conv = [evidence(c, r["output_image"]) for _, (c, r) in batch]
        tick = time.monotonic()
        outs = backend.generate(conv)
        elapsed = time.monotonic() - tick
        for (key, (case, r)), answer in zip(batch, outs, strict=True):
            result = {
                "key": key,
                "run_id": run_id,
                "output_sha256": r["output_sha256"],
                "raw_response": answer,
                "status": "unparsed",
                "batch_wall_seconds": elapsed,
                "batch_size": len(batch),
            }
            try:
                if answer["finish_reason"] == "length":
                    raise ValueError("Truncated Judge response")
                value, repaired = parse(answer["text"], [u["id"] for u in case["units"]])
                result.update(status="scored", scores=value, repaired_json=repaired)
            except (ValueError, KeyError, TypeError) as exc:
                result.update(status="judge-failed", reason=str(exc))
            write_json(root / "records" / f"{key}.json", result)
        print(
            json.dumps(
                {
                    "judge_completed": min(i + len(batch), len(items)),
                    "judge_pending_initial": len(items),
                    "run_id": run_id,
                }
            ),
            flush=True,
        )
    write_json(
        root / ("probe_completed.json" if probe else "completed.json"),
        {"jobs_this_run": len(items), "record_bindings": len(bindings), "run_id": run_id},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--probe", action="store_true")
    p.add_argument("--limit", type=int)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    run(a.probe, a.limit, a.dry_run)
