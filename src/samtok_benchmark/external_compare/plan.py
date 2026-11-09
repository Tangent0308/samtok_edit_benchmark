"""Freeze model scope without resampling cases or modifying the previous experiment."""

from datetime import datetime, timezone
from pathlib import Path
import subprocess

from samtok_benchmark.external_full.data import immutable, read
from samtok_benchmark.external_full.worker import source_identity
from samtok_benchmark.io import digest, sha256_file
from . import ADDITIONAL, REUSED


def checked(path):
    value = read(path)
    if value["digest"] != digest({k: v for k, v in value.items() if k != "digest"}):
        raise ValueError(f"Frozen document changed: {path}")
    return value


def extend_selection(selection, source, output):
    bench = selection["benchmark"]
    if set(selection["models"]) != set(REUSED):
        raise ValueError("Expected the completed SITEdit/base experiment")
    result = dict(selection)
    result.pop("digest")
    result.update(
        schema="external.comparison.selection.v1",
        source_selection=str(Path(source).resolve()),
        source_selection_sha256=sha256_file(source),
        reused_results_root=selection["results_root"],
        results_root=str(Path(output).resolve()),
        generation_models=list(ADDITIONAL[bench]),
        models=list(ADDITIONAL[bench]) + list(REUSED),
        scope_note="Unchanged fixed cohort; new baselines selected after the two-model analysis",
    )
    result["digest"] = digest(result)
    return result


def verify_selection(selection):
    source = Path(selection["source_selection"])
    if sha256_file(source) != selection["source_selection_sha256"]:
        raise ValueError("Original cohort document changed")
    original = checked(source)
    expected = extend_selection(original, source, selection["results_root"])
    if selection != expected:
        raise ValueError("Comparison may only add the fixed baseline roster and output paths")
    if sha256_file(selection["configuration"]) != selection["configuration_sha256"]:
        raise ValueError("Original inference/scoring configuration changed")


def prepare(parent, control):
    parent, control = Path(parent).resolve(), Path(control).resolve()
    control.mkdir(parents=True, exist_ok=False)
    prior = checked(parent / "PLAN.json")
    read(parent / "COMPLETED.json")
    if prior["generation_source_identity"] != source_identity():
        raise ValueError("Scientific generation code differs from the completed pair")
    repo = Path(__file__).parents[3]
    commit = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    paths = [
        repo / "scripts/external_compare.py",
        repo / "src/samtok_benchmark/external_pair/runner.py",
        repo / "src/samtok_benchmark/external_pair/worker.py",
    ]
    paths += sorted(Path(__file__).parent.glob("*.py"))
    entries = []
    for entry in prior["benchmarks"]:
        source = Path(entry["selection"])
        if sha256_file(source) != entry["selection_sha256"]:
            raise ValueError("Original selected case list changed")
        original = checked(source)
        output = Path(original["results_root"]).parent / "comparison_20261109"
        selection = extend_selection(original, source, output)
        verify_selection(selection)
        output.mkdir(parents=True, exist_ok=False)
        for section in ("run", "scores"):
            (output / section).mkdir()
            for model in REUSED:
                target = Path(original["results_root"]) / section / model
                if not target.is_dir():
                    raise ValueError(f"Missing completed result directory: {target}")
                (output / section / model).symlink_to(target, target_is_directory=True)
        path = control / original["benchmark"] / "SELECTION.json"
        immutable(path, selection)
        entries.append({"selection": str(path), "selection_sha256": sha256_file(path)})
    plan = {
        "schema": "external.comparison.plan.v1",
        "source_commit": commit,
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "parent_plan": str(parent / "PLAN.json"),
        "parent_plan_sha256": sha256_file(parent / "PLAN.json"),
        "generation_source_identity": source_identity(),
        "orchestration_source": {str(p.relative_to(repo)): sha256_file(p) for p in paths},
        "benchmarks": entries,
        "authorized_local_gpus": list(range(8)),
        "paid_api_calls": 0,
        "new_generation_requests": 1520,
        "reused_generation_requests": 1280,
        "failures": "Retain all expected cases, publish coverage; no automatic retries or fabricated scores",
    }
    plan["digest"] = digest(plan)
    immutable(control / "PLAN.json", plan)
    return plan
