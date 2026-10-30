"""Approved v2.1 input corrections; native model implementations stay unchanged."""

from copy import deepcopy
import inspect

from samtok_benchmark.io import digest
from .render import COLOR_NAMES

REVISION = "fairness-v2.1-dev20"
MICE_TOKEN_LIMIT = 200
MICE_HEADER = (
    "U marks select source objects, parts, or attachment points. "
    "Remove all marks; keep everything else unchanged."
)


def revise_request(model, original):
    """Change only Qwen21 resolution and the MICE annotation preamble."""
    request = deepcopy(original)
    if model == "qwen21":
        request["parameters"]["output_resolution"] = 2048
    elif model == "mice" and any(u["locator"] == "point" for u in request["public_units"]):
        global_units = [u for u in request["public_units"] if u["locator"] in {"none", "point"}]
        regional = [u for u in request["public_units"] if u["locator"] in {"box", "mask"}]
        if [u["id"] for u in global_units] != request["global_unit_ids"]:
            raise ValueError("MICE global unit routing changed")
        if regional != request["regional_units"]:
            raise ValueError("MICE local unit routing changed")
        lines = []
        for unit in global_units:
            mark = (
                f" [{COLOR_NAMES[int(unit['id'][1:]) - 1]} point, label {unit['id']}]"
                if unit["locator"] == "point"
                else ""
            )
            lines.append(f"{unit['id']}.{mark} {unit['instruction']}")
        segments = [MICE_HEADER + "\n" + "\n".join(lines)]
        segments.extend(u["instruction"] for u in regional)
        if any("$BREAKFLAG$" in u["instruction"] for u in request["public_units"]):
            raise ValueError("Public instruction contains the native MICE segment separator")
        request["prompt"] = "$BREAKFLAG$".join(segments)
        request.pop("request_digest", None)
        request["request_digest"] = digest(request)
    return request


class MiceTextOverflow(ValueError):
    def __init__(self, audit):
        self.audit = audit
        failed = [s["index"] for s in audit["segments"] if not s["within_limit"]]
        super().__init__(f"MICE native 200-token condition would truncate segments {failed}")


def verify_mice_native_defaults(pipe):
    parameters = inspect.signature(pipe._get_qwen3_prompt_embeds).parameters
    for name in ("num_global_text_tokens", "num_instance_text_tokens"):
        if parameters[name].default != MICE_TOKEN_LIMIT:
            raise ValueError(f"MICE native default changed: {name}")


def mice_text_audit(tokenizer, prompt, expected_segments):
    """Count the real native chat tokens, before either native truncation.

    The native call omits add_special_tokens (therefore uses the tokenizer's
    default). Match it here, including assistant/thinking template tokens.
    Reject all overflows instead of guessing that only harmless text was lost.
    """
    if tokenizer.padding_side != "right":
        raise ValueError("MICE audit requires the pinned right-padding tokenizer")
    parts = prompt.split("$BREAKFLAG$")
    if len(parts) != expected_segments:
        raise ValueError("MICE prompt segments do not match native global/local bindings")
    segments = []
    for index, part in enumerate(parts):
        text = tokenizer.apply_chat_template(
            [{"role": "user", "content": part}],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        ids = tokenizer(text, padding=False, truncation=False)["input_ids"]
        native = tokenizer(text, padding="max_length", truncation=True, max_length=512)
        retained = [
            token
            for token, present in zip(
                native["input_ids"][:MICE_TOKEN_LIMIT],
                native["attention_mask"][:MICE_TOKEN_LIMIT],
                strict=True,
            )
            if present
        ]
        segments.append(
            {
                "index": index,
                "role": "global" if index == 0 else "local",
                "chat_tokens": len(ids),
                "native_kept_tokens": MICE_TOKEN_LIMIT,
                "within_limit": len(ids) <= MICE_TOKEN_LIMIT and retained == ids,
                "native_prefix_matches_complete_text": retained == ids,
                "text_digest": digest(part),
                "input_ids_digest": digest(ids),
            }
        )
    audit = {
        "policy": "mice-native-200-complete-chat-v1",
        "prompt_digest": digest(prompt),
        "native_max_sequence_length": 512,
        "effective_segment_limit": MICE_TOKEN_LIMIT,
        "padding_side": tokenizer.padding_side,
        "segments": segments,
        "tokenizer_class": type(tokenizer).__name__,
        "chat_template_digest": digest(getattr(tokenizer, "chat_template", None)),
        "all_segments_complete": all(s["within_limit"] for s in segments),
        "new_inference_calls": 0,
    }
    if not audit["all_segments_complete"]:
        raise MiceTextOverflow(audit)
    return audit
