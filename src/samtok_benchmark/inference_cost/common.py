from __future__ import annotations

from contextlib import contextmanager
import builtins
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

MODELS = ("qwen21", "replan", "mirage", "mice", "sitedit")
SETTINGS = ("S1", "S3-mask")


def read(path):
    return json.loads(Path(path).read_text())


def read_status(path, previous=None):
    """Only mutable status is tolerant of a NAS rename visibility gap."""
    for delay in (0, 0.05, 0.15):
        if delay:
            time.sleep(delay)
        try:
            return read(path)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    return previous


def identity(plan, model, setting, stage, case, repeat):
    return {
        "plan_digest": plan["digest"],
        "model": model,
        "stage": stage,
        "setting": setting,
        "case_id": case,
        "repeat": repeat,
    }


def terminal(path, expected):
    if not Path(path).exists():
        return False
    value = read(path)
    if value.get("identity") != expected or value.get("status") not in {
        "completed",
        "failed",
        "blocked_dependency",
    }:
        raise ValueError(f"Invalid existing measurement: {path}")
    if value.get("raw_image") and sha(value["raw_image"]) != value.get("raw_file_sha256"):
        raise ValueError(f"Existing profiling image changed: {path}")
    return True


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(8 << 20), b""):
            h.update(data)
    return h.hexdigest()


def save(path, value, *, immutable=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if immutable and path.exists():
        if read(path) != value:
            raise ValueError(f"Existing immutable record differs: {path}")
        return
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, path)


def load_plan(path):
    value = read(path)
    if value["digest"] != digest({k: v for k, v in value.items() if k != "digest"}):
        raise ValueError("Profiling plan changed")
    return value


def select_sources(requests, seed, per_k):
    """Uses public IDs and K only; no outputs, scores or completion information."""
    first = {r["case_id"]: r for r in requests if r["setting"] == "S1"}
    groups = {}
    for k in range(2, 6):
        pool = [r for r in first.values() if r["units"] == k]
        pool.sort(key=lambda r: hashlib.sha256(f"{seed}:{r['case_id']}".encode()).hexdigest())
        if len(pool) < per_k:
            raise ValueError(f"Too few public K={k} sources")
        groups[k] = pool[:per_k]
    return [groups[k][i] for i in range(per_k) for k in range(2, 6)]


def stages(model):
    return (
        ("tokens", "edit")
        if model == "sitedit"
        else (("planner", "edit") if model in {"mirage", "replan"} else ("edit",))
    )


def jobs(plan, model, setting, shard):
    for i, request in enumerate(plan["requests"]):
        if request["setting"] != setting:
            continue
        for repeat in range(plan["repetitions"]):
            if (request["source_index"] + repeat) % 8 == shard:
                yield request, repeat


def result_dir(root, model, setting, stage, case, repeat):
    return Path(root) / "records" / model / setting / stage / case / f"repeat-{repeat}"


def gpu_snapshot():
    def query(args):
        return list(
            csv.reader(
                subprocess.check_output(
                    ["nvidia-smi", *args, "--format=csv,noheader,nounits"], text=True
                ).splitlines(),
                skipinitialspace=True,
            )
        )

    cards = [
        {
            "index": int(i),
            "uuid": u,
            "name": name,
            "total_mib": int(total),
            "used_mib": int(used),
            "utilization": int(util),
        }
        for i, u, name, total, used, util in query(
            ["--query-gpu=index,uuid,name,memory.total,memory.used,utilization.gpu"]
        )
    ]
    processes = [
        {"pid": int(pid), "uuid": u, "used_mib": mem}
        for pid, u, mem in query(["--query-compute-apps=pid,gpu_uuid,used_memory"])
    ]
    return {"time": time.time(), "cards": cards, "processes": processes}


def check_idle(snapshot):
    if len(snapshot["cards"]) != 8 or {c["index"] for c in snapshot["cards"]} != set(range(8)):
        raise RuntimeError("Exactly eight visible GPUs are required")
    if snapshot["processes"]:
        raise RuntimeError("Existing GPU compute processes detected; no process will be stopped")
    for card in snapshot["cards"]:
        if "H100" not in card["name"] or card["total_mib"] < 79000:
            raise RuntimeError("This timing plan requires eight H100 80GB GPUs")
        if card["used_mib"] > 1000 or card["utilization"] > 5:
            raise RuntimeError("A GPU is not quiet; refusing contaminated timing")


@contextmanager
def cached_reads(files):
    """Serve byte-identical public assets from RAM without changing public paths."""
    payloads = {os.fspath(Path(p)): Path(p).read_bytes() for p in files}
    if isinstance(files, dict):
        for path, expected in files.items():
            if hashlib.sha256(payloads[os.fspath(Path(path))]).hexdigest() != expected:
                raise ValueError(f"Input changed before RAM caching: {path}")
    original_builtin, original_io = builtins.open, io.open

    def wrap(original):
        def opened(
            file,
            mode="r",
            buffering=-1,
            encoding=None,
            errors=None,
            newline=None,
            closefd=True,
            opener=None,
        ):
            key = os.fspath(file) if isinstance(file, (str, os.PathLike)) else None
            if key in payloads and mode in {"r", "rt", "rb"} and opener is None:
                raw = io.BytesIO(payloads[key])
                raw.name = key
                return (
                    raw
                    if "b" in mode
                    else io.TextIOWrapper(
                        raw, encoding=encoding or "utf-8", errors=errors, newline=newline
                    )
                )
            return original(file, mode, buffering, encoding, errors, newline, closefd, opener)

        return opened

    with patch("builtins.open", wrap(original_builtin)), patch("io.open", wrap(original_io)):
        yield
