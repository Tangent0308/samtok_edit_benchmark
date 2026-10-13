import copy
from pathlib import Path
import sys

import pytest

from samtok_benchmark.io import write_jsonl
from samtok_benchmark.v2.dataset import load_cases
from samtok_benchmark.v2.instruction_protocol import make_spec, mask_contract, render

REPO = Path(__file__).parents[1]
sys.path.insert(0, str(REPO / "construction"))
from instruction_adapter import design_spec  # noqa: E402


def test_direct_attachment_site_below_does_not_become_remote_anchor():
    spec = design_spec(
        "A",
        "the left sleeve",
        "sleeve",
        "a red patch",
        placement={
            "relation": "sewn onto",
            "site": "area below the cuff",
            "anchor_mode": "support",
        },
    )
    assert mask_contract(spec)["anchor_mode"] == "support"
    assert "area below the cuff of the selected sleeve" in render(spec, False)
    with pytest.raises(ValueError, match="explicitly reviewed"):
        design_spec("A", "the left sleeve", "sleeve", "a red patch below its cuff")


def test_host_subpart_requires_local_execution_but_keeps_host_selector():
    spec = make_spec(
        "attribute",
        "the third chair from the front",
        "chair",
        "white",
        target_part="wooden frame",
        attribute_kind="color",
    )
    assert mask_contract(spec)["execution_region_required"]
    assert (
        render(spec, False)
        == "Change the color of the wooden frame of the selected chair to white."
    )


def test_frozen_contract_is_checked_on_load(tmp_path):
    cases = load_cases(REPO / "data/v2/cases.jsonl")
    original = copy.deepcopy(cases)
    assert all(
        u["mask_semantics"]["anchor_mode"] == "support"
        for c in cases
        for u in c["units"]
        if u["operation"] == "add"
    )
    cases[0]["units"][0]["mask_semantics"]["source_role"] = "anchor"
    manifest = tmp_path / "cases.jsonl"
    write_jsonl(manifest, cases)
    with pytest.raises(ValueError, match="mask semantics"):
        load_cases(manifest)
    unit = original[5]["units"][1]
    assert unit["instruction_spec"]["target_part"] == "wooden frame"
    assert "木制框架" in unit["instruction_noref_zh"]
