"""Prepare the authorized shared dev20 package without any neural inference."""

from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from samtok_benchmark.paths import repository_root
import shutil
import threading

from samtok_benchmark.io import digest, sha256_file
from samtok_benchmark.ifbench.fairness_dev_plan import (
    SCHEMA,
    MODELS,
    SETTINGS,
    read,
    request_identity,
    verify_task,
    verify_cache,
)

REPO = repository_root()
SHARED = Path("/tmp/ifbench/tiered_v1/shared_inputs_20261027")
OLD = Path("/tmp/ifbench/tiered_v1/dev_selection")
REVIEW = Path("/tmp/ifbench/fairness_v2_20261030")
SOURCES = Path("/tmp/ifbench/protocol_review_20261027/sources")
BUNDLE = Path("/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v2-dev20-20261030")
PRETRAINED = Path("/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models")


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if read(path) != value:
            raise ValueError(f"Immutable preparation record differs: {path}")
        return
    with path.open("x") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


_COPY_GUARD = threading.Lock()
_COPY_LOCKS = {}


def copy_verified(source, target):
    key = str(target)
    with _COPY_GUARD:
        lock = _COPY_LOCKS.setdefault(key, threading.Lock())
    with lock:
        return _copy_verified(source, target)


def _copy_verified(source, target):
    source, target = Path(source), Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = sha256_file(source)
    if not target.exists():
        temp = target.with_name(target.name + ".copying")
        shutil.copyfile(source, temp)
        temp.replace(target)
    if sha256_file(target) != expected:
        raise ValueError(f"Copy differs: {target}")
    return {"path": str(target), "sha256": expected, "origin_path": str(source)}


def select_cases(bundle):
    """Selection uses source IDs and public target counts, never scores/images."""
    path = bundle / "selection.json"
    split = read(SHARED / "plan/splits.json")
    by_k = defaultdict(list)
    for cid in split["dev"]:
        by_k[len(read(SHARED / "requests/S1" / cid / "public.json")["units"])].append(cid)
    n = sum(map(len, by_k.values()))
    target = {k: 20 * len(v) / n for k, v in by_k.items()}
    quota = {k: max(1, int(target[k])) for k in by_k}
    while sum(quota.values()) < 20:
        k = max(sorted(quota), key=lambda k: (target[k] - quota[k], -k))
        quota[k] += 1
    while sum(quota.values()) > 20:
        k = max([k for k in quota if quota[k] > 1], key=lambda k: (quota[k] - target[k], k))
        quota[k] -= 1
    ranks = {
        cid: hashlib.sha256(f"20261027:{cid}".encode()).hexdigest()
        for ids in by_k.values()
        for cid in ids
    }
    selected = [
        cid for k in sorted(by_k) for cid in sorted(by_k[k], key=lambda cid: ranks[cid])[: quota[k]]
    ]
    assert len(set(selected)) == 20 and not set(selected) & set(split["test"])
    value = {
        "algorithm": "proportional K-stratified largest remainder (minimum one per K), SHA256(seed:source_id) within strata",
        "seed": 20261027,
        "parent_dev_count": 108,
        "parent_split_digest": split["digest"],
        "case_ids": selected,
        "parent_K_counts": {str(k): len(v) for k, v in by_k.items()},
        "selected_K_counts": {str(k): v for k, v in quota.items()},
        "selection_ranks": ranks,
        "test_count_unchanged": len(split["test"]),
        "unused_88_remain_dev": True,
        "selection_reads_scores": False,
        "selection_reads_outputs": False,
    }
    save(path, value)
    return value


def evidence_copy(bundle, path):
    path = Path(path)
    h = sha256_file(path)
    return copy_verified(path, bundle / "cache/evidence" / h[:2] / (h + path.suffix))


