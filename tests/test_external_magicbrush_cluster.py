"""CPU-only ownership, concurrent NAS status, locking and graceful-stop contracts."""

from __future__ import annotations

from collections import Counter
import json
import multiprocessing as mp
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from samtok_benchmark.external_magicbrush import MODELS, TRACKS
from samtok_benchmark.external_magicbrush.bundle import requests
from samtok_benchmark.external_magicbrush.cluster import (
    Coordinator,
    RANKS,
    PeerClock,
    atomic,
    local_environment,
    partition_sessions,
    read_retry,
    release_stopped,
    validate_topology,
)
from samtok_benchmark.external_magicbrush.launch import initialize_run, run_plan


def synthetic_index():
    cases, sessions = [], []
    for length, count in [(1, 216), (2, 120), (3, 199)]:
        for _ in range(count):
            sid = str(len(sessions))
            sessions.append(sid)
            cases.extend(
                {"session_id": sid, "case_id": f"{sid}-{turn}", "turn": turn, "track": track}
                for turn in range(1, length + 1)
                for track in TRACKS
            )
    return {"sessions": sessions, "cases": cases, "digest": "unchanged"}


def test_complete_session_ownership_and_thirty_two_score_shards():
    index = synthetic_index()
    counts = Counter(i["session_id"] for i in requests(index, index["sessions"]))
    ownership = [partition_sessions(index["sessions"], counts, rank) for rank in RANKS]
    assert sum(map(len, ownership)) == 535
    totals = [sum(counts[s] for s in group) for group in ownership]
    assert max(totals) - min(totals) <= 2
    groups = [requests(index, sessions) for sessions in ownership]
    keys = [{i["key"] for i in group} for group in groups]
    full = requests(index, index["sessions"])
    assert len(set.union(*keys)) == sum(map(len, keys))
    assert set.union(*keys) == {i["key"] for i in full}
    assert len(full) * len(MODELS) == 25136
    for rank, group in enumerate(groups):
        assert all(i["previous_key"] in keys[rank] for i in group if i["mode"] == "iterative")
    pairs = [(m, i["key"]) for m in MODELS for i in full]
    shards = [pairs[s::32] for s in range(32)]
    assert len(set(sum(shards, []))) == sum(map(len, shards)) == len(pairs)


def test_global_plan_and_snapshot_reuse(tmp_path):
    index, config = synthetic_index(), {"seed": 42}
    plan = run_plan(tmp_path / "bundle", index, config, tmp_path / "result", MODELS)
    assert plan["session_ids"] == index["sessions"]
    initialize_run(plan, config, tmp_path / "result")
    before = {
        p: (p.read_bytes(), p.stat().st_mtime_ns)
        for p in (tmp_path / "result").rglob("*")
        if p.is_file()
    }
    initialize_run(plan, config, tmp_path / "result")
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == value for p, value in before.items())
    with pytest.raises(ValueError):
        initialize_run({**plan, "seed": 43}, config, tmp_path / "result")


def test_four_native_queues_cover_each_stage_once_and_resume_without_calls(tmp_path, monkeypatch):
    from samtok_benchmark.external_magicbrush import launch as module
    from samtok_benchmark.external_magicbrush.worker import stages, source_identity, result_path

    index = synthetic_index()
    index["sessions"] = ["0", "216", "336", "337"]  # Mixed lengths on all four nodes.
    index["cases"] = [i for i in index["cases"] if i["session_id"] in index["sessions"]]
    config = json.loads((module.REPO / "configs/external/magicbrush.json").read_text())
    config["formal_results_root"] = str(tmp_path / "formal")
    config_path, estimate_path = tmp_path / "config.json", tmp_path / "estimate.json"
    atomic(config_path, config)
    atomic(
        estimate_path,
        {
            "all_methods_smoke_passed": True,
            "bundle_digest": index["digest"],
            "source_code": source_identity(),
            "total_gpu_hours_estimate": 0.1,
            "methods": [{"model": m, "generation_seconds_mean": 1} for m in MODELS],
        },
    )
    output = tmp_path / "formal/run"
    initialize_run(run_plan(tmp_path / "bundle", index, config, output, MODELS), config, output)
    monkeypatch.setattr(module, "load_bundle", lambda _: index)
    monkeypatch.setattr(module, "verify_config", lambda _: None)
    monkeypatch.setattr(module, "gpu_gate", lambda *_: None)
    monkeypatch.setattr(module.signal, "signal", lambda *_: None)
    calls, processed, guard = [], set(), threading.Lock()

    class FakeNativeWorker:
        def __init__(self, command, **kwargs):
            self.returncode = None
            with guard:
                self.pid = 900000 + len(calls)
                calls.append(command)
                model, stage = [command[command.index(flag) + 1] for flag in ["--model", "--stage"]]
                wave = int(command[command.index("--wave") + 1])
                sessions = command[command.index("--sessions") + 1 :]
                for item in requests(index, sessions):
                    if (
                        wave != -1
                        and (0 if item["mode"] == "independent" else item["turn"]) != wave
                    ):
                        continue
                    key = (model, stage, item["key"])
                    assert key not in processed
                    processed.add(key)
                    atomic(result_path(output, model, stage, item["key"]), {"status": "completed"})

        def wait(self):
            self.returncode = 0
            return 0

        def poll(self):
            return self.returncode

    monkeypatch.setattr(module.subprocess, "Popen", FakeNativeWorker)
    monkeypatch.setenv("MAGICBRUSH_CLUSTER_WORKERS", "4")
    args = SimpleNamespace(
        config=str(config_path),
        bundle=str(tmp_path / "bundle"),
        output=str(output),
        gpus="0,1,2,3,4,5,6,7",
        models=list(MODELS),
        smoke=False,
        cache_dir=str(tmp_path / "cache"),
        estimate=str(estimate_path),
        attempt="first",
    )
    for attempt in ["first", "resume"]:
        args.attempt = attempt
        previous = len(calls)
        for rank in RANKS:
            monkeypatch.setenv("MAGICBRUSH_CLUSTER_NODE_ID", str(rank))
            result = module.launch(args, node_rank=rank)
            assert not result["failed_processes"] and not result["remaining_tasks"]
        if attempt == "resume":
            assert len(calls) == previous
    expected = {
        (m, stage, i["key"])
        for m in MODELS
        for stage in stages(m)
        for i in requests(index, index["sessions"])
    }
    assert processed == expected


