"""Portable canonical Judge for one fixed fairness configuration, dev only.

Raw answers are immutable; deterministic repair has a separate overlay. Cache
reuse requires the exact canonical binding including output SHA and fingerprint.
Admission without a terminal answer is never automatically resubmitted.
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

from PIL import Image

from samtok_benchmark.io import digest, read_jsonl, sha256_file, write_json
from . import dev_judge as canonical
from .dev_judge_stream import prefetched_batches, scored
from .judge_repair import recover, POLICY

FAILURES = {"failed", "failed-planner", "failed-component", "failed-interrupted"}


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


def load_plan(path, root=None, *, helper_root=None):
    path = Path(path).resolve()
    from .fairness_dev_plan import load_plan as verify_plan

    plan = verify_plan(path) if helper_root is None else verify_plan(path, helper_root=helper_root)
    base = path.parent
    if plan.get("test_authorized") or plan.get("test_started") or plan.get("formal_test"):
        raise ValueError("This runner is dev-only")
    case_ids = plan.get("case_ids", plan.get("cases"))
    order = plan.get("model_order", plan.get("models"))
    if isinstance(order, dict):
        order = list(order)
    if not isinstance(order, list) or len(order) != len(set(order)):
        raise ValueError("Explicit unique model order is required")
    if len(case_ids) != len(set(case_ids)) or len(case_ids) != 20:
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
    for case in cases.values():
        references = [(case["source"]["image"], case["source"]["sha256"])]
        references.extend((u["target"]["mask"], u["target"]["mask_sha256"]) for u in case["units"])
        for relative, expected_sha in references:
            if sha256_file(dataset_root / relative) != expected_sha:
                raise ValueError(f"Canonical source/mask asset changed: {relative}")
    context = {
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
    order = context["order"]
    settings = context["plan"]["settings"]
    cases = context["case_ids"]
    for task in sorted(
        context["plan"]["tasks"],
        key=lambda t: (
            order.index(t["model"]),
            settings.index(t["setting"]),
            cases.index(t["case_id"]),
        ),
    ):
        yield {
            **task,
            "result_path": str(resolve(task["result_path"], context["base"])),
            "request_path": str(resolve(task["request_path"], context["base"]))
            if task.get("request_path")
            else None,
        }


def collect(context, *, model=None):
    from .fairness_dev_plan import verify_task

    if model is not None and model not in context["order"]:
        raise ValueError("Cannot collect an unregistered model")
    bindings, jobs = [], {}
    for task in normalized_tasks(context):
        if model is not None and task["model"] != model:
            continue
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
            if key not in jobs:
                jobs[key] = {
                    "key": key,
                    "model": task["model"],
                    "case_id": task["case_id"],
                    "case": case,
                    "record": {**record, "output_image": str(output)},
                    "logical_keys": [],
                }
            jobs[key]["logical_keys"].append(task["key"])
        bindings.append(bound)
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


def restore_and_cache(context, jobs, cache):
    root, raws, effectives, admitted = paths(context)
    for key, job in jobs.items():
        raw_path, effective_path = raws / f"{key}.json", effectives / f"{key}.json"
        if effective_path.exists():
            value = read(effective_path)
            verify_effective(value, job, context, cache)
            continue
        if raw_path.exists():
            raw = read(raw_path)
            verify_raw(raw, job, context)
            immutable(
                effective_path, effective(raw, [u["id"] for u in job["case"]["units"]], raw_path)
            )
            continue
        reused = cache.lookup(job, context)
        if reused is not None:
            immutable(effectives / f"{key}.json", reused)
    unresolved = {p.stem for p in admitted.glob("*.json")} - {p.stem for p in raws.glob("*.json")}
    if unresolved:
        raise RuntimeError(
            f"Admitted Judge calls have no terminal raw record; no automatic retry: {sorted(unresolved)}"
        )


def progress(context, bindings, jobs):
    root, raws, effectives, admitted = paths(context)
    effective_records = {
        key: read(effectives / f"{key}.json")
        for key in jobs
        if (effectives / f"{key}.json").exists()
    }
    per_model = {}
    for model in context["order"]:
        counts = Counter()
        for b in bindings:
            if b["model"] != model:
                continue
            if b["generation_status"] == "generated":
                value = effective_records.get(b["judge_key"])
                counts[value["status"] if value else "judge-pending"] += 1
            else:
                counts[b["generation_status"]] += 1
        per_model[model] = dict(counts)
    value = {
        "updated_at_epoch": time.time(),
        "plan_digest": context["plan"].get("digest"),
        "plan_sha256": context["plan_sha256"],
        "run_id": context["run_id"],
        "models": per_model,
        "logical_requests": len(bindings),
        "unique_generated_keys": len(jobs),
        "new_admitted_calls": len(list(admitted.glob("*.json"))),
        "new_raw_answers": len(list(raws.glob("*.json"))),
        "effective_statuses": dict(Counter(r["status"] for r in effective_records.values())),
        "reused_effective_keys": sum("cache_reuse" in r for r in effective_records.values()),
        "deterministic_repairs": sum(
            r.get("deterministic_repair_used", False) and "cache_reuse" not in r
            for r in effective_records.values()
        ),
        "test_started": False,
        "frozen": False,
    }
    write_json(root / "progress.json", value)
    return value


def run(plan, root=None, cache_index=None, model=None, dry_run=False):
    context = load_plan(plan, root)
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
    restore_and_cache(context, jobs, cache)
    pending = [j for key, j in jobs.items() if not (effectives / f"{key}.json").exists()]
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
    progress(context, bindings, jobs)
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
        return progress(context, bindings, jobs)
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
        "frozen": False,
        "test_started": False,
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
                    immutable(
                        effectives / f"{key}.json",
                        effective(raw, [u["id"] for u in case["units"]], raw_path),
                    )
                    receipt["new_raw_answers"] += 1
                write_json(execution / "receipt.json", receipt)
                print(json.dumps(progress(context, bindings, jobs)), flush=True)
            if stop[0]:
                break
            write_json(
                directory / "model_completed" / f"{current}.json",
                {"model": current, "at": time.time(), "judge_attempts_terminal": True},
            )
        receipt.update(status="drained" if stop[0] else "completed", ended_at=time.time())
        write_json(execution / "receipt.json", receipt)
        return progress(context, bindings, jobs)
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
