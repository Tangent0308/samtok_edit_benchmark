"""Foreground single-node TP8 bootstrap from a verified shared NAS snapshot."""

from concurrent.futures import ThreadPoolExecutor
import fcntl
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time

from .bundle import copy_checked, load
from .common import checked, read, relative_path, save, sha


def free_port():
    for port in range(42300, 49000, 31):
        with socket.socket() as sock, socket.socket() as peer:
            try:
                sock.bind(("127.0.0.1", port))
                peer.bind(("127.0.0.1", port + 1))
            except OSError:
                continue
            return port
    raise RuntimeError("No free port in authorized 39xxx–49xxx range")


def stage_model(config, work):
    """Copy each immutable shard once to local storage; never load 185 GB via NAS mmap."""
    source = Path(config["model"])
    destination = work / "models" / source.name
    destination.mkdir(parents=True, exist_ok=True)
    names = set(config["model_config_sha256"]) | set(config["weight_bytes"])

    def one(name):
        src, dst = source / name, destination / name
        receipt = destination / ".receipts" / f"{name}.json"
        if receipt.exists():
            item = read(receipt)
            if item["source"] != str(src) or item["size"] != dst.stat().st_size:
                raise ValueError(f"Cached model shard differs: {dst}")
            checked(dst, item["sha256"])
            return item
        if dst.exists():
            raise ValueError(f"Unverified existing model file; inspect before retrying: {dst}")
        temp = dst.with_suffix(dst.suffix + ".copying")
        shutil.copyfile(src, temp)
        value = sha(temp)
        if name in config["model_config_sha256"] and value != config["model_config_sha256"][name]:
            raise ValueError(f"Model configuration changed: {src}")
        if name in config["weight_bytes"] and temp.stat().st_size != config["weight_bytes"][name]:
            raise ValueError(f"Model weight size changed: {src}")
        temp.replace(dst)
        item = {"source": str(src), "size": dst.stat().st_size, "sha256": value}
        save(receipt, item, immutable=True)
        return item

    print(f"Staging {len(names)} model files to {destination}; no model downloads.", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        manifest = dict(zip(sorted(names), pool.map(one, sorted(names))))
    save(
        destination / "STAGED.json",
        {"revision": config["revision"], "files": manifest},
        immutable=True,
    )
    return destination


def launch(bundle, attempt, work, validate_only=False):
    from evaluation.protocol_audit.bootstrap_fairness_dev20 import check_gpus, prepare_runtime

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", attempt):
        raise ValueError("Use a short alphanumeric attempt ID")
    bundle, work = Path(bundle).resolve(), Path(work).resolve()
    ready = read(bundle / "READY.json")
    for name, value in ready["files"].items():
        checked(relative_path(bundle, name), value)
    plan = load(bundle)
    if ready["plan_digest"] != plan["digest"] or ready["results_root"] != plan["results_root"]:
        raise ValueError("READY/plan mismatch")
    results = Path(plan["results_root"])
    operational = bundle.parent / (bundle.name + "-launches") / attempt
    operational.mkdir(parents=True, exist_ok=False)
    print(f"Launch log: {operational / 'run.log'}", flush=True)
    work.mkdir(parents=True, exist_ok=True)
    lock = (work / "launch.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    started = time.time()
    # Limit CPU preflight environment; no unrelated site-packages or distributed job variables.
    for key in (
        "PYTHONHOME",
        "PYTHONPATH",
        "CPATH",
        "CPLUS_INCLUDE_PATH",
        "LIBRARY_PATH",
        "LD_LIBRARY_PATH",
        "RANK",
        "WORLD_SIZE",
        "LOCAL_RANK",
        "LOCAL_WORLD_SIZE",
        "GROUP_RANK",
        "ROLE_RANK",
        "ROLE_WORLD_SIZE",
        "MASTER_ADDR",
        "MASTER_PORT",
    ):
        os.environ.pop(key, None)
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0,1,2,3,4,5,6,7")
    os.environ.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        VLLM_USAGE_STATS_ENABLED="0",
        VLLM_WORKER_MULTIPROC_METHOD="spawn",
        OMP_NUM_THREADS="4",
        TOKENIZERS_PARALLELISM="false",
    )
    gpus = check_gpus(min_free_gib=70, required=8)
    save(
        operational / "STARTED.json",
        {
            "started_at": started,
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "gpus": gpus,
            "ready_sha256": sha(bundle / "READY.json"),
        },
        immutable=True,
    )
    local_repo = work / "repo" / ready["source_commit"]
    for name, value in ready["files"].items():
        if name.startswith("repo/"):
            copy_checked(bundle / name, local_repo / name[5:], value)
    python, env, proof = prepare_runtime("judge", plan["runtime"], work / "runtime", local_repo)
    model = stage_model(plan["configuration"], work)
    env.update(
        CUDA_VISIBLE_DEVICES=os.environ["CUDA_VISIBLE_DEVICES"],
        MASTER_ADDR="127.0.0.1",
        MASTER_PORT=str(free_port()),
    )
    env["VLLM_PORT"] = str(int(env["MASTER_PORT"]) + 1)
    # All formal runs have the same TP8/batch16 configuration. No configurable scoring flags.
    script = local_repo / "scripts/compbench_supplementary_judge.py"
    save(
        operational / "PREFLIGHT.json",
        {
            "runtime": proof,
            "model": str(model),
            "source_commit": ready["source_commit"],
            "seconds": time.time() - started,
        },
        immutable=True,
    )
    if validate_only:
        print(
            "CPU/package/runtime/GPU-availability validation passed; no inference started.",
            flush=True,
        )
        return 0
    check_gpus(min_free_gib=70, required=8)
    command = [
        str(python),
        "-I",
        str(script),
        "run",
        "--bundle",
        str(bundle),
        "--output",
        str(results),
        "--attempt",
        attempt,
        "--model",
        str(model),
    ]
    print(
        "Starting one TP8/EP Judge in foreground; progress:", results / "progress.json", flush=True
    )
    with (operational / "run.log").open("w") as log:
        process = subprocess.Popen(
            command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        save(
            operational / "WORKER.json",
            {
                "pid": process.pid,
                "host": socket.gethostname(),
                "graceful_stop": f"kill -USR1 {process.pid}",
            },
            immutable=True,
        )
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
            log.flush()
        code = process.wait()
    if code == 0:
        code = subprocess.call(
            [
                str(python),
                "-I",
                str(script),
                "report",
                "--bundle",
                str(bundle),
                "--output",
                str(results),
                "--destination",
                str(results / "reports" / attempt),
            ],
            env=env,
        )
    save(
        operational / "FINISHED.json",
        {"returncode": code, "seconds": time.time() - started},
        immutable=True,
    )
    lock.close()
    return code
