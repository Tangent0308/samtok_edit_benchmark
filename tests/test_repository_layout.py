"""The public CLI and frozen runtimes must resolve source layouts consistently."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from evaluation.protocol_audit.bootstrap_fairness_dev20 import repo_pythonpath, write_wrapper
from samtok_benchmark.ifbench.cli import main
from samtok_benchmark.paths import source_relative


def test_source_paths_resolve_both_layouts_without_rewriting_evidence(tmp_path):
    relative = Path("samtok_benchmark/ifbench/helper.py")
    flat = tmp_path / relative
    flat.parent.mkdir(parents=True)
    flat.write_text("original")
    assert source_relative(relative, tmp_path) == relative.as_posix()
    modern = tmp_path / "src" / relative
    modern.parent.mkdir(parents=True)
    modern.write_text("new source")
    assert source_relative(relative, tmp_path) == "src/" + relative.as_posix()
    assert flat.read_text() == "original"
    with pytest.raises(ValueError):
        source_relative("../escape.py", tmp_path)


def test_src_runtime_wrapper_and_environment_agree(tmp_path):
    repo = tmp_path / "repo with spaces"
    (repo / "src").mkdir(parents=True)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    path = repo_pythonpath(repo)
    assert path == f"{repo}/src:{repo}"
    wrapper = write_wrapper("generation", runtime, {"python": "env/bin/python"}, repo)
    assert f"export PYTHONPATH='{path}'" in wrapper.read_text()


def test_cli_runs_frozen_bundle_entry_and_preserves_exit_status(tmp_path):
    bundle = tmp_path / "published bundle"
    bundle.mkdir()
    (bundle / "READY.json").write_text("{}")
    (bundle / "start.sh").write_text("#!/bin/sh\nexit 7\n")
    with patch("samtok_benchmark.ifbench.cli.subprocess.call", return_value=7) as run:
        assert main(["run-dev", "--bundle", str(bundle), "--validate-only"]) == 7
    assert run.call_args.args[0] == ["bash", str(bundle / "start.sh"), "--validate-only"]
    assert run.call_args.kwargs["cwd"] == bundle


def test_inspect_is_read_only_and_reports_completion(tmp_path, capsys):
    (tmp_path / "READY.json").write_text('{"published":true}')
    (tmp_path / "results").mkdir()
    (tmp_path / "results/COMPLETED.json").write_text('{"status":"complete"}')
    with patch("samtok_benchmark.ifbench.cli.subprocess.call") as run:
        assert main(["inspect-run", "--bundle", str(tmp_path)]) == 0
    run.assert_not_called()
    assert json.loads(capsys.readouterr().out)["results/COMPLETED.json"]["status"] == "complete"


def test_unpublished_bundle_never_launches(tmp_path):
    with patch("samtok_benchmark.ifbench.cli.subprocess.call") as run:
        with pytest.raises(FileNotFoundError):
            main(["run-dev", "--bundle", str(tmp_path)])
    run.assert_not_called()


def test_current_judge_source_matches_configuration():
    import hashlib

    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "configs/evaluation/fairness_v2_2_1mp.json").read_text())
    source = root / "src/samtok_benchmark/ifbench/dev_judge.py"
    assert (
        hashlib.sha256(source.read_bytes()).hexdigest() == config["judge_config"]["source_sha256"]
    )
