"""Immutable identities and full-cohort requests, separate from the published run."""

from __future__ import annotations

import hashlib
from pathlib import Path

from samtok_benchmark.io import digest, sha256_file
from samtok_benchmark.external_magicbrush.bundle import load_bundle, requests
from samtok_benchmark.external_magicbrush.data import immutable, read
from samtok_benchmark.external_magicbrush.worker import REPO, source_identity as original_identity

from . import MODELS

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
PREP = NAS / ".ifbench-tmp/magicbrush_classic_20261106"
TEMP = Path("/tmp/claude_magicbrush_20261105/classic_baselines")
FORMAL = NAS / "experiments2/SAMTokEdit/external_magicbrush"
SOURCE_REPORT = FORMAL / "run_001_failure_inclusive/REPORT.json"
SOURCE_REPORT_SHA = "d7578d48c987b2c9b2509277f66d5bf1957fe726ed6be0e94f73b368d15c88ed"


def code_identity():
    result = original_identity()
    paths = list(Path(__file__).parent.glob("*.py"))
    paths.append(REPO / "scripts/magicbrush_classic.py")
    paths += [
        REPO / "src/samtok_benchmark/external_magicbrush" / name
        for name in ("metrics.py", "scoring.py", "report.py")
    ]
    return {**result, **{str(p.relative_to(REPO)): sha256_file(p) for p in paths}}


def select_requests(index, sessions):
    """Keep every mask-free request, without score/quality/overlap filtering."""
    return [r for r in requests(index, sessions) if r["track"] == "mask-free"]


def smoke_session(index):
    lengths = {s: 0 for s in index["sessions"]}
    for c in index["cases"]:
        lengths[c["session_id"]] = max(lengths[c["session_id"]], c["turn"])
    eligible = [s for s, n in lengths.items() if n == 2]
    return min(
        eligible,
        key=lambda s: hashlib.sha256(("magicbrush-classic-smoke-42:" + s).encode()).hexdigest(),
    )


def config():
    base = read(REPO / "configs/external/magicbrush.json")
    assets = read(PREP / "ASSETS.json")
    files = {Path(x["relative"]).name: x for x in assets["files"]}
    sources = {x["repo"]: x for x in assets["sources"]}
    specs = {}
    for model, repo, filename in [
        ("instructpix2pix", "timothybrooks/instruct-pix2pix", "instruct-pix2pix-00-22000.ckpt"),
        ("hive", "salesforce/HIVE", "hive_rw.ckpt"),
    ]:
        specs[model] = {
            "repository": repo,
            "commit": sources[repo]["commit"],
            "source": sources[repo]["path"],
            "source_manifest_sha256": sha256_file(Path(sources[repo]["path"]) / "SOURCE.json"),
            "checkpoint": files[filename],
            "resolution": 512,
            "steps": 100,
            "text_cfg": 7.5,
            "image_cfg": 1.5,
            "seed": 42,
            "sampler": "k_diffusion.sampling.sample_euler_ancestral",
            "magicbrush_finetuned": False,
        }
    return {
        "schema": "magicbrush.classic.config.v1",
        "seed": 42,
        "track": "mask-free",
        "metrics": base["metrics"],
        "local_gpu_policy": base["local_gpu_policy"],
        "formal_results_root": str(FORMAL),
        "models": specs,
        "deps": {k: sources[k]["path"] for k in ("CompVis/taming-transformers", "openai/CLIP")},
        "dependency_manifest_sha256s": {
            sources[k]["path"]: sha256_file(Path(sources[k]["path"]) / "SOURCE.json")
            for k in ("CompVis/taming-transformers", "openai/CLIP")
        },
        "text_init": str(NAS / "models/pretrained_models/MagicBrushClassic_20261106/text_init"),
        "text_init_files": [
            {"name": Path(r["relative"]).name, "sha256": r["sha256"]}
            for r in assets["files"]
            if r["relative"].startswith("text_init/")
        ],
        "assets_manifest_sha256": sha256_file(PREP / "ASSETS.json"),
        "native_packages": read(PREP / "NATIVE_RUNTIME.json"),
        "runtime": {
            "native": str(TEMP / "env_native/bin/python"),
            "scoring": base["runtime"]["v4"],
        },
    }


def prepare(output, *, smoke=False):
    output = Path(output).resolve()
    if smoke == output.is_relative_to(FORMAL):
        raise ValueError("Smoke and formal results must use their separate roots")
    bundle = NAS / ".ifbench-tmp/magicbrush_20261105/bundle"
    index = load_bundle(bundle)
    sessions = [smoke_session(index)] if smoke else index["sessions"]
    items = select_requests(index, sessions)
    if len(items) != (3 if smoke else 1571):
        raise ValueError("Unexpected generation coverage")
    if not smoke:
        if sha256_file(SOURCE_REPORT) != SOURCE_REPORT_SHA:
            raise ValueError("Existing report changed")
        if sessions != read(SOURCE_REPORT)["bootstrap"]["subsets"]["full"]["sessions"]:
            raise ValueError("Shared bootstrap session order differs")
    cfg = config()
    plan = {
        "schema": "magicbrush.classic.run.v1",
        "scope": "classic-smoke" if smoke else "full",
        "bundle": str(bundle),
        "bundle_digest": index["digest"],
        "config": str(output / "CONFIG.json"),
        "config_digest": digest(cfg),
        "session_ids": sessions,
        "models": list(MODELS),
        "source_code": code_identity(),
        "seed": 42,
        "requests_per_method": len(items),
        "track": "mask-free",
        "excluded_cases": [],
    }
    output.mkdir(parents=True, exist_ok=True)
    immutable(output / "CONFIG.json", cfg)
    immutable(output / "RUN.json", plan)
    for relative, expected in plan["source_code"].items():
        path = output / "source_snapshot" / relative
        raw = (REPO / relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Source changed during snapshot")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != raw:
                raise ValueError("Existing snapshot differs")
        else:
            path.write_bytes(raw)
    return plan


def load_run(output):
    output = Path(output)
    plan, cfg = read(output / "RUN.json"), read(output / "CONFIG.json")
    if plan["source_code"] != code_identity() or plan["config_digest"] != digest(cfg):
        raise ValueError("Runtime source/config differs from frozen run")
    index = load_bundle(plan["bundle"])
    if index["digest"] != plan["bundle_digest"]:
        raise ValueError("Input bundle changed")
    if tuple(plan["models"]) != MODELS or plan["track"] != "mask-free":
        raise ValueError("Unexpected model/input scope")
    return plan, cfg, index
