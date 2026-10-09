"""Freeze explicitly reviewed cases, never admit candidates by a numerical score."""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
from pathlib import Path

from PIL import Image
import numpy as np

from samtok_benchmark.io import read_jsonl, sha256_file, write_json, write_jsonl
from samtok_benchmark.v2.dataset import validate
from review_state import final_decisions

REPO = Path(__file__).resolve().parents[1]
MODES = [
    (False, "point"),
    (True, "box"),
    (True, "mask"),
    (True, "none"),
    (False, "box"),
    (True, "point"),
    (False, "mask"),
]

# Explicit task design decisions on already visually examined source parts.
# Removal never deletes supporting legs or an object that supports another target.
REMOVE = {
    (35, 4),
    (39, 2),
    (70, 3),
    (81, 2),
    (134, 1),
    (164, 3),
    (306, 2),
    (381, 2),
    (19, 4),
    (42, 3),
    (48, 1),
    (66, 2),
    (85, 1),
    (111, 2),
    (128, 2),
    (139, 4),
    (158, 3),
    (182, 2),
    (194, 3),
    (195, 3),
    (231, 3),
    (249, 1),
    (257, 1),
    (261, 1),
    (262, 2),
    (267, 3),
    (289, 3),
    (344, 2),
    (352, 1),
    (374, 2),
    (412, 1),
    (424, 2),
    (481, 2),
    (549, 3),
    (127, 2),
    (141, 2),
    (166, 2),
    (441, 1),
    (459, 1),
    (481, 1),
}
REPLACE = {
    (10, 2): "a new oval upholstered backrest with dark red fabric",
    (32, 2): "a new rounded rectangular backrest with vertically stitched navy upholstery",
    (37, 4): "a new oval backrest with teal fabric upholstery",
    (94, 3): "a new oval wooden backrest with three vertical slats",
    (120, 3): "a new rounded rectangular backrest upholstered in teal fabric",
    (217, 3): "a new oval backrest with red fabric upholstery",
    (278, 2): "a new curved wooden back panel with two narrow vertical openings",
    (313, 3): "a new oval backrest upholstered in plain navy fabric",
    (330, 1): "a new rounded rectangular backrest upholstered in red fabric",
    (340, 1): "a new oval backrest upholstered in teal fabric",
    (360, 2): "a new oval backrest upholstered in red fabric",
    (395, 4): "a new oval upholstered backrest with navy fabric",
    (449, 1): "a new round padded backrest on a curved support of the same height",
    (51, 2): "a new cylindrical shade made of pleated white fabric",
    (66, 1): "a new cylindrical shade made of pleated white fabric",
    (67, 4): "a new shallow dome-shaped frosted glass shade",
    (85, 2): "a new cylindrical shade made of pleated white fabric",
    (111, 4): "a new cylindrical shade made of pleated white fabric",
    (139, 1): "a new small cylindrical shade of frosted glass",
    (158, 1): "a new cylindrical shade made of pleated white fabric",
    (182, 1): "a new cylindrical shade made of pleated white fabric",
    (262, 1): "a new upward-facing hemispherical frosted-glass shade",
    (289, 2): "a new upward-facing conical shade made of brushed copper",
    (352, 3): "a new curved shade with narrow vertical pleats in white fabric",
    (447, 1): "a new cylindrical shade made of pleated white fabric",
    (35, 1): "a new rounded light-wood handle with two dark metal rivets",
    (39, 4): "a new rounded light-wood handle with two dark metal rivets",
    (81, 1): "a new rounded light-wood handle with two dark metal rivets",
    (112, 2): "a new rounded light-wood handle with two dark metal rivets",
    (137, 2): "a new rounded light-wood handle with two dark metal rivets",
    (140, 2): "a new rounded light-wood handle with two dark metal rivets",
    (164, 2): "a new ribbed orange rubber screwdriver grip",
    (190, 1): "a new ribbed orange rubber hammer grip",
    (218, 4): "a new rounded light-wood handle with two dark metal rivets",
    (220, 3): "a new rounded light-wood handle with two dark metal rivets",
    (272, 2): "a new rounded light-wood handle with two dark metal rivets",
    (297, 4): "a new rounded light-wood handle with two dark metal rivets",
    (401, 2): "a new rounded light-wood handle with two dark metal rivets",
    (435, 1): "a new rounded light-wood handle with two dark metal rivets",
    (534, 3): "two new ribbed orange rubber grips",
}
MATERIAL = {
    (0, 1): "brushed copper",
    (1, 2): "polished chrome",
    (3, 1): "brushed copper",
    (4, 3): "polished chrome",
    (8, 1): "pale oak with visible wood grain",
    (11, 3): "dark red velvet",
    (12, 3): "teal velvet",
    (20, 1): "navy leather",
    (29, 1): "teal velvet",
    (36, 2): "navy leather",
    (47, 3): "brushed copper",
    (56, 1): "navy leather",
    (60, 2): "dark red velvet",
    (63, 1): "pale oak with visible wood grain",
    (68, 2): "polished chrome",
    (73, 1): "dark red velvet",
    (79, 2): "navy leather",
    (90, 1): "pale oak with visible wood grain",
    (96, 1): "dark red velvet",
    (101, 2): "polished chrome",
    (104, 3): "dark red velvet",
    (116, 1): "navy leather",
    (122, 3): "brushed copper",
    (126, 1): "dark red velvet",
    (131, 1): "navy leather",
    (154, 1): "brushed copper",
    (184, 3): "pale oak with visible wood grain",
    (199, 3): "dark red velvet",
    (244, 2): "pale oak with visible wood grain",
    (246, 4): "brushed copper",
    (253, 2): "pale oak with visible wood grain",
    (266, 2): "polished chrome",
    (281, 1): "navy leather",
    (294, 2): "brushed copper",
    (339, 1): "dark red velvet",
    (357, 2): "brushed copper",
    (362, 1): "polished chrome",
    (377, 1): "navy leather",
    (449, 2): "dark red velvet",
    (505, 2): "navy leather",
}