def test_concurrent_overwrite_and_transient_missing_json(tmp_path):
    path = tmp_path / "heartbeat.json"
    observed, errors = [], []

    def writer():
        try:
            for seq in range(180):
                # Exercise both real atomic replacement and NAS-like visibility gaps.
                if seq % 10 == 0:
                    path.unlink(missing_ok=True)
                    path.write_text('{"sequence":')
                    time.sleep(0.001)
                atomic(path, {"sequence": seq})
                time.sleep(0.001)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=writer)
    thread.start()
    while thread.is_alive():
        row = read_retry(path, attempts=2, delay=0.001)
        if row:
            observed.append(row["sequence"])
    thread.join()
    assert not errors and observed
    assert read_retry(path)["sequence"] == 179
    ticks = [0.0]
    clock = PeerClock(10, clock=lambda: ticks[0])
    assert not clock.observe({"sequence": 1})
    ticks[0] = 9
    assert not clock.observe(None)
    assert clock.last_new == 0
    assert not clock.observe({"sequence": 2})
    ticks[0] = 15
    assert not clock.observe(None)  # Must retain t=9, never revert to owner startup t=0.
    ticks[0] = 20
    assert clock.observe({"sequence": 2})  # Rereading the same sequence does not reset staleness.


def _node(root, rank, events, mode="normal"):
    c = Coordinator(
        root,
        "test",
        rank,
        "ready",
        hostname=f"host-{rank}",
        interval=0.025,
        poll=0.01,
        stale_seconds=3,
        join_seconds=10,
    )
    entered = False
    try:
        c.enter()
        entered = True
        c.barrier("JOINED")
        if mode == "failure" and rank == 0:
            raise RuntimeError("simulated infrastructure error")
        if mode == "lock" and rank != 3:
            c.marker("COMPLETE")
            events.put((rank, "exiting"))
            return
        if mode == "lock" and rank == 3:
            deadline = time.monotonic() + 10
            while not (Path(root) / "release").exists() and time.monotonic() < deadline:
                c.check()
                time.sleep(0.02)
            events.put((rank, "released"))
            return
        peers = c.barrier("GENERATED")
        assert set(peers) == set(RANKS) - {rank}
        events.put((rank, "scoring"))
        c.barrier("SCORED")
        c.barrier("COMPLETE")
        events.put((rank, "done"))
    except BaseException as error:
        if entered:
            c.marker("FAILED", {"error": repr(error)})
        events.put((rank, "error", str(error)))
    finally:
        c.close()


@pytest.mark.parametrize("mode", ["normal", "failure"])
def test_four_process_barriers_and_peer_failure(tmp_path, mode):
    ctx = mp.get_context("fork")
    events = ctx.Queue()
    children = [
        ctx.Process(target=_node, args=(str(tmp_path), rank, events, mode)) for rank in [3, 2, 1, 0]
    ]
    for p in children:
        p.start()
    for p in children:
        p.join(20)
        assert not p.is_alive() and p.exitcode == 0
    rows = [events.get(timeout=2) for _ in range(8 if mode == "normal" else 4)]
    if mode == "normal":
        assert sum(r[1] == "done" for r in rows) == 4
    else:
        assert all(r[1] == "error" for r in rows)
        assert any("Peer failed" in r[2] for r in rows)


