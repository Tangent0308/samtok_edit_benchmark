#!/usr/bin/env python3
"""Audit canonical scoring and replay MIRAGE's official parser/locator on recorded replies."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import textwrap
import time
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


def read(path):
    return json.loads(Path(path).read_text())


def pixel_identity(image):
    image = image.convert("RGB")
    return {"size": list(image.size), "pixels_sha256": hashlib.sha256(image.tobytes()).hexdigest()}


def normalize(value):
    if isinstance(value, Image.Image):
        return pixel_identity(value)
    if isinstance(value, dict):
        if {"path", "sha256", "size", "public_hint"} <= set(value):
            assert not value["public_hint"], "MIRA must not inject public spatial hints"
            return pixel_identity(Image.open(value["path"]))
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preview", type=Path, required=True)
    parser.add_argument("--gpu-replay", action="store_true")
    args = parser.parse_args()
    from samtok_benchmark.io import sha256_file
    from samtok_benchmark.external_mira.data import immutable, load_bundle, load_annotations, split_instruction
    config = read(REPO / "configs/external/mira.json")
    native = Path(config["paths"]["sources"]) / "mirage"
    evaluator = Path(read(REPO / "configs/external/mira_judge_gpt54.json")["source"])
    sys.path[:0] = [str(native), str(evaluator / "metrics")]
    from mirage.vlm import Qwen35, parse_instructions, to_pixels
    from inference import qwen_prompt
    from common import load_samples, polygon_mask, masked_pair
    args.output.mkdir(parents=True, exist_ok=True)
    args.preview.mkdir(parents=True, exist_ok=True)
    revision = config["model_specifications"]["mirage"]["method_commit"]
    checked_sources = {}
    for name in ("inference.py", "crop_image.py", "mirage/vlm.py", "mirage/geometry.py",
                 "mirage/composition.py", "mirage/qwen_image_edit.py"):
        url = f"https://raw.githubusercontent.com/ZiqianLiu666/MIRAGE/{revision}/{name}"
        with urllib.request.urlopen(url, timeout=60) as response:
            upstream = response.read()
        expected = hashlib.sha256(upstream).hexdigest()
        assert sha256_file(native / name) == expected, f"Native source differs: {name}"
        checked_sources[name] = expected
    index = load_bundle(args.root / "mira_bundle")
    canonical = {r["case_id"]: r for r in read(args.root / "mira_bundle/private/evaluation.json")}
    official = load_annotations(config["dataset_root"])
    masks_checked = 0
    for row in official:
        case = Path(row["image"]).stem
        value = canonical[case]
        assert value["mask"] == row["mask"]
        assert value["instructions"] == [u["instruction"] for u in split_instruction(row["editing_instruction"])]
        for mask in value["mask"]:
            assert polygon_mask(mask, tuple(value["source"]["size"])).sum() > 0
            masks_checked += 1
    results = []
    for case in ("001", "002"):
        run = args.root / f"mira_smoke{case}"
        public = read(args.root / "mira_bundle/public" / case / "public.json")
        plan = read(run / "mirage/plan" / case / "result.json")
        traces = read(run / "mirage/plan" / case / "traces.json")
        vlm = Qwen35.__new__(Qwen35)
        used = []

        def replay(batch, max_new_tokens=512):
            trace = traces[len(used)]
            assert max_new_tokens == trace["max_new_tokens"]
            assert normalize(batch) == normalize(trace["messages"]), "Official VLM prompt/image differs"
            assert trace["status"] == "returned"
            used.append(trace["index"])
            return trace["response"]

        vlm.chat = replay
        pairs = parse_instructions(vlm, [public["original_instruction"]])[0]
        source = Image.open(public["source"]["path"]).convert("RGB")
        boxes = vlm.locate([source.copy() for _ in pairs], [r[0] for r in pairs])
        assert len(used) == len(traces)
        records = [{"refer_object": ref, "new_instruction": instruction,
                    "bbox": dict(zip(("x1", "y1", "x2", "y2"), to_pixels(box, source.size, 10)))}
                   for (ref, instruction), box in zip(pairs, boxes, strict=True)]
        for expected, actual in zip(records, plan["native"]["regions"], strict=True):
            assert all(actual[k] == v for k, v in expected.items())
        call = read(run / "mirage/edit" / case / "call.json")
        assert call["image"] == public["source"]["path"]
        assert call["prompt"] == public["original_instruction"]
        assert call["sub_prompts"] == [qwen_prompt(r) for r in records]
        assert call["bboxes"] == [r["bbox"] for r in records]
        exports = []
        for model in ("qwen2511", "qwen21", "replan", "mirage", "sitedit"):
            directory = args.root / f"mira_smoke{case}_scores" / model
            samples = load_samples(directory / "annotations.jsonl", directory / "crop_instruction.jsonl")
            assert len(samples) == 1
            name, _, masks, edits = samples[0]
            assert masks == canonical[case]["mask"]
            assert list(edits.values()) == canonical[case]["instructions"]
            assert Image.open(directory / "source" / name).size == Image.open(directory / "edited" / name).size
            exports.append({"model": model, "annotation_sha256": sha256_file(directory / "annotations.jsonl"),
                            "text_sha256": sha256_file(directory / "crop_instruction.jsonl")})
        assert len({r["annotation_sha256"] for r in exports}) == 1
        assert len({r["text_sha256"] for r in exports}) == 1
        original = Image.open(canonical[case]["source"]["path"]).convert("RGB")
        preview = Image.new("RGB", (1500, 400), "white")
        draw = ImageDraw.Draw(preview)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        for i, (mask, text) in enumerate(zip(canonical[case]["mask"], canonical[case]["instructions"])):
            masked, _ = masked_pair(original, original, mask, "source-frame")
            thumb = ImageOps.contain(masked, (296, 240))
            preview.paste(thumb, (i * 300, 0))
            draw.multiline_text((i * 300 + 4, 250), f"{case} / U{i + 1}\n" +
                                "\n".join(textwrap.wrap(text, 35)), fill="black", font=font)
        preview.save(args.preview / f"{case}_judge_regions.png")
        results.append({"case": case, "official_trace_calls_replayed": len(used),
                        "official_planner_records_equal": True, "editor_call_equal": True,
                        "identical_scoring_inputs_across_methods": True, "exports": exports,
                        "legacy_call_planner_record_is_unused": call.get("planner_record"),
                        "actual_planner_result": str(run / "mirage/plan" / case / "result.json")})
    report = {"native_revision": revision, "native_sources_sha256": checked_sources,
              "bundle_digest": index["digest"], "sources": len(official), "nonempty_masks": masks_checked,
              "cases": results, "note": "Planner replay uses recorded replies; no new VLM inference or GT model inputs."}
    immutable(args.output / "PROTOCOL.json", report)
    if args.gpu_replay:
        # Re-run the pinned official editor directly, with the same recorded native plan and input.
        import torch
        from diffusers import QwenImageEditPlusPipeline
        from mirage.qwen_image_edit import run_qwen_image_edit
        target = args.output / "official_001_raw.png"
        if target.exists() or (args.output / "REPLAY_ADMITTED.json").exists():
            raise ValueError("Replay already admitted; inspect its receipt instead of resampling")
        immutable(args.output / "REPLAY_ADMITTED.json", {"case": "001", "seed": 42, "purpose": "native parity"})
        torch.set_num_threads(4)
        pipe = QwenImageEditPlusPipeline.from_pretrained(
            str(Path(config["paths"]["models"]) / "Qwen-Image-Edit-2511"),
            torch_dtype=torch.bfloat16, local_files_only=True).to("cuda")
        call = read(args.root / "mira_smoke001/mirage/edit/001/call.json")
        tick = time.monotonic()
        torch.manual_seed(42)
        with torch.inference_mode():
            image = run_qwen_image_edit(pipe, Image.open(call["image"]).convert("RGB"),
                call["prompt"], call["sub_prompts"], call["bboxes"], num_inference_steps=40,
                true_cfg_scale=4.0, patch_ratio=0.4, generator=torch.Generator("cuda").manual_seed(42))
        image.save(target)
        previous = args.root / "mira_smoke001/mirage/edit/001/raw.png"
        error = np.abs(np.asarray(image, dtype=np.int16) - np.asarray(Image.open(previous), dtype=np.int16))
        immutable(args.output / "REPLAY.json", {"case": "001", "seconds": time.monotonic() - tick,
            "official_sha256": sha256_file(target), "adapter_sha256": sha256_file(previous),
            "pixel_equal": bool((error == 0).all()), "mean_absolute_pixel_error": float(error.mean()),
            "max_absolute_pixel_error": int(error.max())})
    print(json.dumps({"sources": len(official), "masks": masks_checked, "protocol": "passed",
                      "replay": read(args.output / "REPLAY.json") if args.gpu_replay else None}))


if __name__ == "__main__":
    main()
