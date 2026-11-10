"""Verify frozen answers, write a separate syntax overlay, and recompute tables."""

import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

from samtok_benchmark.external_compbench.vlm_judge.bundle import load
from samtok_benchmark.external_compbench.vlm_judge.common import checked, digest, read, save, sha
from samtok_benchmark.external_compbench.vlm_judge.worker import effective

from .statistics import aggregate
from .syntax import RULE, recover


def per_case(plan, records):
    cases = {c["case_id"]: c for c in plan["cases"]}
    rows = []
    for binding in plan["bindings"]:
        value = records[binding["request_key"]]
        item = {
            "model": binding["model"],
            "case_id": binding["case_id"],
            "task": cases[binding["case_id"]]["task"],
            "status": value["status"],
            "request_key": binding["request_key"],
        }
        if value["status"] == "scored":
            scores = value["scores"]
            item["metrics"] = {k: scores[k]["score"] for k in ("E", "P", "Q")}
            item["metrics"].update(
                {
                    f"{k}_pass": int(scores[k]["score"] >= threshold)
                    for k, threshold in (("E", 4), ("P", 3), ("Q", 3))
                }
            )
            item["metrics"]["all_edit_pass"] = int(scores["all_edit_pass"])
            item["evidence"] = {k: scores[k]["evidence"] for k in ("E", "P", "Q")}
        rows.append(item)
    return rows


