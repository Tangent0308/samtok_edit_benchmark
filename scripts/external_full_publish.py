#!/usr/bin/env python3
"""Publish an immutable, pushed four-node benchmark package with no host-local dependency."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[1]
NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
MODELS = ["sitedit", "qwen21", "qwen2511", "replan", "mirage", "flux3", "mice", "flux2_klein9b"]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def publish(benchmark, destination, bundle):
    destination, bundle = map(lambda p: Path(p).resolve(), (destination, bundle))
    if any(not p.is_relative_to(NAS) for p in (destination, bundle)) or destination.exists():
        raise ValueError("Publish only to a new NAS package directory")
    branch = "eval-" + benchmark.replace("_", "-")
    if (
        subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip()
        != branch
    ):
        raise ValueError("Wrong evaluation branch")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO, text=True).strip():
        raise ValueError("Commit all changes before publishing")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    remote = subprocess.check_output(
        ["git", "ls-remote", "origin", "refs/heads/" + branch], cwd=REPO, text=True
    ).split()[0]
    if remote != commit:
        raise ValueError("Push the source commit before publication")
    cfg = json.loads((REPO / "configs/external" / f"{benchmark}_full4.json").read_text())
    index = json.loads((bundle / "index.json").read_text())
    if len(index["cases"]) != cfg["benchmark"]["requests"] or index.get("scope") != "full":
        raise ValueError("Incomplete full-release bundle")
    spec = importlib.util.spec_from_file_location(
        "publish_input_policy", REPO / "src/samtok_benchmark/external_full/input_policy.py"
    )
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    policy.runnable_ids(index, [r["case_id"] for r in index["cases"]], cfg)
    cfg["runtime"] = {
        k: "@NODE_RUNTIME@/" + v
        for k, v in {
            "generation": "generation/env/bin/python",
            "pass1": "env_pass1/bin/python",
            "v4": "env_v4/bin/python",
            "metrics": "env_metrics/bin/python",
        }.items()
    }
    destination.mkdir(parents=True)
    config = destination / "configuration.json"
    config.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    archive = destination / "repo.tar"
    with archive.open("xb") as stream:
        subprocess.run(
            [
                "git",
                "archive",
                "--format=tar",
                commit,
                "src",
                "scripts",
                "configs",
                "tests",
                "pyproject.toml",
                "AGENTS.md",
            ],
            cwd=REPO,
            stdout=stream,
            check=True,
        )
    for source, name in [
        ("scripts/external_full_entry.py", "entry.py"),
        ("src/samtok_benchmark/external_full/coordination.py", "coordination.py"),
    ]:
        shutil.copyfile(REPO / source, destination / name)
    start = destination / "start.sh"
    start.write_text(
        '#!/usr/bin/env bash\nset -Eeuo pipefail\nPACKAGE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"\nexec /usr/bin/python3 -I "$PACKAGE/entry.py" --package "$PACKAGE" "$@"\n'
    )
    descriptors = NAS / ".ifbench-tmp/external_bench_20261102/refedit_runtimes"
    runtime_paths = {name: descriptors / f"env_{name}.json" for name in ("pass1", "v4")}
    runtime_paths["metrics"] = (
        NAS / ".ifbench-tmp/compbench_full_20261107/runtimes/metrics-runtime.json"
    )
    runtimes = {k: {"path": str(p), "sha256": sha(p)} for k, p in runtime_paths.items()}
    controls = {
        str(config): sha(config),
        str(bundle / "index.json"): sha(bundle / "index.json"),
        str(NAS / ".ifbench-tmp/fairness-v2-dev20-20261030/bootstrap.json"): sha(
            NAS / ".ifbench-tmp/fairness-v2-dev20-20261030/bootstrap.json"
        ),
    }
    controls.update({v["path"]: v["sha256"] for v in runtimes.values()})
    # Freeze the executed objective-metric sources as well as their selected
    # weight/configuration files. Native runtime archives verify their payloads
    # independently on each node before any inference is admitted.
    upstream = Path(cfg["scoring"]["upstream"])
    metric_files = (
        [upstream / "eval_all.py"]
        if benchmark == "compbench"
        else list((upstream / "evaluation").rglob("*.py"))
    )
    if benchmark == "interedit":
        metric_files.append(Path(cfg["scoring"]["checkpoint"]))
        alpha = NAS / ".ifbench-tmp/external_pilots_20261107/deps/alphaclip-ef9262b"
        metric_files.extend((alpha / "alpha_clip").rglob("*.py"))
    if cfg["scoring"].get("clip_path"):
        metric_files.extend(
            p
            for p in Path(cfg["scoring"]["clip_path"]).iterdir()
            if p.is_file() and p.suffix in {".json", ".txt", ".bin", ".safetensors"}
        )
    for path in metric_files:
        if not path.is_relative_to(NAS):
            raise ValueError(f"Non-NAS scoring dependency: {path}")
        controls[str(path)] = sha(path)
    if benchmark == "compbench":
        prompt = cfg["scoring"]["vlm_config"]
        if sha(prompt["prompts"]) != prompt["prompts_sha256"]:
            raise ValueError("Frozen GPT prompts changed")
        controls[prompt["prompts"]] = prompt["prompts_sha256"]
    spec = importlib.util.spec_from_file_location(
        "entry_plan", REPO / "scripts/external_full_entry.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    spec = importlib.util.spec_from_file_location("coord_plan", destination / "coordination.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    plan = {
        "benchmark": benchmark,
        "bundle_digest": index["digest"],
        "models": MODELS,
        "workers": 4,
        "gpus_per_worker": 8,
        "node_case_ids": {str(r): module.partition(index, r, helper) for r in range(4)},
        "results_root": cfg["formal_results_root"],
        "source_commit": commit,
    }
    plan_path = destination / "PLAN.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    controls[str(plan_path)] = sha(plan_path)
    ready = {
        "schema": "external.full4.ready.v1",
        "benchmark": benchmark,
        "source_commit": commit,
        "models": MODELS,
        "topology": {"workers": 4, "gpus_per_worker": 8},
        "configuration": str(config),
        "bundle": str(bundle),
        "bundle_digest": index["digest"],
        "plan_digest": sha(plan_path),
        "results_root": cfg["formal_results_root"],
        "runtimes": runtimes,
        "control_files": controls,
        "code": {"archive": str(archive), "sha256": sha(archive)},
        "entry_sha256": sha(destination / "entry.py"),
        "coordination_sha256": sha(destination / "coordination.py"),
        "start_sha256": sha(start),
    }
    (destination / "READY.json").write_text(json.dumps(ready, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "package": str(destination),
                "ready_sha256": sha(destination / "READY.json"),
                "source_commit": commit,
                "plan_digest": ready["plan_digest"],
                "results_root": ready["results_root"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--benchmark", choices=("compbench", "interedit", "omni_iie"), required=True)
    p.add_argument("--destination", required=True)
    p.add_argument("--bundle", required=True)
    publish(**vars(p.parse_args()))
