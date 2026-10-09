import copy
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from samtok_benchmark.io import read_jsonl, sha256_file, write_jsonl
from samtok_benchmark.v2.dataset import load_cases, validate
from samtok_benchmark.v2.editor import run_editor
from samtok_benchmark.v2.evaluation import (
    blank_scores,
    binding,
    evaluate_score,
    prepare_judge,
    report,
)
from samtok_benchmark.v2.gallery import build
from samtok_benchmark.v2.inputs import prepare, verify_job, _digest


@pytest.fixture
def v2release(tmp_path):
    root = tmp_path / "v2"
    root.mkdir()
    image = root / "source.png"
    Image.new("RGB", (160, 120), "white").save(image)
    units = []
    modes = [(True, "none"), (False, "point"), (True, "box"), (False, "mask")]
    for i, (ref, locator) in enumerate(modes):
        x = 8 + 36 * i
        mask = Image.new("L", (160, 120))
        d = ImageDraw.Draw(mask)
        d.rectangle((x, 20, x + 10, 44), fill=255)
        d.rectangle((x, 65, x + 10, 79), fill=255)
        path = root / f"U{i + 1}.png"
        mask.save(path)
        units.append(
            {
                "id": f"U{i + 1}",
                "operation": "attribute",
                "attribute_kind": "color",
                "target": {
                    "parent_instance_id": str(i + 100),
                    "annotation_id": i,
                    "candidate_unit": i + 1,
                    "category": "chair:leg",
                    "mask": path.name,
                    "mask_sha256": sha256_file(path),
                    "box": [x, 20, x + 11, 80],
                    "point": [x + 5, 30],
                    "ref": f"SECRET_INSTANCE_DESCRIPTION_{i}",
                    "scope": "both legs",
                    "geometry": {"area_fraction": 0.02, "significant_components": 2},
                },
                "interaction": {"has_ref": ref, "locator": locator},
                "instruction_ref": f"Recolor SECRET_INSTANCE_DESCRIPTION_{i} blue.",
                "instruction_noref": "Recolor both legs blue.",
                "completion_requirement": "Both visible legs blue.",
                "preserve": ["The seat, background, and other objects."],
            }
        )
    case = {
        "schema_version": "2.0",
        "id": "v2-synthetic",
        "source": {
            "family_id": "synthetic",
            "image": image.name,
            "sha256": sha256_file(image),
            "size": [160, 120],
            "dataset": "synthetic",
            "split": "test",
            "image_id": "1",
        },
        "units": units,
        "difficulty": {
            "mechanisms": ["disconnected_parts"],
            "evidence_zh": "测试用分离细杆",
            "specific_protection_zh": "座椅",
        },
        "review": {
            "decision": "accept",
            "kind": "ai_direct_visual",
            "evidence": "synthetic fixture only",
            "reviewer": "test",
            "card": image.name,
            "card_sha256": sha256_file(image),
        },
    }
    manifest = root / "cases.jsonl"
    write_jsonl(manifest, [case])
    return root, manifest, case


def test_v2_counts_objects_not_mask_components(v2release):
    root, manifest, case = v2release
    stats = validate(manifest, root)
    assert stats["units"] == 4
    assert stats["unique_sources"] == 1
    with pytest.raises(ValueError, match="at least|expected at least"):
        validate(manifest, root, 200)
    case["units"][1]["target"]["parent_instance_id"] = case["units"][0]["target"][
        "parent_instance_id"
    ]
    write_jsonl(manifest, [case])
    with pytest.raises(ValueError, match="physical parent"):
        load_cases(manifest)


@pytest.mark.parametrize(
    "bad",
    ["no_ref_no_region", "same_interaction", "outside_point", "changed_mask", "changed_review"],
)
def test_v2_rejects_invalid_release(v2release, bad):
    root, manifest, c = v2release
    if bad == "no_ref_no_region":
        c["units"][0]["interaction"]["has_ref"] = False
    elif bad == "same_interaction":
        for u in c["units"]:
            u["interaction"] = {"has_ref": False, "locator": "point"}
    elif bad == "outside_point":
        c["units"][0]["target"]["point"] = [159, 119]
    elif bad == "changed_review":
        c["review"]["card_sha256"] = "changed"
    else:
        Image.new("L", (160, 120), 255).save(root / "U1.png")
    write_jsonl(manifest, [c])
    with pytest.raises(ValueError):
        validate(manifest, root)


