"""Where SITEdit's region token goes in a free-form RefEdit-Bench instruction.

The method's ``place_token`` puts the token right after the selector phrase of a protocol-2.0 template sentence and
needs the operation to find that phrase. RefEdit-Bench instructions are free text (imperatives and questions), so this
adapter derives a placement class from the public instruction text only, then:

* uses the method's own ``selector_end`` for template-like imperatives (remove/add at the end, replace before the last
  " with ", attribute before the last " to " of the first clause), and
* adds three deterministic rules the template grammar lacks: questions "Can/Could <selector> be ...?" (token before
  " be "), "... <selector> into <value>" (token before the last " into "), and "Give <selector> a/an <object>"
  (token before the last article).

Anything else falls back to the end of the sentence (before the final punctuation). The rule name is recorded with
every request. No mask, no category and no scoring field is read here.
"""

from __future__ import annotations

import re

VERBS = {
    "remove": ("remove", "delete", "erase", "eliminate", "get rid of", "take away", "take out", "clear away"),
    "add": ("add", "put", "place", "insert", "attach", "draw", "include"),
    "replace": ("replace", "swap", "substitute", "exchange"),
    "attribute": ("change", "turn", "make", "paint", "color", "colour", "recolor", "recolour", "dye",
                  "convert", "transform", "switch", "alter", "modify", "tint"),
    "give": ("give",),
}
QUESTION = re.compile(r"^(can|could|would|will|should|may)\s+(?!you\b|we\b|i\b)(?P<rest>.+?)\s+(be|become|look)\b",
                      re.IGNORECASE)
YOU = re.compile(r"^(?:can|could|would|will)\s+you\s+(?:please\s+)?", re.IGNORECASE)
PLEASE = re.compile(r"^please\s+", re.IGNORECASE)


def _end(text):
    """Index before the final sentence punctuation (and trailing spaces)."""
    end = len(text.rstrip())
    while end and text[end - 1] in ".?!":
        end -= 1
    return len(text[:end].rstrip())


def _verb_class(text):
    lowered = text.lower()
    for name, verbs in VERBS.items():
        for verb in verbs:
            if lowered.startswith(verb + " ") or lowered == verb:
                return name
    return None


def selector_index(instruction):
    """(insert index, placement class, operation passed to the method rule or None, rule name)."""
    from samtok_edit21.evaluation.ifbench import selector_end

    question = QUESTION.match(instruction)
    if question:
        return question.end("rest"), "question_be", None, "question_be"
    offset = 0
    prefix = YOU.match(instruction) or PLEASE.match(instruction)
    if prefix:
        offset = prefix.end()
    body = instruction[offset:]
    stop = _end(body)
    core = body[:stop]          # without final punctuation; the method rule also ignores a final "."
    kind = _verb_class(core)
    if kind in ("remove", "add"):
        return offset + selector_end(core + ".", kind, True), kind, kind, f"{kind}_end"
    if kind == "replace":
        if " with " in core:
            return offset + selector_end(core + ".", "replace", True), kind, "replace", "replace_with"
        return offset + stop, kind, None, "replace_end"
    if kind == "attribute":
        first = core.split(" and its ")[0]
        into = [m.start() for m in re.finditer(r" into ", first)]
        if into:
            return offset + into[-1], kind, None, "attribute_into"
        if re.search(r" to ", first) or re.match(r"^(Make) (.+) (transparent|translucent|opaque)$", core) \
                or core.startswith("Tint "):
            return offset + selector_end(core + ".", "attribute", True), kind, "attribute", "attribute_method"
        return offset + stop, kind, None, "attribute_end"
    if kind == "give":
        articles = [m.start() for m in re.finditer(r" (a|an|some) ", core)]
        if articles:
            return offset + articles[-1], kind, None, "give_before_object"
        return offset + stop, kind, None, "give_end"
    return offset + stop, "other", None, "fallback_end"


def place(instruction, span):
    """The original instruction with the token inserted after its selector phrase; nothing else changes."""
    index, kind, operation, rule = selector_index(instruction)
    if not 0 < index <= len(instruction):
        raise ValueError(f"Invalid token position for {instruction!r}")
    text = instruction[:index] + " " + span + instruction[index:]
    return text, {"rule": rule, "class": kind, "method_operation": operation, "index": index}
