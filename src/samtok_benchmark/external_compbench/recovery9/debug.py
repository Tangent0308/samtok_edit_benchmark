"""Native prompt diagnostics. Uses public inputs only, with every trial retained."""

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import time

from PIL import Image

from samtok_benchmark.external_pair.worker import guard
from samtok_benchmark.external_refedit.data import immutable, read, verify_public
from samtok_benchmark.io import sha256_file
from .parsing import (
    enumeration_bullets,
    enumeration_decisions,
    enumeration_json,
    enumeration_lines,
    enumeration_semicolons,
    recover_answer,
)

PROMPTS = {
    "terse_list": """Look at the photo. Name only the individual objects selected for removal by the instruction. Describe each instance by its distinct position. Honor all color restrictions and exclusions. Answer in one short line: separate individual descriptions with semicolons. No JSON, labels, mask tokens, examples or explanations.
Instruction: """,
    "inventory_decisions": """Inspect all physical objects relevant to the instruction. Make an individual REMOVE or KEEP decision for each visible instance. This is an inventory of object instances, not a segmentation task.
Check the category and the object's predominant BODY color. A mostly white body with black spots is not a black body. When the instruction excludes the right one, mark the rightmost matching instance KEEP. Mark nonmatching instances KEEP. Only instances that satisfy every condition may be marked REMOVE. Distinguish each body by position, do not duplicate one body or imagine hidden objects.
Output exactly one line per relevant visible instance, using either:
REMOVE | a short singular object description including its visible position
KEEP | a short singular object description including its visible position
Use the actual number of visible instances. No headings, bullets, JSON, mask tokens, or explanations. Do not output the format examples literally.
Instruction: """,
    "selection_filter": """List the individual physical objects that satisfy the removal instruction in this photo. Apply every modifier and exclusion before listing anything.
For a color modifier, use the predominant color of the object's body, not a small contrasting patch. For an exclusion such as 'except the right one', first identify the matching objects and exclude the rightmost matching object. Do not list excluded objects or objects that fail the color or category condition.
Output only a short bullet list. Each bullet describes exactly one selected object using a singular noun and its distinct visible position. Do not merge multiple instances, duplicate one body, invent unseen objects, or enumerate separate parts of one body. A partially visible selected body counts once. No JSON, labels, segmentation codes or commentary. Stop after the last actual selected instance.
Removal instruction: """,
    "brief_positions": """Examine the photo and the removal instruction below. Which individual physical objects does the instruction select for removal?
Answer with a short bullet list, one singular object description per bullet. Distinguish objects by visible position. Count bodies, not body parts. Include partially visible selected objects. Exclude objects that must be kept. Never list the same object twice, never invent an unseen object, and stop when all selected objects have been listed.
Only output the bullet list. No JSON, labels, mask tokens, explanations or examples. Each bullet must refer to exactly one physical object in this photo.
Removal instruction: """,
    "individual_lines": """Look carefully at the image. Your task is to describe the individual objects selected by the removal instruction, not to output segmentation tokens.
List EVERY selected physical object separately. Several objects of the same kind must occupy separate lines. Exclude any object that the instruction says to keep. Use a singular noun and a visible position or appearance to distinguish each individual. Order selected objects from left to right.
Answer ONLY in this format, with one line per individual object and consecutive labels:
U1: remove the [one individual object, described by its position or appearance]
U2: remove the [another individual object, described by its position or appearance]
Continue U3, U4, U5 only if more selected objects are visible. Do not list groups. Do not output mask tokens or JSON. Do not copy the collective instruction as one item.
Removal instruction: """,
    "individual_json": """Identify each separate physical instance selected by the instruction in this image. Return an editing checklist, not segmentation masks. Each checklist item removes exactly ONE instance. Use singular object descriptions with distinguishing visible positions. Preserve exclusions in the instruction. Do not describe objects to keep.
Return a JSON array with consecutive labels U1, U2, ... in left-to-right order, and exactly two fields per item: "label" and "instruction". Each instruction must begin with "remove" and describe a single instance, never a plural group. Do not put mask tokens in either field. Do not copy the original plural instruction into one item.
Count actual physical bodies in the image, not their separate parts. A partially visible body is still one object; do not invent unseen objects. Stop immediately after the last selected object. Describe the position of each selected object explicitly, and ensure that no two entries describe the same object.
Instruction: """,
}


