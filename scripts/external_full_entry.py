#!/usr/bin/env python3
"""Foreground 4 x 8 ARNOLD entry; immutable NAS inputs, local runtimes, no network rendezvous."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tarfile
import threading
import time


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def topology():
    if os.environ.get("ARNOLD_WORKER_NUM") != "4" or os.environ.get("ARNOLD_WORKER_GPU") != "8":
        raise ValueError("Exactly four ARNOLD workers, eight GPUs each, are required")
    rank = os.environ.get("ARNOLD_ID")
    if rank not in ("0", "1", "2", "3"):
        raise ValueError("ARNOLD_ID must be 0..3")
    return int(rank)


def partition(index, rank, helper):
    sequences = sorted({x["sequence_id"] for x in index["cases"]})
    counts = Counter(x["sequence_id"] for x in index["cases"])
    owned = set(helper.partition_sessions(sequences, counts, rank))
    return [x["case_id"] for x in index["cases"] if x["sequence_id"] in owned]


def main(package, attempt, validate_only=False):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", attempt):
        raise ValueError("Invalid attempt")
    package = Path(package).resolve()
    ready = read(package / "READY.json")
    rank = topology()
    for name, key in [
        ("entry.py", "entry_sha256"),
        ("coordination.py", "coordination_sha256"),
        ("start.sh", "start_sha256"),
    ]:
        if sha(package / name) != ready[key]:
            raise ValueError(f"Published {name} changed")
    for path, expected in ready["control_files"].items():
        if sha(path) != expected:
            raise ValueError(f"Published configuration/runtime descriptor changed: {path}")
    spec = importlib.util.spec_from_file_location(
        "external_nas_coordination", package / "coordination.py"
    )
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    coord = helper.Coordinator(ready["results_root"], attempt, rank, sha(package / "READY.json"))
    children, lock = {}, threading.Lock()
    coord.enter()
    logs = coord.mine
    print(f"[{ready['benchmark']}] node {rank}/4, attempt {attempt}; logs: {logs}", flush=True)

    def call(name, command, environment=None):
        coord.check()
        log = logs / (name + ".log")
        print(f"node {rank}: {name}; {log}", flush=True)
        tick = time.monotonic()
        with log.open("x") as stream:
            child = subprocess.Popen(
                command,
                env=environment,
                cwd=repo,
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            with lock:
                children[name] = child
            helper.atomic(logs / (name + ".pid.json"), {"pid": child.pid, "command": command})
            try:
                while child.poll() is None:
                    coord.check()
                    time.sleep(3)
                if child.returncode:
                    raise RuntimeError(f"{name} exited {child.returncode}; inspect {log}")
            finally:
                if child.poll() is None:
                    if name == "generation" or name.startswith(("metrics-", "vlm-")):
                        child.send_signal(signal.SIGUSR1)
                    else:
                        os.killpg(child.pid, signal.SIGTERM)
                    child.wait()
                with lock:
                    children.pop(name, None)
                helper.atomic(
                    logs / (name + ".exit.json"),
                    {"returncode": child.returncode, "seconds": time.monotonic() - tick},
                )

    try:
        cfg = read(ready["configuration"])
        key_file = os.environ.get(
            "COMPBENCH_API_KEY_FILE",
            os.environ.get(
                "EXTERNAL_API_KEY_FILE",
                "/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/secrets/gpt54.key",
            ),
        )
        if ready["benchmark"] == "compbench" and not Path(key_file).is_file():
            raise RuntimeError("Missing authorized GPT-5.4 key file; no model started")
        index = read(Path(ready["bundle"]) / "index.json")
        ids = partition(index, rank, helper)
        local_attempt = attempt + f"-node{rank}"
        runtime = (
            Path("/tmp/ifbench/external-full4")
            / ready["benchmark"]
            / ready["source_commit"][:12]
            / local_attempt
        )
        runtime.mkdir(parents=True, exist_ok=False)
        repo = runtime / "repo"
        repo.mkdir()
        coord.phase = "staging-code"
        if sha(ready["code"]["archive"]) != ready["code"]["sha256"]:
            raise ValueError("Source archive changed")
        with tarfile.open(ready["code"]["archive"]) as archive:
            for member in archive:
                path = Path(member.name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or not (member.isfile() or member.isdir())
                ):
                    raise ValueError("Unsafe published code archive")
                archive.extract(member, repo)
        spec = importlib.util.spec_from_file_location(
            "full_input_policy", repo / "src/samtok_benchmark/external_full/input_policy.py"
        )
        policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(policy)
        generation_ids = policy.runnable_ids(index, ids, cfg)
        env = helper.local_environment(rank)
        env["CUDA_VISIBLE_DEVICES"] = ""
        coord.phase = "staging-runtimes"
        call(
            "stage-sources",
            [
                "/usr/bin/python3",
                "-I",
                "scripts/refedit_stage.py",
                "sources",
                "--destination",
                str(runtime / "sources"),
            ],
            env,
        )
        call(
            "stage-generation",
            [
                "/usr/bin/python3",
                "-I",
                "scripts/refedit_stage.py",
                "generation",
                "--work",
                str(runtime),
            ],
            env,
        )
        for name in ("pass1", "v4"):
            descriptor = ready["runtimes"][name]
            call(
                "stage-" + name,
                [
                    "/usr/bin/python3",
                    "-I",
                    "scripts/refedit_runtime.py",
                    "unpack",
                    "--descriptor",
                    descriptor["path"],
                    "--descriptor-sha256",
                    descriptor["sha256"],
                    "--destination",
                    str(runtime / ("env_" + name)),
                    "--method-source",
                    cfg["paths"]["sitedit_source"],
                ],
                env,
            )
        descriptor = ready["runtimes"]["metrics"]
        call(
            "stage-metrics",
            [
                "/usr/bin/python3",
                "-I",
                "scripts/compbench_runtime.py",
                "unpack",
                "--descriptor",
                descriptor["path"],
                "--expected-sha",
                descriptor["sha256"],
                "--destination",
                str(runtime / "env_metrics"),
                "--interpreter",
                str(runtime / "generation/cpython/bin/python3.11"),
            ],
            env,
        )
        cfg["paths"]["sources"] = str(runtime / "sources")
        cfg["runtime"] = {
            "generation": str(runtime / "generation/env/bin/python"),
            **{
                name: str(runtime / ("env_" + name) / "bin/python")
                for name in ("pass1", "v4", "metrics")
            },
        }
        config_path = runtime / "configuration.json"
        config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
        common = [
            cfg["runtime"]["metrics"],
            "-I",
            "scripts/external_full_preflight.py",
            "--config",
            str(config_path),
            "--bundle",
            ready["bundle"],
            "--case-ids",
            *ids,
            "--output",
            str(logs / "PREFLIGHT.json"),
        ]
        call("preflight", common, env)
        peers = coord.barrier(
            "PREPARED",
            {"case_ids": ids, "plan_digest": ready["plan_digest"], "validate_only": validate_only},
        )
        all_values = [
            *peers.values(),
            {"case_ids": ids, "plan_digest": ready["plan_digest"], "validate_only": validate_only},
        ]
        flat = [cid for row in all_values for cid in row["case_ids"]]
        if (
            len(flat) != len(set(flat))
            or set(flat) != {x["case_id"] for x in index["cases"]}
            or any(
                x["plan_digest"] != ready["plan_digest"] or x["validate_only"] != validate_only
                for x in all_values
            )
        ):
            raise ValueError("Four-node ownership/mode mismatch")
        if validate_only:
            coord.barrier("VALIDATED")
            coord.marker("COMPLETE", {"validate_only": True})
            return
        run = Path(ready["results_root"]) / "run"
        scores = Path(ready["results_root"]) / "scores"
        env.update(
            HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TORCH_HOME=cfg["scoring"]["torch_home"]
        )
        coord.phase = "generation-and-scoring"

        def generate():
            call(
                "generation",
                [
                    cfg["runtime"]["generation"],
                    "-I",
                    "scripts/external_full.py",
                    "run",
                    "--config",
                    str(config_path),
                    "--bundle",
                    ready["bundle"],
                    "--output",
                    str(run),
                    "--attempt",
                    local_attempt,
                    "--remote",
                    "--gpus",
                    *map(str, range(8)),
                    "--models",
                    *ready["models"],
                    "--case-ids",
                    *generation_ids,
                ],
                env,
            )

        with ThreadPoolExecutor(max_workers=1) as generation_pool:
            generation = generation_pool.submit(generate)
            try:
                for model in ready["models"]:
                    markers = [
                        run / "attempts" / local_attempt / f"gpu{g}-{model}.terminal.json"
                        for g in range(8)
                    ]
                    while not all(helper.read_retry(p, attempts=1) is not None for p in markers):
                        coord.check()
                        if generation.done():
                            generation.result()
                            raise RuntimeError(f"Missing local completion marker for {model}")
                        time.sleep(3)

                    def metrics(shard):
                        call(
                            f"metrics-{model}-{shard}",
                            [
                                cfg["runtime"]["metrics"],
                                "-I",
                                "scripts/external_full.py",
                                "score",
                                "--config",
                                str(config_path),
                                "--bundle",
                                ready["bundle"],
                                "--run",
                                str(run),
                                "--output",
                                str(scores),
                                "--models",
                                model,
                                "--shard",
                                str(shard),
                                "--shards",
                                "4",
                                "--case-ids",
                                *ids,
                            ],
                            env,
                        )

                    def vlm():
                        if ready["benchmark"] == "compbench":
                            call(
                                "vlm-" + model,
                                [
                                    cfg["runtime"]["metrics"],
                                    "-I",
                                    "scripts/external_full.py",
                                    "judge",
                                    "--config",
                                    str(config_path),
                                    "--bundle",
                                    ready["bundle"],
                                    "--run",
                                    str(run),
                                    "--output",
                                    str(scores),
                                    "--models",
                                    model,
                                    "--key-file",
                                    key_file,
                                    "--workers",
                                    "1",
                                    "--case-ids",
                                    *ids,
                                ],
                                env,
                            )

                    with ThreadPoolExecutor(max_workers=5) as pool:
                        futures = [pool.submit(metrics, s) for s in range(4)] + [pool.submit(vlm)]
                        for future in futures:
                            future.result()
                generation.result()
            except BaseException:
                coord.stop.set()
                raise
        coord.barrier("EVALUATED", {"case_ids": ids})
        if rank == 0:
            coord.phase = "global-report"
            call(
                "report",
                [
                    cfg["runtime"]["metrics"],
                    "-I",
                    "scripts/external_full.py",
                    "report",
                    "--bundle",
                    ready["bundle"],
                    "--run",
                    str(run),
                    "--scores",
                    str(scores),
                    "--output",
                    str(Path(ready["results_root"]) / "reports" / attempt),
                    "--models",
                    *ready["models"],
                ],
                env,
            )
        coord.barrier("REPORT_WRITTEN")
        coord.marker(
            "COMPLETE",
            {"report": str(Path(ready["results_root"]) / "reports" / attempt / "REPORT.json")},
        )
        print(f"Completed {ready['benchmark']}, node {rank}", flush=True)
    except BaseException as error:
        coord.stop.set()
        coord.marker("FAILED", {"error": repr(error)})
        raise
    finally:
        coord.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--validate-only", action="store_true")
    main(**vars(parser.parse_args()))
