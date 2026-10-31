"""Four ARNOLD controllers: TCP rendezvous, shared barriers and owned child cleanup.

This module uses only the standard library so coordination also covers runtime
installation. Model generation and each local TP8 Judge keep their native layout.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import socketserver
import subprocess
import threading
import time
import uuid


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def endpoint(value):
    match = re.fullmatch(r"(?:\[([^\]]+)\]|([^:\s]+)):(\d+)", value)
    if not match or not 1 <= int(match[3]) <= 65535:
        raise ValueError(f"Expected host:port or [IPv6]:port: {value!r}")
    return match[1] or match[2], int(match[3])


@dataclass(frozen=True)
class Topology:
    node: int
    hosts: tuple[str, ...]
    master_host: str
    master_port: int

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        required = ("ARNOLD_ID", "ARNOLD_WORKER_NUM", "ARNOLD_WORKER_GPU", "ARNOLD_WORKER_HOSTS")
        if any(not env.get(k) for k in required):
            raise ValueError(
                "Run the common entry on all four ARNOLD workers; missing ARNOLD variables"
            )
        if int(env["ARNOLD_WORKER_NUM"]) != 4 or int(env["ARNOLD_WORKER_GPU"]) != 8:
            raise ValueError("This frozen run requires exactly 4 workers x 8 GPUs")
        node = int(env["ARNOLD_ID"])
        hosts = tuple(env["ARNOLD_WORKER_HOSTS"].split(","))
        hosts = tuple(h.strip() for h in hosts)
        # ARNOLD may allocate multiple ports per worker (observed: 10 entries
        # for one worker). Endpoint-list length is not the machine count.
        if node not in range(4):
            raise ValueError("ARNOLD_ID must be 0..3")
        for host in hosts:
            endpoint(host)
        master, port = endpoint(hosts[0])
        # Generic PORT and inherited MASTER_PORT can differ between workers.
        return cls(node, hosts, master, port)


def child_environment(env=None):
    result = dict(os.environ if env is None else env)
    # Native pipelines/vLLM must not inherit a platform-wide torchrun rank.
    for key in (
        "PORT",
        "MASTER_ADDR",
        "MASTER_PORT",
        "RANK",
        "LOCAL_RANK",
        "WORLD_SIZE",
        "LOCAL_WORLD_SIZE",
        "GROUP_RANK",
        "ROLE_RANK",
        "ROLE_WORLD_SIZE",
        "NODE_RANK",
        "NNODES",
        "GPUS_PER_NODE",
    ):
        result.pop(key, None)
    result.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    return result


def check_peers(root, identity, stale_seconds=300):
    now = time.time()
    for node in range(4):
        directory = root / "nodes" / str(node)
        owner_path = directory / "OWNER.json"
        if not owner_path.exists():
            continue
        owner = read(owner_path)
        if owner.get("identity") != identity or owner.get("node") != node:
            raise RuntimeError(f"Worker {node} registered a different plan/code/topology/mode")
        failure = directory / "FAILED.json"
        if failure.exists():
            raise RuntimeError(f"Worker {node} failed: {read(failure).get('error')}; see {failure}")
        heartbeat = directory / "heartbeat.json"
        updated = read(heartbeat)["time"] if heartbeat.exists() else owner["time"]
        if now - updated > stale_seconds:
            raise RuntimeError(f"Worker {node} heartbeat missing for over {stale_seconds}s")


def generation_barrier():
    """Called after per-node input preflight, before any model admission."""
    directory = os.environ.get("IFBENCH_CLUSTER_DIRECTORY")
    if not directory:
        return
    root = Path(directory)
    identity = os.environ["IFBENCH_CLUSTER_IDENTITY"]
    node = int(os.environ["IFBENCH_CLUSTER_NODE"])
    save(root / "nodes" / str(node) / "INPUTS_READY.json", {"identity": identity, "node": node})
    deadline = time.monotonic() + 7200
    while True:
        check_peers(root, identity)
        paths = [root / "nodes" / str(n) / "INPUTS_READY.json" for n in range(4)]
        if all(p.exists() and read(p).get("identity") == identity for p in paths):
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("All four input preflights must complete before sampling")
        time.sleep(3)


class Cluster:
    """Persistent per-node supervisor. Claims are never automatically reused."""

    def __init__(
        self,
        root,
        topology,
        identity_fields,
        *,
        timeout=14 * 86400,
        startup_timeout=7200,
        poll=3,
        stale_seconds=300,
        hostname=None,
    ):
        self.root = Path(root)
        self.topology = topology
        # Only the first/common rendezvous endpoint coordinates the job. Do not
        # require unused platform port allocations to match on every worker.
        self.identity = fingerprint(
            {
                **identity_fields,
                "master_host": topology.master_host,
                "master_port": topology.master_port,
                "workers": 4,
                "gpus_per_worker": 8,
            }
        )
        self.node = topology.node
        self.directory = self.root / "nodes" / str(self.node)
        self.host = hostname or socket.gethostname()
        self.timeout, self.startup_timeout = timeout, startup_timeout
        self.poll, self.stale_seconds = poll, stale_seconds
        self.started = time.monotonic()
        self.stage = "registering"
        self.stop = threading.Event()
        self.heartbeat_error = None
        self.server = None
        self.thread = None

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        # Atomic and permanent: a scheduler retry needs a fresh attempt ID and review.
        (self.directory / "CLAIM").mkdir()
        save(
            self.directory / "OWNER.json",
            {
                "identity": self.identity,
                "node": self.node,
                "host": self.host,
                "pid": os.getpid(),
                "time": time.time(),
                "topology": asdict(self.topology),
            },
        )
        self.beat()
        self.thread = threading.Thread(target=self.heartbeat, daemon=True)
        self.thread.start()
        return self

    def beat(self):
        value = {
            "identity": self.identity,
            "node": self.node,
            "host": self.host,
            "stage": self.stage,
            "time": time.time(),
        }
        save(self.directory / "heartbeat.json", value)

    def heartbeat(self):
        while not self.stop.wait(min(15, self.stale_seconds / 4)):
            try:
                self.beat()
                print(
                    json.dumps(
                        {"cluster_node": self.node, "stage": self.stage, "heartbeat": time.time()}
                    ),
                    flush=True,
                )
            except BaseException as error:
                self.heartbeat_error = repr(error)
                return

    def check(self):
        if self.heartbeat_error:
            raise RuntimeError(f"Cannot persist cluster heartbeat: {self.heartbeat_error}")
        if time.monotonic() - self.started > self.timeout:
            raise TimeoutError("Cluster exceeded its bounded execution time")
        check_peers(self.root, self.identity, self.stale_seconds)

    def mark(self, name, **extra):
        save(
            self.directory / (name + ".json"),
            {
                "identity": self.identity,
                "node": self.node,
                "time": time.time(),
                **extra,
            },
        )

    def wait_all(self, name, timeout=None):
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        self.stage = "waiting-" + name.lower()
        while True:
            self.check()
            paths = [self.root / "nodes" / str(n) / (name + ".json") for n in range(4)]
            if all(p.exists() and read(p).get("identity") == self.identity for p in paths):
                return
            if time.monotonic() > deadline:
                raise TimeoutError(f"Four-worker barrier timed out: {name}")
            time.sleep(self.poll)

    def rendezvous(self):
        """Probe real worker-to-worker TCP, including IPv6, before runtime setup."""
        self.stage = "tcp-rendezvous"
        if self.node == 0:
            cluster = self

            class Handler(socketserver.StreamRequestHandler):
                def handle(self):
                    self.request.settimeout(10)
                    request = json.loads(self.rfile.readline(4096))
                    node = request.get("node")
                    valid = (
                        request.get("identity") == cluster.identity
                        and type(node) is int
                        and node in range(4)
                    )
                    self.wfile.write(
                        json.dumps({"accepted": valid, "identity": cluster.identity}).encode()
                        + b"\n"
                    )

            family = socket.getaddrinfo(
                self.topology.master_host, self.topology.master_port, type=socket.SOCK_STREAM
            )[0][0]

            class Server(socketserver.ThreadingTCPServer):
                address_family = family
                allow_reuse_address = True
                daemon_threads = True

            # The advertised host may be routed/NAT, not assigned to a local NIC.
            bind_host = "::" if family == socket.AF_INET6 else "0.0.0.0"
            self.server = Server((bind_host, self.topology.master_port), Handler)
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
        deadline = time.monotonic() + self.startup_timeout
        while True:
            self.check()
            try:
                with socket.create_connection(
                    (self.topology.master_host, self.topology.master_port), timeout=5
                ) as connection:
                    connection.sendall(
                        json.dumps({"identity": self.identity, "node": self.node}).encode() + b"\n"
                    )
                    reply = json.loads(connection.makefile("rb").readline(4096))
                    if reply != {"accepted": True, "identity": self.identity}:
                        raise RuntimeError("Rendezvous answered for a different run/code/topology")
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise TimeoutError("Cannot reach ARNOLD master endpoint") from None
                time.sleep(self.poll)
        self.mark("CONNECTED")
        self.wait_all("CONNECTED", self.startup_timeout)
        owners = [read(self.root / "nodes" / str(n) / "OWNER.json") for n in range(4)]
        if len({o["host"] for o in owners}) != 4:
            raise RuntimeError("The four ranks must run on four distinct worker hosts")

    def supervise(self, command, env, stage):
        self.stage = stage
        self.check()
        child = subprocess.Popen(command, env=env, start_new_session=True)
        self.mark("CHILD", command=list(map(str, command)), pid=child.pid, stage=stage)
        try:
            while child.poll() is None:
                self.check()
                time.sleep(self.poll)
            if child.wait() != 0:
                raise RuntimeError(
                    f"{stage} exited with status {child.returncode}; no automatic retry"
                )
            self.check()
        except BaseException as error:
            # Notify peers before potentially waiting for native child cleanup.
            self.mark("FAILED", error=repr(error))
            raise
        finally:
            if child.poll() is None:
                # The native controller handles TERM and joins its own worker groups.
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()

    def finish(self, **result):
        self.mark("EXIT_READY", controller_wall_seconds=time.monotonic() - self.started, **result)
        self.wait_all("EXIT_READY")
        if self.node == 0:
            save(
                self.root / "SUCCESS.json",
                {
                    "identity": self.identity,
                    "time": time.time(),
                    "workers": 4,
                    **result,
                },
            )
        while not (self.root / "SUCCESS.json").exists():
            self.check()
            time.sleep(self.poll)
        if read(self.root / "SUCCESS.json")["identity"] != self.identity:
            raise RuntimeError("Global completion belongs to another run")
        self.stage = "completed"
        self.beat()

    def __exit__(self, kind, error, traceback):
        try:
            if error is not None:
                self.stage = "failed"
                self.mark("FAILED", error=repr(error))
        finally:
            self.stop.set()
            if self.thread is not None:
                self.thread.join(timeout=20)
            if self.server is not None:
                self.server.shutdown()
                self.server.server_close()
