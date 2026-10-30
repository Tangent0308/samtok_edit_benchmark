"""CPU regression tests for native text completeness and versioned inputs."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from samtok_benchmark.ifbench.fairness_dev_revision import (
    MICE_HEADER,
    MiceTextOverflow,
    mice_text_audit,
    revise_request,
    verify_mice_native_defaults,
)


class Tokenizer:
    padding_side = "right"
    chat_template = "native template fixture"

    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == {
            "tokenize": False,
            "add_generation_prompt": True,
            "enable_thinking": False,
        }
        return messages[0]["content"]

    def __call__(self, text, **kwargs):
        # Include 12 native chat/special tokens, not just user text length.
        ids = list(range(int(text) + 12))
        if kwargs == {"padding": False, "truncation": False}:
            return {"input_ids": ids}
        assert kwargs == {"padding": "max_length", "truncation": True, "max_length": 512}
        ids = ids[:512]
        mask = [1] * len(ids) + [0] * (512 - len(ids))
        return {"input_ids": ids + [0] * (512 - len(ids)), "attention_mask": mask}


@pytest.mark.parametrize("user_tokens", [187, 188])
def test_native_prefix_contains_complete_text_including_chat_tokens(user_tokens):
    audit = mice_text_audit(Tokenizer(), str(user_tokens), 1)
    assert audit["all_segments_complete"]
    assert audit["segments"][0]["chat_tokens"] == user_tokens + 12


@pytest.mark.parametrize("prompt,failed_segment", [("189", 0), ("12$BREAKFLAG$189", 1)])
def test_512_token_acceptance_does_not_hide_global_or_local_200_overflow(prompt, failed_segment):
    with pytest.raises(MiceTextOverflow) as error:
        mice_text_audit(Tokenizer(), prompt, prompt.count("$BREAKFLAG$") + 1)
    audit = error.value.audit
    assert audit["segments"][failed_segment]["chat_tokens"] == 201
    assert audit["new_inference_calls"] == 0


def test_native_padding_or_prefix_drift_cannot_pass_a_length_only_check():
    tokenizer = Tokenizer()
    tokenizer.padding_side = "left"
    with pytest.raises(ValueError, match="right-padding"):
        mice_text_audit(tokenizer, "20", 1)

    class WrongPrefix(Tokenizer):
        def __call__(self, text, **kwargs):
            value = super().__call__(text, **kwargs)
            if kwargs["padding"]:
                value["input_ids"][0] = 999
            return value

    with pytest.raises(MiceTextOverflow):
        mice_text_audit(WrongPrefix(), "20", 1)


def test_segment_routing_and_native_default_drift_fail_closed():
    with pytest.raises(ValueError, match="segments"):
        mice_text_audit(Tokenizer(), "20$BREAKFLAG$20", 1)

    def native(num_global_text_tokens=512, num_instance_text_tokens=200):
        pass

    with pytest.raises(ValueError, match="default changed"):
        verify_mice_native_defaults(SimpleNamespace(_get_qwen3_prompt_embeds=native))


def test_revision_preserves_public_tasks_and_native_local_slots():
    units = [
        {"id": "U1", "locator": "point", "instruction": "Remove the selected region."},
        {"id": "U2", "locator": "none", "instruction": "Turn the door blue."},
        {"id": "U3", "locator": "mask", "instruction": "Add a handle on the selected region."},
    ]
    original = {
        "public_units": units,
        "global_unit_ids": ["U1", "U2"],
        "regional_units": [units[2]],
        "prompt": "old long preamble",
        "request_digest": "old",
        "parameters": {"num_inference_steps": 4},
    }
    before = deepcopy(original)
    revised = revise_request("mice", original)
    assert original == before
    assert revised["prompt"] == (
        MICE_HEADER + "\nU1. [red point, label U1] Remove the selected region."
        "\nU2. Turn the door blue.$BREAKFLAG$Add a handle on the selected region."
    )
    assert {k: v for k, v in revised.items() if k not in {"prompt", "request_digest"}} == {
        k: v for k, v in original.items() if k not in {"prompt", "request_digest"}
    }


def test_qwen_resolution_changes_without_mutating_the_old_request():
    original = {
        "parameters": {"output_resolution": 1024, "num_inference_steps": 40},
        "prompt": "unchanged",
        "images": ["clean", "annotation"],
    }
    revised = revise_request("qwen21", original)
    assert revised["parameters"]["output_resolution"] == 2048
    assert original["parameters"]["output_resolution"] == 1024
    revised["parameters"]["output_resolution"] = 1024
    assert revised == original


def test_mice_without_points_and_other_models_remain_byte_equivalent():
    original = {"public_units": [{"locator": "mask"}], "prompt": "unchanged"}
    for model in ["mice", "qwen2511", "flux3", "replan", "mirage", "flux2_klein9b"]:
        assert revise_request(model, original) == original
