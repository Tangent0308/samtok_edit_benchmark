"""Build a self-contained data-review tool from the current v1 manifest."""

from __future__ import annotations

import shutil
from importlib.resources import files
from pathlib import Path

from PIL import Image

from samtok_benchmark.dataset import instruction_operation_types, load_cases
from samtok_benchmark.inputs import annotate
from samtok_benchmark.io import asset_path, sha256_file, write_json


def package_review(manifest: Path, root: Path, output: Path, revisions: Path | None = None) -> dict:
    cases = load_cases(manifest)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(
            "choose a new output directory; existing human decisions are never overwritten"
        )
    output.mkdir(parents=True, exist_ok=True)
    static = files("samtok_benchmark.review").joinpath("static")
    for name in ("run_review.py", "index.html", "app.js", "style.css"):
        (output / name).write_bytes(static.joinpath(name).read_bytes())
    ui_cases = []
    for i, case in enumerate(cases):
        c = {**case, "index": i, "mask_overlay": f"mask_overlays/{i:04d}.jpg"}
        refs = [case["source_image"], case["evaluation_mask"]] + [
            r["mask"] for r in case["regions"]
        ]
        for ref in refs:
            dest = asset_path(output, ref)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset_path(root, ref), dest)
        with Image.open(asset_path(root, case["source_image"])) as im:
            overlay = annotate(im, case["regions"], root, "mask_annotation")
            overlay.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            dest = output / c["mask_overlay"]
            dest.parent.mkdir(exist_ok=True)
            overlay.save(dest, quality=90)
        ui_cases.append(c)
    write_json(output / "cases.json", ui_cases)
    write_json(
        output / "package_metadata.json",
        {"manifest_sha256": sha256_file(manifest), "cases": len(cases)},
    )
    if revisions:
        dest = output / "benchmark/instruction_revision_audit.jsonl"
        dest.parent.mkdir(exist_ok=True)
        shutil.copy2(revisions, dest)
    (output / "README.md").write_text(
        "# v1 data review\n\nRun `python run_review.py`, then open "
        "http://127.0.0.1:8765/index.html. Python 3 only; no third-party dependency.\n\n"
        "Select a case to load its images. P = pass, D = discard, U = clear. "
        "Instructions and notes are editable. Decisions persist in `review_results.json`; "
        "export a copy with the button. The original manifest is unchanged.\n\n"
        "`reviewed_cases.json` is a review-state copy, not the frozen release. "
        "Use the repository's `export-reviewed` command to create a passed-only manifest "
        "with traceable overrides. Copy existing `review_results.json` before starting "
        "this package if you want to retain prior decisions.\n",
        encoding="utf-8",
    )
    return {"cases": len(cases), "output": str(output.resolve())}


def export_reviewed(manifest: Path, results: Path, output: Path, reviewer: str) -> dict:
    import json
    from samtok_benchmark.io import digest, write_jsonl

    if not reviewer.strip():
        raise ValueError("reviewer identity is required")
    cases = load_cases(manifest)
    review = json.loads(results.read_text(encoding="utf-8"))
    decisions = review["cases"]
    if set(decisions) - {c["id"] for c in cases}:
        raise ValueError("review results contain unknown case IDs")
    kept, audit = [], []
    for case in cases:
        record = decisions.get(case["id"], {})
        if record.get("status") not in {None, "unreviewed", "pass", "discard"}:
            raise ValueError("invalid review decision")
        if record.get("status") != "pass":
            continue
        if record.get("instruction_revision") != case["instruction_revision"]:
            raise ValueError(f"instruction changed since review; recheck {case['id']}")
        new = dict(case)
        override = record.get("instruction_override", "").strip()
        if override and override != case["instruction"]:
            new.update(
                instruction=override,
                region_instruction=override,
                instruction_source=f"human_review:{reviewer}",
                instruction_revision="human_" + digest([reviewer, override])[:16],
            )
        kept.append(new)
        audit.append(
            {
                "id": case["id"],
                "reviewer": reviewer,
                "record": record,
                "original_instruction": case["instruction"],
                "final_instruction": new["instruction"],
            }
        )
    if not kept:
        raise ValueError("no approved cases")
    # Human overrides must meet the same instruction requirements as releases.
    for case in kept:
        if not "A" <= case["instruction"][0] <= "Z":
            raise ValueError(f"instruction must start with a capital letter: {case['id']}")
        if len(instruction_operation_types(case["instruction"])) > 1:
            raise ValueError(f"mixed operation clauses are not allowed: {case['id']}")
    write_jsonl(output, kept)
    write_jsonl(output.with_suffix(".review_audit.jsonl"), audit)
    return {"passed": len(kept), "remaining": len(cases) - len(kept), "output": str(output)}
