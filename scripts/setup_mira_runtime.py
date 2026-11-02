#!/usr/bin/env python3
"""Prepare/check three CPU-side runtimes. This script never launches GPU inference."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

ARCHIVE_SHA = "a9defaaec05b3b54fda510f7b6d8978e1633ddb51354be8049235f7770bf636a"
BOOTSTRAP = Path("/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/"
                 "fairness-v2-dev20-20261030/bootstrap.json")


def run(command, **kwargs):
    subprocess.run(list(map(str, command)), check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=REPO / "configs/external/mira.json")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    from samtok_benchmark.external_mira import METHOD_COMMIT
    method = Path(config["paths"]["sitedit_source"])
    commit = subprocess.check_output(["git", "-C", str(method), "rev-parse", "HEAD"], text=True).strip()
    if commit != METHOD_COMMIT or subprocess.check_output(
            ["git", "-C", str(method), "status", "--porcelain"], text=True).strip():
        raise ValueError("SITEdit dependency must be the clean pinned revision")
    runtimes = {k: Path(v) for k, v in config["runtime"].items()}
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="", PYTHONDONTWRITEBYTECODE="1",
               PYTHONNOUSERSITE="1", PYTHONPATH=os.pathsep.join(map(str, (
                   REPO / "src", method / "src", method / "third_party/diffsynth",
                   method / "third_party"))))
    uv = os.environ.get("UV_BIN") or shutil.which("uv") or str(Path.home() / ".local/bin/uv")
    if not args.check_only:
        if not runtimes["generation"].is_file():
            from evaluation.protocol_audit.bootstrap_fairness_dev20 import prepare_runtime
            descriptor = json.loads(BOOTSTRAP.read_text())["generation"]
            if descriptor["sha256"] != ARCHIVE_SHA or runtimes["generation"].parents[2].name != "generation":
                raise ValueError("Unexpected generation runtime/archive layout")
            prepare_runtime("generation", descriptor, runtimes["generation"].parents[3], REPO)
        for name in ("v4", "pass1"):
            python = runtimes[name]
            if python.is_file():
                continue
            destination = python.parents[1]
            if destination.exists() and any(destination.iterdir()):
                raise ValueError(f"Incomplete existing runtime; inspect without overwriting: {destination}")
            if name == "v4":
                run([uv, "venv", "--python", "/usr/bin/python3.11", "--no-python-downloads", destination], env=env)
                run([uv, "pip", "install", "--python", python, "--torch-backend", "cu128",
                     "--index-url", "https://bytedpypi.byted.org/simple/", "-r", "requirements.txt"],
                    cwd=method, env=env)
            else:
                run(["bash", method / "scripts/ifbench/setup_pass1_env.sh", destination],
                    cwd=method, env=dict(env, UV_BIN=uv))
        # This SDK supplies only the user-requested Azure ModelHub transport.
        run([uv, "pip", "install", "--python", runtimes["generation"], "openai==3.28.0"], env=env)
    expected = {"generation": {"torch": "2.8.0", "transformers": "5.19.0",
                                "diffusers": "0.42.0.dev0", "openai": "3.28.0"},
                "pass1": {"torch": "2.8.0", "transformers": "5.19.0", "peft": "0.20.0"},
                "v4": {"torch": "2.8.0", "transformers": "5.12.1", "peft": "0.20.0"}}
    for name, python in runtimes.items():
        if not python.is_file():
            raise FileNotFoundError(f"Missing {name} runtime: {python}")
        code = ("import importlib.metadata as m,json,torch; "
                f"expected={expected[name]!r}; "
                "actual={k:m.version(k).split('+')[0] for k in expected}; "
                "assert actual==expected,(actual,expected); "
                "assert not torch.cuda.is_initialized(); print(json.dumps(actual))")
        print(f"Checking {name}: {python}", flush=True)
        run([python, "-B", "-c", code], env=env)
    print("MIRA runtimes validated; no GPU inference was launched.", flush=True)


if __name__ == "__main__":
    main()
