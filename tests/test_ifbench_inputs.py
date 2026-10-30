"""Behavioral checks for information isolation, frozen assignment and geometry."""

import copy
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import pytest

from samtok_benchmark.io import read_jsonl, sha256_file
from samtok_benchmark.ifbench import AUDIT_CASES, SETTINGS
from samtok_benchmark.ifbench.geometry import small_box, to_box, to_mask
from samtok_benchmark.ifbench.inputs import discard_region_prompt, export_inputs, global_prompt
from samtok_benchmark.ifbench.plan import assignment, modes, split_cases
from samtok_benchmark.ifbench.public import project, public_digest, verify
from samtok_benchmark.ifbench.render import render


@pytest.fixture
def sample(tmp_path):
    Image.new("RGB", (100, 80), (90, 110, 130)).save(tmp_path / "source.png")
    mask = Image.new("L", (100, 80), 0)
    d = ImageDraw.Draw(mask)
    d.rectangle((0, 0, 39, 39), fill=255)
    d.rectangle((10, 10, 20, 20), fill=0)
    d.rectangle((50, 50, 55, 55), fill=255)
    mask.save(tmp_path / "mask.png")
    units = []
    for i in range(2):
        units.append(
            {
                "id": f"U{i + 1}",
                "operation": ["add", "attribute"][i],
                "instruction_ref": [
                    "Add a bird on the left lamp.",
                    "Change the right lamp to blue.",
                ][i],
                "instruction_noref": [
                    "Add a bird on the selected region.",
                    "Change the selected region to blue.",
                ][i],
                "target": {
                    "point": [10 + 60 * i, 25],
                    "box": [0 + 60 * i, 0, 40 + 60 * i, 40],
                    "mask": "mask.png",
                    "mask_sha256": sha256_file(tmp_path / "mask.png"),
                    "ref": "PRIVATE_REF",
                },
                "interaction": {"has_ref": bool(i), "locator": "none" if i else "point"},
                "completion_requirement": "PRIVATE_COMPLETION",
                "preserve": ["PRIVATE_PRESERVE"],
            }
        )
    return {
        "id": "fixture",
        "source": {
            "image": "source.png",
            "size": [100, 80],
            "sha256": sha256_file(tmp_path / "source.png"),
            "family_id": "fixture",
        },
        "units": units,
    }, tmp_path


def test_split_family_isolation_order_independence_and_exposed_cases():
    cases = read_jsonl(Path("data/v2_2.6.0/cases.jsonl"))
    a = split_cases(cases)
    b = split_cases(list(reversed(cases)))
    assert a == b
    assert len(a["dev"]) == 108 and len(a["test"]) == 976
    assert not set(a["dev"]) & set(a["test"])
    assert not set(a["dev_families"]) & set(a["test_families"])
    assert set(AUDIT_CASES) <= set(a["dev"])


def test_assignments_are_shared_and_s5_not_resampled(sample):
    case, _ = sample
    a = assignment(case)
    assert len(set(a["S4"].values())) >= 2
    assert {u: m["locator"] for u, m in modes("S4-ref", a).items()} == {
        u: m["locator"] for u, m in modes("S4-noref", a).items()
    }
    assert a["S5"] == {u["id"]: u["interaction"] for u in case["units"]}
    reverse = copy.deepcopy(case)
    reverse["units"].reverse()
    assert assignment(reverse) == a


@pytest.mark.parametrize("setting", SETTINGS)
def test_public_schema_and_full_unit_coverage(sample, setting):
    case, root = sample
    r = project(case, setting, assignment(case), root)
    verify(r, assets=True)
    assert [u["id"] for u in r["units"]] == ["U1", "U2"]
    assert "PRIVATE_" not in str(r)
    for u in r["units"]:
        if u["locator"] == "none":
            assert u["region"] is None
        elif u["locator"] == "mask":
            assert set(u["region"]) == {"path", "sha256"}
        else:
            assert set(u["region"]) == {"coordinates"}


@pytest.mark.parametrize("setting", ["S3-point", "S3-box", "S3-mask", "S4-noref"])
def test_hidden_ref_never_changes_no_ref_request(sample, setting):
    case, root = sample
    a = assignment(case)
    before = project(case, setting, a, root)
    changed = copy.deepcopy(case)
    for u in changed["units"]:
        u["instruction_ref"] = "SECRET CANONICAL INSTRUCTION"
        u["target"]["ref"] = "SECRET OBJECT"
        u["target"]["category"] = "SECRET CATEGORY"
        u["preserve"] = ["SECRET PRESERVE"]
        u["completion_requirement"] = "SECRET COMPLETION"
    assert project(changed, setting, a, root) == before