# Fix standalone language and fine-grained scope after source/mask inspection.
REF_FIX = {
    (
        2,
        3,
    ): "the visible legs of the desk immediately behind and to the right of the nearest fully visible desk on the right",
    (
        413,
        2,
    ): "the clear glass immediately to the right of the glass containing the yellow drink, excluding any hidden foot",
    (534, 2): "the narrow book spine immediately to the right of the tall orange book on the shelf",
    (
        133,
        2,
    ): "the rear bumper of the dark hatchback immediately to the right of the car cut off at the far-left edge",
    (261, 2): "the top surface of the small table under the red table lamp on the left",
    (
        357,
        2,
    ): "the exposed front leg of the dining table to the right of the dining chair nearest the camera",
    (363, 2): "the outer lid of the open laptop resting on the folding chair",
    (374, 2): "the shade of the floor lamp to the right of the armchair",
    (412, 2): "the drawer front of the left bedside table supporting the lamp",
    (454, 2): "the body of the brown bag on the rug beside the green bag under the coffee table",
    (458, 3): "the exposed handle of the spoon in the plastic coffee cup",
    (
        465,
        2,
    ): "the solid side of the crate immediately to the right of the leftmost crate beneath the green produce tub",
    (
        465,
        3,
    ): "the visible slatted side of the crate immediately behind the seated man, to the right of the solid-sided crate",
    (475, 2): "the ribbed outside of the larger white bowl near the center of the upper shelf",
    (494, 2): "the handles of the printed shopping bag beside the passenger on the left",
    (505, 2): "both armrests of the armchair to the right of the tall cabinet behind the bird",
    (506, 3): "the folded towel resting on the green bin behind the seated player",
}
SCOPE_FIX = {
    (8, 1): "all six lower drawer fronts",
    (13, 2): "all five doors",
    (21, 4): "the visible curved leg frame",
    (32, 1): "the visible vertical backrest slats",
    (46, 1): "both visible sleeves",
    (46, 2): "both visible sleeves",
    (46, 3): "both visible sleeves",
    (53, 3): "the visible armrest",
    (60, 2): "the visible right armrest",
    (64, 1): "both drawer fronts",
    (108, 2): "the cap collar below the pump",
    (129, 3): "the visible right-hand drawer front",
    (144, 2): "the indicated drawer front",
    (144, 4): "the indicated lower door",
    (150, 1): "the side straps around the visible ear",
    (197, 1): "the visible top drawer front",
    (217, 1): "the curved seat apron",
    (217, 2): "the curved seat apron",
    (244, 2): "the upper two drawer fronts",
    (244, 3): "the headboard including its two rear posts",
    (246, 4): "both front legs",
    (249, 4): "the entire visible scarf",
    (253, 2): "the front of the open upper drawer",
    (257, 2): "the upper drawer front",
    (268, 2): "the opaque circular door frame",
    (268, 3): "the opaque circular door frame",
    (340, 2): "all indicated drawer fronts",
    (341, 2): "the entire visible scarf",
    (341, 3): "the visible bag body",
    (345, 3): "the raised lid",
    (350, 1): "the mirror housing",
    (350, 3): "the rectangular mirror housing",
    (352, 1): "the curved shade",
    (352, 3): "the curved shade",
    (365, 1): "the indicated small drawer front",
    (365, 3): "the opaque door frame surrounding the viewing window",
    (383, 4): "the entire visible wine glass",
    (385, 1): "the closed lid",
    (401, 3): "the dark sleeve section behind the striped cuff",
    (403, 2): "the visible bag body",
    (413, 1): "the entire visible glass, excluding any hidden foot",
    (413, 2): "the entire visible glass, excluding any hidden foot",
    (417, 1): "the visible bag body",
    (417, 3): "the front panel",
    (417, 4): "the diagonal bag strap",
    (421, 1): "the entire visible towel",
    (421, 2): "the entire visible towel",
    (421, 3): "the entire visible towel",
    (424, 2): "the detached lampshade",
    (444, 2): "both visible front legs",
    (446, 2): "the visible side panels",
    (465, 1): "the visible side slats",
    (465, 2): "the solid side panel",
    (465, 3): "the visible side slats",
    (483, 2): "the outer casing, excluding the screen and buttons",
    (499, 4): "the upper drawer front",
    (506, 1): "the entire visible towel",
    (506, 3): "the entire visible folded towel",
    (511, 1): "all twelve visible drawer fronts",
    (511, 2): "the exposed footboard rail and its two posts",
    (516, 3): "the exposed tabletop",
    (534, 1): "the visible spine and cover edge",
    (534, 2): "the visible spine and cover edge",
    (540, 1): "the entire visible scarf",
    (540, 4): "the entire visible scarf",
    (545, 2): "the entire visible towel",
    (545, 4): "the entire visible towel",
    (547, 1): "the closed lid",
    (547, 3): "the faucet",
}


