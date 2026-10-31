"""Canonical, single-source diagnosis of the fixed 1MP setting-coverage probe.

Two immutable generation plans supply 21 + 49 logical requests. Their records
keep their original plan identities; only canonical output keys are deduplicated.
This is a one-image diagnostic, never a population estimate or formal test.
"""

from __future__ import annotations

import argparse
from collections import Counter
import fcntl
from itertools import groupby
import json
import os
from pathlib import Path
import signal
import socket
import time
from types import SimpleNamespace

from samtok_benchmark.io import digest, read_jsonl, sha256_file, write_json
from samtok_benchmark.paths import repository_root
from . import dev_judge as canonical
from . import fairness_dev_judge as judge
from .fairness_dev_plan import MODELS, SETTINGS, check_hash
from .prepare_one_mp import PROBE_SETTINGS

SCHEMA = "ifbench-1mp-single-source-judge-v1"
CASE_ID = "v2-sa_8415518"
SCOPE = "single-source-setting-diagnostic"
SOURCE_SETTINGS = {
    "probe": PROBE_SETTINGS,
    "coverage": [setting for setting in SETTINGS if setting not in PROBE_SETTINGS],
}
ENGINE = {
    "tensor_parallel_size": 8,
    "expert_parallel": True,
    "max_model_len": 49152,
    "batch_size": 16,
    "gpu_memory_utilization": 0.85,
}
TERMINAL_GENERATION = judge.FAILURES | {"generated"}


def helper_hashes():
    """Bind this controller and the unchanged scientific/verification helpers."""
    root = repository_root()
    relative = [
        "src/samtok_benchmark/io.py",
        "src/samtok_benchmark/paths.py",
        "src/samtok_benchmark/v2/judge.py",
        "src/samtok_benchmark/v2/evaluation.py",
        "src/samtok_benchmark/v2/inputs.py",
        *[
            f"src/samtok_benchmark/ifbench/{name}.py"
            for name in (
                "one_mp_judge",
                "fairness_dev_judge",
                "dev_judge",
                "dev_judge_stream",
                "judge_repair",
                "fairness_dev_plan",
                "one_mp_probe",
                "one_mp_coverage",
                "prepare_one_mp",
                "canvas",
                "public",
            )
        ],
    ]
    return {name: sha256_file(root / name) for name in relative}


def source_context(name, source):
    """Verify an original plan against its own archived helper snapshot."""
    from .one_mp_coverage import load_plan as load_coverage
    from .one_mp_probe import load_plan as load_probe

    path = Path(source["path"]).resolve()
    check_hash(path, source["sha256"])
    helper_root = Path(source["helper_root"]).resolve()
    if helper_root != path.parent / "repo":
        raise ValueError("Source helpers must come from that plan's frozen repo snapshot")
    loader = {"probe": load_probe, "coverage": load_coverage}[name]
    plan = loader(path, helper_root=helper_root)
    if plan["digest"] != source["digest"]:
        raise ValueError("Original generation plan digest changed")
    if plan["model_order"] != MODELS or plan["settings"] != SOURCE_SETTINGS[name]:
        raise ValueError("Source has different fixed models/settings")
    if CASE_ID not in plan["case_ids"]:
        raise ValueError("Source does not contain the fixed K5 dev image")
    tasks = [task for task in plan["tasks"] if task["case_id"] == CASE_ID]
    expected = {
        f"{model}/{setting}/{CASE_ID}" for model in MODELS for setting in SOURCE_SETTINGS[name]
    }
    if len(tasks) != len(expected) or {task["key"] for task in tasks} != expected:
        raise ValueError("Source does not cover its exact authorized diagnostic requests")
    manifest = judge.resolve(plan["case_manifest"], path.parent)
    check_hash(manifest, plan["case_manifest_sha256"])
    selected = [case for case in read_jsonl(manifest) if case["id"] == CASE_ID]
    if len(selected) != 1 or len(selected[0]["units"]) != 5:
        raise ValueError("Diagnostic needs the single fixed canonical K5 case")
    return {
        "plan": plan,
        "plan_path": path,
        "plan_sha256": source["sha256"],
        "base": path.parent,
        "tasks": tasks,
        "cases": {CASE_ID: selected[0]},
        "case_ids": [CASE_ID],
        "order": MODELS,
        "config": plan["judge_config"],
    }


