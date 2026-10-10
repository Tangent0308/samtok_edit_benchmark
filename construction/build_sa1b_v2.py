"""Freeze manually authored, visually reviewed SA-1B cases; never generate task semantics."""

from __future__ import annotations
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import statistics
from instructions.scopes import SCOPES
from samtok_benchmark.io import sha256_file, write_json, write_jsonl

VERSION = "2.2.0"
REPO = Path(__file__).resolve().parents[1]
MODES = [
    (False, "point"),
    (True, "box"),
    (False, "mask"),
    (True, "none"),
    (True, "mask"),
    (False, "box"),
    (True, "point"),
]
OPS = {"A": "add", "R": "replace", "D": "remove", "C": "attribute"}
REF_ZH = {
    (25, "U3"): "右前鱼盘左侧的浅托盘",
    (70, "U2"): "最左侧浅绿色细长袋装商品",
    (95, "U3"): "中间灰发男子毛衣外露出的衬衫领口和袖口",
    (147, "U5"): "后排戴眼镜男子露在背包旁的浅蓝上衣",
    (149, "U4"): "右侧粉色上衣男子紧邻左边观众的T恤",
    (149, "U5"): "中间被表演者伸出手臂挡住的T恤",
    (190, "U4"): "中央后排穿马甲兔子摆件的可见身体",
    (198, "U5"): "白色停放踏板车后方第二辆黑车的前挡泥板",
}


def instruction(recipe, target, payload, chinese=False):
    code, *sub = recipe.split(":")
    subtype = sub[0] if sub else ""
    if chinese:
        if code == "A":
            return f"给{target}加上{payload}。"
        if code == "R":
            return f"将{target}替换为{payload}。"
        if code == "C":
            return (
                f"将{target}"
                + (
                    "的材质改为"
                    if subtype == "material"
                    else "染成"
                    if subtype == "tint"
                    else "改为"
                )
                + f"{payload}。"
            )
        if subtype == "contents":
            return f"移除{target}及其中的物品。"
        if subtype == "part":
            return f"移除{target}的{payload}。"
        if subtype == "lowerlegs":
            return f"剪去{target}的下段裤腿，改成及膝短裤。"
        if subtype == "hem":
            return f"剪去{target}的下摆部分，改成及膝长度。"
        return f"移除{target}。"
    if code == "A":
        return f"Add {payload} to {target}."
    if code == "R":
        return f"Replace {target} with {payload}."
    if code == "C":
        if subtype == "tint":
            return f"Tint {target} {payload}."
        return f"Change the {'material' if subtype == 'material' else 'color'} of {target} to {payload}."
    if subtype == "contents":
        return f"Remove {target}, including its contents."
    if subtype == "part":
        return f"Remove {payload.replace('its ', 'the ', 1)} from {target}."
    if subtype == "lowerlegs":
        return f"Remove the lower legs of {target} to make knee-length shorts."
    if subtype == "hem":
        return f"Remove the lower section of {target} to make it knee-length."
    return f"Remove {target}."


