"""Whitelist, verify and freeze the complete 144-case, five-method input cohort."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import subprocess

from .common import checked, digest, read, relative_path, save, sha
from .rubric import fingerprint

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
RESULTS = NAS / "experiments2/SAMTokEdit/external_compbench"
REPORT = RESULTS / "recovery9_20261110/reports/run001/MERGED_REPORT.json"
REPORT_SHA = "cc8b1a46eabef1b772d655600c691b23084bfb110a9387a4c11d889bc054f5c5"
OLD_BUNDLE = NAS / ".ifbench-tmp/compbench_full_20261107/bundle"
IFBENCH = NAS / ".ifbench-tmp/one-mp-full4-20261103-judgeio"
MODELS = ["sitedit", "qwen21", "replan", "mice", "flux2_klein9b"]
TASKS = ["multi_object_add", "multi_object_remove"]
SEED = 20261110


def smoke_cases(cases):
    return sorted(
        x["case_id"]
        for task in TASKS
        for x in sorted(
            (c for c in cases if c["task"] == task),
            key=lambda c: __import__("hashlib")
            .sha256(f"{SEED}:{c['case_id']}".encode())
            .hexdigest(),
        )[:2]
    )


def copy_checked(src, dst, expected):
    dst = Path(dst)
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        temporary = dst.with_suffix(dst.suffix + ".copying")
        shutil.copyfile(src, temporary)
        checked(temporary, expected)
        temporary.replace(dst)
    checked(dst, expected)


def prepare(bundle, results_root):
    bundle = Path(bundle).resolve()
    if (bundle / "READY.json").exists():
        raise ValueError("Published packages are immutable")
    checked(REPORT, REPORT_SHA)
    rows = [r for r in read(REPORT)["per_case"] if r["task"] in TASKS]
    private = {
        x["case_id"]: x for x in read(OLD_BUNDLE / "private/evaluation.json") if x["task"] in TASKS
    }
    assert len(private) == 144 and len(rows) == 720
    assert {r["model"] for r in rows} == set(MODELS)
    cases, copies = [], {}
    for cid, item in sorted(private.items()):
        public = read(OLD_BUNDLE / "public" / cid / "public.json")
        if public["instruction"] != item["instruction"]:
            raise ValueError(f"Public instruction differs: {cid}")
        src = item["canonical_source"]
        path = f"assets/source/{cid}.png"
        copies[path] = (src["path"], src["sha256"])
        cases.append(
            {
                "case_id": cid,
                "task": item["task"],
                "cluster": Path(item["image_path"]).stem.split("_")[0],
                "instruction": public["instruction"],
                "source": {"path": path, "sha256": src["sha256"], "size": src["size"]},
            }
        )
    case_map = {x["case_id"]: x for x in cases}

    def entry(row):
        record = Path(row["generation_record"])
        actual = read(record)
        if actual["status"] != "completed" or row["generation_status"] != "completed":
            raise ValueError(f"Generation not completed: {record}")
        if actual["identity"]["case_id"] != row["case_id"]:
            raise ValueError(f"Wrong generation case: {record}")
        if actual["identity"]["model"] != row["model"]:
            raise ValueError(f"Wrong generation model: {record}")
        cid, model = row["case_id"], row["model"]
        output = {"path": f"assets/output/{model}/{cid}.png", "sha256": actual["output_sha256"]}
        copy_checked(actual["output_image"], bundle / output["path"], output["sha256"])
        request = {k: case_map[cid][k] for k in ("instruction", "source")}
        request["output"] = output
        # Paths and method labels are excluded from inference and duplicate-cache identity.
        key = digest(
            {
                "source": request["source"]["sha256"],
                "output": output["sha256"],
                "instruction": request["instruction"],
                "rubric": fingerprint(),
            }
        )
        return {
            "model": model,
            "case_id": cid,
            "request_key": key,
            "generation_record": str(record),
            "generation_record_sha256": sha(record),
        }, request

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda p: copy_checked(p[1][0], bundle / p[0], p[1][1]), copies.items()))
        entries = list(pool.map(entry, rows))
    bindings, requests = [], {}
    for binding, request in entries:
        bindings.append(binding)
        requests.setdefault(binding["request_key"], request)
    assert len({(x["model"], x["case_id"]) for x in bindings}) == 720
    prior = read(IFBENCH / "configuration.json")["judge_config"]
    model = Path(prior["model"])
    descriptor = read(model / "download_record.json")
    assert descriptor["revision"] == prior["revision"]
    config_files = {
        p.name: sha(p)
        for p in model.iterdir()
        if p.is_file() and p.suffix in (".json", ".jinja", ".txt")
    }
    weights = {p.name: p.stat().st_size for p in model.glob("*.safetensors")}
    assert len(weights) == descriptor["shards"]
    config = {
        "rubric": fingerprint(),
        "model": str(model),
        "revision": prior["revision"],
        "model_config_sha256": config_files,
        "weight_bytes": weights,
        "packages": prior["packages"],
        "decode": prior["decode"],
        "engine": prior["engine"],
        "reference_ifbench_config_sha256": sha(IFBENCH / "configuration.json"),
    }
    plan = {
        "schema": "compbench.supplementary-plan.v1",
        "models": MODELS,
        "cases": cases,
        "bindings": sorted(bindings, key=lambda x: (x["case_id"], x["model"])),
        "requests": requests,
        "configuration": config,
        "source_report": str(REPORT),
        "source_report_sha256": REPORT_SHA,
        "results_root": str(Path(results_root).resolve()),
        "smoke_case_ids": smoke_cases(cases),
        "bootstrap": {"seed": SEED, "replicates": 10000, "cluster": "image_path scene prefix"},
        "runtime": read(IFBENCH / "bootstrap.json")["judge"],
    }
    plan["digest"] = digest(plan)
    save(bundle / "PLAN.json", plan, immutable=True)
    return {
        "plan_digest": plan["digest"],
        "bindings": len(bindings),
        "unique_requests": len(requests),
        "smoke_case_ids": plan["smoke_case_ids"],
    }


def load(bundle, verify_assets=True):
    bundle = Path(bundle)
    plan = read(bundle / "PLAN.json")
    if plan["digest"] != digest({k: v for k, v in plan.items() if k != "digest"}):
        raise ValueError("Plan digest changed")
    if plan["configuration"]["rubric"] != fingerprint():
        raise ValueError("Running rubric differs from frozen plan")
    if verify_assets:
        files = {
            v["path"]: v["sha256"]
            for r in plan["requests"].values()
            for v in (r["source"], r["output"])
        }
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda v: checked(relative_path(bundle, v[0]), v[1]), files.items()))
    return plan


def publish(bundle, repo):
    bundle, repo = Path(bundle).resolve(), Path(repo).resolve()
    if (bundle / "READY.json").exists():
        raise ValueError("Refusing to overwrite READY")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=repo).strip():
        raise ValueError("Commit all changes before publication")
    plan = load(bundle)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=repo).decode().split("\0")
    files = {}
    for name in tracked:
        if not (
            name.startswith("src/")
            or name == "scripts/compbench_supplementary_judge.py"
            or name == "docs/COMPBENCH_SUPPLEMENTARY_JUDGE.md"
            or name == "pyproject.toml"
        ):
            continue
        copy_checked(repo / name, bundle / "repo" / name, sha(repo / name))
        files["repo/" + name] = sha(repo / name)
    shell = """#!/usr/bin/env bash
set -euo pipefail
BUNDLE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
unset PYTHONHOME PYTHONPATH
exec /usr/bin/python3 -I "$BUNDLE/repo/scripts/compbench_supplementary_judge.py" launch --bundle "$BUNDLE" "$@"
"""
    (bundle / "start.sh").write_text(shell)
    (bundle / "start.sh").chmod(0o755)
    files["start.sh"] = sha(bundle / "start.sh")
    files["PLAN.json"] = sha(bundle / "PLAN.json")
    ready = {
        "schema": "compbench.supplementary-ready.v1",
        "source_commit": commit,
        "plan_digest": plan["digest"],
        "results_root": plan["results_root"],
        "files": files,
    }
    save(bundle / "READY.json", ready, immutable=True)
    return {"bundle": str(bundle), "ready_sha256": sha(bundle / "READY.json"), **ready}
