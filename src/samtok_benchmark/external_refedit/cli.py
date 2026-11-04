"""Download/prepare, bounded smoke runs, resumable multi-GPU generation and generation reports for RefEdit-Bench."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time

from samtok_benchmark.io import digest, write_json, sha256_file
from . import MODELS, NUM_CASES
from .data import read, immutable, load_bundle
from .worker import run, stages, verify_config, source_identity

REPO_SRC = Path(__file__).resolve().parents[2]


def runtime_for(model, stage):
    return "pass1" if stage == "tokens" else "v4" if model == "sitedit" else "generation"


# Planning only (never part of a request's identity): median wall seconds per case and stage measured in the
# 2026-11-04 dry run on H100 (single instruction, ~1MP), and a typical model load.
SCHEDULE = {"estimated_case_seconds": {"sitedit": {"tokens": 1.5, "edit": 50}, "qwen21": {"edit": 40},
                                       "qwen2511": {"edit": 75}, "replan": {"plan": 2.5, "edit": 98},
                                       "mirage": {"plan": 5.5, "edit": 67}, "flux3": {"edit": 9},
                                       "mice": {"edit": 6}, "flux2_klein9b": {"edit": 4.5}},
            "estimated_load_seconds": 180, "target_task_seconds": 3000}


def plan_tasks(config, models, case_ids, gpus, target=None):
    """Split each method into case shards (planning estimates only) and order them longest first."""
    schedule = dict(SCHEDULE)
    if target:
        schedule["target_task_seconds"] = target
    tasks = []
    for model in models:
        per_case = sum(schedule["estimated_case_seconds"][model][s] for s in stages(model))
        total = per_case * len(case_ids)
        shards = max(1, min(gpus, len(case_ids), round(total / schedule["target_task_seconds"])))
        for shard in range(shards):
            count = len(case_ids[shard::shards])
            tasks.append({"model": model, "shard": shard, "shards": shards, "cases": count,
                          "estimated_seconds": per_case * count + schedule["estimated_load_seconds"] *
                          len(stages(model))})
    return sorted(tasks, key=lambda t: (-t["estimated_seconds"], t["model"], t["shard"]))


def gpu_used_mib(card):
    try:
        out = subprocess.check_output(["nvidia-smi", "-i", str(card), "--query-gpu=memory.used",
                                       "--format=csv,noheader,nounits"], text=True, timeout=60)
        return float(out.strip().splitlines()[0])
    except Exception:
        return None


def wait_for_gpu(card, max_used_gib, timeout_seconds=1800):
    """Never start on a card that someone else filled; wait for it to drain, then give up."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        used = gpu_used_mib(card)
        if used is not None and used <= max_used_gib * 1024:
            return used
        if time.monotonic() > deadline:
            raise RuntimeError(f"GPU {card} stayed occupied ({used} MiB used)")
        time.sleep(30)


