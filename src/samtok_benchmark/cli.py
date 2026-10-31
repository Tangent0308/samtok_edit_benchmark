"""Public CLI. Paths to images/checkpoints are supplied by the caller."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from samtok_benchmark.inputs import PROTOCOLS, SETTINGS

DEFAULT_MANIFEST = Path("data/v1/cases.jsonl")


def _data_args(parser):
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dataset-root", type=Path, required=True)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SAMTok Edit Benchmark v1 (450 cases)")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("validate", help="validate schema, geometry, images and release hashes")
    _data_args(a)
    a.add_argument("--asset-manifest", type=Path, default=Path("data/v1/asset_manifest.jsonl"))
    a.add_argument("--expected-cases", type=int, default=450)
    a.add_argument("--output", type=Path)
    a = sub.add_parser("build", help="materialize the frozen v1 selection in a new directory")
    a.add_argument("--release", type=Path, default=Path("data/v1"))
    a.add_argument("--assets-root", type=Path)
    a.add_argument("--source-map", action="append", default=[])
    a.add_argument("--output", type=Path, required=True)
    a = sub.add_parser("prepare", help="freeze inputs for selected modalities")
    _data_args(a)
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--settings", nargs="+", choices=SETTINGS, default=SETTINGS)
    a.add_argument("--protocol", choices=PROTOCOLS, default="visual_locator_v1")
    a = sub.add_parser("run-editor", help="run an importable editor callback on frozen inputs")
    a.add_argument("--inputs", type=Path, required=True)
    a.add_argument("--adapter", required=True, help="module:function returning an RGB PIL image")
    a.add_argument("--method", required=True)
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--seed", type=int, default=0)
    a.add_argument("--settings", nargs="+", choices=SETTINGS, default=SETTINGS)
    a.add_argument("--adapter-config", type=Path)
    a = sub.add_parser("review", help="build a standalone dataset pass/discard review tool")
    _data_args(a)
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--revisions", type=Path, default=Path("data/v1/instruction_revisions.jsonl"))
    a = sub.add_parser("export-reviewed", help="export an approved-only, traceable derivative")
    a.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    a.add_argument("--results", type=Path, required=True)
    a.add_argument("--reviewer", required=True)
    a.add_argument("--output", type=Path, required=True)
    a = sub.add_parser("prepare-judge", help="freeze source/output/mask inputs for the judge")
    _data_args(a)
    a.add_argument("--inputs", type=Path, required=True)
    a.add_argument("--outputs", type=Path, required=True)
    a.add_argument("--method", required=True)
    a.add_argument("--output", type=Path, required=True)
    a = sub.add_parser("judge", help="two-image, three-axis VLM judge; --dry-run uses no GPU/model")
    a.add_argument("--manifest", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--model", type=Path)
    a.add_argument("--variants", nargs="+", choices=("pair_v3", "pair_v3_r1"), default=["pair_v3"])
    a.add_argument("--rank", type=int, default=0)
    a.add_argument("--world-size", type=int, default=1)
    a.add_argument("--batch-size", type=int, default=2)
    a.add_argument("--max-pixels", type=int, default=1024 * 1024)
    a.add_argument("--max-tokens", type=int, default=4096)
    a.add_argument("--max-model-len", type=int, default=16384)
    a.add_argument("--gpu-memory-utilization", type=float, default=0.85)
    a.add_argument("--thinking", action="store_true")
    a.add_argument("--reasoning-effort", choices=["low", "medium", "xhigh"], default="low")
    a.add_argument("--limit", type=int)
    a.add_argument("--dry-run", action="store_true")
    a = sub.add_parser("report", help="coverage-aware VLM tables and optional human agreement")
    a.add_argument("--manifest", type=Path, required=True)
    a.add_argument("--run", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--human-scores", type=Path)
    a = sub.add_parser("human-review", help="package blind, native-resolution output assessment")
    a.add_argument("--manifest", type=Path, required=True)
    a.add_argument("--reviewer", required=True)
    a.add_argument("--output", type=Path, required=True)
    return p


def main(argv=None) -> None:
    a = parser().parse_args(argv)
    if a.command == "validate":
        from samtok_benchmark.dataset import validate

        result = validate(a.manifest, a.dataset_root, a.asset_manifest, a.expected_cases, a.output)
    elif a.command == "build":
        from samtok_benchmark.build import materialize

        result = materialize(a.release, a.output, a.assets_root, a.source_map)
    elif a.command == "prepare":
        from samtok_benchmark.inputs import prepare

        rows = prepare(a.manifest, a.dataset_root, a.output, a.settings, a.protocol)
        result = {"jobs": len(rows), "inputs": str(a.output / "inputs.jsonl")}
    elif a.command == "run-editor":
        from samtok_benchmark.editor import run_editor

        config = json.loads(a.adapter_config.read_text()) if a.adapter_config else {}
        result = {
            "registered_outputs": len(
                run_editor(a.inputs, a.output, a.adapter, a.method, a.seed, a.settings, config)
            )
        }
    elif a.command == "review":
        from samtok_benchmark.review.package import package_review

        result = package_review(a.manifest, a.dataset_root, a.output, a.revisions)
    elif a.command == "export-reviewed":
        from samtok_benchmark.review.package import export_reviewed

        result = export_reviewed(a.manifest, a.results, a.output, a.reviewer)
    elif a.command == "prepare-judge":
        from samtok_benchmark.judge.prepare import prepare_judge

        result = {
            "jobs": len(
                prepare_judge(a.manifest, a.dataset_root, a.inputs, a.outputs, a.method, a.output)
            )
        }
    elif a.command == "judge":
        from samtok_benchmark.judge.runner import run

        code = run(a)
        if code:
            raise SystemExit(code)
        return
    elif a.command == "report":
        from samtok_benchmark.judge.report import report

        result = report(a.manifest, a.run, a.output, a.human_scores)
    elif a.command == "human-review":
        from samtok_benchmark.judge.human import package_human_review

        result = package_human_review(a.manifest, a.output, a.reviewer)
    else:
        raise AssertionError(a.command)
    print(json.dumps(result, ensure_ascii=False, indent=2))
