"""Lossless recovery of complete E/P/Q objects; never infer or fill a score."""

import json
import re

from samtok_benchmark.external_compbench.vlm_judge.common import digest
from samtok_benchmark.external_compbench.vlm_judge.rubric import parse

RULE = "lossless-complete-epq-structure-recovery.v1"


class ObjectPairs(list):
    """Distinguish object fields (including duplicates) from JSON arrays."""


def unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        value[key] = unique_pairs(item) if isinstance(item, ObjectPairs) else item
    return value


def root_comma(text, index):
    stack, quoted, escaped = [], False, False
    for char in text[:index]:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]":
            if not stack or stack.pop() != ("{" if char == "}" else "["):
                return False
    return not quoted and stack == ["{"] and text[index] == ","


def recover(answer):
    if answer.get("finish_reason") != "stop":
        raise ValueError("Only complete, normally stopped answers may be recovered")
    try:
        parse(answer)
    except (ValueError, TypeError, KeyError):
        pass
    else:
        raise ValueError("Already valid; no recovery permitted")
    text = answer["text"].split("</think>")[-1].strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    corrected, span, removed, rules = text, None, "", []
    # Both a complete empty key and its unfinished opening quote contain no value.
    match = re.search(r'(,\s*(?:""|")\s*)(})\s*$', text)
    if match:
        if not root_comma(text, match.start(1)):
            raise ValueError("Dangling token is not at root-object level")
        start, end = match.span(1)
        span, removed = [start, end], text[start:end]
        corrected = text[:start] + text[end:]
        rules.append("remove_final_valueless_empty_key")
    decoded = json.loads(corrected, object_pairs_hook=ObjectPairs)
    if not isinstance(decoded, ObjectPairs):
        raise ValueError("Expected a root JSON object")
    fields, summaries, notes = {}, {}, {}
    for key, value in decoded:
        if key in ("E", "P", "Q"):
            if isinstance(value, ObjectPairs):
                if key in fields:
                    raise ValueError(f"Multiple full score objects for {key}")
                fields[key] = unique_pairs(value)
            elif type(value) is int:
                if key in summaries:
                    raise ValueError(f"Multiple scalar summaries for {key}")
                summaries[key] = value
            else:
                raise ValueError(f"Ambiguous score-field value for {key}")
        elif key in ("E_note", "P_note", "Q_note") and isinstance(value, str) and value.strip():
            if key in notes:
                raise ValueError(f"Duplicate auxiliary note: {key}")
            notes[key] = value
        else:
            raise ValueError(f"Unsupported extra root field: {key!r}")
    if set(fields) != {"E", "P", "Q"}:
        raise ValueError("All three complete score/evidence objects are required")
    for key, value in summaries.items():
        if type(fields[key].get("score")) is not int or fields[key]["score"] != value:
            raise ValueError(f"Conflicting duplicate scalar score: {key}")
    if summaries:
        rules.append("discard_identical_scalar_summary")
    if notes:
        rules.append("retain_auxiliary_notes_outside_score_schema")
    if not rules:
        raise ValueError("No approved structural recovery applies")
    normalized = json.dumps(fields, ensure_ascii=False) if summaries or notes else corrected
    result = parse({**answer, "text": normalized})
    if any(result[k] != fields[k] for k in ("E", "P", "Q")):
        raise ValueError("Parser altered a score or evidence")
    return {
        "rule": RULE,
        "applied_rules": rules,
        "original_json_digest": digest(text),
        "corrected_json_digest": digest(normalized),
        "removed_span": span,
        "removed_text": removed,
        "identical_scalar_summaries": summaries,
        "retained_auxiliary_notes": notes,
        "corrected_json": normalized,
        "scores": result,
    }