def report(output):
    """Generation-only status with per-case wall time, load time and peak memory; never a quality claim."""
    output = Path(output).resolve()
    plan = read(output / "RUN.json")
    rows = []
    for model in plan["models"]:
        cases, stage_stats = [], {}
        for stage in stages(model):
            walls, infs, loads, peaks, reserved = [], [], [], [], []
            for case in plan["case_ids"]:
                path = output / model / stage / case / "result.json"
                if not path.exists():
                    continue
                result = read(path)
                if result["status"] == "completed":
                    walls.append(result["wall_seconds"])
                    infs.append(result.get("inference_seconds") or 0.0)
                    if result.get("peak_gpu_allocated_bytes"):
                        peaks.append(result["peak_gpu_allocated_bytes"] / 2 ** 30)
                    if result.get("peak_gpu_reserved_bytes"):
                        reserved.append(result["peak_gpu_reserved_bytes"] / 2 ** 30)
                if result.get("load_seconds") is not None:
                    loads.append(result["load_seconds"])
            stage_stats[stage] = {
                "completed": len(walls), "wall_seconds_median": statistics.median(walls) if walls else None,
                "wall_seconds_mean": statistics.fmean(walls) if walls else None,
                "wall_seconds_sum": sum(walls), "inference_seconds_median": statistics.median(infs) if infs else None,
                "load_seconds": loads, "peak_allocated_gib_max": max(peaks) if peaks else None,
                "peak_reserved_gib_max": max(reserved) if reserved else None}
        for case in plan["case_ids"]:
            result, state = {}, "pending"
            for stage in stages(model):
                directory = output / model / stage / case
                if (directory / "result.json").exists():
                    result = read(directory / "result.json")
                    state = result["status"]
                    if state != "completed":
                        result = {"status": "failed", "error": f"{stage}: {result.get('error')}"}
                        break
                elif (directory / "ADMITTED.json").exists():
                    result, state = {"status": "unknown", "error": f"{stage}: admitted without terminal record"}, \
                        "unknown"
                    break
                else:
                    result, state = {}, "pending"
                    break
            cases.append({"case_id": case, "status": state, "output_image": result.get("output_image"),
                          "output_sha256": result.get("output_sha256"), "error": result.get("error"),
                          "fallback_units": result.get("fallback_units"),
                          "placement": (result.get("placement") or {}).get("rule")
                          if isinstance(result.get("placement"), dict) else None})
        rows.append({"model": model, "total": len(cases),
                     "completed": sum(c["status"] == "completed" for c in cases),
                     "failed": sum(c["status"] == "failed" for c in cases),
                     "unknown": sum(c["status"] == "unknown" for c in cases),
                     "pending": sum(c["status"] == "pending" for c in cases),
                     "stages": stage_stats, "cases": cases})
    value = {"scope": plan["scope"], "generation_only": True, "rows": rows,
             "all_generated": all(r["completed"] == r["total"] for r in rows),
             "time": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    write_json(output / "GENERATION_REPORT.json", value)
    return value


def snapshot_sources(output, identity):
    for name, expected in identity.items():
        saved = output / "source_snapshot" / name
        saved.parent.mkdir(parents=True, exist_ok=True)
        if not saved.exists():
            with saved.open("xb") as stream:
                stream.write((REPO_SRC / name).read_bytes())
        if sha256_file(saved) != expected:
            raise ValueError(f"Source snapshot changed: {saved}")


def launch(args):
    config = read(args.config)
    verify_config(config)
    index = load_bundle(args.bundle, args.cases)
    case_ids = args.cases or [i["case_id"] for i in index["cases"]]
    if len(set(case_ids)) != len(case_ids) or not set(case_ids) <= {i["case_id"] for i in index["cases"]}:
        raise ValueError("Unknown or duplicated case IDs")
    output = Path(args.output).resolve()
    formal = Path(config["formal_results_root"]).resolve()
    if args.smoke:
        if not args.cases or len(case_ids) > 3:
            raise ValueError("Smoke requires one to three explicitly chosen case IDs")
        if output.is_relative_to(formal):
            raise ValueError("Smoke artifacts must not enter the formal results directory")
    elif len(case_ids) != NUM_CASES:
        raise ValueError("A formal run must contain all 200 cases; use --smoke for bounded checks")
    if index.get("dryrun") and (not args.smoke or output.is_relative_to(formal)):
        raise ValueError("A dry-run bundle only supports bounded smoke runs outside the formal root")
    cards = args.gpus.split(",")
    if len(cards) != len(set(cards)) or not all(c.isdecimal() for c in cards):
        raise ValueError("GPU IDs must be distinct nonnegative integers")
    if len(args.models) != len(set(args.models)):
        raise ValueError("Duplicated methods would sample the same request twice")
    output.mkdir(parents=True, exist_ok=True)
    lock_stream = (output / "LAUNCH.lock").open("a")
    try:
        fcntl.flock(lock_stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError(f"Another launcher is active on {output}")
    immutable(output / "CONFIG.json", config)
    identity = source_identity()
    plan = {"scope": "smoke" if args.smoke else "full", "bundle": str(Path(args.bundle).resolve()),
            "bundle_digest": index["digest"], "config": str(output / "CONFIG.json"),
            "config_digest": digest(config), "source_code": identity,
            "case_ids": case_ids, "models": args.models, "seed": 42}
    immutable(output / "RUN.json", plan)
    snapshot_sources(output, identity)
    attempt = args.attempt or datetime.now(timezone.utc).strftime("local-%Y%m%dT%H%M%SZ")
    attempt_dir = output / "attempts" / attempt
    attempt_dir.mkdir(parents=True, exist_ok=False)
    logs = output / "logs"
    logs.mkdir(exist_ok=True)
    tasks = plan_tasks(config, args.models, case_ids, len(cards), args.target_task_seconds)
    write_json(attempt_dir / "TASKS.json", {"gpus": cards, "tasks": tasks,
                                            "started": datetime.now(timezone.utc).isoformat()})
    source = Path(config["paths"]["sitedit_source"])
    queue, guard, history = list(tasks), threading.Lock(), []

    def run_task(card, task):
        model = task["model"]
        codes = []
        for stage in stages(model):
            python = config["runtime"][runtime_for(model, stage)]
            paths = [str(REPO_SRC)]
            if model == "sitedit":
                paths += [str(source / "src"), str(source / "third_party/diffsynth"), str(source / "third_party")]
            env = dict(os.environ, CUDA_DEVICE_ORDER="PCI_BUS_ID", CUDA_VISIBLE_DEVICES=card,
                       PYTHONPATH=os.pathsep.join(paths),
                       PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1", OMP_NUM_THREADS="4",
                       TOKENIZERS_PARALLELISM="false", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
            for key in ("IFBENCH_NATIVE_SOURCES", "LD_PRELOAD", "PYTHONHOME", "PYTHONSTARTUP"):
                env.pop(key, None)
            cache = Path(args.cache_dir or output / "cache") / model
            env["TORCHINDUCTOR_CACHE_DIR"] = str(cache / "inductor")
            env["TRITON_CACHE_DIR"] = str(cache / "triton")
            command = [python, "-B", "-m", "samtok_benchmark.external_refedit", "worker",
                       "--bundle", plan["bundle"], "--config", plan["config"], "--output", str(output),
                       "--model", model, "--stage", stage, "--shard", str(task["shard"]),
                       "--shards", str(task["shards"]), "--cases", *case_ids]
            used = wait_for_gpu(card, args.max_used_gib) if not args.no_gpu_gate else None
            name = f"{model}-{stage}-{task['shard']}of{task['shards']}"
            tick = time.monotonic()
            print(f"[{datetime.now(timezone.utc):%H:%M:%S}] GPU {card}: start {name} (used {used} MiB)", flush=True)
            with (logs / f"{name}.log").open("a") as log:
                log.write(json.dumps({"attempt": attempt, "command": command, "gpu": card,
                                      "time": datetime.now(timezone.utc).isoformat()}) + "\n")
                log.flush()
                # Native code may write debug files into its working directory (MICE saves
                # HARD_MASK_smoothpl.png); give every task its own scratch directory inside the run.
                scratch = output / "scratch" / name
                scratch.mkdir(parents=True, exist_ok=True)
                code = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                                      cwd=scratch).returncode
            seconds = time.monotonic() - tick
            codes.append(code)
            print(f"[{datetime.now(timezone.utc):%H:%M:%S}] GPU {card}: end {name} exit {code} {seconds:.0f}s",
                  flush=True)
            with guard:
                history.append({"task": name, "gpu": card, "exit": code, "seconds": seconds})
            # A normal case failure still lets the editor process the other successful plans.
            if code not in (0, 1):
                break
        return codes

    def lane(card):
        codes = []
        while True:
            with guard:
                if not queue:
                    return codes
                task = queue.pop(0)
            codes += run_task(card, task)

    with ThreadPoolExecutor(max_workers=len(cards)) as pool:
        results = list(pool.map(lane, cards))
    value = report(output)
    summary = {"attempt": attempt, "finished": datetime.now(timezone.utc).isoformat(), "history": history,
               "all_generated": value["all_generated"],
               "counts": {r["model"]: {k: r[k] for k in ("completed", "failed", "unknown", "pending")}
                          for r in value["rows"]}}
    write_json(attempt_dir / "ATTEMPT.json", summary)
    print(json.dumps({"all_generated": value["all_generated"], "output": str(output), "counts": summary["counts"]},
                     indent=2), flush=True)
    return 0 if value["all_generated"] and not any(c not in (0,) for codes in results for c in codes) else 1


def release(output, model, stage, case, reason):
    """The logged, manual way out for an admission without a terminal record (e.g. a killed worker).

    The case directory is moved aside with its partial files; a later launch then samples the request again with
    the same inputs and seed. Never applies to a request that has a terminal record."""
    output = Path(output).resolve()
    directory = output / model / stage / case
    if (directory / "result.json").exists():
        raise ValueError("A request with a terminal record is never released")
    if not (directory / "ADMITTED.json").exists():
        raise ValueError("No open admission to release")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = output / "_released" / model / stage / f"{case}-{stamp}"
    target.parent.mkdir(parents=True, exist_ok=True)
    admission = read(directory / "ADMITTED.json")
    directory.rename(target)
    entry = {"model": model, "stage": stage, "case_id": case, "reason": reason, "moved_to": str(target),
             "admission": admission, "time": datetime.now(timezone.utc).isoformat()}
    with (output / "RELEASES.jsonl").open("a") as stream:
        stream.write(json.dumps(entry) + "\n")
    return entry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="build the public/private bundle from an extracted dataset")
    p.add_argument("--dataset", required=True)
    p.add_argument("--bundle", required=True)
    p = sub.add_parser("run", help="foreground multi-GPU launcher")
    for key in ("bundle", "config", "output"):
        p.add_argument(f"--{key}", required=True)
    p.add_argument("--models", choices=MODELS, nargs="+", default=list(MODELS))
    p.add_argument("--gpus", default="0")
    p.add_argument("--cases", nargs="+")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--attempt", help="unique attempt label (logs and receipts); never reused")
    p.add_argument("--cache-dir", help="compile caches; defaults to <output>/cache")
    p.add_argument("--max-used-gib", type=float, default=8.0,
                   help="do not start a task while another process uses more than this on the card")
    p.add_argument("--no-gpu-gate", action="store_true")
    p.add_argument("--target-task-seconds", type=float,
                   help="shard size target (planning only); defaults to the configuration's schedule")
    p = sub.add_parser("worker")
    for key in ("bundle", "config", "output", "model", "stage"):
        p.add_argument(f"--{key}", required=True)
    p.add_argument("--cases", nargs="+", required=True)
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=1)
    p = sub.add_parser("report")
    p.add_argument("--output", required=True)
    p = sub.add_parser("release", help="move aside one admission without a terminal record (logged)")
    for key in ("output", "model", "stage", "case", "reason"):
        p.add_argument(f"--{key}", required=True)
    p = sub.add_parser("score-export", help="official masked/full judge inputs bound to output SHAs")
    for key in ("bundle", "run", "output"):
        p.add_argument(f"--{key}", required=True)
    p.add_argument("--models", choices=MODELS, nargs="+", default=list(MODELS))
    p = sub.add_parser("judge", help="official Modified VIEScore requests for one exported method")
    p.add_argument("--job", required=True)
    p.add_argument("--judge-config", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--ledger", help="append-only paid-request ledger shared by all paid jobs")
    p.add_argument("--max-paid-requests", type=int, help="hard cap on API call attempts in the ledger")
    p.add_argument("--cases", nargs="+")
    p.add_argument("--prompt-cache")
    p.add_argument("--retry-unparsable", action="store_true")
    p = sub.add_parser("aggregate", help="per-split official means and source-paired bootstrap")
    p.add_argument("--scores", required=True)
    p.add_argument("--models", choices=MODELS, nargs="+", required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        from .data import prepare
        result = prepare(args.dataset, args.bundle)
        print(f"Prepared {len(result['cases'])} requests at {args.bundle}")
    elif args.command == "worker":
        result = run(args.bundle, args.config, args.output, args.model, args.stage,
                     args.cases, args.shard, args.shards)
        print(json.dumps(result), flush=True)
        return 2 if result.get("fatal") else int(result["failed"] > 0 or result["unknown"] > 0)
    elif args.command == "report":
        print(json.dumps(report(args.output), indent=2))
    elif args.command == "release":
        print(json.dumps(release(args.output, args.model, args.stage, args.case, args.reason), indent=2))
    elif args.command == "run":
        return launch(args)
    elif args.command == "score-export":
        from .score import export
        for model in args.models:
            job = export(args.bundle, args.run, Path(args.output) / model, model)
            print(f"{model}: {job['valid_outputs']}/{job['total']} outputs bound for judging", flush=True)
    elif args.command == "judge":
        from .score import judge
        counts = judge(args.job, args.judge_config, args.output, args.ledger, args.max_paid_requests,
                       args.cases, args.prompt_cache, args.retry_unparsable)
        print(json.dumps(counts), flush=True)
        return int(counts["errors"] > 0 or counts["unparsable"] > 0)
    elif args.command == "aggregate":
        from .score import aggregate
        print(json.dumps(aggregate(args.scores, args.models), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
