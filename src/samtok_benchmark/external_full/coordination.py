"""Four-node NAS coordination, with no distributed model process or network listener.

This module is standard-library-only so heartbeats also cover runtime staging.
Scientific generation and scoring implementations remain unchanged.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import threading
import time
import uuid


WORKERS, GPUS_PER_WORKER = 4, 8
RANKS = tuple(range(WORKERS))


def partition_sessions(sessions, counts, rank):
    """Balance fixed request counts without splitting a recurrent conversation."""
    if rank not in RANKS:
        raise ValueError("Invalid node rank")
    totals, owned = [0] * WORKERS, [set() for _ in RANKS]
    order = {sid: index for index, sid in enumerate(sessions)}
    for sid in sorted(sessions, key=lambda sid: (-counts[sid], order[sid])):
        node = min(RANKS, key=lambda r: (totals[r], len(owned[r]), r))
        totals[node] += counts[sid]
        owned[node].add(sid)
    return [sid for sid in sessions if sid in owned[rank]]


def read_retry(path, attempts=5, delay=0.1):
    """Never use exists() followed by open() for shared status snapshots."""
    for attempt in range(attempts):
        try:
            return json.loads(Path(path).read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            if attempt + 1 < attempts:
                time.sleep(delay)
    return None


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def claim(path, value):
    """Exclusive owner claim; incomplete visibility is handled by read_retry."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def release_stopped(output, attempt, reason, confirmed=False):
    """Release coordination only after the operator confirms all four workers exited."""
    if not confirmed or not reason.strip():
        raise ValueError(
            "Explicit confirmation that all four workers exited and a reason are required"
        )
    output = Path(output)
    lease = read_retry(output / "CLUSTER.lock" / "OWNER.json")
    if lease is None or lease["attempt"] != attempt:
        raise ValueError("The active lease does not belong to the specified stopped attempt")
    claim(
        output / "cluster" / attempt / "FORCED_RELEASE.json",
        {
            **lease,
            "confirmed_all_workers_stopped": True,
            "reason": reason,
            "operator_host": socket.gethostname(),
            "time": time.time(),
        },
    )
    return {"released_coordination_only": attempt, "scientific_records_changed": False}


class PeerClock:
    """Track newly observed sequences using our monotonic clock, not remote wall time."""

    def __init__(self, stale_seconds=600, clock=time.monotonic):
        self.stale_seconds, self.clock = stale_seconds, clock
        self.sequence, self.last_new = -1, None

    def observe(self, snapshot):
        if snapshot is not None and snapshot["sequence"] > self.sequence:
            self.sequence, self.last_new = snapshot["sequence"], self.clock()
        return self.last_new is not None and self.clock() - self.last_new > self.stale_seconds


def local_environment(rank):
    """Isolate each native single-GPU program from the outer ARNOLD topology.

    The outer coordinator validates the real 4 x 8 job. Native frozen workers
    expect an independent one-node runtime and do not participate in rendezvous.
    Preserve the real ownership explicitly rather than changing their code.
    """
    environment = dict(os.environ)
    for key in [
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "LD_PRELOAD",
        "IFBENCH_NATIVE_SOURCES",
        "RANK",
        "LOCAL_RANK",
        "LOCAL_WORLD_SIZE",
        "GROUP_RANK",
        "NODE_RANK",
        "MASTER_ADDR",
    ]:
        environment.pop(key, None)
    environment.update(
        ARNOLD_WORKER_NUM="1",
        ARNOLD_ID="0",
        WORLD_SIZE="1",
        EXTERNAL_FULL_CLUSTER_WORKERS=str(WORKERS),
        EXTERNAL_FULL_CLUSTER_NODE_ID=str(rank),
        MASTER_PORT="42000",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUNBUFFERED="1",
        PYTHONNOUSERSITE="1",
        TOKENIZERS_PARALLELISM="false",
        OMP_NUM_THREADS="4",
        CUDA_DEVICE_ORDER="PCI_BUS_ID",
    )
    return environment


