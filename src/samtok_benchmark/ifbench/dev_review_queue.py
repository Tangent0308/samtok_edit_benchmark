"""Read-only per-model Judge completion signals for parallel report workers."""

import argparse
from collections import Counter, defaultdict
import fcntl
import html
import os
from pathlib import Path
import time

from samtok_benchmark.io import atomic_text, write_json
from .dev_plan import ROOT, read
from .dev_scope import active_plan

DIRECTORY = ROOT / "model_reviews"


def state_for(model, keys, statuses, generation):
    counts = Counter(statuses.get(k, "pending") for k in keys)
    counts = {k: counts[k] for k in ("scored", "judge-failed", "pending")}
    terminal = bool(keys) and not counts["pending"] and not generation.get("pending", 0)
    return {
        "model": model,
        "judge_unique_total": len(keys),
        "judge_counts": counts,
        "generation_counts": dict(generation),
        "judge_attempts_complete": terminal,
        "score_complete": terminal and not counts["judge-failed"],
        "state": (
            "ready_with_judge_failures"
            if terminal and counts["judge-failed"]
            else "ready_for_scored_review"
            if terminal
            else "waiting_judge"
        ),
    }


def run(once=False, interval=60):
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    lock = (DIRECTORY / "queue.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    plan = active_plan()
    current = read(ROOT / "judge/current.json")
    run_id = current["run_id"]
    judge = ROOT / "judge" / run_id
    keys = defaultdict(set)
    for b in read(judge / "bindings.json"):
        model = Path(b["record"]).relative_to(ROOT / "runs").parts[0]
        assert model in plan["candidates"]
        keys[model].add(b["key"])
    generation = defaultdict(Counter)
    for task in plan["tasks"]:
        path = ROOT / "runs" / task["key"] / "result.json"
        generation[task["model"]][read(path)["status"] if path.exists() else "pending"] += 1
    cache = {}
    previous = {}
    metadata = {
        "pid": os.getpid(),
        "started_at": time.time(),
        "interval_seconds": interval,
        "run_id": run_id,
        "mode": "read-only-completion-signals",
        "status": "running",
    }
    write_json(DIRECTORY / "queue_process.json", metadata)
    while True:
        assert read(ROOT / "judge/current.json")["run_id"] == run_id, (
            "Judge run changed; review queue must be rebound explicitly"
        )
        for path in (judge / "records").glob("*.json"):
            stamp = path.stat().st_mtime_ns
            if path.stem not in cache or cache[path.stem][0] != stamp:
                value = read(path)["status"]
                assert value in ("scored", "judge-failed"), value
                cache[path.stem] = (stamp, value)
        statuses = {k: v[1] for k, v in cache.items()}
        now = time.time()
        models = {m: state_for(m, keys[m], statuses, generation[m]) for m in plan["candidates"]}
        for model, item in models.items():
            item.update(run_id=run_id, updated_at=now)
            signature = (
                item["judge_attempts_complete"],
                item["score_complete"],
                tuple(item["judge_counts"].values()),
            )
            if item["judge_attempts_complete"] and previous.get(model) != signature:
                write_json(DIRECTORY / model / "trigger.json", item)
                with (DIRECTORY / "events.jsonl").open("a") as stream:
                    import json

                    stream.write(json.dumps(item, ensure_ascii=False) + "\n")
            previous[model] = signature
        status = {
            "updated_at": now,
            "utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(now)),
            "run_id": run_id,
            "models": models,
            "note": "Counts are unique Judge keys per model, not alias-expanded candidate denominators. Terminal Judge failures block score-complete selection.",
        }
        write_json(DIRECTORY / "STATUS.json", status)
        rows = []
        for model, item in models.items():
            c = item["judge_counts"]
            report = DIRECTORY / model / "REPORT.html"
            link = f'<a href="{model}/REPORT.html">图文报告</a>' if report.exists() else "准备中"
            rows.append(
                f"<tr><td>{html.escape(model)}</td><td>{c['scored']}</td><td>{c['judge-failed']}</td><td>{c['pending']}</td><td>{html.escape(item['state'])}</td><td>{link}</td></tr>"
            )
        page = (
            '<!doctype html><html lang="zh"><meta charset="utf-8"><meta http-equiv="refresh" content="60">'
            "<title>IF-Bench 模型审阅队列</title><style>body{font:16px/1.6 system-ui;margin:30px}td,th{border:1px solid #bbb;padding:8px}table{border-collapse:collapse}</style>"
            "<h1>逐模型Judge与并行审阅</h1><p>Qwen-2511 → Qwen-2.1 → FLUX.3 → RePlan → MIRAGE → MICE。"
            "评分请求终态后触发CPU报告；评分失败单列，分数不齐不得选型。所有材料均为dev临时材料，图片内嵌于各模型报告。</p>"
            f"<p>{status['utc']}；下表为模型内去重Judge请求数，不是候选/setting的alias展开分母。</p>"
            "<table><tr><th>模型</th><th>评分成功</th><th>评分失败</th><th>待评分</th><th>审阅状态</th><th>材料</th></tr>"
            + "".join(rows)
            + "</table></html>"
        )
        atomic_text(DIRECTORY / "INDEX.html", page)
        metadata.update(last_check_at=now)
        write_json(DIRECTORY / "queue_process.json", metadata)
        if once:
            break
        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()
    assert args.interval >= 30
    run(args.once, args.interval)
