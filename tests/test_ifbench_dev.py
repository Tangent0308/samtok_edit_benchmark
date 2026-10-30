"""Protocol boundaries that must hold before any dev selection."""

import copy

from samtok_benchmark.ifbench.dev_plan import MODELS, candidates
from samtok_benchmark.ifbench.dev_judge import canonical, prompt
from samtok_benchmark.ifbench.ref_extract import extract_ref


def test_candidate_budget_and_discard_scope():
    for model in MODELS:
        pool = candidates(model)
        assert len(pool) <= 4
        assert sum(c["role"] == "discard" for c in pool) == 1
        for c in pool:
            for s, form in c["mapping"].items():
                assert form != "discard-region" or s.startswith("S2-")
            for mode in ("point", "box", "mask"):
                if c["role"] != "discard":
                    assert c["mapping"]["S2-" + mode] == c["mapping"]["S3-" + mode]
            if c["component"]:
                assert c["role"] == "official-supplement"


def test_judge_never_receives_editor_input_metadata_or_noref_text():
    case = {
        "id": "public-id",
        "units": [
            {
                "id": "U1",
                "operation": "attribute",
                "instruction_ref": "Change the red coat to navy blue.",
                "instruction_noref": "SECRET_NOREF",
                "interaction": {"has_ref": False, "locator": "SECRET_LOCATOR"},
                "completion_requirement": "The coat is navy blue.",
                "edit_contract": {},
                "preserve": ["Keep the face."],
            }
        ],
    }
    other = copy.deepcopy(case)
    other["units"][0]["interaction"] = {"has_ref": True, "locator": "mask"}
    other["units"][0]["instruction_noref"] = "DIFFERENT_NOREF"
    other["model"] = "SECRET_MODEL"
    assert canonical(case) == canonical(other)
    assert prompt(case) == prompt(other)
    assert all(
        s not in prompt(case)
        for s in ["SECRET_NOREF", "SECRET_LOCATOR", "SECRET_MODEL", "has_ref", "instruction_noref"]
    )
    assert case["units"][0]["instruction_ref"] in prompt(case)


def test_public_grammar_preserves_source_modifiers_and_new_object_attachment():
    text = "Replace the top handle of the gray suitcase with a green NEW sticker immediately behind the pale-purple suitcase with a folding rectangular brass handle."
    assert (
        extract_ref(text, "replace")
        == "the top handle of the gray suitcase with a green NEW sticker immediately behind the pale-purple suitcase"
    )
    text = "Add one small red pennant flag on a short pole on the upper tiled roof to the right of the tower."
    assert extract_ref(text, "add") == "the upper tiled roof to the right of the tower"
    text = "Tint the arched window on the church at the right light blue."
    assert extract_ref(text, "attribute") == "the arched window on the church at the right"
