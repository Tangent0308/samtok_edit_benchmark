"""Resume canonical Judge with bounded prefetch and continuous request admission.

The original dev_judge module/config/cache remain immutable. Each new record
links an execution receipt recording scheduling overrides and source hashes.
Calibration responses are isolated and never replace evaluation responses.
"""

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import fcntl
import inspect
from itertools import groupby
import os
from pathlib import Path
import signal
import shutil
import time
from types import SimpleNamespace

from samtok_benchmark.io import digest, sha256_file, write_json
from . import dev_judge as canonical
from .dev_plan import ROOT, read


def stream(
    items,
    prepare,
    enqueue,
    step,
    completed,
    concurrency,
    prefetch=64,
    workers=4,
    draining=lambda: False,
):
    """Bound CPU evidence memory; replenish slots without a batch barrier.

    All engine methods run on the caller thread. Worker threads only prepare
    independent, deterministic image evidence. A drain stops admission and
    persists every already-admitted result before returning.
    """
    pending, active = deque(), {}
    source = iter(items)
    exhausted = False
    count = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while pending or active or not exhausted:
            stop = draining()
            while not stop and not exhausted and len(pending) < prefetch:
                try:
                    item = next(source)
                except StopIteration:
                    exhausted = True
                    break
                pending.append((item, pool.submit(prepare, item)))
            while not stop and pending and len(active) < concurrency:
                item, future = pending[0]
                if active and not future.done():
                    break
                prepared = future.result()
                pending.popleft()
                rid = enqueue(item, prepared)
                if rid in active:
                    raise ValueError(f"Duplicate engine request ID: {rid}")
                active[rid] = item
            if active:
                for output in step():
                    if output.finished:
                        item = active.pop(output.request_id)
                        completed(item, output)
                        count += 1
            elif stop:
                for _, future in pending:
                    future.cancel()
                break
    return count


def request(backend, conversation):
    """Exactly the same chat rendering/image order as canonical Backend.generate."""
    images = [
        p["image"]
        for m in conversation
        if isinstance(m["content"], list)
        for p in m["content"]
        if p["type"] == "image"
    ]
    effort = backend.args.reasoning_effort
    text = backend.processor.apply_chat_template(
        conversation,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=effort != "off",
        **({} if effort == "off" else {"reasoning_effort": effort}),
    )
    return {"prompt": text, "multi_modal_data": {"image": images}}


def answer(output):
    o = output.outputs[0]
    return {
        "text": o.text,
        "finish_reason": o.finish_reason,
        "prompt_tokens": len(output.prompt_token_ids),
        "output_tokens": len(o.token_ids),
    }


def enqueue_request(backend, prompt):
    """vLLM 0.31 enqueue returns an internal ID; step emits the external ID.

    Read the actual state mapping, never guess by stripping an ID suffix.
    The output processor retains this state until step() consumes completion.
    """
    internal = backend.model.enqueue([prompt], backend.sampling, use_tqdm=False)[0]
    state = backend.model.llm_engine.output_processor.request_states[internal]
    return state.external_req_id


def scored(item, raw, run_id):
    key, (case, record) = item
    result = {
        "key": key,
        "run_id": run_id,
        "output_sha256": record["output_sha256"],
        "raw_response": raw,
        "status": "unparsed",
    }
    try:
        if raw["finish_reason"] == "length":
            raise ValueError("Truncated Judge response")
        value, repaired = canonical.parse(raw["text"], [u["id"] for u in case["units"]])
        result.update(status="scored", scores=value, repaired_json=repaired)
    except (ValueError, KeyError, TypeError) as exc:
        result.update(status="judge-failed", reason=str(exc))
    return result


def save_new(path, result):
    # Single controller lock; never overwrite even a failed existing response.
    if path.exists():
        raise FileExistsError(path)
    write_json(path, result)


def prepare(item):
    _, (case, record) = item
    return canonical.evidence(case, record["output_image"])


