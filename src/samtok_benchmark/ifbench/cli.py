"""IF-Bench's checkout-oriented data and immutable dev-bundle entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from samtok_benchmark.paths import repository_root


def parser():
    root = repository_root()
    command = argparse.ArgumentParser(description=__doc__)
    sub = command.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-data", help="Validate an existing release and its assets")
    validate.add_argument("--manifest", type=Path, default=root / "data/v2_2.6.0/cases.jsonl")
    validate.add_argument("--dataset-root", type=Path, required=True)
    validate.add_argument("--output", type=Path, required=True)
    validate.add_argument("--minimum-cases", type=int, default=0)
    inputs = sub.add_parser(
        "prepare-inputs", help="Build the shared inputs for the original dev pool"
    )
    inputs.add_argument("--manifest", type=Path, default=root / "data/v2_2.6.0/cases.jsonl")
    inputs.add_argument("--dataset-root", type=Path, required=True)
    inputs.add_argument("--output", type=Path, required=True)
    inputs.add_argument("--workers", type=int, default=4)
    config = sub.add_parser("show-config", help="Print the current dev configuration reference")
    config.add_argument(
        "--config", type=Path, default=root / "configs/evaluation/fairness_v2_1.json"
    )
    inspect = sub.add_parser(
        "inspect-run", help="Read published run metadata without launching workers"
    )
    inspect.add_argument("--bundle", type=Path, required=True)
    run = sub.add_parser(
        "run-dev", help="Run a published bundle using its own frozen foreground entry"
    )
    run.add_argument("--bundle", type=Path, required=True)
    run.add_argument("--validate-only", action="store_true")
    return command


def inspect_run(bundle):
    bundle = bundle.resolve()
    result = {"bundle": str(bundle)}
    for name in ("READY.json", "results/progress.json", "results/COMPLETED.json"):
        path = bundle / name
        result[name] = json.loads(path.read_text()) if path.is_file() else None
    if result["READY.json"] is None:
        raise FileNotFoundError(f"Not a published run: {bundle / 'READY.json'}")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == "validate-data":
        from samtok_benchmark.v2.dataset import validate

        result = validate(args.manifest, args.dataset_root, args.minimum_cases, args.output)
    elif args.command == "prepare-inputs":
        from .__main__ import main as prepare

        return prepare(
            [
                "--manifest",
                str(args.manifest),
                "--dataset-root",
                str(args.dataset_root),
                "--output",
                str(args.output),
                "--workers",
                str(args.workers),
            ]
        )
    elif args.command == "show-config":
        result = json.loads(args.config.read_text())
    elif args.command == "inspect-run":
        result = inspect_run(args.bundle)
    else:
        bundle = args.bundle.resolve()
        inspect_run(bundle)  # Publication must exist; the frozen bootstrap verifies every hash.
        start = bundle / "start.sh"
        if not start.is_file():
            raise FileNotFoundError(start)
        command = ["bash", str(start)]
        if args.validate_only:
            command.append("--validate-only")
        # Preserve the bundle's code identity and foreground lifetime. No shell interpolation.
        return subprocess.call(command, cwd=bundle)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
