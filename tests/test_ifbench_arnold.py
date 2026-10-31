"""CPU-only checks for the common ARNOLD entry; no model sampling or fake scores."""

from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest

from samtok_benchmark.ifbench.arnold import (
    Cluster,
    Topology,
    check_peers,
    child_environment,
    endpoint,
    fingerprint,
    generation_barrier,
    read,
    save,
)


def environment(node=0, hosts=None):
    return {
        "ARNOLD_ID": str(node),
        "ARNOLD_WORKER_NUM": "4",
        "ARNOLD_WORKER_GPU": "8",
        "ARNOLD_WORKER_HOSTS": hosts or "worker0:12000,worker1:12001,worker2:12002,worker3:12003",
        "PORT": "9999",
        "MASTER_PORT": "9998",
        "RANK": "17",
        "WORLD_SIZE": "32",
    }


def test_platform_identity_common_port_and_ipv6():
    hosts = ",".join(f"[fd00::{i + 1}]:{12000 + i}" for i in range(4))
    for i in range(4):
        topo = Topology.from_env(environment(i, hosts))
        assert (topo.node, topo.master_host, topo.master_port) == (i, "fd00::1", 12000)
    assert endpoint("worker0:1234") == ("worker0", 1234)
    with pytest.raises(ValueError):
        endpoint("fd00::1:1234")


@pytest.mark.parametrize(
    "field,value",
    [
        ("ARNOLD_ID", "4"),
        ("ARNOLD_WORKER_NUM", "8"),
        ("ARNOLD_WORKER_GPU", "4"),
        ("ARNOLD_WORKER_HOSTS", "same:12,same:12,same:12,same:12"),
        ("ARNOLD_ID", ""),
    ],
)
def test_invalid_platform_topology_is_rejected(field, value):
    with pytest.raises(ValueError):
        Topology.from_env({**environment(), field: value})


def test_native_workers_do_not_inherit_cluster_torchrun_environment():
    env = environment()
    isolated = child_environment({**env, "CUDA_VISIBLE_DEVICES": "0,1,2,3,4,5,6,7"})
    assert "RANK" not in isolated and "WORLD_SIZE" not in isolated and "MASTER_PORT" not in isolated
    assert isolated["ARNOLD_ID"] == "0" and isolated["CUDA_VISIBLE_DEVICES"] == "0,1,2,3,4,5,6,7"
    assert env["RANK"] == "17"


def free_port(address="127.0.0.1"):
    with socket.socket(socket.AF_INET6 if ":" in address else socket.AF_INET) as sock:
        sock.bind((address, 0))
        return sock.getsockname()[1]


def four_process_worker(root, node, port, fail=False, address="127.0.0.1"):
    host = f"[{address}]" if ":" in address else address
    hosts = tuple(f"{host}:{port + n}" for n in range(4))
    topo = Topology(node, hosts, address, port)
    try:
        with Cluster(
            root,
            topo,
            {"test": "CPU-only"},
            poll=0.02,
            startup_timeout=10,
            timeout=20,
            stale_seconds=10,
            hostname=f"synthetic-host-{node}",
        ) as c:
            c.rendezvous()
            if fail and node == 2:
                raise RuntimeError("injected infrastructure failure, no GPU calls")
            os.environ.update(
                IFBENCH_CLUSTER_DIRECTORY=str(root),
                IFBENCH_CLUSTER_IDENTITY=c.identity,
                IFBENCH_CLUSTER_NODE=str(node),
            )
            generation_barrier()
            c.mark("WORK_DONE")
            c.wait_all("WORK_DONE", 10)
            if node == 0:
                # Simulate CPU report latency: peers must remain alive for this ack.
                time.sleep(0.15)
                save(Path(root) / "report_evidence.json", {"writer": 0, "scores": "not produced"})
            c.mark("REPORT_ACK")
            c.wait_all("REPORT_ACK", 10)
            c.finish(new_inference_calls=0)
    except BaseException:
        if not fail:
            raise


