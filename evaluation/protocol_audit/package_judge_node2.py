"""Snapshot the authorized three-model dev Judge shard into shared temporary storage."""

import collections
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

from samtok_benchmark.io import digest, sha256_file, write_json
from samtok_benchmark.ifbench import dev_judge as canonical
from samtok_benchmark.ifbench.dev_plan import ROOT, read

BUNDLE = Path("/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/judge-node2-20261029")
REPO = Path("/opt/tiger/tanyue/if-bench")
MODELS = ["qwen21", "mirage", "mice"]


def main():
    BUNDLE.mkdir(parents=True, exist_ok=True)
    if (BUNDLE / "READY.json").exists():
        raise RuntimeError("Published bundle is immutable; do not overwrite it")
    current = read(ROOT / "judge/current.json")
    jr = ROOT / "judge" / current["run_id"]
    config = read(jr / "config.json")
    by_case = canonical.cases()
    grouped = {}
    for b in read(jr / "bindings.json"):
        r = read(Path(b["record"]))
        if b["key"] in grouped:
            assert grouped[b["key"]]["task"]["model"] == r["task"]["model"], (
                "Cross-model shared key needs explicit assignment"
            )
        else:
            grouped[b["key"]] = r
    jobs = []
    (BUNDLE / "outputs").mkdir(exist_ok=True)

    def copy_job(entry):
        key, r = entry
        assert not (jr / "records" / f"{key}.json").exists(), "Remote key already scored"
        assert not (jr / "admitted" / f"{key}.json").exists(), "Remote key already submitted"
        source = Path(r["output_image"])
        dest = BUNDLE / "outputs" / f"{key}{source.suffix}"
        if not dest.exists() or dest.stat().st_size != source.stat().st_size:
            temporary = dest.with_suffix(".copying")
            shutil.copyfile(source, temporary)
            os.replace(temporary, dest)
        assert sha256_file(dest) == r["output_sha256"]
        return {
            "key": key,
            "case": by_case[r["task"]["case_id"]],
            "record": r | {"output_image": str(dest)},
        }

    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = list(
            pool.map(copy_job, [(k, r) for k, r in grouped.items() if r["task"]["model"] in MODELS])
        )
    # Keep each model contiguous, preserving registered request order within it.
    jobs.sort(key=lambda j: MODELS.index(j["record"]["task"]["model"]))
    write_json(BUNDLE / "jobs.json", jobs)
    for relative in ["samtok_benchmark", "data/v2_2.6.0"]:
        shutil.copytree(
            REPO / relative,
            BUNDLE / "repo" / relative,
            ignore=shutil.ignore_patterns("__pycache__"),
            dirs_exist_ok=True,
        )
    hashes = {
        str(p.relative_to(BUNDLE / "repo")): sha256_file(p)
        for p in (BUNDLE / "repo/samtok_benchmark").rglob("*.py")
    }
    allocation = {
        "run_id": current["run_id"],
        "remote_models": MODELS,
        "local_models": ["qwen2511", "flux3", "replan"],
        "origin_hostname": socket.gethostname(),
        "remote_keys_digest": digest([j["key"] for j in jobs]),
        "scope": "dev only; no freeze/test; no retries",
        "created_at": time.time(),
    }
    write_json(BUNDLE / "reservation.json", allocation)
    write_json(
        BUNDLE / "manifest.json",
        {
            "run_id": current["run_id"],
            "config": config,
            "models": MODELS,
            "origin_hostname": socket.gethostname(),
            "jobs_sha256": sha256_file(BUNDLE / "jobs.json"),
            "source_hashes": hashes,
            "counts": dict(collections.Counter(j["record"]["task"]["model"] for j in jobs)),
            "created_at": time.time(),
            "note": "Shared temporary dev artifacts; not formal experiments.",
        },
    )
    print({"packaged_jobs": len(jobs), "bundle": str(BUNDLE)}, flush=True)
    archive = BUNDLE / "runtime.tar"
    if not archive.exists():
        temp = BUNDLE / "runtime.tar.incomplete"
        subprocess.run(
            [
                "tar",
                "--exclude=__pycache__",
                "-cf",
                str(temp),
                "-C",
                "/tmp",
                "ifbench-judge-runtime",
                "-C",
                "/home/tiger/.local/share/uv/python",
                "cpython-3.12.13-linux-x86_64-gnu",
            ],
            check=True,
        )
        os.replace(temp, archive)
    write_json(
        BUNDLE / "runtime.json",
        {
            "archive": archive.name,
            "sha256": sha256_file(archive),
            "bytes": archive.stat().st_size,
            "python": "3.12.13",
            "packages": config["packages"],
        },
    )
    print({"runtime_packaged_bytes": archive.stat().st_size}, flush=True)


if __name__ == "__main__":
    main()