def test_last_worker_blocks_new_attempt_until_all_four_release(tmp_path):
    ctx, root = mp.get_context("fork"), tmp_path / "run"
    events = ctx.Queue()
    children = [ctx.Process(target=_node, args=(str(root), rank, events, "lock")) for rank in RANKS]
    for p in children:
        p.start()
    rows = [events.get(timeout=10) for _ in range(3)]
    assert set(rows) == {(r, "exiting") for r in (0, 1, 2)}
    for p in children[:3]:
        p.join(5)
        assert p.exitcode == 0
    assert children[3].is_alive()
    c = Coordinator(root, "next", 0, "ready")
    try:
        with pytest.raises(RuntimeError, match="active"):
            c.enter()
    finally:
        c.close()
    (root / "release").touch()
    children[3].join(5)
    assert children[3].exitcode == 0
    c = Coordinator(root, "after-release", 0, "ready")
    try:
        c.enter()
        assert c.lease["attempt"] == "after-release"
    finally:
        c.close()


def test_same_host_and_stale_peer_are_rejected(tmp_path):
    c = Coordinator(tmp_path, "samehost", 0, "ready", hostname="same", interval=0.01)
    try:
        c.enter()
        atomic(c.peers[1] / "OWNER.json", {**c.lease, "hostname": "same"})
        with pytest.raises(ValueError, match="same host"):
            c.check()
        atomic(c.peers[1] / "OWNER.json", {**c.lease, "hostname": "other"})
        atomic(c.peers[1] / "heartbeat.json", {**c.lease, "sequence": 7})
        c.check()
        c.peer_clocks[1].last_new = time.monotonic() - 601
        (c.peers[1] / "heartbeat.json").unlink()
        with pytest.raises(RuntimeError, match="stale"):
            c.check()
    finally:
        c.close()


def test_force_release_requires_explicit_confirmation_and_preserves_records(tmp_path):
    original = tmp_path / "runs/example/result.json"
    atomic(original, {"status": "completed", "test_only": True})
    before = original.read_bytes(), original.stat().st_mtime_ns
    c = Coordinator(tmp_path, "stopped", 0, "ready")
    try:
        c.enter()
    finally:
        c.close()
    with pytest.raises(ValueError, match="confirmation"):
        release_stopped(tmp_path, "stopped", "platform stopped all four workers")
    result = release_stopped(tmp_path, "stopped", "platform stopped all four workers", True)
    assert not result["scientific_records_changed"]
    c = Coordinator(tmp_path, "recovered", 0, "ready")
    try:
        c.enter()
        assert c.lease["attempt"] == "recovered"
    finally:
        c.close()
    assert (original.read_bytes(), original.stat().st_mtime_ns) == before
    assert list((tmp_path / "cluster/stopped").glob("LEASE_RELEASED-*"))


def test_native_environment_preserves_real_topology_and_local_guard(monkeypatch):
    monkeypatch.setenv("ARNOLD_WORKER_NUM", "4")
    monkeypatch.setenv("ARNOLD_WORKER_GPU", "8")
    monkeypatch.setenv("ARNOLD_ID", "1")
    monkeypatch.setattr("socket.gethostname", lambda: "healthy-remote-worker")
    assert validate_topology() == 1
    child = local_environment(1)
    assert child["ARNOLD_WORKER_NUM"] == "1" and child["WORLD_SIZE"] == "1"
    assert child["MAGICBRUSH_CLUSTER_WORKERS"] == "4"
    assert child["MAGICBRUSH_CLUSTER_NODE_ID"] == "1"
    monkeypatch.setattr("socket.gethostname", lambda: "n124-253-176")
    with pytest.raises(ValueError, match="shared local"):
        validate_topology()


def test_graceful_stop_waits_for_owned_request_and_leaves_unrelated_process(tmp_path):
    c = Coordinator(tmp_path, "stop", 0, "ready", poll=0.01, interval=0.01)
    unrelated = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(60)"])
    child_script = tmp_path / "child.py"
    child_script.write_text(
        "import signal,time\nfrom pathlib import Path\n"
        "stopped=[]\nsignal.signal(signal.SIGUSR1, lambda *_: stopped.append(True))\n"
        f"Path({str(tmp_path / 'admitted')!r}).touch()\n"
        "while not stopped: time.sleep(.01)\ntime.sleep(.05)\n"
        f"Path({str(tmp_path / 'completed')!r}).touch()\n"
    )
    try:
        c.enter()

        def stop_later():
            deadline = time.monotonic() + 10
            while not (tmp_path / "admitted").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            c.stop.set()

        thread = threading.Thread(target=stop_later)
        thread.start()
        with pytest.raises(RuntimeError, match="Stop requested"):
            c.jobs(
                [
                    (
                        [sys.executable, "-I", str(child_script)],
                        dict(os.environ),
                        tmp_path / "child.log",
                    )
                ],
                "fake-generation",
            )
        thread.join()
        assert (tmp_path / "completed").exists()
        assert unrelated.poll() is None
    finally:
        c.close()
        unrelated.send_signal(signal.SIGTERM)
        unrelated.wait()
