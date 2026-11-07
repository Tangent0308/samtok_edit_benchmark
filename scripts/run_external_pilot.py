"""Foreground two-model pilot launcher; one stage per GPU, immutable generation receipts."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument("--config", required=True)
p.add_argument("--bundle", required=True)
p.add_argument("--output", required=True)
p.add_argument("--gpus", nargs=2, required=True)
p.add_argument("--case-ids", nargs="+")
p.add_argument("--attempt", required=True)
a = p.parse_args()
c = json.loads(Path(a.config).read_text())
repo = Path(__file__).resolve().parents[1]
logs = Path(a.output) / "logs" / a.attempt
logs.mkdir(parents=True, exist_ok=False)

def run_model(model, gpu):
    for stage in (["tokens", "edit"] if model == "sitedit" else ["edit"]):
        runtime = "pass1" if stage == "tokens" else "v4" if model == "sitedit" else "generation"
        paths = [str(repo / "src")]
        if model == "sitedit":
            source = Path(c["paths"]["sitedit_source"])
            paths += [str(source / name) for name in ("src", "third_party/diffsynth", "third_party")]
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=gpu, CUDA_DEVICE_ORDER="PCI_BUS_ID",
                   PYTHONPATH=os.pathsep.join(paths), PYTHONNOUSERSITE="1",
                   PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1", OMP_NUM_THREADS="4",
                   TOKENIZERS_PARALLELISM="false", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
        for key in ("IFBENCH_NATIVE_SOURCES", "LD_PRELOAD", "PYTHONHOME", "PYTHONSTARTUP"):
            env.pop(key, None)
        cmd = [c["runtime"][runtime], "-m", "samtok_benchmark.external_pilot.worker",
               "--config", a.config, "--bundle", a.bundle, "--output", a.output,
               "--model", model, "--stage", stage]
        if a.case_ids:
            cmd += ["--case-ids", *a.case_ids]
        print(f"Starting {model}/{stage} on GPU {gpu}", flush=True)
        with (logs / f"{model}-{stage}.log").open("x") as log:
            child = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
            (logs / f"{model}-{stage}.pid").write_text(str(child.pid))
            rc = child.wait()
        print(f"Finished {model}/{stage}: exit {rc}", flush=True)
        if rc:
            return rc
    return 0

with ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(lambda x: run_model(*x), zip(["qwen21", "sitedit"], a.gpus)))
raise SystemExit(int(any(results)))
