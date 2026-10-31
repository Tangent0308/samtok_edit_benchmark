"""Visual instruction audit; advisory evidence, never silently rewrites frozen tasks."""

import argparse
import json
import time
import hashlib
from pathlib import Path
from samtok_benchmark.paths import repository_root
from PIL import Image, ImageDraw, ImageOps

PROMPT = """Audit one benchmark task against the actual source pixels. Image 1 is the clean full scene. Image 2 contains aligned clean crop (LEFT), binary source mask (MIDDLE: white selected, black excluded), and isolated selected pixels (RIGHT). Gray outside pixels is annotation, not an object color. Source mask selects an existing object/part; holes and occluders are NOT selected.
Check the Ref phrase identifies this exact visible instance unambiguously among rivals. It may use a short ordinal, image-side, color or belonging relation only if true. For named subparts, a host mask is allowed, but requested part must belong to that host. No-ref MUST retain edit content and local site, removing only source-instance localization. For add: source mask is direct host/site, not future new object silhouette; new item must have natural contact/support. A nearby exception requires direct placement to be unnatural plus unique adjacent supported site. Do not reject small, partial or unusual-but-plausible edits only for taste. Replace requires a distinct category/form, not color alone. Remove clothing/parts is allowed when remaining scene/body can be natural; removing an attached body limb is not. Text should be concise but necessary modifiers are allowed.
Return JSON: {"ref_correct":true/false,"unambiguous":true/false,"scope_correct":true/false,"natural":true/false,"category_correct":true/false,"pair_equivalent":true/false,"issues":["concrete source evidence only"],"suggestion":"short correction if needed"}. Do not invent a defect just to give feedback. Judge ONLY source/instruction, no edited output is supplied.
Task: """


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--shard", type=int, required=True)
    p.add_argument("--shards", type=int, default=8)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    repo = repository_root()
    raw = (repo / "data/v2/cases.jsonl").read_bytes()
    cases = [json.loads(line) for line in raw.splitlines()]
    jobs = [(n, c, u) for n, c in enumerate(cases, 1) for u in c["units"]]
    jobs = [x for i, x in enumerate(jobs) if i % a.shards == a.shard]
    from transformers import AutoProcessor
    from vllm import LLM, SamplingParams
    from vllm.sampling_params import StructuredOutputsParams

    model = "/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/Qwen3.8-27B"
    processor = AutoProcessor.from_pretrained(model)
    llm = LLM(
        model=model,
        tensor_parallel_size=1,
        dtype="bfloat16",
        max_model_len=12288,
        max_num_seqs=8,
        max_num_batched_tokens=8192,
        gpu_memory_utilization=0.85,
        enforce_eager=True,
        trust_remote_code=True,
        limit_mm_per_prompt={"image": 2, "video": 0},
        mm_encoder_attn_backend="TORCH_SDPA",
    )
    flags = [
        "ref_correct",
        "unambiguous",
        "scope_correct",
        "natural",
        "category_correct",
        "pair_equivalent",
    ]
    schema = {
        "type": "object",
        "properties": {
            **{k: {"type": "boolean"} for k in flags},
            "issues": {"type": "array", "items": {"type": "string"}},
            "suggestion": {"type": "string"},
        },
        "required": flags + ["issues", "suggestion"],
        "additionalProperties": False,
    }
    params = SamplingParams(
        temperature=0, max_tokens=380, structured_outputs=StructuredOutputsParams(json=schema)
    )
    out = a.output / f"audit_{a.shard}.jsonl"
    start = time.time()
    for b in range(0, len(jobs), 8):
        info = []
        requests = []
        for n, c, u in jobs[b : b + 8]:
            src = Image.open(a.root / c["source"]["image"]).convert("RGB")
            m = Image.open(a.root / u["target"]["mask"]).convert("L")
            box = m.getbbox()
            pad = max(30, round(max(box[2] - box[0], box[3] - box[1]) * 0.55))
            box = (
                max(0, box[0] - pad),
                max(0, box[1] - pad),
                min(src.width, box[2] + pad),
                min(src.height, box[3] + pad),
            )
            iso = Image.new("RGB", src.size, (100, 100, 100))
            iso.paste(src, mask=m)
            panel = Image.new("RGB", (1440, 520), "#dddddd")
            d = ImageDraw.Draw(panel)
            for j, (im, label) in enumerate(
                [(src, "SOURCE"), (m.convert("RGB"), "MASK"), (iso, "SELECTED RGB")]
            ):
                im = ImageOps.contain(im.crop(box), (470, 480))
                panel.paste(im, (480 * j + (470 - im.width) // 2, 35 + (480 - im.height) // 2))
                d.text((480 * j + 5, 5), label, fill="black")
            scene = src.copy()
            scene.thumbnail((1280, 1280))
            task = {
                k: u[k]
                for k in ["instruction_ref", "instruction_noref", "operation", "instruction_spec"]
            }
            prompt = PROMPT + json.dumps(task, ensure_ascii=False)
            content = [{"type": "image", "image": im} for im in [scene, panel]] + [
                {"type": "text", "text": prompt}
            ]
            text = processor.apply_chat_template(
                [{"role": "user", "content": content}],
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
            requests.append({"prompt": text, "multi_modal_data": {"image": [scene, panel]}})
            info.append((n, c, u))
        outputs = llm.generate(requests, params, use_tqdm=False)
        with out.open("a") as f:
            for (n, c, u), o in zip(info, outputs):
                answer = o.outputs[0].text
                try:
                    r = json.loads(answer)
                except ValueError:
                    r = {"issues": ["malformed_audit_json"], "raw": answer}
                f.write(
                    json.dumps(
                        {
                            "case_number": n,
                            "case_id": c["id"],
                            "unit_id": u["id"],
                            "instruction_ref": u["instruction_ref"],
                            "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                            "model": model,
                            "audit": r,
                            "pass": all(r.get(k) is True for k in flags),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        print(
            json.dumps(
                {
                    "completed": min(b + 8, len(jobs)),
                    "total": len(jobs),
                    "seconds": time.time() - start,
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
