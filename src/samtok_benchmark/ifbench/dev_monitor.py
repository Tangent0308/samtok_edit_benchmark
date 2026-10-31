"""Read-only execution monitor: progress, health, measured-time ETA and history."""

import argparse
import base64
from collections import Counter, defaultdict
from datetime import datetime, timezone
import fcntl
import html
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import time

from samtok_benchmark.io import atomic_text, write_json
from .dev_balancer import identity, workloads
from .dev_plan import ROOT, read
from .dev_scope import active_plan

MONITOR = ROOT / "monitor"


def utc(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def simulate(work, assignments, capacity=8):
    """Estimate queue completion with future dynamic handoffs; no measured scores here."""
    remaining = {m: float(s) for m, s in work.items() if s > 0}
    active = {g: m for g, m in assignments.items() if m in remaining}

    def fill(gpus):
        for gpu in gpus:
            counts = Counter(active.values())
            candidates = [m for m, s in remaining.items() if s > 0.001]
            if candidates:
                active[gpu] = max(candidates, key=lambda m: (remaining[m] / (counts[m] + 1), m))

    fill(g for g in range(capacity) if g not in active)
    elapsed = 0.0
    events = []
    while active:
        counts = Counter(active.values())
        delta = min(remaining[m] / n for m, n in counts.items())
        elapsed += delta
        for model, n in counts.items():
            remaining[model] = max(0.0, remaining[model] - delta * n)
        freed = [g for g, m in active.items() if remaining[m] < 0.001]
        events.append({"seconds_from_now": elapsed, "models": sorted({active[g] for g in freed})})
        for gpu in freed:
            del active[gpu]
        fill(freed)
    return elapsed, events


def active_workers():
    workers, dispatchers = [], set()
    for path in (ROOT / "engineering/balanced_queue").glob("worker-*.json"):
        entry = read(path)
        if identity(entry["pid"]) != entry["process_identity"]:
            continue
        dispatchers.add(entry["pid"])
        if (
            entry["status"] == "running"
            and entry.get("child_pid")
            and identity(entry["child_pid"]) is not None
        ):
            workers.append(
                {
                    "model": entry["model"],
                    "gpu": int(entry["visible_devices"]),
                    "pid": entry["child_pid"],
                    "log": entry["log"],
                    "started_at": entry["time"],
                }
            )
    for job in read(ROOT / "orchestration/jobs.json"):
        if job["status"] != "running" or job["pid"] in dispatchers or identity(job["pid"]) is None:
            continue
        command = job["command"]
        if "samtok_benchmark.ifbench.dev_runner" in command:
            model = command[command.index("samtok_benchmark.ifbench.dev_runner") + 1]
            workers.append(
                {
                    "model": model,
                    "gpu": int(job["gpus"]),
                    "pid": job["pid"],
                    "log": job["log"],
                    "started_at": job["started_at"],
                }
            )
    return workers


def collect():
    now = time.time()
    plan = active_plan()
    counts, durations = defaultdict(Counter), defaultdict(list)
    latest, recent = {}, Counter()
    problems, failures, known = [], [], []
    for task in plan["tasks"]:
        model = task["model"]
        counts[model]["total"] += 1
        path = ROOT / "runs" / task["key"] / "result.json"
        if not path.exists():
            counts[model]["pending"] += 1
            continue
        result = read(path)
        counts[model][result["status"]] += 1
        if result["status"] == "generated":
            stamp = path.stat().st_mtime
            latest[model] = max(latest.get(model, 0), stamp)
            recent[model] += stamp >= now - 3600
            if result.get("pipeline_wall_seconds"):
                durations[model].append(result["pipeline_wall_seconds"])
        else:
            failures.append(
                {
                    "task": task["key"],
                    "status": result["status"],
                    "reason": result.get("reason", result.get("error")),
                    "record": str(path),
                }
            )
    controller = read(ROOT / "orchestration/controller.json")
    controller_alive = identity(controller["pid"]) is not None
    receipt_path = (
        Path(controller["execution"]) / "receipt.json" if controller.get("execution") else None
    )
    controller_completed = bool(
        receipt_path and receipt_path.exists() and read(receipt_path).get("status") == "completed"
    )
    ready = (ROOT / "REVIEW_REQUIRED.json").exists()
    if not controller_alive and not ready and not controller_completed:
        problems.append("评测调度器已退出；请检查 controller 状态和日志。")
    if controller["status"] == "needs-attention":
        problems.append("评测调度器报告 needs-attention，需要处理阻塞。")
    for model in plan["candidates"]:
        path = ROOT / model / "PAUSED.json"
        if path.exists():
            problems.append(f"{model} 已暂停：{read(path).get('reason')}; {path}")
    workers = active_workers()
    for worker in workers:
        log = Path(worker["log"])
        age = now - log.stat().st_mtime if log.exists() else now - worker["started_at"]
        limit = max(1800, 5 * max(durations.get(worker["model"], [0])))
        worker.update(log_age_seconds=round(age), stale_threshold_seconds=round(limit))
        if age > limit:
            problems.append(
                f"GPU {worker['gpu']} / {worker['model']} 日志 {age / 60:.0f} 分钟未更新，疑似停滞。"
            )
    pending = sum(c["pending"] for c in counts.values())
    if pending and not workers and controller_alive:
        problems.append("仍有生成请求未完成，但未发现活跃生成进程；可能正在交接，下一轮复核。")
    for group in ("planners", "components"):
        for directory in (ROOT / group).glob("*"):
            if directory.name not in plan["candidates"] or not directory.is_dir():
                continue
            for path in directory.glob("*--*.json"):
                if path.name.endswith(".started.json"):
                    continue
                result = read(path)
                if result.get("status") == "failed" or result.get("native_parse_fallback_used"):
                    known.append(
                        {
                            "model": directory.name,
                            "record": str(path),
                            "reason": result.get("error", "官方解析回退"),
                            "finish_reason": result.get("finish_reason"),
                        }
                    )
    judge_root = ROOT / "judge" / read(ROOT / "judge/current.json")["run_id"]
    bindings_path = judge_root / "bindings.json"
    judge = {"stage": "not-started", "scored": 0, "failed": 0, "total": None}
    if bindings_path.exists():
        keys = {b["key"] for b in read(bindings_path)}
        samples, stamps, present_keys = [], [], set()
        judge.update(stage="loading-or-scoring", total=len(keys))
        for key in keys:
            path = judge_root / "records" / f"{key}.json"
            if not path.exists():
                continue
            result = read(path)
            present_keys.add(key)
            judge["scored" if result["status"] == "scored" else "failed"] += 1
            stamps.append(path.stat().st_mtime)
            if result.get("batch_size", 0) >= 16 and result.get("batch_wall_seconds"):
                samples.append(result["batch_wall_seconds"] / result["batch_size"])
        judge["pending"] = judge["total"] - judge["scored"] - judge["failed"]
        if judge["pending"] == 0:
            judge["stage"] = "first-pass-completed"
        judge["latest_record_age_seconds"] = round(now - max(stamps)) if stamps else None
        if judge["failed"]:
            problems.append(f"Judge 有 {judge['failed']} 条评分失败，不能完成冻结前选型。")
        if judge["pending"] and stamps and now - max(stamps) > 3600:
            problems.append("Judge 已有评分但超过60分钟没有新结果，疑似停滞；请核查实际日志。")
        if len(samples) >= 32:
            # Mean per-request share weights each real batch by its actual batch size.
            seconds = judge["pending"] * statistics.mean(samples[-128:])
            judge["estimated_remaining_hours"] = [
                round(seconds / 3600, 2),
                round(seconds * 1.3 / 3600 + 0.25, 2),
            ]
            judge["eta_basis"] = (
                "至少32条正式batch>=16记录的实际推理耗时；不含全部证据预处理开销，非置信区间"
            )
        execution_path = judge_root / "execution_current.json"
        if execution_path.exists():
            receipt = read(Path(read(execution_path)["receipt"]))
            judge["execution_status"] = receipt["status"]
            judge["concurrency"] = receipt.get("selected_concurrency")
            progress_path = judge_root / "stream_progress.json"
            # Batch averages cannot estimate a continuous queue. Use completed
            # wall-clock throughput, including preprocessing and persistence.
            judge.pop("estimated_remaining_hours", None)
            judge["eta_basis"] = "连续调度等待至少33条新评分完成，暂不沿用旧批处理吞吐。"
            if progress_path.exists():
                progress = read(progress_path)
                rate = progress.get("recent_requests_per_second")
                if receipt.get("selected_mode") == "prefetch16":
                    # Batched writes arrive in bursts. An interarrival window
                    # starting inside the first burst overstates early speed.
                    rate = (
                        progress["completed"] / progress["wall_seconds"]
                        if progress["completed"] >= 32 and progress["wall_seconds"] > 0
                        else None
                    )
                if rate and progress["execution"] == str(
                    Path(read(execution_path)["receipt"]).parent
                ):
                    hours = judge["pending"] / rate / 3600
                    judge["estimated_remaining_hours"] = [
                        round(hours, 2),
                        round(hours * 1.3 + 0.25, 2),
                    ]
                    judge["eta_basis"] = (
                        "预取批处理至少32条结果的完整墙钟吞吐，含首批准备与落盘；非置信区间。"
                        if receipt.get("selected_mode") == "prefetch16"
                        else "最近至多129条连续调度评分的实际完成速率，含预处理；非置信区间。"
                    )
            if receipt.get("remote_reservation"):
                bundle = Path(receipt["remote_reservation"]).parent
                remote_keys = set(read(bundle / "remote_keys.json"))
                remote_pending = len(remote_keys - present_keys)
                local_pending = judge["pending"] - remote_pending
                remote_path = bundle / "results/progress.json"
                remote = (
                    read(remote_path)
                    if remote_path.exists()
                    else {"status": "awaiting-user-launch"}
                )
                remote_current = bundle / "results/current.json"
                if remote_current.exists():
                    remote_receipt = read(Path(read(remote_current)["receipt"]))
                    remote["status"] = remote_receipt["status"]
                    remote["hostname"] = remote_receipt.get("hostname")
                    if remote_receipt.get("error"):
                        remote["error"] = remote_receipt["error"]
                        problems.append(f"第二台Judge异常：{remote_receipt['error']}")
                judge["machines"] = {
                    "local": {"pending": local_pending, "status": receipt["status"]},
                    "node2": {"pending": remote_pending, "progress": remote},
                }
                judge.pop("estimated_remaining_hours", None)
                judge["eta_basis"] = "双机分片；等待两台各至少32条实际完成记录后按较慢一侧估算。"
                local_rate = None
                if progress_path.exists():
                    progress = read(progress_path)
                    if (
                        progress.get("completed", 0) >= 32
                        and progress.get("wall_seconds", 0) > 0
                        and progress["execution"]
                        == str(Path(read(execution_path)["receipt"]).parent)
                    ):
                        local_rate = progress["completed"] / progress["wall_seconds"]
                remote_rate = (
                    remote["completed_this_execution"] / remote["wall_seconds"]
                    if remote.get("completed_this_execution", 0) >= 32
                    and remote.get("wall_seconds", 0) > 0
                    else None
                )
                if (local_pending == 0 or local_rate) and (remote_pending == 0 or remote_rate):
                    hours = (
                        max(
                            local_pending / local_rate if local_pending else 0,
                            remote_pending / remote_rate if remote_pending else 0,
                        )
                        / 3600
                    )
                    judge["estimated_remaining_hours"] = [
                        round(hours, 2),
                        round(hours * 1.3 + 0.25, 2),
                    ]
                    judge["eta_basis"] = (
                        "两台各自完整墙钟吞吐，取剩余耗时较大者；不含评分失败处理。"
                    )
        jobs = [
            j
            for j in read(ROOT / "orchestration/jobs.json")
            if j["label"] == "canonical-judge" and j["status"] == "running"
        ]
        for job in jobs:
            if job["pid"] == controller["pid"] and controller_completed:
                continue
            path = Path(job["log"])
            age = now - path.stat().st_mtime if path.exists() else now - job["started_at"]
            if identity(job["pid"]) is None or age > 3600:
                problems.append("Judge 进程已退出或日志超过60分钟未更新，请检查。")
    eta = {"stage": "generation", "type": "planning_estimate_not_quality_score"}
    if pending and not problems:
        work, _ = workloads(plan)
        assignments = {w["gpu"]: w["model"] for w in workers}
        seconds, events = simulate(work, assignments)
        eta.update(
            central_hours=round(seconds / 3600, 2),
            range_hours=[round(seconds / 3600, 2), round(seconds * 1.25 / 3600 + 0.5, 2)],
            finish_utc=[utc(now + seconds), utc(now + seconds * 1.25 + 1800)],
            estimated_gpu_hours=round(sum(work.values()) / 3600, 2),
            events=events,
            note="至生成结束/启动Judge进程；不含Judge加载及评分。实测耗时驱动，区间为工程余量，不是置信区间。",
        )
    elif problems:
        eta.update(status="withheld", note="存在异常，暂停给出全流程完成时间，避免漏算被阻塞任务。")
    else:
        eta.update(
            central_hours=0, note="生成阶段结束；Judge剩余时间见Judge记录，尚无吞吐证据时不估算。"
        )
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=15,
        )
        gpu = [
            dict(
                zip(
                    ("index", "memory_mib", "utilization_percent"),
                    map(int, line.split(",")),
                    strict=True,
                )
            )
            for line in output.splitlines()
        ]
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        gpu = {"error": repr(exc)}
    return {
        "timestamp": now,
        "utc": utc(now),
        "scope_digest": plan.get("scope", {}).get("digest"),
        "generated": sum(c["generated"] for c in counts.values()),
        "total": len(plan["tasks"]),
        "pending": pending,
        "per_model": counts,
        "outputs_last_hour": dict(recent),
        "latest_output_age_seconds": {m: round(now - v) for m, v in latest.items()},
        "controller_alive": controller_alive,
        "controller_status": controller["status"],
        "workers": workers,
        "gpus": gpu,
        "problems": problems,
        "recorded_failures": failures,
        "known_component_issues": known,
        "eta": eta,
        "judge": judge,
        "review_required": ready,
        "health": "needs-attention"
        if problems
        else "running-with-recorded-issues"
        if failures or known
        else "normal",
        "test_started": False,
        "frozen": False,
    }


