"""Build release 2.6.0 from frozen 2.5.0 plus explicit, reviewed revisions.

Protocol 2.0 (docs 07): every no-ref is rendered blind by `render(spec, False)`, and every
source mask is the actually edited region (add: the attachment site). Semantic fixes come
only from revision records in construction/release_2_6/revisions/<case_id>.json; masks only
from reviewed files <work>/<case_id>/<unit>_v2.png. Nothing in 2.5.0 is overwritten: new masks
are written as assets/<case>/<unit>_v2.png and old geometry is kept as *_v1 fields.

  python construction/release_2_6/build.py [--check-only] [--cases ID ...]
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, label

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from samtok_benchmark.io import read_jsonl, sha256_file, write_json, write_jsonl  # noqa: E402
from samtok_benchmark.v2.instruction_protocol import (  # noqa: E402
    VERSION,
    length_advice,
    mask_contract,
    render,
    validate_spec,
)
from samtok_benchmark.v2.instruction_compat import check_blind_noref  # noqa: E402
from samtok_benchmark.v2.instruction_style import STYLE_VERSION  # noqa: E402

RELEASE = "2.6.0"
BASE = REPO / "data/v2_1084"
OUT = REPO / "data/v2_2.6.0"
HERE = Path(__file__).resolve().parent
REVISIONS = HERE / "revisions"
ROOT = Path("/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2")
WORK = ROOT / "release_2_6_work"
SPEC_FIELDS = ("operation", "ref", "scope", "payload", "target_part", "remove_mode",
               "attributes", "placement", "qualifier")
PROP_ZH = {"color": "颜色", "material": "材质", "finish": "表面效果", "pattern": "图案",
           "texture": "纹理", "text": "文字"}
OPACITY_ZH = {"transparent": "透明", "translucent": "半透明", "opaque": "不透明"}
ADD_VERBS = "加上|添加|挂上|装上|放上|系上|贴上|别上|缝上|安装|放置|增加|插上|摆上|印上|戴上|套上|围上"


def needs_part_mask(spec):
    """S != T under 1.0: the 2.5.0 mask is the host, 2.0 needs the edited part/site."""
    return bool(spec["target_part"]) or spec["remove_mode"] not in ("whole",) or bool(
        spec["operation"] == "add" and spec["placement"].get("site")
    )


def blind_zh(spec, old_zh, scope_zh=""):
    """Chinese blind no-ref: keep the "what" from the reviewed translation, collapse "where"."""
    op = spec["operation"]
    r = "选中区域"
    if op == "remove":
        return {
            "whole": f"移除{r}。", "part": f"移除{r}。", "contents_only": f"移除{r}。",
            "contents": f"移除{r}及其中的物品。",
            "lowerlegs": f"移除{r}，使其成为及膝短裤。",
            "hem": f"移除{r}，使其成为及膝长度。",
        }[spec["remove_mode"]]
    text = old_zh.strip().rstrip("。")
    if op == "replace":
        m = re.search(r"替换(?:为|成)(.+)$", text)
        return f"将{r}替换为{m.group(1)}。" if m else None
    if op == "add":
        # Single-character verbs also occur inside nouns; only look after the selection phrase.
        start = text.find("选中")
        start = 0 if start < 0 else start + 2
        if scope_zh and scope_zh in text[start:]:
            start = text.index(scope_zh, start) + len(scope_zh)
        m = re.search(rf"({ADD_VERBS}|加|系|挂|装|贴|别|缝|插|摆|印|戴|套|围)(.+)$", text[start:])
        return f"给{r}{m.group(1)}{m.group(2)}。" if m else None
    attrs = spec["attributes"]
    if len(attrs) != 1:
        return None
    prop = attrs[0]["property"]
    if prop == "opacity":
        return f"将{r}变为{OPACITY_ZH[attrs[0]['value']]}。"
    m = re.search(r"(?:染成|改为|改成|变为)(.+)$", text)
    if not m:
        return None
    if prop == "tint":
        return f"将{r}染成{m.group(1)}。"
    return f"将{r}的{PROP_ZH[prop]}改为{m.group(1)}。"


def mask_geometry(mask):
    ys, xs = np.where(mask)
    dist = distance_transform_edt(np.pad(mask, 1))
    py, px = np.unravel_index(dist.argmax(), dist.shape)
    components = np.bincount(label(mask)[0].ravel())[1:]
    return {
        "box": [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)],
        "point": [int(px - 1), int(py - 1)],
        "geometry": {
            "area_fraction": round(float(mask.mean()), 6),
            "significant_components": int(sum(v >= max(16, mask.sum() * 0.005) for v in components)),
        },
    }


def load_mask(path):
    with Image.open(path) as im:
        return np.array(im.convert("L")) > 127


def spec_from(base_spec, override=None):
    spec = {k: copy.deepcopy(base_spec[k]) for k in SPEC_FIELDS}
    for k, v in (override or {}).items():
        if k not in SPEC_FIELDS:
            raise ValueError(f"unknown spec field {k}")
        spec[k] = v
    if override and spec["operation"] == "attribute":
        # 2.5.0 convention: an attribute payload is its value; never keep a stale replacement payload.
        spec["payload"] = " and ".join(a["value"] for a in spec["attributes"])
    if override and spec["operation"] != "remove":
        spec["remove_mode"] = "whole" if spec["operation"] != "remove" else spec["remove_mode"]
    spec = {"version": VERSION, **spec}
    validate_spec(spec)
    return spec


def definition_text(spec):
    return render(spec, True)


def apply_unit(case, unit, rev, problems, actions):
    uid = unit["id"]
    action = (rev or {}).get("action", "keep")
    if action == "drop":
        actions.append({"case": case["id"], "unit": uid, "action": "drop", "reason": rev.get("reason", "")})
        return None
    new = copy.deepcopy(unit)
    base_spec = unit["instruction_spec"]
    spec = spec_from(base_spec, rev.get("spec") if action == "revise" else None)
    target = new["target"]
    for key in ("ref_zh", "scope_zh", "physical_parent_zh", "parent_instance_id", "category",
                "source_category"):
        if action == "revise" and key in rev:
            target[key] = rev[key]
    target["ref"], target["scope"] = spec["ref"], spec["scope"]
    if action == "revise" and "interaction" in rev:
        new["interaction"] = rev["interaction"]

    # Mask: protocol-2.0 part masks and reviewed retargets come from the work directory.
    v2 = WORK / case["id"] / f"{uid}_v2.png"
    use_v2 = v2.exists()
    if needs_part_mask(spec) and not use_v2 and not (rev or {}).get("mask_exemption"):
        problems.append(f"{case['id']}:{uid} needs a reviewed part/site mask (protocol 2.0 S=T)")
    if (rev or {}).get("mask") == "v1" and use_v2:
        problems.append(f"{case['id']}:{uid} revision says mask v1 but a v2 mask exists")
    if use_v2:
        rel = f"assets/{case['id']}/{uid}_v2.png"
        mask = load_mask(v2)
        if not mask.any():
            problems.append(f"{case['id']}:{uid} empty v2 mask")
            return new
        target.update(mask_v1=target["mask"], mask_sha256_v1=target["mask_sha256"],
                      box_v1=target["box"], point_v1=target["point"], geometry_v1=target["geometry"])
        target["mask"] = rel
        target["_v2_source"] = str(v2)
        target.update(mask_geometry(mask))
        recipe = WORK / case["id"] / f"{uid}_v2.json"
        target["annotation_origin"] = (
            "release 2.6.0 SAM3-assisted mask, visually reviewed; recipe "
            + (recipe.read_text().strip() if recipe.exists() else "unrecorded")
        )
        if action == "revise" and rev.get("annotation_id_v1_note"):
            target["annotation_note"] = rev["annotation_id_v1_note"]

    # Instructions: both renders come from the spec; Chinese ref from 2.5.0 or the revision.
    new["instruction_protocol_version"] = VERSION
    new["operation"] = spec["operation"]
    new["instruction_spec"] = spec
    new["mask_semantics"] = mask_contract(spec)
    new["attribute_kind"] = spec["attributes"][0]["property"] if spec["operation"] == "attribute" else None
    new["instruction_ref"] = render(spec, True)
    new["instruction_noref"] = render(spec, False)
    if action == "keep" and new["instruction_ref"] != unit["instruction_ref"]:
        problems.append(f"{case['id']}:{uid} ref changed without a revision")
    if action == "revise":
        for key in ("instruction_ref_zh",):
            if key in rev:
                new[key] = rev[key]
            elif new["instruction_ref"] != unit["instruction_ref"]:
                problems.append(f"{case['id']}:{uid} revised ref needs instruction_ref_zh")
    zh = (rev or {}).get("instruction_noref_zh") or blind_zh(spec, unit["instruction_noref_zh"], unit["target"].get("scope_zh", ""))
    if action == "revise" and "instruction_noref_zh" not in rev and new["instruction_ref"] != unit["instruction_ref"]:
        zh = blind_zh(spec, new["instruction_ref_zh"], target.get("scope_zh", ""))
    if not zh or "选中区域" not in zh or "选中的" in zh:
        problems.append(f"{case['id']}:{uid} needs a blind Chinese no-ref (got {zh!r})")
    new["instruction_noref_zh"] = zh or ""
    for p in check_blind_noref(spec, new["instruction_noref"]):
        problems.append(f"{case['id']}:{uid} blind check: {p}")
    new["instruction_length_advice"] = length_advice(new["instruction_ref"], new["instruction_noref"])

    if action == "revise":
        new["completion_requirement"] = rev.get("completion_requirement") or (
            new["instruction_ref"] + " Apply the edit only to this selected region; preserve unrelated content."
        )
        if "preserve" in rev:
            new["preserve"] = rev["preserve"]
    elif use_v2 and spec["operation"] != "add":
        # Scope descriptions must match the new edited-region mask.
        new["completion_requirement"] = unit["completion_requirement"]
    contract = new["edit_contract"]
    contract["definition"] = new["instruction_ref"]
    contract["locator_semantics"] = "addition_support" if spec["operation"] == "add" else "existing_edit_target"
    contract["source_mask_role"] = (
        "attachment site of the new item (anchor), not output difference ground truth"
        if spec["operation"] == "add"
        else "actually edited visible region, not output difference ground truth"
    )
    contract["scope_relation"] = (
        "attachment_to_selected_region" if spec["operation"] == "add" else "selected_edited_region"
    )
    new["instruction_design"] = {
        **unit.get("instruction_design", {}),
        "release": RELEASE,
        "style": STYLE_VERSION,
        "revision": action,
        "previous_instruction_ref": unit["instruction_ref"] if action == "revise" else None,
        "previous_instruction_noref": unit["instruction_noref"],
    }
    if (rev or {}).get("mask_exemption") and not use_v2:
        new["instruction_design"]["mask_exemption"] = rev["mask_exemption"]
    if action == "revise":
        new["instruction_design"].update(
            revision_reason=rev.get("reason", ""),
            findings_addressed=rev.get("findings_addressed", []),
            reviewer=rev.get("reviewer", ""),
        )
    actions.append({"case": case["id"], "unit": uid, "action": action, "mask": "v2" if use_v2 else "v1",
                    "reason": (rev or {}).get("reason", "")})
    return new


def check_case(case):
    """Release-level rules (same as samtok_benchmark.v2.dataset) on the revised case."""
    cid, units, found = case["id"], case["units"], []
    if not 2 <= len(units) <= 5:
        found.append(f"{cid}: needs 2-5 units, has {len(units)}")
    parents = [u["target"]["parent_instance_id"] for u in units]
    if len(set(parents)) != len(parents):
        found.append(f"{cid}: units must have distinct physical parents")
    forms = {("ref" if u["interaction"]["has_ref"] else "noref") + "+" + u["interaction"]["locator"] for u in units}
    if len(forms) < 2:
        found.append(f"{cid}: needs at least two interaction forms")
    masks = []
    for u in units:
        i = u["interaction"]
        if not i["has_ref"] and i["locator"] == "none":
            found.append(f"{cid}:{u['id']} no-ref unit requires a locator")
        t = u["target"]
        m = load_mask(t.get("_v2_source") or ROOT / t["mask"])
        px, py = t["point"]
        x1, y1, x2, y2 = t["box"]
        ys, xs = np.where(m)
        if not m[py, px] or not (x1 <= xs.min() and xs.max() < x2 and y1 <= ys.min() and ys.max() < y2):
            found.append(f"{cid}:{u['id']} box/point inconsistent with mask")
        for uid, prev in masks:
            if (m & prev).sum() / min(m.sum(), prev.sum()) > 0.04:
                found.append(f"{cid}: {uid} and {u['id']} masks overlap > 4%")
        masks.append((u["id"], m))
    return found


def build(case_filter=None, check_only=False):
    base = read_jsonl(BASE / "cases.jsonl")
    revisions = {}
    for path in sorted(REVISIONS.glob("*.json")):
        rec = json.loads(path.read_text())
        if rec["case_id"] != path.stem:
            raise ValueError(f"{path} names another case")
        revisions[rec["case_id"]] = rec
    if set(revisions) - {c["id"] for c in base}:
        raise ValueError("revisions for unknown cases")
    problems, actions, out = [], [], []
    for case in base:
        if case_filter and case["id"] not in case_filter:
            continue
        rev = revisions.get(case["id"], {})
        if rev.get("action") == "drop_case":
            actions.append({"case": case["id"], "action": "drop_case", "reason": rev.get("reason", "")})
            continue
        unit_revs = {u["id"]: u for u in rev.get("units", [])}
        if set(unit_revs) - {u["id"] for u in case["units"]}:
            problems.append(f"{case['id']}: revision names unknown units")
        new_case = copy.deepcopy(case)
        new_case["units"] = [
            u for u in (apply_unit(case, unit, unit_revs.get(unit["id"]), problems, actions)
                        for unit in case["units"]) if u is not None
        ]
        if rev:
            new_case["revision_2_6"] = {k: rev[k] for k in ("reviewer", "notes", "reviewed_views") if k in rev}
        if "difficulty" in rev:
            new_case["difficulty"] = rev["difficulty"]
        problems.extend(check_case(new_case))
        out.append(new_case)
    if problems:
        return {"status": "problems", "problems": problems, "actions": actions}
    if check_only:
        return {"status": "ok_check_only", "cases": len(out), "actions": actions}

    OUT.mkdir(parents=True, exist_ok=True)
    for case in out:
        for unit in case["units"]:
            src = unit["target"].pop("_v2_source", None)
            if src:
                dest = ROOT / unit["target"]["mask"]
                if dest.exists() and sha256_file(dest) != sha256_file(Path(src)):
                    raise ValueError(f"refusing to overwrite a different existing {dest}")
                if not dest.exists():
                    shutil.copyfile(src, dest)
                unit["target"]["mask_sha256"] = sha256_file(dest)
    write_jsonl(OUT / "cases.jsonl", out)
    inventory, seen = [], set()
    for case in out:
        paths = [case["source"]["image"], case["review"]["card"]] + [u["target"]["mask"] for u in case["units"]]
        for rel in paths:
            if rel not in seen:
                seen.add(rel)
                p = ROOT / rel
                inventory.append({"path": rel, "sha256": sha256_file(p), "bytes": p.stat().st_size})
    write_jsonl(OUT / "asset_manifest.jsonl", inventory)
    write_jsonl(OUT / "revisions_applied.jsonl", actions)
    units = [u for c in out for u in c["units"]]
    interaction = Counter(
        ("ref" if u["interaction"]["has_ref"] else "noref") + "+" + u["interaction"]["locator"] for u in units
    )
    areas = sorted(u["target"]["geometry"]["area_fraction"] for u in units)
    write_json(OUT / "statistics.json", {
        "release_version": RELEASE,
        "cases": len(out),
        "units": len(units),
        "manifest_sha256": sha256_file(OUT / "cases.jsonl"),
        "unit_operations": dict(Counter(u["operation"] for u in units)),
        "case_unit_counts": dict(sorted(Counter(len(c["units"]) for c in out).items())),
        "unit_interactions": dict(interaction),
        "cases_containing_operation": dict(Counter(op for c in out for op in {u["operation"] for u in c["units"]})),
        "area_fraction": {"median": areas[len(areas) // 2], "min": areas[0], "max": areas[-1],
                          "below_1pct": sum(a < 0.01 for a in areas)},
        "multiple_components": sum(u["target"]["geometry"]["significant_components"] > 1 for u in units),
        "masks_v2": sum("mask_v1" in u["target"] for u in units),
        "revision_actions": dict(Counter(a["action"] for a in actions)),
        "noref_words_max": max(len(u["instruction_noref"].split()) for u in units),
    })
    issues = [
        {"case_id": c["id"], "unit_id": u["id"], "severity": "mask_semantics",
         "problem": "protocol 2.0 part/site mask could not be segmented; 2.5.0 host mask kept",
         "reason": u["instruction_design"].get("mask_exemption", "")}
        for c in out for u in c["units"] if u["instruction_design"].get("mask_exemption")
    ]
    write_json(OUT / "known_issues.json", {
        "release_version": RELEASE,
        "status": "open" if issues else "none_recorded",
        "issues": issues,
        "resolved_from_2_5_0": ["v2-sa_9357354 (U1/U2 person-clothing level) via revision record"]
        if (REVISIONS / "v2-sa_9357354.json").exists() else [],
        "independent_human_verified": False,
    })
    base_release = json.loads((BASE / "release.json").read_text())
    write_json(OUT / "release.json", {
        **{k: base_release[k] for k in ("schema_version", "dataset_root", "storage_root")},
        "release_version": RELEASE,
        "name": f"SAMTok Benchmark v2 — SA-1B {len(out)}",
        "status": "protocol_2_0_blind_noref_and_audit_repairs_pending_independent_review",
        "base_release": base_release["release_version"],
        "base_manifest_sha256": base_release["manifest_sha256"],
        "cases": len(out),
        "units": len(units),
        "instruction_protocol_version": VERSION,
        "mask_semantics_version": "2.0",
        "instruction_style_version": STYLE_VERSION,
        "manifest": "cases.jsonl",
        "manifest_sha256": sha256_file(OUT / "cases.jsonl"),
        "comparability": "No-ref units use blind 'the selected region' sentences and edited-region masks; "
        "results from <=2.5.0 are not comparable on no-ref units.",
        "revisions": "construction/release_2_6/revisions/ (applied list: revisions_applied.jsonl)",
        "known_issue_units": len(issues),
        "known_issues": "known_issues.json",
        "independent_human_verified": False,
        "semantic_signoff": False,
    })
    return {"status": "built", "cases": len(out), "units": sum(len(c["units"]) for c in out),
            "actions": Counter(a["action"] for a in actions)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--check-only", action="store_true")
    p.add_argument("--cases", nargs="*")
    a = p.parse_args()
    result = build(set(a.cases) if a.cases else None, a.check_only)
    if result["status"] == "problems":
        print("\n".join(result["problems"][:200]))
        print(json.dumps({"problems": len(result["problems"])}))
        raise SystemExit(1)
    print(json.dumps({k: v for k, v in result.items() if k != "actions"}, default=dict, ensure_ascii=False))


if __name__ == "__main__":
    main()
