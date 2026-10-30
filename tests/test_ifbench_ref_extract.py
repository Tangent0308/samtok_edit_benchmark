"""Public-only referring phrases: retain relations and never use the new object as anchor."""

import pytest

from samtok_benchmark.ifbench.smoke_ref_extract import extract_ref


@pytest.mark.parametrize(
    "operation,instruction,expected",
    [
        (
            "add",
            "Add one small gray pigeon on the top of the rightmost traffic light.",
            "the top of the rightmost traffic light",
        ),
        (
            "add",
            "Add one small zipped hip pocket sewn onto the long skirt of the bending woman.",
            "the long skirt of the bending woman",
        ),
        (
            "replace",
            "Replace the outer sleeve of the woman on the left with a flared bell sleeve.",
            "the outer sleeve of the woman on the left",
        ),
        (
            "attribute",
            "Change the color of the coat next to the blue bag to navy blue.",
            "the coat next to the blue bag",
        ),
        (
            "remove",
            "Remove the lower section of the skirt next to the car to make it knee-length.",
            "the lower section of the skirt next to the car",
        ),
    ],
)
def test_preserves_public_ref_and_existing_anchor(operation, instruction, expected):
    span = extract_ref(instruction, operation)
    assert span == expected
    assert instruction[instruction.index(span) : instruction.index(span) + len(span)] == span


@pytest.mark.parametrize(
    "operation,instruction",
    [
        ("add", "Add a bird."),
        ("add", "Add a bird on the rail on the left."),
        ("replace", "Replace the cup with a cup with handles."),
        ("attribute", "Make it blue."),
        ("unknown", "Use the private annotation to identify the target."),
    ],
)
def test_unsupported_or_ambiguous_grammar_does_not_invent_ref(operation, instruction):
    with pytest.raises(ValueError):
        extract_ref(instruction, operation)
