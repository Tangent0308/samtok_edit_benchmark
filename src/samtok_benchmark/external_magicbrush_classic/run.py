"""Resume-safe native workers and a four-GPU local coordinator."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import threading
import time
import traceback

from PIL import Image

from samtok_benchmark.io import digest, sha256_file, write_json
from samtok_benchmark.ifbench.canvas import restore_output
from samtok_benchmark.external_magicbrush.data import immutable, read
from samtok_benchmark.external_magicbrush.worker import (
    FATAL_TERMS,
    gpu_gate,
    resolve_public,
    result_path,
)

from .common import TEMP, load_run, select_requests


def worker(output, model, shard=0, shards=1):
    output = Path(output)
    plan, cfg, index = load_run(output)
    cards = [int(x) for x in os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",") if x]
    if len(cards) != 1 or not 0 <= shard < shards or model not in plan["models"]:
        raise ValueError("Invalid GPU, model or shard")
    gpu_gate(cfg, cards)
    stop = []
    signal.signal(signal.SIGUSR1, lambda *_: stop.append(True))
    signal.signal(signal.SIGTERM, lambda *_: stop.append(True))
    sessions = plan["session_ids"][shard::shards]
    items = select_requests(index, sessions)
    counts = {"completed": 0, "failed": 0, "reused": 0, "unknown": 0, "pending": 0}
    backend = None
    for item in items:
        if stop:
            break
        public, geometry, dependency = resolve_public(item, output, model)
        if dependency and dependency["status"] == "pending_dependency":
            counts["pending"] += 1
            continue
        identity = {
            "schema": "magicbrush.classic.result.v1",
            "model": model,
            "stage": "edit",
            "key": item["key"],
            "case_id": item["case_id"],
            "bundle_digest": plan["bundle_digest"],
            "config_digest": plan["config_digest"],
            "public_digest": public["input_digest"] if public else None,
            "geometry": geometry,
            "source_code": plan["source_code"],
            "recurrent_dependency": dependency,
        }
        identity["digest"] = digest(identity)
        path = result_path(output, model, "edit", item["key"])
        if path.exists():
            saved = read(path)
            if saved["identity"] != identity:
                raise ValueError("Existing request identity differs")
            for kind in ("raw", "output"):
                if (
                    saved.get(kind + "_image")
                    and sha256_file(saved[kind + "_image"]) != saved[kind + "_sha256"]
                ):
                    raise ValueError("Saved image changed")
            counts["reused"] += 1
            continue
        directory = path.parent
        if (directory / "ADMITTED.json").exists():
            counts["unknown"] += 1
            continue
        upstream_failed = dependency and dependency["status"] != "completed"
        load_seconds = None
        if backend is None and not upstream_failed:
            from .backend import OfficialEditor
            import torch

            torch.set_num_threads(4)
            tick = time.monotonic()
            try:
                backend = OfficialEditor(model, cfg)
                torch.cuda.synchronize()
            except Exception as error:
                immutable(
                    output / "load_failures" / f"{model}-{shard}-{os.getpid()}.json",
                    {
                        "model": model,
                        "error": repr(error),
                        "traceback": traceback.format_exc(),
                        "no_request_admitted": True,
                        "gpu": cards,
                        "time": datetime.now(timezone.utc).isoformat(),
                    },
                )
                raise
            load_seconds = time.monotonic() - tick
            print(f"{model}: loaded in {load_seconds:.2f}s", flush=True)
        if stop:
            break
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "ADMITTED.json").open("x") as f:
            json.dump(
                {
                    "identity": identity,
                    "pid": os.getpid(),
                    "host": socket.gethostname(),
                    "gpu": cards,
                    "time": datetime.now(timezone.utc).isoformat(),
                },
                f,
            )
        tick = time.monotonic()
        result = {
            "identity": identity,
            "status": "failed",
            "gpu": cards,
            "host": socket.gethostname(),
            "load_seconds": load_seconds,
            "started": datetime.now(timezone.utc).isoformat(),
        }
        fatal = False
        try:
            if upstream_failed:
                raise RuntimeError("Previous model output failed; no GT replacement")
            raw = backend.run(public, directory)
            inference_seconds = time.monotonic() - tick
            with Image.open(raw) as generated:
                restored = restore_output(generated, geometry)
            out = directory / "output.png"
            restored.save(out)
            result.update(
                status="completed",
                raw_image=str(raw),
                raw_sha256=sha256_file(raw),
                output_image=str(out),
                output_sha256=sha256_file(out),
                inference_seconds=inference_seconds,
                peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated(),
                peak_gpu_reserved_bytes=torch.cuda.max_memory_reserved(),
                native_calls=1,
                packages={
                    n: importlib.metadata.version(n)
                    for n in ("torch", "transformers", "k-diffusion", "pytorch-lightning", "Pillow")
                },
            )
            counts["completed"] += 1
        except Exception as error:
            result.update(error=repr(error), traceback=traceback.format_exc())
            fatal = any(term.lower() in result["traceback"].lower() for term in FATAL_TERMS)
            counts["failed"] += 1
        result.update(
            wall_seconds=time.monotonic() - tick, finished=datetime.now(timezone.utc).isoformat()
        )
        immutable(path, result)
        print(
            f"{model}/{item['key']}: {result['status']} {result['wall_seconds']:.2f}s", flush=True
        )
        if fatal:
            raise RuntimeError("Fatal runtime failure; stop our worker for investigation")
    if counts["unknown"] or counts["pending"]:
        raise RuntimeError(f"Unresolved requests: {counts}")
    return counts


def launch(output, cards, attempt, *, estimate_path=None):
    output = Path(output).resolve()
    plan, cfg, index = load_run(output)
    if not cards or len(cards) != len(set(cards)):
        raise ValueError("Cards must be unique")
    gpu_gate(cfg, cards)
    smoke = plan["scope"] == "classic-smoke"
    if not smoke:
        if estimate_path is None:
            raise ValueError("Formal launch needs measured smoke evidence")
        estimate = read(estimate_path)
        if not estimate["all_passed"] or estimate["source_code"] != plan["source_code"]:
            raise ValueError("Smoke does not match frozen native implementation")
        if (
            estimate["config_digest"] != plan["config_digest"]
            or estimate["bundle_digest"] != plan["bundle_digest"]
        ):
            raise ValueError("Smoke inputs/configuration differ")
        if estimate["total_gpu_hours"] / len(cards) > 8:
            raise ValueError("Local estimate exceeds eight hours; report before cluster execution")
    destination = output / "attempts" / attempt
    destination.mkdir(parents=True, exist_ok=False)
    shards = 1 if smoke else len(cards)
    tasks = [
        {"model": m, "shard": s, "shards": shards} for m in plan["models"] for s in range(shards)
    ]
    immutable(
        destination / "TASKS.json",
        {"tasks": tasks, "gpus": cards, "started": datetime.now(timezone.utc).isoformat()},
    )
    guard = threading.Lock()
    children, history = {}, []
    stopping = threading.Event()

    def stop(*_):
        stopping.set()
        with guard:
            active = list(children.values())
        for p in active:
            if p.poll() is None:
                p.send_signal(signal.SIGUSR1)

    for sig in (signal.SIGUSR1, signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop)

    def on_card(card):
        while not stopping.is_set():
            with guard:
                task = tasks.pop(0) if tasks else None
            if task is None:
                return
            sessions = plan["session_ids"][task["shard"] :: task["shards"]]
            items = select_requests(index, sessions)
            if all(
                result_path(output, task["model"], "edit", item["key"]).exists() for item in items
            ):
                with guard:
                    history.append({**task, "gpu": card, "skipped_terminal": True})
                continue
            deadline = time.monotonic() + 60
            while True:
                try:
                    gpu_gate(cfg, [card])
                    break
                except ValueError as error:
                    if "occupied" not in str(error) or time.monotonic() >= deadline:
                        raise
                    if stopping.wait(3):
                        return
            tag = f"{task['model']}-{task['shard']}of{task['shards']}"
            work = TEMP / "work" / attempt / tag
            work.mkdir(parents=True, exist_ok=True)
            environment = dict(
                os.environ,
                CUDA_VISIBLE_DEVICES=str(card),
                CUDA_DEVICE_ORDER="PCI_BUS_ID",
                PYTHONUNBUFFERED="1",
                PYTHONNOUSERSITE="1",
                OMP_NUM_THREADS="4",
                HF_HUB_OFFLINE="1",
                TRANSFORMERS_OFFLINE="1",
                MASTER_PORT=str(43000 + card),
            )
            for name in ("PYTHONPATH", "PYTHONHOME", "RANK", "LOCAL_RANK", "WORLD_SIZE"):
                environment.pop(name, None)
            command = [
                cfg["runtime"]["native"],
                "-I",
                str(Path(__file__).resolve().parents[3] / "scripts/magicbrush_classic.py"),
                "worker",
                "--output",
                str(output),
                "--model",
                task["model"],
                "--shard",
                str(task["shard"]),
                "--shards",
                str(task["shards"]),
            ]
            tick = time.monotonic()
            with (destination / f"{tag}.log").open("x") as log:
                child = subprocess.Popen(
                    command, cwd=work, env=environment, stdout=log, stderr=subprocess.STDOUT
                )
                with guard:
                    children[tag] = child
                code = child.wait()
            record = {
                **task,
                "gpu": card,
                "pid": child.pid,
                "returncode": code,
                "wall_seconds": time.monotonic() - tick,
                "command": command,
            }
            with guard:
                children.pop(tag, None)
                history.append(record)
                write_json(
                    destination / "PROGRESS.json",
                    {
                        "finished": history,
                        "pending": tasks,
                        "active_pids": {k: v.pid for k, v in children.items()},
                    },
                )
            if code:
                stop()
                raise RuntimeError(f"Native worker failed: {tag}; inspect its log")

    def checked_card(card):
        try:
            on_card(card)
        except Exception:
            stop()
            raise

    with ThreadPoolExecutor(max_workers=len(cards)) as pool:
        list(pool.map(checked_card, cards))
    complete = not stopping.is_set()
    immutable(destination / ("COMPLETE.json" if complete else "STOPPED.json"), {"history": history})
    return {"complete": complete, "history": history}