def request_for(model, cid, setting, *, shared_root=None):
    from evaluation.protocol_audit import fairness_flux3_replan as fr
    from evaluation.protocol_audit import fairness_mirage_mice_probe as mm

    directory = Path(shared_root or SHARED) / "requests" / setting / cid
    public, inputs = read(directory / "public.json"), read(directory / "inputs.json")
    if model in ["flux3", "replan"]:
        value = fr.request(model, cid, setting, shared_root=shared_root)
        value["images_sha256"] = [sha256_file(Path(p)) for p in value["images"]]
        value["call_digest"] = digest(value)
        return value
    if model in ["mirage", "mice"]:
        return mm.payload(model, cid, setting, shared_root=shared_root)
    parameters = {
        "qwen2511": {
            "num_inference_steps": 40,
            "true_cfg_scale": 4.0,
            "guidance_scale": 1.0,
            "negative_prompt": " ",
            "num_images_per_prompt": 1,
            "max_sequence_length": 512,
        },
        "qwen21": {
            "num_inference_steps": 40,
            "true_cfg_scale": 1.0,
            "output_resolution": 1024,
            "use_kv_cache": True,
        },
        "flux2_klein9b": {
            "num_inference_steps": 4,
            "guidance_scale": 1.0,
            "max_sequence_length": 512,
        },
    }[model]
    form = inputs["forms"]["dual"]
    value = {
        "model": model,
        "case_id": cid,
        "setting": setting,
        "images": form["images"],
        "prompt": form["prompt"],
        "seed": 42,
        "parameters": parameters,
        "public_request": str(directory / "public.json"),
        "public_digest": public["input_digest"],
        "source": public["source"],
        "extra_component_calls": {
            "rewriter": 0,
            "planner": 0,
            "reflection": 0,
            "external_grounder": 0,
            "sam": 0,
        },
    }
    if model == "flux2_klein9b":
        value["weight_revision"] = "92196c8e11f7b6cf2b7493e037d8c5345c559216"
    return value


def old_cache(bundle, plan, task, request):
    model, setting, cid = task["model"], task["setting"], task["case_id"]
    if model not in ["qwen2511", "qwen21"] and not (
        model in ["flux3", "replan"] and setting == "S1"
    ):
        return
    directory = (
        OLD / "runs" / model / ("dual" if model.startswith("qwen") else "native") / setting / cid
    )
    oldcall, oldresult = read(directory / "call.json"), read(directory / "result.json")
    if oldresult["status"] != "generated":
        # Preserve historical failure; do not call it an identical successful computation.
        return
    ev = [
        evidence_copy(bundle, directory / "call.json"),
        evidence_copy(bundle, directory / "result.json"),
    ]
    output = Path(oldresult["output_image"])
    image = copy_verified(
        output, bundle / "cache/images" / (oldresult["output_sha256"] + output.suffix)
    )
    evidence = ev + [image]
    rec = {
        "kind": "old-qwen-dual" if model.startswith("qwen") else f"old-{model}-s1",
        "scientific_digest": task["scientific_digest"],
        "stage": "edit",
        "original_call": ev[0]["path"],
        "original_result": ev[1]["path"],
        "output_image": image["path"],
        "output_sha256": oldresult["output_sha256"],
        "evidence": evidence,
    }
    if model == "replan":
        planner = evidence_copy(bundle, oldcall["planner_record"])
        env = evidence_copy(
            bundle, Path("/tmp/ifbench/tiered_v1/smoke/replan/worker0.environment.json")
        )
        rec.update(old_planner=planner["path"], old_environment=env["path"])
        evidence += [planner, env]
    else:
        environments = list((OLD / model).glob("*environment.json"))
        env = evidence_copy(bundle, sorted(environments)[0])
        rec["old_environment"] = env["path"]
        evidence.append(env)
    stages = ["planner", "edit"] if model == "replan" else ["edit"]
    for stage in stages:
        r = {**rec, "stage": stage}
        path = bundle / "cache/generation" / model / setting / cid / (stage + ".json")
        save(path, r)
        task["cache"][stage] = str(path)
        task["cache_sha256"][stage] = sha256_file(path)
        verify_cache(plan, task, stage)