def select_schedule(timings):
    # A cut-off trial supplies only observed elapsed time, never a fabricated
    # full-run duration. It is ineligible for deployment.
    t32 = (
        float("inf")
        if timings["stream32"].get("status") == "aborted-performance-trial"
        else timings["stream32"]["seconds"]
    )
    selected = 32 if t32 < 0.95 * timings["stream16"]["seconds"] else 16
    if timings[f"stream{selected}"]["seconds"] >= 0.95 * timings["batch16"]["seconds"]:
        return "prefetch16", 16
    return "continuous", selected


def prefetched_batches(items, prepare, size=16, workers=4, group_key=None):
    """Keep at most two batches of deterministic CPU evidence in memory."""
    source, pending, exhausted = iter(items), deque(), False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while pending or not exhausted:
            while not exhausted and len(pending) < 2 * size:
                try:
                    item = next(source)
                except StopIteration:
                    exhausted = True
                    break
                pending.append((item, pool.submit(prepare, item)))
            batch = []
            while pending and len(batch) < size:
                if (
                    batch
                    and group_key is not None
                    and group_key(pending[0][0]) != group_key(batch[0][0])
                ):
                    break
                batch.append(pending.popleft())
            if batch:
                yield [item for item, _ in batch], [future.result() for _, future in batch]


def calibrate(backend, items, root, run_id, baseline=None):
    """Same fixed inputs, three schedules; choose solely by elapsed time."""
    timings = {}
    for mode, concurrency in (("batch16", 16), ("stream16", 16), ("stream32", 32)):
        if mode == "batch16" and baseline is not None:
            assert read(baseline.parent / "calibration_inputs.json") == [k for k, _ in items]
            assert read(baseline.parent / "receipt.json")["run_id"] == run_id
            shutil.copytree(baseline / mode, root / mode)
            timings[mode] = read(baseline / "timings.json")[mode]
            write_json(
                root / "baseline_reuse.json",
                {
                    "source": str(baseline),
                    "reason": "Completed baseline retained after ID-mapping integration failure",
                    "extra_calls_this_execution": 0,
                },
            )
            continue
        directory = root / mode
        directory.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        if mode == "batch16":
            for i in range(0, len(items), 16):
                batch = items[i : i + 16]
                raw = backend.generate([prepare(item) for item in batch])
                for item, response in zip(batch, raw, strict=True):
                    save_new(directory / f"{item[0]}.json", scored(item, response, run_id))
        else:

            def enqueue(item, conv):
                record_path = root / "submissions" / mode / f"{item[0]}.json"
                submission = {"key": item[0], "at": time.time(), "status": "submitting"}
                save_new(record_path, submission)
                rid = enqueue_request(backend, request(backend, conv))
                write_json(record_path, submission | {"status": "admitted", "external_id": rid})
                return rid

            def completed(item, output):
                save_new(directory / f"{item[0]}.json", scored(item, answer(output), run_id))

            stream(
                items,
                prepare,
                enqueue,
                backend.model.llm_engine.step,
                completed,
                concurrency=concurrency,
            )
        seconds = time.monotonic() - start
        records = [read(directory / f"{item[0]}.json") for item in items]
        timings[mode] = {
            "seconds": seconds,
            "requests": len(items),
            "requests_per_hour": len(items) * 3600 / seconds,
            "output_tokens": sum(r["raw_response"]["output_tokens"] for r in records),
            "failed": sum(r["status"] != "scored" for r in records),
        }
        write_json(root / "timings.json", timings)
        print({"calibration": mode, **timings[mode]}, flush=True)
    mode, selected = select_schedule(timings)
    comparisons = {}
    for mode in ("stream16", "stream32"):
        same_text = same_score = comparable = 0
        for item in items:
            a = read(root / "batch16" / f"{item[0]}.json")
            b = read(root / mode / f"{item[0]}.json")
            same_text += a["raw_response"]["text"] == b["raw_response"]["text"]
            if a["status"] == b["status"] == "scored":
                comparable += 1

                # Compare numeric judgments, not free-text evidence wording.
                def numbers(v):
                    return [u[k]["score"] for u in v["units"] for k in ("E", "P", "Q")] + [
                        v[k]["score"] for k in ("global_P", "global_Q")
                    ]

                same_score += numbers(a["scores"]) == numbers(b["scores"])
        comparisons[mode] = {
            "identical_raw": same_text,
            "identical_numeric_scores": same_score,
            "both_parseable": comparable,
            "total": len(items),
        }
    result = {
        "timings": timings,
        "comparisons": comparisons,
        "selected_concurrency": selected,
        "selected_mode": mode,
        "selection_rule": "Continuous must beat batch16 by >5%; 32 must beat stream16 by >5%; otherwise prefetch16. Scores never select schedule.",
        "extra_judge_calls": (2 if baseline else 3) * len(items),
        "baseline_reused_from": str(baseline) if baseline else None,
        "evaluation_records_replaced": 0,
        "note": "Scheduling can change FP8 numerical paths; deterministic seed does not guarantee batch-invariant text.",
    }
    write_json(root / "summary.json", result)
    return result