@pytest.mark.parametrize(
    "fail,address", [(False, "127.0.0.1"), (True, "127.0.0.1"), (False, "::1")]
)
def test_real_tcp_four_process_barriers_and_failure_propagation(tmp_path, fail, address):
    ctx = multiprocessing.get_context("spawn")
    try:
        port = free_port(address)
    except OSError:
        if address == "::1":
            pytest.skip("Host has no IPv6 loopback")
        raise
    processes = [
        ctx.Process(target=four_process_worker, args=(str(tmp_path), n, port, fail, address))
        for n in range(4)
    ]
    for p in processes:
        p.start()
    try:
        for p in processes:
            p.join(25)
        assert all(not p.is_alive() and p.exitcode == 0 for p in processes)
        if fail:
            assert not (tmp_path / "SUCCESS.json").exists()
            assert len(list(tmp_path.glob("nodes/*/FAILED.json"))) == 4
        else:
            assert read(tmp_path / "SUCCESS.json")["new_inference_calls"] == 0
            assert read(tmp_path / "report_evidence.json")["writer"] == 0
            assert len(list(tmp_path.glob("nodes/*/EXIT_READY.json"))) == 4
    finally:
        for p in processes:
            if p.is_alive():
                p.terminate()
                p.join()


def test_reused_attempt_and_foreign_plan_are_rejected(tmp_path):
    topo = Topology.from_env(environment())
    with Cluster(tmp_path, topo, {"plan": "one"}) as first:
        with pytest.raises(FileExistsError):
            with Cluster(tmp_path, topo, {"plan": "one"}):
                pass
        with pytest.raises(RuntimeError, match="different plan"):
            check_peers(tmp_path, fingerprint({"plan": "two"}))
        assert read(first.directory / "OWNER.json")["identity"] == first.identity


def test_stale_worker_is_detected(tmp_path):
    topo = Topology.from_env(environment())
    with Cluster(tmp_path, topo, {"test": "stale"}) as cluster:
        save(cluster.directory / "heartbeat.json", {"time": time.time() - 100})
        with pytest.raises(RuntimeError, match="heartbeat"):
            check_peers(tmp_path, cluster.identity, stale_seconds=10)


def test_peer_failure_stops_only_owned_child(tmp_path):
    topo = Topology.from_env(environment())
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
    try:
        with Cluster(tmp_path, topo, {"test": "child"}, poll=0.02) as cluster:

            def fail_peer():
                time.sleep(0.15)
                directory = tmp_path / "nodes/2"
                save(
                    directory / "OWNER.json",
                    {"identity": cluster.identity, "node": 2, "time": time.time()},
                )
                save(directory / "FAILED.json", {"error": "test failure"})

            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(fail_peer)
                with pytest.raises(RuntimeError, match="Worker 2 failed"):
                    cluster.supervise(
                        [sys.executable, "-c", "import time; time.sleep(20)"],
                        dict(os.environ),
                        "synthetic-child",
                    )
                future.result()
            child = read(cluster.directory / "CHILD.json")["pid"]
            with pytest.raises(ProcessLookupError):
                os.kill(child, 0)
            assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait()


def test_upstream_source_materialization_and_shared_code_refusal(tmp_path):
    from evaluation.protocol_audit.bootstrap_full4 import local_source_alias
    import hashlib

    target = tmp_path / "shared/source"
    target.mkdir(parents=True)
    (target / "native.py").write_text("# audited native source\n")
    sha = hashlib.sha256((target / "native.py").read_bytes()).hexdigest()
    item = {
        "alias": str(tmp_path / "local/source"),
        "target": str(target),
        "files": {"native.py": sha},
    }
    assert local_source_alias(item)["status"] == "copied-node-local"
    assert not Path(item["alias"]).is_symlink()
    assert local_source_alias(item)["status"] == "verified-node-local"
    (Path(item["alias"]) / "native.py").write_text("changed")
    with pytest.raises(RuntimeError, match="changed file"):
        local_source_alias(item)
