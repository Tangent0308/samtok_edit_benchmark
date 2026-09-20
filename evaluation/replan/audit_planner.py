#!/usr/bin/env python3
"""Count exact reuse of the two bbox examples in RePlan's output template.

This is a structural planner audit, not an image-edit quality metric.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

if __package__:
    from .runner import OUTPUT_ROOT, SETTINGS, write_json
else:
    from runner import OUTPUT_ROOT, SETTINGS, write_json

MODELS = ("qwen2511", "flux2_klein4b")
EXAMPLE_BOXES = {(10, 150, 150, 210), (150, 50, 200, 150)}


def audit(root: Path) -> dict:
    records = []
    sidecars = sorted((root / "inference").glob("*/*/[0-9][0-9][0-9][0-9].json"))
    for path in sidecars:
        if path.parent.name not in SETTINGS or path.parent.parent.name not in MODELS:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        hits = [box for region in data.get("predicted_boxes", [])
                if isinstance(region, dict)
                for box in [region.get("bbox_2d")]
                if isinstance(box, (list, tuple)) and len(box) == 4
                and tuple(box) in EXAMPLE_BOXES]
        if hits:
            records.append({
                "model": data["model"], "setting": data["setting"],
                "eval_index": data["eval_index"], "boxes": hits,
                "sidecar": str(path),
            })
    return {
        "definition": "At least one predicted bbox_2d exactly equals one of the two numeric example boxes in the bundled planner output-format template. This is a structural warning, not a manual failure rate.",
        "template_boxes": [list(box) for box in sorted(EXAMPLE_BOXES)],
        "total_sidecars_scanned": len(sidecars),
        "output_records": len(records),
        "distinct_case_setting_pairs": len({(r["eval_index"], r["setting"]) for r in records}),
        "distinct_cases": len({r["eval_index"] for r in records}),
        "by_model": dict(Counter(r["model"] for r in records)),
        "by_setting_records": dict(Counter(r["setting"] for r in records)),
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = audit(args.output_root)
    path = args.report or args.output_root / "reports/qualitative_expanded_20260920/template_coordinate_audit.json"
    write_json(path, result)
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, indent=2))


if __name__ == "__main__":
    main()
