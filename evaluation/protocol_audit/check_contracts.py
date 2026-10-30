"""Read-only data audit and CPU execution of selected official parser functions."""

import ast
import collections
import hashlib
import importlib.util
import json
import re
from pathlib import Path

from PIL import Image
import numpy as np

ROOT = Path("/tmp/ifbench/protocol_review_20261027")
REPO = Path("/opt/tiger/tanyue/if-bench")
DATA = Path("/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2")


def function(path, name):
    tree = ast.parse(path.read_text())
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    namespace = {"re": re, "json": json}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


def main():
    manifest = REPO / "data/v2_2.6.0/cases.jsonl"
    cases = [json.loads(line) for line in manifest.read_text().splitlines() if line]
    units = [u for c in cases for u in c["units"]]
    audit = {
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "protocol_sha256": hashlib.sha256(
            Path("/opt/tiger/tanyue/PROTOCOL.md").read_bytes()
        ).hexdigest(),
        "cases": len(cases),
        "units": len(units),
        "unique_sources": len({c["source"]["image_id"] for c in cases}),
        "K": dict(collections.Counter(len(c["units"]) for c in cases)),
        "operations": dict(collections.Counter(u["operation"] for u in units)),
        "source_roles": dict(
            collections.Counter(u["mask_semantics"]["source_role"] for u in units)
        ),
        "original_interaction": dict(collections.Counter(str(u["interaction"]) for u in units)),
        "all_masks_are_source_selectors": all(
            not u["mask_semantics"]["output_difference_ground_truth"] for u in units
        ),
        "missing_ref_fields": sum(not u["instruction_spec"].get("ref") for u in units),
        "human_verified_cases": sum(
            bool(c.get("review", {}).get("independent_human_verified")) for c in cases
        ),
        "examples": [],
    }
    samples = [
        cases[0],
        next(
            c
            for c in cases
            if len(c["units"]) == 2 and any(u["operation"] == "add" for u in c["units"])
        ),
    ]
    for case in samples:
        example = {"case_id": case["id"], "units": []}
        source = DATA / case["source"]["image"]
        example["source_hash_matches"] = (
            hashlib.sha256(source.read_bytes()).hexdigest() == case["source"]["sha256"]
        )
        for u in case["units"]:
            path = DATA / u["target"]["mask"]
            mask = np.asarray(Image.open(path).convert("L")) > 127
            ys, xs = np.where(mask)
            x, y = u["target"]["point"]
            example["units"].append(
                {
                    "id": u["id"],
                    "operation": u["operation"],
                    "ref": u["instruction_ref"],
                    "noref": u["instruction_noref"],
                    "source_role": u["mask_semantics"]["source_role"],
                    "mask_hash_matches": hashlib.sha256(path.read_bytes()).hexdigest()
                    == u["target"]["mask_sha256"],
                    "stored_box": u["target"]["box"],
                    "tight_half_open_box": [
                        int(xs.min()),
                        int(ys.min()),
                        int(xs.max() + 1),
                        int(ys.max() + 1),
                    ],
                    "point_in_mask": bool(mask[y, x]),
                }
            )
        audit["examples"].append(example)
    src = ROOT / "sources"
    spec = importlib.util.spec_from_file_location("official_bbox", src / "flux3/src/flux3/bbox.py")
    bbox = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bbox)
    original = [
        {
            "id": 1,
            "from": 0,
            "src_bbox": [0.1, 0.2, 0.3, 0.4],
            "tgt_bbox": [0.1, 0.2, 0.3, 0.4],
            "desc": "Edit",
        }
    ]
    corrected = [
        {
            "id": "obj_1",
            "from": "ref_image_0",
            "src_bbox": [0.1, 0.2, 0.3, 0.4],
            "tgt_bbox": [0.1, 0.2, 0.3, 0.4],
            "desc": "the selected region",
        }
    ]
    new = {
        "id": "obj_2",
        "from": "target",
        "src_bbox": None,
        "tgt_bbox": [100, 200, 300, 400],
        "desc": "a red umbrella",
    }
    checks = {
        "flux3_original_rows": bbox.to_canvas(original),
        "flux3_original_finished": bbox.is_finished("<1> " + json.dumps(bbox.to_canvas(original))),
        "flux3_corrected_rows": bbox.to_canvas(corrected),
        "flux3_corrected_finished": bbox.is_finished(
            "<obj_1> " + json.dumps(bbox.to_canvas(corrected))
        ),
        "flux3_added_row_valid": bbox.valid_added(new, "Add <obj_2>") is not None,
    }
    extract = function(src / "replan/replan/pipelines/replan.py", "extract_bbox_from_response")
    region = '[{"bbox_2d":[10,20,30,40],"hint":"Change the selected region to red."}]'
    checks["replan_html_entities_rejected"] = (
        extract(None, "&lt;region&gt;" + region + "&lt;/region&gt;") is None
    )
    checks["replan_literal_tags_accepted"] = (
        extract(None, "<region>" + region + "</region>") is not None
    )
    qp = function(src / "mirage/inference.py", "qwen_prompt")
    checks["mirage_noref_prompt"] = qp(
        {"refer_object": "the selected region", "new_instruction": "Remove the selected region."}
    )
    checks["mice_mask_box_assertions"] = []
    tree = ast.parse((src / "mice/flux2/pipeline_flux2_klein.py").read_text())
    nodes = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Assert) and "instance_bboxes_xyxy_normalized" in ast.unparse(n)
    ]
    code = compile(
        ast.Module(body=nodes, type_ignores=[]), "official_mice_region_assertions", "exec"
    )
    for boxes, masks in [
        (None, None),
        ([[0.1, 0.2, 0.3, 0.4]], None),
        (None, [np.ones((8, 8))]),
        ([[0.1, 0.2, 0.3, 0.4]], [np.ones((8, 8))]),
    ]:
        ns = {"instance_bboxes_xyxy_normalized": boxes, "instance_masks_yx": masks}
        try:
            exec(code, ns)
            outcome = "accepted"
        except AssertionError as e:
            outcome = str(e)
        checks["mice_mask_box_assertions"].append(
            {"boxes": boxes is not None, "masks": masks is not None, "outcome": outcome}
        )
    checks["scope"] = (
        "Actual upstream parser/assert execution only, not end-to-end model validation."
    )
    (ROOT / "checks/data_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2))
    (ROOT / "checks/interface_checks.json").write_text(
        json.dumps(checks, ensure_ascii=False, indent=2)
    )
    print(
        json.dumps(
            {"data": {k: v for k, v in audit.items() if k != "examples"}, "checks": checks},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