def validate_sources(sources):
    if set(sources) != {"probe", "coverage"}:
        raise ValueError("Exactly the original probe and new coverage sources are required")
    contexts = {name: source_context(name, sources[name]) for name in SOURCE_SETTINGS}
    probe, coverage = contexts["probe"], contexts["coverage"]
    origin = coverage["plan"]["probe_origin"]
    if (
        Path(origin["path"]).resolve() != probe["plan_path"]
        or origin["sha256"] != probe["plan_sha256"]
    ):
        raise ValueError("Coverage was not prepared from this exact original probe")
    for name in ("judge_config", "configuration_sha256", "case_manifest_sha256"):
        if probe["plan"][name] != coverage["plan"][name]:
            raise ValueError(f"Source scientific identity differs: {name}")
    if probe["cases"] != coverage["cases"]:
        raise ValueError("Source canonical case records differ")
    config = probe["config"]
    if sha256_file(Path(canonical.__file__)) != config["source_sha256"]:
        raise ValueError("Canonical evaluator bytes changed")
    if (
        digest([canonical.RUBRIC, canonical.VIEWS_NOTE, canonical.OUTPUT_FORMAT])
        != config["prompt_digest"]
    ):
        raise ValueError("Canonical rubric changed")
    if config["engine"] != ENGINE:
        raise ValueError("Judge requires the unchanged TP8/EP batch16 engine")
    for context in contexts.values():
        dataset = judge.resolve(
            context["plan"].get("dataset_root", str(canonical.DATA)), context["base"]
        )
        if dataset.resolve() != canonical.DATA.resolve():
            raise ValueError("Canonical dataset mount changed")
    case = probe["cases"][CASE_ID]
    assets = [(case["source"]["image"], case["source"]["sha256"])]
    assets += [(unit["target"]["mask"], unit["target"]["mask_sha256"]) for unit in case["units"]]
    for relative, expected in assets:
        check_hash(canonical.DATA / relative, expected)
    return contexts


def task_references(contexts):
    references = {}
    for name, context in contexts.items():
        for task in context["tasks"]:
            if task["key"] in references:
                raise ValueError("Original and coverage tasks overlap; no resampling is allowed")
            references[task["key"]] = {
                "key": task["key"],
                "source": name,
                "model": task["model"],
                "setting": task["setting"],
                "case_id": task["case_id"],
                "scientific_digest": task["scientific_digest"],
                "request_sha256": task["request_sha256"],
            }
    expected = [f"{model}/{setting}/{CASE_ID}" for model in MODELS for setting in SETTINGS]
    if set(references) != set(expected):
        raise ValueError("Diagnostic must cover exactly seven models by ten settings")
    return [references[key] for key in expected]


