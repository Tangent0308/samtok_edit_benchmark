#!/usr/bin/env python3
"""Freeze the reviewed one/two-region selection for every MIRAGE case."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


DEFAULT_ROOT = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/datasets/MIRAGE/benchmark"
)
DEFAULT_OUTPUT = Path(__file__).with_name("mirage_selected_regions.jsonl")

# One-based indices into MIRAGE's five released regions. The list was fixed by
# source-only review: small parts and structure-sensitive edits are preferred;
# pairs must address distinct same-class instances and increase binding
# difficulty. The six pilot decisions (0, 2, 25, 61, 63, 93) are preserved.
CHOICES: dict[int, list[int]] = {
    0: [1, 3], 1: [2, 3], 2: [1, 2], 3: [2, 3], 4: [1, 3],
    5: [1, 2], 6: [1, 2], 7: [2, 3], 8: [2, 3], 9: [1, 2],
    10: [1, 2], 11: [1, 2], 12: [2, 3], 13: [2, 3], 14: [1, 3],
    15: [2, 5], 16: [1, 2], 17: [1, 3], 18: [2, 3], 19: [1, 2],
    20: [1, 5], 21: [2, 3], 22: [1, 2], 23: [2, 3], 24: [2, 3],
    25: [2], 26: [1, 3], 27: [1, 3], 28: [1, 2], 29: [1, 4],
    30: [1, 3], 31: [1, 3], 32: [1, 2], 33: [2, 3], 34: [1, 3],
    35: [1, 4], 36: [1, 2], 37: [2, 3], 38: [1, 3], 39: [1, 3],
    40: [1, 2], 41: [1, 2], 42: [1, 3], 43: [1, 3], 44: [1, 2],
    45: [3, 4], 46: [1, 2], 47: [3, 4], 48: [2, 3], 49: [1, 2],
    50: [1, 4], 51: [3, 4], 52: [1, 3], 53: [2, 3], 54: [2, 4],
    55: [3, 4], 56: [2, 4], 57: [2, 4], 58: [2, 3], 59: [4, 5],
    60: [2, 3], 61: [3, 4], 62: [1, 2], 63: [1, 4], 64: [1, 4],
    65: [4, 5], 66: [1, 4], 67: [2, 5], 68: [2, 3], 69: [1, 4],
    70: [3, 4], 71: [1, 3], 72: [2, 3], 73: [1, 2], 74: [1, 2],
    75: [1, 5], 76: [1, 3], 77: [1, 5], 78: [2, 4], 79: [3, 4],
    80: [2, 3], 81: [1, 4], 82: [2, 3], 83: [2, 3], 84: [1, 2],
    85: [2, 4], 86: [1, 3], 87: [2, 3], 88: [3, 4], 89: [1, 3],
    90: [2, 3], 91: [1, 4], 92: [2, 3], 93: [4, 5], 94: [1, 5],
    95: [1, 3], 96: [2, 5], 97: [3, 4], 98: [2, 5], 99: [2, 3],
}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def normalize_operation(instruction: str) -> str:
    first = instruction.strip().split(maxsplit=1)[0].lower()
    if first == "add":
        return "add"
    if first == "remove":
        return "remove"
    if first in {"change", "make", "replace"}:
        return "replace"
    raise ValueError(f"unsupported MIRAGE atomic operation: {instruction}")


def aggregate_operation(operations: list[str]) -> str:
    return operations[0] if len(set(operations)) == 1 else "mixed"


def sentence(text: str, capitalize: bool = True) -> str:
    value = re.sub(r"\s+", " ", text.strip().rstrip("."))
    if capitalize and value:
        value = value[0].upper() + value[1:]
    return value + "."


def compose_location_instruction(clauses: list[str], indices: list[int]) -> str:
    selected = [clauses[index - 1].strip().rstrip(".") for index in indices]
    value = ", and ".join(selected)
    return sentence(value)


def compose_region_instruction(candidates: list[dict], indices: list[int]) -> str:
    parts = []
    for position, index in enumerate(indices, 1):
        edit = candidates[index - 1]["new_instruction"].strip().rstrip(".")
        edit = edit[0].lower() + edit[1:]
        parts.append(f"For {{region_{position}}}, {edit}.")
    return " ".join(parts)


def selection_reason(candidates: list[dict], indices: list[int]) -> str:
    targets = [candidates[index - 1]["refer_object"] for index in indices]
    if len(indices) == 1:
        return (
            f"Selected the single structure-sensitive local target ({targets[0]}); "
            "adding a weaker second edit would dilute the case."
        )
    return (
        "Selected two localized edits on distinct same-class instances "
        f"({targets[0]}; {targets[1]}) to maximize ordinal/directional binding and "
        "small-part or structure-sensitive editing difficulty."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    annotations = read_jsonl(args.benchmark_root / "annotations.jsonl")
    crop_rows = read_jsonl(args.benchmark_root / "crops/crop_instruction.jsonl")
    candidates_by_image: dict[str, list[dict]] = {}
    for row in crop_rows:
        candidates_by_image.setdefault(row["original_image"], []).append(row)

    if len(annotations) != 100 or set(CHOICES) != set(range(100)):
        raise ValueError("MIRAGE selection must cover exactly cases 0..99")

    output = []
    for case_id, annotation in enumerate(annotations):
        image_name = annotation["image"]
        candidates = candidates_by_image.get(image_name, [])
        if len(candidates) != 5 or len(annotation["mask"]) != 5:
            raise ValueError(f"case {case_id}: expected five aligned candidates and masks")
        indices = CHOICES[case_id]
        if len(indices) not in {1, 2} or len(set(indices)) != len(indices):
            raise ValueError(f"case {case_id}: invalid selection {indices}")
        clauses = re.split(",\\s+and\\s+", annotation["editing_instruction"].rstrip("."), flags=re.I)
        if len(clauses) != 5:
            raise ValueError(f"case {case_id}: cannot align five full-instruction clauses")
        atoms = []
        operations = []
        for position, index in enumerate(indices, 1):
            candidate = candidates[index - 1]
            operation = normalize_operation(candidate["new_instruction"])
            operations.append(operation)
            atoms.append(
                {
                    "region": position,
                    "source_region_index": index,
                    "refer_object": candidate["refer_object"],
                    "edit_instruction": sentence(candidate["new_instruction"]),
                    "operation": operation,
                    "released_bbox": candidate["bbox"],
                }
            )
        output.append(
            {
                "candidate_id": f"mirage_{case_id:03d}",
                "source_dataset": "MIRAGE",
                "source_split": "test",
                "source_row": case_id,
                "source_record_id": image_name,
                "source_group_id": f"mirage-source-{case_id:03d}",
                "selected_region_indices": indices,
                "selected_atomic_edits": atoms,
                "instruction_original": compose_location_instruction(clauses, indices),
                "region_only_instruction": compose_region_instruction(candidates, indices),
                "edit_type": aggregate_operation(operations),
                "local_caption": "; ".join(
                    atom["edit_instruction"].rstrip(".") for atom in atoms
                ) + ".",
                "target_prompt": None,
                "has_gt_image": False,
                "same_class_multi_instance_proxy": True,
                "multi_object_scene": True,
                "source_only_review": True,
                "selection_status": "accepted",
                "selection_focus": [
                    "ordinal_or_directional_instance",
                    "fine_grained_local_target",
                    "multi_instance_binding" if len(indices) == 2 else "structure_sensitive_single_target",
                ],
                "selection_reason": selection_reason(candidates, indices),
            }
        )

    atomic_text(
        args.output,
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in output),
    )
    report = {
        "status": "passed",
        "source_cases": len(annotations),
        "selected_cases": len(output),
        "selected_regions": sum(len(row["selected_region_indices"]) for row in output),
        "counts_by_region_count": dict(sorted(Counter(len(row["selected_region_indices"]) for row in output).items())),
        "counts_by_edit_type": dict(sorted(Counter(row["edit_type"] for row in output).items())),
        "selection_uses_model_outputs_or_scores": False,
        "policy": (
            "Source-only manual semantic review prioritizing small parts, structural edits, "
            "and ordinal/directional binding between same-class instances; at most two regions."
        ),
    }
    report_path = args.output.with_name("mirage_selection_stats.json")
    atomic_text(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
