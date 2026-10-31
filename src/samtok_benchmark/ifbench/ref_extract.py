"""Public-text-only deterministic referring spans; unknown grammar fails closed.

Rules were checked on public dev instructions before any dev quality scoring.
No manifest, target category, private reference, image or model output is read.
"""

import re

from .smoke_ref_extract import extract_ref as smoke_extract


def extract_ref(instruction, operation):
    try:
        return smoke_extract(instruction, operation)
    except ValueError:
        pass
    text = instruction.rstrip().removesuffix(".")
    span = None
    if operation == "attribute":
        match = re.fullmatch(r"Change the finish of (.+) to (.+)", text)
        if match:
            span = match[1]
        else:
            match = re.fullmatch(r"Tint (.+) (?:pale green|light blue|dark green|deep blue)", text)
            if match:
                span = match[1]
    elif operation == "add" and text.startswith("Add "):
        # A preceding "on a short pole" may describe the NEW accessory. The first
        # definite attachment/support phrase identifies an existing source anchor.
        matches = list(
            re.finditer(
                r" (?:sewn onto|attached to|hanging from|pinned to|on|in|to|across|around|along) (the\b)",
                text,
            )
        )
        if matches:
            span = text[matches[0].start(1) :]
    elif operation == "replace" and text.startswith("Replace "):
        # Source modifiers such as "with crutches" or "with its sole facing ..."
        # must remain in the target phrase. A destination starts with an article.
        matches = list(re.finditer(r" with (?:a|an)\b", text))
        if matches:
            boundary = matches[0].start()
            if len(matches) > 1:
                between = text[matches[0].end() : matches[1].start()]
                if " immediately behind " in between:
                    boundary = matches[1].start()
            span = text[len("Replace ") : boundary]
    if not span or span not in instruction:
        raise ValueError("Unresolved public referring phrase; no private-field fallback")
    return span
