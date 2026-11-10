import pytest

from samtok_benchmark.external_compbench.recovery9.parsing import enumeration_lines, recover_answer

A = "<|mt_start|><|mt_0012|><|mt_0301|><|mt_end|>"
B = "<|mt_start|><|mt_0028|><|mt_0402|><|mt_end|>"


@pytest.fixture
def native_request():
    protocol = pytest.importorskip("samtok_edit21.pass1.protocol")
    return {
        "protocol": protocol.VERSION,
        "coordinate_system": "normalized_0_1000",
        "targets": [
            {
                "label": uid,
                "instruction": "remove the selected object",
                "has_ref": True,
                "locator": "none",
            }
            for uid in ("U1", "U2")
        ],
    }


@pytest.mark.parametrize(
    "bad",
    [
        '[{"label":"U1","mask_2d":"%s"},{"label":"U2":"%s"}]' % (A, B),
        '[{"label":"U1","mask_2d":"%s"},{"label":"label":"U2","mask_2d":"%s"}]' % (A, B),
    ],
)
def test_recovers_exact_existing_codes(native_request, bad):
    result = recover_answer(bad, native_request)
    assert result["parsed"]["spans"] == {"U1": A, "U2": B}
    assert len(result["repairs"]) == 1


@pytest.mark.parametrize(
    "bad",
    [
        '[{"label":"U1","mask_2d":"%s"},{"label":"U1":"%s"}]' % (A, B),
        '[{"label":"U1","mask_2d":"%s"},{"label":"U2":"<|mt_start|><|mt_0999|><|mt_0402|><|mt_end|>"}]'
        % A,
        '[{"label":"U1","mask_2d":"%s"},{"label":"U2":"missing"}]' % A,
    ],
)
def test_rejects_ambiguity_bad_codes_or_invention(native_request, bad):
    with pytest.raises(ValueError):
        recover_answer(bad, native_request)


def test_enumeration_requires_separate_consecutive_units():
    assert enumeration_lines(
        "U1: remove the left rabbit\nU2: remove the right rabbit<|im_end|>"
    ) == ["remove the left rabbit", "remove the right rabbit"]
    for raw in (
        "U1: remove the rabbits",
        "U1: remove the duck\nU2: remove the duck",
        "U1: remove the left duck\nU3: remove the right duck",
    ):
        with pytest.raises(ValueError):
            enumeration_lines(raw)