def export_judge_cache(bundle, selected, config):
    provenance = read(OLD / "judge_rejudge13_v1/analysis/PROVENANCE.json")
    entries = {}
    for item in provenance["records"]:
        if item["case_id"] not in selected:
            continue
        paths = [item["raw_path"]]
        if item.get("overlay"):
            paths.append(item["overlay"]["path"])
        if item.get("rejudge"):
            info = item["rejudge"]
            effective = info["effective_path"]
            paths += [
                info["raw_path"],
                effective,
                info["admission_path"],
                info["execution_receipt"],
                str(OLD / "judge_rejudge13_v1/authorization.json"),
                str(OLD / "judge_repair_v1/PROPOSED_REJUDGE_13.json"),
            ]
        elif item.get("overlay"):
            effective = item["overlay"]["path"]
        else:
            effective = item["raw_path"]
        copied = {p: evidence_copy(bundle, p) for p in dict.fromkeys(paths)}
        if sha256_file(Path(item["raw_path"])) != item["raw_sha256"]:
            raise ValueError("Historical Judge raw changed")
        if (
            item.get("overlay")
            and sha256_file(Path(item["overlay"]["path"])) != item["overlay"]["sha256"]
        ):
            raise ValueError("Historical Judge repair changed")
        if (
            item.get("rejudge")
            and sha256_file(Path(effective)) != item["rejudge"]["effective_sha256"]
        ):
            raise ValueError("Historical authorized rejudge changed")
        value = read(effective)
        if value["status"] != "scored":
            raise ValueError("Incomplete legacy effective Judge")
        entries[item["key"]] = {
            "effective_record": copied[effective]["path"],
            "sha256": copied[effective]["sha256"],
            "provenance_files": list(copied.values()),
            "origin_provenance": item,
            "case_id": item["case_id"],
        }
    index = {
        "schema": "ifbench-exact-canonical-judge-cache-v1",
        "config": config,
        "run_id": digest(config),
        "entries": entries,
        "source_provenance": evidence_copy(
            bundle, OLD / "judge_rejudge13_v1/analysis/PROVENANCE.json"
        ),
    }
    save(bundle / "cache/judge_index.json", index)
    return len(entries)


