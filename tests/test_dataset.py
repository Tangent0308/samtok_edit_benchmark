import json
from pathlib import Path

import pytest
from PIL import Image

from samtok_benchmark.dataset import load_cases, validate
from samtok_benchmark.io import asset_path, read_jsonl, sha256_file, write_jsonl


def test_current_release_metadata_and_instruction_identity():
    from samtok_benchmark.v2.dataset import load_cases as load_v2

    root = Path(__file__).resolve().parents[1] / "data/v2"
    cases = load_v2(root / "cases.jsonl")
    release = json.loads((root / "release.json").read_text())
    assert release["manifest_sha256"] == sha256_file(root / "cases.jsonl")
    designs = {
        (d["case_id"], d["unit_id"]): d for d in read_jsonl(root / "instruction_design.jsonl")
    }
    assets = {a["path"]: a for a in read_jsonl(root / "asset_manifest.jsonl")}
    assert len(cases) == release["cases"] == 200
    assert len(designs) == release["units"] == 785
    assert len(assets) == 1185
    for c in cases:
        assert assets[c["source"]["image"]]["sha256"] == c["source"]["sha256"]
        for u in c["units"]:
            assert assets[u["target"]["mask"]]["sha256"] == u["target"]["mask_sha256"]
            d = designs[(c["id"], u["id"])]
            for mode in ["ref", "noref"]:
                for suffix in ["", "_zh"]:
                    key = "instruction_" + mode + suffix
                    assert u[key] == d[key]


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
