"""Resumable local-model Judge; one immutable admission and answer per key."""

from collections import Counter
import fcntl
import importlib.metadata
import os
from pathlib import Path
import signal
import socket
import time
from types import SimpleNamespace

from .bundle import load
from .common import checked, digest, read, save, sha
from .rubric import conversation, parse


def check_model(model, config):
    model = Path(model)
    if read(model / "download_record.json")["revision"] != config["revision"]:
        raise ValueError("Wrong model revision")
    for name, expected in config["model_config_sha256"].items():
        checked(model / name, expected)
    for name, size in config["weight_bytes"].items():
        if (model / name).stat().st_size != size:
            raise ValueError(f"Missing/truncated model shard: {name}")


def effective(raw, identity, key):
    value = {"identity": identity, "request_key": key, "raw_digest": digest(raw)}
    try:
        value.update(status="scored", scores=parse(raw["answer"]))
    except (ValueError, KeyError, TypeError) as exc:
        value.update(status="judge_failed", error=f"{type(exc).__name__}: {exc}")
    return value


def restore(root, keys, identity):
    """One startup scan; no repeated NAS existence sweep between batches."""
    root = Path(root)
    maps = {
        kind: {p.stem: p for p in (root / kind).glob("*.json")}
        for kind in ("admissions", "raw", "effective")
    }
    counters = Counter(admitted=0, answered=0, scored=0, judge_failed=0)
    pending, unknown = [], []
    for key in keys:
        records = {kind: read(paths[key]) for kind, paths in maps.items() if key in paths}
        for record in records.values():
            if record.get("identity") != identity or record.get("request_key") != key:
                raise ValueError(f"Cached Judge identity mismatch: {key}")
        if "effective" in records and not {"admissions", "raw"} <= records.keys():
            raise ValueError(f"Effective without admission/raw: {key}")
        if "raw" in records and "admissions" not in records:
            raise ValueError(f"Raw answer without admission: {key}")
        if "admissions" in records:
            counters["admitted"] += 1
        if "raw" in records:
            counters["answered"] += 1
            derived = effective(records["raw"], identity, key)
            if "effective" in records and records["effective"] != derived:
                raise ValueError(f"Effective record differs from raw: {key}")
            if "effective" not in records:
                save(root / "effective" / f"{key}.json", derived, immutable=True)
            counters[derived["status"]] += 1
        elif "admissions" in records:
            unknown.append(key)
        else:
            pending.append(key)
    return counters, pending, unknown


