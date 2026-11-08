"""CPU-only four-process coordination, shared-file races, leases and graceful-stop contracts."""

import multiprocessing as mp
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import pytest
from samtok_benchmark.external_full.coordination import (
    Coordinator,
    RANKS,
    PeerClock,
    atomic,
    local_environment,
    read_retry,
    release_stopped,
    validate_topology,
)


def test_concurrent_overwrite_and_transient_missing_json(tmp_path):
    path = tmp_path / "heartbeat.json"
    observed, errors = ([], [])

    def writer():
        try:
            for seq in range(180):
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
    assert not clock.observe(None)
    ticks[0] = 20
    assert clock.observe({"sequence": 2})


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
        assert sum((r[1] == "done" for r in rows)) == 4
    else:
        assert all((r[1] == "error" for r in rows))
        assert any(("Peer failed" in r[2] for r in rows))


def test_last_worker_blocks_new_attempt_until_all_four_release(tmp_path):
    ctx, root = (mp.get_context("fork"), tmp_path / "run")
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
    before = (original.read_bytes(), original.stat().st_mtime_ns)
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
    assert child["EXTERNAL_FULL_CLUSTER_WORKERS"] == "4"
    assert child["EXTERNAL_FULL_CLUSTER_NODE_ID"] == "1"
    monkeypatch.setattr("socket.gethostname", lambda: "n124-253-176")
    with pytest.raises(ValueError, match="shared local"):
        validate_topology()


def test_graceful_stop_waits_for_owned_request_and_leaves_unrelated_process(tmp_path):
    c = Coordinator(tmp_path, "stop", 0, "ready", poll=0.01, interval=0.01)
    unrelated = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(60)"])
    child_script = tmp_path / "child.py"
    child_script.write_text(
        f"import signal,time\nfrom pathlib import Path\nstopped=[]\nsignal.signal(signal.SIGUSR1, lambda *_: stopped.append(True))\nPath({str(tmp_path / 'admitted')!r}).touch()\nwhile not stopped: time.sleep(.01)\ntime.sleep(.05)\nPath({str(tmp_path / 'completed')!r}).touch()\n"
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
