import copy
import json
from pathlib import Path

import pytest

from samtok_benchmark.io import write_jsonl
from samtok_benchmark.v2.dataset import load_cases
from samtok_benchmark.v2.inputs import prepare, verify_job, _digest
from samtok_benchmark.v2.review import package_review
from test_v2 import v2release as v2release


@pytest.mark.parametrize("protocol", ["visual_locator_v2", "native_regions_v2"])
def test_add_uses_public_support_locator_and_does_not_leak_translation(
    v2release, tmp_path, protocol
):
    root, manifest, case = v2release
    unit = case["units"][1]
    unit.update(
        operation="add",
        instruction_noref="Add protective boots to both legs.",
        instruction_ref="Add protective boots to the secret chair legs.",
        instruction_ref_zh="私有完整指代翻译",
        instruction_noref_zh="给两条支腿加保护套。",
        edit_contract={"locator_semantics": "addition_support", "definition": "PRIVATE_GOLD"},
    )
    write_jsonl(manifest, [case])
    job = prepare(manifest, root, tmp_path / "inputs", protocol)[0]
    public = job["units"][1]
    assert public["operation"] == "add" and public["locator"] == "point"
    assert "PRIVATE_GOLD" not in json.dumps(job) and "instruction_zh" not in json.dumps(job)
    assert "Keep all non-target" not in job["prompt"]
    if protocol == "native_regions_v2":
        assert set(public["region"]) == {"point"}
    package_review(manifest, root, tmp_path / "review")
    view = json.loads((tmp_path / "review/cases/v2-synthetic.json").read_text())
    assert view["public_units"][1]["instruction_zh"] == "给两条支腿加保护套。"
    broken = copy.deepcopy(job)
    broken["units"][1]["operation"] = "invented"
    broken["input_digest"] = _digest(broken)
    with pytest.raises(ValueError, match="operation"):
        verify_job(broken)


def test_add_requires_explicit_support_semantics(v2release):
    _, manifest, case = v2release
    case["units"][0]["operation"] = "add"
    write_jsonl(manifest, [case])
    with pytest.raises(ValueError, match="support"):
        load_cases(manifest)


def test_current_instruction_release_is_balanced_bilingual_and_concise():
    from collections import Counter

    cases = load_cases(Path(__file__).parents[1] / "data/v2/cases.jsonl")
    units = [u for c in cases for u in c["units"]]
    assert Counter(u["operation"] for u in units) == dict.fromkeys(
        ["add", "replace", "remove", "attribute"], 135
    )
    for u in units:
        for mode in ["ref", "noref"]:
            assert u["instruction_" + mode + "_zh"].strip()
            assert len(u["instruction_" + mode].split()) <= 40
            assert "preserv" not in u["instruction_" + mode].lower()
        assert u["instruction_design"]["version"] == "2.1.0"