def run(calibration_count=32, baseline=None, reuse_calibration=None, reservation=None):
    lock = (ROOT / "controller.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    current = read(ROOT / "judge/current.json")
    run_id = current["run_id"]
    root = ROOT / "judge" / run_id
    config = read(root / "config.json")
    assert canonical.fingerprint() == config, "Canonical code/config changed; refuse cache reuse"
    assert digest(config) == run_id
    allocation = read(reservation) if reservation else None
    excluded = set(allocation["remote_models"]) if allocation else set()
    if allocation:
        assert allocation["run_id"] == run_id
    segment = root / "executions" / time.strftime("stream_%Y%m%dT%H%M%SZ", time.gmtime())
    segment.mkdir(parents=True, exist_ok=False)
    for label, path in (
        ("runner.py", Path(__file__)),
        ("canonical.py", Path(canonical.__file__)),
        ("backend.py", Path(inspect.getfile(canonical.Backend))),
    ):
        shutil.copyfile(path, segment / label)
    receipt = {
        "run_id": run_id,
        "pid": os.getpid(),
        "started_at": time.time(),
        "canonical_config": str(root / "config.json"),
        "source_sha256": sha256_file(Path(__file__)),
        "backend_sha256": sha256_file(Path(inspect.getfile(canonical.Backend))),
        "engine_overrides": {"batch_size": 32},
        "cpu_workers": 4,
        "prefetch": 64,
        "cache_reuse": "Canonical semantics unchanged; actual scheduling recorded per execution",
        "status": "validating",
    }
    receipt["remote_reservation"] = str(reservation) if reservation else None
    receipt["excluded_models"] = sorted(excluded)
    write_json(segment / "receipt.json", receipt)
    write_json(root / "execution_current.json", {"receipt": str(segment / "receipt.json")})
    orchestration = ROOT / "orchestration"
    controller = {
        "pid": os.getpid(),
        "status": "judge-validating",
        "started_at": time.time(),
        "freeze_authorized": False,
        "test_started": False,
        "execution": str(segment),
    }
    write_json(orchestration / "controller.json", controller)
    drain = [False]
    signal.signal(signal.SIGUSR1, lambda *_: drain.__setitem__(0, True))
    try:
        by_case = canonical.cases()
        all_items = {}
        for b in read(root / "bindings.json"):
            if b["key"] in all_items:
                continue
            r = read(Path(b["record"]))
            case = by_case[r["task"]["case_id"]]
            assert sha256_file(Path(r["output_image"])) == r["output_sha256"]
            assert canonical.binding(case, r["output_sha256"], config) == b["key"]
            all_items.setdefault(b["key"], (case, r))
            if len(all_items) % 1024 == 0:
                print({"validated_unique_bindings": len(all_items)}, flush=True)
        old = {p.stem: sha256_file(p) for p in (root / "records").glob("*.json")}
        write_json(segment / "preserved_records.json", old)
        pending = [
            (k, v)
            for k, v in all_items.items()
            if k not in old and v[1]["task"]["model"] not in excluded
        ]
        unresolved = [p for p in (root / "admitted").glob("*.json") if p.stem not in old]
        assert not unresolved, "Admitted requests lack responses; do not silently resample"
        if reuse_calibration:
            calibration_keys = read(reuse_calibration.parent / "calibration_inputs.json")
            assert all(k in old and k in all_items for k in calibration_keys)
            calibration = [(k, all_items[k]) for k in calibration_keys]
        else:
            calibration = [(k, all_items[k]) for k in sorted(old) if k in all_items][
                :calibration_count
            ]
        assert len(calibration) == calibration_count
        write_json(segment / "calibration_inputs.json", [k for k, _ in calibration])
        controller["status"] = "judge-loading"
        write_json(orchestration / "controller.json", controller)
        engine_capacity = 32
        if reuse_calibration:
            previous = read(reuse_calibration / "summary.json")
            if select_schedule(previous["timings"])[0] == "prefetch16":
                engine_capacity = 16
        receipt["engine_overrides"] = {"batch_size": engine_capacity}
        write_json(segment / "receipt.json", receipt)
        args = SimpleNamespace(
            model=canonical.MODEL,
            **(config["engine"] | {"batch_size": engine_capacity}),
            **config["decode"],
        )
        backend = canonical.Backend(args, 22)
        print({"engine_ready": True, "maximum_concurrency": engine_capacity}, flush=True)
        controller["status"] = "judge-calibrating"
        write_json(orchestration / "controller.json", controller)
        if reuse_calibration:
            assert read(reuse_calibration.parent / "calibration_inputs.json") == [
                k for k, _ in calibration
            ]
            assert read(reuse_calibration.parent / "receipt.json")["run_id"] == run_id
            previous = read(reuse_calibration / "summary.json")
            mode, selected = select_schedule(previous["timings"])
            measurement = previous | {
                "selected_mode": mode,
                "selected_concurrency": selected,
                "extra_judge_calls": 0,
                "reused_from": str(reuse_calibration),
            }
            write_json(segment / "calibration/summary.json", measurement)
        else:
            measurement = calibrate(backend, calibration, segment / "calibration", run_id, baseline)
        receipt.update(
            status="running",
            calibration=str(segment / "calibration/summary.json"),
            selected_concurrency=measurement["selected_concurrency"],
            selected_mode=measurement["selected_mode"],
            extra_judge_calls=measurement["extra_judge_calls"],
        )
        receipt["model_scheduling"] = "contiguous model groups; no mixed-model inference batches"
        write_json(segment / "receipt.json", receipt)
        controller["status"] = "judge-running"
        write_json(orchestration / "controller.json", controller)
        start, start_utc = time.monotonic(), time.time()
        completions = []
        admitted_at = {}

        def enqueue(item, conv):
            key = item[0]
            prompt = request(backend, conv)
            save_new(
                root / "admitted" / f"{key}.json",
                {
                    "key": key,
                    "execution": str(segment),
                    "at": time.time(),
                    "rendered_prompt_sha256": digest(prompt["prompt"]),
                },
            )
            rid = enqueue_request(backend, prompt)
            admitted_at[key] = time.monotonic()
            return rid

        def completed(item, output):
            result = scored(item, output if isinstance(output, dict) else answer(output), run_id)
            now = time.time()
            result.update(
                execution_receipt=str(segment / "receipt.json"),
                completed_at=now,
                request_wall_seconds=time.monotonic() - admitted_at.pop(item[0]),
                scheduling=receipt["selected_mode"],
                concurrency=receipt["selected_concurrency"],
            )
            save_new(root / "records" / f"{item[0]}.json", result)
            completions.append(now)
            recent = completions[-129:]
            rate = (
                (len(recent) - 1) / (recent[-1] - recent[0])
                if len(recent) >= 33 and recent[-1] > recent[0]
                else None
            )
            progress = {
                "execution": str(segment),
                "started_at": start_utc,
                "updated_at": now,
                "completed": len(completions),
                "pending_initial": len(pending),
                "wall_seconds": time.monotonic() - start,
                "recent_requests_per_second": rate,
                "concurrency": receipt["selected_concurrency"],
            }
            write_json(root / "stream_progress.json", progress)
            if len(completions) % 16 == 0:
                print(progress, flush=True)

        if receipt["selected_mode"] == "prefetch16":
            n = 0
            batches = prefetched_batches(
                pending, prepare, group_key=lambda item: item[1][1]["task"]["model"]
            )
            try:
                for batch, conversations in batches:
                    if drain[0]:
                        break
                    assert len({item[1][1]["task"]["model"] for item in batch}) == 1
                    for item in batch:
                        save_new(
                            root / "admitted" / f"{item[0]}.json",
                            {
                                "key": item[0],
                                "execution": str(segment),
                                "at": time.time(),
                                "scheduling": "prefetch16",
                            },
                        )
                        admitted_at[item[0]] = time.monotonic()
                    outputs = backend.generate(conversations)
                    for item, raw in zip(batch, outputs, strict=True):
                        completed(item, raw)
                        n += 1
            finally:
                batches.close()
        else:
            n = 0
            for _, group in groupby(pending, key=lambda item: item[1][1]["task"]["model"]):
                if drain[0]:
                    break
                n += stream(
                    list(group),
                    prepare,
                    enqueue,
                    backend.model.llm_engine.step,
                    completed,
                    concurrency=receipt["selected_concurrency"],
                    draining=lambda: drain[0],
                )
        assert all(sha256_file(root / "records" / f"{k}.json") == v for k, v in old.items())
        receipt.update(
            status="drained" if drain[0] else "completed",
            completed_at=time.time(),
            production_calls=n,
            preserved_records_verified=len(old),
        )
        write_json(segment / "receipt.json", receipt)
        if not drain[0] and all((root / "records" / f"{k}.json").exists() for k in all_items):
            write_json(
                root / "completed.json",
                {
                    "jobs_this_run": n,
                    "execution_receipt": str(segment / "receipt.json"),
                    "record_bindings": len(read(root / "bindings.json")),
                },
            )
        from .dev_report import generate

        report = generate()
        state = (
            "ready-for-pre-freeze-review"
            if report["ready_for_pre_freeze_review"] and not drain[0]
            else "needs-attention"
        )
        controller["status"] = state
        write_json(orchestration / "controller.json", controller)
        if state == "ready-for-pre-freeze-review":
            write_json(
                ROOT / "REVIEW_REQUIRED.json",
                {
                    "status": state,
                    "report": str(ROOT / "PROGRESS.html"),
                    "instruction": "Stop: user approval required before freezing/test.",
                },
            )
    except BaseException as exc:
        receipt.update(status="error", error=repr(exc), ended_at=time.time())
        write_json(segment / "receipt.json", receipt)
        controller.update(status="needs-attention", error=repr(exc))
        write_json(orchestration / "controller.json", controller)
        raise
    finally:
        lock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibration-count", type=int, default=32)
    parser.add_argument("--baseline-calibration", type=Path)
    parser.add_argument("--reuse-calibration", type=Path)
    parser.add_argument(
        "--reservation", type=Path, help="Immutable model ownership allocation for a second machine"
    )
    args = parser.parse_args()
    run(args.calibration_count, args.baseline_calibration, args.reuse_calibration, args.reservation)
