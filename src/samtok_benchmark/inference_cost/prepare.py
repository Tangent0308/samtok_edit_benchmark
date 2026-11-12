"""Freeze a public-only sample and original adapter inputs before profiling."""

from pathlib import Path

from .common import MODELS, SETTINGS, digest, read, save, select_sources, sha


def prepare(bundle, sit_run, method_source, destination, per_k=5, seed=20261112):
    bundle, sit_run = Path(bundle).resolve(), Path(sit_run).resolve()
    original = read(bundle / "plan.json")
    sit = read(sit_run / "RUN.json")
    selected = select_sources(sit["requests"], seed, per_k)
    ids = [r["case_id"] for r in selected]
    requests_by_key = {(r["setting"], r["case_id"]): r for r in sit["requests"]}
    tasks_by_key = {(r["model"], r["setting"], r["case_id"]): r for r in original["tasks"]}
    requests, tasks, files = [], [], {}
    for setting in SETTINGS:
        for i, case in enumerate(ids):
            r = dict(requests_by_key[setting, case], source_index=i)
            public = read(r["public"])
            if len(public["units"]) != r["units"]:
                raise ValueError("Public K differs from the existing run index")
            requests.append(r)
            for key in ("public", "geometry"):
                files[r[key]] = r[key + "_sha256"]
            for model in MODELS:
                if model == "sitedit":
                    continue
                t = tasks_by_key[model, setting, case]
                tasks.append(
                    {
                        k: t[k]
                        for k in [
                            "model",
                            "case_id",
                            "setting",
                            "request_path",
                            "request_sha256",
                            "input_files",
                            "result_path",
                            "planner_dir",
                        ]
                    }
                )
                files[t["request_path"]] = t["request_sha256"]
                files.update(t["input_files"])
                native = read(t["request_path"])
                if native.get("planner_template"):
                    files[native["planner_template"]] = sha(native["planner_template"])
    for path, expected in files.items():
        if sha(path) != expected:
            raise ValueError(f"Frozen public asset changed: {path}")
    config = {
        "paths": original["paths"],
        "model_specifications": original["model_specifications"],
        "configuration_reference": original["configuration_reference"],
    }
    expected_method = read(Path(method_source) / "configs/ifbench/main_row.json")
    if expected_method != sit["method"]:
        raise ValueError("R2 method config differs from the completed IF-Bench run")
    plan = {
        "schema": "ifbench.inference-cost.v1",
        "benchmark_bundle": str(bundle),
        "benchmark_ready_sha256": sha(bundle / "READY.json"),
        "benchmark_plan_digest": original["digest"],
        "baseline_config": config,
        "method": sit["method"],
        "method_source": str(Path(method_source).resolve()),
        "sitedit_reference_run": str(sit_run),
        "method_commit": "8beaffbd24a773cb7441948df57e65c576e31126",
        "selection_seed": seed,
        "seed": 42,
        "per_k": per_k,
        "models": list(MODELS),
        "settings": list(SETTINGS),
        "case_ids": ids,
        "requests": requests,
        "tasks": tasks,
        "repetitions": 3,
        "warmup_policy": "One successful warmup per worker phase, trying assigned requests in fixed order; every attempt retained. No output/score-based sample selection.",
        "assets": files,
        "timing_definition": "Synchronized warm native-stage wall time; public reads from RAM; "
        "weight loading, validation and final image persistence excluded. Native CPU/GPU "
        "transfers, encoding, decoding and mandatory compile resets included. "
        "The sum of independently resident stage times is not end-to-end request latency.",
        "memory_definition": "Peak allocated/reserved GPU memory per active stage, not all-stage residency.",
        "quality_policy": "No Judge, no score changes or candidate selection. Fixed-seed timing repeats only.",
        "output_root_policy": "New cost-study records only; never overwrite benchmark results.",
    }
    plan["digest"] = digest(plan)
    save(destination, plan, immutable=True)
    return plan
