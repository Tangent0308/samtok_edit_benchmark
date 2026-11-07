"""Wait for authorized idle GPUs, then smoke-test, estimate, generate and score."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import traceback

from samtok_benchmark.io import write_json
from samtok_benchmark.external_magicbrush.data import immutable, read
from samtok_benchmark.external_magicbrush.worker import REPO, gpu_gate

from .common import PREP, TEMP, code_identity, config, prepare


def supervise(output, cards, attempt):
    """The user retains the right to stop this one foreground controller by PID."""
    output = Path(output).resolve()
    directory = PREP / "supervision" / attempt
    directory.mkdir(parents=True, exist_ok=False)
    cfg = config()
    source = code_identity()
    entry = str(REPO / "scripts/magicbrush_paper.py")
    smoke = TEMP / "smoke" / attempt
    stopping = threading.Event()
    guard = threading.Lock()
    children = {}
    stage = "preparing"
    immutable(
        directory / "OWNER.json",
        {
            "pid": os.getpid(),
            "output": str(output),
            "gpus": cards,
            "source_code": source,
            "started": datetime.now(timezone.utc).isoformat(),
        },
    )

    def status(**detail):
        record = {
            "stage": stage,
            "time": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
            "output": str(output),
            "smoke": str(smoke),
            **detail,
        }
        write_json(directory / "STATUS.json", record)
        print(json.dumps(record, ensure_ascii=False), flush=True)

    def stop(*_):
        stopping.set()
        with guard:
            active = list(children.values())
        for child in active:
            if child.poll() is None:
                child.send_signal(signal.SIGUSR1)

    for sig in (signal.SIGTERM, signal.SIGUSR1, signal.SIGINT):
        signal.signal(sig, stop)

    def wait_free(needed):
        while not stopping.is_set():
            if code_identity() != source:
                raise ValueError(
                    "Implementation changed while waiting; do not run a different configuration"
                )
            try:
                gpu_gate(cfg, needed)
                return
            except ValueError as error:
                if "occupied" not in str(error):
                    raise
                status(waiting_for_gpus=needed, reason=str(error))
                stopping.wait(30)
        raise InterruptedError("Controller stopped before GPU use")

    def run(name, runtime, args, card=None):
        if stopping.is_set():
            raise InterruptedError("Controller stopped")
        environment = dict(
            os.environ,
            PYTHONUNBUFFERED="1",
            PYTHONNOUSERSITE="1",
            OMP_NUM_THREADS="4",
            TOKENIZERS_PARALLELISM="false",
        )
        for key in ("PYTHONPATH", "PYTHONHOME", "RANK", "LOCAL_RANK", "WORLD_SIZE"):
            environment.pop(key, None)
        if card is not None:
            environment.update(CUDA_VISIBLE_DEVICES=str(card), CUDA_DEVICE_ORDER="PCI_BUS_ID")
        else:
            environment["CUDA_VISIBLE_DEVICES"] = ""
        command = [runtime, "-I", entry, *args]
        with (directory / f"{name}.log").open("x") as log:
            child = subprocess.Popen(
                command, env=environment, cwd=REPO, stdout=log, stderr=subprocess.STDOUT
            )
            with guard:
                children[name] = child
            code = child.wait()
        with guard:
            children.pop(name, None)
        if stopping.is_set():
            raise InterruptedError("Controller stopped after finishing the active request")
        if code:
            raise RuntimeError(f"{name} exited {code}; see {directory / (name + '.log')}")

    def score_all(root, prefix, assigned):
        pending = list(range(len(assigned)))

        def one(card):
            while not stopping.is_set():
                with guard:
                    if not pending:
                        return
                try:
                    gpu_gate(cfg, [card])
                except ValueError as error:
                    if "occupied" not in str(error):
                        raise
                    stopping.wait(15)
                    continue
                with guard:
                    if not pending:
                        return
                    shard = pending.pop(0)
                run(
                    f"{prefix}-score-{shard}",
                    cfg["runtime"]["scoring"],
                    [
                        "score",
                        "--output",
                        str(root),
                        "--cache",
                        str(TEMP / "score_cache" / attempt / prefix),
                        "--shard",
                        str(shard),
                        "--shards",
                        str(len(assigned)),
                        "--device",
                        "cuda",
                    ],
                    card,
                )

        def checked(card):
            try:
                one(card)
            except Exception:
                stop()
                raise

        with ThreadPoolExecutor(max_workers=len(assigned)) as pool:
            list(pool.map(checked, assigned))

    try:
        prepare(smoke, smoke=True)
        stage = "waiting_for_free_gpus"
        wait_free(cards)
        stage = "smoke_generation"
        status()
        run(
            "smoke-generation",
            cfg["runtime"]["native"],
            [
                "launch",
                "--output",
                str(smoke),
                "--gpus",
                ",".join(map(str, cards[:1])),
                "--attempt",
                attempt + "-smoke",
            ],
        )
        stage = "smoke_scoring"
        status()
        score_all(smoke, "smoke", cards[:1])
        stage = "runtime_estimate"
        run("estimate", cfg["runtime"]["scoring"], ["estimate", "--output", str(smoke)])
        estimate = read(smoke / "ESTIMATE.json")
        immutable(directory / "ESTIMATE.json", estimate)
        if not estimate["all_passed"]:
            raise RuntimeError(
                "A smoke test failed; formal generation is not authorized to bypass it"
            )
        if estimate["total_gpu_hours"] / len(cards) > 8:
            stage = "needs_cluster"
            status(estimate=estimate)
            return {"status": stage, "directory": str(directory)}
        stage = "waiting_for_formal_gpus"
        status(estimate=estimate)
        wait_free(cards)
        prepare(output)
        stage = "formal_generation"
        status(estimate=estimate)
        run(
            "formal-generation",
            cfg["runtime"]["native"],
            [
                "launch",
                "--output",
                str(output),
                "--gpus",
                ",".join(map(str, cards)),
                "--attempt",
                attempt,
                "--estimate",
                str(smoke / "ESTIMATE.json"),
            ],
        )
        stage = "formal_scoring"
        status()
        score_all(output, "formal", cards)
        stage = "reporting"
        status()
        run("report", cfg["runtime"]["scoring"], ["report", "--output", str(output)])
        stage = "complete"
        status(report=str(output / "report/MERGED_REPORT.json"))
        immutable(
            directory / "COMPLETE.json", {"report": str(output / "report/MERGED_REPORT.json")}
        )
    except InterruptedError as error:
        stage = "stopped"
        status(reason=str(error))
    except Exception as error:
        stop()
        failed_stage = stage
        stage = "failed"
        status(failed_stage=failed_stage, error=repr(error))
        immutable(
            directory / "FAILED.json",
            {"stage": failed_stage, "error": repr(error), "traceback": traceback.format_exc()},
        )
        raise
    return {"status": stage, "directory": str(directory)}
