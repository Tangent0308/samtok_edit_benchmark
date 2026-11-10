"""Post-hoc recovery report, preserving the original full-run evidence."""

from pathlib import Path

from samtok_benchmark.external_compbench.multitarget.report import combine, render
from samtok_benchmark.external_full.report import report as official_report
from samtok_benchmark.external_refedit.data import immutable, read
from samtok_benchmark.io import sha256_file
from .plan import load


def report(control, parent_report, output):
    plan, _ = load(control)
    parent_report, output = Path(parent_report), Path(output)
    original = read(parent_report)
    root = Path(plan["results_root"])
    official_report(
        plan["bundle"],
        root / "run",
        root / "scores",
        output / "nine",
        ["sitedit"],
        plan["case_ids"],
    )
    correction = read(output / "nine/REPORT.json")
    merged = combine(
        {
            **plan,
            "original_report": str(parent_report),
            "original_report_sha256": sha256_file(parent_report),
        },
        original,
        correction,
    )
    previous = {(r["model"], r["case_id"]): r for r in original["per_case"]}
    for i, row in enumerate(merged["per_case"]):
        if row["model"] == "sitedit" and row["case_id"] in plan["case_ids"]:
            row["provenance"] = "authorized_recovery9"
        else:
            merged["per_case"][i] = previous[row["model"], row["case_id"]]
    merged.update(
        schema="compbench.sitedit.recovery9.merged.v1",
        post_hoc=True,
        disclosure="User-authorized repair of six formatting failures and prompt debugging on three known enumeration failures. Original records and all trials retained; no score-based output selection.",
        unchanged_records=3285 * len(merged["models"]) - 9,
        correction_report=str(output / "nine/REPORT.json"),
        correction_report_sha256=sha256_file(output / "nine/REPORT.json"),
    )
    immutable(output / "MERGED_REPORT.json", merged)
    text = render(merged).replace(
        "多目标添加/删除共 144 条全部采用修正后的结果，不按得分选择旧输出。其余请求和基线只读复用原始正式记录。",
        "在逐目标重测上进一步替换九条授权修复结果；保留六条格式恢复、三条枚举调试的全部原始证据。其余请求和基线不变。这是事后修复结果，不是未经调试的一次性评测。",
    )
    path = output / "MERGED_REPORT.md"
    if path.exists() and path.read_text() != text:
        raise ValueError("Existing report differs")
    path.write_text(text)
    return merged
