"""Protocol 2.0: blind no-ref rendering, deterministic leak checks and version coexistence."""

import pytest

from samtok_benchmark.v2.instruction_compat import (
    check_blind_noref,
    make_spec,
    mask_contract,
    render,
    validate_pair,
)

REF = "the red coat of the woman on the right"


@pytest.mark.parametrize(
    "op,payload,kwargs,expected",
    [
        ("attribute", "navy blue", {}, "Change the color of the selected region to navy blue."),
        (
            "attribute",
            "matte black",
            {"target_part": "wooden frame"},
            "Change the color of the selected region to matte black.",
        ),
        ("replace", "a flared bell sleeve", {}, "Replace the selected region with a flared bell sleeve."),
        ("remove", "", {}, "Remove the selected region."),
        ("remove", "", {"remove_mode": "part", "target_part": "white chest emblem"}, "Remove the selected region."),
        (
            "remove",
            "",
            {"remove_mode": "lowerlegs"},
            "Remove the selected region to make knee-length shorts.",
        ),
        ("remove", "", {"remove_mode": "hem"}, "Remove the selected region to make it knee-length."),
        (
            "remove",
            "",
            {"remove_mode": "contents"},
            "Remove the selected region, including its contents.",
        ),
        ("remove", "", {"remove_mode": "contents_only"}, "Remove the selected region."),
        (
            "add",
            "one small round enamel pin",
            {"placement": {"relation": "on", "site": "upper back"}},
            "Add one small round enamel pin on the selected region.",
        ),
        ("attribute", "pale blue", {"attribute_kind": "tint"}, "Tint the selected region pale blue."),
        ("attribute", "translucent", {"attribute_kind": "opacity"}, "Make the selected region translucent."),
        (
            "attribute",
            "KEBAB HOUSE",
            {"attribute_kind": "text"},
            'Change the text on the selected region to "KEBAB HOUSE".',
        ),
        (
            "attribute",
            "",
            {"attributes": [{"property": "color", "value": "blue"}, {"property": "finish", "value": "matte"}]},
            "Change the color of the selected region to blue and its finish to matte.",
        ),
    ],
)
def test_blind_noref_templates(op, payload, kwargs, expected):
    s = make_spec(op, REF, "coat", payload, **kwargs)
    assert render(s, False) == expected
    assert check_blind_noref(s, expected) == []
    validate_pair(s, render(s), expected)


def test_ref_rendering_is_unchanged_between_versions():
    for version in ("1.0", "2.0"):
        s = make_spec("remove", REF, "coat", "", remove_mode="part", target_part="belt", version=version)
        assert render(s) == "Remove the belt from " + REF + "."


def test_historical_noref_still_validates():
    s = make_spec("replace", REF, "coat", "a trench coat", version="1.0")
    assert render(s, False) == "Replace the selected coat with a trench coat."
    assert mask_contract(s)["version"] == "1.1"


def test_leaks_are_detected():
    s = make_spec("attribute", REF, "coat", "navy blue")
    assert check_blind_noref(s, "Change the color of the selected coat to navy blue.")
    with pytest.raises(ValueError):
        validate_pair(s, render(s), "Change the color of the selected coat to navy blue.")


def test_payload_words_may_repeat_location_or_category():
    s = make_spec("replace", "the sleeve of the woman on the left", "sleeve", "a left-side bell sleeve")
    assert check_blind_noref(s, render(s, False)) == []


def test_qualifier_mentioning_neighbors_is_dropped_but_edit_only_is_kept():
    s = make_spec("remove", "the pot", "pot", "", qualifier="preserving the plant growing in it")
    assert render(s, False) == "Remove the selected region."
    s = make_spec("attribute", "the wall", "wall", "white", qualifier="preserving the underlying surface")
    assert render(s, False).endswith(", preserving the underlying surface.")


def test_mask_semantics_2_roles():
    add = make_spec("add", REF, "coat", "a pin", placement={"relation": "on", "site": "collar"})
    assert mask_contract(add)["source_role"] == "anchor" and mask_contract(add)["version"] == "2.0"
    rem = make_spec("remove", REF, "coat", "", remove_mode="part", target_part="belt")
    assert mask_contract(rem)["source_role"] == "target"
