"""CPU fixtures reproduce a remote host lacking preparation-host /tmp files."""

import json
import shutil

import pytest

from evaluation.protocol_audit.prepare_fairness_dev20_revision import portable_judge_entry
from samtok_benchmark.ifbench.fairness_dev_judge import Cache
from samtok_benchmark.ifbench import fairness_dev_run
from samtok_benchmark.io import digest, sha256_file, write_json


def fixture(tmp_path):
    origin, bundle = tmp_path / "original-node", tmp_path / "shared-bundle"
    config = {"synthetic": True}

    def block(value):
        return {"score": value, "pass": True, "evidence": "synthetic fixture"}

    scores = {
        "units": [{"id": "U1", "E": block(4), "P": block(3), "Q": block(3)}],
        "global_P": block(3),
        "global_Q": block(3),
    }
    receipt = origin / "receipt.json"
    write_json(receipt, {"synthetic_fixture": True, "new_judge_calls": 1})
    answer = origin / "effective.json"
    value = {
        "key": "synthetic-key",
        "run_id": digest(config),
        "output_sha256": "output",
        "status": "scored",
        "scores": scores,
        "execution_receipt": str(receipt),
        "raw_response": {"text": json.dumps(scores), "finish_reason": "stop"},
    }
    write_json(answer, value)
    entry = {
        "effective_record": str(answer),
        "sha256": sha256_file(answer),
        "provenance_files": [
            {"path": str(path), "sha256": sha256_file(path)} for path in (answer, receipt)
        ],
    }
    return origin, bundle, config, value, entry


def test_exact_cache_remains_usable_after_original_node_is_removed(tmp_path):
    origin, bundle, config, value, entry = fixture(tmp_path)
    portable = portable_judge_entry(bundle, entry, origin_base=origin)
    index = bundle / "cache/index.json"
    write_json(index, {"config": config, "entries": {"synthetic-key": portable}})
    shutil.rmtree(origin)  # Simulate the remote node: original /tmp does not exist.
    cache = Cache(index, config)
    assert cache.verify_portable_files(bundle) == {"entries": 1, "unique_files": 2}
    restored = cache.lookup(
        {
            "key": "synthetic-key",
            "case": {"units": [{"id": "U1"}]},
            "record": {"output_sha256": "output"},
        },
        {"run_id": digest(config)},
    )
    assert restored["scores"] == value["scores"] and restored["new_judge_calls"] == 0
    assert restored["execution_receipt"] == value["execution_receipt"]
    assert sha256_file(portable["effective_record"]) == entry["sha256"]


def test_startup_rejects_local_dependency_before_any_generation_check(tmp_path, monkeypatch):
    origin, bundle, config, value, entry = fixture(tmp_path)
    index = bundle / "cache/index.json"
    write_json(index, {"config": config, "entries": {"synthetic-key": entry}})
    plan = {
        "cache_index": str(index),
        "cache_index_sha256": sha256_file(index),
        "judge_config": config,
    }
    monkeypatch.setattr(fairness_dev_run, "verify_task", lambda *a: pytest.fail("too late"))
    with pytest.raises(ValueError, match="outside the portable bundle"):
        fairness_dev_run.preflight(plan, bundle / "plan.json", check_gpus=False)


def test_export_refuses_changed_evidence_and_preflight_detects_corruption(tmp_path):
    origin, bundle, config, value, entry = fixture(tmp_path)
    wrong = {**entry, "sha256": "not-the-record-hash"}
    with pytest.raises(ValueError, match="provenance changed"):
        portable_judge_entry(bundle, wrong, origin_base=origin)
    portable = portable_judge_entry(bundle, entry, origin_base=origin)
    index = bundle / "cache/index.json"
    write_json(index, {"config": config, "entries": {"synthetic-key": portable}})
    from pathlib import Path

    Path(portable["provenance_files"][1]["path"]).write_text("changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        Cache(index, config).verify_portable_files(bundle)


def test_repeated_cache_references_are_hashed_once(tmp_path, monkeypatch):
    from samtok_benchmark.ifbench import fairness_dev_judge as judge

    origin, bundle, config, _, entry = fixture(tmp_path)
    portable = portable_judge_entry(bundle, entry, origin_base=origin)
    index = bundle / "cache/index.json"
    write_json(index, {"config": config, "entries": {str(i): portable for i in range(10)}})
    cache = Cache(index, config)
    checked = []

    def record_hash(path):
        checked.append(str(path))
        return sha256_file(path)

    monkeypatch.setattr(judge, "sha256_file", record_hash)
    assert cache.verify_portable_files(bundle) == {"entries": 10, "unique_files": 2}
    assert len(checked) == len(set(checked)) == 2


def test_conflicting_hashes_for_one_cache_file_are_rejected(tmp_path):
    origin, bundle, config, _, entry = fixture(tmp_path)
    portable = portable_judge_entry(bundle, entry, origin_base=origin)
    portable["provenance_files"].append(
        {"path": portable["effective_record"], "sha256": "conflict"}
    )
    index = bundle / "cache/index.json"
    write_json(index, {"config": config, "entries": {"synthetic-key": portable}})
    with pytest.raises(ValueError, match="Conflicting hashes"):
        Cache(index, config).verify_portable_files(bundle)
