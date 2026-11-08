"""Run an authorized pair of local GPUs; overlap unchanged CPU/API scoring.

The initial job can be an already-started owned pilot PID. It is observed, never
signalled or restarted. Subsequent jobs are confined to this pilot's new roots.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import time

BASE = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
WORK = Path("/opt/tiger/tanyue")
PYTHON = "/tmp/ifbench/external_pilots_20261107/env_metrics/bin/python"
METRICS = BASE / "models/pretrained_models/ExternalBenchMetrics"
DEPS = BASE / ".ifbench-tmp/external_pilots_20261107/deps"
UPSTREAM = {"gie": "gie-06953ba", "compbench": "compbench-ca0ec0d", "complexbench_edit": "complexbench-edit-e5b8474",
            "interedit": "interedit-220c1dc", "complex_edit": "complex-edit-3502eaa", "gedit": "gedit-4cca05d",
            "omni_iie": "omni-iie-d957aea", "gide": "gide-afd593c"}


def root(bench):
    return BASE / "experiments2/SAMTokEdit" / ("external_"+bench) / "pilot20_20261108"


def repo(bench):
    return WORK / ("if-bench-"+bench.replace("_", "-"))


def score_commands(bench, key_file):
    r = root(bench) / "additional"
    common = ["--bundle", str(r/"bundle"), "--run", str(r/"run"), "--output", str(r/"scores"),
              "--upstream", str(DEPS/UPSTREAM[bench])]
    commands = []
    if bench in {"gie", "complexbench_edit"}:
        commands += [("judge", ["judge", *common, "--key-file", key_file])]
        extra = ["--cache", str(METRICS/"clip")] if bench == "gie" else ["--detector", str(METRICS/"grounding-dino-base")]
        commands += [("local", ["local", *common, *extra])]
    elif bench in {"complex_edit", "gedit", "gide"}:
        commands += [("judge", [*common, "--key-file", key_file])]
    elif bench == "interedit":
        commands += [("local", [*common, "--checkpoint", str(METRICS/"alphaclip/clip_l14_grit1m_fultune_8xe.pth"),
                    "--clip-cache", str(METRICS/"clip"), "--torch-home", str(METRICS/"torch")])]
    else:
        clip = METRICS/"clip-vit-large-patch14" if bench == "compbench" else BASE/"models/pretrained_models/MagicBrushMetrics/clip"
        commands += [("local", [*common, "--clip-path", str(clip)])]
    return [(name, [PYTHON, "-I", "scripts/score_external_pilot.py", bench, *args]) for name, args in commands]


def execute(bench, name, command, attempt, cpu=False):
    logs = root(bench) / "additional/orchestration" / attempt
    logs.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1",
               OMP_NUM_THREADS="4", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TORCH_HOME=str(METRICS/"torch"))
    if cpu:
        env["CUDA_VISIBLE_DEVICES"] = ""
    print(f"START {bench}/{name}", flush=True)
    with (logs / (name+".log")).open("x") as stream:
        child = subprocess.Popen(command, cwd=repo(bench), env=env, stdout=stream, stderr=subprocess.STDOUT)
        (logs / (name+".pid")).write_text(str(child.pid))
        rc = child.wait()
    (logs / (name+".terminal.json")).write_text(json.dumps({"returncode": rc})+"\n")
    print(f"END {bench}/{name} rc={rc}", flush=True)
    return rc


def score_and_report(bench, key_file, attempt):
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(execute, bench, "score-"+name, command, attempt, True)
                   for name, command in score_commands(bench, key_file)]
        scores = [f.result() for f in futures]
    if any(scores):
        print(f"SCORING NEEDS INSPECTION {bench}; preserved answers will not be resubmitted", flush=True)
        return False
    command = [PYTHON, "-I", "scripts/report_external_pilot20.py", "--benchmark", bench,
               "--root", str(root(bench)), "--previews", str(WORK/"visualization_tmp/ExternalPilot20_20261108"/bench),
               "--old-config", f"configs/external/{bench}.json", "--new-config", f"configs/external/{bench}_pilot20.json",
               "--doc", f"docs/{bench.upper()}_PILOT20_RESULTS.md"]
    return execute(bench, "report", command, attempt, True) == 0


def main(benches, gpus, key_file, attempt, wait_pid=None):
    if len(set(gpus)) != 2 or any(g not in {"4", "5", "6", "7"} for g in gpus):
        raise ValueError("Only two distinct, authorized local GPUs 4–7 may be used")
    if not Path(key_file).is_file():
        raise ValueError("Missing protected Judge credential file")
    with ThreadPoolExecutor(max_workers=2) as score_pool:
        scores = []
        for i, bench in enumerate(benches):
            selection = json.loads((root(bench)/"SELECTION.json").read_text())
            if i == 0 and wait_pid:
                path = Path(f"/proc/{wait_pid}/cmdline")
                identity = path.read_bytes() if path.exists() else None
                if identity and (b"scripts/run_external_pilot.py" not in identity or bench.encode()+b"_pilot20.json" not in identity):
                    raise ValueError("Initial PID is not this expansion's owned generation job")
                print(f"WAIT owned generation PID {wait_pid}: {bench}", flush=True)
                while identity:
                    try:
                        if path.read_bytes() != identity:
                            break
                    except FileNotFoundError:
                        break
                    time.sleep(5)
            else:
                r = root(bench)/"additional"
                command = [PYTHON, "-I", "scripts/run_external_pilot.py", "--config", f"configs/external/{bench}_pilot20.json",
                           "--bundle", str(r/"bundle"), "--output", str(r/"run"), "--gpus", *gpus, "--attempt", attempt]
                execute(bench, "generation", command, attempt)
            for model in ("sitedit", "qwen21"):
                for cid in selection["additional_ids"]:
                    p = root(bench)/"additional/run"/model/"edit"/cid/"result.json"
                    if not p.exists() or json.loads(p.read_text()).get("fatal"):
                        raise RuntimeError(f"Incomplete or fatal generation: {bench}/{model}/{cid}; queue stopped")
            scores.append(score_pool.submit(score_and_report, bench, key_file, attempt))
        results = [f.result() for f in scores]
    return int(not all(results))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--benches", nargs="+", choices=sorted(UPSTREAM), required=True)
    p.add_argument("--gpus", nargs=2, required=True)
    p.add_argument("--key-file", required=True)
    p.add_argument("--attempt", required=True)
    p.add_argument("--wait-pid", type=int)
    raise SystemExit(main(**vars(p.parse_args())))
