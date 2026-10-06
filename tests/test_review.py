import importlib.util
import json

import pytest

from samtok_benchmark.io import read_jsonl, write_json
from samtok_benchmark.review.package import export_reviewed, package_review
from samtok_benchmark.judge.human import package_human_review


def test_portable_review_and_instruction_migration(release, tmp_path):
    root, manifest, case = release
    out = tmp_path / "review"
    package_review(manifest, root, out)
    assert all((out / f).exists() for f in ("index.html", "app.js", "run_review.py", "cases.json"))
    spec = importlib.util.spec_from_file_location("isolated_review", out / "run_review.py")
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    record = {
        "version": 1,
        "cases": {
            case["id"]: {
                "status": "pass",
                "note": "checked",
                "instruction_revision": case["instruction_revision"],
                "instruction_override": "Paint the support tube green.",
            }
        },
    }
    server.save_results(record)
    assert server.load_results() == record
    derivative = json.loads((out / "reviewed_cases.json").read_text())
    assert derivative[0]["reviewed_instruction"] == "Paint the support tube green."
    assert json.loads((out / "cases.json").read_text())[0]["instruction"] == case["instruction"]
    with pytest.raises(FileExistsError):
        package_review(manifest, root, out)
    server.RESULTS_PATH.write_text("corrupted JSON")
    with pytest.raises(json.JSONDecodeError):
        server.load_results()


def test_export_passed_only_and_trace_changes(release, tmp_path):
    _, manifest, case = release
    results = tmp_path / "results.json"
    write_json(
        results,
        {
            "cases": {
                case["id"]: {
                    "status": "pass",
                    "instruction_revision": "mask_grounded_v2",
                    "instruction_override": "Paint the support tube green.",
                    "note": "reviewed",
                }
            }
        },
    )
    output = tmp_path / "approved.jsonl"
    export_reviewed(manifest, results, output, "reviewer_a")
    derivative = read_jsonl(output)[0]
    assert derivative["instruction"].endswith("green.")
    assert derivative["region_instruction"] == derivative["instruction"]
    assert derivative["instruction_source"] == "human_review:reviewer_a"
    assert read_jsonl(manifest)[0]["instruction"] == case["instruction"]
    assert output.with_suffix(".review_audit.jsonl").exists()


def test_stale_approval_cannot_publish_new_instruction(release, tmp_path):
    _, manifest, case = release
    results = tmp_path / "results.json"
    write_json(results, {"cases": {case["id"]: {"status": "pass", "instruction_revision": "old"}}})
    with pytest.raises(ValueError, match="recheck"):
        export_reviewed(manifest, results, tmp_path / "approved.jsonl", "reviewer")


def test_lowercase_human_override_cannot_publish(release, tmp_path):
    _, manifest, case = release
    results = tmp_path / "results.json"
    write_json(
        results,
        {
            "cases": {
                case["id"]: {
                    "status": "pass",
                    "instruction_revision": case["instruction_revision"],
                    "instruction_override": "paint the support tube green.",
                }
            }
        },
    )
    output = tmp_path / "approved.jsonl"
    with pytest.raises(ValueError, match="capital letter"):
        export_reviewed(manifest, results, output, "reviewer")
    assert not output.exists()


def test_review_copy_keeps_stale_decision_without_counting_as_approved(release, tmp_path):
    root, manifest, case = release
    out = tmp_path / "review"
    package_review(manifest, root, out)
    spec = importlib.util.spec_from_file_location("revision_review", out / "run_review.py")
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    record = {
        "version": 1,
        "cases": {
            case["id"]: {"status": "pass", "instruction_revision": "old", "note": "Keep my note"}
        },
    }
    server.save_results(record)
    assert server.load_results()["cases"][case["id"]]["status"] == "pass"
    derivative = json.loads((out / "reviewed_cases.json").read_text())[0]
    assert derivative["review_status"] == "unreviewed"
    assert derivative["previous_review_status"] == "pass"
    assert derivative["review_note"] == "Keep my note"


def test_human_output_review_is_blind_and_separate(pipeline, tmp_path):
    *_, jobs, rows = pipeline
    output = tmp_path / "human"
    result = package_human_review(jobs, output, "reviewer_a")
    assert result["available_outputs"] == 1
    samples = json.loads((output / "samples.json").read_text())
    assert "method" not in samples[0] and "scores" not in samples[0]
    assert samples[0]["input_digest"] == rows[0]["input_digest"]
    assert samples[0]["reviewer"] == "reviewer_a"
    assert all(
        (output / samples[0][k]).exists()
        for k in ("before_clean", "after_clean", "before_contours", "after_contours")
    )


def test_mixed_human_override_cannot_publish(release, tmp_path):
    _, manifest, case = release
    results = tmp_path / "results.json"
    write_json(
        results,
        {
            "cases": {
                case["id"]: {
                    "status": "pass",
                    "instruction_revision": case["instruction_revision"],
                    "instruction_override": "Paint the support tube green and remove the handle.",
                }
            }
        },
    )
    output = tmp_path / "approved.jsonl"
    with pytest.raises(ValueError, match="mixed operation clauses"):
        export_reviewed(manifest, results, output, "reviewer")
    assert not output.exists()
