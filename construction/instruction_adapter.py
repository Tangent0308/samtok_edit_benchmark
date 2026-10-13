"""Map the reviewed v2 recipes to protocol 1.0 without inventing edit content."""

import re
from samtok_benchmark.v2.instruction_protocol import make_spec


def design_spec(recipe, ref, scope, payload, *, placement=None, target_part=""):
    code, _, subtype = recipe.partition(":")
    operation = {"A": "add", "R": "replace", "D": "remove", "C": "attribute"}[code]
    kwargs = {}
    if code == "D":
        kwargs["remove_mode"] = subtype or "whole"
        if subtype == "part":
            kwargs["target_part"] = re.sub(r"^its\s+", "", payload)
        payload = ""
    elif code == "C":
        kwargs["attribute_kind"] = subtype or "color"
    elif code == "A":
        if not placement:
            raise ValueError("add requires an explicitly reviewed structured placement")
        kwargs["placement"] = dict(placement)
    if target_part:
        if "target_part" in kwargs and kwargs["target_part"] != target_part:
            raise ValueError("conflicting target parts")
        kwargs["target_part"] = target_part
    return make_spec(operation, ref, scope, payload, **kwargs)