def test_point_render_does_not_read_hidden_masks_boxes_or_ref(sample, tmp_path):
    case, root = sample
    a = assignment(case)
    before = project(case, "S3-point", a, root)
    changed = copy.deepcopy(case)
    for u in changed["units"]:
        u["target"]["mask"] = "THIS_FILE_DOES_NOT_EXIST.png"
        u["target"]["mask_sha256"] = "not_a_hash"
        u["target"]["box"] = [99, 79, 1, 0]
        u["instruction_ref"] = "PRIVATE REF"
    after = project(changed, "S3-point", a, root)
    assert before == after
    render(before, tmp_path / "one.png")
    render(after, tmp_path / "two.png")
    assert (tmp_path / "one.png").read_bytes() == (tmp_path / "two.png").read_bytes()


def test_reject_private_field_even_with_recomputed_digest(sample):
    case, root = sample
    r = project(case, "S3-point", assignment(case), root)
    r["units"][0]["region"]["mask"] = "private.png"
    r["input_digest"] = public_digest(r)
    with pytest.raises(ValueError):
        verify(r)


def test_geometric_conversions_holes_components_edges_and_fraction(sample):
    case, root = sample
    r = project(case, "S3-mask", assignment(case), root)
    u = r["units"][0]
    assert to_box(u, [100, 80]) == [0, 0, 56, 56]
    result = np.array(to_mask(u, [100, 80]))
    assert result[0, 0] == 255 and result[15, 15] == 0 and result[55, 55] == 255
    assert np.array_equal(result, np.array(Image.open(root / "mask.png")))
    assert small_box([0, 0], [100, 80]) == [0, 0, 2, 2]
    assert small_box([50, 40], [100, 80]) == [48, 38, 52, 42]
    point = project(case, "S3-point", assignment(case), root)["units"][0]
    box = to_box(point, [100, 80])
    a = np.array(to_mask(point, [100, 80]))
    assert np.count_nonzero(a) == (box[2] - box[0]) * (box[3] - box[1])


@pytest.mark.parametrize("setting", ["S3-point", "S3-box", "S3-mask", "S4-noref", "S5", "S1"])
def test_discard_region_rejected_outside_s2(sample, setting):
    case, root = sample
    r = project(case, setting, assignment(case), root)
    with pytest.raises(ValueError):
        discard_region_prompt(r)


def test_s2_discard_is_exact_s1_prompt_and_s1_has_no_annotation(sample, tmp_path):
    case, root = sample
    a = assignment(case)
    s1 = project(case, "S1", a, root)
    for setting in ("S2-point", "S2-box", "S2-mask"):
        r = project(case, setting, a, root)
        assert discard_region_prompt(r) == global_prompt(s1)
    payload = export_inputs(s1, tmp_path / "s1")
    assert payload["annotation"] is None
    assert len(payload["forms"]["dual"]["images"]) == 1
    assert not (tmp_path / "s1/annotation.png").exists()
    assert all(u["mask"] is None for u in payload["native"]["units"])


def test_source_and_mask_mutations_rejected(sample):
    case, root = sample
    r = project(case, "S3-mask", assignment(case), root)
    Image.new("L", (100, 80), 255).save(root / "mask.png")
    with pytest.raises(ValueError, match="Mask asset changed"):
        verify(r, assets=True)


def test_frozen_plan_refuses_changes(tmp_path):
    from samtok_benchmark.ifbench.plan import persist

    path = tmp_path / "plan.json"
    persist(path, {"seed": 42, "assignments": ["point", "mask"]})
    before = path.read_bytes()
    persist(path, {"seed": 42, "assignments": ["point", "mask"]})
    with pytest.raises(ValueError, match="Refusing to change"):
        persist(path, {"seed": 99, "assignments": ["box", "mask"]})
    assert path.read_bytes() == before


def test_point_rejects_upper_edge_coordinate_and_bool(sample):
    case, root = sample
    for coordinates in ([100, 79], [99, 80], [True, 20]):
        changed = copy.deepcopy(case)
        changed["units"][0]["target"]["point"] = coordinates
        with pytest.raises(ValueError):
            project(changed, "S3-point", assignment(changed), root)
