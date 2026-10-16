"""Release 2.6.0 repair progress, computed from files only.

Reads revision records, agent logs, committed work-dir masks and the 2026-10-15 audit findings.
Masks are read only as arrays by the same release checks that build.py runs; nothing is opened
for viewing. Rerun after every repair session:

  /opt/tiger/envs/gen/bin/python construction/release_2_6/status.py

Writes construction/release_2_6/status.json, construction/release_2_6/remaining_work.jsonl and
docs/RELEASE_2_6_REMAINING_CASES_ZH.md.
"""

from __future__ import annotations

import collections
import datetime
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import build  # noqa: E402

FINDINGS = HERE / "audit" / "findings.jsonl"
ASSIGNMENTS = HERE / "assignments"
LOGS = HERE / "logs"
DOC = REPO / "docs" / "RELEASE_2_6_REMAINING_CASES_ZH.md"
TAIL_START = 945
# 2026-10-15: shards 0-2 kept these prefixes; the rest of each list moved to shard<k>b.
SHARD_PREFIX = {"shard0": 81, "shard1": 141, "shard2": 151}
MAIN_SESSION = {"v2-sa_9345888", "v2-sa_2566092"}
ORIGINAL_OPERATIONS = {"add": 980, "replace": 969, "remove": 935, "attribute": 988}
OPEN = ("failing", "partial", "todo", "done_unlogged")
SEVERITY_ZH = {"blocking": "阻断", "major": "严重", "minor": "轻微"}
SEVERITY_ORDER = {"blocking": 0, "major": 1, "minor": 2}
CATEGORY_ZH = {
    "wrong_instance_spatial": "方位/序数与 mask 不符",
    "person_clothing_level": "人物/服装层级错误",
    "category_mismatch": "ref 名词与实物不符",
    "ill_posed_edit": "编辑不合理",
    "attribute_value": "属性值无变化或含糊",
    "replace_is_attribute": "replace 实为换色/换材质",
    "mask_quality": "mask 质量",
    "independence_violation": "同一物体/编辑冲突",
    "ambiguous_ref": "指代歧义",
    "add_anchor": "add 锚点问题",
    "grammar_style": "措辞/语法",
    "translation": "中英不一致",
    "ref_noref_mismatch": "ref/no-ref 不一致",
}
STATUS_ZH = {
    "done": "已完成（修订 + 日志 + 检查通过）",
    "done_unlogged": "已写修订且检查通过，但缺日志",
    "failing": "已写修订但检查未通过",
    "partial": "进行中：已有 v2 mask，无修订文件",
    "todo": "未开始",
    "not_needed": "无需处理",
}


def shard_owner():
    owner = {}
    for path in sorted(ASSIGNMENTS.glob("shard*.txt")):
        ids = [line.strip() for line in path.read_text().splitlines() if line.strip()]
        for cid in ids[: SHARD_PREFIX.get(path.stem, len(ids))]:
            owner.setdefault(cid, path.stem)
    owner.update({cid: "main-session" for cid in MAIN_SESSION})
    return owner


def log_entries():
    entries = collections.defaultdict(list)
    for path in sorted(LOGS.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict) and rec.get("case_id"):
                entries[rec["case_id"]].append({**rec, "_log": path.stem})
    return entries


def evaluate(item):
    """Apply the case's revision exactly as build.py would and run the release checks."""
    case, index = item
    cid = case["id"]
    rev_path = build.REVISIONS / f"{cid}.json"
    work = build.WORK / cid
    result = {
        "case_id": cid,
        "index": index,
        "has_revision": rev_path.exists(),
        "v2_masks": sorted(p.stem[:-3] for p in work.glob("U*_v2.png")) if work.exists() else [],
        "reviewer": None,
        "revision_error": None,
        "drop_case": False,
        "problems": [],
        "unit_actions": {},
        "operations": [u["operation"] for u in case["units"]],
    }
    rev = {}
    if rev_path.exists():
        try:
            rev = json.loads(rev_path.read_text())
            result["reviewer"] = rev.get("reviewer")
        except json.JSONDecodeError as exc:
            result["revision_error"] = f"invalid JSON: {exc}"
            return result
    if rev.get("action") == "drop_case":
        result.update(drop_case=True, operations=[])
        return result
    problems, actions = [], []
    try:
        unit_revs = {u["id"]: u for u in rev.get("units", [])}
        unknown = set(unit_revs) - {u["id"] for u in case["units"]}
        if unknown:
            problems.append(f"{cid}: revision names unknown units {sorted(unknown)}")
        units = [build.apply_unit(case, u, unit_revs.get(u["id"]), problems, actions) for u in case["units"]]
        new_case = dict(case, units=[u for u in units if u is not None])
        problems.extend(build.check_case(new_case))
        result["operations"] = [u["operation"] for u in new_case["units"]]
        result["unit_actions"] = {
            a["unit"]: a["action"] + ("+mask_v2" if a.get("mask") == "v2" else "")
            for a in actions if "unit" in a
        }
    except Exception as exc:  # a malformed spec must be reported, not crash the scan
        problems.append(f"{cid}: {type(exc).__name__}: {exc}")
    result["problems"] = problems
    return result