def validate_topology():
    if (
        os.environ.get("ARNOLD_WORKER_NUM") != str(WORKERS)
        or os.environ.get("ARNOLD_WORKER_GPU") != "8"
    ):
        raise ValueError("Requires exactly four ARNOLD workers with eight GPUs each")
    if os.environ.get("ARNOLD_ID") not in tuple(map(str, RANKS)):
        raise ValueError("ARNOLD_ID must be 0, 1, 2 or 3")
    if socket.gethostname() == "n124-253-176":
        raise ValueError("This remote entry is forbidden on the shared local machine")
    return int(os.environ["ARNOLD_ID"])


class Coordinator:
    def __init__(
        self,
        output,
        attempt,
        rank,
        ready_sha,
        *,
        hostname=None,
        stale_seconds=600,
        join_seconds=3600,
        interval=15,
        poll=3,
    ):
        if rank not in RANKS or not re.fullmatch(r"[A-Za-z0-9_-]+", attempt):
            raise ValueError("Invalid node rank or attempt")
        self.output, self.attempt, self.rank = Path(output), attempt, rank
        self.identity = {"attempt": attempt, "ready_sha256": ready_sha}
        self.root = self.output / "cluster" / attempt
        self.mine = self.root / f"node-{rank}"
        self.peers = {r: self.root / f"node-{r}" for r in RANKS if r != rank}
        self.host = hostname or socket.gethostname()
        self.peer_clocks = {r: PeerClock(stale_seconds) for r in self.peers}
        self.join_seconds, self.interval, self.poll = join_seconds, interval, poll
        self.stop, self.closed = threading.Event(), threading.Event()
        self.heartbeat_error, self.thread = None, None
        self.phase, self.sequence, self.started = "joining", 0, time.monotonic()
        self.signals = {}
        self.claimed = False

    def enter(self):
        self.output.mkdir(parents=True, exist_ok=True)
        lease_dir = self.output / "CLUSTER.lock"
        lease_path = lease_dir / "OWNER.json"
        if self.rank == 0:
            self.root.mkdir(parents=True, exist_ok=False)
            self.lease = {**self.identity, "token": uuid.uuid4().hex}
            try:
                lease_dir.mkdir()
            except FileExistsError:
                old = read_retry(lease_path)
                if old is None:
                    raise RuntimeError("Active lease is unreadable; inspect it before recovery")
                old_root = self.output / "cluster" / old["attempt"]
                forced = read_retry(old_root / "FORCED_RELEASE.json")
                released = [read_retry(old_root / f"node-{r}" / "RELEASED.json") for r in RANKS]

                def valid(row):
                    return row is not None and all(row.get(k) == v for k, v in old.items())

                if not (all(valid(row) for row in released) or valid(forced)):
                    raise RuntimeError(
                        "Another attempt is active or was forcibly interrupted; "
                        "all four workers must exit before explicit recovery"
                    )
                # Claim retirement within that lease and recheck its token. A
                # delayed competing starter must never rename a newly acquired lease.
                retirement = lease_dir / "RETIRE"
                try:
                    retirement.mkdir()
                except FileExistsError:
                    raise RuntimeError("Another starter is retiring this lease") from None
                if read_retry(lease_path) != old:
                    retirement.rmdir()
                    raise RuntimeError("Active lease changed during admission")
                lease_dir.rename(old_root / ("LEASE_RELEASED-" + old["token"]))
                lease_dir.mkdir()
            atomic(lease_path, self.lease)
        else:
            deadline = time.monotonic() + self.join_seconds
            while True:
                lease = read_retry(lease_path)
                if lease and all(lease.get(k) == v for k, v in self.identity.items()):
                    self.lease = lease
                    break
                if time.monotonic() >= deadline or self.stop.wait(self.poll):
                    raise RuntimeError("Timed out or stopped while waiting for node 0 admission")
        self.mine.mkdir(parents=True, exist_ok=True)
        claim(
            self.mine / "OWNER.json",
            {
                **self.lease,
                "rank": self.rank,
                "hostname": self.host,
                "pid": os.getpid(),
                "workers": WORKERS,
                "gpus_per_worker": 8,
                "time": time.time(),
            },
        )
        self.claimed = True
        self.started = time.monotonic()
        for sig in (signal.SIGUSR1, signal.SIGTERM, signal.SIGINT):
            self.signals[sig] = signal.signal(sig, lambda *_: self.stop.set())
        self.thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.thread.start()
        return self

    def _heartbeat(self):
        try:
            while not self.closed.is_set():
                self.sequence += 1
                atomic(
                    self.mine / "heartbeat.json",
                    {
                        **self.lease,
                        "sequence": self.sequence,
                        "phase": self.phase,
                        "time": time.time(),
                    },
                )
                self.closed.wait(self.interval)
        except BaseException as error:
            self.heartbeat_error = error
            self.stop.set()

    def marker(self, name, value=None):
        atomic(self.mine / f"{name}.json", {**self.lease, "time": time.time(), "value": value})

    def peer_record(self, rank, name, attempts=1):
        row = read_retry(self.peers[rank] / f"{name}.json", attempts=attempts)
        if row is not None and any(row.get(k) != v for k, v in self.lease.items()):
            raise ValueError(f"Peer {rank} {name} belongs to a different attempt or READY")
        return row

    def check(self):
        active = read_retry(self.output / "CLUSTER.lock" / "OWNER.json")
        if active is not None and active != self.lease:
            raise RuntimeError("Active run lease changed; refusing concurrent attempts")
        if read_retry(self.root / "FORCED_RELEASE.json", attempts=1):
            raise RuntimeError("Operator released this attempt; stop before any further work")
        if self.heartbeat_error:
            raise RuntimeError("Own heartbeat write failed") from self.heartbeat_error
        if self.stop.is_set():
            raise RuntimeError("Stop requested; finish current requests before exit")
        hosts = {self.host}
        for rank in self.peers:
            failed = self.peer_record(rank, "FAILED")
            if failed:
                raise RuntimeError(f"Peer failed (node {rank}): {failed['value']}")
            owner = self.peer_record(rank, "OWNER")
            if owner:
                if owner["hostname"] in hosts:
                    raise ValueError("Two node ranks are on the same host")
                hosts.add(owner["hostname"])
            if self.peer_record(rank, "COMPLETE"):
                continue
            heartbeat = self.peer_record(rank, "heartbeat", attempts=5)
            clock = self.peer_clocks[rank]
            if clock.observe(heartbeat):
                raise RuntimeError(
                    f"Peer {rank} heartbeat stale; last successful sequence stopped advancing"
                )
            if clock.last_new is None and time.monotonic() - self.started > self.join_seconds:
                raise RuntimeError(f"Peer {rank} did not join before the startup deadline")

    def barrier(self, name, value=None):
        self.phase = f"barrier-{name}"
        self.marker(name, value)
        while True:
            self.check()
            peers = {r: self.peer_record(r, name) for r in self.peers}
            if all(row is not None for row in peers.values()):
                return {r: row["value"] for r, row in peers.items()}
            self.stop.wait(self.poll)

    def jobs(self, jobs, phase, *, graceful=True):
        """Supervise only our PIDs; a stop never signals unrelated processes."""
        self.phase = phase
        children, streams = [], []
        try:
            self.check()
            for command, environment, log in jobs:
                stream = Path(log).open("x")
                streams.append(stream)
                children.append(
                    subprocess.Popen(
                        command,
                        env=environment,
                        stdout=stream,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                )
            atomic(
                self.mine / "ACTIVE.json",
                {**self.lease, "phase": phase, "pids": [p.pid for p in children]},
            )
            while True:
                self.check()
                codes = [p.poll() for p in children]
                if any(c is not None and c != 0 for c in codes):
                    raise RuntimeError(f"{phase} child failed: {codes}; see {self.mine}")
                if all(c is not None for c in codes):
                    return
                self.stop.wait(self.poll)
        finally:
            for child in children:
                if child.poll() is None:
                    try:
                        if graceful:
                            child.send_signal(signal.SIGUSR1)
                        else:
                            os.killpg(child.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            for child in children:
                child.wait()
            for stream in streams:
                stream.close()
            atomic(self.mine / "ACTIVE.json", {**self.lease, "phase": phase, "pids": []})

    def close(self):
        self.closed.set()
        if self.thread:
            self.thread.join()
        for sig, previous in self.signals.items():
            signal.signal(sig, previous)
        if self.claimed:
            self.marker("RELEASED", {"pid": os.getpid(), "hostname": self.host})