def run(bundle, output, attempt, model=None, smoke=False):
    from samtok_benchmark.v2.judge import Backend

    bundle, output = Path(bundle).resolve(), Path(output).resolve()
    plan = load(bundle)
    if not smoke and output != Path(plan["results_root"]).resolve():
        raise ValueError("Formal output must equal frozen results_root")
    if smoke and output == Path(plan["results_root"]).resolve():
        raise ValueError("Smoke must never enter formal results")
    config = plan["configuration"]
    versions = {k: importlib.metadata.version(k) for k in config["packages"]}
    if versions != config["packages"]:
        raise ValueError(f"Runtime versions differ: {versions}")
    engine = dict(config["engine"])
    if smoke:
        engine.update(tensor_parallel_size=4, batch_size=4)
    selected = {
        b["request_key"]
        for b in plan["bindings"]
        if not smoke or b["case_id"] in plan["smoke_case_ids"]
    }
    keys = sorted(selected)
    this = Path(__file__)
    source = {
        p.name: sha(p) for p in (this, this.with_name("rubric.py"), this.with_name("common.py"))
    }
    import samtok_benchmark.v2.judge as native

    source["native_backend"] = sha(native.__file__)
    identity = digest(
        {
            "plan_digest": plan["digest"],
            "engine": engine,
            "versions": versions,
            "source": source,
            "smoke": smoke,
            "keys": keys,
        }
    )
    output.mkdir(parents=True, exist_ok=True)
    lock = (output / "worker.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    save(
        output / "CONFIGURATION.json",
        {
            "identity": identity,
            "plan_digest": plan["digest"],
            "engine": engine,
            "packages": versions,
            "source": source,
            "smoke": smoke,
            "request_keys": keys,
        },
        immutable=True,
    )
    state, pending, unknown = restore(output, keys, identity)
    start = time.time()
    stop = []
    old_handlers = {}
    for sig in (signal.SIGUSR1, signal.SIGTERM, signal.SIGINT):
        old_handlers[sig] = signal.signal(sig, lambda signum, frame: stop.append(signum))
    runtime = {
        "attempt": attempt,
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "started_at": start,
        "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "engine": engine,
        "identity": identity,
    }
    save(output / "attempts" / attempt / "STARTED.json", runtime, immutable=True)

    def progress(stage, **extra):
        value = {
            **runtime,
            "stage": stage,
            "updated_at": time.time(),
            "total": len(keys),
            **dict(state),
            "pending": len(keys) - state["admitted"],
            "unknown": state["admitted"] - state["answered"],
            "elapsed_seconds": time.time() - start,
            **extra,
        }
        save(output / "progress.json", value)
        print(__import__("json").dumps(value), flush=True)
        return value

    try:
        if unknown:
            progress("blocked_unknown_admissions", unknown_keys=unknown)
            raise RuntimeError(f"{len(unknown)} admitted requests have no raw answer; do not retry")
        progress("verifying_model" if pending else "completed")
        if not pending:
            return progress("completed")
        model = Path(model or config["model"])
        check_model(model, config)
        args = SimpleNamespace(
            model=str(model),
            **engine,
            **{k: config["decode"][k] for k in ("max_tokens", "reasoning_effort")},
        )
        progress("loading")
        load_started = time.time()
        backend = Backend(args, max_images=10)
        progress("running", load_seconds=time.time() - load_started)
        for offset in range(0, len(pending), engine["batch_size"]):
            if stop:
                break
            batch = pending[offset : offset + engine["batch_size"]]
            conversations = [conversation(bundle, plan["requests"][key]) for key in batch]
            batch_start = time.time()
            for key in batch:
                save(
                    output / "admissions" / f"{key}.json",
                    {
                        "identity": identity,
                        "request_key": key,
                        "attempt": attempt,
                        "admitted_at": time.time(),
                    },
                    immutable=True,
                )
                state["admitted"] += 1
            answers = backend.generate(conversations)
            if len(answers) != len(batch):
                raise RuntimeError("Judge returned incomplete batch; preserve all admissions")
            # Persist the entire raw batch first; parsing cannot lose another answer.
            raws = []
            for key, answer in zip(batch, answers):
                raw = {
                    "identity": identity,
                    "request_key": key,
                    "answer": answer,
                    "answered_at": time.time(),
                    "attempt": attempt,
                }
                save(output / "raw" / f"{key}.json", raw, immutable=True)
                raws.append(raw)
                state["answered"] += 1
            for key, raw in zip(batch, raws):
                record = effective(raw, identity, key)
                save(output / "effective" / f"{key}.json", record, immutable=True)
                state[record["status"]] += 1
            seconds = time.time() - batch_start
            save(
                output / "attempts" / attempt / f"batch-{offset:06d}.json",
                {
                    "keys": batch,
                    "seconds": seconds,
                    "prompt_tokens": [r["answer"]["prompt_tokens"] for r in raws],
                    "output_tokens": [r["answer"]["output_tokens"] for r in raws],
                },
                immutable=True,
            )
            progress("running", last_batch_seconds=seconds)
        final = progress(
            "stopped" if state["answered"] < len(keys) else "completed", stop_signals=stop
        )
        save(output / "attempts" / attempt / "FINISHED.json", final, immutable=True)
        return final
    except Exception as exc:
        value = progress("error", error=f"{type(exc).__name__}: {exc}")
        save(output / "attempts" / attempt / "ERROR.json", value, immutable=True)
        raise
    finally:
        for sig, previous in old_handlers.items():
            signal.signal(sig, previous)
        lock.close()
