import hashlib
from pathlib import Path

import pytest

from samtok_benchmark.ifbench.fairness_dev_plan import check_hash


def test_hash_detects_same_length_change_with_identical_file_metadata(tmp_path, monkeypatch):
    p = tmp_path / "source"
    p.write_bytes(b"abcd")
    expected = hashlib.sha256(b"abcd").hexdigest()
    check_hash(p, expected)
    check_hash(p, expected)
    unchanged_stat = p.stat()
    p.write_bytes(b"efgh")
    # Reproduce coarse timestamp filesystems without a timing-dependent sleep.
    monkeypatch.setattr(Path, "stat", lambda self, **kwargs: unchanged_stat)
    with pytest.raises(ValueError, match="Artifact changed"):
        check_hash(p, expected)


def test_archived_plan_checks_its_explicit_snapshot_without_weakening_default(tmp_path):
    from samtok_benchmark.io import digest, sha256_file, write_json
    from samtok_benchmark.ifbench.fairness_dev_plan import MODELS, SETTINGS, SCHEMA, load_plan

    cases = [f"case-{i}" for i in range(20)]
    auth, selection, plan_path = (
        tmp_path / name for name in ("auth.json", "selection.json", "plan.json")
    )
    write_json(auth, {"dev20_and_judge_authorized": True})
    write_json(selection, {"case_ids": cases, "parent_split_digest": "fixed-split"})
    write_json(
        tmp_path / "plan/splits.json",
        {"digest": "fixed-split", "dev": cases, "test": ["test-only"]},
    )
    archived = tmp_path / "repo"
    helper = archived / "historical_helper.py"
    helper.parent.mkdir()
    helper.write_text("ARCHIVED = True\n")
    plan = {
        "schema": SCHEMA,
        "model_order": MODELS,
        "settings": SETTINGS,
        "seed": 42,
        "case_ids": cases,
        "paths": {"shared": str(tmp_path)},
        "authorization_path": str(auth),
        "authorization_sha256": sha256_file(auth),
        "selection_path": str(selection),
        "selection_sha256": sha256_file(selection),
        "tasks": [
            {"model": m, "setting": s, "case_id": c}
            for m in MODELS
            for s in SETTINGS
            for c in cases
        ],
        "helper_sha256": {helper.name: sha256_file(helper)},
    }
    plan["digest"] = digest(plan)
    write_json(plan_path, plan)
    assert load_plan(plan_path, helper_root=archived) == plan
    with pytest.raises(FileNotFoundError):
        load_plan(plan_path)  # A parent-only file is not accepted as active code.
    helper.write_text("ARCHIVED = False\n")
    with pytest.raises(ValueError, match="Artifact changed"):
        load_plan(plan_path, helper_root=archived)
