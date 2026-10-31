"""Proposed fail-closed extraction of an existing contiguous public-text span."""

import re


def extract_ref(instruction, operation):
    text = instruction.rstrip().removesuffix(".")
    if operation == "replace":
        if not text.startswith("Replace ") or text.count(" with ") != 1:
            raise ValueError("Ambiguous replacement span")
        span = text[len("Replace ") : text.index(" with ")]
    elif operation == "attribute":
        match = re.fullmatch(r"Change the (?:color|texture|material|pattern) of (.+) to (.+)", text)
        if not match:
            raise ValueError("Unrecognized attribute grammar")
        span = match[1]
    elif operation == "remove":
        if not text.startswith("Remove "):
            raise ValueError("Unrecognized removal grammar")
        span = re.split(
            r" to (?:make|leave|reveal|expose|create|show|reduce|shorten)\b",
            text[len("Remove ") :],
            maxsplit=1,
        )[0]
    elif operation == "add":
        if not text.startswith("Add "):
            raise ValueError("Unrecognized addition grammar")
        if " sewn onto " in text:
            span = text.split(" sewn onto ", 1)[1]
        elif text.count(" on ") == 1:
            span = text.split(" on ", 1)[1]
        else:
            raise ValueError("Ambiguous addition anchor; no automatic semantic inference")
    else:
        raise ValueError("Unsupported operation")
    if not span or span not in instruction:
        raise ValueError("Extracted ref is not an exact public-text span")
    return span
