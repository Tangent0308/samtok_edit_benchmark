"""Write-once plans binding the correction to the original public bytes."""

from collections import Counter
from pathlib import Path
import subprocess

from samtok_benchmark.external_full.worker import source_identity as frozen_source_identity
from samtok_benchmark.external_refedit.data import immutable, read, verify_public
from samtok_benchmark.io import digest, sha256_file
from . import VERSION
from .text import compile_instruction

MODEL_SOURCE = "/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/deps/sitedit-aa5a414"
LOCAL_RUNTIMES = {
    "pass1": "/tmp/ifbench/external_bench_20261102/env_pass1/bin/python",
    "v4": "/tmp/ifbench/external_bench_20261102/env_v4/bin/python",
    "metrics": "/tmp/ifbench/external_pilots_20261107/env_metrics/bin/python",
}


def source_identity():
    values = frozen_source_identity()
    root = Path(__file__).parents[2]
    for p in sorted(Path(__file__).parent.glob("*.py")):
        values[str(p.relative_to(root.parent))] = sha256_file(p)
    script = root.parents[1] / "scripts/compbench_multitarget.py"
    values["scripts/compbench_multitarget.py"] = sha256_file(script)
    return values


def prepare(package, control, results_root):
    package, control, results_root = map(
        lambda p: Path(p).resolve(), (package, control, results_root)
    )
    ready = read(package / "READY.json")
    config = read(package / "configuration.json")
    bundle = Path(ready["bundle"])
    index = read(bundle / "index.json")
    if index["digest"] != ready["bundle_digest"] or index["digest"] != digest(
        {k: v for k, v in index.items() if k != "digest"}
    ):
        raise ValueError("Original full input bundle changed")
    cases = []
    for row in index["cases"]:
        if row["task"] not in {"multi_object_add", "multi_object_remove"}:
            continue
        public = read(row["public"])
        verify_public(public)
        if sha256_file(row["public"]) != row["public_sha256"]:
            raise ValueError("Original public request changed")
        if public["instruction"] != row["instruction"] or row["turn"]:
            raise ValueError("Unexpected original multi-object request")
        cases.append(
            {
                "case_id": row["case_id"],
                "task": row["task"],
                "public": row["public"],
                "public_sha256": row["public_sha256"],
                "public_digest": public["input_digest"],
                "instruction": public["instruction"],
                **compile_instruction(public["instruction"]),
            }
        )
    if Counter(r["task"] for r in cases) != {"multi_object_add": 72, "multi_object_remove": 72}:
        raise ValueError("The complete 144-request correction cohort changed")
    native = [r["case_id"] for r in cases if r["mode"] == "native_enumeration"]
    if len(native) != 3:
        raise ValueError("User authorized three additional native enumeration calls")
    baseline = Path(ready["results_root"]) / "reports/run001/REPORT.json"
    if results_root == Path(ready["results_root"]) or results_root.is_relative_to(package):
        raise ValueError("Correction must not overwrite the original run or published package")
    plan = {
        "schema": VERSION,
        "cases": cases,
        "case_ids": [r["case_id"] for r in cases],
        "bundle": str(bundle),
        "bundle_digest": index["digest"],
        "original_package": str(package),
        "original_ready_sha256": sha256_file(package / "READY.json"),
        "original_source_commit": ready["source_commit"],
        "original_report": str(baseline),
        "original_report_sha256": sha256_file(baseline),
        "results_root": str(results_root),
        "source_identity": source_identity(),
        "source_commit": subprocess.check_output(
            ["git", "-C", str(Path(__file__).parents[4]), "rev-parse", "HEAD"], text=True
        ).strip(),
        "method_commit": "aa5a414",
        "native_enumeration_case_ids": native,
        "native_enumeration_authorization": "User explicitly approved 2026-11-10; same Pass1 model and LoRA",
        "paid_api_calls": 0,
        "generation_seed": 42,
        "policy": "All 144 multi-object requests; one joint Pass1 and one joint S2; no score-based search",
    }
    plan["digest"] = digest(plan)
    immutable(control / "PLAN.json", plan)
    config["benchmark"] = {
        **config["benchmark"],
        "multitarget_protocol": VERSION,
        "multitarget_plan": str(control / "PLAN.json"),
        "multitarget_plan_digest": plan["digest"],
    }
    config["runtime"].update(LOCAL_RUNTIMES)
    config["paths"]["sitedit_source"] = MODEL_SOURCE
    config["formal_results_root"] = str(results_root)
    immutable(control / "configuration.json", config)
    immutable(
        control / "SEAL.json",
        {
            "plan_digest": plan["digest"],
            "configuration_sha256": sha256_file(control / "configuration.json"),
        },
    )
    # Fixed syntax-coverage smoke, chosen without looking at any image output or score.
    smoke_ids = [
        "multi_object_add--06020d7aa7b841b1",  # coordinated targets, colour 'and'
        "multi_object_remove--0971987fcf12b618",  # explicit count
        "multi_object_remove--7a3b354f5c320aa1",  # native enumeration
    ]
    immutable(control / "SMOKE.json", {"case_ids": smoke_ids, "selection": "fixed syntax coverage"})
    lines = ["# 推理前冻结的逐条拆分", "", "只使用公开文本；不含 GT 或评分。", ""]
    for row in cases:
        lines += [f"## {row['case_id']}", "", row["instruction"], "", f"规则：`{row['rule']}`", ""]
        lines += [f"- U{i}: {unit}" for i, unit in enumerate(row["units"], 1)]
        if row["mode"] == "native_enumeration":
            lines.append("- 等待一次原生 Pass1 枚举；不能猜测 K。")
        lines.append("")
    path = control / "DECOMPOSITION.md"
    text = "\n".join(lines)
    if path.exists() and path.read_text() != text:
        raise ValueError("Existing decomposition audit differs")
    path.write_text(text)
    return plan


def load(control):
    control = Path(control).resolve()
    plan = read(control / "PLAN.json")
    if plan["schema"] != VERSION or plan["digest"] != digest(
        {k: v for k, v in plan.items() if k != "digest"}
    ):
        raise ValueError("Invalid correction plan")
    if plan["source_identity"] != source_identity():
        raise ValueError("Correction code changed after freezing")
    config = read(control / "configuration.json")
    seal = read(control / "SEAL.json")
    if seal != {
        "plan_digest": plan["digest"],
        "configuration_sha256": sha256_file(control / "configuration.json"),
    }:
        raise ValueError("Sealed configuration was changed")
    if config["benchmark"]["multitarget_plan_digest"] != plan["digest"]:
        raise ValueError("Configuration points to another decomposition plan")
    return plan, config
