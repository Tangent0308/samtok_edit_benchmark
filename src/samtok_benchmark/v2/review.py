"""Build the standalone, lazy-loading v2 annotation review application."""

from __future__ import annotations

import shutil
from importlib.resources import files
from pathlib import Path

from samtok_benchmark.io import asset_path, sha256_file, write_json, write_jsonl
from samtok_benchmark.v2.dataset import load_cases, validate
from samtok_benchmark.v2.inputs import render_locators


def package_review(manifest: Path, root: Path, output: Path):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Use an empty review directory; existing reviews are preserved")
    summary = validate(manifest, root, minimum_cases=0)
    cases = load_cases(manifest)
    output.mkdir(parents=True, exist_ok=True)
    static = files("samtok_benchmark.v2").joinpath("review_static")
    for name in ("run_review.py", "index.html", "app.js", "style.css"):
        (output / name).write_bytes(static.joinpath(name).read_bytes())
    benchmark = output / "benchmark"
    benchmark.mkdir()
    for name in (
        "cases.jsonl",
        "asset_manifest.jsonl",
        "provenance.jsonl",
        "statistics.json",
        "release.json",
        "instruction_revision.json",
        "instruction_reviews.jsonl",
        "instruction_design.jsonl",
        "storage.json",
    ):
        source = manifest.parent / name
        if source.exists():
            shutil.copyfile(source, benchmark / name)
    write_json(benchmark / "validation.json", summary)
    if (manifest.parent / "selection").exists():
        shutil.copytree(manifest.parent / "selection", benchmark / "selection", dirs_exist_ok=True)
    inventory, index = [], []
    for n, case in enumerate(cases):
        refs = {case["source"]["image"], case["review"]["card"]}
        refs |= {u["target"]["mask"] for u in case["units"]}
        for ref in sorted(refs):
            source, dest = asset_path(root, ref), asset_path(output, ref)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            inventory.append(
                {"path": ref, "sha256": sha256_file(dest), "bytes": dest.stat().st_size}
            )
        formal = Path("formal_inputs") / f"{case['id']}.jpg"
        render_locators(case, case["units"], output, output / formal)
        public = [
            {
                "id": u["id"],
                **u["interaction"],
                "operation": u["operation"],
                "instruction_zh": u.get(
                    "instruction_ref_zh" if u["interaction"]["has_ref"] else "instruction_noref_zh",
                    "",
                ),
                "instruction": u[
                    "instruction_ref" if u["interaction"]["has_ref"] else "instruction_noref"
                ],
            }
            for u in case["units"]
        ]
        view = {**case, "index": n, "formal_input_image": str(formal), "public_units": public}
        write_json(output / "cases" / f"{case['id']}.json", view)
        index.append(
            {
                "id": case["id"],
                "index": n,
                "dataset": case["source"]["dataset"],
                "objects": len(case["units"]),
                "operations": sorted({u["operation"] for u in case["units"]}),
                "evidence": case["difficulty"]["evidence_zh"],
                "mechanisms": case["difficulty"]["mechanisms"],
            }
        )
    write_json(output / "cases.json", index)
    metadata = {
        "schema_version": "2.0",
        "instruction_version": cases[0].get("instruction_review", {}).get("version", "2.0.0"),
        "unit_operations": summary["unit_operations"],
        "cases": len(cases),
        "units": summary["units"],
        "manifest_sha256": sha256_file(manifest),
        "lazy_case_assets": True,
        "default_overlays": "none",
        "independent_human_verified": False,
    }
    write_json(output / "package_metadata.json", metadata)
    write_jsonl(output / "copied_assets.jsonl", inventory)
    documentation = root / "BENCHMARK_V2_ZH.md"
    if documentation.exists():
        shutil.copyfile(documentation, output / "BENCHMARK_V2_ZH.md")
        figures = root / "docs/assets"
        if figures.exists():
            shutil.copytree(figures, output / "docs/assets", dirs_exist_ok=True)
    return metadata