def run(control, output, variant):
    if os.environ.get("CUDA_VISIBLE_DEVICES") not in {"4", "5", "6", "7"}:
        raise RuntimeError("Only an idle authorized local GPU 4-7 may be used")
    guard()
    control, output = Path(control), Path(output)
    cfg, plan = read(control / "configuration.json"), read(control / "PLAN.json")
    sys.path.insert(0, str(Path(cfg["paths"]["sitedit_source"]) / "src"))
    from samtok_edit21.pass1.grounder import Pass1Grounder
    from samtok_edit21.pass1.model import adapter_enabled
    from samtok_edit21.pass1.protocol import EMPTY_THINK
    import torch

    from samtok_benchmark.external_compbench.multitarget.adapters import unit_request

    method = cfg["sitedit"]
    print("Loading original Pass1 model and LoRA", flush=True)
    grounder = Pass1Grounder(
        method["pass1_adapter"], base_model=method["samtok"], max_pixels=method["pass1_max_pixels"]
    )
    for row in plan["cases"]:
        if row["case_id"] not in plan["native_enumeration_case_ids"]:
            continue
        directory = output / variant / row["case_id"]
        if (directory / "RESULT.json").exists():
            continue
        public = read(row["public"])
        verify_public(public)
        image = Image.open(public["source"]["path"]).convert("RGB")
        prompt = PROMPTS[variant] + public["instruction"]
        messages = [
            {"role": "user", "content": [{"type": "image"}, {"type": "text", "text": prompt}]}
        ]
        prefix = (
            grounder.processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            + EMPTY_THINK
        )
        inputs = {
            k: v.to(grounder.device)
            for k, v in grounder.processor(
                text=[prefix], images=[image], return_tensors="pt"
            ).items()
        }
        immutable(
            directory / "REQUEST.json",
            {
                "case_id": row["case_id"],
                "public_sha256": sha256_file(row["public"]),
                "prompt": prompt,
                "variant": variant,
                "method": method,
                "source_sha256": sha256_file(public["source"]["path"]),
                "debug_source_sha256": sha256_file(__file__),
                "time": datetime.now(timezone.utc).isoformat(),
                "gpu": os.environ["CUDA_VISIBLE_DEVICES"],
                "do_sample": False,
                "max_new_tokens": 512,
                "adapter_enabled": True,
            },
        )
        tick = time.monotonic()
        with torch.inference_mode(), adapter_enabled(grounder.model, True):
            grounder.model.model.rope_deltas = None
            ids = grounder.model.generate(
                **inputs, max_new_tokens=512, do_sample=False, use_cache=True
            )
        raw = grounder.processor.tokenizer.decode(
            ids[0, inputs["input_ids"].shape[1] :], skip_special_tokens=False
        )
        record = {
            "raw": raw,
            "seconds": time.monotonic() - tick,
            "generated_tokens": int(ids.shape[1] - inputs["input_ids"].shape[1]),
        }
        immutable(directory / "ENUMERATION.json", record)
        try:
            units = {
                "individual_lines": enumeration_lines,
                "individual_json": enumeration_json,
                "brief_positions": enumeration_bullets,
                "selection_filter": enumeration_bullets,
                "inventory_decisions": enumeration_decisions,
                "terse_list": enumeration_semicolons,
            }[variant](raw)
            request = unit_request(units)
            answer = grounder.ground(image, request, max_new_tokens=512)
            immutable(directory / "GROUNDING.json", {"request": request, "answer": answer})
            repaired = recover_answer(answer["raw"], request)
            record.update(status="completed", units=units, grounding=repaired)
        except (ValueError, KeyError, TypeError) as error:
            record.update(status="native_failure", error=repr(error))
        immutable(directory / "RESULT.json", record)
        print(row["case_id"], record, flush=True)
