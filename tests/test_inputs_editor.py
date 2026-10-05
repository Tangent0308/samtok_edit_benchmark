import json

import pytest

from samtok_benchmark.editor import run_editor
from samtok_benchmark.inputs import prepare, verify_job
from samtok_benchmark.io import read_jsonl, write_jsonl
from samtok_benchmark.judge.prepare import prepare_judge


def test_modalities_do_not_leak_other_controls_or_answers(release, tmp_path):
    root, manifest, _ = release
    visual = prepare(manifest, root, tmp_path / "visual")
    assert len(visual) == 4
    for j in visual:
        verify_job(j)
        assert len(j["images"]) == (1 if j["setting"] == "text_only" else 2)
        assert j["controls"] == []
        assert "evaluation" not in json.dumps(j) and "target_local_content" not in j
    native = prepare(manifest, root, tmp_path / "native", protocol="native_regions_v1")
    for j in native:
        verify_job(j)
        assert len(j["images"]) == 1
        if j["setting"] == "text_only":
            assert j["controls"] == []
        else:
            field = j["setting"].removesuffix("_annotation")
            assert field in j["controls"][0]
            assert not ({"mask", "box", "point"} - {field}) & set(j["controls"][0])


def test_frozen_prompt_change_rejected(release, tmp_path):
    root, manifest, _ = release
    job = prepare(manifest, root, tmp_path / "prepared")[0]
    job["prompt"] = "A different task."
    with pytest.raises(ValueError, match="metadata changed"):
        verify_job(job)


def test_runner_resume_and_config_identity(release, fake_adapter, tmp_path):
    root, manifest, _ = release
    inputs = tmp_path / "inputs"
    prepare(manifest, root, inputs, ["text_only"])
    output = tmp_path / "editor"
    run_editor(inputs / "inputs.jsonl", output, fake_adapter[0], "model")
    run_editor(inputs / "inputs.jsonl", output, fake_adapter[0], "model")
    assert len(fake_adapter[1]) == 1
    with pytest.raises(ValueError, match="different inputs/config"):
        run_editor(inputs / "inputs.jsonl", output, fake_adapter[0], "model", seed=1)


def test_prepare_judge_rejects_old_instruction_output(pipeline, tmp_path):
    root, manifest, _, inputs, editor, _, _ = pipeline
    rows = read_jsonl(editor / "outputs.jsonl")
    rows[0]["manifest_sha256"] = "old instruction manifest"
    write_jsonl(editor / "outputs.jsonl", rows)
    with pytest.raises(ValueError, match="another instruction"):
        prepare_judge(
            manifest,
            root,
            inputs / "inputs.jsonl",
            editor / "outputs.jsonl",
            "test_model",
            tmp_path / "bad.jsonl",
        )


def test_missing_outputs_are_not_dropped(release, tmp_path):
    root, manifest, _ = release
    inputs = tmp_path / "inputs"
    prepare(manifest, root, inputs)
    empty = tmp_path / "outputs.jsonl"
    write_jsonl(empty, [])
    jobs = prepare_judge(
        manifest, root, inputs / "inputs.jsonl", empty, "model", tmp_path / "j.jsonl"
    )
    assert len(jobs) == 4
    assert all(j["delivery_status"] == "missing_output" for j in jobs)
    assert all(j["output_image"] is None for j in jobs)
