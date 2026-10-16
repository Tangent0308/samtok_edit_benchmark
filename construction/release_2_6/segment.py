"""SAM3-assisted source masks for release 2.6.0 (protocol 2.0: mask = actually edited region).

Every mask produced here is a proposal until a reviewer has looked at its sheet; `commit`
only copies the reviewed final mask into the work directory that the release builder reads.

  segment.py text    --case C --unit U --text "white emblem" [--within host|none] [--box x1 y1 x2 y2]
  segment.py prompt  --case C --unit U [--box x1 y1 x2 y2] [--pos x,y ...] [--neg x,y ...]
  segment.py compose --case C --unit U --expr "t1_2|t1_3" [--and-host] [--and-box x1 y1 x2 y2]
                     [--minus-box x1 y1 x2 y2] [--minus-unit U2 ...] [--minus-expr "..."]
  segment.py commit  --case C --unit U        # copies the last compose result to <unit>_v2.png
  segment.py show    --case C [--unit U]      # case sheet: all current/v2 unit masks

Candidates are saved as <work>/<case>/<unit>/<tag>_<k>.png (full source size, 0/255) and a
numbered review sheet <tag>.jpg. Use one GPU via CUDA_VISIBLE_DEVICES.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(
    os.environ.get(
        "SAMTOK_BENCHMARK_ROOT",
        "/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2",
    )
)
WORK = Path(os.environ.get("SAMTOK_R26_WORK", ROOT / "release_2_6_work"))
MODEL = Path(
    os.environ.get(
        "SAMTOK_SAM3", "/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/sam3"
    )
)
MANIFEST = Path(__file__).resolve().parents[2] / "data/v2_1084/cases.jsonl"
COLORS = [(235, 40, 75), (0, 150, 240), (220, 165, 0), (145, 75, 210), (0, 175, 120),
          (255, 120, 0), (0, 200, 200), (200, 0, 200), (120, 200, 0), (90, 90, 255)]


def case_record(case_id):
    with MANIFEST.open() as f:
        for line in f:
            c = json.loads(line)
            if c["id"] == case_id:
                return c
    raise SystemExit(f"unknown case {case_id}")


def load_mask(path):
    with Image.open(path) as m:
        return np.array(m.convert("L")) > 127


def save_mask(mask, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((mask.astype(np.uint8) * 255)).save(path)


def unit_mask(case, unit_id, prefer_v2=True):
    v2 = WORK / case["id"] / f"{unit_id}_v2.png"
    if prefer_v2 and v2.exists():
        return load_mask(v2)
    unit = next(u for u in case["units"] if u["id"] == unit_id)
    return load_mask(ROOT / unit["target"]["mask"])


def bbox(mask):
    ys, xs = np.where(mask)
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1] if len(xs) else None


def outline(mask, width):
    m = Image.fromarray(mask.astype(np.uint8) * 255)
    return (np.array(m.filter(ImageFilter.MaxFilter(2 * width + 1))) > 0) & ~mask


def sheet(image, masks, labels, path, focus=None, host=None, max_side=1400):
    """Full view plus zoom on `focus` box; host shown as a thin gray outline."""
    w, h = image.size
    font = ImageFont.load_default(size=max(14, round(min(w, h) / 45)))

    def render(img, region):
        img = img.copy()
        arr = np.array(img)
        width = max(2, round(max(img.size) / 300))
        if host is not None:
            hm = host[region[1]:region[3], region[0]:region[2]]
            arr[outline(hm, width) & ~hm] = (160, 160, 160)
        for i, m in enumerate(masks):
            mm = m[region[1]:region[3], region[0]:region[2]]
            color = np.array(COLORS[i % len(COLORS)])
            arr[mm] = (arr[mm] * 0.55 + color * 0.45).astype(np.uint8)
            arr[outline(mm, width) & ~mm] = color
        out = Image.fromarray(arr)
        d = ImageDraw.Draw(out)
        for i, (m, label) in enumerate(zip(masks, labels)):
            b = bbox(m[region[1]:region[3], region[0]:region[2]])
            if b:
                d.text((b[0], max(0, b[1] - font.size - 2)), label, fill=COLORS[i % len(COLORS)],
                       font=font, stroke_width=2, stroke_fill="black")
        return out

    full = render(image, (0, 0, w, h))
    full.thumbnail((max_side, max_side))
    panels = [full]
    if focus:
        x1, y1, x2, y2 = focus
        pad = max(24, round(max(x2 - x1, y2 - y1) * 0.35))
        region = (max(0, x1 - pad), max(0, y1 - pad), min(w, x2 + pad), min(h, y2 + pad))
        zoom = render(image.crop(region), region)
        scale = min(3.0, 900 / max(zoom.size))
        zoom = zoom.resize((round(zoom.width * scale), round(zoom.height * scale)))
        # Grid in ORIGINAL source pixels so reviewers can read boxes/points directly.
        d = ImageDraw.Draw(zoom)
        span = max(region[2] - region[0], region[3] - region[1])
        step = next(s for s in (10, 20, 25, 50, 100, 200, 250, 500) if span / s <= 12)
        gfont = ImageFont.load_default(size=13)
        for gx in range((region[0] // step + 1) * step, region[2], step):
            x = (gx - region[0]) * scale
            d.line([(x, 0), (x, zoom.height)], fill=(255, 255, 255), width=1)
            d.text((x + 2, 2), str(gx), fill=(255, 255, 0), font=gfont, stroke_width=2, stroke_fill="black")
        for gy in range((region[1] // step + 1) * step, region[3], step):
            y = (gy - region[1]) * scale
            d.line([(0, y), (zoom.width, y)], fill=(255, 255, 255), width=1)
            d.text((2, y + 2), str(gy), fill=(255, 255, 0), font=gfont, stroke_width=2, stroke_fill="black")
        panels.append(zoom)
    total_w = sum(p.width for p in panels) + 10 * (len(panels) - 1)
    canvas = Image.new("RGB", (total_w, max(p.height for p in panels)), "white")
    x = 0
    for p in panels:
        canvas.paste(p, (x, 0))
        x += p.width + 10
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, quality=90)


def parse_points(values):
    return [[int(v) for v in re.split(r"[,\s]+", p.strip())] for p in values or []]


def cmd_text(a, case, image, host, out):
    import torch
    from transformers import Sam3Model, Sam3Processor

    region = a.box or (bbox(host) if a.within == "host" else [0, 0, image.width, image.height])
    pad = a.pad
    x1, y1 = max(0, region[0] - pad), max(0, region[1] - pad)
    x2, y2 = min(image.width, region[2] + pad), min(image.height, region[3] + pad)
    model = Sam3Model.from_pretrained(MODEL).cuda().eval()
    proc = Sam3Processor.from_pretrained(MODEL)
    inputs = proc(images=image.crop((x1, y1, x2, y2)), text=a.text, return_tensors="pt").to("cuda")
    with torch.no_grad():
        result = model(**inputs)
    res = proc.post_process_instance_segmentation(
        result, threshold=a.threshold, mask_threshold=0.5,
        target_sizes=inputs.get("original_sizes").tolist(),
    )[0]
    candidates = []
    for m, score in zip(res["masks"], res["scores"]):
        full = np.zeros((image.height, image.width), bool)
        full[y1:y2, x1:x2] = m.cpu().numpy().astype(bool)
        if a.within == "host":
            full &= host
        if full.sum() >= 16:
            candidates.append((float(score), full))
    candidates.sort(key=lambda c: -c[0])
    return candidates


def cmd_prompt(a, case, image, host, out):
    import torch
    from transformers import Sam3TrackerModel, Sam3TrackerProcessor

    model = Sam3TrackerModel.from_pretrained(MODEL).cuda().eval()
    proc = Sam3TrackerProcessor.from_pretrained(MODEL)
    kwargs = {}
    pos, neg = parse_points(a.pos), parse_points(a.neg)
    if pos or neg:
        kwargs["input_points"] = [[pos + neg]]
        kwargs["input_labels"] = [[[1] * len(pos) + [0] * len(neg)]]
    if a.box:
        kwargs["input_boxes"] = [[a.box]]
    inputs = proc(images=image, return_tensors="pt", **kwargs).to("cuda")
    with torch.no_grad():
        result = model(**inputs, multimask_output=True)
    masks = proc.post_process_masks(result.pred_masks.cpu(), inputs["original_sizes"])[0][0]
    scores = result.iou_scores.cpu().numpy().reshape(-1)
    return sorted(((float(s), m.numpy().astype(bool)) for s, m in zip(scores, masks)), key=lambda c: -c[0])


def evaluate(expr, unit_dir, host=None):
    """Expression over saved candidates (and `host`): | union, & intersection, - difference."""
    tokens = re.findall(r"[A-Za-z0-9_]+|[|&\-()]", expr)
    pos = 0

    def atom():
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            value = union()
            pos += 1
            return value
        if tok == "host":
            return host.copy()
        return load_mask(unit_dir / f"{tok}.png")

    def union():
        nonlocal pos
        value = atom()
        while pos < len(tokens) and tokens[pos] in "|&-":
            op = tokens[pos]
            pos += 1
            rhs = atom()
            value = value | rhs if op == "|" else value & rhs if op == "&" else value & ~rhs
        return value

    return union()


def box_mask(shape, box):
    m = np.zeros(shape, bool)
    m[box[1]:box[3], box[0]:box[2]] = True
    return m


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("text", "prompt", "compose", "commit", "show"))
    p.add_argument("--case", required=True)
    p.add_argument("--unit")
    p.add_argument("--tag", default=None)
    p.add_argument("--text")
    p.add_argument("--within", choices=("host", "none"), default="host")
    p.add_argument("--box", type=int, nargs=4)
    p.add_argument("--pad", type=int, default=40)
    p.add_argument("--threshold", type=float, default=0.3)
    p.add_argument("--pos", nargs="*")
    p.add_argument("--neg", nargs="*")
    p.add_argument("--expr")
    p.add_argument("--and-host", action="store_true")
    p.add_argument("--and-box", type=int, nargs=4)
    p.add_argument("--minus-box", type=int, nargs=4, action="append")
    p.add_argument("--minus-unit", nargs="*")
    a = p.parse_args()

    case = case_record(a.case)
    with Image.open(ROOT / case["source"]["image"]) as im:
        image = im.convert("RGB")
    case_dir = WORK / case["id"]
    if a.command == "show":
        units = [u["id"] for u in case["units"] if not a.unit or u["id"] == a.unit]
        masks = [unit_mask(case, uid) for uid in units]
        labels = [uid + (" v2" if (case_dir / f"{uid}_v2.png").exists() else "") for uid in units]
        path = case_dir / "case_sheet.jpg"
        focus = bbox(masks[0]) if a.unit else None
        sheet(image, masks, labels, path, focus=focus)
        print(json.dumps({"sheet": str(path), "units": labels}))
        return
    if not a.unit:
        raise SystemExit("--unit is required")
    unit_dir = case_dir / a.unit
    host = unit_mask(case, a.unit, prefer_v2=False)

    if a.command in ("text", "prompt"):
        tag = a.tag or ("t" if a.command == "text" else "p") + str(len(list(unit_dir.glob("*.jpg"))) + 1)
        found = (cmd_text if a.command == "text" else cmd_prompt)(a, case, image, host, unit_dir)
        rows, masks, labels = [], [], []
        for k, (score, m) in enumerate(found[:10], 1):
            name = f"{tag}_{k}"
            save_mask(m, unit_dir / f"{name}.png")
            masks.append(m)
            labels.append(name)
            rows.append({"name": name, "score": round(score, 3), "area_px": int(m.sum()),
                         "box": bbox(m), "frac_in_host": round(float((m & host).sum() / max(1, m.sum())), 3)})
        focus = a.box or bbox(host)
        sheet(image, masks, labels, unit_dir / f"{tag}.jpg", focus=focus, host=host)
        print(json.dumps({"sheet": str(unit_dir / f"{tag}.jpg"), "candidates": rows}, ensure_ascii=False))
    elif a.command == "compose":
        m = evaluate(a.expr, unit_dir, host) if a.expr else host.copy()
        if a.and_host:
            m &= host
        if a.and_box:
            m &= box_mask(m.shape, a.and_box)
        for b in a.minus_box or []:
            m &= ~box_mask(m.shape, b)
        for uid in a.minus_unit or []:
            m &= ~unit_mask(case, uid)
        save_mask(m, unit_dir / "final.png")
        recipe = {"expr": a.expr or "host", "and_host": a.and_host, "and_box": a.and_box,
                  "minus_box": a.minus_box, "minus_unit": a.minus_unit}
        (unit_dir / "final.json").write_text(json.dumps(recipe))
        hb, mb = bbox(host), bbox(m) or bbox(host)
        focus = [min(hb[0], mb[0]), min(hb[1], mb[1]), max(hb[2], mb[2]), max(hb[3], mb[3])]
        sheet(image, [m], [a.unit + " final"], unit_dir / "final.jpg", focus=focus, host=host)
        print(json.dumps({"sheet": str(unit_dir / "final.jpg"), "area_px": int(m.sum()),
                          "box": bbox(m), "frac_of_host": round(float((m & host).sum() / max(1, host.sum())), 3)}))
    else:
        final = unit_dir / "final.png"
        if not final.exists():
            raise SystemExit("run compose first and review final.jpg")
        target = case_dir / f"{a.unit}_v2.png"
        m = load_mask(final)
        if not m.any():
            raise SystemExit("empty mask")
        save_mask(m, target)
        recipe = json.loads((unit_dir / "final.json").read_text())
        (case_dir / f"{a.unit}_v2.json").write_text(json.dumps(recipe))
        print(json.dumps({"committed": str(target), "box": bbox(m), "area_px": int(m.sum())}))


if __name__ == "__main__":
    main()
