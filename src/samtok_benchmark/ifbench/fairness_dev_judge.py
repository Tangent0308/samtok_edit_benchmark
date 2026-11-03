"""Portable canonical Judge for one fixed fairness configuration, dev only.

Raw answers are immutable; deterministic repair has a separate overlay. Cache
reuse requires the exact canonical binding including output SHA and fingerprint.
Admission without a terminal answer is never automatically resubmitted.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import fcntl
from itertools import groupby
import json
import os
from pathlib import Path
import signal
import socket
import time
from types import SimpleNamespace

from PIL import Image

from samtok_benchmark.io import digest, read_jsonl, sha256_file, write_json
from . import dev_judge as canonical
from .dev_judge_stream import prefetched_batches, scored
from .judge_repair import recover, POLICY

FAILURES = {"failed", "failed-planner", "failed-component", "failed-interrupted"}
IO_WORKERS = 16


def read(path):
    return json.loads(Path(path).read_text())


def resolve(path, base):
    path = Path(path)
    return path if path.is_absolute() else Path(base) / path


def immutable(path, value):
    """Caller holds the single-controller lock; a matching artifact is reusable."""
    path = Path(path)
    if path.exists():
        if read(path) != value:
            raise ValueError(f"Immutable artifact differs: {path}")
        return
    write_json(path, value)


def validate_scores(scores, unit_ids):
    if [unit["id"] for unit in scores["units"]] != list(unit_ids):
        raise ValueError("Judge unit IDs/count/order differ from canonical case")
    blocks = [(d, unit[d]) for unit in scores["units"] for d in "EPQ"]
    blocks += [(d, scores["global_" + d]) for d in "PQ"]
    for dimension, block in blocks:
        value = block.get("score")
        expected = value == 4 if dimension == "E" else isinstance(value, int) and value >= 3
        if type(value) is not int or not 0 <= value <= 4:
            raise ValueError("Invalid numeric Judge score")
        if type(block.get("pass")) is not bool or block["pass"] != expected:
            raise ValueError("Judge pass differs from the fixed threshold")
        if not isinstance(block.get("evidence"), str) or not block["evidence"].strip():
            raise ValueError("Judge evidence is missing")


def effective(raw, unit_ids, raw_path):
    value = dict(raw)
    value.update(
        raw_record_path=str(raw_path),
        raw_record_sha256=sha256_file(Path(raw_path)),
        repair_policy=POLICY,
        repair_inference_calls=0,
        deterministic_repair_used=False,
    )
    if raw["status"] == "judge-failed" and raw["raw_response"].get("finish_reason") == "stop":
        try:
            scores, audit = recover(raw["raw_response"]["text"], unit_ids)
            value.update(
                status="scored",
                scores=scores,
                repair_audit=audit,
                deterministic_repair_used=True,
                original_parse_reason=raw.get("reason"),
            )
            value.pop("reason", None)
        except (ValueError, KeyError, TypeError) as exc:
            value["repair_reason"] = str(exc)
    if value["status"] == "scored":
        validate_scores(value["scores"], unit_ids)
    return value


def load_plan(path, root=None, *, helper_root=None, node_id=None, io_workers=IO_WORKERS):
    path = Path(path).resolve()
    full = read(path).get("schema") == "ifbench-full-release-four-node-v1"
    if full:
        from .full_plan import load_plan as verify_plan
    else:
        from .fairness_dev_plan import load_plan as verify_plan
        if node_id is not None:
            raise ValueError("Node selector requires an authorized whole-release plan")

    plan = verify_plan(path) if helper_root is None else verify_plan(path, helper_root=helper_root)
    base = path.parent
    if not full and (plan.get("test_authorized") or plan.get("test_started") or plan.get("formal_test")):
        raise ValueError("This runner is dev-only")
    case_ids = plan.get("case_ids", plan.get("cases"))
    order = plan.get("model_order", plan.get("models"))
    if isinstance(order, dict):
        order = list(order)
    if not isinstance(order, list) or len(order) != len(set(order)):
        raise ValueError("Explicit unique model order is required")
    if len(case_ids) != len(set(case_ids)) or (not full and len(case_ids) != 20):
        raise ValueError("The authorized fixed dev sample must contain 20 unique source images")
    tasks = plan["tasks"]
    expected = {(m, s, c) for m in order for s in plan["settings"] for c in case_ids}
    if {(t["model"], t["setting"], t["case_id"]) for t in tasks} != expected or len(tasks) != len(
        expected
    ):
        raise ValueError("Tasks must cover the exact model × setting × case Cartesian product")
    if len({t["key"] for t in tasks}) != len(tasks):
        raise ValueError("Task keys are not unique")
    manifest = resolve(plan["case_manifest"], base)
    if sha256_file(manifest) != plan["case_manifest_sha256"]:
        raise ValueError("Case manifest changed")
    cases = {c["id"]: c for c in read_jsonl(manifest) if c["id"] in set(case_ids)}
    if set(cases) != set(case_ids):
        raise ValueError("Case manifest does not contain every registered dev image")
    if plan.get("split_path"):
        split_path = resolve(plan["split_path"], base)
        if plan.get("split_sha256") and sha256_file(split_path) != plan["split_sha256"]:
            raise ValueError("Split artifact changed")
        split = read(split_path)
        if not set(case_ids) <= set(split["dev"]) or set(case_ids) & set(split["test"]):
            raise ValueError("Selected images are not wholly within the fixed dev split")
    config = plan["judge_config"]
    if isinstance(config, str):
        config = read(resolve(config, base))
    if sha256_file(Path(canonical.__file__)) != config["source_sha256"]:
        raise ValueError("Canonical source differs from the original fingerprint")
    if (
        digest([canonical.RUBRIC, canonical.VIEWS_NOTE, canonical.OUTPUT_FORMAT])
        != config["prompt_digest"]
    ):
        raise ValueError("Canonical rubric/prompt changed")
    if config["engine"] != {
        "tensor_parallel_size": 8,
        "expert_parallel": True,
        "max_model_len": 49152,
        "batch_size": 16,
        "gpu_memory_utilization": 0.85,
    }:
        raise ValueError("Judge engine differs from original eight-card batch16 configuration")
    dataset_root = resolve(plan.get("dataset_root", str(canonical.DATA)), base)
    if dataset_root.resolve() != canonical.DATA.resolve():
        raise ValueError(
            "Canonical dataset mount must retain its original path; do not rewrite the canonical evaluator"
        )
    assets = {}
    for case in cases.values():
        references = [(case["source"]["image"], case["source"]["sha256"])]
        references.extend((u["target"]["mask"], u["target"]["mask_sha256"]) for u in case["units"])
        for relative, expected_sha in references:
            if relative in assets and assets[relative] != expected_sha:
                raise ValueError(f"Conflicting canonical asset hashes: {relative}")
            assets[relative] = expected_sha

    def check_asset(item):
        relative, expected_sha = item
        if sha256_file(dataset_root / relative) != expected_sha:
            raise ValueError(f"Canonical source/mask asset changed: {relative}")

    with ThreadPoolExecutor(max_workers=io_workers) as pool:
        list(pool.map(check_asset, assets.items()))
    if node_id is not None:
        from .full_plan import node_tasks
        selected = node_tasks(plan, node_id)
        case_ids = [cid for cid in case_ids if cid in set(plan["node_assignments"][str(node_id)])]
        cases = {cid: cases[cid] for cid in case_ids}
        root = root or Path(plan["results_root"]) / "nodes" / f"node-{node_id}"
    else:
        selected = tasks
    context = {
        "full_release": full,
        "node_id": node_id,
        "tasks": selected,
        "plan": plan,
        "plan_path": path,
        "plan_sha256": sha256_file(path),
        "base": base,
        "root": Path(root).resolve()
        if root
        else resolve(plan.get("results_root", plan.get("run_root", ".")), base).resolve(),
        "case_ids": case_ids,
        "order": order,
        "cases": cases,
        "config": config,
        "run_id": digest(config),
    }
    return context


def normalized_tasks(context):
    order = {key: i for i, key in enumerate(context["order"])}
    settings = {key: i for i, key in enumerate(context["plan"]["settings"])}
    cases = {key: i for i, key in enumerate(context["case_ids"])}
    for task in sorted(
        context.get("tasks", context["plan"]["tasks"]),
        key=lambda t: (
            order[t["model"]],
            settings[t["setting"]],
            cases[t["case_id"]],
        ),
    ):
        yield {
            **task,
            "result_path": str(resolve(task["result_path"], context["base"])),
            "request_path": str(resolve(task["request_path"], context["base"]))
            if task.get("request_path")
            else None,
        }


def collect(context, *, model=None, workers=IO_WORKERS):
    from .fairness_dev_plan import verify_task

    if model is not None and model not in context["order"]:
        raise ValueError("Cannot collect an unregistered model")
    tasks = [t for t in normalized_tasks(context) if model is None or t["model"] == model]

    def inspect(task):
        verify_task(context["plan"], task)
        path = Path(task["result_path"])
        record = read(path) if path.exists() else None
        bound = {
            k: task[k]
            for k in ["key", "model", "setting", "case_id", "result_path", "request_path"]
        }
        bound.update(generation_status=record["status"] if record else "pending", judge_key=None)
        if record:
            bound["generation_record_sha256"] = sha256_file(path)
            required = {
                "plan_digest": context["plan"]["digest"],
                "task_id": task["key"],
                "model": task["model"],
                "case_id": task["case_id"],
                "setting": task["setting"],
                "stage": "edit",
                "seed": 42,
                "scientific_digest": task["scientific_digest"],
                "request_sha256": task["request_sha256"],
                "public_digest": task["public_digest"],
            }
            if any(record.get(k) != v for k, v in required.items()):
                raise ValueError(
                    f"Generation record identity differs from fixed task: {task['key']}"
                )
            if record.get("reused") and record.get("inference_api_calls") != 0:
                raise ValueError("Reused generation must record zero new API calls")
            if record["status"] == "not-applicable" and not task.get("not_applicable", False):
                raise ValueError("Unregistered N/A cannot replace a supported request")
        if task.get("request_sha256") and task["request_path"]:
            if sha256_file(Path(task["request_path"])) != task["request_sha256"]:
                raise ValueError("Prepared model request changed")
        job = None
        if record and record["status"] == "generated":
            output = Path(record["output_image"])
            if not output.is_absolute():
                output = path.parent / output
            if sha256_file(output) != record["output_sha256"]:
                raise ValueError(f"Output hash mismatch: {task['key']}")
            case = context["cases"][task["case_id"]]
            with Image.open(output) as image:
                if list(image.size) != case["source"]["size"]:
                    raise ValueError(f"Output is not on the canonical source canvas: {task['key']}")
            key = canonical.binding(case, record["output_sha256"], context["config"])
            bound.update(
                judge_key=key, output_sha256=record["output_sha256"], output_image=str(output)
            )
            job = {
                "key": key,
                "model": task["model"],
                "case_id": task["case_id"],
                "case": case,
                "record": {**record, "output_image": str(output)},
                "logical_keys": [],
            }
        return bound, job

    bindings, jobs = [], {}
    # Ordered reduction preserves the original first model, duplicate-output
    # binding and batch order regardless of filesystem completion order.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for bound, job in pool.map(inspect, tasks):
            bindings.append(bound)
            if job is not None:
                key = job["key"]
                if key not in jobs:
                    jobs[key] = job
                jobs[key]["logical_keys"].append(bound["key"])
    return bindings, jobs


class Cache:
    def __init__(self, path, config):
        self.path = Path(path).resolve() if path else None
        self.data = read(self.path) if self.path else {"config": config, "entries": {}}
        self.index_sha256 = sha256_file(self.path) if self.path else None
        if self.data.get("config", self.data.get("judge_config")) != config:
            raise ValueError("Historical cache fingerprint differs from this Judge")
        if self.data.get("run_id", digest(config)) != digest(config):
            raise ValueError("Historical cache run id differs")
        self.entries = self.data["entries"]
        if isinstance(self.entries, list):
            self.entries = {x["key"]: x for x in self.entries}
        self.verified_files = {}

    def checked(self, reference, expected):
        path = resolve(reference, self.path.parent)
        if self.verified_files.get(str(path)) != expected:
            if sha256_file(path) != expected:
                raise ValueError(f"Cache provenance hash mismatch: {path}")
            self.verified_files[str(path)] = expected
        return path

    def verify_portable_files(self, bundle):
        """CPU preflight of the complete cache dependency set before generation.

        Only live index references are relocated. Historical strings embedded
        in immutable answers are retained; lookup validates via hashed copies.
        """
        bundle = Path(bundle).resolve()
        references = {}
        for entry in self.entries.values():
            chain = entry.get("provenance_files", [])
            if not chain:
                raise ValueError("Judge cache has no provenance chain")
            entry_references = [
                {"path": entry["effective_record"], "sha256": entry["sha256"]}, *chain,
            ]
            for ref in entry_references:
                reference = str(resolve(ref["path"], self.path.parent))
                if reference in references and references[reference] != ref["sha256"]:
                    raise ValueError("Conflicting hashes for the same cache provenance file")
                references[reference] = ref["sha256"]

        def verify(reference):
            expected = references[reference]
            path = Path(reference).resolve()
            if not path.is_relative_to(bundle):
                raise ValueError(f"Judge cache dependency is outside the portable bundle: {path}")
            self.checked(reference, expected)
            return str(path)

        # Canonical records are immutable and hash checks are independent. Resolve
        # each unique reference once, with bounded I/O on the shared filesystem.
        with ThreadPoolExecutor(max_workers=8) as pool:
            unique = set(pool.map(verify, references))
        return {"entries": len(self.entries), "unique_files": len(unique)}

    def lookup(self, job, context):
        entry = self.entries.get(job["key"])
        if entry is None:
            return None
        path = self.checked(entry["effective_record"], entry["sha256"])
        chain = entry.get("provenance_files", [])
        if not chain:
            raise ValueError(
                "Effective cache entry has no raw/overlay/authorization provenance chain"
            )
        chain_by_hash = {p["sha256"]: self.checked(p["path"], p["sha256"]) for p in chain}
        record = read(path)
        if (
            record.get("key") != job["key"]
            or record.get("run_id") != context["run_id"]
            or record.get("output_sha256") != job["record"]["output_sha256"]
        ):
            raise ValueError("Cache key/run/output binding differs")
        if record["status"] != "scored":
            raise ValueError(
                "Only effective scored records may be imported from the completed historical cache"
            )
        units = [u["id"] for u in job["case"]["units"]]
        validate_scores(record["scores"], units)
        raw = record.get("raw_response")
        if not raw or raw.get("finish_reason") != "stop":
            raise ValueError("Cached effective score lacks a complete raw answer")
        hash_fields = [
            "raw_record_sha256",
            "retry_raw_record_sha256",
            "first_pass_record_sha256",
            "repair_overlay_sha256",
            "proposal_sha256",
        ]
        for field in hash_fields:
            if record.get(field) and record[field] not in chain_by_hash:
                raise ValueError(f"Cached overlay provenance is incomplete: {field}")
        answer_hash = record.get(
            "retry_raw_record_sha256", record.get("raw_record_sha256", entry["sha256"])
        )
        answer_path = path if answer_hash == entry["sha256"] else chain_by_hash[answer_hash]
        answer_record = read(answer_path)
        for field in ["key", "run_id", "output_sha256", "raw_response"]:
            if answer_record[field] != record[field]:
                raise ValueError(
                    f"Cached effective record differs from its actual raw answer: {field}"
                )
        if record.get("retry_raw_record_sha256"):
            proposal = read(chain_by_hash[record["proposal_sha256"]])
            if job["key"] not in {item["key"] for item in proposal["requests"]}:
                raise ValueError("Cached additional answer was not in the old 13-key proposal")
            authorizations = [read(p) for p in chain_by_hash.values()]
            if not any(
                a.get("proposal_sha256") == record["proposal_sha256"]
                and a.get("maximum_extra_judge_calls") == 13
                for a in authorizations
            ):
                raise ValueError(
                    "Cached additional answer lacks the original limited authorization"
                )
        try:
            actual, _ = canonical.parse(raw["text"], units)
        except (ValueError, KeyError, TypeError):
            actual, _ = recover(raw["text"], units)
        if actual != record["scores"]:
            raise ValueError("Cached scores differ from the unchanged raw parser/repair policy")
        return {
            **record,
            "new_judge_calls": 0,
            "cache_reuse": {
                "index": str(self.path),
                "index_sha256": self.index_sha256,
                "effective_record": str(path),
                "effective_sha256": entry["sha256"],
                "provenance_files": chain,
            },
            "binding_verified_against_current_output": True,
        }


def paths(context):
    root = context["root"] / "judge"
    return root, root / "raw_records", root / "effective_records", root / "admitted"


def verify_effective(value, job, context, cache):
    key = job["key"]
    if (
        value["key"] != key
        or value["run_id"] != context["run_id"]
        or value["output_sha256"] != job["record"]["output_sha256"]
    ):
        raise ValueError("Existing effective answer has a different binding")
    if value["status"] == "scored":
        validate_scores(value["scores"], [u["id"] for u in job["case"]["units"]])
    raw_path = paths(context)[1] / f"{key}.json"
    if raw_path.exists():
        if value.get("raw_record_sha256") != sha256_file(raw_path):
            raise ValueError("Effective overlay no longer matches immutable raw answer")
        raw = read(raw_path)
        verify_raw(raw, job, context)
        expected = effective(raw, [u["id"] for u in job["case"]["units"]], raw_path)
        if expected != value:
            raise ValueError("Existing effective overlay differs from unchanged raw parser/repair")
    elif value.get("cache_reuse"):
        if cache.lookup(job, context) != value:
            raise ValueError("Existing reused cache record changed")
    else:
        raise ValueError("Effective answer lacks either immutable raw or exact cache provenance")


def verify_raw(raw, job, context):
    for field, expected in [
        ("key", job["key"]),
        ("run_id", context["run_id"]),
        ("output_sha256", job["record"]["output_sha256"]),
    ]:
        if raw.get(field) != expected:
            raise ValueError(f"Immutable raw answer has a different binding: {field}")
    parsed = scored(
        (job["key"], (job["case"], job["record"])), raw["raw_response"], context["run_id"]
    )
    for field in ["status", "scores", "reason", "repaired_json"]:
        if parsed.get(field) != raw.get(field):
            raise ValueError(f"Immutable raw answer differs from the original parser: {field}")


def record_index(context):
    """One directory snapshot under the single-controller lock, never per batch."""
    _, raws, effectives, admitted = paths(context)
    return {
        name: {p.stem for p in folder.glob("*.json")}
        for name, folder in (("raw", raws), ("effective", effectives), ("admitted", admitted))
    }


def restore_and_cache(context, jobs, cache, *, index=None, workers=IO_WORKERS):
    root, raws, effectives, admitted = paths(context)
    index = record_index(context) if index is None else index
    if context.get("full_release"):
        verify_admissions(context, jobs, index=index, workers=workers)

    def restore(item):
        key, job = item
        raw_path, effective_path = raws / f"{key}.json", effectives / f"{key}.json"
        if key in index["effective"]:
            value = read(effective_path)
            verify_effective(value, job, context, cache)
            return key, value
        if key in index["raw"]:
            raw = read(raw_path)
            verify_raw(raw, job, context)
            value = effective(raw, [u["id"] for u in job["case"]["units"]], raw_path)
            immutable(effective_path, value)
            return key, value
        reused = cache.lookup(job, context)
        if reused is not None:
            immutable(effectives / f"{key}.json", reused)
        return key, reused

    restored = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for key, value in pool.map(restore, jobs.items()):
            if value is not None:
                restored[key] = value
    index["effective"].update(restored)
    unresolved = index["admitted"] - index["raw"]
    if unresolved:
        raise RuntimeError(
            f"Admitted Judge calls have no terminal raw record; no automatic retry: {sorted(unresolved)}"
        )
    return restored


def verify_admissions(context, jobs, *, index=None, workers=IO_WORKERS):
    """Bind every new raw answer to its one recorded native Judge admission."""
    directory, raws, effectives, admitted = paths(context)
    index = record_index(context) if index is None else index
    raw_keys = index["raw"]
    admission_keys = index["admitted"]
    if raw_keys != admission_keys:
        raise ValueError("Judge raw/admission sets differ; no automatic retry")
    if raw_keys - set(jobs):
        raise ValueError("Unregistered Judge admission/raw key")
    def verify(key):
        job = jobs[key]
        admission = read(admitted / f"{key}.json")
        raw = read(raws / f"{key}.json")
        expected = {
            "key": key,
            "model": job["model"],
            "case_id": job["case_id"],
            "output_sha256": job["record"]["output_sha256"],
            "canonical_prompt_digest": digest(canonical.prompt(job["case"])),
        }
        if any(admission.get(k) != v for k, v in expected.items()):
            raise ValueError("Judge admission identity differs from canonical job")
        if type(admission.get("attempt")) is not int or admission["attempt"] != 1:
            raise ValueError("Judge admission is not a single attempt")
        execution = Path(admission["execution"])
        if execution.parent.resolve() != (directory / "executions").resolve():
            raise ValueError("Judge admission belongs to a different node execution")
        receipt_path = execution / "receipt.json"
        if raw.get("execution_receipt") != str(receipt_path) or raw.get("new_judge_calls") != 1:
            raise ValueError("Raw answer is not bound to its admitted execution")
        if any(raw.get(k) != expected[k] for k in ("model", "case_id")):
            raise ValueError("Raw answer model/source differs from admission")
        receipt = read(receipt_path)
        if (
            receipt.get("run_id") != context["run_id"]
            or receipt.get("plan_sha256") != context["plan_sha256"]
            or receipt.get("canonical_sha256") != context["config"]["source_sha256"]
            or receipt.get("frozen") is not True
        ):
            raise ValueError("Judge execution receipt differs from frozen full plan")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(verify, sorted(raw_keys)))


class ProgressState:
    """Incremental bookkeeping; only successful immutable writes advance state."""

    def __init__(self, context, bindings, jobs, index, effective_records):
        self.models = {m: Counter() for m in context["order"]}
        self.logical_requests = len(bindings)
        self.unique_generated_keys = len(jobs)
        self.logical_by_key = {}
        self.effective = {}
        self.statuses = Counter()
        self.reused = 0
        self.repairs = 0
        self.admitted = set(index["admitted"])
        self.raw = set(index["raw"])
        for b in bindings:
            status = b["generation_status"]
            if status == "generated":
                status = "judge-pending"
                self.logical_by_key.setdefault(b["judge_key"], Counter())[b["model"]] += 1
            self.models[b["model"]][status] += 1
        for key, value in effective_records.items():
            self.record_effective(key, value)

    def record_effective(self, key, value):
        summary = (value["status"], "cache_reuse" in value,
                   bool(value.get("deterministic_repair_used", False)))
        if key in self.effective:
            if self.effective[key] != summary:
                raise ValueError("Progress cannot overwrite an immutable effective status")
            return
        self.effective[key] = summary
        status, reused, repaired = summary
        self.statuses[status] += 1
        self.reused += reused
        self.repairs += repaired and not reused
        for model, count in self.logical_by_key[key].items():
            self.models[model]["judge-pending"] -= count
            if not self.models[model]["judge-pending"]:
                del self.models[model]["judge-pending"]
            self.models[model][status] += count


def progress(context, bindings, jobs, *, state=None):
    root, _, effectives, _ = paths(context)
    if state is None:
        # Read-only callers can request a fresh snapshot. The running Judge
        # always supplies its state and performs zero record reads/globs here.
        index = record_index(context)
        records = {key: read(effectives / f"{key}.json")
                   for key in jobs if key in index["effective"]}
        state = ProgressState(context, bindings, jobs, index, records)
    value = {
        "updated_at_epoch": time.time(),
        "plan_digest": context["plan"].get("digest"),
        "plan_sha256": context["plan_sha256"],
        "run_id": context["run_id"],
        "models": {m: dict(c) for m, c in state.models.items()},
        "logical_requests": state.logical_requests,
        "unique_generated_keys": state.unique_generated_keys,
        "new_admitted_calls": len(state.admitted),
        "new_raw_answers": len(state.raw),
        "effective_statuses": dict(state.statuses),
        "reused_effective_keys": state.reused,
        "deterministic_repairs": state.repairs,
        "test_started": context.get("full_release", False),
        "frozen": context.get("full_release", False),
    }
    write_json(root / "progress.json", value)
    return value


def run(plan, root=None, cache_index=None, model=None, dry_run=False, node_id=None):
    context = load_plan(plan, root, node_id=node_id)
    directory, raws, effectives, admitted = paths(context)
    directory.mkdir(parents=True, exist_ok=True)
    lock = (directory / "controller.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    immutable(directory / "config.json", context["config"])
    immutable(
        directory / "plan_binding.json",
        {
            "plan_sha256": context["plan_sha256"],
            "run_id": context["run_id"],
            "model_order": context["order"],
        },
    )
    cache_path = cache_index or context["plan"].get(
        "cache_index", context["plan"].get("judge_cache_index")
    )
    cache = Cache(resolve(cache_path, context["base"]) if cache_path else None, context["config"])
    if (
        context["plan"].get("cache_index_sha256")
        and cache.index_sha256 != context["plan"]["cache_index_sha256"]
    ):
        raise ValueError("Historical Judge index changed from the fixed plan")
    bindings, jobs = collect(context)
    write_json(directory / "bindings.json", bindings)
    index = record_index(context)
    restored = restore_and_cache(context, jobs, cache, index=index)
    state = ProgressState(context, bindings, jobs, index, restored)
    pending = [j for key, j in jobs.items() if key not in state.effective]
    if model is not None and model not in context["order"]:
        raise ValueError("Requested model is outside plan")
    # A later model never jumps an earlier model with unresolved generation or
    # unattempted Judge requests. Terminal Judge failures do not trigger retries.
    allowed = []
    for current in context["order"]:
        bb = [b for b in bindings if b["model"] == current]
        if any(
            b["generation_status"] not in FAILURES | {"generated", "not-applicable"} for b in bb
        ):
            break
        jj = [j for j in pending if j["model"] == current]
        if model and current != model and jj:
            break
        if model is None or current == model:
            allowed.extend(jj)
    progress(context, bindings, jobs, state=state)
    generation_complete = all(
        b["generation_status"] in FAILURES | {"generated", "not-applicable"} for b in bindings
    )
    if dry_run:
        for job in allowed:
            canonical.evidence(job["case"], job["record"]["output_image"])
        result = {
            "dry_run": True,
            "eligible_unique_jobs": len(allowed),
            "runtime_fingerprint_checked": False,
            "new_judge_calls": 0,
            "model_serial_order": context["order"],
            "all_generation_terminal": generation_complete,
        }
        write_json(directory / "dry_run.json", result)
        return result
    if not generation_complete:
        raise RuntimeError(
            "Generation is not fully terminal; cache verification completed, but eight-card Judge cannot start"
        )
    if not allowed:
        return progress(context, bindings, jobs, state=state)
    if canonical.fingerprint() != context["config"]:
        raise ValueError("Actual Judge runtime/checkpoint fingerprint differs from original")
    execution = (
        directory / "executions" / f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{os.getpid()}"
    )
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
        "repair_policy": POLICY,
        "new_admitted_calls": 0,
        "new_raw_answers": 0,
        "calibration_calls": 0,
        "editor_calls": 0,
        "scheduling": "model serial; original batch16; four CPU evidence workers; at most two prefetched batches",
        "frozen": context.get("full_release", False),
        "test_started": context.get("full_release", False),
    }
    write_json(execution / "receipt.json", receipt)
    stop = [False]
    signal.signal(signal.SIGUSR1, lambda *_: stop.__setitem__(0, True))
    try:
        args = SimpleNamespace(
            model=canonical.MODEL, **context["config"]["engine"], **context["config"]["decode"]
        )
        backend = canonical.Backend(args, 22)
        receipt["status"] = "running"
        write_json(execution / "receipt.json", receipt)
        for current, group in groupby(allowed, key=lambda j: j["model"]):
            group = list(group)
            items = [(j["key"], (j["case"], j["record"])) for j in group]
            for batch, conversations in prefetched_batches(
                items,
                lambda item: canonical.evidence(item[1][0], item[1][1]["output_image"]),
                size=16,
                workers=4,
            ):
                if stop[0]:
                    break
                for key, (case, record) in batch:
                    immutable(
                        admitted / f"{key}.json",
                        {
                            "key": key,
                            "model": current,
                            "case_id": case["id"],
                            "output_sha256": record["output_sha256"],
                            "canonical_prompt_digest": digest(canonical.prompt(case)),
                            "at": time.time(),
                            "execution": str(execution),
                            "attempt": 1,
                        },
                    )
                    state.admitted.add(key)
                    receipt["new_admitted_calls"] += 1
                write_json(execution / "receipt.json", receipt)
                tick = time.monotonic()
                answers = backend.generate(conversations)
                elapsed = time.monotonic() - tick
                if len(answers) != len(batch):
                    raise RuntimeError(
                        "Judge returned a different answer count; admissions retained, no retry"
                    )
                for item, answer in zip(batch, answers, strict=True):
                    key, (case, _) = item
                    raw = scored(item, answer, context["run_id"])
                    raw.update(
                        model=current,
                        case_id=case["id"],
                        completed_at=time.time(),
                        batch_size=len(batch),
                        batch_wall_seconds=elapsed,
                        execution_receipt=str(execution / "receipt.json"),
                        new_judge_calls=1,
                    )
                    raw_path = raws / f"{key}.json"
                    immutable(raw_path, raw)
                    state.raw.add(key)
                    value = effective(raw, [u["id"] for u in case["units"]], raw_path)
                    immutable(effectives / f"{key}.json", value)
                    state.record_effective(key, value)
                    receipt["new_raw_answers"] += 1
                write_json(execution / "receipt.json", receipt)
                print(json.dumps(progress(context, bindings, jobs, state=state)), flush=True)
            if stop[0]:
                break
            write_json(
                directory / "model_completed" / f"{current}.json",
                {"model": current, "at": time.time(), "judge_attempts_terminal": True},
            )
        receipt.update(status="drained" if stop[0] else "completed", ended_at=time.time())
        write_json(execution / "receipt.json", receipt)
        return progress(context, bindings, jobs, state=state)
    except BaseException as exc:
        receipt.update(status="error", error=repr(exc), ended_at=time.time())
        write_json(execution / "receipt.json", receipt)
        raise
    finally:
        lock.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--root", type=Path)
    p.add_argument("--cache-index", type=Path)
    p.add_argument("--model")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    print(
        json.dumps(run(a.plan, a.root, a.cache_index, a.model, a.dry_run), ensure_ascii=False),
        flush=True,
    )