def prepare(bundle, probe_plan, coverage_plan, *, cache_index=None):
    """Freeze a read-only view; generation may still be in progress."""
    bundle = Path(bundle).resolve()
    sources = {}
    for name, path in (("probe", probe_plan), ("coverage", coverage_plan)):
        path = Path(path).resolve()
        if bundle.is_relative_to(path.parent) or path.parent.is_relative_to(bundle):
            raise ValueError("Judge bundle must be separate from both generation bundles")
        sources[name] = {
            "path": str(path),
            "sha256": sha256_file(path),
            "digest": judge.read(path)["digest"],
            "helper_root": str(path.parent / "repo"),
        }
    contexts = validate_sources(sources)
    configuration = contexts["probe"]["config"]
    coverage = contexts["coverage"]["plan"]
    plan = {
        "schema": SCHEMA,
        "scope": SCOPE,
        "case_ids": [CASE_ID],
        "model_order": MODELS,
        "settings": SETTINGS,
        "sources": sources,
        "tasks": task_references(contexts),
        "judge_config": configuration,
        "seed": 42,
        "quality_search": False,
        "formal_test": False,
        "population_estimate": False,
        "results_root": str(bundle / "results"),
        "authorization_path": coverage["authorization_path"],
        "authorization_sha256": coverage["authorization_sha256"],
        "case_manifest_sha256": contexts["probe"]["plan"]["case_manifest_sha256"],
        "helper_sha256": helper_hashes(),
        "cache_index": str(Path(cache_index).resolve()) if cache_index else None,
        "cache_index_sha256": sha256_file(Path(cache_index)) if cache_index else None,
    }
    if cache_index:
        judge.Cache(cache_index, configuration)
    plan["digest"] = digest(plan)
    bundle.mkdir(parents=True, exist_ok=True)
    with (bundle / "prepare.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        judge.immutable(bundle / "plan.json", plan)
    return plan


def load_plan(path, *, helper_root=None):
    path = Path(path).resolve()
    plan = judge.read(path)
    if plan.get("schema") != SCHEMA or plan.get("digest") != digest(
        {key: value for key, value in plan.items() if key != "digest"}
    ):
        raise ValueError("Invalid single-source diagnostic plan/digest")
    fixed = {
        "scope": SCOPE,
        "case_ids": [CASE_ID],
        "model_order": MODELS,
        "settings": SETTINGS,
        "seed": 42,
        "quality_search": False,
        "formal_test": False,
        "population_estimate": False,
        "results_root": str(path.parent / "results"),
    }
    if any(plan.get(key) != value for key, value in fixed.items()):
        raise ValueError("Single-source diagnostic scope changed")
    root = Path(helper_root) if helper_root else repository_root()
    if set(plan["helper_sha256"]) != set(helper_hashes()):
        raise ValueError("Diagnostic helper dependency set changed")
    for relative, expected in plan["helper_sha256"].items():
        check_hash(root / relative, expected)
    contexts = validate_sources(plan["sources"])
    coverage = contexts["coverage"]["plan"]
    for key in ("authorization_path", "authorization_sha256"):
        if plan[key] != coverage[key]:
            raise ValueError("Diagnostic authorization is not the approved coverage authorization")
    if (
        plan["judge_config"] != contexts["probe"]["config"]
        or plan["case_manifest_sha256"] != contexts["probe"]["plan"]["case_manifest_sha256"]
        or plan["tasks"] != task_references(contexts)
    ):
        raise ValueError("Diagnostic source/task/configuration binding changed")
    if plan["cache_index"]:
        check_hash(plan["cache_index"], plan["cache_index_sha256"])
    elif plan["cache_index_sha256"] is not None:
        raise ValueError("Unbound Judge cache SHA")
    return {
        "plan": plan,
        "plan_path": path,
        "plan_sha256": sha256_file(path),
        "base": path.parent,
        "root": Path(plan["results_root"]),
        "order": MODELS,
        "case_ids": [CASE_ID],
        "cases": contexts["probe"]["cases"],
        "config": plan["judge_config"],
        "run_id": digest(plan["judge_config"]),
        "source_contexts": contexts,
        "full_release": False,
    }


def collect(context):
    """Retain original plan bindings and merge only identical canonical keys."""
    by_logical, candidates = {}, {}
    for source, original in context["source_contexts"].items():
        bindings, source_jobs = judge.collect(original)
        for bound in bindings:
            if bound["key"] in by_logical:
                raise ValueError("Duplicate logical request across generation sources")
            if bound["generation_status"] not in TERMINAL_GENERATION | {"pending"}:
                raise ValueError("Unknown generation status or unregistered N/A")
            by_logical[bound["key"]] = {
                **bound,
                "generation_source": source,
                "source_plan_sha256": original["plan_sha256"],
                "source_plan_digest": original["plan"]["digest"],
            }
            if bound["judge_key"]:
                candidates[bound["key"]] = source_jobs[bound["judge_key"]]
    expected = [task["key"] for task in context["plan"]["tasks"]]
    if set(by_logical) != set(expected):
        raise ValueError("Generated binding scope differs from the frozen 70-task view")
    bindings, jobs = [], {}
    for logical in expected:
        bound = by_logical[logical]
        bindings.append(bound)
        key = bound["judge_key"]
        if key:
            candidate = candidates[logical]
            if key not in jobs:
                jobs[key] = {
                    **candidate,
                    "model": bound["model"],
                    "logical_keys": [],
                }
            elif (
                jobs[key]["case"] != candidate["case"]
                or jobs[key]["record"]["output_sha256"] != candidate["record"]["output_sha256"]
            ):
                raise ValueError("Conflicting canonical key collision")
            jobs[key]["logical_keys"].append(logical)
    return bindings, jobs


def verify_records(context, jobs, cache):
    judge.verify_admissions(context, jobs)
    _, _, effectives, _ = judge.paths(context)
    if {path.stem for path in effectives.glob("*.json")} - set(jobs):
        raise ValueError("Unregistered effective Judge answer")
    for key, job in jobs.items():
        path = effectives / f"{key}.json"
        if path.exists():
            value = judge.read(path)
            if value.get("status") not in {"scored", "judge-failed"}:
                raise ValueError("Unknown effective Judge terminal status")
            judge.verify_effective(value, job, context, cache)


def diagnostic(context, bindings, jobs, cache):
    """Auditable report interface; failed Judge answers remain missing, never zero."""
    verify_records(context, jobs, cache)
    directory, raws, effectives, _ = judge.paths(context)
    keys, rows = {}, []
    for key, job in jobs.items():
        effective_path, raw_path = effectives / f"{key}.json", raws / f"{key}.json"
        value = judge.read(effective_path) if effective_path.exists() else None
        keys[key] = {
            "key": key,
            "representative_model": job["model"],
            "logical_keys": job["logical_keys"],
            "output_sha256": job["record"]["output_sha256"],
            "status": value["status"] if value else "judge-pending",
            "scores": value.get("scores") if value else None,
            "raw_record": str(raw_path) if raw_path.exists() else None,
            "raw_sha256": sha256_file(raw_path) if raw_path.exists() else None,
            "effective_record": str(effective_path) if value else None,
            "effective_sha256": sha256_file(effective_path) if value else None,
            "new_judge_calls": value.get("new_judge_calls", 0) if value else 0,
            "deterministic_repair_used": value.get("deterministic_repair_used", False)
            if value
            else False,
            "cache_reuse": value.get("cache_reuse") if value else None,
            "failure_reason": value.get("repair_reason", value.get("reason")) if value else None,
        }
    for bound in bindings:
        result = keys.get(bound["judge_key"])
        failed = bound["generation_status"] in judge.FAILURES
        status = result["status"] if result else bound["generation_status"]
        unit_pass = joint_pass = None
        if failed:
            unit_pass = joint_pass = 0
        elif result and result["status"] == "scored":
            scores = result["scores"]
            unit_pass = sum(all(unit[d]["pass"] for d in "EPQ") for unit in scores["units"])
            joint_pass = int(unit_pass == 5 and all(scores[f"global_{d}"]["pass"] for d in "PQ"))
        rows.append(
            {
                **bound,
                "judge_status": status,
                "scores": result["scores"] if result else None,
                "unit_pass_numerator": unit_pass,
                "unit_denominator": 5,
                "joint_pass_numerator": joint_pass,
                "case_denominator": 1,
                "UnitPass": unit_pass / 5 if unit_pass is not None else None,
                "JointPass": joint_pass,
                "judge_missing": unit_pass is None,
                "unit_pass_count": unit_pass,
                "unit_count": 5,
                "joint_pass": bool(joint_pass) if joint_pass is not None else None,
                "effective_path": result["effective_record"] if result else None,
                "effective_sha256": result["effective_sha256"] if result else None,
                "raw_path": result["raw_record"] if result else None,
                "raw_sha256": result["raw_sha256"] if result else None,
            }
        )
    progress = judge.progress(context, bindings, jobs)
    terminal = all(bound["generation_status"] in TERMINAL_GENERATION for bound in bindings)
    all_attempts_terminal = terminal and all(
        row["status"] != "judge-pending" for row in keys.values()
    )
    value = {
        **progress,
        "schema": SCHEMA,
        "scope": SCOPE,
        "case_ids": [CASE_ID],
        "settings": SETTINGS,
        "model_order": MODELS,
        "population_estimate": False,
        "formal_test": False,
        "diagnostic_inputs_frozen": True,
        "confidence_intervals": None,
        "interpretation": "One fixed K5 image only; no population CI, ranking, or method selection.",
        "all_generation_terminal": terminal,
        "all_judge_attempts_terminal": all_attempts_terminal,
        "ready_for_report": all_attempts_terminal,
        "all_generated_outputs_scored": terminal
        and all(row["status"] == "scored" for row in keys.values()),
        "generation_counts": dict(Counter(row["generation_status"] for row in bindings)),
        "logical_judge_counts": dict(Counter(row["judge_status"] for row in rows)),
        "source_logical_counts": dict(Counter(row["generation_source"] for row in bindings)),
        "logical_bindings": rows,
        "unique_records": keys,
        "execution_receipts": [
            {"path": str(path), "sha256": sha256_file(path), "receipt": judge.read(path)}
            for path in sorted((directory / "executions").glob("*/receipt.json"))
        ],
        "no_automatic_retries": True,
        "generation_failures_in_denominator": True,
        "judge_failure_policy": "missing, never zero",
    }
    write_json(
        directory / "progress.json",
        {key: value[key] for key in progress}
        | {
            "scope": SCOPE,
            "diagnostic_inputs_frozen": True,
            "formal_test": False,
        },
    )
    write_json(context["root"] / "DIAGNOSTIC.json", value)
    write_json(
        context["root"] / "REPORT.json",
        {
            "schema": SCHEMA,
            "scope": SCOPE,
            "case_ids": [CASE_ID],
            "model_order": MODELS,
            "settings": SETTINGS,
            "plan_sha256": context["plan_sha256"],
            "run_id": context["run_id"],
            "ready_for_report": all_attempts_terminal,
            "all_generated_outputs_scored": value["all_generated_outputs_scored"],
            "population_estimate": False,
            "formal_test": False,
            "confidence_intervals": None,
            "rows": rows,
            "summary": {
                **{
                    key: progress[key]
                    for key in (
                        "logical_requests",
                        "unique_generated_keys",
                        "new_admitted_calls",
                        "new_raw_answers",
                        "reused_effective_keys",
                        "deterministic_repairs",
                    )
                },
                "scored_logical": sum(row["judge_status"] == "scored" for row in rows),
                "judge_failed_logical": sum(row["judge_status"] == "judge-failed" for row in rows),
                "judge_pending_logical": sum(
                    row["judge_status"] == "judge-pending" for row in rows
                ),
                "generation_failed_logical": sum(
                    row["generation_status"] in judge.FAILURES for row in rows
                ),
                "generation_pending_logical": sum(
                    row["generation_status"] == "pending" for row in rows
                ),
                "missing_logical": sum(row["judge_missing"] for row in rows),
                "unique_effective_statuses": progress["effective_statuses"],
                "source_logical_counts": value["source_logical_counts"],
            },
            "diagnostic_path": str(context["root"] / "DIAGNOSTIC.json"),
            "diagnostic_sha256": sha256_file(context["root"] / "DIAGNOSTIC.json"),
            "interpretation": value["interpretation"],
        },
    )
    if all_attempts_terminal:
        write_json(
            context["root"] / "COMPLETED.json",
            {
                "scope": SCOPE,
                "plan_sha256": context["plan_sha256"],
                "logical_requests": len(bindings),
                "unique_judge_keys": len(jobs),
                "all_generated_outputs_scored": value["all_generated_outputs_scored"],
                "report_sha256": sha256_file(context["root"] / "DIAGNOSTIC.json"),
                "summary_report_sha256": sha256_file(context["root"] / "REPORT.json"),
                "formal_test": False,
            },
        )
    return value


def execute_pending(context, bindings, jobs, cache, pending):
    """Use unchanged canonical Backend/scored/evidence and the fixed native batch budget."""
    if canonical.fingerprint() != context["config"]:
        raise ValueError("Actual Judge runtime/checkpoint fingerprint differs from the original")
    directory, raws, effectives, admitted = judge.paths(context)
    execution = directory / "executions" / f"{time.time_ns()}-{os.getpid()}"
    execution.mkdir(parents=True, exist_ok=False)
    receipt = {
        "status": "loading",
        "started_at": time.time(),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "run_id": context["run_id"],
        "plan_sha256": context["plan_sha256"],
        "config": context["config"],
        "source_sha256": sha256_file(Path(__file__)),
        "canonical_sha256": sha256_file(Path(canonical.__file__)),
        "repair_policy": judge.POLICY,
        "scope": SCOPE,
        "frozen": True,
        "diagnostic_inputs_frozen": True,
        "formal_test": False,
        "test_started": False,
        "population_estimate": False,
        "new_admitted_calls": 0,
        "new_raw_answers": 0,
        "calibration_calls": 0,
        "editor_calls": 0,
        "scheduling": "model serial; original batch16; four CPU evidence workers; at most two prefetched batches",
    }
    write_json(execution / "receipt.json", receipt)
    stop = [False]
    previous_handler = signal.signal(signal.SIGUSR1, lambda *_: stop.__setitem__(0, True))
    try:
        args = SimpleNamespace(
            model=canonical.MODEL, **context["config"]["engine"], **context["config"]["decode"]
        )
        backend = canonical.Backend(args, 22)
        receipt["status"] = "running"
        write_json(execution / "receipt.json", receipt)
        for model, grouped in groupby(pending, key=lambda job: job["model"]):
            items = [(job["key"], (job["case"], job["record"])) for job in grouped]
            for batch, conversations in judge.prefetched_batches(
                items,
                lambda item: canonical.evidence(item[1][0], item[1][1]["output_image"]),
                size=16,
                workers=4,
            ):
                if stop[0]:
                    break
                for key, (case, record) in batch:
                    judge.immutable(
                        admitted / f"{key}.json",
                        {
                            "key": key,
                            "model": model,
                            "case_id": case["id"],
                            "output_sha256": record["output_sha256"],
                            "canonical_prompt_digest": digest(canonical.prompt(case)),
                            "at": time.time(),
                            "execution": str(execution),
                            "attempt": 1,
                        },
                    )
                    receipt["new_admitted_calls"] += 1
                write_json(execution / "receipt.json", receipt)
                tick = time.monotonic()
                answers = backend.generate(conversations)
                elapsed = time.monotonic() - tick
                if len(answers) != len(batch):
                    raise RuntimeError("Judge answer count differs; admissions retained, no retry")
                for item, answer in zip(batch, answers, strict=True):
                    key, (case, _) = item
                    raw = judge.scored(item, answer, context["run_id"])
                    raw.update(
                        model=model,
                        case_id=case["id"],
                        completed_at=time.time(),
                        batch_size=len(batch),
                        batch_wall_seconds=elapsed,
                        execution_receipt=str(execution / "receipt.json"),
                        new_judge_calls=1,
                    )
                    raw_path = raws / f"{key}.json"
                    judge.immutable(raw_path, raw)
                    judge.immutable(
                        effectives / f"{key}.json",
                        judge.effective(
                            raw,
                            [unit["id"] for unit in case["units"]],
                            raw_path,
                        ),
                    )
                    receipt["new_raw_answers"] += 1
                write_json(execution / "receipt.json", receipt)
                print(json.dumps(judge.progress(context, bindings, jobs)), flush=True)
            if stop[0]:
                break
            write_json(
                directory / "model_completed" / f"{model}.json",
                {
                    "model": model,
                    "at": time.time(),
                    "judge_attempts_terminal": True,
                    "scope": SCOPE,
                },
            )
        receipt.update(status="drained" if stop[0] else "completed", ended_at=time.time())
        write_json(execution / "receipt.json", receipt)
    except BaseException as exc:
        receipt.update(status="error", error=repr(exc), ended_at=time.time())
        write_json(execution / "receipt.json", receipt)
        raise
    finally:
        signal.signal(signal.SIGUSR1, previous_handler)
    return diagnostic(context, bindings, jobs, cache)


def run(plan, *, dry_run=False, verify_only=False):
    context = load_plan(plan)
    directory, _, effectives, _ = judge.paths(context)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        judge.immutable(directory / "config.json", context["config"])
        judge.immutable(
            directory / "plan_binding.json",
            {
                "plan_sha256": context["plan_sha256"],
                "run_id": context["run_id"],
                "model_order": MODELS,
                "scope": SCOPE,
            },
        )
        cache = judge.Cache(context["plan"]["cache_index"], context["config"])
        bindings, jobs = collect(context)
        terminal = all(bound["generation_status"] in TERMINAL_GENERATION for bound in bindings)
        if terminal:
            judge.immutable(directory / "bindings.json", bindings)
        else:
            write_json(directory / "bindings.pending.json", bindings)
        verify_records(context, jobs, cache)
        judge.restore_and_cache(context, jobs, cache)
        value = diagnostic(context, bindings, jobs, cache)
        pending = [job for key, job in jobs.items() if not (effectives / f"{key}.json").exists()]
        if dry_run:
            for job in pending:
                canonical.evidence(job["case"], job["record"]["output_image"])
            write_json(
                directory / "dry_run.json",
                {
                    "eligible_unique_jobs": len(pending),
                    "runtime_fingerprint_checked": False,
                    "new_judge_calls": 0,
                    "all_generation_terminal": terminal,
                    "scope": SCOPE,
                },
            )
            return value
        if verify_only:
            return value
        if not terminal:
            raise RuntimeError("All 70 generation requests must be terminal before loading Judge")
        if not pending:
            return value
        return execute_pending(context, bindings, jobs, cache, pending)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "run", "verify"])
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--probe-plan", type=Path)
    parser.add_argument("--coverage-plan", type=Path)
    parser.add_argument("--cache-index", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.action == "prepare":
        if not all((args.bundle, args.probe_plan, args.coverage_plan)):
            parser.error("prepare requires --bundle, --probe-plan and --coverage-plan")
        result = prepare(
            args.bundle, args.probe_plan, args.coverage_plan, cache_index=args.cache_index
        )
        result = {
            "plan": str(args.bundle.resolve() / "plan.json"),
            "digest": result["digest"],
            "logical_requests": len(result["tasks"]),
            "new_judge_calls": 0,
        }
    else:
        if args.plan is None:
            parser.error("run/verify requires --plan")
        result = run(args.plan, dry_run=args.dry_run, verify_only=args.action == "verify")
        result = {
            key: value
            for key, value in result.items()
            if key not in {"logical_bindings", "unique_records", "execution_receipts"}
        }
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
