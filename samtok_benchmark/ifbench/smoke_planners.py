"""Native planners on public S1 / missing-region S5 instructions only."""

import argparse
import json
from pathlib import Path
import sys
import time
import traceback

from PIL import Image

from samtok_benchmark.io import sha256_file, write_json
from .smoke_suite import SHARED, SOURCES, MODELS, ROOT, load_request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", choices=["replan", "mirage"])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args()
    import torch

    torch.set_num_threads(4)
    torch.manual_seed(42)
    call_count = [0]
    root = args.root / "planners" / args.model
    root.mkdir(parents=True, exist_ok=True)
    if args.model == "mirage":
        sys.path.insert(0, str(SOURCES / "mirage"))
        from mirage.vlm import load_vlm, parse_instructions, to_pixels

        vlm = load_vlm("qwen35", str(MODELS / "Qwen3.5-9B"), "cuda", torch.bfloat16)
        original_chat = vlm.chat
        traces = []

        def chat(batch, max_new_tokens=512):
            call_count[0] += 1
            result = original_chat(batch, max_new_tokens)

            def serial(value):
                if isinstance(value, Image.Image):
                    p = root / f"trace_image_{len(list(root.glob('trace_image_*.png'))):04d}.png"
                    value.save(p)
                    return {"path": str(p), "sha256": sha256_file(p)}
                if isinstance(value, dict):
                    return {k: serial(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [serial(v) for v in value]
                return value

            traces.append(
                {
                    "batch": serial(batch),
                    "max_new_tokens": max_new_tokens,
                    "do_sample": False,
                    "response": result,
                }
            )
            return result

        vlm.chat = chat
    else:
        sys.path.insert(0, str(SOURCES / "replan"))
        from replan.pipelines.replan import RePlanPipeline
        from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor

        vlm = RePlanPipeline.__new__(RePlanPipeline)
        vlm.init_vlm = True
        vlm.stage_offload = "none"
        vlm.sync_cuda_for_timing = True
        vlm.device = "cuda"
        checkpoint = "/tmp/ifbench/weights/RePlan-Qwen2.5-VL-7B"
        vlm.vlm_model = (
            Qwen2_5_VLForConditionalGeneration.from_pretrained(
                checkpoint,
                torch_dtype=torch.bfloat16,
                attn_implementation="sdpa",
                local_files_only=True,
            )
            .to("cuda")
            .eval()
        )
        vlm.processor = AutoProcessor.from_pretrained(checkpoint, local_files_only=True)
        vlm.template = (SOURCES / "replan/replan/pipelines/prompt_template/replan.txt").read_text()
        write_json(
            root / "environment.json",
            {
                "planner_revision": "518f82339520058d043c4fbc270481876d8463e4",
                "attention_backend": "sdpa",
                "engineering_deviation": "Official constructor requests FlashAttention2; unavailable locally. Same full-attention computation via PyTorch SDPA; no generation/prompt parameters changed.",
                "template_sha256": sha256_file(
                    SOURCES / "replan/replan/pipelines/prompt_template/replan.txt"
                ),
            },
        )
    cases = (
        sorted(json.loads((SHARED / "plan/splits.json").read_text())["dev"])
        if args.dev
        else json.loads((SHARED / "example_selection.json").read_text())["case_ids"]
    )
    for cid in cases:
        for setting in ("S1", "S5"):
            task = {"case_id": cid, "setting": setting}
            req, _, native = load_request(task)
            missing = [u for u in req["units"] if u["locator"] == "none"]
            if not missing:
                continue
            p = root / f"{cid}--{setting}.json"
            if p.exists():
                continue
            marker = p.with_suffix(".started.json")
            if marker.exists():
                write_json(
                    p,
                    {
                        "status": "failed",
                        "input_digest": req["input_digest"],
                        "error": "Planner interrupted; no automatic resampling",
                        "extra_planner_calls": None,
                    },
                )
                continue
            # For S5 each missing unit has its own native planning request, ensuring unambiguous binding.
            groups = [missing] if setting == "S1" else [[u] for u in missing]
            record = {
                "input_digest": req["input_digest"],
                "model": args.model,
                "case_id": cid,
                "setting": setting,
                "groups": [],
                "extra_planner_calls": 0,
            }
            source = Image.open(req["source"]["path"]).convert("RGB")
            start = time.monotonic()
            call_count[0] = 0
            write_json(marker, {"time": time.time(), "seed": 42})
            try:
                for units in groups:
                    torch.manual_seed(42)
                    instruction = (
                        "Apply all of the following edits to the image. Keep everything else unchanged.\n"
                        + "\n".join(f"{u['id']}. {u['instruction']}" for u in units)
                    )
                    group = {"unit_ids": [u["id"] for u in units], "instruction": instruction}
                    if args.model == "mirage":
                        before = len(traces)
                        pairs = parse_instructions(vlm, [instruction])[0]
                        if len(pairs) != len(units):
                            raise ValueError(
                                f"Native parser returned {len(pairs)} edits for {len(units)} units; do not drop or invent units"
                            )
                        boxes = vlm.locate([source] * len(pairs), [ref for ref, _ in pairs])
                        regions = []
                        for u, (ref, inst), box in zip(units, pairs, boxes, strict=True):
                            if box is None:
                                raise ValueError("Native planner returned no box")
                            regions.append(
                                {
                                    "unit_id": u["id"],
                                    "refer_object": ref,
                                    "new_instruction": inst,
                                    "bbox": list(to_pixels(box, source.size, padding=10)),
                                    "padding_applied": 10,
                                }
                            )
                        group.update(regions=regions, traces=traces[before:])
                        record["extra_planner_calls"] += len(traces) - before
                    else:
                        call_count[0] += 1
                        text, _ = vlm.get_vlm_response(instruction, source)
                        regions = vlm.extract_bbox_from_response(text)
                        if not isinstance(regions, list) or not regions:
                            raise ValueError("Native planner produced no valid regions")
                        # S1 retains the native complete plan; S5 requires exactly one region for one missing unit.
                        if setting == "S5" and len(regions) != 1:
                            raise ValueError("S5 missing-unit plan has ambiguous region binding")
                        group.update(
                            response=text,
                            regions=regions,
                            global_prompt=vlm.extract_gen_image_prompt(text),
                            template=vlm.template,
                            max_new_tokens=2048,
                        )
                        record["extra_planner_calls"] += 1
                    record["groups"].append(group)
                record["status"] = "planned"
            except Exception as exc:
                record.update(status="failed", error=repr(exc), traceback=traceback.format_exc())
                traceback.print_exc()
            record["extra_planner_calls"] = call_count[0]
            record["wall_seconds"] = time.monotonic() - start
            write_json(p, record)
            print(cid, setting, record["status"], flush=True)


if __name__ == "__main__":
    main()
