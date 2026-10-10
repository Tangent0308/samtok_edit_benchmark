"""Entrypoint for the current SA-1B v2 release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from samtok_benchmark.v2 import PROTOCOLS
from samtok_benchmark.v2.dataset import validate
from samtok_benchmark.v2.editor import run_editor
from samtok_benchmark.v2.evaluation import prepare_judge, report
from samtok_benchmark.v2.gallery import build
from samtok_benchmark.v2.inputs import prepare, VARIANTS
from samtok_benchmark.v2.review import package_review


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="SAMTok v2: independent objects, mixed per-unit interactions"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "prepare", "gallery", "review", "prepare-judge", "report"):
        p = sub.add_parser(command)
        p.add_argument("--manifest", type=Path, required=True)
        if command != "report":
            p.add_argument("--dataset-root", type=Path, required=True)
        p.add_argument("--output", type=Path, required=True)
        if command in {"gallery", "prepare-judge", "report"}:
            p.add_argument("--inputs", type=Path, required=True)
        if command in {"prepare-judge", "report"}:
            p.add_argument("--outputs", type=Path, required=True)
        if command == "validate":
            p.add_argument("--minimum-cases", type=int, default=200)
        if command == "prepare":
            p.add_argument("--protocol", choices=PROTOCOLS, default=PROTOCOLS[0])
            p.add_argument("--variants", nargs="+", choices=VARIANTS, default=["mixed"])
        if command == "report":
            p.add_argument("--scores", type=Path, required=True)
            p.add_argument("--allow-incomplete", action="store_true")
    p = sub.add_parser("run-editor")
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--adapter", required=True)
    p.add_argument("--method", required=True)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--config", type=Path, help="JSON adapter configuration")
    a = parser.parse_args(argv)
    if a.command == "validate":
        result = validate(a.manifest, a.dataset_root, a.minimum_cases, a.output)
    elif a.command == "prepare":
        jobs = prepare(a.manifest, a.dataset_root, a.output, a.protocol, a.variants)
        result = {"jobs": len(jobs), "path": str(a.output / "jobs.jsonl")}
    elif a.command == "gallery":
        if a.output.resolve() != (a.dataset_root / "index.html").resolve():
            parser.error(
                "gallery --output must be DATASET_ROOT/index.html so relative assets remain portable"
            )
        result = {"gallery": str(build(a.manifest, a.dataset_root, a.inputs))}
    elif a.command == "review":
        result = package_review(a.manifest, a.dataset_root, a.output)
    elif a.command == "run-editor":
        rows = run_editor(
            a.inputs,
            a.output,
            a.adapter,
            a.method,
            a.seed,
            json.loads(a.config.read_text()) if a.config else {},
        )
        result = {"outputs": len(rows)}
    elif a.command == "prepare-judge":
        rows = prepare_judge(a.manifest, a.dataset_root, a.inputs, a.outputs, a.output)
        result = {"judge_jobs": len(rows)}
    else:
        result = report(a.manifest, a.inputs, a.outputs, a.scores, a.output, a.allow_incomplete)
        result = {k: v for k, v in result.items() if k != "case_results"}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
