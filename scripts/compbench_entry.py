#!/usr/bin/env python3
"""Single-node eight-GPU ARNOLD entry. Stage verified NAS code/runtimes, then generation and CPU scores."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
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
        for data in iter(lambda: stream.read(8 << 20), b""):
            h.update(data)
    return h.hexdigest()


def main(package, attempt):
    package = Path(package).resolve()
    ready = json.loads((package / "READY.json").read_text())
    if not re.fullmatch(r"[A-Za-z0-9_-]+", attempt):
        raise ValueError("Invalid attempt")
    if (os.environ.get("ARNOLD_WORKER_NUM"), os.environ.get("ARNOLD_WORKER_GPU"), os.environ.get("ARNOLD_ID")) != ("1", "8", "0"):
        raise ValueError("This entry requires exactly one ARNOLD worker with eight GPUs")
    for path, expected in [(package / "entry.py", ready["entry_sha256"]),
                           (package / "start.sh", ready["start_sha256"]),
                           (ready["configuration"], ready["configuration_sha256"]),
                           (Path(ready["bundle"]) / "index.json", ready["index_sha256"])]:
        if sha(path) != expected:
            raise ValueError(f"Published file changed: {path}")
    results = Path(ready["results_root"])
    logs = results / "launches" / attempt
    logs.mkdir(parents=True, exist_ok=False)
    (logs / "CLAIM.json").write_text(json.dumps({"attempt": attempt, "pid": os.getpid(), "ready_sha256": sha(package / "READY.json")}) + "\n")
    runtime = Path("/tmp/compbench-full") / ready["source_commit"][:12] / attempt
    runtime.mkdir(parents=True, exist_ok=False)
    repo = runtime / "repo"
    repo.mkdir()
    if sha(ready["code"]["archive"]) != ready["code"]["sha256"]:
        raise ValueError("Code archive changed")
    with tarfile.open(ready["code"]["archive"]) as stream:
        for member in stream:
            name = Path(member.name)
            if name.is_absolute() or ".." in name.parts or not (member.isfile() or member.isdir()):
                raise ValueError("Unexpected link or unsafe name in published code archive")
            stream.extract(member, repo)
    children, lock, stopped = {}, threading.Lock(), threading.Event()

    def stop(sig, frame):
        stopped.set()
        with lock:
            for child in children.values():
                if child.poll() is None:
                    child.send_signal(sig)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def call(name, command, env=None):
        if stopped.is_set():
            raise RuntimeError("Entry interrupted; no further stages started")
        print(f"[{attempt}] {name}; log={logs / (name + '.log')}", flush=True)
        (logs / "phase.txt").write_text(name + "\n")
        with (logs / f"{name}.log").open("x") as log:
            child = subprocess.Popen(command, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
            with lock:
                children[name] = child
                if stopped.is_set():
                    child.terminate()
            code = child.wait()
            with lock:
                children.pop(name, None)
        if code:
            raise RuntimeError(f"{name} exited {code}; inspect {logs / (name + '.log')}")

    try:
        cfg = json.loads(Path(ready["configuration"]).read_text())
        key_file = os.environ.get("COMPBENCH_API_KEY_FILE")
        if cfg["scoring"]["vlm"] == "gpt54-paper-v2-confirmed" and (not key_file or not Path(key_file).is_file()):
            raise RuntimeError("Confirmed GPT scoring requires COMPBENCH_API_KEY_FILE; no model started")
        prompt_spec = cfg["scoring"].get("vlm_config")
        if prompt_spec and sha(prompt_spec["prompts"]) != prompt_spec["prompts_sha256"]:
            raise ValueError("Published scoring prompts changed; no model started")
        call("stage-sources", ["/usr/bin/python3", "-I", "scripts/refedit_stage.py", "sources", "--destination", str(runtime / "sources")])
        call("stage-generation", ["/usr/bin/python3", "-I", "scripts/refedit_stage.py", "generation", "--work", str(runtime)])
        descriptors = Path("/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/refedit_runtimes")
        hashes = {"v4": "450e236b51febcde15c53c05ed0c4d52feafe51135f3450d61d17eec987385fb",
                  "pass1": "7f88a98c8b47919342c671cc881a06927f79fb7d5f81d3697cb0c579d7750675"}
        for name, expected in hashes.items():
            call("stage-" + name, ["/usr/bin/python3", "-I", "scripts/refedit_runtime.py", "unpack",
                 "--descriptor", str(descriptors / f"env_{name}.json"), "--descriptor-sha256", expected,
                 "--destination", str(runtime / f"env_{name}"), "--method-source", cfg["paths"]["sitedit_source"]])
        call("stage-metrics", ["/usr/bin/python3", "-I", "scripts/compbench_runtime.py", "unpack",
             "--descriptor", ready["metrics_runtime"], "--expected-sha", ready["metrics_descriptor_sha256"],
             "--destination", str(runtime / "env_metrics"), "--interpreter", str(runtime / "generation/cpython/bin/python3.11")])
        cfg["paths"]["sources"] = str(runtime / "sources")
        cfg["runtime"] = {"generation": str(runtime / "generation/env/bin/python"),
                          **{name: str(runtime / f"env_{name}/bin/python") for name in ("v4", "pass1", "metrics")}}
        config_path = runtime / "configuration.json"
        config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
        run = results / "run"
        env = dict(os.environ, CUDA_VISIBLE_DEVICES="", PYTHONNOUSERSITE="1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
        def generate():
            call("generation", [cfg["runtime"]["generation"], "-I", "scripts/compbench_full.py", "run",
                 "--config", str(config_path), "--bundle", ready["bundle"], "--output", str(run),
                 "--attempt", attempt, "--remote", "--gpus", *map(str, range(8))])

        # Finish scoring each model while GPUs generate the following model. Poll just eight
        # terminal markers, never all 27,848 image/score paths after each generation batch.
        with ThreadPoolExecutor(max_workers=1) as generation_pool:
            generation = generation_pool.submit(generate)
            try:
                for model in ("sitedit", "qwen21", "qwen2511", "replan", "mirage", "flux3", "mice", "flux2_klein9b"):
                    markers = [run / "attempts" / attempt / f"gpu{gpu}-{model}.terminal.json" for gpu in range(8)]
                    while not all(p.exists() for p in markers):
                        if stopped.is_set():
                            raise RuntimeError("Entry interrupted while waiting for model completion")
                        if generation.done():
                            generation.result()
                            raise RuntimeError(f"Missing model completion markers: {model}")
                        time.sleep(10)
                    def metrics(shard):
                        call(f"metrics-{model}-{shard}", [cfg["runtime"]["metrics"], "-I", "scripts/compbench_full.py", "score",
                             "--config", str(config_path), "--bundle", ready["bundle"], "--run", str(run),
                             "--output", str(results / "scores"), "--models", model,
                             "--shard", str(shard), "--shards", "8"], env)
                    def vlm():
                        if cfg["scoring"]["vlm"] == "gpt54-paper-v2-confirmed":
                            call(f"vlm-{model}", [cfg["runtime"]["metrics"], "-I", "scripts/compbench_full.py", "judge",
                                 "--config", str(config_path), "--bundle", ready["bundle"], "--run", str(run),
                                 "--output", str(results / "scores"), "--models", model, "--key-file", key_file], env)
                    with ThreadPoolExecutor(max_workers=9) as pool:
                        calls = [pool.submit(metrics, i) for i in range(8)] + [pool.submit(vlm)]
                        for future in calls:
                            future.result()
                generation.result()
            except BaseException:
                stop(signal.SIGTERM, None)
                raise
        call("report", [cfg["runtime"]["metrics"], "-I", "scripts/compbench_full.py", "report",
             "--bundle", ready["bundle"], "--run", str(run), "--scores", str(results / "scores"),
             "--output", str(results / "reports" / attempt)], env)
        (logs / "DONE.json").write_text(json.dumps({"generation": "terminal", "objective_metrics": "terminal",
                                                  "vlm": cfg["scoring"]["vlm"]}) + "\n")
    except BaseException as error:
        (logs / "FAILED.json").write_text(json.dumps({"error": repr(error)}) + "\n")
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package", required=True)
    p.add_argument("--attempt", required=True)
    main(**vars(p.parse_args()))