def scope_for(index, unit):
    key = index, unit["candidate_unit"]
    if key in SCOPE_FIX:
        return SCOPE_FIX[key]
    ref = REF_FIX.get(key, unit["ref"])
    s = re.split(
        r" of | worn | at | on | beneath | behind | beside | nearest | immediately | to the | through | around ",
        ref,
        maxsplit=1,
    )[0]
    s = re.sub(
        r"\b(red|blue|green|white|black|purple|teal|tan|brown|yellow|turquoise|striped|floral|light-colored|dark|small|large|smaller|larger|wooden|metal|upholstered)\s+",
        "",
        s,
    )
    return s


def task(key, ref, scope, value):
    if key in REMOVE:
        if key == (424, 2):
            template = "Remove {target} completely. Reconstruct the exposed glass tabletop naturally, retaining its transparency and the objects seen through it. Preserve every other object; do not add a lamp, fixture or replacement shade."
            return (
                "remove",
                template.format(target=ref),
                template.format(target=scope),
                "The detached shade is completely absent; the glass table, its transparency and all other objects are preserved, with no invented lamp fixture.",
            )
        template = "Remove {target} completely. Reconstruct the newly exposed surface or background naturally. Keep the remaining object in place and intact; do not remove or add any other component."
        if "shade" in scope:
            template += " Retain the light fixture, support and a plausible exposed bulb or socket."
        return (
            "remove",
            template.format(target=ref),
            template.format(target=scope),
            "The entire specified part is absent, including every visible fragment; the remaining object is intact and the exposed area is plausible.",
        )
    if key in REPLACE:
        template = (
            "Replace {target} with "
            + REPLACE[key]
            + ". Keep its attachment, orientation and approximate footprint, and retain all other parts of the original object. Adapt only the immediate attachment boundary as necessary."
        )
        return (
            "replace",
            template.format(target=ref),
            template.format(target=scope),
            "The original specified part is replaced by "
            + REPLACE[key]
            + "; every requested part is replaced, attached naturally, with no duplicated original part.",
        )
    if key in MATERIAL:
        template = (
            "Change the material of {target} to "
            + MATERIAL[key]
            + ". Preserve its geometry, folds, pose and all other parts. The surface texture and reflections must convincingly match the new material."
        )
        return (
            "attribute",
            template.format(target=ref),
            template.format(target=scope),
            "All specified visible surfaces convincingly have "
            + MATERIAL[key]
            + " material; their geometry and non-target parts are preserved.",
        )
    template = (
        "Recolor {target} "
        + value
        + ". Apply the new color across every specified visible piece while preserving its shape, texture and existing markings. On transparent surfaces use a transparent tint; preserve the identity and level of their contents."
    )
    return (
        "attribute",
        template.format(target=ref),
        template.format(target=scope),
        "Every specified visible piece has the requested "
        + value
        + " color, including occlusion-separated pieces; no original target is left unchanged or replaced by an extra object.",
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    pool = read_jsonl(args.root / "candidate_pool.jsonl")
    reviews = final_decisions(args.root)
    audit = json.loads((args.root / "audit/source_audit.json").read_text())
    if audit["flags"]:
        raise ValueError("Resolve source overlap flags before freeze")
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    cases, provenance, assets, changes = [], [], [], []
    for n, r in enumerate(x for x in reviews if x["decision"] == "accept"):
        c = pool[r["index"]]
        cid = "v2-" + c["candidate_id"]
        dest = out / "assets" / cid
        dest.mkdir(parents=True, exist_ok=True)
        source = dest / "source.jpg"
        shutil.copyfile(args.root / c["source_image"], source)
        Image.open(source).verify()
        original = np.asarray(Image.open(source).convert("RGB"))
        units = []
        selected = list(r["units"])
        random.Random("v2-order-" + cid).shuffle(selected)
        for j, u in enumerate(selected):
            key = r["index"], u["candidate_unit"]
            meta = next(m for m in c["units"] if m["candidate_unit"] == u["candidate_unit"])
            mask = dest / f"U{j + 1}.png"
            shutil.copyfile(args.root / meta["mask"], mask)
            scope = scope_for(r["index"], u)
            ref = REF_FIX.get(key, u["ref"])
            if key[0] == 268:
                ref = ref.replace("the circular door", "the opaque frame of the circular door")
            value = u["value"]
            # Avoid near-no-op blue-on-blue or white-on-white prototypes. This changes
            # only the requested destination color, never an image or annotation.
            if key not in REMOVE | REPLACE.keys() | MATERIAL.keys():
                a = np.asarray(Image.open(mask).convert("L")) > 0
                med = np.median(original[a], axis=0)
                if (
                    ("white" in value and min(med) > 160)
                    or ("blue" in value and med[2] > med[0] * 1.2 and med[2] > med[1] * 1.05)
                    or ("red" in value and med[0] > med[1] * 1.4 and med[0] > med[2] * 1.3)
                    or ("teal" in value and med[1] > med[0] * 1.25 and med[2] > med[0] * 1.15)
                ):
                    value = "bright magenta" if "red" not in value else "bright cyan"
                    changes.append(
                        {
                            "candidate_id": c["candidate_id"],
                            "unit": key[1],
                            "old_value": u["value"],
                            "value": value,
                            "reason": "source-color contrast guard",
                        }
                    )
            op, ir, inn, completion = task(key, ref, scope, value)
            has_ref, locator = MODES[(n + j * 2) % len(MODES)]
            units.append(
                {
                    "id": f"U{j + 1}",
                    "operation": op,
                    "attribute_kind": ("material" if key in MATERIAL else "color")
                    if op == "attribute"
                    else None,
                    "target": {
                        "parent_instance_id": meta["parent_instance_id"],
                        "annotation_id": meta["annotation_id"],
                        "category": meta["category"],
                        "candidate_unit": key[1],
                        "mask": str(mask.relative_to(out)),
                        "mask_sha256": sha256_file(mask),
                        "box": meta["geometry"]["box"],
                        "point": meta["geometry"]["point"],
                        "geometry": meta["geometry"],
                        "ref": ref,
                        "scope": scope,
                    },
                    "interaction": {"has_ref": has_ref, "locator": locator},
                    "instruction_ref": ir,
                    "instruction_noref": inn,
                    "completion_requirement": completion,
                    "preserve": [
                        "All other parts of this physical object, except another explicitly authorized unit.",
                        "All non-target objects, people, background, identity, pose, framing and perspective.",
                        "Adjacent supports, handles, glass openings, visible lettering and occluding objects unless explicitly targeted.",
                        "Existing light direction and coherent local shadows/reflections; only physically necessary local adaptation is allowed.",
                    ],
                }
            )
        card = dest / "review.jpg"
        shutil.copyfile(args.root / r["review_card"], card)
        case = {
            "schema_version": "2.0",
            "id": cid,
            "source": {
                "family_id": c["candidate_id"],
                "image": str(source.relative_to(out)),
                "sha256": sha256_file(source),
                "size": c["source_size"],
                "dataset": c["source_dataset"],
                "split": c["source_split"],
                "image_id": c["source_image_id"],
            },
            "units": units,
            "difficulty": {
                "mechanisms": r["mechanisms"],
                "evidence_zh": r["evidence"],
                "specific_protection_zh": r["protect"],
            },
            "review": {
                "decision": "accept",
                "kind": "ai_direct_visual",
                "reviewer": "assistant",
                "reviewed_at": r["reviewed_at"],
                "evidence": r["evidence"],
                "card": str(card.relative_to(out)),
                "card_sha256": sha256_file(card),
                "independent_human_verified": False,
            },
        }
        cases.append(case)
        provenance.append(
            {
                "id": cid,
                "candidate_index": r["index"],
                "source_original": c["source_original"],
                "annotation_file": c["source_annotation_file"],
                "annotation_sha256": pool[0].get("unused", ""),
                "mask_extraction": c["mask_extraction"],
                "selected_annotations": [u["target"]["annotation_id"] for u in units],
            }
        )
        for file in [source, card] + [out / u["target"]["mask"] for u in units]:
            assets.append(
                {
                    "path": str(file.relative_to(out)),
                    "sha256": sha256_file(file),
                    "bytes": file.stat().st_size,
                }
            )
    # Hash each large annotation file once, not once per case.
    annotation_hashes = {
        s: sha256_file(Path(s)) for s in {p["annotation_file"] for p in provenance}
    }
    for row in provenance:
        row["annotation_sha256"] = annotation_hashes[row["annotation_file"]]
    write_jsonl(out / "cases.jsonl", cases)
    write_jsonl(out / "provenance.jsonl", provenance)
    write_jsonl(out / "asset_manifest.jsonl", assets)
    write_jsonl(out / "visual_decisions.jsonl", reviews)
    shutil.copyfile(args.root / "visual_decisions.jsonl", out / "first_pass_visual_decisions.jsonl")
    if (args.root / "final_review_overrides.jsonl").exists():
        shutil.copyfile(
            args.root / "final_review_overrides.jsonl", out / "final_review_overrides.jsonl"
        )
    write_jsonl(
        out / "instruction_design_revisions.jsonl",
        [
            {
                "candidate_index": i,
                "candidate_unit": j,
                "operation": (
                    "remove"
                    if (i, j) in REMOVE
                    else "replace"
                    if (i, j) in REPLACE
                    else "attribute"
                ),
                "design": REPLACE.get(
                    (i, j), MATERIAL.get((i, j), "remove the visually reviewed component")
                ),
                "review_kind": "assistant_task_design_after_source_visual_review",
            }
            for i, j in sorted(REMOVE | REPLACE.keys() | MATERIAL.keys())
        ],
    )
    write_jsonl(out / "color_contrast_revisions.jsonl", changes)
    write_jsonl(
        out / "language_scope_revisions.jsonl",
        [
            {
                "candidate_index": r["index"],
                "candidate_unit": u["candidate_unit"],
                "original_ref": u["ref"],
                "standalone_ref": REF_FIX.get((r["index"], u["candidate_unit"]), u["ref"]),
                "noref_part_scope": scope_for(r["index"], u),
                "reason": "Standalone referring expression independent of unit order; no-ref text retains only the requested part scope.",
            }
            for r in reviews
            if r["decision"] == "accept"
            for u in r["units"]
        ],
    )
    for name in ["candidate_pool_summary.json"]:
        shutil.copyfile(args.root / name, out / name)
    shutil.copytree(args.root / "audit", out / "audit", dirs_exist_ok=True)
    report = validate(out / "cases.jsonl", out, minimum_cases=200, output=out / "validation.json")
    release = REPO / "data/v2"
    release.mkdir(parents=True, exist_ok=True)
    for file in out.glob("*.json*"):
        shutil.copyfile(file, release / file.name)
    (release / "audit").mkdir(exist_ok=True)
    for name in ["source_audit.json", "overlap_flags.jsonl", "selected_fingerprints.jsonl"]:
        shutil.copyfile(out / "audit" / name, release / "audit" / name)
    write_json(
        release / "release.json",
        {
            "release": "2.0.0",
            "manifest_sha256": sha256_file(out / "cases.jsonl"),
            "assets_bytes": sum(a["bytes"] for a in assets),
            "construction_decisions": len(reviews),
            "admitted": len(cases),
            "rejected": len(reviews) - len(cases),
            "independent_human_verified": False,
            "parent_branch": "v1branch",
            "base_commit": "c72a83c74e8b684040240d487b53d1e6b54b23a8",
            "input_assignment": "deterministic per-image unit shuffle; seven-mode cyclic schedule with stride 2",
            "scope": "Existing-object and part editing. Add-at-new-position tasks are outside this release.",
        },
    )
    shutil.copyfile(release / "release.json", out / "release.json")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
