"""Reproduce the visually designed, bilingual 2.1.0 instructions from release 2.0.0."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from instructions.designs import ADD, ATTRIBUTE, REPLACE
from instructions.scopes import scope_zh
from samtok_benchmark.io import read_jsonl, sha256_file, write_json, write_jsonl

BASELINE_SHA = "bfba2cc937bb0711d0858a4a44c6fb39ab0014c57d5adaef37b6fc7ac5ad5316"
DESIGN = Path(__file__).parent / "instructions/design.tsv"
OP = {"A": "add", "R": "replace", "D": "remove", "C": "attribute"}


def revise(baseline, output):
    if sha256_file(baseline) != BASELINE_SHA:
        raise ValueError(
            "Use the immutable 2.0.0 baseline; do not revise an already revised manifest"
        )
    cases = read_jsonl(baseline)
    rows = [line.split("|") for line in DESIGN.read_text().splitlines() if line.strip()]
    if [int(r[0]) for r in rows] != list(range(len(cases))):
        raise ValueError("Design must cover every case exactly once in baseline order")
    changes = []
    for case, row in zip(cases, rows):
        if len(row) - 1 != len(case["units"]):
            raise ValueError("Design/unit count mismatch")
        for unit, entry in zip(case["units"], row[1:]):
            ref_zh, key = entry.rsplit("@", 1)
            code, _, value = key.partition(":")
            target = unit["target"]
            # Redundant hidden-foot clauses are evaluator scope, not user instructions.
            ref_en = target["ref"].replace(", excluding any hidden foot", "")
            scope_en = target["scope"].replace(", excluding any hidden foot", "")
            # These masks cover label panels / a bag body, not whole source objects.
            if case["id"] == "v2-paco_000000281687" and unit["id"] == "U3":
                ref_en = "the body of the small handbag hanging in front of the striped shirt"
            if case["id"] == "v2-paco_000000548780" and unit["id"] == "U4":
                ref_en = (
                    "the body of the small handbag carried by the standing woman in the back left"
                )
            target["ref_zh"], target["scope_zh"] = (
                ref_zh,
                scope_zh(target["scope"], target["category"]),
            )
            target["ref"] = ref_en
            unit["operation"] = OP[code]
            unit["attribute_kind"] = None
            if code == "A":
                en, zh = ADD[value]
                semantics = "addition_support"
                completion = (
                    "The requested new accessory is visibly present in the stated count and attachment/location on the selected support. "
                    "Keep the underlying support and its existing parts; a recolor, material change or replacement of that support does not count as addition. "
                    "The accessory must read as a separate physical layer/item with an appropriate edge or attachment, not merely a painted texture. For repeated additions, cover each specified visible attachment site. "
                )
            elif code == "R":
                new_en, new_zh = REPLACE[value]
                en, zh = "Replace {t} with " + new_en + ".", "将{t}替换为" + new_zh + "。"
                semantics = "existing_edit_target"
                completion = (
                    "The selected old component is replaced in situ by the requested visibly different component design, at every specified visible part. "
                    "A recolor/material swap without the requested shape or construction change is insufficient; an extra copy beside an unchanged original fails. "
                )
            elif code == "D":
                en, zh = "Remove {t}.", "移除{t}。"
                semantics = "existing_edit_target"
                completion = (
                    "All specified visible pieces of the selected component are absent. Reconstruct the locally revealed surface, cavity or background coherently; "
                    "do not remove the rest of the parent object. For a removed shade retain the fixture; for a drawer front retain the drawer/cabinet structure; "
                    "for a sleeve retain the arm and the remainder of the garment. "
                )
            else:
                new_en, new_zh, kind = ATTRIBUTE[value]
                unit["attribute_kind"] = kind
                if kind == "material":
                    en, zh = (
                        "Change the material of {t} to " + new_en + ".",
                        "将{t}的材质改为" + new_zh + "。",
                    )
                elif kind == "tint":
                    en, zh = "Apply " + new_en + " to {t}.", "将{t}着色为" + new_zh + "。"
                else:
                    en, zh = "Recolor {t} " + new_en + ".", "将{t}改为" + new_zh + "。"
                semantics = "existing_edit_target"
                completion = (
                    "All specified visible surfaces acquire the requested appearance, including occlusion-separated pieces. "
                    "Retain their geometry, markings and identity; for glass retain transparency, contents and fill level. "
                )
            unit["instruction_ref"] = en.format(t=ref_en)
            unit["instruction_noref"] = en.format(t=scope_en)
            unit["instruction_ref_zh"] = zh.format(t=ref_zh)
            unit["instruction_noref_zh"] = zh.format(t=target["scope_zh"])
            unit["completion_requirement"] = (
                completion + "Requested result: " + unit["instruction_ref"]
            )
            unit["edit_contract"] = {
                "locator_semantics": semantics,
                "source_mask_role": "official visible source support/part localization, not an output footprint",
                "allowed_local_effects": "requested geometry, new occlusion/revealed surfaces, immediate attachments and physically necessary local shadows/reflections",
                "definition": completion.strip(),
            }
            unit["instruction_design"] = {
                "version": "2.1.0",
                "key": key,
                "review_kind": "ai_direct_visual",
                "reviewer": "assistant",
            }
            changes.append(
                {
                    "case_id": case["id"],
                    "unit_id": unit["id"],
                    "design_key": key,
                    "operation": unit["operation"],
                    "ref_zh": ref_zh,
                    "scope_zh": target["scope_zh"],
                    "instruction_ref": unit["instruction_ref"],
                    "instruction_noref": unit["instruction_noref"],
                    "instruction_ref_zh": unit["instruction_ref_zh"],
                    "instruction_noref_zh": unit["instruction_noref_zh"],
                }
            )
        case["instruction_review"] = {
            "version": "2.1.0",
            "kind": "ai_direct_visual",
            "reviewer": "assistant",
            "decision": "accept",
            "source_viewed": True,
            "base_mask_review": case["review"]["kind"],
            "evidence_zh": case["difficulty"]["evidence_zh"]
            + " 本轮设计："
            + " ".join(u["id"] + " " + u["instruction_ref_zh"] for u in case["units"]),
            "independent_human_verified": False,
        }
    count = Counter(u["operation"] for c in cases for u in c["units"])
    assert count == {"add": 135, "remove": 135, "replace": 135, "attribute": 135}, count
    output.mkdir(parents=True, exist_ok=True)
    write_jsonl(output / "cases.jsonl", cases)
    write_jsonl(output / "instruction_design_revisions.jsonl", changes)
    lengths = [
        len(u["instruction_ref" if u["interaction"]["has_ref"] else "instruction_noref"].split())
        for c in cases
        for u in c["units"]
    ]
    report = {
        "release": "2.1.0",
        "baseline_manifest_sha256": BASELINE_SHA,
        "manifest_sha256": sha256_file(output / "cases.jsonl"),
        "design_sha256": sha256_file(DESIGN),
        "cases": len(cases),
        "units": len(changes),
        "unit_operations": dict(count),
        "case_operation_presence": dict(
            Counter(op for c in cases for op in {u["operation"] for u in c["units"]})
        ),
        "instruction_words": {
            "min": min(lengths),
            "mean": round(sum(lengths) / len(lengths), 2),
            "max": max(lengths),
        },
        "bilingual_units": len(changes),
        "source_visual_cases": len(cases),
        "source_and_mask_assets_changed": False,
        "independent_human_verified": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(output / "instruction_revision.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(revise(args.baseline, args.output))
