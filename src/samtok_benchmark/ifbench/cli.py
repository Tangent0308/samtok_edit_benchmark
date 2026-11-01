"""IF-Bench's checkout-oriented data and immutable dev/full-release bundle entry point."""

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
    config = sub.add_parser("show-config", help="Print the current 1MP evaluation configuration")
    config.add_argument(
        "--config", type=Path, default=root / "configs/evaluation/fairness_v2_2_1mp.json"
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
    full = sub.add_parser(
        "run-full", help="Run one source-owned node of a published full-release bundle"
    )
    full.add_argument("--bundle", type=Path, required=True)
    full.add_argument("--node", type=int, choices=range(4), required=True)
    full.add_argument("--validate-only", action="store_true")
    full_status = sub.add_parser("inspect-full", help="Read the four-node full-release progress")
    full_status.add_argument("--bundle", type=Path, required=True)
    prepare = sub.add_parser("prepare-1mp", help="Prepare fixed 1MP inputs and native requests (CPU only)")
    prepare.add_argument("--bundle", type=Path, required=True)
    prepare.add_argument("--scope", choices=["probe", "full"], default="probe")
    prepare.add_argument("--results", type=Path)
    probe = sub.add_parser("probe-1mp", help="Run the bounded 42-request native engineering probe")
    probe.add_argument("--bundle", type=Path, required=True)
    report = sub.add_parser("report-1mp", help="Render current real probe inputs and outputs")
    report.add_argument("--bundle", type=Path, required=True)
    return command


def inspect_run(bundle):
    from .live_state import read_live

    bundle = bundle.resolve()
    result = {"bundle": str(bundle)}
    for name in ("READY.json", "results/progress.json", "results/COMPLETED.json"):
        path = bundle / name
        if name == "READY.json":
            result[name] = json.loads(path.read_text()) if path.is_file() else None
        else:
            result[name] = read_live(path)
    if result["READY.json"] is None:
        raise FileNotFoundError(f"Not a published run: {bundle / 'READY.json'}")
    return result


def inspect_full(bundle):
    from .live_state import read_live

    bundle = bundle.resolve()
    ready = json.loads((bundle / "READY.json").read_text())
    if ready.get("schema") != "ifbench-full-release-four-node-v1":
        raise ValueError("Not a full-release four-node bundle")
    root = Path(ready["results_root"])
    result = {"bundle": str(bundle), "results_root": str(root), "nodes": {}}
    for node in range(4):
        directory = root / "nodes" / f"node-{node}"
        result["nodes"][str(node)] = {
            name: read_live(directory / name)
            for name in ("progress.json", "COMPLETED.json", "ERROR.json")
        }
    final = root / "report/COMPLETED.json"
    result["aggregate"] = read_live(final)
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
    elif args.command == "inspect-full":
        result = inspect_full(args.bundle)
    elif args.command == "prepare-1mp":
        from .prepare_one_mp import prepare

        plan = prepare(args.bundle, scope=args.scope, results=args.results)
        result = {"bundle": str(args.bundle), "plan_digest": plan["digest"]}
    elif args.command == "probe-1mp":
        from .one_mp_probe import execute

        result = execute(args.bundle / "plan.json")
    elif args.command == "report-1mp":
        from .one_mp_report import render

        render(args.bundle)
        result = {"report": str(repository_root() / "docs/RESULTS.md")}
    else:
        bundle = args.bundle.resolve()
        inspect_run(bundle)  # Publication must exist; the frozen bootstrap verifies every hash.
        start = bundle / "start.sh"
        if not start.is_file():
            raise FileNotFoundError(start)
        command = ["bash", str(start)]
        if args.command == "run-full":
            inspect_full(bundle)
            command += ["--node", str(args.node)]
        if args.validate_only:
            command.append("--validate-only")
        # Preserve the bundle's code identity and foreground lifetime. No shell interpolation.
        return subprocess.call(command, cwd=bundle)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