def render(value):
    esc = html.escape
    body = [
        '<!doctype html><html lang="zh"><meta charset="utf-8"><meta http-equiv="refresh" content="60"><title>IF-Bench后台监控</title><style>body{font:16px/1.6 system-ui;margin:30px}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:8px}img{max-width:100%;height:auto}pre{white-space:pre-wrap}</style>',
        "<h1>IF-Bench 后台监控</h1>",
        f"<p>最新检查：{value['utc']}；每分钟检查，每10分钟保存常规历史快照。页面每60秒刷新。</p>",
    ]
    label = (
        "需要检查"
        if value["problems"]
        else "运行中，存在已记录的请求/组件异常"
        if value["health"] != "normal"
        else "正常运行"
    )
    if value["review_required"]:
        label = "dev选型已完成，等待用户确认；不进入test"
    body += [
        f"<p><b>{label}</b>；成功出图 {value['generated']} / {value['total']}（{value['generated'] / value['total']:.1%}）。这是生成进度，不是质量通过率。</p>",
        "<table><tr><th>模型</th><th>已出图</th><th>已记录失败/阻塞</th><th>待完成</th><th>近1小时新增</th><th>GPU</th></tr>",
    ]
    for model, counts in value["per_model"].items():
        failed = counts["total"] - counts["generated"] - counts["pending"]
        devices = [w["gpu"] for w in value["workers"] if w["model"] == model]
        body.append(
            f"<tr><td>{model}</td><td>{counts['generated']}/{counts['total']}</td><td>{failed}</td><td>{counts['pending']}</td><td>{value['outputs_last_hour'].get(model, 0)}</td><td>{devices}</td></tr>"
        )
    body += ["</table><h2>预计时间</h2>"]
    eta = value["eta"]
    if "range_hours" in eta:
        body += [
            f"<p>生成结束 / Judge进程启动：预计还有 {eta['range_hours'][0]:.1f}–{eta['range_hours'][1]:.1f} 小时，约 {eta['finish_utc'][0]} 至 {eta['finish_utc'][1]}。</p>"
        ]
    body += [
        "<p>" + esc(eta.get("note", "")) + "</p>",
        "<p>Judge：" + esc(json.dumps(value["judge"], ensure_ascii=False)) + "</p>",
        "<h2>问题与阻塞</h2>",
    ]
    body += ["<p>" + esc(problem) + "</p>" for problem in value["problems"]]
    if not value["problems"]:
        body += [
            "<p>未发现调度器退出、模型暂停或日志超时等运行阻塞。已记录失败不隐藏，且不自动重试。</p>"
        ]
    for issue in value["known_component_issues"]:
        body += [
            "<p>"
            + esc(issue["model"] + ": " + issue["reason"])
            + ' · <a href="'
            + esc(issue["record"])
            + '">证据</a></p>'
        ]
    body += [
        '<h2>下一步</h2><p>继续已确认dev生成 → 统一Judge → 候选分数与推荐 → 停在冻结前。MaskFlow暂缓。监控只读取评测状态，不重启任务、不改配置、不重采样。</p><p><a href="../PROGRESS.html">完整实时评分/图片报告</a> · <a href="../status_20261028_settings/REPORT.html">逐模型×setting图片及prompt</a> · <a href="latest.json">机器状态</a> · <a href="history.jsonl">10分钟历史快照</a> · <a href="events.jsonl">异常和状态变更</a></p><h2>既有固定dev案例预览</h2><p>以下复用既有输入/输出预览，非每次监控重新采样，也不表示最新或最优结果。</p>'
    ]
    for model in value["per_model"]:
        images = sorted((ROOT / "previews" / model).glob("*.jpg"))
        if images:
            uri = "data:image/jpeg;base64," + base64.b64encode(images[0].read_bytes()).decode()
            body.append(f'<h3>{model}</h3><img src="{uri}" alt="{model}源图与输出">')
    body.append("</html>")
    atomic_text(MONITOR / "REPORT.html", "".join(body))