def part_mask_note(unit):
    s = unit["instruction_spec"]
    if s["operation"] == "add":
        return f'add 附着部位 site="{s["placement"].get("site")}" → mask 改为该部位本身'
    mode = s["remove_mode"]
    if s["operation"] == "remove" and mode != "whole":
        return {
            "part": f'remove part，target_part="{s["target_part"]}" → mask 改为被删部件本身',
            "lowerlegs": "remove lowerlegs → mask 改为被剪掉的裤腿下半截",
            "hem": "remove hem → mask 改为被剪掉的下摆",
            "contents": "remove contents → mask 改为容器 ∪ 内容物",
            "contents_only": "remove contents_only → mask 改为内容物",
        }[mode]
    return f'{s["operation"]} target_part="{s["target_part"]}" → mask 改为该部件本身'


def cell(text, limit=700):
    text = " ".join(str(text or "").split()).replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def fix_text(f):
    fix = f.get("suggested_fix")
    parts = []
    if isinstance(fix, dict):
        if fix.get("instruction_ref"):
            parts.append(f"ref 改为：{fix['instruction_ref']}")
        other = f.get("other_zh") or fix.get("other")
        if other:
            parts.append(str(other))
    elif fix:
        parts.append(str(fix))
    return "；".join(parts)


def interaction(unit):
    i = unit["interaction"]
    return ("ref" if i["has_ref"] else "noref") + "+" + i["locator"]