@pytest.mark.parametrize("protocol", ["visual_locator_v2", "native_regions_v2"])
def test_public_projection_and_diagnostic_identity(v2release, protocol):
    root, manifest, c = v2release
    jobs = prepare(
        manifest, root, root / protocol, protocol, ("mixed", "all_ref", "all_mask_noref", "single")
    )
    assert len(jobs) == 7
    assert len({j["case_id"] for j in jobs}) == 1
    for job in jobs:
        verify_job(job)
        assert "target" not in job and "review" not in job
        for u in job["units"]:
            assert "target" not in u and "completion_requirement" not in u
            if not u["has_ref"]:
                assert "SECRET_INSTANCE_DESCRIPTION" not in u["instruction"]
            if u["locator"] == "none":
                assert "region" not in u
            if "region" in u:
                assert set(u["region"]) == {u["locator"]}
        if job["variant"] == "all_ref":
            assert len(job["images"]) == len(job["input_files"]) == 1
    mixed = jobs[0]
    assert "SECRET_INSTANCE_DESCRIPTION_1" not in mixed["prompt"]
    assert "SECRET_INSTANCE_DESCRIPTION_3" not in mixed["prompt"]
    assert "SECRET_INSTANCE_DESCRIPTION_0" in mixed["prompt"]
    assert "SECRET_INSTANCE_DESCRIPTION_2" in mixed["prompt"]
    # The ref-only target's mask is a private evaluator asset, never an editor input.
    (root / "U1.png").write_bytes(b"private annotation changed")
    verify_job(mixed)


def test_public_tampering_and_private_field_rejection(v2release):
    root, manifest, c = v2release
    job = prepare(manifest, root, root / "inputs")[0]
    altered = copy.deepcopy(job)
    altered["prompt"] += " do something else"
    with pytest.raises(ValueError, match="digest"):
        verify_job(altered)
    altered = copy.deepcopy(job)
    altered["units"][0]["target"] = {"mask": "secret"}
    altered["input_digest"] = _digest(altered)
    with pytest.raises(ValueError, match="private/unknown"):
        verify_job(altered)
    altered = copy.deepcopy(job)
    altered["units"][0]["region"] = {"point": [12, 25]}
    altered["input_digest"] = _digest(altered)
    with pytest.raises(ValueError, match="leaked"):
        verify_job(altered)
    Image.new("RGB", (160, 120), "black").save(job["images"][1])
    with pytest.raises(ValueError, match="asset changed"):
        verify_job(job)


def test_native_geometry_rejects_out_of_bounds_and_wrong_types(v2release):
    root, manifest, _ = v2release
    job = prepare(manifest, root, root / "native", "native_regions_v2")[0]
    for coords in ([160, 30], [12.5, 30], [12, 30, 31]):
        bad = copy.deepcopy(job)
        bad["units"][1]["region"]["point"] = coords
        bad["input_digest"] = _digest(bad)
        with pytest.raises(ValueError, match="native"):
            verify_job(bad)


@pytest.fixture
def v2pipeline(v2release, fake_adapter):
    root, manifest, case = v2release
    jobs = prepare(manifest, root, root / "inputs")
    rows = run_editor(root / "inputs/jobs.jsonl", root / "outputs", fake_adapter[0], "SMOKE_ONLY")
    return root, manifest, jobs, rows, fake_adapter


def test_editor_resume_configuration_and_output_integrity(v2pipeline):
    root, manifest, jobs, rows, (adapter, calls) = v2pipeline
    run_editor(root / "inputs/jobs.jsonl", root / "outputs", adapter, "SMOKE_ONLY")
    assert len(calls) == 1
    assert "target" not in calls[0][0]["units"][0]
    with pytest.raises(ValueError, match="changed input/model/config"):
        run_editor(root / "inputs/jobs.jsonl", root / "outputs", adapter, "SMOKE_ONLY", seed=9)
    Path(rows[0]["output_image"]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="modified"):
        run_editor(root / "inputs/jobs.jsonl", root / "outputs", adapter, "SMOKE_ONLY")


