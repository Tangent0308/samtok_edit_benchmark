"""Public-only generation inputs and separate scoring annotations, including recurrent input bindings."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import hashlib

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from samtok_benchmark.io import digest, sha256_file
from samtok_benchmark.ifbench.canvas import make_source
from .data import immutable, read, load_turns, write_bytes
from . import REVISION, TRACKS, NUM_SESSIONS, NUM_TURNS

MASK_POLICY = "RGBA alpha < 128; binary 255=editable; nearest-neighbor canvas mapping"
SOURCE_POLICY = "Public square source to fixed 1024x1024 RGB by LANCZOS; IF-Bench 1MP canvas; restore to 1024x1024, without GT or alpha compositing"
PUBLIC_KEYS = {
    "schema",
    "case_id",
    "session_id",
    "turn",
    "track",
    "source",
    "instruction",
    "mask",
    "annotation",
    "input_digest",
}
FONT_SHA256 = "abdc775b21b1bc470d50c97e790d276f2054b7504e56e5bd3e64f48d68582322"
FONT_PATH = Path(
    "/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/magicbrush_20261105/assets/DejaVuSans.ttf"
)


def annotation_font(size):
    # Recurrent requests are rendered on new nodes. Bind font bytes, not a container's font version.
    for path in [FONT_PATH, Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]:
        if path.exists():
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() == FONT_SHA256:
                return ImageFont.truetype(BytesIO(raw), size)
    raise ValueError("The frozen annotation font is unavailable or changed")


def asset(path):
    with Image.open(path) as im:
        size = list(im.size)
    return {"path": str(Path(path).resolve()), "sha256": sha256_file(path), "size": size}


def save_image(image, path):
    data = BytesIO()
    image.save(data, format="PNG")
    write_bytes(path, data.getvalue())
    return asset(path)


def binary_mask(path):
    with Image.open(path) as im:
        if im.mode not in {"RGBA", "LA", "P"}:
            raise ValueError(f"Mask lacks the documented transparency channel: {path}")
        mask = np.asarray(im.convert("RGBA").getchannel("A")) < 128
    if not mask.any():
        raise ValueError(f"Empty transparent edit region: {path}")
    return Image.fromarray(mask.astype(np.uint8) * 255)


def render_mask(source, mask, destination):
    """Single-U adaptation of the IF-Bench contour renderer; no GT-derived placement."""
    im = Image.open(source).convert("RGB")
    m = Image.open(mask).convert("L")
    w, h = im.size
    line = max(1, round(min(w, h) * 0.004))
    eroded = ImageOps.expand(m, border=line, fill=0).filter(ImageFilter.MinFilter(2 * line + 1))
    edge = ImageChops.subtract(m, eroded.crop((line, line, w + line, h + line)))
    im.paste((255, 0, 0), mask=edge)
    y, x = np.nonzero(np.asarray(m))
    anchor = (int(x[0]), int(y[0]))
    font = annotation_font(max(12, round(min(w, h) * 0.02)))
    d = ImageDraw.Draw(im)
    bounds = d.textbbox((0, 0), "U1", font=font)
    tw, th = bounds[2] - bounds[0] + 2 * line, bounds[3] - bounds[1] + 2 * line
    left, top = (
        min(w - tw, max(0, anchor[0] + 2 * line)),
        min(h - th, max(0, anchor[1] - th - 2 * line)),
    )
    d.line((anchor, (left, top + th)), fill=(255, 0, 0), width=max(1, line // 2))
    d.rectangle(
        (left, top, left + tw - 1, top + th - 1),
        fill="white",
        outline="red",
        width=max(1, line // 2),
    )
    d.text((left + line - bounds[0], top + line - bounds[1]), "U1", font=font, fill="red")
    return save_image(im, destination)


def make_public(row, canonical_source, track, directory, canonical_mask=None):
    """row must contain only public instruction/identity fields, never target or captions."""
    if set(row) != {"case_id", "session_id", "turn", "instruction"}:
        raise ValueError("Private annotation passed to public constructor")
    directory = Path(directory)
    source, geometry = make_source(canonical_source, directory)
    public = {
        "schema": "magicbrush.public.v1",
        **row,
        "track": track,
        "source": source,
        "mask": None,
        "annotation": None,
    }
    if track == "mask-provided":
        if (
            canonical_mask is None
            or sha256_file(canonical_mask["path"]) != canonical_mask["sha256"]
        ):
            raise ValueError("Missing/changed public mask")
        with Image.open(canonical_mask["path"]) as im:
            if list(im.size) != geometry["source_size"]:
                raise ValueError("Mask dimensions differ from current source")
            content = im.convert("L").resize(
                tuple(geometry["content_size"]), Image.Resampling.NEAREST
            )
        mask = Image.new("L", tuple(geometry["canvas_size"]), 0)
        mask.paste(content, tuple(geometry["offset_xy"]))
        public["mask"] = save_image(mask, directory / "mask.png")
        public["annotation"] = render_mask(
            source["path"], public["mask"]["path"], directory / "annotation.png"
        )
    elif track != "mask-free" or canonical_mask is not None:
        raise ValueError("Mask-free constructor must not receive any mask")
    public["input_digest"] = digest(public)
    verify_public(public)
    immutable(directory / "public.json", public)
    return {
        "public": str((directory / "public.json").resolve()),
        "public_sha256": sha256_file(directory / "public.json"),
        "geometry": geometry,
    }


def verify_public(public, assets=True):
    if set(public) != PUBLIC_KEYS or public["schema"] != "magicbrush.public.v1":
        raise ValueError("Unknown or private public fields")
    if public["input_digest"] != digest({k: v for k, v in public.items() if k != "input_digest"}):
        raise ValueError("Public digest mismatch")
    if (
        public["track"] not in TRACKS
        or not isinstance(public["instruction"], str)
        or not public["instruction"].strip()
    ):
        raise ValueError("Invalid public track/instruction")
    if (public["mask"] is None) != (public["track"] == "mask-free"):
        raise ValueError("Wrong mask information for track")
    if (public["annotation"] is None) != (public["mask"] is None):
        raise ValueError("Missing/extra mask annotation")
    if assets:
        for k in ("source", "mask", "annotation"):
            a = public[k]
            if a is not None and (set(a) != {"path", "sha256", "size"} or asset(a["path"]) != a):
                raise ValueError(f"Public asset changed: {k}")
        if public["mask"]:
            with Image.open(public["mask"]["path"]) as im:
                a = np.asarray(im)
                if (
                    list(im.size) != public["source"]["size"]
                    or not np.isin(a, [0, 255]).all()
                    or not a.any()
                ):
                    raise ValueError("Invalid public binary mask")


def prepare(dataset, output):
    """Separate private GT/captions from all independent-turn public requests and recurrence specifications."""
    output = Path(output).resolve()
    rows = load_turns(dataset, assets=True)
    cases = []
    for r in rows:
        public_row = {k: r[k] for k in ("case_id", "session_id", "turn", "instruction")}
        # Most initial sources are 500px but later rounds are 1024px. A public, fixed 1024px grid
        # prevents first-turn restoration from unnecessarily downsampling every recurrent output to 500px.
        # The constant and this operation never depend on a target, caption or mask.
        with Image.open(r["source"]["path"]) as original:
            normalized = original.convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS)
        source = save_image(normalized, output / "public_sources" / (r["case_id"] + ".png"))
        mask = save_image(
            binary_mask(r["mask"]["path"]), output / "public_masks" / (r["case_id"] + ".png")
        )
        for track in TRACKS:
            item = make_public(
                public_row,
                source,
                track,
                output / "public" / track / r["case_id"],
                mask if track == "mask-provided" else None,
            )
            cases.append(
                {
                    **public_row,
                    "track": track,
                    "canonical_mask": mask if track == "mask-provided" else None,
                    **item,
                }
            )
    immutable(output / "private/evaluation.json", rows)
    index = {
        "schema": "magicbrush.bundle.v1",
        "dataset_revision": REVISION,
        "source_sha256": sha256_file(Path(dataset) / "SOURCE.json"),
        "extract_sha256": sha256_file(Path(dataset) / "extracted/EXTRACT.json"),
        "evaluation_sha256": sha256_file(output / "private/evaluation.json"),
        "mask_policy": MASK_POLICY,
        "source_policy": SOURCE_POLICY,
        "cases": cases,
        "sessions": sorted({r["session_id"] for r in rows}, key=int),
    }
    index["digest"] = digest(index)
    immutable(output / "index.json", index)
    return {
        "sessions": len(index["sessions"]),
        "turns": len(rows),
        "public_requests": len(cases),
        "digest": index["digest"],
    }


def load_bundle(path):
    index = read(Path(path) / "index.json")
    if index["schema"] != "magicbrush.bundle.v1" or index["dataset_revision"] != REVISION:
        raise ValueError("Unexpected bundle")
    if len(index["sessions"]) != NUM_SESSIONS or len(index["cases"]) != NUM_TURNS * len(TRACKS):
        raise ValueError("Incomplete test bundle")
    if digest({k: v for k, v in index.items() if k != "digest"}) != index["digest"]:
        raise ValueError("Bundle identity changed")
    return index


def requests(index, sessions, smoke=False):
    selected = [c for c in index["cases"] if c["session_id"] in sessions]
    out = []
    for c in selected:
        keep_independent = c["turn"] == 1 and (
            (c["session_id"] == sessions[0] and c["track"] == "mask-free")
            or (
                len(sessions) > 1
                and c["session_id"] == sessions[1]
                and c["track"] == "mask-provided"
            )
        )
        if not smoke or keep_independent:
            out.append(
                {**c, "mode": "independent", "key": f"{c['track']}/independent/{c['case_id']}"}
            )
        if c["turn"] > 1 and (
            not smoke
            or (c["session_id"] == sessions[0] and c["track"] == "mask-free" and c["turn"] == 2)
        ):
            previous_mode = "independent" if c["turn"] == 2 else "iterative"
            out.append(
                {
                    **c,
                    "mode": "iterative",
                    "key": f"{c['track']}/iterative/{c['case_id']}",
                    "previous_key": f"{c['track']}/{previous_mode}/{c['session_id']}-{c['turn'] - 1}",
                }
            )
    return sorted(
        out,
        key=lambda c: (
            0 if c["mode"] == "independent" else c["turn"],
            c["track"],
            int(c["session_id"]),
            c["turn"],
        ),
    )


def smoke_sessions(index):
    lengths = {
        sid: max(c["turn"] for c in index["cases"] if c["session_id"] == sid)
        for sid in index["sessions"]
    }
    eligible = [sid for sid, k in lengths.items() if k >= 2]

    def key(sid):
        return hashlib.sha256(("magicbrush-smoke-42:" + sid).encode()).hexdigest()

    first = min(eligible, key=key)
    second = min([sid for sid in index["sessions"] if sid != first], key=key)
    return [first, second]