def prepare(bundle):
    bundle.mkdir(parents=True, exist_ok=True)
    if (bundle / "READY.json").exists():
        raise ValueError("Published package is immutable")
    selection = select_cases(bundle)  # must precede opening any outputs/scores
    save(
        bundle / "AUTHORIZATION.json",
        {
            "schema": SCHEMA,
            "user_instruction": "我确认，但我希望减少dev数量到20张图，加快速度。给我8卡入口指令，进行dev集评测。",
            "dev20_and_judge_authorized": True,
            "fixed_configuration_approved": True,
            "quality_search": False,
            "test_authorized": False,
            "freeze_authorized": False,
            "seed": 42,
            "one_sample_per_request": True,
        },
    )
    review = read(REVIEW / "FINAL_EVALUATION_METHODS.json")
    specs = {
        m: review["models"]["flux2_klein_9b" if m == "flux2_klein9b" else m]["specification"]
        for m in MODELS
    }
    current = read(OLD / "judge/current.json")
    config = read(current["config"])
    case_manifest = bundle / "repo/data/v2_2.6.0/cases.jsonl"
    copy_verified(REPO / "data/v2_2.6.0/cases.jsonl", case_manifest)
    helper_files = [
        "src/evaluation/protocol_audit/fairness_flux3_replan.py",
        "src/evaluation/protocol_audit/fairness_mirage_mice_probe.py",
        "src/evaluation/protocol_audit/fairness_qwen_flux2_smoke.py",
        "src/samtok_benchmark/ifbench/dev_judge.py",
        "src/samtok_benchmark/v2/judge.py",
        "src/samtok_benchmark/ifbench/judge_repair.py",
    ]
    plan = {
        "schema": SCHEMA,
        "seed": 42,
        "model_order": MODELS,
        "models": MODELS,
        "case_ids": selection["case_ids"],
        "settings": SETTINGS,
        "authorization_path": str(bundle / "AUTHORIZATION.json"),
        "authorization_sha256": sha256_file(bundle / "AUTHORIZATION.json"),
        "selection_path": str(bundle / "selection.json"),
        "selection_sha256": sha256_file(bundle / "selection.json"),
        "configuration_sha256": review["scientific_configuration_sha256"],
        "model_specifications": specs,
        "case_manifest": str(case_manifest),
        "case_manifest_sha256": sha256_file(case_manifest),
        "judge_config": config,
        "results_root": str(bundle / "results"),
        "cache_index": str(bundle / "cache/judge_index.json"),
        "helper_sha256": {f: sha256_file(REPO / f) for f in helper_files},
        "paths": {
            "sources": str(SOURCES),
            "models": str(PRETRAINED),
            "shared": str(SHARED),
            "replan_planner_weights": "/tmp/ifbench/weights/RePlan-Qwen2.5-VL-7B",
        },
        "test_authorized": False,
        "freeze_authorized": False,
        "quality_search": False,
        "tasks": [],
    }

    def prepare_task(model, cid, setting):
        request = request_for(model, cid, setting)
        path = bundle / "requests" / model / setting / cid / "request.json"
        save(path, request)
        public_path = SHARED / "requests" / setting / cid / "public.json"
        public = read(public_path)
        files = {public["source"]["path"]: public["source"]["sha256"]}
        inputs = read(public_path.with_name("inputs.json"))
        if inputs.get("annotation"):
            files[inputs["annotation"]["path"]] = inputs["annotation"]["sha256"]
        for unit in public["units"]:
            if unit["locator"] == "mask":
                files[unit["region"]["path"]] = unit["region"]["sha256"]
        if model == "replan":
            files[request["planner_template"]] = sha256_file(Path(request["planner_template"]))
        out = bundle / "results/runs" / model / "outputs" / setting / cid
        task = {
            "key": f"{model}/{setting}/{cid}",
            "task_id": f"{model}/{setting}/{cid}",
            "model": model,
            "case_id": cid,
            "setting": setting,
            "request_path": str(path),
            "request_sha256": sha256_file(path),
            "public_request": str(public_path),
            "public_digest": public["input_digest"],
            "output_dir": str(out),
            "result_path": str(out / "result.json"),
            "planner_dir": str(bundle / "results/runs" / model / "planners" / setting / cid),
            "input_files": files,
            "scientific_digest": request_identity(plan, model, request),
            "cache": {},
            "cache_sha256": {},
        }
        old_cache(bundle, plan, task, request)
        verify_task(plan, task)
        return task

    for model in MODELS:
        keys = [(model, cid, setting) for cid in selection["case_ids"] for setting in SETTINGS]
        with ThreadPoolExecutor(max_workers=8) as pool:
            plan["tasks"].extend(pool.map(lambda item: prepare_task(*item), keys))
        print(json.dumps({"prepared_model": model, "tasks": 200}), flush=True)
    nj = export_judge_cache(bundle, set(selection["case_ids"]), config)
    plan["cache_index_sha256"] = sha256_file(bundle / "cache/judge_index.json")
    plan["digest"] = digest(plan)
    save(bundle / "plan.json", plan)
    counts = Counter(t["model"] for t in plan["tasks"] if "edit" in t["cache"])
    save(
        bundle / "PREPARATION.json",
        {
            "logical_requests": 1400,
            "selection": selection,
            "exact_generation_cache_counts": dict(counts),
            "potential_historical_judge_keys": nj,
            "new_gpu_calls_during_preparation": 0,
        },
    )
    print(
        json.dumps(
            {
                "prepared": 1400,
                "cached_generation": dict(counts),
                "judge_cache_keys": nj,
                "plan_digest": plan["digest"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    prepare(parser.parse_args().bundle)
