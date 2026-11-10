"""Compile public text, never private captions, masks, inverse edits or model scores.

These rules expand coordinated edits and explicit counts. An unknown plural count
requires the separately authorized native Pass1 enumeration; it is never guessed.
"""

import re

PLURALS = {
    "bears": "bear",
    "birds": "bird",
    "chickens": "chicken",
    "cows": "cow",
    "cranes": "crane",
    "dogs": "dog",
    "ducks": "duck",
    "flamingos": "flamingo",
    "geese": "goose",
    "giraffes": "giraffe",
    "goats": "goat",
    "men": "man",
    "monkeys": "monkey",
    "planes": "plane",
    "rabbits": "rabbit",
    "tigers": "tiger",
    "turtles": "turtle",
    "zebras": "zebra",
    "antelopes": "antelope",
    "fish": "fish",
    "sheep": "sheep",
}
HEADS = (
    set(PLURALS)
    | set(PLURALS.values())
    | {
        "woman",
        "boy",
        "tail",
        "body",
        "one",
        "lion",
        "cat",
        "horse",
    }
)
UNKNOWN_COUNT = {
    "remove the rabbits",
    "remove the planes",
    "remove all the black ducks except the right one",
}


def singular(text):
    # Inflect the target head only: 'birds flying above the birds' must retain
    # the plural reference birds; the same applies to giraffes on the left of a herd.
    boundary = re.search(
        r"\s+(?:on|in|at|above|below|to|behind|between|near|facing|flying|with|of|up|down)\b",
        text,
    )
    end = boundary.start() if boundary else len(text)
    return (
        re.sub(r"\b(" + "|".join(PLURALS) + r")\b", lambda m: PLURALS[m[0]], text[:end], count=1)
        + text[end:]
    )


def _noun(text):
    """Find the shared noun before a positional/modifying preposition."""
    head = re.split(r"\s+(?:on|in|above|below|behind|between|near|facing|flying|with|of)\s+", text)[
        0
    ]
    return next((w for w in reversed(head.split()) if w in HEADS), None)


def compile_instruction(instruction):
    """Return a transparent text-only decomposition, or a native-enumeration request.

    This is called for the fixed multi-object task cohort, not an English parser
    applied blindly to adjective conjunctions in every single-target sentence.
    """
    if not isinstance(instruction, str) or not instruction.strip() or "<|" in instruction:
        raise ValueError("Expected an original public instruction without model tokens")
    text = instruction.strip()
    core = text.rstrip(".?!")
    if core in UNKNOWN_COUNT:
        return {"mode": "native_enumeration", "rule": "unspecified_plural_count", "units": []}
    match = re.fullmatch(r"(add|remove) (.+)", core)
    if not match:
        raise ValueError(f"Unreviewed multi-target operation: {instruction!r}")
    operation, body = match.groups()
    if operation == "add" and body.startswith("two "):
        phrase = singular(body[4:])
        if " up and down" in phrase:
            first, suffix = phrase.split(" up and down", 1)
            if suffix == " with opposite direction":
                units = [
                    f"add one {first} up",
                    f"add another {first} down facing in the opposite direction to the first added {first}",
                ]
            else:
                units = [f"add one {first} up{suffix}", f"add another {first} down{suffix}"]
            rule = "explicit_two_and_two_positions"
        else:
            units = [f"add one {phrase}", f"add another {phrase}"]
            rule = "explicit_two_additions"
    elif operation == "remove" and re.search(r"\btwo\b", body) and " and the " not in body:
        # A count in a reference clause does not imply two targets: only a count
        # before the first target noun can activate this branch.
        target_noun = _noun(body.split(" two ")[0]) if " two " in body else None
        if target_noun:
            raise ValueError(f"Count is in a reference rather than target: {instruction!r}")
        group = body if body.startswith("the ") else "the " + body
        units = [f"remove one of {group}", f"remove the other of {group}"]
        rule = "explicit_two_removals"
        # The explicit left/right pair supplies two selectors; no geometry is invented.
        if " on the left and right of " in body:
            head, reference = body.split(" on the left and right of ")
            head = singular(re.sub(r"\btwo\s+", "", head))
            units = [
                f"remove {head} on the left of {reference}",
                f"remove {head} on the right of {reference}",
            ]
            rule = "explicit_two_and_two_positions"
    else:
        # Repeating the operation on the second conjunct is syntax expansion,
        # not rewriting a target caption. Colour/clothing conjunctions stay intact.
        pattern = (
            r"\s+and\s+(?=(?:add\s+|a\s+|an\s+|another\s+|half body\b))"
            if operation == "add"
            else r"\s+and\s+(?=(?:remove\s+|the\s+|a\s+))"
        )
        parts = re.split(pattern, body)
        if len(parts) == 1 and operation == "remove":
            parts = re.split(r"\s+and\s+(?=(?:rightmost|leftmost|second rightmost)\b)", body)
        if len(parts) != 2:
            raise ValueError(f"Unreviewed target conjunction: {instruction!r}")
        parts = [re.sub(r"^(?:add|remove)\s+", "", p).strip() for p in parts]
        # Ellipsis: 'the rightmost and the leftmost flamingos'. Restore only the
        # shared noun, without copying the second target's position to the first.
        if operation == "remove":
            noun = _noun(parts[1])
            if not _noun(parts[0]) and noun:
                shared = PLURALS.get(noun, noun)
                if re.fullmatch(r"(?:the )?(?:second )?(?:leftmost|rightmost)", parts[0]):
                    tail = re.fullmatch(
                        r"(?:the )?(?:second )?(?:leftmost|rightmost) (.+)", parts[1]
                    )
                    if tail:
                        shared = singular(tail[1])
                parts[0] += " " + shared
                parts[1] = singular(parts[1])
            elif _noun(parts[0]) and not _noun(parts[1]):
                # 'the chickens on the leftmost and rightmost'
                left = re.fullmatch(r"(.+?) on (?:the )?(leftmost|rightmost)", parts[0])
                if not left:
                    raise ValueError(f"Unreviewed shared selector: {instruction!r}")
                noun_phrase, location = left.groups()
                parts = [
                    f"{singular(noun_phrase)} on the {location}",
                    f"{singular(noun_phrase)} on the {parts[1]}",
                ]
        units = [operation + " " + part for part in parts]
        rule = "coordinated_target_phrases"
    if len(units) != 2 or any(not u for u in units):
        raise ValueError("Reviewed CompBench decomposition must have two explicit units")
    return {"mode": "text", "rule": rule, "units": units}


def validate_enumeration(value):
    """No repair, best-candidate choice or GT-guided rematching."""
    if not isinstance(value, list) or not 2 <= len(value) <= 5:
        raise ValueError("Native enumeration must return 2–5 targets")
    for i, unit in enumerate(value, 1):
        if not isinstance(unit, dict) or set(unit) != {"label", "instruction"}:
            raise ValueError("Native enumeration needs exactly label/instruction")
        if unit["label"] != f"U{i}" or not isinstance(unit["instruction"], str):
            raise ValueError("Native enumeration label order is invalid")
        if not unit["instruction"].startswith("remove ") or "<|" in unit["instruction"]:
            raise ValueError("Native enumeration must retain the removal operation")
    if len({u["instruction"] for u in value}) != len(value):
        raise ValueError("Native enumeration repeated the same target instruction")
    return [u["instruction"] for u in value]
