"""Portable, exclusively owned dev Judge shard; never resamples admitted work."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import inspect
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
from types import SimpleNamespace

from samtok_benchmark.io import digest, sha256_file, write_json
from . import dev_judge as canonical
from .dev_judge_stream import prefetched_batches, scored, save_new
from .dev_plan import read


def validate_result(result, item, config):
    key, (case, record) = item
    if (
        result["key"] != key
        or result["run_id"] != digest(config)
        or result["output_sha256"] != record["output_sha256"]
    ):
        raise ValueError("Result binding mismatch")
    parsed = scored(item, result["raw_response"], digest(config))
    for field in ("status", "scores", "reason", "repaired_json"):
        if result.get(field) != parsed.get(field):
            raise ValueError(f"Canonical raw-response validation failed: {key} {field}")


def pending_items(items, root):
    keys = {k for k, _ in items}
    records = {p.stem for p in (root / "records").glob("*.json")}
    admitted = {p.stem for p in (root / "admitted").glob("*.json")}
    if (records | admitted) - keys:
        raise ValueError("Unexpected records/admissions outside shard")
    if admitted - records:
        raise ValueError("Admitted requests lack responses; no automatic retry/resampling")
    return [(k, v) for k, v in items if k not in records]


def load_bundle(bundle, check_runtime=True):
    manifest = read(bundle / "manifest.json")
    config = manifest["config"]
    if digest(config) != manifest["run_id"]:
        raise ValueError("Invalid run fingerprint")
    for rel, expected in manifest["source_hashes"].items():
        if sha256_file(bundle / "repo" / rel) != expected:
            raise ValueError(f"Changed source: {rel}")
    actual_repo = Path(__file__).resolve().parents[2]
    for path in (
        Path(__file__),
        Path(canonical.__file__),
        Path(inspect.getfile(canonical.Backend)),
        Path(inspect.getfile(scored)),
    ):
        relative = str(path.resolve().relative_to(actual_repo))
        if sha256_file(path) != manifest["source_hashes"][relative]:
            raise ValueError(f"Imported source differs from bundle: {path}")
    if check_runtime and canonical.fingerprint() != config:
        raise ValueError("Judge runtime/weights/canonical code differs from registered run")
    if sha256_file(bundle / "jobs.json") != manifest["jobs_sha256"]:
        raise ValueError("Changed shard jobs")
    jobs = read(bundle / "jobs.json")
    if len({j["key"] for j in jobs}) != len(jobs):
        raise ValueError("Duplicate shard key")

    def validate_job(job):
        case, record, key = job["case"], job["record"], job["key"]
        if record["task"]["model"] not in manifest["models"]:
            raise ValueError("Duplicate or unassigned job")
        if sha256_file(Path(record["output_image"])) != record["output_sha256"]:
            raise ValueError(f"Changed output: {key}")
        if canonical.binding(case, record["output_sha256"], config) != key:
            raise ValueError(f"Changed case binding: {key}")
        return key, (case, record)

    with ThreadPoolExecutor(max_workers=8) as pool:
        items = list(pool.map(validate_job, jobs))
    allocation = read(bundle / "reservation.json")
    if (
        allocation["run_id"] != manifest["run_id"]
        or allocation["remote_models"] != manifest["models"]
        or digest([k for k, _ in items]) != allocation["remote_keys_digest"]
    ):
        raise ValueError("Shard key ownership mismatch")
    return manifest, items


def run(bundle, validate_only=False):
    bundle = bundle.resolve()
    manifest, items = load_bundle(bundle)
    # Validate each distinct source/mask once, before loading 8-GPU weights.
    assets = {}
    for _, (case, _) in items:
        assets[case["source"]["image"]] = case["source"]["sha256"]
        assets.update({u["target"]["mask"]: u["target"]["mask_sha256"] for u in case["units"]})
    for rel, expected in assets.items():
        if sha256_file(canonical.DATA / rel) != expected:
            raise ValueError(f"Changed dataset asset: {rel}")
    print(
        json.dumps(
            {
                "preflight": "passed",
                "validated_jobs": len(items),
                "models": manifest["models"],
                "run_id": manifest["run_id"],
            }
        ),
        flush=True,
    )
    if validate_only:
        print(
            json.dumps(
                {
                    "validated": len(items),
                    "models": manifest["models"],
                    "run_id": manifest["run_id"],
                    "inference_calls": 0,
                }
            ),
            flush=True,
        )
        return
    if socket.gethostname() == manifest["origin_hostname"]:
        raise ValueError("Launch on the NEW machine, not the existing Judge host")
    allocation = read(bundle / "reservation.json")
    ready = read(bundle / "READY.json")
    if (
        ready["reservation_digest"] != digest(allocation)
        or allocation["run_id"] != manifest["run_id"]
        or allocation["remote_models"] != manifest["models"]
    ):
        raise ValueError("Remote ownership has not been safely activated")
    output = bundle / "results"
    output.mkdir(exist_ok=True)
    # flock is local only; mkdir is an additional shared-filesystem exclusive claim.
    # A crash leaves claim/admitted in place and requires explicit recovery.
    lock = (output / "controller.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    pending = pending_items(items, output)
    for item in items:
        path = output / "records" / f"{item[0]}.json"
        if path.exists():
            validate_result(read(path), item, manifest["config"])
    if not pending:
        print("All shard requests already terminal; no inference needed", flush=True)
        return
    gpu = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.free,driver_version",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    )
    import torch

    if torch.cuda.device_count() != 8:
        raise ValueError("Exactly 8 visible GPUs required")
    for i in range(8):
        prop = torch.cuda.get_device_properties(i)
        free, total = torch.cuda.mem_get_info(i)
        if "H100" not in prop.name or total < 79 * 1024**3 or free < total * 0.90:
            raise ValueError(
                f"Need idle 8x H100 80GB, GPU {i}: {prop.name}, free={free}, total={total}"
            )
    claim = output / "ACTIVE"
    claim.mkdir()
    write_json(
        claim / "owner.json",
        {"hostname": socket.gethostname(), "pid": os.getpid(), "started_at": time.time()},
    )
    segment = output / "executions" / time.strftime("node2_%Y%m%dT%H%M%SZ", time.gmtime())
    segment.mkdir(parents=True, exist_ok=False)
    receipt = {
        "run_id": manifest["run_id"],
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "started_at": time.time(),
        "status": "loading",
        "models": manifest["models"],
        "gpu": gpu,
        "cuda": torch.version.cuda,
        "config": manifest["config"],
        "reservation_digest": digest(allocation),
        "runner_sha256": sha256_file(Path(__file__)),
        "backend_sha256": sha256_file(Path(inspect.getfile(canonical.Backend))),
        "environment": {
            k: v
            for k, v in os.environ.items()
            if k.startswith(("VLLM_", "NCCL_", "CUDA_", "TORCH_"))
        },
        "extra_judge_calls": 0,
        "scheduling": "prefetch16; serial by model",
        "test_started": False,
        "freeze_authorized": False,
    }
    write_json(segment / "receipt.json", receipt)
    write_json(output / "current.json", {"receipt": str(segment / "receipt.json")})
    drain = [False]
    signal.signal(signal.SIGUSR1, lambda *_: drain.__setitem__(0, True))
    completed = 0
    try:
        args = SimpleNamespace(
            model=canonical.MODEL, **manifest["config"]["engine"], **manifest["config"]["decode"]
        )
        backend = canonical.Backend(args, 22)
        receipt["status"] = "running"
        write_json(segment / "receipt.json", receipt)
        start = time.monotonic()
        batches = prefetched_batches(
            pending,
            lambda item: canonical.evidence(item[1][0], item[1][1]["output_image"]),
            group_key=lambda item: item[1][1]["task"]["model"],
        )
        try:
            for batch, conversations in batches:
                if drain[0]:
                    break
                tick = time.monotonic()
                for key, _ in batch:
                    save_new(
                        output / "admitted" / f"{key}.json",
                        {"key": key, "execution": str(segment), "at": time.time()},
                    )
                answers = backend.generate(conversations)
                for item, answer in zip(batch, answers, strict=True):
                    result = scored(item, answer, manifest["run_id"])
                    result.update(
                        execution_receipt=str(segment / "receipt.json"),
                        completed_at=time.time(),
                        scheduling="prefetch16",
                        concurrency=16,
                        batch_size=len(batch),
                        batch_wall_seconds=time.monotonic() - tick,
                    )
                    save_new(output / "records" / f"{item[0]}.json", result)
                    completed += 1
                progress = {
                    "updated_at": time.time(),
                    "completed_this_execution": completed,
                    "pending_initial": len(pending),
                    "model": batch[0][1][1]["task"]["model"],
                    "wall_seconds": time.monotonic() - start,
                    "status": "running",
                }
                write_json(output / "progress.json", progress)
                print(json.dumps(progress), flush=True)
        finally:
            batches.close()
        receipt.update(
            status="drained" if drain[0] else "completed",
            ended_at=time.time(),
            production_calls=completed,
        )
        write_json(segment / "receipt.json", receipt)
        write_json(output / "progress.json", receipt)
        # Only clean completion releases claim. Exceptions retain it for inspection.
        (claim / "owner.json").unlink()
        claim.rmdir()
    except BaseException as exc:
        receipt.update(
            status="error", error=repr(exc), ended_at=time.time(), production_calls=completed
        )
        write_json(segment / "receipt.json", receipt)
        raise
    finally:
        lock.close()


def merge(bundle, loaded=None):
    """Validate raw responses and bindings before importing, never replace scores."""
    manifest, items = loaded or load_bundle(bundle, check_runtime=False)
    root = canonical.ROOT / "judge" / manifest["run_id"]
    if read(root / "config.json") != manifest["config"]:
        raise ValueError("Local canonical run changed")
    allocation = read(bundle / "reservation.json")
    if read(bundle / "READY.json")["reservation_digest"] != digest(allocation):
        raise ValueError("Unactivated remote allocation")
    original_keys = {b["key"] for b in read(root / "bindings.json")}
    if not {k for k, _ in items} <= original_keys:
        raise ValueError("Remote keys not in original registered bindings")
    imported = existing = 0
    for item in items:
        key = item[0]
        src = bundle / "results/records" / f"{key}.json"
        if not src.exists():
            continue
        result = read(src)
        validate_result(result, item, manifest["config"])
        execution = Path(result["execution_receipt"])
        if not execution.resolve().is_relative_to((bundle / "results/executions").resolve()):
            raise ValueError("Unrecognized remote execution")
        receipt = read(execution)
        if (
            receipt["run_id"] != manifest["run_id"]
            or receipt["config"] != manifest["config"]
            or receipt["reservation_digest"] != digest(allocation)
            or receipt["backend_sha256"]
            != manifest["source_hashes"]["samtok_benchmark/v2/judge.py"]
            or receipt["runner_sha256"]
            != manifest["source_hashes"]["samtok_benchmark/ifbench/dev_judge_shard.py"]
        ):
            raise ValueError("Execution receipt mismatch")
        dest = root / "records" / src.name
        if dest.exists():
            if read(dest) != result:
                raise ValueError(f"Conflicting local/remote result: {key}")
            existing += 1
        else:
            save_new(dest, result)
            imported += 1
    status = {
        "at": time.time(),
        "imported": imported,
        "already_imported": existing,
        "total": len(items),
        "pending": len(items) - imported - existing,
    }
    write_json(bundle / "merge_status.json", status)
    print(json.dumps(status), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--merge-watch", action="store_true")
    args = parser.parse_args()
    if args.merge_watch:
        loaded = load_bundle(args.bundle, check_runtime=False)
        while True:
            merge(args.bundle, loaded)
            time.sleep(60)
    else:
        run(args.bundle, args.validate_only)