def main():
    cases = build.read_jsonl(build.BASE / "cases.jsonl")
    by_id = {c["id"]: c for c in cases}
    findings = collections.defaultdict(list)
    for line in FINDINGS.read_text().splitlines():
        if line.strip():
            f = json.loads(line)
            findings[f["case_id"]].append(f)
    owner, logs = shard_owner(), log_entries()
    with ProcessPoolExecutor(32) as pool:
        results = list(pool.map(evaluate, [(c, i) for i, c in enumerate(cases)], chunksize=8))

    for r in results:
        case = by_id[r["case_id"]]
        st = [u for u in case["units"] if build.needs_part_mask(u["instruction_spec"])]
        fs = findings.get(case["id"], [])
        r.update(
            shard=owner.get(case["id"]),
            tail=r["index"] >= TAIL_START,
            findings=len(fs),
            part_mask_units=[u["id"] for u in st],
            logged=bool(logs.get(case["id"])),
        )
        in_work = bool(fs or st or r["tail"])
        if r["revision_error"] or (r["has_revision"] and r["problems"]):
            status = "failing"
        elif r["has_revision"] or r["drop_case"]:
            status = "done" if r["logged"] or r["reviewer"] == "main-session" else "done_unlogged"
        elif not in_work:
            status = "not_needed"
        elif r["v2_masks"]:
            status = "partial"
        else:
            status = "todo"
        r["status"] = status

    open_ids = {r["case_id"] for r in results if r["status"] in OPEN}
    open_findings = [f for cid in open_ids for f in findings.get(cid, [])]
    open_part = [(r["case_id"], u) for r in results if r["case_id"] in open_ids
                 for u in r["part_mask_units"] if u not in r["v2_masks"]]
    rejected, new_problems = [], []
    for cid, entries in logs.items():
        for e in entries:
            for item in e.get("findings_rejected") or []:
                rejected.append({"case_id": cid, "log": e["_log"], **(item if isinstance(item, dict) else {"why": item})})
            for item in e.get("new_problems_found") or []:
                new_problems.append({"case_id": cid, "log": e["_log"], "note": item})

    per_shard = collections.defaultdict(collections.Counter)
    for r in results:
        if r["shard"]:
            per_shard[r["shard"]][r["status"]] += 1
    summary = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "cases": len(results),
        "status": dict(collections.Counter(r["status"] for r in results)),
        "work_list_cases": sum(r["status"] != "not_needed" for r in results),
        "per_shard": {k: dict(v) for k, v in sorted(per_shard.items())},
        "open_findings": dict(collections.Counter(f["severity"] for f in open_findings)),
        "open_findings_by_category": dict(collections.Counter(f["category"] for f in open_findings).most_common()),
        "open_part_mask_units": len(open_part),
        "part_mask_units_total": sum(len(r["part_mask_units"]) for r in results),
        "v2_masks_committed": sum(len(r["v2_masks"]) for r in results),
        "operations_now": dict(collections.Counter(op for r in results for op in r["operations"])),
        "operations_2_5_0": ORIGINAL_OPERATIONS,
        "units_now": sum(len(r["operations"]) for r in results),
        "rejected_findings_logged": len(rejected),
    }
    write = build.write_json
    write(HERE / "status.json", {"summary": summary, "cases": {
        r["case_id"]: {k: r[k] for k in ("index", "shard", "status", "tail", "findings", "part_mask_units",
                                          "v2_masks", "reviewer", "logged", "unit_actions", "problems")}
        for r in results}})

    remaining = []
    for r in sorted((r for r in results if r["status"] in OPEN), key=lambda r: r["index"]):
        case = by_id[r["case_id"]]
        remaining.append({
            "case_id": r["case_id"], "index": r["index"], "shard": r["shard"], "status": r["status"],
            "tail": r["tail"], "v2_masks_present": r["v2_masks"], "check_problems": r["problems"],
            "revision_error": r["revision_error"],
            "units": [{"id": u["id"], "operation": u["operation"], "interaction": interaction(u),
                       "instruction_ref": u["instruction_ref"]} for u in case["units"]],
            "part_masks_needed": [{"unit": u["id"], "note": part_mask_note(u)} for u in case["units"]
                                  if u["id"] in r["part_mask_units"] and u["id"] not in r["v2_masks"]],
            "findings": [{"unit": f.get("unit_id"), "severity": f["severity"], "category": f["category"],
                          "evidence": f.get("evidence_zh") or f.get("evidence"), "suggested_fix": fix_text(f),
                          "verified_visually": f.get("verified_visually")}
                         for f in sorted(findings.get(r["case_id"], []),
                                         key=lambda f: (SEVERITY_ORDER[f["severity"]], str(f.get("unit_id"))))],
        })
    build.write_jsonl(HERE / "remaining_work.jsonl", remaining)
    write_doc(summary, remaining, rejected, new_problems)
    print(json.dumps(summary, ensure_ascii=False))


