import pytest
from samtok_benchmark.v2.instruction_protocol import make_spec, render, validate_pair, length_advice


@pytest.mark.parametrize(
    "op,payload,kwargs,expected",
    [
        (
            "add",
            "two red tags",
            {"placement": {"relation": "attached to", "site": "handle"}},
            "Add two red tags attached to the selected region.",
        ),
        (
            "replace",
            "a rigid arched handle",
            {"target_part": "handle"},
            "Replace the selected region with a rigid arched handle.",
        ),
        (
            "remove",
            "",
            {"remove_mode": "part", "target_part": "logo"},
            "Remove the selected region.",
        ),
        (
            "remove",
            "",
            {"remove_mode": "contents"},
            "Remove the selected region, including its contents.",
        ),
        (
            "remove",
            "",
            {"remove_mode": "contents_only"},
            "Remove the selected region.",
        ),
        (
            "remove",
            "",
            {"remove_mode": "lowerlegs"},
            "Remove the selected region to make knee-length shorts.",
        ),
        (
            "remove",
            "",
            {"remove_mode": "hem"},
            "Remove the selected region to make it knee-length.",
        ),
        ("attribute", "amber", {"attribute_kind": "tint"}, "Tint the selected region amber."),
        (
            "attribute",
            "OPEN!",
            {"attribute_kind": "text"},
            'Change the text on the selected region to "OPEN!".',
        ),
        (
            "attribute",
            "translucent",
            {"attribute_kind": "opacity"},
            "Make the selected region translucent.",
        ),
        (
            "attribute",
            "",
            {
                "attributes": [
                    {"property": "color", "value": "blue"},
                    {"property": "finish", "value": "matte"},
                ]
            },
            "Change the color of the selected region to blue and its finish to matte.",
        ),
    ],
)
def test_semantic_slots_survive_ref_removal(op, payload, kwargs, expected):
    # Synthetic grammar fixtures only, not source-grounded editing proposals.
    s = make_spec(op, "the red suitcase on the left", "suitcase", payload, **kwargs)
    assert render(s, False) == expected
    assert "the red suitcase on the left" in render(s)
    validate_pair(s, render(s), expected)
    with pytest.raises(ValueError, match="semantic|blind"):
        validate_pair(s, render(s), expected.replace("selected region", "selected bag"))


def test_no_minimum_or_hard_truncation_and_invalid_property_rejected():
    s = make_spec("remove", "it", "vase")
    assert render(s) == "Remove it."
    s["ref"] = "the " + ("very " * 50) + "large vase"
    assert length_advice(render(s), render(s, False))
    with pytest.raises(ValueError, match="property"):
        make_spec("attribute", "the vase", "vase", "blue", attribute_kind="invented")


def test_relative_add_must_be_explicit_and_text_is_exact():
    with pytest.raises(ValueError, match="anchor_mode"):
        make_spec("add", "the desk", "desk", "a bin", placement={"relation": "beside"})
    s = make_spec(
        "add",
        "the desk",
        "desk",
        "a bin",
        placement={"relation": "beside", "anchor_mode": "reference"},
    )
    assert render(s, False) == "Add a bin beside the selected region."
    s = make_spec("attribute", "the sign", "sign", 'A "quote"!', attribute_kind="text")
    assert '"A \\"quote\\"!"' in render(s)
