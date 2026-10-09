"""Read upstream annotations, exclude old sources, and build new image-level review cards.

Ranking is retrieval only. No candidate is admitted without recorded direct visual review.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shutil

import numpy as np
from PIL import Image
from pycocotools import mask as cm
from scipy import ndimage as ndi

UPSTREAM = Path("/mnt/bn/strategy-mllm-train/user/tanyue/datasets/PACO_benchmark_candidates")
COCO = Path("/mnt/bn/strategy-mllm-train/intern/common_datasets/coco/val2017")
ADE = UPSTREAM / "goal_1k/ade20k_part234/official/ADE20KPart234"
REPO = Path(__file__).resolve().parents[1]


def read_jsonl(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode(seg, h, w):
    if isinstance(seg, list):
        seg = cm.merge(cm.frPyObjects(seg, h, w))
    elif isinstance(seg.get("counts"), list):
        seg = cm.frPyObjects(seg, h, w)
    return cm.decode(seg).astype(bool)


def geometry(m):
    ys, xs = np.where(m)
    if not len(xs):
        return None
    box = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
    dist = ndi.distance_transform_edt(m)
    py, px = np.unravel_index(dist.argmax(), m.shape)
    labs, count = ndi.label(m, structure=np.ones((3, 3)))
    areas = np.bincount(labs.ravel())[1:]
    holes = ndi.binary_fill_holes(m) & ~m
    return {
        "box": box,
        "point": [int(px), int(py)],
        "area_pixels": int(m.sum()),
        "area_fraction": float(m.mean()),
        "components": int(count),
        "significant_components": int((areas >= max(12, m.sum() * 0.005)).sum()),
        "hole_pixels": int(holes.sum()),
        "box_fill": float(m.sum() / ((box[2] - box[0]) * (box[3] - box[1]))),
        "max_interior_radius": float(dist.max()),
    }


PREFERRED = {
    "handle": 14,
    "leg": 13,
    "arm": 12,
    "armrest": 12,
    "rim": 12,
    "shade": 12,
    "back": 10,
    "seat": 9,
    "seat cushion": 9,
    "drawer": 10,
    "door": 10,
    "frame": 11,
    "base": 7,
    "stem": 12,
    "lid": 11,
    "cap": 8,
    "neck": 8,
    "sleeve": 12,
    "collar": 12,
    "strap": 13,
    "wheel": 8,
    "tire": 8,
    "bumper": 11,
    "mirror": 10,
    "hood": 10,
    "spout": 13,
    "blade": 11,
    "top": 6,
    "body": 5,
    "side": 6,
    "inner_wall": 8,
    "inner_body": 5,
    "apron": 11,
    "stretcher": 13,
    "spindle": 13,
    "stile": 11,
    "rail": 12,
    "pipe": 12,
    "column": 12,
    "support": 12,
    "cord": 13,
    "wing": 12,
    "back pillow": 9,
    "headboard": 10,
    "footboard": 10,
    "seat base": 9,
}
EXCLUDE_PARTS = {
    "highlight",
    "light source",
    "opening",
    "gaze",
    "logo",
    "drawing",
    "label",
    "license plate",
    "screen",
    "monitor",
    "window",
    "headlight",
    "button panel",
    "food_cup",
    "inner_side",
    "bottom",
    "food",
    "bulb",
    "canopy",
}


def part_score(name, g):
    p = name.split(":")[-1]
    if p in EXCLUDE_PARTS:
        return -100
    value = PREFERRED.get(p, 2)
    value += min(g["significant_components"] - 1, 3) * 1.4
    value += 2 if 0.002 <= g["area_fraction"] <= 0.08 else 0
    value += 1 if 0.10 < g["box_fill"] < 0.75 else 0
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "candidates").mkdir(exist_ok=True)
    reviews = read_jsonl(REPO / "docs/results/qwen21_text_only_20261009/case_reviews.jsonl")
    excluded_paco = set()
    excluded_ade = set()
    for r in reviews:
        m = re.search(r"paco_lvis_v1_(\d+)_", r["case_id"])
        if m:
            excluded_paco.add(int(m[1]))
        m = re.search(r"adepart_(\d+)_", r["case_id"])
        if m:
            excluded_ade.add(f"ADE_val_{int(m[1]):08d}")
    for p in read_jsonl(REPO / "data/v1/provenance.jsonl"):
        match = re.search(r"ADE_val_\d+", p.get("source_image_original", ""))
        if match:
            excluded_ade.add(match[0])
    # Previously shown protocol examples also stay out of this new release.
    probe = Path("/opt/tiger/SA1B_数据分析/Benchmark_多对象交互方案/paco_probe_annotations.json")
    if probe.exists():
        excluded_paco.update(i["id"] for i in json.loads(probe.read_text())["images"])
    annotation_file = UPSTREAM / "annotations/paco_lvis_v1_test.json"
    paco = json.loads(annotation_file.read_text())
    categories = {c["id"]: c for c in paco["categories"]}
    images = {
        i["id"]: i
        for i in paco["images"]
        if i["file_name"].startswith("val2017/") and i["id"] not in excluded_paco
    }
    grouped = defaultdict(list)
    for a in paco["annotations"]:
        if a["image_id"] in images and categories[a["category_id"]]["supercategory"] == "PART":
            grouped[a["image_id"]].append(a)
    jobs = []
    for iid, aa in grouped.items():
        if len({a["obj_ann_id"] for a in aa}) >= 2:
            jobs.append(("paco", images[iid], aa))
    ade = json.loads((ADE / "ade20k_instance_val.json").read_text())
    adeimages = {i["id"]: i for i in ade["images"] if i["id"] not in excluded_ade}
    class_names = json.loads(
        (UPSTREAM / "goal_1k/ade20k_part234/part_and_object_class_names.json").read_text()
    )["CLASS_NAMES"]
    grouped_ade = defaultdict(list)
    for a in ade["annotations"]:
        if a["image_id"] in adeimages:
            grouped_ade[a["image_id"]].append(a)
    for iid, aa in grouped_ade.items():
        if len(aa) >= 2:
            jobs.append(("ade", adeimages[iid], aa))

    def process(job):
        source, imeta, aa = job
        iid = imeta["id"]
        h, w = imeta["height"], imeta["width"]
        cid = f"paco_{int(iid):012d}" if source == "paco" else f"ade_{iid}"
        p = (
            (COCO / f"{iid:012d}.jpg")
            if source == "paco"
            else ADE / "images/validation" / imeta["file_name"]
        )
        if min(w, h) < 250 or max(w, h) < 400:
            return None
        if source == "ade":
            part_path = ADE / "annotations_detectron2_part/validation" / f"{iid}.png"
            part_image = np.array(Image.open(part_path))
        choices = []
        for a in aa:
            if source == "paco":
                name = categories[a["category_id"]]["name"]
                if name.split(":")[-1] in EXCLUDE_PARTS:
                    continue
                entries = [(a["id"], name, decode(a["segmentation"], h, w), a["obj_ann_id"], None)]
            else:
                parent = decode(a["segmentation"], h, w)
                entries = []
                for partid in a["part_category_id"]:
                    name = class_names[partid]
                    obj, part = name.rsplit("'s ", 1)
                    if part in EXCLUDE_PARTS:
                        continue
                    # Official class PNG is zero-based; intersect with the object instance.
                    m = (part_image == partid) & parent
                    entries.append((f"{a['id']}_p{partid}", f"{obj}:{part}", m, a["id"], partid))
            for aid, name, m, parent, partid in entries:
                area = int(m.sum())
                if area < 220 or not 0.0008 <= area / (h * w) <= 0.20:
                    continue
                g = geometry(m)
                b = g["box"]
                if min(b[2] - b[0], b[3] - b[1]) < 8 or g["max_interior_radius"] < 1.5:
                    continue
                score = part_score(name, g)
                if score < 5:
                    continue
                choices.append(
                    (
                        score,
                        {
                            "annotation_id": aid,
                            "parent_instance_id": str(parent),
                            "category": name,
                            "part_category_id": partid,
                            "geometry": g,
                        },
                        m,
                    )
                )
        choices.sort(key=lambda t: -t[0])
        selected = []
        parents = set()
        for score, entry, m in choices:
            if entry["parent_instance_id"] in parents:
                continue
            if any((m & prev).sum() / min(m.sum(), prev.sum()) > 0.04 for _, prev in selected):
                continue
            selected.append((entry, m))
            parents.add(entry["parent_instance_id"])
            if len(selected) == 4:
                break
        if len(selected) < 2:
            return None
        # Stable spatial order is only for review. Public unit order is counterbalanced later.
        selected.sort(
            key=lambda t: (sum(t[0]["geometry"]["box"][::2]), sum(t[0]["geometry"]["box"][1::2]))
        )
        dest = out / "candidates" / cid
        dest.mkdir(exist_ok=True)
        source_dest = dest / "source.jpg"
        if not source_dest.exists():
            shutil.copyfile(p, source_dest)
        with Image.open(source_dest) as raw:
            if raw.size != (w, h):
                raise ValueError(f"source geometry mismatch {cid}")
        units = []
        for i, (entry, m) in enumerate(selected, 1):
            target = dest / f"unit_{i}.png"
            Image.fromarray(m.astype("uint8") * 255).save(target)
            entry.update(
                {
                    "candidate_unit": i,
                    "mask": str(target.relative_to(out)),
                    "mask_sha256": sha(target),
                }
            )
            units.append(entry)
        same = Counter(u["category"] for u in units)
        rank = sum(part_score(u["category"], u["geometry"]) for u in units) / len(units)
        rank += 3 * min(len(units) - 1, 2) + 2 * (max(same.values()) >= 2)
        record = {
            "candidate_id": cid,
            "source_dataset": "PACO-LVIS" if source == "paco" else "ADE20K-Part-234",
            "source_image_id": str(iid),
            "source_split": "COCO val2017" if source == "paco" else "validation",
            "source_original": str(p),
            "source_image": str(source_dest.relative_to(out)),
            "source_sha256": sha(source_dest),
            "source_size": [w, h],
            "source_annotation_file": str(
                annotation_file if source == "paco" else ADE / "ade20k_instance_val.json"
            ),
            "mask_extraction": "official segmentation decode"
            if source == "paco"
            else "official zero-based part category PNG intersected with official parent instance RLE",
            "units": units,
            "retrieval_score": round(rank, 3),
            "status": "unreviewed",
        }
        (dest / "candidate.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n"
        )
        return record

    records = []
    errors = []

    def safe(job):
        try:
            return process(job)
        except Exception as exc:
            return {"error": repr(exc), "source": job[0], "image_id": job[1]["id"]}

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for i, result in enumerate(executor.map(safe, jobs), 1):
            if result and "error" in result:
                errors.append(result)
            elif result:
                records.append(result)
            if i % 100 == 0:
                print(
                    f"processed {i}/{len(jobs)}, candidates {len(records)}, errors {len(errors)}",
                    flush=True,
                )
    # Alternate sources within ranked blocks so review does not exhaust one domain first.
    records.sort(key=lambda r: (-r["retrieval_score"], r["candidate_id"]))
    (out / "candidate_pool.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    )
    report = {
        "eligible_annotation_images_before_geometry": len(jobs),
        "candidate_images": len(records),
        "by_source": dict(Counter(r["source_dataset"] for r in records)),
        "unit_counts": dict(Counter(len(r["units"]) for r in records)),
        "excluded_paco_ids": sorted(excluded_paco),
        "excluded_ade_ids": sorted(excluded_ade),
        "paco_annotation_sha256": sha(annotation_file),
        "ade_annotation_sha256": sha(ADE / "ade20k_instance_val.json"),
        "errors": errors,
        "status": "retrieval only; all candidates require direct visual review",
    }
    (out / "candidate_pool_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ["excluded_paco_ids", "excluded_ade_ids", "errors"]
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