def append(name, value):
    with (MONITOR / name).open("a") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--check-seconds", type=int, default=60)
    parser.add_argument("--report-seconds", type=int, default=600)
    args = parser.parse_args()
    assert args.check_seconds >= 10 and args.report_seconds >= args.check_seconds
    MONITOR.mkdir(parents=True, exist_ok=True)
    lock = (MONITOR / "monitor.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    stopped = [False]
    signal.signal(signal.SIGTERM, lambda *_: stopped.__setitem__(0, True))
    signal.signal(signal.SIGINT, lambda *_: stopped.__setitem__(0, True))
    metadata = {
        "pid": os.getpid(),
        "process_identity": identity(os.getpid()),
        "started_at": time.time(),
        "check_seconds": args.check_seconds,
        "report_seconds": args.report_seconds,
        "mode": "read-only-observer",
        "status": "running",
    }
    write_json(MONITOR / "process.json", metadata)
    previous_signature, last_report = None, 0
    while not stopped[0]:
        try:
            value = collect()
            signature = json.dumps(
                [
                    value["health"],
                    value["problems"],
                    value["recorded_failures"],
                    value["controller_status"],
                    value["review_required"],
                ],
                sort_keys=True,
            )
            changed = signature != previous_signature
            write_json(MONITOR / "latest.json", value)
            if changed:
                append("events.jsonl", value)
                previous_signature = signature
            if changed or time.time() - last_report >= args.report_seconds or args.once:
                append("history.jsonl", value)
                print(
                    json.dumps(
                        {
                            "utc": value["utc"],
                            "health": value["health"],
                            "generated": value["generated"],
                            "total": value["total"],
                            "problems": value["problems"],
                            "eta": value["eta"],
                            "judge": value["judge"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                last_report = time.time()
            render(value)
            metadata.update(last_check_at=time.time(), last_check_utc=value["utc"])
            write_json(MONITOR / "process.json", metadata)
            if value["review_required"]:
                metadata["status"] = "completed-awaiting-user-review"
                break
        except Exception as exc:
            error = {"utc": utc(time.time()), "monitor_error": repr(exc)}
            append("monitor_errors.jsonl", error)
            print(json.dumps(error), flush=True)
            if args.once:
                raise
        if args.once:
            metadata["status"] = "one-shot-complete"
            break
        deadline = time.monotonic() + args.check_seconds
        while not stopped[0] and time.monotonic() < deadline:
            time.sleep(min(1, max(0, deadline - time.monotonic())))
    metadata.update(status="stopped" if stopped[0] else metadata["status"], ended_at=time.time())
    write_json(MONITOR / "process.json", metadata)


if __name__ == "__main__":
    main()
