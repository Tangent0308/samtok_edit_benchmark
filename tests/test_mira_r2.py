"""CPU contracts for checkpoint comparison, provenance and safe resumption."""

import errno
import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_mira_r2 as audit  # noqa: E402
import report_mira_r2 as report  # noqa: E402
import run_mira_r2_full as run  # noqa: E402


def test_batch_partition_has_each_full_source_once():
    ids = [f"{i:03d}" for i in range(1, 201)]
    batches = run.batch_cases(ids)
    assert len(batches) == 20
    assert all(len(values) == 10 for values in batches.values())
    assert sorted(c for values in batches.values() for c in values) == ids
    assert batches["lane2_batch00"] == ids[2::4][:10]
    with pytest.raises(ValueError):
        run.batch_cases(ids[:-1])
    with pytest.raises(ValueError):
        run.batch_cases(ids[:-1] + [ids[0]])


def test_paired_formula_uses_component_means_and_aligned_sources():
    values = {"001": [0, 10, 10], "002": [10, 0, 10]}
    result = run.statistics(values, dict(reversed(list(values.items()))), list(values))
    assert result["rows"]["R2_1000"]["Overall"] == np.sqrt(50)
    assert result["paired_R2_minus_v4"]["Overall"] == 0
    assert result["paired_R2_minus_v4"]["CI95"]["Overall"] == [0, 0]
    with pytest.raises(ValueError):
        run.statistics(values, {"001": values["001"]}, list(values))
    with pytest.raises(ValueError):
        run.statistics({}, {}, [])
    with pytest.raises(ValueError):
        run.statistics({"001": [np.nan, 5, 5]}, {"001": [5, 5, 5]}, ["001"])


def test_resume_preserves_original_coordinator_but_rejects_changed_science(tmp_path):
    path = tmp_path / "PROVENANCE.json"
    old = {"script_sha256": "original", "adapter_files": {"weight": "fixed"}, "cases": ["001"]}
    run.preserve_provenance(path, old)
    before = path.read_bytes()
    run.preserve_provenance(path, dict(old, script_sha256="maintained"))
    assert path.read_bytes() == before
    with pytest.raises(ValueError):
        run.preserve_provenance(path, dict(old, adapter_files={"weight": "changed"}))
    assert path.read_bytes() == before


def test_append_preserves_original_bytes_on_nas_without_fsync(tmp_path, monkeypatch):
    doc = tmp_path / "RESULTS.md"
    doc.write_bytes("已有结果\n".encode())
    before = doc.read_bytes()
    content = "### 16.6 MIRA-Bench 全量 R2@1000\n\n已完成。\n"

    def unsupported(fd):
        raise OSError(errno.ENOSYS, "Not implemented")

    monkeypatch.setattr(run.os, "fsync", unsupported)
    run.append_section(content, doc)
    assert doc.read_bytes() == before + ("\n\n" + content).encode()
    run.append_section(content, doc)
    assert doc.read_bytes() == before + ("\n\n" + content).encode()
    with pytest.raises(ValueError, match="different content"):
        run.append_section(content + "不同内容", doc)


def test_judge_resume_requires_exact_committed_coverage(tmp_path):
    path = tmp_path / "scores/per_image_results.jsonl"
    path.parent.mkdir()
    assert not run.judge_complete(tmp_path, ["001", "002"])
    path.write_text(json.dumps({"image": "001.png"}) + "\n")
    assert not run.judge_complete(tmp_path, ["001", "002"])
    path.write_text(path.read_text() + json.dumps({"image": "002.png"}) + "\n")
    assert run.judge_complete(tmp_path, ["001", "002"])
    with pytest.raises(ValueError):
        run.judge_complete(tmp_path, ["001"])
    path.write_text(path.read_text() + json.dumps({"image": "001.png"}) + "\n")
    with pytest.raises(ValueError):
        run.judge_complete(tmp_path, ["001", "002"])


def test_retry_only_capacity_and_transport_failures():
    assert run.transient_error("RateLimitError: Error code: 429")
    assert run.transient_error("Error code: 503")
    assert not run.transient_error("ValueError: malformed model answer")
    assert not run.transient_error("AuthenticationError: Error code: 401")
    assert [run.retry_delay(i) for i in range(1, 7)] == [30, 60, 120, 240, 300, 300]


def test_credentials_are_explicit_and_file_contents_are_not_read(tmp_path, monkeypatch):
    monkeypatch.delenv("MIRA_API_KEY_FILE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        run.credential_env()
    path = tmp_path / "private.key"
    path.write_text("unit-test-placeholder")
    env = run.credential_env(path)
    assert env["MIRA_API_KEY_FILE"] == str(path)
    assert "OPENAI_API_KEY" not in env


def test_reproduction_detects_changed_scores_or_coverage():
    report.equal_numbers({"n": 200, "score": [1.25]}, {"n": 200, "score": [1.25]}, "table")
    with pytest.raises(ValueError):
        report.equal_numbers({"n": 199}, {"n": 200}, "table")
    with pytest.raises(ValueError):
        report.equal_numbers({"score": [1.2501]}, {"score": [1.25]}, "table")
    with pytest.raises(ValueError):
        report.equal_numbers({"score": [1.25], "extra": 1}, {"score": [1.25]}, "table")


def test_verification_cannot_overwrite_formal_results(tmp_path):
    formal = tmp_path / "formal"
    formal.mkdir()
    with pytest.raises(ValueError):
        report.write_new(formal / "new", {"TABLE.md": "test"}, [formal])
    scratch = tmp_path / "scratch"
    report.write_new(scratch, {"TABLE.md": "test"}, [formal])
    with pytest.raises(ValueError):
        report.write_new(scratch, {"TABLE.md": "different"}, [formal])
    assert (scratch / "TABLE.md").read_text() == "test"


def test_audit_rejects_empty_negative_branch_and_wrong_step_count():
    call = {"prompt": "U1: remove object <|mt_start|><|mt_0001|><|mt_end|>.",
            "fallback_units": 0,
            "parameters": {"num_inference_steps": 40, "seed": 42, "use_kv_cache": True,
                           "cfg_scale": 2.0, "mode": "inline", "pass2_te": "raw",
                           "negative_prompt": "U1: remove object."}}
    result = {"fallback_units": 0, "status": "completed",
              "native": {"blend": None, "pass2_te": "raw", "actual_variant": "inline"},
              "calls": {"inference_api_calls": 1, "expected_dit_forwards": 80}}
    audit.validate_call(call, result)
    call["parameters"]["negative_prompt"] = ""
    with pytest.raises(ValueError, match="Negative branch"):
        audit.validate_call(call, result)
    call["parameters"]["num_inference_steps"] = 20
    with pytest.raises(ValueError, match="parameters"):
        audit.validate_call(call, result)
