"""Historical candidate difficulty heuristic used to prioritize v1 source review.

Scores rank review work, not baseline failure probabilities or admission labels.
Final v1 membership is frozen in data/v1; provenance and visual decisions are
required in addition to this heuristic. Optional dependency: opencv-python.
"""

import math
import re
import cv2
import numpy as np

source_prior = {
    "PACO-LVIS": 1.0,
    "ADE20K-Part": 1.0,
    "SA-V": 0.95,
    "MOSEv2": 0.95,
    "BURST": 0.8,
    "MeViS-valid_u": 0.65,
}
cue_weights = [
    (r"same.?class|same.?instance|instance.?selection|实例|同款|同类|multiple|nearby", 4),
    (r"occlu|overlap|遮挡|交叠|cross|fragment|分段|断开|visible.?片", 4),
    (r"thin|细|杆|腿|支架|线|窄|wire|boundary|边界|轮廓", 3),
    (r"part|部件|局部|structure|结构|relation|关系|保护|preserv", 3),
    (r"hole|perforat|孔|洞|clutter|杂乱|complex|复杂", 2),
]


def load_mask(path):
    a = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if a is None:
        return None
    return (a > 0).astype(np.uint8)


def geom(path):
    a = load_mask(path)
    if a is None or not a.any():
        raise ValueError(f"empty or unreadable mask: {path}")
    h, w = a.shape
    area = int(a.sum())
    ratio = area / (h * w)
    n, lab, stats, cents = cv2.connectedComponentsWithStats(a, 8)
    comps = sorted(stats[1:, cv2.CC_STAT_AREA].tolist(), reverse=True)
    cnts, hier = cv2.findContours(a, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    per = sum(cv2.arcLength(c, True) for c in cnts if cv2.contourArea(c) > 0)
    # bbox of all foreground
    ys, xs = np.where(a)
    x0, x1 = xs.min(), xs.max()
    y0, y1 = ys.min(), ys.max()
    bw = x1 - x0 + 1
    bh = y1 - y0 + 1
    edge = int(x0 == 0 or y0 == 0 or x1 == w - 1 or y1 == h - 1)
    holes = 0 if hier is None else sum(1 for i, c in enumerate(cnts) if hier[0][i][3] >= 0)
    thin = per / (math.sqrt(area) + 1e-6)
    frag = sum(1 for x in comps if x >= max(8, area * 0.005))
    return {
        "height": h,
        "width": w,
        "area_px": area,
        "area_ratio": ratio,
        "components": n - 1,
        "major_components": frag,
        "holes": holes,
        "perimeter": per,
        "boundary_complexity": thin,
        "bbox_fill": area / (bw * bh),
        "bbox_ratio": min(bw, bh) / max(bw, bh),
        "edge_touch": edge,
    }


def score(r, g):
    axes = (
        " ".join(map(str, r.get("mechanism_evidence") or []))
        + " "
        + str(r.get("review_reason") or "")
    )
    cue = 0
    cue_hits = []
    for pat, w in cue_weights:
        if re.search(pat, axes, re.I):
            cue += w
            cue_hits.append(pat)
    cue = min(20, cue)
    # geometry: use monotone bonuses, designed to prioritize visible masks that are small/thin/fragmented/holed.
    gr = 0
    gh = []
    ar = g.get("area_ratio", 1)
    comp = g.get("major_components", 1)
    holes = g.get("holes", 0)
    bc = g.get("boundary_complexity", 0)
    bf = g.get("bbox_fill", 1)
    if ar < 0.02:
        gr += 8
        gh.append("very_small")
    elif ar < 0.05:
        gr += 6
        gh.append("small")
    elif ar < 0.12:
        gr += 4
        gh.append("moderate_small")
    elif ar < 0.25:
        gr += 2
    if comp >= 4:
        gr += 7
        gh.append("fragmented4+")
    elif comp == 3:
        gr += 5
        gh.append("fragmented3")
    elif comp == 2:
        gr += 3
        gh.append("fragmented2")
    if holes >= 2:
        gr += 4
        gh.append("holes2+")
    elif holes == 1:
        gr += 2
        gh.append("hole")
    if bc > 18:
        gr += 5
        gh.append("complex_boundary")
    elif bc > 12:
        gr += 3
        gh.append("boundary")
    if bf < 0.35:
        gr += 3
        gh.append("sparse_bbox")
    elif bf < 0.55:
        gr += 1
    if g.get("edge_touch"):
        gr += 1
        gh.append("edge_touch")
    gr = min(28, gr)
    evidence = min(
        15,
        len(cue_hits) * 2
        + (3 if r.get("review_reason") else 0)
        + (2 if r.get("mechanism_evidence") else 0),
    )
    provenance = str(r.get("provenance_status", ""))
    prov = 0
    if "origin_heldout_id_verified" in provenance:
        prov = 8
    elif (
        "official" in provenance or "disjoint" in provenance or "known_dataset_split" in provenance
    ):
        prov = 6
    elif "valid_video_id_disjoint" in provenance:
        prov = 6
    elif "pending" in provenance:
        prov = 2
    indep = 4 if r.get("independent_visual_review") else 0
    prior = round(5 * source_prior.get(r["source_dataset"], 0.5))
    generic_penalty = 5 if not r.get("mechanism_evidence") and not r.get("review_reason") else 0
    total = cue + gr + evidence + prov + indep + prior - generic_penalty
    return total, {
        "cue": cue,
        "geometry": gr,
        "evidence": evidence,
        "provenance": prov,
        "independent": indep,
        "source_prior": prior,
        "generic_penalty": generic_penalty,
        "cue_hits": cue_hits,
        "geometry_hits": gh,
    }
