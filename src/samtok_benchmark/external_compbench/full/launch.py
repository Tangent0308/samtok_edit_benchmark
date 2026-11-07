"""Foreground GPU sharding by sequence; native stages and turns run in dependency order."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time

from samtok_benchmark.external_refedit.data import read, immutable
from samtok_benchmark.external_refedit.worker import stages
from . import MODELS
from .worker import scientific_config
from samtok_benchmark.io import digest


def select_cases(index, case_ids=None):
    by_id = {x["case_id"]: x for x in index["cases"]}
    selected = set(case_ids or by_id)
    if not selected <= by_id.keys():
        raise ValueError("Unknown case IDs")
    # Explicit turn-2 selection always includes the preceding same-method turn.
    selected |= {by_id[c]["parent_case_id"] for c in selected if by_id[c]["parent_case_id"]}
    return [x for x in index["cases"] if x["case_id"] in selected]


def launch(config, bundle, output, attempt, gpus, models=MODELS, case_ids=None, remote=False, smoke=False):
    config, bundle, output = str(Path(config).resolve()), str(Path(bundle).resolve()), str(Path(output).resolve())
    cfg = read(config)
    index = read(Path(bundle) / "index.json")
    if index["digest"] != digest({k: v for k, v in index.items() if k != "digest"}):
        raise ValueError("Bundle digest mismatch")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", attempt) or len(set(gpus)) != len(gpus):
        raise ValueError("Invalid attempt or GPU list")
    if not remote and (set(gpus) - {"4", "5", "6", "7"}):
        raise ValueError("Only local GPUs 4–7 are authorized")
    if remote and (os.environ.get("ARNOLD_WORKER_NUM") != "1" or os.environ.get("ARNOLD_ID") != "0"):
        raise ValueError("Only a single-worker ARNOLD job is supported")
    if smoke and Path(output).is_relative_to(Path(cfg["formal_results_root"])):
        raise ValueError("Smoke outputs cannot enter the formal results directory")
    if not remote and not smoke:
        raise ValueError("Full evaluation is delegated to the prepared ARNOLD entry after the budget review")
    if smoke and not case_ids:
        raise ValueError("Smoke requires explicit case IDs")
    cases = select_cases(index, case_ids)
    sequences = sorted({x["sequence_id"] for x in cases})
    logs = Path(output) / "attempts" / attempt
    logs.mkdir(parents=True, exist_ok=False)
    immutable(logs / "PLAN.json", {"bundle_digest": index["digest"], "models": list(models),
              "case_ids": [x["case_id"] for x in cases], "gpus": gpus, "smoke": smoke,
              "scientific_config_digest": digest(scientific_config(cfg))})
    repo = Path(__file__).parents[4]
    children, lock, stopped = {}, threading.Lock(), threading.Event()

    def stop(signum, frame):
        stopped.set()
        with lock:
            for child in children.values():
                if child.poll() is None:
                    child.send_signal(signum)

    old = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}

    def one_card(pair):
        rank, gpu = pair
        owned = set(sequences[rank::len(gpus)])
        for model in models:
            for wave in (0, 1):
                ids = [x["case_id"] for x in cases if x["sequence_id"] in owned and (x["turn"] == 2) == bool(wave)]
                if not ids:
                    continue
                for stage in stages(model):
                    if stopped.is_set():
                        return 2
                    label = f"gpu{gpu}-{model}-turn{wave + 1}-{stage}"
                    # A fully terminal stage needs no worker/model load. Worker validates identities on reuse.
                    terminal = [Path(output) / model / stage / cid / "result.json" for cid in ids]
                    terminal_on_entry = sum(p.exists() for p in terminal)
                    if terminal_on_entry == len(terminal):
                        print(f"Verifying reusable stage {label}", flush=True)
                    runtime = "pass1" if stage == "tokens" else "v4" if model == "sitedit" else "generation"
                    paths = [str(repo / "src")]
                    if model == "sitedit":
                        method = Path(cfg["paths"]["sitedit_source"])
                        paths.extend(str(method / x) for x in ("src", "third_party/diffsynth", "third_party"))
                    scratch = Path("/tmp/ifbench/compbench-full-workers") / attempt / label
                    scratch.mkdir(parents=True, exist_ok=False)
                    env = dict(os.environ, CUDA_VISIBLE_DEVICES=gpu, CUDA_DEVICE_ORDER="PCI_BUS_ID",
                               PYTHONPATH=os.pathsep.join(paths), PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1",
                               OMP_NUM_THREADS="4", TOKENIZERS_PARALLELISM="false", HF_HUB_OFFLINE="1",
                               TRANSFORMERS_OFFLINE="1", MASTER_PORT=str(41000 + int(gpu)),
                               TORCHINDUCTOR_CACHE_DIR=str(scratch / "inductor"), TRITON_CACHE_DIR=str(scratch / "triton"))
                    for key in ("IFBENCH_NATIVE_SOURCES", "LD_PRELOAD", "PYTHONHOME", "PYTHONSTARTUP"):
                        env.pop(key, None)
                    cmd = [cfg["runtime"][runtime], "-u", "-m", "samtok_benchmark.external_compbench.full.cli",
                           "worker", "--bundle", bundle, "--config", config, "--output", output,
                           "--model", model, "--stage", stage, "--case-ids", *ids]
                    if remote:
                        cmd += ["--remote"]
                    print(f"Starting {label}: {len(ids)} requests", flush=True)
                    tick = time.monotonic()
                    with (logs / f"{label}.log").open("x") as stream:
                        child = subprocess.Popen(cmd, env=env, cwd=scratch, stdout=stream, stderr=subprocess.STDOUT)
                        with lock:
                            children[label] = child
                            if stopped.is_set():
                                child.terminate()
                        immutable(logs / f"{label}.pid.json", {"pid": child.pid})
                        progress = {"model": model, "stage": stage, "gpu": gpu, "wave": wave,
                                    "expected": len(ids), "terminal_on_entry": terminal_on_entry,
                                    "new_terminal": 0, "new_completed": 0, "new_failed": 0, "pid": child.pid}
                        pattern = re.compile(re.escape(model + "/" + stage + "/") + r"([^:\n]+): (completed|failed|blocked_dependency) ")
                        seen, offset, tail = set(), 0, ""
                        while True:
                            code = child.poll()
                            with (logs / f"{label}.log").open(errors="replace") as reader:
                                reader.seek(offset)
                                text = tail + reader.read()
                                offset = reader.tell()
                            for cid, status in pattern.findall(text.replace("\r", "\n")):
                                if cid not in seen:
                                    seen.add(cid)
                                    progress["new_terminal"] += 1
                                    progress["new_completed" if status == "completed" else "new_failed"] += 1
                            tail = text[-2048:]
                            progress.update(updated=datetime.now(timezone.utc).isoformat(),
                                            wall_seconds=time.monotonic() - tick, returncode=code)
                            tmp = logs / f"{label}.progress.partial"
                            tmp.write_text(json.dumps(progress) + "\n")
                            tmp.replace(logs / f"{label}.progress.json")
                            if code is not None:
                                break
                            time.sleep(10)
                        with lock:
                            children.pop(label, None)
                    immutable(logs / f"{label}.exit.json", {"returncode": code, "wall_seconds": time.monotonic() - tick})
                    if code:
                        stopped.set()
                        return code
            immutable(logs / f"gpu{gpu}-{model}.terminal.json", {
                "model": model, "gpu": gpu, "case_ids": [x["case_id"] for x in cases if x["sequence_id"] in owned]})
        return 0

    try:
        with ThreadPoolExecutor(max_workers=len(gpus)) as pool:
            results = list(pool.map(one_card, enumerate(gpus)))
        result = int(any(results))
        immutable(logs / "DONE.json", {"exit_code": result, "workers": results})
        return result
    finally:
        for sig, previous in old.items():
            signal.signal(sig, previous)
