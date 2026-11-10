"""Frozen SITEdit components with the trained multi-unit request and renderer."""

import json
import time

import numpy as np
from PIL import Image

from samtok_benchmark.external_refedit import adapters as original
from samtok_benchmark.external_refedit.data import immutable, read, verify_public
from samtok_benchmark.external_refedit.placement import place
from samtok_benchmark.io import digest
from .text import validate_enumeration

ENUMERATION_PROMPT = """Decompose this removal instruction into separate source-image object selections.
Use only the image and instruction. Identify every individual object the instruction selects,
excluding every object it says to keep. Do not change the operation or add edits.
Return a JSON array in left-to-right order (top-to-bottom to break ties). Each element must
contain exactly "label" (U1, U2, ...) and "instruction" (one removal instruction identifying
one selected object using its visible appearance or position). Return 2 to 5 elements.
Do not output mask tokens, coordinates, commentary, Markdown or alternative candidates.
Instruction: """


def enumerate_native(grounder, image, instruction, maximum):
    """One authorized extra greedy call using exactly the same Pass1 model/LoRA.

    The normal mask request is unchanged and follows this call. Enumeration is
    never inferred from private task masks, captions or another model's output.
    """
    import torch
    from samtok_edit21.pass1.model import adapter_enabled
    from samtok_edit21.pass1.protocol import EMPTY_THINK

    text = ENUMERATION_PROMPT + instruction
    messages = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": text}]}]
    prefix = (
        grounder.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        + EMPTY_THINK
    )
    inputs = {
        k: v.to(grounder.device)
        for k, v in grounder.processor(
            text=[prefix], images=[image.convert("RGB")], return_tensors="pt"
        ).items()
    }
    tick = time.monotonic()
    with torch.inference_mode(), adapter_enabled(grounder.model, True):
        grounder.model.model.rope_deltas = None
        ids = grounder.model.generate(
            **inputs, max_new_tokens=maximum, do_sample=False, use_cache=True
        )
    raw = grounder.processor.tokenizer.decode(
        ids[0, inputs["input_ids"].shape[1] :], skip_special_tokens=False
    )
    return {
        "prompt": text,
        "raw": raw,
        "seconds": time.monotonic() - tick,
        "do_sample": False,
        "max_new_tokens": maximum,
        "adapter_enabled": True,
    }


def parse_enumeration(raw):
    text = raw.strip()
    if text.endswith("<|im_end|>"):
        text = text[: -len("<|im_end|>")].rstrip()

    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("Duplicate key in native enumeration")
            obj[key] = value
        return obj

    return validate_enumeration(json.loads(text, object_pairs_hook=unique))


def unit_request(instructions):
    from samtok_edit21.pass1.protocol import VERSION, validate_request

    return validate_request(
        {
            "protocol": VERSION,
            "coordinate_system": "normalized_0_1000",
            "targets": [
                {"label": f"U{i}", "instruction": sentence, "has_ref": True, "locator": "none"}
                for i, sentence in enumerate(instructions, 1)
            ],
        }
    )


def multi_prompt(public, tokens):
    """Native training renderer; code U_i can only attach to instruction U_i."""
    from samtok_edit21.preparation.round2_data import multi_edit_prompt

    verify_public(public)
    units = tokens["units"]
    if not 2 <= len(units) <= 5 or tokens["original_instruction"] != public["instruction"]:
        raise ValueError("Multi-unit tokens do not bind to the original public instruction")
    sentences, placements = [], []
    for i, unit in enumerate(units, 1):
        if unit["id"] != f"U{i}":
            raise ValueError("Pass1 and S2 unit ordering differs")
        if unit["token"]:
            sentence, placement = place(unit["instruction"], unit["token"])
            placements.append({"id": unit["id"], **placement})
        else:
            sentence = unit["instruction"]
            placements.append({"id": unit["id"], "rule": "native_text_fallback"})
        sentences.append(sentence)
    guided = any(unit["token"] for unit in units)
    placement = {
        "renderer": "samtok_edit21.preparation.round2_data.multi_edit_prompt",
        "units": placements,
        "decomposition_digest": tokens["decomposition_digest"],
    }
    return multi_edit_prompt(sentences), placement if guided else None, guided


class MultiTokens(original.SITTokens):
    def __init__(self, config):
        super().__init__(config)
        self.plan = read(config["benchmark"]["multitarget_plan"])
        if self.plan["digest"] != digest({k: v for k, v in self.plan.items() if k != "digest"}):
            raise ValueError("Decomposition plan changed")
        self.by_id = {r["case_id"]: r for r in self.plan["cases"]}

    def run(self, public, out, previous=None):
        from samtok_edit21.pass1.protocol import valid_span

        verify_public(public)
        row = self.by_id[public["case_id"]]
        if (
            row["instruction"] != public["instruction"]
            or row["public_digest"] != public["input_digest"]
        ):
            raise ValueError("Public source/instruction differs from the frozen decomposition")
        instructions = row["units"]
        image = Image.open(public["source"]["path"]).convert("RGB")
        extra = None
        if row["mode"] == "native_enumeration":
            extra = enumerate_native(
                self.models.grounder,
                image,
                public["instruction"],
                self.method["pass1_max_new_tokens"],
            )
            # Save before parsing: even an invalid native answer is auditable.
            immutable(out / "enumeration.json", extra)
            instructions = parse_enumeration(extra["raw"])
        request = unit_request(instructions)
        immutable(out / "request.json", request)
        tick = time.monotonic()
        answer = self.models.grounder.ground(
            image, request, max_new_tokens=self.method["pass1_max_new_tokens"]
        )
        ground_seconds = time.monotonic() - tick
        immutable(out / "answer.json", {"raw": answer["raw"], "parsed": answer["parsed"]})
        units, decoded_calls = [], 0
        for i, sentence in enumerate(instructions, 1):
            uid = f"U{i}"
            span = answer["parsed"]["spans"].get(uid)
            valid = bool(span and valid_span(span))
            area = None
            if valid:
                decoded = self.models.codec.decode_strict(image.convert("RGBA"), span)[0] > 0
                area = float(decoded.mean())
                Image.fromarray(np.asarray(decoded, dtype=np.uint8) * 255).save(out / f"{uid}.png")
                decoded_calls += 1
            units.append(
                {
                    "id": uid,
                    "instruction": sentence,
                    "token": span if valid else None,
                    "source": "pass1" if valid else "fallback_text",
                    "decoded_area": area,
                }
            )
        return None, {
            "native": {
                "units": units,
                "original_instruction": public["instruction"],
                "decomposition_digest": digest(instructions),
                "request": request,
                "raw": answer["raw"],
                "parsed": answer["parsed"],
                "ground_seconds": ground_seconds,
                "enumeration": extra,
                "fallback_units": sum(u["token"] is None for u in units),
            },
            "calls": {
                "grounder_requests": 1,
                "enumeration_requests": int(extra is not None),
                "codec_encode": 0,
                "diagnostic_codec_decode": decoded_calls,
            },
        }


def build(model, stage, config, root):
    if model != "sitedit":
        raise ValueError("This correction must not alter or rerun baselines")
    return MultiTokens(config) if stage == "tokens" else original.SITEditor(config)
