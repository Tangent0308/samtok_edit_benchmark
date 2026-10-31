"""Frozen whole-release contracts, distinct from the unchanged dev20 authorization."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from samtok_benchmark.io import digest, read_jsonl, sha256_file
from samtok_benchmark.paths import repository_root
from . import MANIFEST_SHA256
from .fairness_dev_plan import MODELS, SETTINGS, check_hash, read, verify_task, verify_cache

SCHEMA = "ifbench-full-release-four-node-v1"
NODES = 4
SOURCES = 1084
UNITS = 3872
SHARD_SEED = 20261031


def assign_nodes(cases, nodes=NODES):
    """Balance immutable source groups by K and count; no output/score input."""
    capacity = (len(cases) + nodes - 1) // nodes
    assigned = [[] for _ in range(nodes)]
    loads = [0] * nodes
    for case in sorted(cases, key=lambda c: (-len(c["units"]), digest([SHARD_SEED, c["id"]]))):
        node = min(
            (n for n in range(nodes) if len(assigned[n]) < capacity),
            key=lambda n: (loads[n], len(assigned[n]), n),
        )
        assigned[node].append(case["id"])
        loads[node] += len(case["units"])
    return {str(n): sorted(ids) for n, ids in enumerate(assigned)}


def owner_map(plan):
    result = {}
    if set(plan["node_assignments"]) != {str(n) for n in range(NODES)}:
        raise ValueError("Exactly four node IDs, 0 through 3, are required")
    for node, ids in plan["node_assignments"].items():
        for cid in ids:
            if cid in result:
                raise ValueError(f"Duplicate source ownership: {cid}")
            result[cid] = int(node)
    if set(result) != set(plan["case_ids"]):
        raise ValueError("Source ownership has gaps or unregistered cases")
    return result


def node_tasks(plan, node):
    if type(node) is not int or not 0 <= node < NODES:
        raise ValueError("Node must be 0, 1, 2 or 3")
    ids = set(plan["node_assignments"][str(node)])
    return [t for t in plan["tasks"] if t["case_id"] in ids]


def load_plan(path, *, helper_root=None):
    path = Path(path)
    plan = read(path)
    if plan.get("schema") != SCHEMA or plan.get("digest") != digest(
        {k: v for k, v in plan.items() if k != "digest"}
    ):
        raise ValueError("Invalid whole-release plan or digest")
    if (
        plan.get("model_order") != MODELS
        or plan.get("settings") != SETTINGS
        or plan.get("seed") != 42
    ):
        raise ValueError("Changed approved models, settings or seed")
    if (
        not plan.get("freeze_authorized")
        or not plan.get("full_release_authorized")
        or plan.get("quality_search") is not False
        or plan.get("report_scope") != "all-1084"
    ):
        raise ValueError("Whole-release authorization/scope missing")
    check_hash(plan["authorization_path"], plan["authorization_sha256"])
    auth = read(plan["authorization_path"])
    if (
        auth.get("schema") != SCHEMA
        or not auth.get("full_release_and_judge_authorized")
        or auth.get("one_sample_per_request") is not True
        or auth.get("nodes") != NODES
        or auth.get("quality_search") is not False
        or auth.get("seed") != 42
    ):
        raise ValueError("Authorization does not cover this fixed four-node run")
    check_hash(plan["configuration_reference"], plan["configuration_reference_sha256"])
    reference = read(plan["configuration_reference"])
    if (
        plan["model_specifications"] != reference["model_specifications"]
        or plan["judge_config"] != reference["judge_config"]
    ):
        raise ValueError("Native model/Judge configuration differs from approved dev reference")
    if plan["case_manifest_sha256"] != MANIFEST_SHA256:
        raise ValueError("Full evaluation requires the unchanged audited release")
    check_hash(plan["case_manifest"], MANIFEST_SHA256)
    cases = read_jsonl(plan["case_manifest"])
    if len(cases) != SOURCES or sum(len(c["units"]) for c in cases) != UNITS:
        raise ValueError("Release must contain exactly 1084 sources and 3872 units")
    if [c["id"] for c in cases] != plan["case_ids"]:
        raise ValueError("Full result must cover every manifest source in manifest order")
    if len({c["source"]["sha256"] for c in cases}) != len(cases):
        raise ValueError("Duplicate source SHA would invalidate source ownership")
    for stem, path_key in [
        ("assignments", "assignments_path"),
        ("historical_exposure", "historical_exposure"),
        ("text_preflight", "text_preflight_path"),
        ("renderer", "renderer_path"),
    ]:
        check_hash(plan[path_key], plan[stem + "_sha256"])
    owners = owner_map(plan)
    if plan["node_assignments"] != assign_nodes(cases):
        raise ValueError("Frozen source assignment changed")
    expected = {(m, s, c) for m in MODELS for s in SETTINGS for c in plan["case_ids"]}
    actual = [(t["model"], t["setting"], t["case_id"]) for t in plan["tasks"]]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Incomplete or duplicated full model x setting x source coverage")
    if len({t["key"] for t in plan["tasks"]}) != len(actual):
        raise ValueError("Duplicate task keys")
    for t in plan["tasks"]:
        if (
            t["node"] != owners[t["case_id"]]
            or t["key"] != f"{t['model']}/{t['setting']}/{t['case_id']}"
        ):
            raise ValueError("Task source ownership/key differs from frozen assignment")
        output = (
            Path(plan["results_root"])
            / "runs"
            / t["model"]
            / "outputs"
            / t["setting"]
            / t["case_id"]
        )
        planner = (
            Path(plan["results_root"])
            / "runs"
            / t["model"]
            / "planners"
            / t["setting"]
            / t["case_id"]
        )
        if (
            t["output_dir"] != str(output)
            or t["result_path"] != str(output / "result.json")
            or t["planner_dir"] != str(planner)
        ):
            raise ValueError("Task result paths must be unique in the registered formal run")
    source_root = Path(helper_root) if helper_root is not None else repository_root()
    for filename, expected_sha in plan["helper_sha256"].items():
        if Path(filename).is_absolute() or ".." in Path(filename).parts:
            raise ValueError("Unsafe source file in plan")
        check_hash(source_root / filename, expected_sha)
    return plan


def summary(plan):
    return {
        "schema": SCHEMA,
        "sources": len(plan["case_ids"]),
        "tasks": len(plan["tasks"]),
        "nodes": {
            str(n): {
                "sources": len(plan["node_assignments"][str(n)]),
                "tasks": len(node_tasks(plan, n)),
            }
            for n in range(NODES)
        },
        "cache_tasks": dict(Counter(t["model"] for t in plan["tasks"] if "edit" in t["cache"])),
        "manifest_sha256": plan["case_manifest_sha256"],
        "plan_digest": plan["digest"],
    }


__all__ = ["load_plan", "verify_task", "verify_cache", "sha256_file", "node_tasks", "summary"]
