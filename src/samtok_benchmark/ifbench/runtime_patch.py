"""Authenticate a narrow scheduling/I/O patch without changing a sampled plan."""

from pathlib import Path

from samtok_benchmark.io import sha256_file
from .fairness_dev_plan import check_hash, read

SCHEMA = "ifbench-runtime-io-patch-v1"
# The fixed allowlist excludes native inference, canonical evidence/parser,
# image transformations, prompts, parameters and statistical calculations.
REPLACEABLE = frozenset(
    "src/samtok_benchmark/ifbench/" + name + ".py"
    for name in ("fairness_dev_judge", "full_plan", "full_run", "full_report")
)
ADDITIONS = frozenset({
    "src/samtok_benchmark/ifbench/runtime_patch.py",
    "src/evaluation/protocol_audit/prepare_runtime_patch.py",
})


def source_changes(before, after):
    """Reject any unreviewed source deletion, addition or inference change."""
    changes = {}
    for name in sorted(set(before) | set(after)):
        if not name.startswith("src/") or before.get(name) == after.get(name):
            continue
        if name not in after or (name in before and name not in REPLACEABLE):
            raise ValueError(f"Runtime patch changes protected source: {name}")
        if name not in before and name not in ADDITIONS:
            raise ValueError(f"Runtime patch adds unregistered source: {name}")
        changes[name] = {"before": before.get(name), "after": after[name]}
    if not changes:
        raise ValueError("Runtime patch has no source changes")
    return changes


def verify_patch(plan_path, *, ready=None):
    """READY pins the patch, parent READY, unchanged plan and both manifests."""
    plan_path = Path(plan_path).resolve()
    bundle = plan_path.parent
    if ready is None:
        try:
            ready = read(bundle / "READY.json")
        except FileNotFoundError:
            if (bundle / "RUNTIME_PATCH.json").exists():
                raise ValueError("Unpublished runtime patch") from None
            return None
    if not ready.get("runtime_patch_sha256"):
        if (bundle / "RUNTIME_PATCH.json").exists():
            raise ValueError("Runtime patch is not pinned by READY")
        return None
    check_hash(bundle / "RUNTIME_PATCH.json", ready["runtime_patch_sha256"])
    patch = read(bundle / "RUNTIME_PATCH.json")
    if patch.get("schema") != SCHEMA:
        raise ValueError("Unrecognized runtime patch schema")
    parent = Path(patch["parent_bundle"])
    if not parent.is_absolute() or parent.resolve() == bundle:
        raise ValueError("Runtime patch needs a distinct absolute parent bundle")
    check_hash(parent / "READY.json", patch["parent_ready_sha256"])
    old_ready = read(parent / "READY.json")
    if old_ready.get("runtime_patch_sha256"):
        raise ValueError("A further patch requires an explicit reviewed ancestry update")
    for base, manifest_sha in (
        (parent, patch["parent_code_manifest_sha256"]),
        (bundle, patch["code_manifest_sha256"]),
    ):
        check_hash(base / "code_manifest.json", manifest_sha)
        check_hash(base / "plan.json", patch["plan_sha256"])
    if (
        ready["plan_sha256"] != patch["plan_sha256"]
        or old_ready["plan_sha256"] != patch["plan_sha256"]
        or ready["code_manifest_sha256"] != patch["code_manifest_sha256"]
        or old_ready["code_manifest_sha256"] != patch["parent_code_manifest_sha256"]
        or ready["source_commit"] != patch["source_commit"]
        or ready["results_root"] != old_ready["results_root"]
        or ready["results_root"] != patch["results_root"]
    ):
        raise ValueError("Runtime patch changes the plan/results or code binding")
    for filename, key in (
        ("aliases.json", "aliases_sha256"), ("bootstrap.json", "bootstrap_sha256"),
        ("start.sh", "entrypoint_sha256"),
    ):
        if ready[key] != old_ready[key]:
            raise ValueError(f"Runtime patch changes protected runtime: {filename}")
        check_hash(bundle / filename, old_ready[key])
    check_hash(bundle / "configuration.json", sha256_file(parent / "configuration.json"))
    before = read(parent / "code_manifest.json")["files"]
    after = read(bundle / "code_manifest.json")["files"]
    if source_changes(before, after) != patch["source_changes"]:
        raise ValueError("Runtime patch source changes differ from manifest")
    if before["data/v2_2.6.0/cases.jsonl"] != after["data/v2_2.6.0/cases.jsonl"]:
        raise ValueError("Runtime patch changes the canonical case manifest")
    return patch


def helper_hashes(plan_path, original, *, source_root):
    patch = verify_patch(plan_path)
    hashes = dict(original)
    if patch is None:
        return hashes
    for filename, change in patch["source_changes"].items():
        if filename in original:
            if change["before"] != original[filename]:
                raise ValueError("Runtime patch does not extend the exact original helpers")
            hashes[filename] = change["after"]
        elif change["before"] is None:
            # New infrastructure also remains hash checked on node-local staging.
            check_hash(Path(source_root) / filename, change["after"])
    return hashes


def accepted_code_manifests(plan_path):
    bundle = Path(plan_path).resolve().parent
    ready = read(bundle / "READY.json")
    check_hash(bundle / "code_manifest.json", ready["code_manifest_sha256"])
    patch = verify_patch(plan_path, ready=ready)
    accepted = {ready["code_manifest_sha256"]}
    if patch:
        accepted.add(patch["parent_code_manifest_sha256"])
    return accepted
