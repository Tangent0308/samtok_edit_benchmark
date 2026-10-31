"""Audit a completed dev input package, including view/prompt and split bindings."""

from __future__ import annotations

import argparse
from collections import Counter
from functools import lru_cache
import json
from pathlib import Path

from PIL import Image

from samtok_benchmark.io import digest, read_jsonl, sha256_file, write_json
from . import SETTINGS
from .inputs import global_prompt
from .public import verify


def validate_package(root):
    split = json.loads((root / "plan/splits.json").read_text())
    summary = json.loads((root / "build_summary.json").read_text())
    assignments = json.loads((root / "plan/assignments.json").read_text())
    assert not set(split["dev"]) & set(split["test"])
    assert summary["split_digest"] == split["digest"]
    assert summary["assignment_digest"] == assignments["digest"]
    assert digest({k: v for k, v in split.items() if k != "digest"}) == split["digest"]
    assert digest({k: v for k, v in assignments.items() if k != "digest"}) == assignments["digest"]
    requests = read_jsonl(root / "public_dev_requests.jsonl")
    expected = {(c, s) for c in split["dev"] for s in SETTINGS}
    assert {(r["case_id"], r["setting"]) for r in requests} == expected and len(requests) == len(
        expected
    )
    hashes = lru_cache(maxsize=None)(lambda p: sha256_file(Path(p)))
    setting_counts = Counter()
    artifacts = Counter()
    label_overlap = []
    label_out_of_bounds = []
    changed_prompt_files = []
    image_sizes = []
    for r in requests:
        verify(r)
        setting_counts[r["setting"]] += 1
        directory = root / "requests" / r["setting"] / r["case_id"]
        payload = json.loads((directory / "inputs.json").read_text())
        assert payload["public_input_digest"] == r["input_digest"]
        assert payload["digest"] == digest({k: v for k, v in payload.items() if k != "digest"})
        assert json.loads((directory / "public.json").read_text()) == r
        assert hashes(r["source"]["path"]) == r["source"]["sha256"]
        size = tuple(r["source"]["size"])
        for u in r["units"]:
            if u["locator"] == "mask":
                assert hashes(u["region"]["path"]) == u["region"]["sha256"]
        marked = any(u["locator"] != "none" for u in r["units"])
        assert bool(payload["annotation"]) == marked
        if marked:
            a = payload["annotation"]
            assert hashes(a["path"]) == a["sha256"]
            with Image.open(a["path"]) as im:
                assert im.size == size and im.mode == "RGB"
            for label in a["labels"]:
                x1, y1, x2, y2 = label["label_box_xyxy"]
                if not 0 <= x1 < x2 <= size[0] or not 0 <= y1 < y2 <= size[1]:
                    label_out_of_bounds.append([r["request_id"], label])
                if label["label_overlap_pixels"]:
                    label_overlap.append([r["request_id"], label])
            artifacts["annotations"] += 1
        for mode, form in payload["forms"].items():
            assert form["images"][0] == (
                payload["annotation"]["path"]
                if mode == "single" and marked
                else r["source"]["path"]
            )
            assert len(form["images"]) == (2 if mode == "dual" and marked else 1)
            if (directory / f"prompt.{mode}.txt").read_text() != form["prompt"] + "\n":
                changed_prompt_files.append([r["request_id"], mode])
            artifacts["prompt_files"] += 1
        if r["setting"].startswith("S2-"):
            assert payload["forms"]["discard-region"]["prompt"] == global_prompt(r)
            assert payload["forms"]["discard-region"]["images"] == [r["source"]["path"]]
            artifacts["discard_region_requests"] += 1
        else:
            assert "discard-region" not in payload["forms"]
        assert [u["unit_id"] for u in payload["native"]["units"]] == [u["id"] for u in r["units"]]
        for u, native in zip(r["units"], payload["native"]["units"], strict=True):
            assert native["instruction"] == u["instruction"]
            assert native["input_modality"] == u["locator"]
            assert (native["mask"] is None) == (u["locator"] == "none")
            if native["mask"]:
                path = native["mask"]["path"]
                assert hashes(path) == native["mask"]["sha256"]
                with Image.open(path) as im:
                    if im.size != size or im.mode != "L":
                        image_sizes.append(path)
                artifacts["native_masks"] += 1
    gallery = json.loads((root / "gallery_index.json").read_text())
    assert set(gallery) == set(SETTINGS)
    assert all(
        len(v) == 3 and all(x["case_id"] in split["dev"] for x in v) for v in gallery.values()
    )
    assert not changed_prompt_files and not label_out_of_bounds and not image_sizes
    result = {
        "status": "passed",
        "requests": len(requests),
        "per_setting": dict(setting_counts),
        "artifacts": dict(artifacts),
        "gallery_requests": sum(len(v) for v in gallery.values()),
        "gallery_unique_cases": len({r["case_id"] for v in gallery.values() for r in v}),
        "label_overlap_count": len(label_overlap),
        "label_overlaps": label_overlap,
        "label_out_of_bounds": label_out_of_bounds,
        "changed_prompt_files": changed_prompt_files,
        "geometry_errors": image_sizes,
        "split_overlap": [],
        "test_images_or_masks_in_public_inputs": 0,
        "scope": "dev inputs, artifacts and fixed plan; no model quality judgement",
    }
    write_json(root / "validation.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate_package(args.directory), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
