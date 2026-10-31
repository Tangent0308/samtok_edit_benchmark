"""One identical foreground ARNOLD command on all four eight-GPU workers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import signal
import sys
import time

from evaluation.protocol_audit.bootstrap_fairness_dev20 import checked, sha
from samtok_benchmark.paths import repository_root
from samtok_benchmark.ifbench.arnold import Cluster, Topology, child_environment, read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--attempt", default="run001")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--coordination-only", action="store_true")
    group.add_argument("--validate-only", action="store_true")
    group.add_argument("--status", action="store_true")
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    ready = read(bundle / "READY.json")
    repo = repository_root()
    if args.status:
        launches = {}
        for path in sorted((bundle / "launches").glob("*/nodes/*/heartbeat.json")):
            value = read(path)
            value["heartbeat_age_seconds"] = time.time() - value["time"]
            launches.setdefault(path.parents[2].name, {})[path.parent.name] = value
        for attempt in launches:
            root = bundle / "launches" / attempt
            launches[attempt]["failures"] = [read(p) for p in root.glob("nodes/*/FAILED.json")]
            launches[attempt]["success"] = (
                read(root / "SUCCESS.json") if (root / "SUCCESS.json").exists() else None
            )
        nodes = {}
        for node in range(4):
            directory = Path(ready["results_root"]) / "nodes" / f"node-{node}"
            nodes[str(node)] = {
                name: read(directory / name) if (directory / name).exists() else None
                for name in ("progress.json", "COMPLETED.json", "ERROR.json")
            }
        completed = Path(ready["results_root"]) / "report/COMPLETED.json"
        print(
            json.dumps(
                {
                    "launches": launches,
                    "formal_results": ready["results_root"],
                    "nodes": nodes,
                    "report": read(completed) if completed.exists() else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    for name, key in (
        ("plan.json", "plan_sha256"),
        ("code_manifest.json", "code_manifest_sha256"),
        ("aliases.json", "aliases_sha256"),
        ("bootstrap.json", "bootstrap_sha256"),
        ("start.sh", "entrypoint_sha256"),
    ):
        checked(bundle / name, ready[key])
    for name, expected in read(bundle / "code_manifest.json")["files"].items():
        checked(repo / name, expected)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", args.attempt):
        parser.error("Use a short, common attempt ID without path separators")
    topology = Topology.from_env()
    mode = (
        "coordination"
        if args.coordination_only
        else "validate"
        if args.validate_only
        else "evaluate"
    )
    plan = read(bundle / "plan.json")
    if plan.get("cluster_execution", {}).get("platform") != "arnold":
        raise ValueError(
            "Publish a new ARNOLD bundle; do not retrofit a frozen independent-node plan"
        )
    identity = {"ready_sha256": sha(bundle / "READY.json"), "attempt": args.attempt, "mode": mode}
    root = bundle / "launches" / args.attempt

    def terminate(signum, frame):
        raise KeyboardInterrupt(
            f"Signal {signum}; preserve admissions and stop only owned children"
        )

    signal.signal(signal.SIGTERM, terminate)
    with Cluster(root, topology, identity) as cluster:
        cluster.rendezvous()
        env = child_environment()
        env.update(
            IFBENCH_CLUSTER_DIRECTORY=str(root),
            IFBENCH_CLUSTER_IDENTITY=cluster.identity,
            IFBENCH_CLUSTER_NODE=str(topology.node),
            IFBENCH_CLUSTER_MANAGED="1",
            IFBENCH_FULL4_WORK=f"/tmp/ifbench/arnold-runtime/{ready['source_commit']}",
        )
        if not args.coordination_only:
            command = [
                sys.executable,
                str(repo / "src/evaluation/protocol_audit/bootstrap_full4.py"),
                "--bundle",
                str(bundle),
                "--node",
                str(topology.node),
            ]
            if args.validate_only:
                command.append("--validate-only")
            cluster.supervise(command, env, "runtime-preflight-and-" + mode)
        cluster.mark("WORK_DONE")
        cluster.wait_all("WORK_DONE")
        if mode == "evaluate":
            if topology.node == 0:
                runtime = read(root / "nodes/0/runtime.json")
                cluster.supervise(
                    [
                        runtime["generation_python"],
                        "-m",
                        "samtok_benchmark.ifbench.full_report",
                        "--bundle",
                        str(bundle),
                    ],
                    env,
                    "global-report",
                )
                report = Path(ready["results_root"]) / "report/COMPLETED.json"
                if not report.exists() or read(report)["plan_digest"] != plan["digest"]:
                    raise RuntimeError("Aggregation exited without a matching global completion")
            # Keep every worker alive until node 0 completes the verified report.
            cluster.mark("REPORT_ACK")
            cluster.wait_all("REPORT_ACK")
        cluster.finish(
            mode=mode,
            results_root=ready["results_root"],
            new_inference_calls=0 if mode != "evaluate" else None,
            calls_ledger=str(Path(ready["results_root"]) / "report/CALLS.json")
            if mode == "evaluate"
            else None,
        )


if __name__ == "__main__":
    main()