def full_score(job, row):
    score = {**binding(job, row), **blank_scores(job["unit_ids"])}
    score.update(judge_kind="ai", judge_name="synthetic_test_not_model_result")
    for u in score["units"]:
        for dim in "EPQ":
            u[dim] = {
                "pass": True,
                "evidence": "Synthetic fixture, not an actual benchmark judgement.",
            }
    for d in ("global_P", "global_Q"):
        score[d] = {"pass": True, "evidence": "Synthetic fixture."}
    return score


def test_strict_conjunction_never_averages_away_one_failed_unit(v2pipeline):
    root, manifest, jobs, rows, _ = v2pipeline
    job, row = jobs[0], rows[0]
    s = full_score(job, row)
    assert evaluate_score(job, row, s)["joint_pass"]
    for uid in range(4):
        for dim in "EPQ":
            bad = copy.deepcopy(s)
            bad["units"][uid][dim]["pass"] = False
            assert not evaluate_score(job, row, bad)["joint_pass"]
    for dim in ("global_P", "global_Q"):
        bad = copy.deepcopy(s)
        bad[dim]["pass"] = False
        assert not evaluate_score(job, row, bad)["joint_pass"]
    for value in (1, "true", None):
        bad = copy.deepcopy(s)
        bad["units"][0]["E"]["pass"] = value
        with pytest.raises(ValueError, match="boolean"):
            evaluate_score(job, row, bad)
    bad = copy.deepcopy(s)
    bad["units"].pop()
    with pytest.raises(ValueError, match="every authorized unit"):
        evaluate_score(job, row, bad)
    bad = copy.deepcopy(s)
    bad["output_sha256"] = "different"
    with pytest.raises(ValueError, match="different inputs/output"):
        evaluate_score(job, row, bad)


def test_judge_fixed_crops_and_incomplete_denominator(v2pipeline):
    root, manifest, jobs, rows, _ = v2pipeline
    prepared = prepare_judge(
        manifest, root, root / "inputs/jobs.jsonl", root / "outputs/outputs.jsonl", root / "judge"
    )
    assert len(prepared[0]["private_evaluation_details"]) == 4
    for detail in prepared[0]["private_evaluation_details"]:
        assert Image.open(detail["source_crop"]).size == Image.open(detail["output_crop"]).size
    empty = root / "empty.jsonl"
    write_jsonl(empty, [])
    with pytest.raises(ValueError, match="incomplete"):
        report(
            manifest,
            root / "inputs/jobs.jsonl",
            root / "outputs/outputs.jsonl",
            empty,
            root / "report.json",
        )
    r = report(
        manifest,
        root / "inputs/jobs.jsonl",
        root / "outputs/outputs.jsonl",
        empty,
        root / "report.json",
        True,
    )
    assert {
        k: r["groups"]["mixed/all"][k]
        for k in ["cases", "evaluated", "joint_pass", "joint_success_rate"]
    } == {
        "cases": 1,
        "evaluated": 0,
        "joint_pass": 0,
        "joint_success_rate": 0.0,
    }
    assert r["primary_release_coverage"]["complete"]
    scores = root / "scores.jsonl"
    write_jsonl(scores, [full_score(jobs[0], rows[0])])
    r = report(
        manifest,
        root / "inputs/jobs.jsonl",
        root / "outputs/outputs.jsonl",
        scores,
        root / "report.json",
    )
    assert r["groups"]["mixed/all"]["joint_success_rate"] == 1
    assert read_jsonl(root / "judge/scores_template.jsonl")[0]["global_P"]["pass"] is None


def test_gallery_is_offline_with_relative_assets(v2release):
    root, manifest, c = v2release
    prepare(manifest, root, root / "inputs")
    path = build(manifest, root, root / "inputs/jobs.jsonl")
    text = path.read_text()
    assert "fetch(" not in text
    assert str(root) not in text
    assert "__PAYLOAD__" not in text
    assert (root / "final_review.jpg").exists()
