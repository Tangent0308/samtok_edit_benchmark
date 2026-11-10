"""Narrow syntax repairs: never invent, reorder, or replace model region codes."""

import json
import re

SPAN = re.compile(r"<\|mt_start\|><\|mt_[0-9]{4}\|><\|mt_[0-9]{4}\|><\|mt_end\|>")


def recover_answer(raw, request):
    from samtok_edit21.pass1.protocol import parse_answer

    original = parse_answer(raw, request)
    if original["complete"]:
        return {"parsed": original, "repaired_text": raw, "repairs": []}
    if original["errors"] != ["invalid_json"]:
        raise ValueError(f"Not an unambiguous JSON syntax failure: {original['errors']}")
    text, changes = raw, []
    for rule, pattern, replacement in (
        (
            "missing_mask_key_after_label",
            r'"label"\s*:\s*"(U[1-5])"\s*:\s*("<\|mt_start\|>)',
            r'"label":"\1","mask_2d":\2',
        ),
        (
            "duplicated_label_literal",
            r'"label"\s*:\s*"label"\s*:\s*"(U[1-5])"',
            r'"label":"\1"',
        ),
    ):
        text, count = re.subn(pattern, replacement, text)
        if count:
            changes.append({"rule": rule, "count": count})
    if not changes or SPAN.findall(raw) != SPAN.findall(text):
        raise ValueError("Repair may not alter or create any region code")
    parsed = parse_answer(text, request)
    if not parsed["complete"]:
        raise ValueError(f"Narrow repair does not yield a complete answer: {parsed['errors']}")
    return {"parsed": parsed, "repaired_text": text, "repairs": changes}


def enumeration_lines(raw):
    text = raw.strip().removesuffix("<|im_end|>").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not 2 <= len(lines) <= 5:
        raise ValueError("Expected 2-5 separate individual removal instructions")
    units = []
    for i, line in enumerate(lines, 1):
        match = re.fullmatch(rf"U{i}:\s*(remove\s+.+)", line, re.I)
        if not match or "<|" in line:
            raise ValueError("Invalid per-instance instruction line")
        units.append(match[1])
    if len(set(units)) != len(units):
        raise ValueError("Duplicate instance instructions")
    return units


def enumeration_json(raw):
    from samtok_benchmark.external_compbench.multitarget.adapters import parse_enumeration

    return parse_enumeration(raw)


def enumeration_bullets(raw):
    text = raw.strip().removesuffix("<|im_end|>").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not 2 <= len(lines) <= 5:
        raise ValueError("Expected 2-5 separate source instances")
    units = []
    for line in lines:
        match = re.fullmatch(r"[-*]\s+(.+)", line)
        if not match or "<|" in line:
            raise ValueError("Expected only one singular object description per bullet")
        phrase = match[1]
        units.append(phrase if phrase.lower().startswith("remove ") else "remove " + phrase)
    if len(set(units)) != len(units):
        raise ValueError("Duplicate instance descriptions")
    return units


def enumeration_decisions(raw):
    text = raw.strip().removesuffix("<|im_end|>").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    units = []
    for line in lines:
        match = re.fullmatch(r"(REMOVE|KEEP)\s*\|\s*(.+)", line)
        if not match or "<|" in line:
            raise ValueError("Expected a per-instance REMOVE or KEEP decision")
        if match[1] == "REMOVE":
            units.append("remove " + match[2])
    if not 2 <= len(units) <= 5 or len(set(units)) != len(units):
        raise ValueError("Expected 2-5 distinct selected objects")
    return units


def enumeration_semicolons(raw):
    text = raw.strip().removesuffix("<|im_end|>").strip()
    items = [part.strip() for part in text.split(";")]
    if not 2 <= len(items) <= 5 or any(not item or "\n" in item or "<|" in item for item in items):
        raise ValueError("Expected 2-5 semicolon-separated individual descriptions")
    if len(set(items)) != len(items):
        raise ValueError("Duplicate descriptions")
    return [part if part.lower().startswith("remove ") else "remove " + part for part in items]


def jsonable(value):
    return json.loads(json.dumps(value, ensure_ascii=False))