def write_doc(summary, remaining, rejected, new_problems):
    s = summary["status"]
    lines = [
        "# Release 2.6.0 剩余待修复 case 清单（自动生成）",
        "",
        f"> 由 `construction/release_2_6/status.py` 于 {summary['generated_at']} 生成，只读取修订文件、日志、work 目录 mask "
        "和 2026-10-15 审查结果（`construction/release_2_6/audit/findings.jsonl`），没有重新看图。修复后重新运行即可刷新。",
        ">",
        "> 审查给出的“建议修改”中的 no-ref 写法已过时：协议 2.0 的 no-ref 由 `render(spec, False)` 自动生成为 "
        "`the selected region`，只需改 spec、ref、中文和 mask。replace 实为换色的问题按用户决定优先改成真实结构替换。",
        "",
        "## 汇总",
        "",
        "| 状态 | case 数 |",
        "|---|---:|",
    ]
    for key in ("done", "done_unlogged", "failing", "partial", "todo", "not_needed"):
        lines.append(f"| {STATUS_ZH[key]} | {s.get(key, 0)} |")
    of = summary["open_findings"]
    lines += [
        "",
        f"未完成 case（缺日志、检查未通过、进行中、未开始）共 {sum(s.get(k, 0) for k in OPEN)} 个，其中的审查问题："
        f"阻断 {of.get('blocking', 0)}、严重 {of.get('major', 0)}、轻微 {of.get('minor', 0)} 条；"
        f"协议 2.0 仍需换部件/附着部位 mask 的单元 {summary['open_part_mask_units']} 个"
        f"（全库共 {summary['part_mask_units_total']} 个）。",
        "",
        "| 类别 | 未完成 case 中的条数 |",
        "|---|---:|",
    ]
    for cat, n in summary["open_findings_by_category"].items():
        lines.append(f"| {CATEGORY_ZH.get(cat, cat)} | {n} |")
    sections = [
        ("failing", "1. 已写修订但检查未通过"),
        ("partial", "2. 进行中：已有 v2 mask，但没有修订文件"),
        ("todo", "3. 未开始"),
    ]
    for key, title in sections:
        items = [r for r in remaining if r["status"] == key]
        lines += ["", f"## {title}（{len(items)} 个）", ""]
        if key == "partial" and items:
            lines += ["这些 case 的修复 agent 在提交 mask 后中断。已提交的 v2 mask 会被 build.py 自动采用，"
                      "必须先看图确认，再写修订文件。", ""]
        for r in items:
            reasons = []
            if r["findings"]:
                c = collections.Counter(f["severity"] for f in r["findings"])
                reasons.append("审查问题 " + "、".join(f"{SEVERITY_ZH[k]} {c[k]}" for k in ("blocking", "major", "minor") if c[k]))
            if r["part_masks_needed"]:
                reasons.append(f"协议 2.0 需换 mask {len(r['part_masks_needed'])} 个")
            if r["tail"]:
                reasons.append("尾段：每个单元都要重写")
            lines += [f"### #{r['index']} `{r['case_id']}` · {r['shard']}", "", "- 原因：" + "；".join(reasons)]
            if r["v2_masks_present"]:
                lines.append("- 已提交的 v2 mask（未确认）：" + "、".join(r["v2_masks_present"]))
            if r["revision_error"]:
                lines.append(f"- 修订文件错误：{r['revision_error']}")
            for p in r["check_problems"] if key == "failing" else []:
                lines.append(f"- 检查问题：{cell(p, 300)}")
            lines.append("- 当前单元：")
            for u in r["units"]:
                lines.append(f"  - {u['id']} {u['operation']}（{u['interaction']}）：{cell(u['instruction_ref'], 300)}")
            for p in r["part_masks_needed"]:
                lines.append(f"- 协议 2.0 mask：{p['unit']} {p['note']}")
            if r["findings"]:
                lines += ["", "| 单元 | 级别 | 类别 | 问题 | 建议修改 |", "|---|---|---|---|---|"]
                for f in r["findings"]:
                    lines.append(
                        f"| {f['unit'] or '整图'} | {SEVERITY_ZH[f['severity']]} | {CATEGORY_ZH.get(f['category'], f['category'])} "
                        f"| {cell(f['evidence'])}{'' if f['verified_visually'] else '（仅文本规则）'} | {cell(f['suggested_fix'])} |"
                    )
            lines.append("")
    unlogged = [r for r in remaining if r["status"] == "done_unlogged"]
    lines += ["", f"## 4. 已写修订且检查通过，但缺日志（{len(unlogged)} 个）", "",
              "修复 agent 可能在写日志前中断。请确认修订是否完整，再补日志或重修。", ""]
    lines += [f"- #{r['index']} `{r['case_id']}` · {r['shard']}" for r in unlogged]
    lines += ["", f"## 5. 已完成 case 中被否定的审查问题（{len(rejected)} 条，来自修复日志）", "",
              "| case | 单元 | 类别 | 否定理由 | 日志 |", "|---|---|---|---|---|"]
    for item in sorted(rejected, key=lambda x: x["case_id"]):
        lines.append(f"| `{item['case_id']}` | {cell(item.get('unit'))} | {cell(item.get('category'))} "
                     f"| {cell(item.get('why') or item.get('reason'), 400)} | {item['log']} |")
    lines += ["", f"## 6. 修复时在审查清单之外额外发现的问题（{len(new_problems)} 条，来自修复日志）", "",
              "这些是修复 agent 自己发现的问题，按要求通常已在同一份修订中处理，列出仅供追溯；不是剩余工作。", ""]
    lines += [f"- `{p['case_id']}`（{p['log']}）：{cell(p['note'], 400)}" for p in sorted(new_problems, key=lambda x: x["case_id"])]
    DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
