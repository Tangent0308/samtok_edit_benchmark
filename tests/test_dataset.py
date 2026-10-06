import json
from pathlib import Path

import pytest
from PIL import Image

from samtok_benchmark.dataset import load_cases, validate
from samtok_benchmark.io import asset_path, read_jsonl, sha256_file, write_jsonl


def test_release_metadata_and_instruction_identity():
    root = Path(__file__).resolve().parents[1] / "data/v1"
    cases = load_cases(root / "cases.jsonl", 450)
    assert sum(len(c["regions"]) for c in cases) == 466
    stats = json.loads((root / "statistics.json").read_text())
    assert sha256_file(root / "cases.jsonl") == stats["manifest_sha256"]
    revised = read_jsonl(root / "instruction_revisions_single_ops_v4.jsonl")
    assert len(revised) == 450
    assets = {a["local_path"]: a for a in read_jsonl(root / "asset_manifest.jsonl")}
    for r in revised:
        c = cases[r["index"]]
        assert c["id"] == r["id"] and c["instruction"] == r["instruction"]
        assert c["edit_type"] == r["edit_type"]
        assert assets[c["source_image"]]["sha256"] == r["source_sha256"]
        assert [assets[m["mask"]]["sha256"] for m in c["regions"]] == r["region_mask_sha256"]
    decisions = read_jsonl(root / "selection/v0_filter_decisions.jsonl")
    assert len(decisions) == 656
    admitted = {d["id"] for d in decisions if d["filter_decision"] == "admit_core_hard_relevant"}
    assert admitted == {c["original_id"] for c in cases[:150]}
    assert sum(c["instruction_revision"] == "mask_grounded_single_ops_v4" for c in cases) == 47
    assert stats["edit_type_counts"] == {
        "add": 113,
        "remove": 112,
        "replace": 113,
        "attribute": 112,
    }
    assert len(assets) == 1366
    for c, r in zip(cases, revised):
        assert c["instruction"][0].isupper()
        assert c["edit_type"] not in {"mixed", "composite"}
        assert len(set(r["region_operations"])) == 1
        if r["changed_in_single_ops_v4"]:
            assert len(c["regions"]) == 1
            assert c["regions"] == [r["previous_regions"][r["selected_original_region_index"] - 1]]
            assert r["selected_original_region_index"] != r["discarded_original_region_index"]
        else:
            assert c["regions"] == r["previous_regions"]
            assert c["instruction"] == r["previous_instruction"]
            assert c["edit_type"] == r["previous_edit_type"]
    history = read_jsonl(root / "instruction_revisions.jsonl")
    assert len(history) == 797
    assert history[-47:] == [r for r in revised if r["changed_in_single_ops_v4"]]
    removed = read_jsonl(root / "selection/removed_regions_single_ops_v4.jsonl")
    assert len(removed) == 47
    assert all(r["local_path"] not in assets for r in removed)


@pytest.mark.parametrize("operation", ["mixed", "composite"])
@pytest.mark.parametrize("region_count", [1, 2])
def test_mixed_types_are_forbidden_with_any_mask_count(release, operation, region_count):
    _, manifest, case = release
    case["edit_type"] = operation
    case["regions"] *= region_count
    write_jsonl(manifest, [case])
    with pytest.raises(ValueError, match="invalid edit type"):
        load_cases(manifest)


@pytest.mark.parametrize("field", ["instruction", "region_instruction"])
def test_lowercase_instruction_is_rejected(release, field):
    _, manifest, case = release
    case[field] = "remove the object."
    write_jsonl(manifest, [case])
    with pytest.raises(ValueError, match="capital letter"):
        load_cases(manifest)


def test_geometry_and_assets_validate(release):
    root, manifest, _ = release
    result = validate(manifest, root, expected_cases=1)
    assert result["checked_assets"] == 3
    assert result["region_masks"] == 1


@pytest.mark.parametrize("change", ["empty_mask", "point_outside", "small_box", "eval_incomplete"])
def test_bad_region_is_rejected(release, change):
    root, manifest, case = release
    if change == "empty_mask":
        Image.new("L", (80, 64), 0).save(root / "region.png")
    elif change == "point_outside":
        case["regions"][0]["point"] = [0, 0]
    elif change == "small_box":
        case["regions"][0]["box"] = [18, 18, 30, 47]
    else:
        m = Image.new("L", (80, 64), 0)
        m.putpixel((20, 20), 255)
        m.save(root / "evaluation.png")
    write_jsonl(manifest, [case])
    with pytest.raises(ValueError):
        validate(manifest, root)


def test_tampering_detected_by_hash(release, tmp_path):
    root, manifest, case = release
    assets = tmp_path / "assets.jsonl"
    write_jsonl(
        assets,
        [
            {"local_path": p, "sha256": sha256_file(root / p)}
            for p in [case["source_image"], case["evaluation_mask"], "region.png"]
        ],
    )
    Image.new("RGB", (80, 64), "blue").save(root / "source.png")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate(manifest, root, assets)


def test_duplicate_id_and_unconfined_paths_rejected(release):
    root, manifest, case = release
    write_jsonl(manifest, [case, case])
    with pytest.raises(ValueError, match="duplicate"):
        load_cases(manifest)
    for path in ("../secret", "/absolute/path"):
        with pytest.raises(ValueError):
            asset_path(root, path)


@pytest.mark.parametrize(
    "instruction",
    [
        "Change the object to blue and remove the handle.",
        "Remove the object. Add a flower in its place.",
        "Replace the object with a cup; paint its handle red.",
    ],
)
def test_mixed_text_cannot_hide_under_an_atomic_label(release, instruction):
    _, manifest, case = release
    case["instruction"] = instruction
    write_jsonl(manifest, [case])
    with pytest.raises(ValueError, match="mixed operation clauses"):
        load_cases(manifest)
