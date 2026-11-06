#!/usr/bin/env python3
"""Foreground four-worker MagicBrush entry; model/scorer source is unchanged."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
if not sys.flags.isolated:
    raise SystemExit("Use python -I")
sys.path.insert(0, str(REPO / "src"))

from samtok_benchmark.external_magicbrush import MODELS  # noqa: E402
from samtok_benchmark.external_magicbrush.cluster import (  # noqa: E402
    Coordinator,
    WORKERS,
    GPUS_PER_WORKER,
    RANKS,
    local_environment,
    read_retry,
    release_stopped,
    validate_topology,
)


def scientific_step(args):
    from samtok_benchmark.external_magicbrush.bundle import load_bundle
    from samtok_benchmark.external_magicbrush.data import read
    from samtok_benchmark.external_magicbrush.launch import initialize_run, launch, run_plan
    from samtok_benchmark.external_magicbrush.worker import gpu_gate, verify_config
    from samtok_benchmark.io import digest

    ready = read(Path(args.package) / "READY.json")
    config_path = Path(args.runtime) / "magicbrush.json"
    config = read(config_path)
    verify_config(config)
    if args.command == "preflight":
        gpu_gate(config, list(range(8)))
        index = load_bundle(ready["bundle"])
        if index["digest"] != ready["bundle_digest"]:
            raise ValueError("Bundle changed")
        return {"config_digest": digest(config), "bundle_digest": index["digest"]}
    output = Path(ready["results_root"])
    if args.command == "initialize":
        index = load_bundle(ready["bundle"])
        initialize_run(run_plan(ready["bundle"], index, config, output, MODELS), config, output)
        return {"initialized": True}
    return launch(
        SimpleNamespace(
            config=str(config_path),
            bundle=ready["bundle"],
            output=str(output),
            models=list(MODELS),
            gpus="0,1,2,3,4,5,6,7",
            smoke=False,
            attempt=args.attempt,
            cache_dir=str(Path(args.runtime) / "cache"),
            estimate=ready["estimate"],
        ),
        node_rank=args.rank,
    )


def control(args):
    rank = validate_topology()
    ready_path = Path(args.package) / "READY.json"
    raw = ready_path.read_bytes()
    ready, ready_sha = json.loads(raw), hashlib.sha256(raw).hexdigest()
    if ready["topology"] != {"workers": WORKERS, "gpus_per_worker": GPUS_PER_WORKER}:
        raise ValueError("READY does not describe the four-node deployment")
    coordinator = Coordinator(ready["results_root"], args.attempt, rank, ready_sha)
    entered = False
    try:
        coordinator.enter()
        entered = True
        environment = local_environment(rank)
        environment["CUDA_VISIBLE_DEVICES"] = ""
        rt = Path(args.runtime)
        python = str(rt / "env_v4/bin/python")
        base = [python, "-I", "-B", str(REPO / "scripts/magicbrush_cluster.py")]
        options = [
            "--package",
            args.package,
            "--runtime",
            args.runtime,
            "--attempt",
            args.attempt,
            "--rank",
            str(rank),
        ]

        def job(command, name, env=None, graceful=False):
            print(f"node {rank}: {name}", flush=True)
            coordinator.jobs(
                [(command, env or environment, coordinator.mine / f"{name}.log")],
                name,
                graceful=graceful,
            )

        peer_mode = coordinator.barrier("JOINED", {"validate_only": args.validate_only})
        if any(value != {"validate_only": args.validate_only} for value in peer_mode.values()):
            raise ValueError("All four nodes must use the same validation mode")
        job(
            [
                "/usr/bin/python3",
                "-I",
                str(REPO / "scripts/magicbrush_publish.py"),
                "verify",
                "--package",
                args.package,
                "--commit",
                ready["source_commit"],
            ],
            "verify",
        )
        job(["bash", str(REPO / "scripts/arnold/magicbrush_stage.sh")], "stage")
        job(base + ["preflight"] + options, "preflight")
        proof = read_retry(coordinator.mine / "preflight.log")
        if proof is None:
            raise ValueError("Missing preflight proof")
        if any(value != proof for value in coordinator.barrier("STAGED", proof).values()):
            raise ValueError("Node runtime configuration or bundle differs")
        if not args.validate_only:
            if rank == 0:
                job(base + ["initialize"] + options, "initialize")
            coordinator.barrier("INITIALIZED")
            job(base + ["generate"] + options, "generation", graceful=True)
            coordinator.barrier("GENERATED")
            jobs = []
            for card in range(8):
                shard = rank * 8 + card
                command = [
                    python,
                    "-I",
                    "-B",
                    str(REPO / "scripts/magicbrush.py"),
                    "score",
                    "--output",
                    ready["results_root"],
                    "--config",
                    str(rt / "magicbrush.json"),
                    "--cache",
                    str(rt / "metric_cache"),
                    "--device",
                    "cuda",
                    "--shard",
                    str(shard),
                    "--shards",
                    str(WORKERS * GPUS_PER_WORKER),
                ]
                jobs.append(
                    (
                        command,
                        dict(environment, CUDA_VISIBLE_DEVICES=str(card)),
                        coordinator.mine / f"score-{shard}.log",
                    )
                )
            print(f"node {rank}: eight standard-metric workers", flush=True)
            coordinator.jobs(jobs, "scoring")
            coordinator.barrier("SCORED")
            if rank == 0:
                job(
                    [
                        python,
                        "-I",
                        "-B",
                        str(REPO / "scripts/magicbrush.py"),
                        "report",
                        "--output",
                        ready["results_root"],
                        "--overlap",
                        ready["overlap"],
                        "--destination",
                        str(Path(ready["results_root"]) / "report"),
                    ],
                    "report",
                )
                job(
                    [
                        python,
                        "-I",
                        "-B",
                        str(REPO / "scripts/magicbrush.py"),
                        "preview",
                        "--output",
                        ready["results_root"],
                        "--destination",
                        str(Path(ready["results_root"]) / "report/previews"),
                    ],
                    "preview",
                )
            coordinator.barrier("REPORTED")
        coordinator.barrier("COMPLETE", {"validate_only": args.validate_only})
        return {"completed": True, "node": rank, "validate_only": args.validate_only}
    except BaseException as error:
        if entered:
            coordinator.marker("FAILED", {"error": repr(error)})
        raise
    finally:
        coordinator.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["control", "preflight", "initialize", "generate", "release"]
    )
    parser.add_argument("--package", required=True)
    parser.add_argument("--runtime", default="/tmp/ifbench-magicbrush-runtime-aa5a414")
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--rank", type=int, choices=RANKS)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--confirm-all-workers-stopped", action="store_true")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()
    if args.command == "release":
        ready = json.loads((Path(args.package) / "READY.json").read_text())
        result = release_stopped(
            ready["results_root"], args.attempt, args.reason, args.confirm_all_workers_stopped
        )
    else:
        result = control(args) if args.command == "control" else scientific_step(args)
    print(json.dumps(result, indent=2), flush=True)
    return (
        2 if any(result.get(k) for k in ["stopped", "failed_processes", "remaining_tasks"]) else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
