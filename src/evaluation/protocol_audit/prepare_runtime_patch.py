"""Publish an authorized I/O patch over the exact sampled plan; CPU only."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

from samtok_benchmark.io import sha256_file, write_json
from samtok_benchmark.paths import repository_root
from samtok_benchmark.ifbench import full_plan
from samtok_benchmark.ifbench.fairness_dev_plan import check_hash, read
from samtok_benchmark.ifbench.runtime_patch import SCHEMA, source_changes, verify_patch
from evaluation.protocol_audit.prepare_fairness_dev20_revision import snapshot_repo


def publish(bundle, parent, interruption_audit=None):
    bundle, parent = Path(bundle).resolve(), Path(parent).resolve()
    repo = repository_root()
    if bundle.exists():
        raise ValueError("Use a new bundle; never overwrite published or partial evidence")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=repo).strip():
        raise ValueError("Commit and test the source before publishing")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    old_ready = read(parent / "READY.json")
    if old_ready.get("runtime_patch_sha256"):
        raise ValueError("Only the reviewed first runtime patch may be published")
    for name, key in (
        ("plan.json", "plan_sha256"), ("code_manifest.json", "code_manifest_sha256"),
        ("aliases.json", "aliases_sha256"), ("bootstrap.json", "bootstrap_sha256"),
        ("start.sh", "entrypoint_sha256"), ("PREPARATION.json", "preparation_sha256"),
    ):
        check_hash(parent / name, old_ready[key])
    # Validate the original immutable plan against its original code snapshot.
    plan = full_plan.load_plan(parent / "plan.json", helper_root=parent / "repo")
    before = read(parent / "code_manifest.json")["files"]
    for name, expected in before.items():
        check_hash(parent / "repo" / name, expected)
    bundle.mkdir(parents=True)
    for name in ("assets", "requests", "preflight", "cache"):
        if not (parent / name).is_dir():
            raise ValueError(f"Missing immutable input tree: {name}")
        (bundle / name).symlink_to(parent / name, target_is_directory=True)
    for name in (
        "plan.json", "aliases.json", "bootstrap.json", "configuration.json", "AUTHORIZATION.json"
    ):
        shutil.copyfile(parent / name, bundle / name)
        check_hash(bundle / name, sha256_file(parent / name))
    snapshot_repo(bundle)
    shutil.copyfile(parent / "start.sh", bundle / "start.sh")
    (bundle / "start.sh").chmod(0o755)
    after = read(bundle / "code_manifest.json")["files"]
    changes = source_changes(before, after)
    patch = {
        "schema": SCHEMA, "created_at": datetime.now(timezone.utc).isoformat(),
        "authorization": "User requested incremental Judge progress, bounded parallel validation, terminal phase skipping and run004 continuation; no scientific changes or record rewrites.",
        "parent_bundle": str(parent),
        "parent_ready_sha256": sha256_file(parent / "READY.json"),
        "parent_code_manifest_sha256": old_ready["code_manifest_sha256"],
        "plan_sha256": old_ready["plan_sha256"], "plan_digest": plan["digest"],
        "results_root": plan["results_root"], "source_commit": commit,
        "code_manifest_sha256": sha256_file(bundle / "code_manifest.json"),
        "source_changes": changes,
        "changed_scientific_inputs": 0, "rewritten_records": 0, "new_inference_calls": 0,
    }
    if interruption_audit is not None:
        audit = Path(interruption_audit).resolve()
        completion = read(audit / "COMPLETED.json")
        authorization = read(audit / "AUTHORIZATION.json")
        manifest = read(audit / "RELEASE_MANIFEST.json")
        check_hash(audit / "RELEASE_MANIFEST.json", completion["manifest_sha256"])
        if (authorization["plan_sha256"] != old_ready["plan_sha256"]
                or authorization["results_root"] != plan["results_root"]
                or completion["raw_or_effective_records_modified"] != 0
                or completion["generation_records_modified"] != 0):
            raise ValueError("Interruption audit does not preserve the sampled plan/answers")
        for record in manifest["records"]:
            check_hash(record["quarantine"], record["sha256"])
        patch["interruption_recovery"] = {
            "directory": str(audit), "released_admissions": manifest["count"],
            "unknown_prior_sampling_outcomes": completion["unknown_prior_sampling_outcomes"],
            "files": {name: sha256_file(audit / name) for name in
                      ("COMPLETED.json", "AUTHORIZATION.json", "RELEASE_MANIFEST.json",
                       "USER_LIST_VERIFIED.json", "USER_ADMITTED_WITHOUT_ANSWER.json")},
            "rewritten_answers": 0,
        }
    write_json(bundle / "RUNTIME_PATCH.json", patch)
    write_json(bundle / "PREPARATION.json", {
        **full_plan.summary(plan), "new_inference_calls": 0,
        "source_preparation": str(parent / "PREPARATION.json"),
        "source_preparation_sha256": old_ready["preparation_sha256"],
        "runtime_patch_sha256": sha256_file(bundle / "RUNTIME_PATCH.json"),
        "unchanged_input_trees": {name: str((bundle / name).resolve())
                                  for name in ("assets", "requests", "preflight", "cache")},
        "input_rebuilds": 0, "plan_byte_identical": True,
    })
    ready = {
        **old_ready, "source_commit": commit,
        "code_manifest_sha256": patch["code_manifest_sha256"],
        "preparation_sha256": sha256_file(bundle / "PREPARATION.json"),
        "runtime_patch_sha256": sha256_file(bundle / "RUNTIME_PATCH.json"),
    }
    # Check candidate identity before writing the one immutable READY.
    verify_patch(bundle / "plan.json", ready=ready)
    for name, expected in after.items():
        check_hash(bundle / "repo" / name, expected)
        check_hash(repo / name, expected)
    write_json(bundle / "READY.json", ready)
    result = {
        "bundle": str(bundle), "ready_sha256": sha256_file(bundle / "READY.json"),
        "source_commit": commit, "plan_digest": plan["digest"],
        "plan_sha256": ready["plan_sha256"], "results_root": plan["results_root"],
        "public_inputs_byte_identical": True, "new_inference_calls": 0,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", required=True, type=Path)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--interruption-audit", type=Path)
    args = parser.parse_args()
    publish(args.bundle, args.parent, args.interruption_audit)
