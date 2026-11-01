"""Concurrent NAS visibility faults must not create false worker failures."""

from concurrent.futures import ThreadPoolExecutor
from functools import partial
import json
from pathlib import Path
import threading
import time

import pytest

from samtok_benchmark.ifbench import arnold
from samtok_benchmark.ifbench.live_state import read_live


def peer(root, timestamp):
    directory = root / "nodes/0"
    arnold.save(directory / "OWNER.json", {"identity": "run", "node": 0, "time": 1})
    arnold.save(directory / "heartbeat.json", {"identity": "run", "node": 0, "time": timestamp})
    return directory


def fast_reads(monkeypatch):
    monkeypatch.setattr(arnold, "read_live", partial(read_live, delay=0.001))


def test_live_read_retries_missing_and_partial_json(tmp_path, monkeypatch):
    calls = []

    def interrupted_read(path):
        calls.append(path)
        if len(calls) == 1:
            raise FileNotFoundError(path)
        return '{"time":' if len(calls) == 2 else '{"time": 3}'

    monkeypatch.setattr(Path, "read_text", interrupted_read)
    assert read_live(tmp_path / "heartbeat.json", delay=0) == {"time": 3}
    assert len(calls) == 3


def test_read_errors_and_invalid_schema_are_not_silenced(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text("[]")
    with pytest.raises(ValueError, match="JSON object"):
        read_live(path, delay=0)

    def denied(path):
        raise PermissionError(path)

    monkeypatch.setattr(Path, "read_text", denied)
    with pytest.raises(PermissionError):
        read_live(path, delay=0)


def test_old_owner_and_transient_reads_do_not_reset_or_expire_heartbeat(tmp_path, monkeypatch):
    fast_reads(monkeypatch)
    clock = [300000.0]
    mono = [1000.0]
    monkeypatch.setattr(arnold.time, "time", lambda: clock[0])
    monkeypatch.setattr(arnold.time, "monotonic", lambda: mono[0])
    directory = peer(tmp_path, clock[0])
    observations = {}
    check = partial(arnold.check_peers, tmp_path, "run", observations=observations)
    check()
    state = observations[(str(tmp_path), "run", 0)]
    for payload in (None, '{"time":', '{"identity":"run","node":0,"time":299999}'):
        clock[0] += 10
        mono[0] += 10
        path = directory / "heartbeat.json"
        if payload is None:
            path.unlink()
        else:
            path.write_text(payload)
        check()
        assert state.heartbeat_time == 300000 and state.last_advance == 1000
    # A missing OWNER must not make an already registered dead peer invisible.
    (directory / "OWNER.json").unlink()
    (directory / "heartbeat.json").write_text('{"time":')
    clock[0], mono[0] = 300301, 1301
    with pytest.raises(RuntimeError, match="heartbeat missing"):
        check()


def test_same_cached_timestamp_does_not_keep_dead_peer_alive(tmp_path, monkeypatch):
    fast_reads(monkeypatch)
    mono = [10.0]
    monkeypatch.setattr(arnold.time, "monotonic", lambda: mono[0])
    # Even a producer clock ahead of this reader cannot extend life forever.
    peer(tmp_path, time.time() + 10000)
    observations = {}
    arnold.check_peers(tmp_path, "run", 30, observations=observations)
    mono[0] = 41
    with pytest.raises(RuntimeError, match="heartbeat missing"):
        arnold.check_peers(tmp_path, "run", 30, observations=observations)


def test_initial_missing_heartbeat_has_bounded_grace_not_old_owner_time(tmp_path, monkeypatch):
    fast_reads(monkeypatch)
    mono = [10.0]
    monkeypatch.setattr(arnold.time, "monotonic", lambda: mono[0])
    directory = peer(tmp_path, time.time())
    (directory / "heartbeat.json").unlink()
    observations = {}
    arnold.check_peers(tmp_path, "run", 30, observations=observations)
    mono[0] = 41
    with pytest.raises(RuntimeError, match="heartbeat missing"):
        arnold.check_peers(tmp_path, "run", 30, observations=observations)


def test_concurrent_writer_and_reader_survive_nas_visibility_gaps(tmp_path, monkeypatch):
    fast_reads(monkeypatch)
    directory = peer(tmp_path, time.time())
    path = directory / "heartbeat.json"
    observations = {}
    check = partial(arnold.check_peers, tmp_path, "run", 30, observations=observations)
    check()
    barrier = threading.Barrier(2, timeout=10)

    def writer():
        for i in range(30):
            # Emulate another NAS client's transient view of rename. The actual
            # producer still publishes each complete record with save/replace.
            if i % 2:
                path.write_text('{"time":')
            else:
                path.unlink()
            barrier.wait()
            barrier.wait()  # Reader exhausts its short retries during this gap.
            arnold.save(path, {"identity": "run", "node": 0, "time": time.time()})
            barrier.wait()
            barrier.wait()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(writer)
        try:
            for _ in range(30):
                old = observations[(str(tmp_path), "run", 0)].last_advance
                barrier.wait()
                check()
                assert observations[(str(tmp_path), "run", 0)].last_advance == old
                barrier.wait()
                barrier.wait()
                check()
                barrier.wait()
            future.result()
        finally:
            barrier.abort()
    assert read_live(path)["identity"] == "run"


def test_heartbeat_identity_and_failure_markers_remain_fatal(tmp_path, monkeypatch):
    fast_reads(monkeypatch)
    directory = peer(tmp_path, time.time())
    arnold.save(directory / "heartbeat.json", {"identity": "other", "node": 0, "time": 1})
    with pytest.raises(RuntimeError, match="different plan"):
        arnold.check_peers(tmp_path, "run")
    arnold.save(directory / "FAILED.json", {"error": "native failure"})
    with pytest.raises(RuntimeError, match="native failure"):
        arnold.check_peers(tmp_path, "run")


def test_atomic_replacements_while_peer_checks_are_running(tmp_path, monkeypatch):
    fast_reads(monkeypatch)
    directory = peer(tmp_path, time.time())
    stop, started = threading.Event(), threading.Event()
    observations = {}

    def writer():
        writes = 0
        while not stop.is_set():
            arnold.save(directory / "heartbeat.json",
                        {"identity": "run", "node": 0, "time": time.time()})
            writes += 1
            started.set()
            stop.wait(0.001)
        return writes

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(writer)
        try:
            assert started.wait(5)
            for _ in range(30):
                arnold.check_peers(tmp_path, "run", 30, observations=observations)
        finally:
            stop.set()
        assert future.result() > 1
    assert observations[(str(tmp_path), "run", 0)].heartbeat_time is not None


def test_unavailable_barrier_is_pending_and_foreign_identity_is_rejected(tmp_path):
    path = tmp_path / "INPUTS_READY.json"
    path.write_text('{"identity":')
    assert not arnold.marker_ready(path, "run")
    arnold.save(path, {"identity": "run"})
    assert arnold.marker_ready(path, "run")
    arnold.save(path, {"identity": "other"})
    with pytest.raises(RuntimeError, match="different run"):
        arnold.marker_ready(path, "run")


def test_progress_visibility_gap_cannot_stop_native_workers(tmp_path, monkeypatch):
    from samtok_benchmark.ifbench import full_run

    monkeypatch.setattr(full_run, "read_live", partial(read_live, delay=0))
    root = tmp_path / "nodes/node-0"
    worker = root / "workers/qwen21/edit/shard-0-of-8/execution/status.json"
    worker.parent.mkdir(parents=True)
    worker.write_text('{"completed":')
    (root / "judge").mkdir()
    (root / "judge/progress.json").write_text('{"progress":')
    result = full_run.progress(
        {"results_root": str(tmp_path), "node_assignments": {"0": ["case"]},
         "settings": ["S1"], "digest": "plan"},
        0, {"model": "qwen21", "stage": "edit"},
        {"status": "running", "phases": []},
    )
    assert result["phase_counters_complete"] is False
    assert result["phase_eta_seconds_estimate"] is None
    assert result["judge"] is None
    assert result["unavailable_worker_status_files"] == [str(worker)]
    assert json.loads((root / "progress.json").read_text())["status"] == "running"
