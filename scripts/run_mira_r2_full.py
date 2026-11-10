#!/usr/bin/env python3
"""Evaluate one replacement DiT checkpoint through the unchanged full MIRA framework."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from samtok_benchmark.external_mira.data import immutable, load_bundle, read  # noqa: E402
from samtok_benchmark.external_mira.score import ensure_evaluator, export  # noqa: E402
from samtok_benchmark.external_mira.worker import source_identity, verify_config  # noqa: E402
from samtok_benchmark.io import digest, sha256_file, write_json  # noqa: E402

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
PROFILE = read(REPO / "configs/external/mira_r2_1000.json")
BASE = Path(PROFILE["baseline_root"])
QUALITY = NAS / "experiments2/SAMTokEdit/quality_anchor_20261104"
ADAPTER = Path(PROFILE["dit_adapter"])
GPUS = (4, 5, 6, 7)
FIELDS = ("prompt_following", "consistency", "perceptual_quality")
METRICS = ("PF", "Cons", "PQ", "Overall")


def now():
    return datetime.now(timezone.utc).isoformat()


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def batch_cases(case_ids):
    if len(case_ids) != 200 or len(set(case_ids)) != 200:
        raise ValueError("Expected exactly 200 distinct full-benchmark sources")
    return {f"lane{i}_batch{j // 10:02d}": case_ids[i::4][j:j + 10]
            for i in range(4) for j in range(0, 50, 10)}


def credential_env(key_file=None):
    env = dict(os.environ)
    key_file = key_file or env.get("MIRA_API_KEY_FILE")
    if key_file:
        if not Path(key_file).is_file():
            raise FileNotFoundError("The specified MIRA API credential file is unavailable")
        env["MIRA_API_KEY_FILE"] = str(Path(key_file).resolve())
    elif not env.get("OPENAI_API_KEY"):
        raise RuntimeError("Set MIRA_API_KEY_FILE or OPENAI_API_KEY before requesting paid judging")
    return env


def transient_error(text):
    return any(term in text for term in (
        "RateLimitError", "APIConnectionError", "APITimeoutError", "InternalServerError",
        "RemoteProtocolError", "ConnectionResetError", "Error code: 429",
        "Error code: 502", "Error code: 503", "Error code: 504"))


def retry_delay(failures):
    return min(300, 30 * 2 ** min(max(failures - 1, 0), 4))


def judge_complete(directory, expected):
    path = directory / "scores/per_image_results.jsonl"
    if not path.exists():
        return False
    rows = read_rows(path)
    cases = [Path(row["image"]).stem for row in rows]
    if len(cases) != len(set(cases)) or not set(cases) <= set(expected):
        raise ValueError("Duplicate or unexpected committed Judge source")
    return set(cases) == set(expected)


def preserve_provenance(path, value):
    """Allow coordinator maintenance while preserving the original execution record."""
    if path.exists():
        previous = read(path)
        if {k: v for k, v in previous.items() if k != "script_sha256"} != (
                {k: v for k, v in value.items() if k != "script_sha256"}):
            raise ValueError("Scientific inputs or execution partition changed")
        return
    immutable(path, value)


def score_vector(means):
    import numpy as np

    means = np.asarray(means, dtype=float)
    return np.concatenate((means, np.sqrt(np.minimum(means[..., :1], means[..., 1:2])
                                          * means[..., 2:3])), axis=-1)


def statistics(old, new, case_ids):
    import numpy as np

    if not case_ids or len(case_ids) != len(set(case_ids)):
        raise ValueError("Source IDs must be nonempty and distinct")
    if set(old) != set(case_ids) or set(new) != set(case_ids):
        raise ValueError("Paired comparison requires exactly the same scored sources")
    arrays = [np.array([rows[c] for c in case_ids], dtype=float) for rows in (old, new)]
    if any(a.shape != (len(case_ids), 3) or not np.isfinite(a).all()
           or not ((0 <= a) & (a <= 10)).all() for a in arrays):
        raise ValueError("Invalid per-source score vector")
    indices = np.random.default_rng(20261027).integers(0, len(case_ids),
                                                     size=(10000, len(case_ids)))
    means = [score_vector(a.mean(axis=0)) for a in arrays]
    draws = [score_vector(a[indices].mean(axis=1)) for a in arrays]
    return {
        "rows": {name: {"count": len(case_ids), **dict(zip(METRICS, value.tolist())),
                         "CI95": dict(zip(METRICS, np.quantile(sample, [.025, .975],
                                                               axis=0).T.tolist()))}
                 for name, value, sample in zip(("v4_S2_16000", "R2_1000"), means, draws)},
        "paired_R2_minus_v4": {
            "count": len(case_ids), **dict(zip(METRICS, (means[1] - means[0]).tolist())),
            "CI95": dict(zip(METRICS, np.quantile(draws[1] - draws[0], [.025, .975],
                                                   axis=0).T.tolist()))},
        "bootstrap": {"unit": "source image", "replicates": 10000, "seed": 20261027,
                      "shared_indices_sha256": hashlib.sha256(
                          indices.astype("<i8").tobytes()).hexdigest()},
    }


def append_section(content, doc=None):
    """Append one complete section without relying on unsupported NAS file locks."""
    doc = Path(doc) if doc is not None else QUALITY / "RESULTS_V5.md"
    local_lock = Path("/tmp/mira_r2_results_v5_append.lock")
    with local_lock.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        before = doc.read_bytes()
        text = before.decode()
        if content.strip() in text:
            return
        if "MIRA-Bench 全量 R2@1000" in text or "### 16.6" in text or "## 16.6" in text:
            raise ValueError("Section 16.6 already exists with different content")
        if doc.read_bytes() != before:
            raise RuntimeError("Results document changed before append; retry after inspection")
        extra = ("\n\n" + content).encode()
        fd = os.open(str(doc), os.O_WRONLY | os.O_APPEND)
        try:
            if os.write(fd, extra) != len(extra):
                raise RuntimeError("Short append; inspect document before retrying")
            try:
                os.fsync(fd)
            except OSError as error:
                if error.errno not in (22, 38):  # Some NAS backends also omit fsync.
                    raise
        finally:
            os.close(fd)
        if doc.read_bytes() != before + extra:
            raise RuntimeError("Concurrent document change detected after append; inspect contents")


def finish(root, plan, batches, append_doc=None):
    if (root / "REPORT.json").exists() and (root / "SUMMARY_CONTENT.json").exists():
        existing = read(root / "REPORT.json")
        if existing["case_ids"] != plan["case_ids"] or existing["generation_config_sha256"] != (
                sha256_file(root / "run_001/CONFIG.json")):
            raise ValueError("Existing report belongs to a different experiment")
        if append_doc is not None:
            append_section(read(root / "SUMMARY_CONTENT.json")["markdown"], append_doc)
        return existing
    old_dir = BASE / "scores_gpt54_001/sitedit"
    old_job = read(old_dir / "JOB.json")
    old_rows = read_rows(old_dir / "scores/per_image_results.jsonl")
    old = {Path(r["image"]).stem: [r[k] for k in FIELDS] for r in old_rows}
    if len(old) != len(old_rows):
        raise ValueError("Duplicate v4 score")
    new, evidence, costs = {}, {}, []
    baseline_bindings = {Path(b["image"]).stem: b for b in old_job["bindings"]}
    for batch in batches:
        directory = root / "scores_gpt54" / batch / "sitedit"
        job = read(directory / "JOB.json")
        if job["canonical_sha256"] != old_job["canonical_sha256"] or (
                job["evaluator"] != old_job["evaluator"] or
                job["evaluator_source"] != old_job["evaluator_source"]):
            raise ValueError("New and v4 judges do not share canonical data and configuration")
        if read(directory / "JUDGE.json")["job_sha256"] != sha256_file(directory / "JOB.json"):
            raise ValueError("Judge job binding mismatch")
        bindings = {Path(b["image"]).stem: b for b in job["bindings"]}
        rows = read_rows(directory / "scores/per_image_results.jsonl")
        if len(rows) != job["total"] or job["unscorable"]:
            raise ValueError("Incomplete batch; missing scores will not be imputed")
        for row in rows:
            cid = Path(row["image"]).stem
            if cid in new or cid not in bindings or row["num_crops"] != 5:
                raise ValueError("Duplicate or unexpected score")
            binding = bindings[cid]
            result_path = root / "run_001/sitedit/edit" / cid / "result.json"
            result = read(result_path)
            if (sha256_file(result_path) != binding["result_sha256"] or
                    sha256_file(result["output_image"]) != binding["output_sha256"] or
                    binding["source_sha256"] != baseline_bindings[cid]["source_sha256"]):
                raise ValueError("Edited image or source binding changed")
            new[cid] = [row[k] for k in FIELDS]
            costs.append({"case_id": cid, "stage": "edit",
                          "inference_seconds": result["inference_seconds"],
                          "peak_gpu_allocated_bytes": result["peak_gpu_allocated_bytes"]})
        evidence[batch] = {"job_sha256": sha256_file(directory / "JOB.json"),
                           "scores_sha256": sha256_file(directory / "scores/per_image_results.jsonl")}
    report = statistics(old, new, plan["case_ids"])
    report.update(schema="mira.r2.full.report.v1", case_ids=plan["case_ids"],
                  completed_at=now(), new_root=str(root), baseline_root=str(BASE),
                  generation_config_sha256=sha256_file(root / "run_001/CONFIG.json"),
                  baseline_scores_sha256=sha256_file(old_dir / "scores/per_image_results.jsonl"),
                  baseline_job_sha256=sha256_file(old_dir / "JOB.json"), batches=evidence,
                  per_case={c: {"v4": old[c], "R2": new[c]} for c in plan["case_ids"]},
                  costs=costs,
                  aggregation="sqrt(min(mean(PF), mean(Cons)) * mean(PQ))",
                  score_range=[0, 10],
                  judge_calls=sum(len(list((root / "scores_gpt54" / b / "sitedit/judge_requests")
                                          .glob("*.request.json"))) for b in batches),
                  note="All 200 images. Original v4 judge answers are read-only; R2 is newly judged. "
                       "Shared judge configuration, distinct judging dates. No baseline resampling.")
    immutable(root / "REPORT.json", report)
    lines = ["### 16.6 MIRA-Bench 全量 R2@1000", "",
             "MIRA-Bench 全量 200 张图，每图 5 项联合编辑。仅将 v4 的 DiT adapter 换为 "
             "R2@1000；Pass1 step 2000、raw SAMTok TE、40 步、LoRA 强度 1.0、token guidance 2、"
             "seed 42 及 aa5a414 源码保持不变。所有图像均重新生成。", "",
             "沿用原生 MIRA 提示词与 GPT-5.4 评判，PF/Cons/PQ 均为 0–10 分，越高越好。"
             "Overall = sqrt(min(mean PF, mean Cons) × mean PQ)。v4 使用已有全量逐图分数，未重判。", "",
             "| 检查点 | 已评分 | PF ↑ | Cons ↑ | PQ ↑ | Overall ↑ |",
             "|---|---:|---:|---:|---:|---:|"]
    for key, label in (("v4_S2_16000", "v4 / S2@16000"), ("R2_1000", "R2@1000")):
        row = report["rows"][key]
        lines.append("| " + " | ".join([label, "200/200", *[f"{row[m]:.3f}" for m in METRICS]]) + " |")
    lines += ["", "R2@1000 − v4 的配对差（原始分值差；同源图 10,000 次配对 bootstrap，"
              "seed 20261027）：", "", "| 指标 | 配对差 | 95% CI |", "|---|---:|---:|"]
    pair = report["paired_R2_minus_v4"]
    for metric in METRICS:
        lo, hi = pair["CI95"][metric]
        lines.append(f"| {metric} | {pair[metric]:+.3f} | [{lo:+.3f}, {hi:+.3f}] |")
    lines += ["", f"- 新结果与逐图证据：`{root}`。",
              f"- 原 v4 逐图评分：`{old_dir / 'scores/per_image_results.jsonl'}`。",
              f"- 配置、配对统计及完整精度数值：`{root / 'REPORT.json'}`。",
              "- 对比保留全部 200 张图，未筛选成功样例；两轮 Judge 使用相同配置、不同执行日期。", ""]
    content = "\n".join(lines)
    immutable(root / "SUMMARY_CONTENT.json", {"markdown": content})
    (root / "REPORT.md").write_text(content)
    if append_doc is not None:
        append_section(content, append_doc)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=BASE / PROFILE["default_run_name"])
    parser.add_argument("--scratch", type=Path,
                        default=Path(PROFILE["scratch"]))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--report-only", action="store_true",
                        help="Complete saved score aggregation without GPU or API calls")
    parser.add_argument("--key-file", type=Path, help="Defaults to MIRA_API_KEY_FILE")
    parser.add_argument("--append-results", type=Path,
                        help="Explicitly append section 16.6 to a results Markdown file")
    args = parser.parse_args()
    root, scratch = args.root.resolve(), args.scratch.resolve()
    if root.parent != BASE or root.name in {
            "run_001", "scores_gpt54_001", "audited_report_v2", "execution_audit",
            "overlap_audit", "diagnostics"} or scratch.is_relative_to(BASE):
        raise ValueError("Unexpected output or scratch root")
    if args.prepare_only and args.report_only:
        parser.error("--prepare-only and --report-only are mutually exclusive")
    if args.report_only:
        plan = read(root / "run_001/RUN.json")
        report = finish(root, plan, batch_cases(plan["case_ids"]), args.append_results)
        print(json.dumps(report["rows"]), flush=True)
        return 0
    if (root / "STATUS.json").exists() and read(root / "STATUS.json").get("status") == "complete":
        print(f"Run already complete: {root}. Use report_mira_r2.py for read-only verification.")
        return 0
    root.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    lock = (scratch / "pipeline.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    config = read(BASE / "run_001/CONFIG.json")
    original = deepcopy(config)
    config["sitedit"]["dit_adapter"] = str(ADAPTER)
    check = deepcopy(config)
    check["sitedit"]["dit_adapter"] = original["sitedit"]["dit_adapter"]
    if check != original:
        raise ValueError("A configuration other than dit_adapter changed")
    verify_config(config)
    previous_plan = read(BASE / "run_001/RUN.json")
    source = source_identity()
    if source != previous_plan["source_code"]:
        raise ValueError("Native MIRA or frozen helper source differs from v4")
    bundle = previous_plan["bundle"]
    index = load_bundle(bundle, previous_plan["case_ids"])
    if index["digest"] != previous_plan["bundle_digest"] or len(index["cases"]) != 200:
        raise ValueError("Expected the original full 200-image input bundle")
    run = root / "run_001"
    immutable(run / "CONFIG.json", config)
    plan = dict(previous_plan, config=str(run / "CONFIG.json"), config_digest=digest(config),
                models=["sitedit"])
    immutable(run / "RUN.json", plan)
    for name, expected in source.items():
        dst = run / "source_snapshot" / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            with dst.open("xb") as stream:
                stream.write((REPO / "src" / name).read_bytes())
        if sha256_file(dst) != expected:
            raise ValueError("Snapshot mismatch")
    judge_config = read(BASE / "JUDGE_CONFIG.json")
    if judge_config != read(BASE / "scores_gpt54_001/sitedit/JOB.json")["evaluator"]:
        raise ValueError("Baseline judge configuration mismatch")
    immutable(root / "JUDGE_CONFIG.json", judge_config)
    evaluator = ensure_evaluator(judge_config["source"])
    preserve_provenance(root / "PROVENANCE.json", {
        "schema": "mira.r2.full.v1", "original_config": str(BASE / "run_001/CONFIG.json"),
        "original_config_sha256": sha256_file(BASE / "run_001/CONFIG.json"),
        "only_generation_parameter_changed": "sitedit.dit_adapter",
        "new_adapter": str(ADAPTER),
        "adapter_files": {p.name: sha256_file(p) for p in sorted(ADAPTER.iterdir()) if p.is_file()},
        "source_code": source, "gpus": list(GPUS), "fresh_pass1": True,
        "cases": plan["case_ids"], "judge_partition": "20 fixed 10-source batches; four API lanes",
        "script_sha256": sha256_file(__file__),
        "baseline_scores_sha256": sha256_file(BASE / "scores_gpt54_001/sitedit/scores/per_image_results.jsonl")})
    controller = scratch / "controllers" / (sha256_file(__file__) + ".py")
    controller.parent.mkdir(exist_ok=True)
    if not controller.exists():
        with controller.open("xb") as stream:
            stream.write(Path(__file__).read_bytes())
    batches = batch_cases(plan["case_ids"])
    views = scratch / "judge_views"
    for name, cases in batches.items():
        view = views / name
        immutable(view / "RUN.json", dict(plan, case_ids=cases))
        if not (view / "sitedit").is_symlink():
            (view / "sitedit").symlink_to(run / "sitedit", target_is_directory=True)
    if args.prepare_only:
        print(json.dumps({"prepared": True, "root": str(root), "case_count": 200}), flush=True)
        return 0
    credentials = credential_env(args.key_file)
    gpu_locks = []
    for name in ("claude_gpu_4_5.lock", "claude_gpu_6_7.lock"):
        handle = (Path("/tmp") / name).open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        gpu_locks.append(handle)
    available = subprocess.check_output(["nvidia-smi", "--query-gpu=index,memory.used,memory.free",
                                         "--format=csv,noheader,nounits"], text=True)
    for line in available.splitlines():
        card, used, free = map(int, line.split(","))
        if card in GPUS and (used > 2300 or free < 70000):
            raise RuntimeError(f"GPU {card} has another workload; nothing started")
    logs = scratch / "logs"
    logs.mkdir(exist_ok=True)
    children, mutex = {}, threading.Lock()
    stopping = threading.Event()
    env_base = dict(credentials, PYTHONPATH=str(REPO / "src"), PYTHONDONTWRITEBYTECODE="1",
                    PYTHONUNBUFFERED="1", OMP_NUM_THREADS="4",
                    TOKENIZERS_PARALLELISM="false", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    env_base.pop("LD_PRELOAD", None)
    env_base.pop("IFBENCH_NATIVE_SOURCES", None)

    def execute(command, env, logfile):
        if stopping.is_set():
            raise RuntimeError("Pipeline is stopping")
        with logfile.open("a") as log:
            with mutex:
                process = subprocess.Popen(command, cwd=REPO, env=env, stdout=log,
                                           stderr=subprocess.STDOUT)
                children[process.pid] = process
            try:
                return process.wait()
            finally:
                with mutex:
                    children.pop(process.pid, None)

    def stop(signum, frame):
        stopping.set()
        with mutex:
            for process in children.values():
                if process.poll() is None:
                    process.terminate()
        raise KeyboardInterrupt(f"Received signal {signum}")

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def lane(i, card):
        method = Path(config["paths"]["sitedit_source"])
        env = dict(env_base, CUDA_VISIBLE_DEVICES=str(card), MASTER_PORT=str(44000 + card),
                   PYTHONPATH=os.pathsep.join(map(str, (REPO / "src", method / "src",
                                                       method / "third_party/diffsynth", method / "third_party"))),
                   TORCHINDUCTOR_CACHE_DIR=f"/tmp/ifbench/mira_r2_full_20261110/gpu{card}/inductor",
                   TRITON_CACHE_DIR=f"/tmp/ifbench/mira_r2_full_20261110/gpu{card}/triton")
        for stage, runtime in (("tokens", "pass1"), ("edit", "v4")):
            command = [config["runtime"][runtime], "-B", "-u", "-m", "samtok_benchmark.external_mira",
                       "worker", "--bundle", bundle, "--config", plan["config"], "--output", str(run),
                       "--model", "sitedit", "--stage", stage, "--shard", str(i), "--shards", "4",
                       "--cases", *plan["case_ids"]]
            print(f"{now()} GPU {card}: start {stage}", flush=True)
            code = execute(command, env, logs / f"gpu{card}_{stage}.log")
            print(f"{now()} GPU {card}: {stage} exit={code}", flush=True)
            if code != 0:
                raise RuntimeError(f"GPU {card} {stage} failed with exit {code}; inspect preserved log")
        return card

    def judge_batch(name):
        directory = root / "scores_gpt54" / name / "sitedit"
        export(bundle, views / name, directory, "sitedit", config, evaluator, judge_config)
        if judge_complete(directory, batches[name]):
            return name
        command = [config["runtime"]["generation"], "-B", "-u", "-m",
                   "samtok_benchmark.external_mira", "judge", "--job", str(directory / "JOB.json")]
        attempts = read(directory / "ATTEMPTS.json") if (directory / "ATTEMPTS.json").exists() else []
        failures = 0
        while not stopping.is_set():
            attempt = len(attempts) + 1
            log = logs / f"judge_{name}_{attempt}.log"
            started = now()
            code = execute(command, dict(env_base, CUDA_VISIBLE_DEVICES=""), log)
            attempts.append({"attempt": attempt, "started_at": started, "finished_at": now(),
                             "exit_code": code, "log": str(log)})
            write_json(directory / "ATTEMPTS.json", attempts)
            if code == 0:
                if not judge_complete(directory, batches[name]):
                    raise RuntimeError(f"Judge {name} exited with missing committed scores")
                print(f"{now()} Judge {name}: complete", flush=True)
                return name
            text = log.read_text()
            if not transient_error(text):
                break
            failures += 1
            delay = retry_delay(failures)
            print(f"{now()} Judge {name}: transient error; resume missing answers in {delay}s", flush=True)
            stopping.wait(delay)
        raise RuntimeError(f"Judge {name} failed; original answers and requests preserved")

    token_done, edit_done, judge_tasks = {}, {}, {}
    started = now()
    write_json(root / "STATUS.json", {"status": "starting", "started_at": started,
                                      "pipeline_pid": os.getpid(), "case_count": 200})
    try:
        with ThreadPoolExecutor(max_workers=4) as gen_pool, ThreadPoolExecutor(max_workers=4) as judge_pool:
            generators = [gen_pool.submit(lane, i, card) for i, card in enumerate(GPUS)]
            last_print = 0
            while True:
                for future in generators:
                    if future.done():
                        future.result()
                for stage, completed in (("tokens", token_done), ("edit", edit_done)):
                    for cid in plan["case_ids"]:
                        if cid in completed:
                            continue
                        path = run / "sitedit" / stage / cid / "result.json"
                        if path.exists():
                            completed[cid] = read(path)["status"]
                for name, cases in batches.items():
                    if name not in judge_tasks and all(c in edit_done for c in cases):
                        if any(edit_done[c] != "completed" for c in cases):
                            raise RuntimeError(f"Generation failure in {name}; no score imputation")
                        judge_tasks[name] = judge_pool.submit(judge_batch, name)
                for future in judge_tasks.values():
                    if future.done():
                        future.result()
                scored = 0
                for name in judge_tasks:
                    path = root / "scores_gpt54" / name / "sitedit/scores/per_image_results.jsonl"
                    if path.exists():
                        # Last newline is the official committed-record boundary.
                        data = path.read_text()
                        scored += len(data.splitlines()) - int(bool(data) and not data.endswith("\n"))
                status = {"status": "running", "started_at": started, "updated_at": now(),
                          "pipeline_pid": os.getpid(), "tokens": len(token_done), "generated": len(edit_done),
                          "scored": scored, "total": 200, "generation_finished": all(f.done() for f in generators),
                          "judge_batches_submitted": len(judge_tasks),
                          "judge_batches_finished": sum(f.done() for f in judge_tasks.values())}
                write_json(root / "STATUS.json", status)
                if time.monotonic() - last_print >= 30:
                    print(json.dumps(status), flush=True)
                    last_print = time.monotonic()
                if all(f.done() for f in generators):
                    for handle in gpu_locks:
                        handle.close()
                    gpu_locks.clear()
                    if len(judge_tasks) == len(batches) and all(f.done() for f in judge_tasks.values()):
                        break
                time.sleep(10)
        report = finish(root, plan, batches, args.append_results)
        write_json(root / "STATUS.json", {"status": "complete", "started_at": started,
                                          "finished_at": now(), "generated": 200, "scored": 200,
                                          "report": str(root / "REPORT.json"),
                                          "appended": str(args.append_results) if args.append_results else None})
        print(json.dumps(report["rows"]), flush=True)
        return 0
    except BaseException as error:
        stopping.set()
        write_json(root / "STOPPED.json", {"time": now(), "error": repr(error),
                                           "generated": len(edit_done), "tokens": len(token_done)})
        raise
    finally:
        for handle in gpu_locks:
            handle.close()


if __name__ == "__main__":
    sys.exit(main())
