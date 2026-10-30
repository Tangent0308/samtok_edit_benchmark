import json
import sys
import time

import pytest

from samtok_benchmark.ifbench import fairness_dev_run as runner


def test_foreground_waits_until_child_completes(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "print_progress", lambda *a: None)
    result = runner.run_processes(
        [([sys.executable, "-c", 'import time; time.sleep(.15); print("done")'], None)],
        {},
        None,
        tmp_path,
    )
    assert result["return_codes"] == [0]
    assert "done" in (tmp_path / "worker-0.log").read_text()


def test_failed_worker_stops_only_its_sibling_group(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "print_progress", lambda *a: None)
    start = time.monotonic()
    with pytest.raises(RuntimeError, match="Worker exited"):
        runner.run_processes(
            [
                ([sys.executable, "-c", "raise SystemExit(7)"], None),
                ([sys.executable, "-c", "import time; time.sleep(60)"], None),
            ],
            {},
            None,
            tmp_path,
        )
    assert time.monotonic() - start < 30
    children = json.loads((tmp_path / "children.json").read_text())
    assert len(children) == 2


def test_finished_plan_does_not_require_free_gpus(tmp_path, monkeypatch):
    results = tmp_path / "results"
    results.mkdir()
    (results / "COMPLETED.json").write_text(json.dumps({"plan_digest": "fixed"}))
    monkeypatch.setattr(runner, "verify_package", lambda p: tmp_path)
    monkeypatch.setattr(
        runner, "load_plan", lambda p: {"digest": "fixed", "results_root": str(results)}
    )
    monkeypatch.setattr(
        runner,
        "preflight",
        lambda *a, **kw: pytest.fail("no GPU check or inference after completion"),
    )
    runner.execute(tmp_path / "plan.json")
