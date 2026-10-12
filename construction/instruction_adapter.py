"""Map the reviewed v2 recipes to protocol 1.0 without inventing edit content."""

import re
from samtok_benchmark.v2.instruction_protocol import make_spec


def design_spec(recipe, ref, scope, payload):
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
        # Move an explicit, already-reviewed placement phrase out of the item
        # description. No new side/site/count is inferred from category labels.
        match = re.fullmatch(
            r"(.+?) (on|around|across|along|over|below|above|near|at) (its|the) (.+)", payload
        )
        if match:
            payload, relation, _, site = match.groups()
            kwargs["placement"] = {
                "relation": relation,
                "site": site,
                "anchor_mode": "reference" if relation in {"below", "above", "near"} else "support",
            }
        elif payload.endswith(" on top"):
            payload = payload[:-7]
            kwargs["placement"] = {"relation": "on", "site": "top", "anchor_mode": "support"}
        else:
            kwargs["placement"] = {"relation": "to", "anchor_mode": "support"}
    return make_spec(operation, ref, scope, payload, **kwargs)
