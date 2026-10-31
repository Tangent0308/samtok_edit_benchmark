"""Live dev completeness and strict candidate selection; never write freeze.json."""

from collections import Counter
import base64
import json

from markdown_it import MarkdownIt
from PIL import Image, ImageDraw

from samtok_benchmark.io import write_json
from .dev_plan import ROOT, read
from .smoke_suite import SHARED
from .dev_scope import active_plan


def generate():
    plan = active_plan()
    tasks = {t["key"]: t for t in plan["tasks"]}
    aliases = {a["key"]: a["target"] for a in plan["aliases"]}
    records = {}
    for key in tasks:
        p = ROOT / "runs" / key / "result.json"
        if p.exists():
            try:
                records[key] = read(p)
            except json.JSONDecodeError:
                continue  # Live writer; try again on next refresh.
    score_by_record = {}
    judge_root = None
    current = ROOT / "judge/current.json"
    if current.exists():
        judge_root = ROOT / "judge" / read(current)["run_id"]
        bindings = judge_root / "bindings.json"
        if bindings.exists():
            for b in read(bindings):
                p = judge_root / "records" / f"{b['key']}.json"
                if p.exists():
                    r = read(p)
                    if r["status"] == "scored":
                        score_by_record[b["record"]] = r["scores"]
    unit_counts = {
        cid: len(read(SHARED / "requests/S1" / cid / "public.json")["units"])
        for cid in plan["case_ids"]
    }
    rows = []
    for model, candidates in plan["candidates"].items():
        for candidate in candidates:
            for setting in plan["settings"]:
                counts = Counter()
                unit_pass = joint_pass = 0
                complete = True
                expected_na = model == "maskflow" and (
                    setting in ("S1", "S5")
                    or (candidate["role"] == "discard" and setting.startswith("S2-"))
                )
                for cid in plan["case_ids"]:
                    key = f"{model}/{candidate['id']}/{setting}/{cid}"
                    target = aliases.get(key, key)
                    r = records.get(target)
                    if r is None:
                        counts["pending"] += 1
                        complete = False
                        continue
                    status = r["status"]
                    counts[status] += 1
                    if expected_na:
                        if status != "not-applicable":
                            raise ValueError("N/A path received a substitute result")
                        continue
                    if status == "generated":
                        score = score_by_record.get(str(ROOT / "runs" / target / "result.json"))
                        if score is None:
                            counts["judge-pending"] += 1
                            complete = False
                            continue
                        if len(score["units"]) != unit_counts[cid]:
                            raise ValueError("Incomplete unit scores")
                        bits = [all(u[d]["pass"] for d in "EPQ") for u in score["units"]]
                        unit_pass += sum(bits)
                        joint_pass += int(
                            all(bits) and score["global_P"]["pass"] and score["global_Q"]["pass"]
                        )
                    elif status not in (
                        "failed",
                        "failed-planner",
                        "failed-component",
                        "failed-interrupted",
                    ):
                        complete = False
                rows.append(
                    {
                        "model": model,
                        "candidate": candidate["id"],
                        "role": candidate["role"],
                        "setting": setting,
                        "status_counts": dict(counts),
                        "complete": complete,
                        "not_applicable": expected_na,
                        "UnitPass": unit_pass / sum(unit_counts.values())
                        if complete and not expected_na
                        else None,
                        "JointPass": joint_pass / len(unit_counts)
                        if complete and not expected_na
                        else None,
                        "unit_denominator": sum(unit_counts.values()),
                        "case_denominator": len(unit_counts),
                    }
                )
    selection = {}
    for model, candidates in plan["candidates"].items():
        eligible = []
        for priority, c in enumerate(candidates):
            if c["role"] != "primary":
                continue
            rr = [
                r
                for r in rows
                if r["model"] == model
                and r["candidate"] == c["id"]
                and r["setting"] in plan["selection"]["settings"][model]
            ]
            value = (
                sum(r["JointPass"] for r in rr) / len(rr)
                if all(r["complete"] and r["JointPass"] is not None for r in rr)
                else None
            )
            eligible.append(
                {"candidate": c["id"], "mean_JointPass": value, "registered_priority": priority}
            )
        ready = all(c["mean_JointPass"] is not None for c in eligible)
        chosen = (
            min(
                eligible,
                key=lambda c: (-c["mean_JointPass"], c["registered_priority"], c["candidate"]),
            )["candidate"]
            if ready
            else None
        )
        s2 = {}
        for setting in ("S2-point", "S2-box", "S2-mask"):
            rr = [
                r
                for r in rows
                if r["model"] == model
                and r["setting"] == setting
                and r["role"] in ("primary", "discard")
                and not r["not_applicable"]
            ]
            winner = (
                min(rr, key=lambda r: (-r["JointPass"], r["role"] == "discard", r["candidate"]))
                if all(r["JointPass"] is not None for r in rr)
                else None
            )
            s2[setting] = {
                "candidate": winner["candidate"] if winner else None,
                "discard_region": winner["role"] == "discard" if winner else None,
            }
        selection[model] = {
            "primary_candidates": eligible,
            "proposed_primary": chosen,
            "S2_best_adapted": s2,
        }
    statuses = Counter(r["status"] for r in records.values())
    physical_calls = sum(
        r.get("inference_api_calls") or 0 for r in records.values() if not r.get("reused")
    )
    report = {
        "scope": plan.get("scope"),
        "dev_plan_digest": plan["digest"],
        "physical_task_statuses": dict(statuses),
        "unique_tasks": len(tasks),
        "aliases": len(aliases),
        "pending_tasks": len(tasks) - len(records),
        "actual_diffusion_calls_recorded": physical_calls,
        "unknown_call_count_records": sum(
            r.get("inference_api_calls") is None for r in records.values()
        ),
        "rows": rows,
        "selection": selection,
        "ready_for_pre_freeze_review": all(r["complete"] for r in rows),
        "frozen": False,
        "test_started": False,
    }
    report["judge_executions"] = (
        [
            {"receipt_path": str(p), **read(p)}
            for p in sorted((judge_root / "executions").glob("*/receipt.json"))
        ]
        if judge_root is not None
        else []
    )
    write_json(ROOT / "PROGRESS.json", report)
    md = "# IF-Bench dev选型进度\n\n"
    md += "**这里只运行dev；配置尚未冻结，未启动test。缺失评分显示待完成，不补零。**\n\n"
    if report["judge_executions"]:
        md += (
            "Judge 已启用独立执行记录：基础 config.json 记录原始批处理配置，"
            "连续调度的实际引擎参数、并发、代码快照及性能验证额外调用以执行记录为准。"
            "性能验证回答不进入评分表。\n\n"
        )
        for execution in report["judge_executions"]:
            md += f"[Judge 执行记录]({execution['receipt_path']})\n\n"
    if plan.get("scope"):
        md += (
            "**按用户要求暂缓评测："
            + ", ".join(plan["scope"]["excluded_models"])
            + "。已有输出仅作历史临时记录，不进入当前分数、分母、Judge或候选选择，也不记为失败或N/A。**\n\n"
        )
    md += "|汇报项|当前状态|\n|---|---|\n"
    md += f"|做了什么|预登记{len(plan['case_ids'])}张dev图、10个setting；物理请求状态：{dict(statuses)}；待完成请求{report['pending_tasks']}。|\n"
    md += "|问题与偏差|MIRAGE公开短语语法扩展已留档；Judge改用canonical指令和统一GT证据，不读取输入形式。错误保留在逐请求记录与日志。|\n"
    md += "|阻塞项|未生成或未评分的行暂不选型；运行错误触发对应模型暂停，不换seed重跑。|\n"
    md += "|下一步|完成候选生成、统一Judge和评分汇总；停在冻结前审核。|\n\n"
    md += "[已登记候选](plan.json) · [机器记录](PROGRESS.json) · [冒烟图片报告](../smoke/SUMMARY_REPORT.html)\n\n"
    md += "|模型|拟选主配置|S2-point best-adapted|S2-box best-adapted|S2-mask best-adapted|\n|---|---|---|---|---|\n"
    for model, selected in selection.items():
        choices = []
        for setting in ("S2-point", "S2-box", "S2-mask"):
            c = selected["S2_best_adapted"][setting]
            choices.append(
                "待评分"
                if c["candidate"] is None
                else ("**丢弃区域**" if c["discard_region"] else c["candidate"])
            )
        md += f"|{model}|{selected['proposed_primary'] or '待评分'}|" + "|".join(choices) + "|\n"
    md += "\n官方PE/PUP固定补充行不参与受控主行选择；候选分数未完整前不宣布胜出。\n\n"
    md += "|模型|候选|setting|UnitPass|JointPass|完成状态|\n|---|---|---|---|---|---|\n"
    for r in rows:
        up = (
            "N/A"
            if r["not_applicable"]
            else ("待完成" if r["UnitPass"] is None else f"{r['UnitPass']:.4f}")
        )
        jp = (
            "N/A"
            if r["not_applicable"]
            else ("待完成" if r["JointPass"] is None else f"{r['JointPass']:.4f}")
        )
        md += f"|{r['model']}|{r['candidate']}|{r['setting']}|{up}|{jp}|{r['status_counts']}|\n"
    previews = []
    md += "\n## 首批实际dev输出\n\n按预登记任务顺序展示每模型最先完成的不同case，最多3个；不是按好坏挑图。左为源图，右为输出。完整调用和prompt在链接中。\n\n"
    for model in plan["candidates"]:
        seen = set()
        for key, t in tasks.items():
            r = records.get(key)
            if (
                t["model"] != model
                or not r
                or r["status"] != "generated"
                or r.get("reused")
                or t["case_id"] in seen
            ):
                continue
            seen.add(t["case_id"])
            out = ROOT / "runs" / key
            path = ROOT / "previews" / model / (r["output_sha256"] + ".jpg")
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                call = read(out / "call.json")
                canvas = Image.new("RGB", (1200, 450), "white")
                draw = ImageDraw.Draw(canvas)
                draw.text(
                    (10, 10),
                    f"{model} | {t['candidate']} | {t['setting']} | {t['case_id']} | source / output",
                    fill="black",
                )
                for col, p in enumerate((call["source"]["path"], r["output_image"])):
                    image = Image.open(p).convert("RGB")
                    image.thumbnail((580, 400))
                    canvas.paste(
                        image,
                        (10 + 600 * col + (580 - image.width) // 2, 35 + (400 - image.height) // 2),
                    )
                canvas.save(path, quality=92)
            previews.append(path)
            md += f"![{model}实际dev对照]({path})\n\n[完整输入及最终prompt]({out / 'call.json'}) · [原始结果记录]({out / 'result.json'})\n\n"
            if len(seen) == 3:
                break
    (ROOT / "PROGRESS.md").write_text(md)
    html = MarkdownIt().enable("table").render(md)
    for p in previews:
        uri = "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()
        html = html.replace(f'src="{p}"', f'src="{uri}"')
    (ROOT / "PROGRESS.html").write_text(
        '<!doctype html><html lang="zh"><meta charset="utf-8"><title>IF-Bench dev progress</title><style>body{font:16px/1.6 system-ui;margin:30px}table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:8px}</style>'
        + html
        + "</html>"
    )
    return report


if __name__ == "__main__":
    r = generate()
    print(
        json.dumps(
            {
                k: r[k]
                for k in ("physical_task_statuses", "pending_tasks", "ready_for_pre_freeze_review")
            },
            ensure_ascii=False,
        )
    )
