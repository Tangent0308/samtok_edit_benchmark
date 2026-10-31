import copy

import pytest

from evaluation.protocol_audit.wait_qwen21_memory_probe import blocking_reasons


@pytest.fixture
def idle():
    config = {
        "hostname": "local-training-node",
        "all_gpu_uuids": [f"gpu-{i}" for i in range(8)],
        "minimum_free_mib": 70 * 1024,
        "maximum_idle_utilization": 5,
        "minimum_cpu_available_gib": 100,
    }
    snapshot = {
        "hostname": config["hostname"],
        "processes": [],
        "cpu_available_gib": 128,
        "gpus": [
            {"index": i, "uuid": uuid, "free_mib": 79 * 1024, "utilization": 0}
            for i, uuid in enumerate(config["all_gpu_uuids"])
        ],
    }
    return config, snapshot


def test_only_idle_full_registered_host_is_ready(idle):
    config, snapshot = idle
    assert not blocking_reasons(snapshot, config)


def test_even_small_or_replacement_gpu_process_blocks_launch(idle):
    config, snapshot = idle
    # An exited initial training PID is insufficient: any current process blocks.
    snapshot["processes"] = [{"pid": 999, "gpu_uuid": "gpu-0"}]
    assert "gpu_processes_still_active" in blocking_reasons(snapshot, config)


def test_idle_gap_between_training_stages_is_not_job_completion(idle):
    config, snapshot = idle
    snapshot["training_workflows_alive"] = [{"pid": 99, "start_ticks": "12"}]
    assert "training_workflow_still_active" in blocking_reasons(snapshot, config)


def test_explicit_background_allowance_never_covers_new_or_growing_jobs(idle):
    config, snapshot = idle
    config["existing_background_processes"] = [
        {"pid": 123, "gpu_uuids": ["gpu-0"], "maximum_used_mib": 2048}
    ]
    snapshot["processes"] = [{"pid": 123, "gpu_uuid": "gpu-0", "used_mib": 1596}]
    assert not blocking_reasons(snapshot, config)
    snapshot["processes"][0]["used_mib"] = 3000
    assert "gpu_processes_still_active" in blocking_reasons(snapshot, config)
    snapshot["processes"][0].update(pid=124, used_mib=1596)
    assert "gpu_processes_still_active" in blocking_reasons(snapshot, config)
    snapshot["processes"][0].update(pid=123, gpu_uuid="gpu-1")
    assert "gpu_processes_still_active" in blocking_reasons(snapshot, config)
    snapshot["processes"][0].update(gpu_uuid="gpu-0")
    snapshot["training_workflows_alive"] = [{"pid": 99, "start_ticks": "12"}]
    assert "training_workflow_still_active" in blocking_reasons(snapshot, config)


def test_waiter_does_not_launch_or_admit_while_training_uses_gpu(idle, tmp_path, monkeypatch):
    import json
    from evaluation.protocol_audit import wait_qwen21_memory_probe as gate

    config, snapshot = idle
    config.update(
        output_directory=str(tmp_path / "outputs"), source_sha256={}, poll_seconds=60, idle_polls=3
    )
    snapshot["processes"] = [{"pid": 999, "gpu_uuid": "gpu-0"}]
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(config))
    monkeypatch.setattr(gate, "query_resources", lambda *a: snapshot)
    monkeypatch.setattr(gate.subprocess, "Popen", lambda *a, **kw: pytest.fail("GPU launch"))

    def end_test_after_wait(seconds):
        assert seconds == 60
        raise InterruptedError("test observed wait without launch")

    monkeypatch.setattr(gate.time, "sleep", end_test_after_wait)
    with pytest.raises(InterruptedError):
        gate.run(plan)
    assert not (tmp_path / "ADMITTED.json").exists()
    assert not (tmp_path / "outputs").exists()
    assert json.loads((tmp_path / "gate_status.json").read_text())["new_inference_calls"] == 0


@pytest.mark.parametrize("problem", ["host", "missing", "duplicate", "busy", "memory", "ram"])
def test_incomplete_or_insufficient_resources_fail_closed(idle, problem):
    config, snapshot = copy.deepcopy(idle)
    if problem == "host":
        snapshot["hostname"] = "remote-node"
    elif problem == "missing":
        snapshot["gpus"].pop()
    elif problem == "duplicate":
        snapshot["gpus"][1]["uuid"] = "gpu-0"
    elif problem == "busy":
        snapshot["gpus"][4]["utilization"] = 80
    elif problem == "memory":
        snapshot["gpus"][4]["free_mib"] = 54000
    else:
        snapshot["cpu_available_gib"] = 50
    assert blocking_reasons(snapshot, config)