def copy_asset(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if sha256_file(src) != sha256_file(dst):
            raise ValueError(f"changed asset: {dst}")
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset-root", type=Path, required=True)
    p.add_argument("--selection-root", type=Path)
    p.add_argument("--metadata-dir", type=Path, default=REPO / "data/v2")
    args = p.parse_args()
    root = args.dataset_root
    selection = args.selection_root or root / "sa1b_source_selection"
    meta = args.metadata_dir
    sources = json.loads((selection / "gallery_data.json").read_text())
    design_path = REPO / "construction/instructions/design.tsv"
    design_hash = sha256_file(design_path)
    source_manifest_hash = sha256_file(selection / "selected_sources.jsonl")
    designs = {}
    for line in design_path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        n, uid, recipe, ref, scope, payload, zh = line.split("|")
        key = (int(n), uid)
        if key in designs:
            raise ValueError(f"duplicate design {key}")
        designs[key] = {
            "recipe": recipe,
            "ref": ref,
            "scope": scope,
            "payload": payload,
            "payload_zh": zh,
        }
    assert len(sources) == 200 and len(designs) == 785
    cases = []
    inventory = []
    provenance = []
    reviews = []
    design_records = []
    counter = 0
    for number, source in enumerate(sources, 1):
        cid = "v2-" + source["id"]
        base = Path("assets") / cid
        paths = [
            (source["image"], base / "source.jpg"),
            (source["review_image"], base / "selection_review.jpg"),
        ]
        units = []
        for target in source["targets"]:
            uid = target["unit_id"]
            key = (number, uid)
            d = designs[key]
            scope = d["scope"]
            recipe = d["recipe"]
            op = OPS[recipe[0]]
            mask = base / (uid + ".png")
            paths.append((target["mask"], mask))
            refzh = REF_ZH.get(key, target["label_zh"])
            has_ref, locator = MODES[counter % len(MODES)]
            counter += 1
            subregion = recipe in {"D:part", "D:lowerlegs", "D:hem"}
            texts = {}
            for mode, t, tzh in [
                ("ref", d["ref"], refzh),
                ("noref", "the selected " + scope, "选中的" + SCOPES[scope]),
            ]:
                texts["instruction_" + mode] = instruction(recipe, t, d["payload"])
                texts["instruction_" + mode + "_zh"] = instruction(
                    recipe, tzh, d["payload_zh"], True
                )
                if len(texts["instruction_" + mode].split()) > 40:
                    raise ValueError((key, texts["instruction_" + mode]))
            geometry = {
                "area_fraction": target["area_fraction"],
                "significant_components": target["significant_components"],
            }
            contract = {
                "locator_semantics": "addition_support" if op == "add" else "existing_edit_target",
                "source_mask_role": "visible semantic selector, not output difference ground truth",
                "scope_relation": "subregion_of_selected_object"
                if subregion
                else "attachment_to_selected_object"
                if op == "add"
                else "selected_visible_object_or_part",
                "definition": texts["instruction_ref"],
                "allowed_local_effects": "Only physically necessary local attachment, revealed background, occlusion, edge, lighting or shadow changes.",
            }
            completion = (
                texts["instruction_ref"]
                + " Select this instance only; complete the requested change across its relevant visible pieces. "
            )
            completion += (
                "The source object remains, and the added item must have the specified count and attachment."
                if op == "add"
                else "Remove only the named subpart; the rest of the selected object remains."
                if subregion
                else "The old target must be absent; do not leave fragments or add a duplicate beside it."
                if op in {"remove", "replace"}
                else "Change the requested appearance while retaining the selected object geometry."
            )
            u = {
                "id": uid,
                "operation": op,
                "attribute_kind": ("material" if recipe == "C:material" else "color")
                if op == "attribute"
                else None,
                "target": {
                    "parent_instance_id": source["id"] + ":" + target["physical_parent_zh"],
                    "physical_parent_zh": target["physical_parent_zh"],
                    "annotation_id": target["object_id"],
                    "source_category": target["source_category"],
                    "category": scope,
                    "mask": str(mask),
                    "mask_sha256": target["mask_sha256"],
                    "box": target["bbox_xyxy"],
                    "point": target["point_xy"],
                    "geometry": geometry,
                    "ref": d["ref"],
                    "ref_zh": refzh,
                    "scope": scope,
                    "scope_zh": SCOPES[scope],
                    "annotation_origin": target["annotation_origin"],
                },
                "interaction": {"has_ref": has_ref, "locator": locator},
                **texts,
                "completion_requirement": completion,
                "preserve": [
                    "All unrequested parts of this parent, neighboring objects and background; other units authorize their own changes.",
                    source["protected_content_zh"],
                ],
                "edit_contract": contract,
                "instruction_design": {
                    "version": VERSION,
                    "recipe": recipe,
                    "review_kind": "ai_direct_visual",
                    "key": f"{number:03d}:{uid}",
                },
            }
            units.append(u)
            design_records.append(
                {
                    "case_id": cid,
                    "case_number": number,
                    "unit_id": uid,
                    **d,
                    "ref_zh": refzh,
                    **texts,
                }
            )
        assert len(set(u["operation"] for u in units)) == min(4, len(units)), cid
        for old, new in paths:
            copy_asset(selection / old, root / new)
            inventory.append(
                {
                    "path": str(new),
                    "sha256": sha256_file(root / new),
                    "bytes": (root / new).stat().st_size,
                }
            )
        sheet = f"{((number - 1) // 4) * 4 + 1:03d}_{((number - 1) // 4) * 4 + 4:03d}.jpg"
        audit = {
            "case_id": cid,
            "case_number": number,
            "version": VERSION,
            "kind": "ai_direct_visual",
            "reviewer": "assistant",
            "source_viewed": True,
            "selected_mask_overlays_viewed": True,
            "scene_specific_design": True,
            "independent_human_verified": False,
            "authoring_sheet": str(root / "construction/instructions/sheets" / sheet),
            "authoring_sheet_sha256": sha256_file(
                root / "construction/instructions/sheets" / sheet
            ),
            "design_sha256": design_hash,
        }
        reviews.append(audit)
        case = {
            "schema_version": "2.0",
            "id": cid,
            "selection_index": number - 1,
            "source": {
                "dataset": "SA-1B",
                "annotation_dataset": "SA-1B companion dense labels",
                "family_id": source["id"],
                "image_id": source["id"],
                "image": str(base / "source.jpg"),
                "sha256": source["image_sha256"],
                "size": [source["width"], source["height"]],
                "training_catalog_member": source["training_index_member"],
            },
            "units": units,
            "difficulty": {
                "mechanisms": source["difficulty_tags"],
                "scene_zh": source["scene_zh"],
                "evidence_zh": source["difficulty_evidence_zh"],
                "specific_protection_zh": source["protected_content_zh"],
            },
            "review": {
                "decision": "accept",
                "kind": "ai_direct_visual",
                "reviewer": "assistant",
                "evidence": source["difficulty_evidence_zh"],
                "card": str(base / "selection_review.jpg"),
                "card_sha256": sha256_file(root / base / "selection_review.jpg"),
                "independent_human_verified": False,
            },
            "instruction_review": audit,
        }
        cases.append(case)
        provenance.append(
            {
                "case_id": cid,
                "source_id": source["id"],
                "source_index_original": source["source_index"],
                "source_index_resolved": {
                    kind: {
                        **record,
                        "file": record["file"].replace(
                            "/sg_byte_ttlive_strategy_llm/", "/byte_ttlive_strategy_llm/"
                        ),
                    }
                    for kind, record in source["source_index"].items()
                },
                "selected_object_ids": [u["annotation_id"] for u in (x["target"] for x in units)],
                "source_manifest_sha256": source_manifest_hash,
                "training_index_member": source["training_index_member"],
                "training_index_path": source["training_index_path"],
                "selection_visual_review": source["visual_review"],
                "excluded_candidates": source.get("excluded_candidates", []),
            }
        )
    allunits = [u for c in cases for u in c["units"]]
    ops = Counter(u["operation"] for u in allunits)
    assert sorted(ops.values()) == [196, 196, 196, 197]
    srcstats = json.loads((selection / "statistics.json").read_text())
    stats = {
        "release_version": VERSION,
        "cases": len(cases),
        "independent_targets": len(allunits),
        "sources": dict(Counter(c["source"]["dataset"] for c in cases)),
        "targets_per_case": dict(sorted(Counter(len(c["units"]) for c in cases).items())),
        "operations": dict(ops),
        "case_operation_presence": dict(
            Counter(op for c in cases for op in sorted(set(u["operation"] for u in c["units"])))
        ),
        "case_operation_combinations": dict(
            Counter("+".join(sorted(u["operation"] for u in c["units"])) for c in cases)
        ),
        "interactions": dict(
            Counter(
                ("ref" if u["interaction"]["has_ref"] else "noref")
                + "+"
                + u["interaction"]["locator"]
                for u in allunits
            )
        ),
        "operation_by_interaction": {
            op: dict(
                Counter(
                    ("ref" if u["interaction"]["has_ref"] else "noref")
                    + "+"
                    + u["interaction"]["locator"]
                    for u in allunits
                    if u["operation"] == op
                )
            )
            for op in sorted(ops)
        },
        "recipes": dict(Counter(u["instruction_design"]["recipe"] for u in allunits)),
        "scope_relations": dict(Counter(u["edit_contract"]["scope_relation"] for u in allunits)),
        "scope_types": dict(Counter(u["target"]["scope"] for u in allunits)),
        "english_instruction_words": {
            mode: {"min": min(v), "median": statistics.median(v), "max": max(v)}
            for mode in ["ref", "noref"]
            for v in [[len(u["instruction_" + mode].split()) for u in allunits]]
        },
        "source_selection": {
            k: v for k, v in srcstats.items() if k not in {"original_212_modified"}
        },
        "all_cases_maximal_operation_diversity": True,
        "assistant_instruction_reviews": 200,
        "independent_human_reviews": 0,
        "model_evaluation_runs": 0,
        "training_catalog_overlap": 200,
        "checkpoint_exposure_audited": False,
    }
    release = {
        "schema_version": "2.0",
        "release_version": VERSION,
        "name": "SAMTok Benchmark v2 — SA-1B 200",
        "status": "tasks_frozen_pending_independent_review_and_model_evaluation",
        "cases": 200,
        "units": 785,
        "source_selection": "Latest 200 SA-1B cases only",
        "supersedes": "2.1.0 non-SA-1B 212-case release (archived)",
        "manifest": "cases.jsonl",
        "dataset_root": str(root),
        "annotation_geometry": "unchanged visible masks; tight half-open boxes; deterministic mask-interior points",
        "independent_human_verified": False,
        "checkpoint_exposure_audited": False,
    }
    for directory in [meta, root / "benchmark"]:
        write_jsonl(directory / "cases.jsonl", cases)
        write_jsonl(directory / "asset_manifest.jsonl", inventory)
        write_jsonl(directory / "provenance.jsonl", provenance)
        write_jsonl(directory / "instruction_reviews.jsonl", reviews)
        write_jsonl(directory / "instruction_design.jsonl", design_records)
        write_json(directory / "statistics.json", stats)
        write_json(
            directory / "release.json",
            {**release, "manifest_sha256": sha256_file(directory / "cases.jsonl")},
        )
        write_json(
            directory / "instruction_revision.json",
            {
                "version": VERSION,
                "design_sha256": design_hash,
                "reviewed_cases": 200,
                "units": 785,
                "operations": dict(ops),
            },
        )
        write_json(
            directory / "storage.json",
            {
                "dataset_root": str(root),
                "repo_metadata": str(meta),
                "selection_process": str(selection),
                "authoring_process": str(root / "construction/instructions"),
                "archive": str(root / "archive"),
            },
        )
    write_json(
        root / "construction/instructions/progress.json",
        {
            "version": VERSION,
            "reviewed_authored_cases": 200,
            "authored_units": 785,
            "operations": dict(ops),
            "status": "drafts_frozen_for_validation",
        },
    )
    print(
        json.dumps(
            {
                "cases": 200,
                "units": 785,
                "operations": dict(ops),
                "interactions": stats["interactions"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