def render(report):
    lines = [
        "# CompBench 多目标补充 E/P/Q：格式恢复后结果",
        "",
        "本表是补充自动诊断，不替代 CompBench 官方指标。E/P/Q 为 0–4 分；整条通过要求 E=4、P≥3、Q≥3。",
        "置信区间按固定源场景聚类配对 bootstrap，10,000 次。",
        "",
        f"恢复 {len(report['syntax_recovery']['repaired'])} 条已有答案的 JSON 语法；未重新推理、未填补或改写评分。",
        f"仍无法恢复：{len(report['syntax_recovery']['rejected'])} 条。原始记录和原始报告保留不变。",
        "",
    ]
    for task, label in (
        ("all", "全部 144 条"),
        ("multi_object_add", "多目标添加 72 条"),
        ("multi_object_remove", "多目标删除 72 条"),
    ):
        lines += [
            f"## {label}",
            "",
            "| 方法 | 有效/总数 | E ↑ | P ↑ | Q ↑ | E 通过 % | 整条通过 % [95% CI] |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for r in report["rows"]:
            if r["task"] != task:
                continue
            mean = r["mean"]
            if mean is None:
                values = "— | — | — | — | 缺分"
            else:
                low, high = r["CI95"]["all_edit_pass"]
                values = (
                    f"{mean['E']:.3f} | {mean['P']:.3f} | {mean['Q']:.3f} | "
                    f"{100 * mean['E_pass']:.1f} | {100 * mean['all_edit_pass']:.1f} "
                    f"[{100 * low:.1f}, {100 * high:.1f}]"
                )
            lines.append(f"| {r['model']} | {r['scored']}/{r['total']} | {values} |")
        lines.append("")
    lines += [
        "## 读取与复核",
        "",
        f"- 原始报告：`{report['syntax_recovery']['source_report']}`。",
        f"- 原始报告 SHA256：`{report['syntax_recovery']['source_report_sha256']}`。",
        "- `OVERLAY.json` 记录恢复项、拒绝项、源文件哈希与严格校验结果。",
        "- `repairs/<key>.json` 保留精确删除的字符位置及恢复的 JSON。",
        "- `SOURCE_RECORDS.json` 固定全部 admission/raw/effective 的 SHA256。",
        "- 原报告全部逐条结果与统计已先复算通过；未受影响的行、方法差值和共享抽样索引完全一致。",
        "- 冒烟目视检查曾发现自动 Judge 误判与数量判断疑点；本修复仅处理语法，没有人工改分。",
        "",
    ]
    return "\n".join(lines)


def run(bundle, original_root, source_report, output):
    bundle, original_root = Path(bundle).resolve(), Path(original_root).resolve()
    source_report, output = Path(source_report).resolve(), Path(output).resolve()
    if output == original_root or output.is_relative_to(original_root):
        raise ValueError("Repair output must be outside the immutable original results")
    if not source_report.is_relative_to(original_root):
        raise ValueError("Source report must belong to original results")
    source = read(source_report)
    plan = load(bundle, verify_assets=False)
    config = read(original_root / "CONFIGURATION.json")
    if config["smoke"] or config["plan_digest"] != plan["digest"]:
        raise ValueError("Require the full formal plan, never smoke")
    expected = sorted(plan["requests"])
    if config["request_keys"] != expected or len(expected) != 720:
        raise ValueError("Require the complete frozen 720-key cohort")
    identity = digest(
        {
            "plan_digest": plan["digest"],
            "engine": config["engine"],
            "versions": config["packages"],
            "source": config["source"],
            "smoke": False,
            "keys": expected,
        }
    )
    if identity != config["identity"] or source["identity"] != identity:
        raise ValueError("Scientific Judge identity mismatch")
    for name in ("worker.py", "rubric.py", "common.py"):
        path = Path(__file__).parents[1] / "vlm_judge" / name
        checked(path, config["source"][name])
    checked(Path(__file__).parents[2] / "v2/judge.py", config["source"]["native_backend"])
    ready_before, report_before = sha(bundle / "READY.json"), sha(source_report)
    bindings = {b["request_key"]: b for b in plan["bindings"]}

    def validate(key):
        values, hashes = {}, {}
        for kind in ("admissions", "raw", "effective"):
            data = (original_root / kind / f"{key}.json").read_bytes()
            hashes[kind] = hashlib.sha256(data).hexdigest()
            values[kind] = json.loads(data)
            if values[kind]["identity"] != identity or values[kind]["request_key"] != key:
                raise ValueError(f"Wrong {kind} binding: {key}")
        if values["effective"] != effective(values["raw"], identity, key):
            raise ValueError(f"Raw/effective mismatch: {key}")
        return key, values, hashes

    with ThreadPoolExecutor(max_workers=8) as pool:
        entries = list(pool.map(validate, expected))
    records = {key: values["effective"] for key, values, hashes in entries}
    original_cases = per_case(plan, records)
    baseline = {
        "protocol": plan["configuration"]["rubric"]["protocol"],
        "plan_digest": plan["digest"],
        "identity": identity,
        "smoke": False,
        **aggregate(original_cases, plan),
        "per_case": original_cases,
    }
    baseline["digest"] = digest(baseline)
    if baseline != source:
        raise ValueError("Recomputed original report does not exactly match; abort overlay")
    repairs, rejected, source_records = [], [], {}
    fingerprint = {p.name: sha(p) for p in sorted(Path(__file__).parent.glob("*.py"))}
    for key, values, hashes in entries:
        source_records[key] = hashes
        if values["effective"]["status"] != "judge_failed":
            continue
        proof = {
            "request_key": key,
            "model": bindings[key]["model"],
            "case_id": bindings[key]["case_id"],
            "original_files_sha256": hashes,
            "original_error": values["effective"]["error"],
            "repair_code": fingerprint,
        }
        try:
            recovery = recover(values["raw"]["answer"])
        except (ValueError, KeyError, TypeError) as exc:
            rejected.append({**proof, "rejection": f"{type(exc).__name__}: {exc}"})
            continue
        proof.update(recovery)
        repairs.append(proof)
        records[key] = {"status": "scored", "scores": recovery["scores"]}
    cases = per_case(plan, records)
    new_stats = aggregate(cases, plan)
    if new_stats["bootstrap"] != baseline["bootstrap"]:
        raise ValueError("Paired bootstrap indices changed")
    changed = {p["request_key"] for p in repairs}
    for before, after in zip(original_cases, cases):
        if before["request_key"] not in changed and before != after:
            raise ValueError("Unrepaired case changed")
    changed_models_tasks = {
        (p["model"], c["task"])
        for p in repairs
        for c in plan["cases"]
        if c["case_id"] == p["case_id"]
    }
    affected = changed_models_tasks | {(m, "all") for m, task in changed_models_tasks}
    checked_rows = 0
    for before, after in zip(source["rows"], new_stats["rows"]):
        if (before["model"], before["task"]) not in affected:
            if before != after:
                raise ValueError("Unchanged row statistics differ")
            checked_rows += 1
    difference_map = {(x["task"], x["comparison"]): x for x in new_stats["paired_differences"]}
    for before in source["paired_differences"]:
        if difference_map.get((before["task"], before["comparison"])) != before:
            raise ValueError("Existing paired comparison changed")
    metadata = {
        "rule": RULE,
        "source_report": str(source_report),
        "source_report_sha256": report_before,
        "source_root": str(original_root),
        "ready_sha256": ready_before,
        "plan_digest": plan["digest"],
        "source_configuration_sha256": sha(original_root / "CONFIGURATION.json"),
        "source_records_digest": digest(source_records),
        "repaired": repairs,
        "rejected": rejected,
        "additional_judge_calls": 0,
        "additional_gpu_seconds": 0,
        "checks": {
            "original_report_exact_match": True,
            "unaffected_rows_exact_match": checked_rows,
            "bootstrap_indices_identical": True,
            "unchanged_cases_exact_match": len(expected) - len(repairs),
        },
    }
    result = copy.deepcopy(source)
    result.pop("digest")
    result.update(new_stats, per_case=cases, syntax_recovery=metadata)
    result["digest"] = digest(result)
    checked(bundle / "READY.json", ready_before)
    checked(source_report, report_before)
    output.mkdir(parents=True, exist_ok=True)
    for proof in repairs:
        save(output / "repairs" / f"{proof['request_key']}.json", proof, immutable=True)
    save(output / "SOURCE_RECORDS.json", source_records, immutable=True)
    save(output / "OVERLAY.json", metadata, immutable=True)
    save(output / "MERGED_REPORT.json", result, immutable=True)
    markdown = render(result)
    path = output / "MERGED_REPORT.md"
    if path.exists() and path.read_text() != markdown:
        raise ValueError("Different Markdown report already exists")
    path.write_text(markdown)
    return {
        "repaired": len(repairs),
        "unresolved": len(rejected),
        "scored": sum(x["status"] == "scored" for x in cases),
        "total": len(cases),
        "complete_rows": sum(x["complete"] for x in result["rows"]),
        "report": str(output / "MERGED_REPORT.json"),
        "report_sha256": sha(output / "MERGED_REPORT.json"),
        "checks": metadata["checks"],
    }
