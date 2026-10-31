# ruff: noqa: E402
# Standalone entrypoint: configure CPU threads/import paths before dependent imports.
"""CPU-only analysis of immutable original Judge records plus authorized repair overlay.

No model/Judge inference, score writes, freeze or test. Run only after the repair
schema and completed overlay have been supplied. Generated files are confined to either historical repair analysis or the explicitly
selected judge_rejudge13_v1/analysis directory; rejudge mode preserves repair history.
"""

from __future__ import annotations
import os

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"
import argparse
import base64
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import html
import io
import json
from pathlib import Path
from samtok_benchmark.paths import repository_root
import sys
import numpy as np
from PIL import Image

REPO = repository_root()
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO / "src"))
from samtok_benchmark.ifbench.dev_scope import active_plan

ROOT = Path("/tmp/ifbench/tiered_v1/dev_selection")
REPAIR = ROOT / "judge_repair_v1"
OUT = REPAIR / "analysis"
REJUDGE_ROOT = ROOT / "judge_rejudge13_v1"
SHARED = ROOT.parent / "shared_inputs_20261027"
SEED, REPLICATES = 20261027, 10000
FAILURES = {"failed", "failed-planner", "failed-component", "failed-interrupted"}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(name, data):
    path = OUT / name
    assert path.resolve().is_relative_to(OUT.resolve())
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def quantiles(values):
    valid = np.isfinite(values)
    return {
        "CI95": np.quantile(values[valid], [0.025, 0.975]).tolist() if valid.any() else None,
        "valid_replicates": int(valid.sum()),
        "zero_denominator_replicates": int((~valid).sum()),
    }


def validate_scores(scores, unit_ids):
    if [u["id"] for u in scores["units"]] != unit_ids:
        raise ValueError("Score unit IDs/count/order do not match the canonical dev case")
    blocks = [(d, u[d]) for u in scores["units"] for d in "EPQ"]
    blocks += [(d, scores["global_" + d]) for d in "PQ"]
    for dim, block in blocks:
        value = block["score"]
        if type(value) is not int or not 0 <= value <= 4:
            raise ValueError("Invalid numeric score")
        expected = value == 4 if dim == "E" else value >= 3
        if type(block.get("pass")) is not bool or block["pass"] != expected:
            raise ValueError("Stored pass does not match the fixed score threshold")
        if not isinstance(block.get("evidence"), str) or not block["evidence"].strip():
            raise ValueError("Score evidence is missing")


def overlay_record(key, original, original_path, overlay_dir):
    """Schema adapter: original-like status/scores with raw_record_sha256 provenance.

    No missing field is guessed. Parent will confirm the final overlay schema
    before production invocation of this analysis entry point.
    """
    path = overlay_dir / (key + ".json")
    if not path.exists():
        return original, None
    fixed = read(path)
    if original["status"] != "judge-failed":
        raise ValueError(f"Overlay may replace only an originally failed record: {key}")
    if fixed.get("raw_record_sha256") != sha(original_path):
        raise ValueError(f"Overlay original-record SHA256 mismatch: {key}")
    if fixed.get("key", key) != key:
        raise ValueError(f"Overlay key mismatch: {key}")
    if fixed.get("run_id", original["run_id"]) != original["run_id"]:
        raise ValueError(f"Overlay run mismatch: {key}")
    if fixed.get("output_sha256", original["output_sha256"]) != original["output_sha256"]:
        raise ValueError(f"Overlay output mismatch: {key}")
    if fixed.get("raw_response") != original.get("raw_response"):
        raise ValueError(f"Overlay raw response changed: {key}")
    if fixed.get("repair_inference_calls") != 0:
        raise ValueError(f"Overlay must contain zero new inference calls: {key}")
    if fixed["status"] not in ("scored", "judge-failed"):
        raise ValueError(f"Unexpected repair status: {key}")
    if fixed["status"] == "scored" and "scores" not in fixed:
        raise ValueError(f"Repaired scored record lacks scores: {key}")
    if fixed["status"] == "scored":
        by_field = {u["id"] + "." + d: u[d] for u in fixed["scores"]["units"] for d in "EPQ"}
        by_field.update({f"global_{d}": fixed["scores"][f"global_{d}"] for d in "PQ"})
        atoms = defaultdict(list)
        for item in fixed["repair_audit"]:
            field = item["field"]
            if field not in by_field:
                raise ValueError(f"Unknown repair audit field: {key} {field}")
            literal = item["literal_atom"]
            if literal not in original["raw_response"]["text"]:
                raise ValueError(f"Repair literal absent from original raw response: {key} {field}")
            atom = json.loads(literal)
            if atom["score"] != by_field[field]["score"]:
                raise ValueError(f"Repair changed numeric score: {key} {field}")
            atoms[field].append(atom)
        if set(atoms) != set(by_field):
            raise ValueError(f"Incomplete per-field raw numeric provenance: {key}")
        for field, values in atoms.items():
            evidences = list(
                dict.fromkeys(v["evidence"].strip() for v in values if v["evidence"].strip())
            )
            if "\n\n".join(evidences) != by_field[field]["evidence"].strip():
                raise ValueError(
                    f"Repair evidence not exact ordered unique raw-evidence concatenation: {key} {field}"
                )
    return fixed, {
        "path": str(path),
        "sha256": sha(path),
        "raw_record_sha256": fixed["raw_record_sha256"],
        "status": fixed["status"],
    }


def validate_raw_atoms(effective, raw):
    """Check supplied deterministic recovery; never call recover or change scores."""
    blocks = {u["id"] + "." + d: u[d] for u in effective["scores"]["units"] for d in "EPQ"}
    blocks.update({f"global_{d}": effective["scores"][f"global_{d}"] for d in "PQ"})
    atoms = defaultdict(list)
    for item in effective["repair_audit"]:
        field = item["field"]
        if field not in blocks or item["literal_atom"] not in raw["raw_response"]["text"]:
            raise ValueError("Supplemental repair atom is not an authorized original field/literal")
        atom = json.loads(item["literal_atom"])
        if atom["score"] != blocks[field]["score"]:
            raise ValueError("Supplemental repair changed a numeric score")
        atoms[field].append(atom)
    if set(atoms) != set(blocks):
        raise ValueError("Supplemental repair has incomplete numeric provenance")
    for field, values in atoms.items():
        evidence = "\n\n".join(
            dict.fromkeys(x["evidence"].strip() for x in values if x["evidence"].strip())
        )
        if evidence != blocks[field]["evidence"].strip():
            raise ValueError("Supplemental repair evidence differs from the original atoms")


def load_rejudge_layer(rejudge_root, judges, originals, provenance, run_id, public, label):
    """Apply only the sole authorized new answer; preserve first-pass/repair history."""
    from samtok_benchmark.io import digest
    from samtok_benchmark.ifbench import dev_judge as canonical

    proposal_path = REPAIR / "PROPOSED_REJUDGE_13.json"
    proposal, authorization = read(proposal_path), read(rejudge_root / "authorization.json")
    proposal_sha = sha(proposal_path)
    if authorization["proposal_sha256"] != proposal_sha or not authorization.get("authorized_by"):
        raise ValueError("Missing authorization binding to the immutable 13-key proposal")
    if (
        authorization["maximum_extra_judge_calls"] != 13
        or proposal["maximum_extra_judge_calls"] != 13
    ):
        raise ValueError("Supplemental Judge call budget differs from authorized 13")
    if (
        proposal.get("image_generation_calls") != 0
        or authorization.get("frozen")
        or authorization.get("test_started")
    ):
        raise ValueError("Unauthorized editor/freeze/test action in supplemental authorization")
    if digest(proposal["judge_config"]) != run_id:
        raise ValueError("Supplemental Judge run/config differs from first pass")
    jobs = {j["key"]: j for j in proposal["requests"]}
    if len(jobs) != len(proposal["requests"]) or len(jobs) != 13:
        raise ValueError("Proposal must contain exactly 13 unique keys")
    unresolved = {k for k, v in judges.items() if v["status"] == "judge-failed"}
    if set(jobs) != unresolved:
        raise ValueError("Supplemental scope must exactly equal the 13 unresolved post-repair keys")
    dirs = {
        name: {p.stem: p for p in (rejudge_root / name).glob("*.json")}
        for name in ("admitted", "records", "effective_records")
    }
    if any(set(paths) - set(jobs) for paths in dirs.values()):
        raise ValueError("Supplemental record/admission outside authorized scope")
    if set(dirs["records"]) - set(dirs["admitted"]) or set(dirs["effective_records"]) - set(
        dirs["records"]
    ):
        raise ValueError("Supplemental records lack an admission/raw-answer chain")
    if len(dirs["admitted"]) > 13:
        raise ValueError("Supplemental call budget exceeded")
    if label == "final" and (
        set(dirs["records"]) != set(jobs) or set(dirs["admitted"]) != set(jobs)
    ):
        raise ValueError("Final supplemental analysis requires all 13 authorized attempts terminal")
    policy = read(REPAIR / "policy.json")
    if sha(Path(canonical.__file__)) != proposal["judge_config"]["source_sha256"]:
        raise ValueError("Loaded canonical implementation differs from authorized Judge config")
    source_cases = canonical.cases()
    file_hashes = {
        str(proposal_path): proposal_sha,
        str(rejudge_root / "authorization.json"): sha(rejudge_root / "authorization.json"),
    }
    result = dict(judges)
    by_key = {p["key"]: dict(p, repair_effective_status=p["effective_status"]) for p in provenance}
    canonical_counts, effective_counts = Counter(), Counter()
    execution_counts, execution_receipts = Counter(), {}
    deterministic_count = 0
    for key, job in jobs.items():
        original_path = ROOT / "judge" / run_id / "records" / (key + ".json")
        repair_path = REPAIR / "records" / (key + ".json")
        if Path(job["original_record"]).resolve() != original_path.resolve():
            raise ValueError("Proposal first-pass record path mismatch")
        old_sha, repair_sha = sha(original_path), sha(repair_path)
        if originals[key]["status"] != "judge-failed" or judges[key]["status"] != "judge-failed":
            raise ValueError("Cannot supersede an already valid first-pass or repaired score")
        if (
            job["output_sha256"] != originals[key]["output_sha256"]
            or sha(job["output_image"]) != job["output_sha256"]
        ):
            raise ValueError("Supplemental edited-output hash changed")
        case = source_cases[job["case_id"]]
        if digest(canonical.prompt(case)) != job["canonical_prompt_sha256"]:
            raise ValueError("Supplemental canonical prompt changed")
        if canonical.binding(case, job["output_sha256"], proposal["judge_config"]) != key:
            raise ValueError("Supplemental key no longer binds the original evidence/config")
        if key not in dirs["records"]:
            continue
        raw_path = dirs["records"][key]
        raw = read(raw_path)
        expected = {
            "key": key,
            "run_id": run_id,
            "output_sha256": job["output_sha256"],
            "attempt": 2,
            "additional_judge_calls": 1,
            "proposal_sha256": proposal_sha,
            "first_pass_record_sha256": old_sha,
            "repair_overlay_sha256": repair_sha,
        }
        if any(raw.get(k) != v for k, v in expected.items()):
            raise ValueError("Supplemental raw-answer binding/call-count mismatch: " + key)
        if raw["status"] not in ("scored", "judge-failed"):
            raise ValueError("Supplemental raw answer is not terminal")
        admission_path = dirs["admitted"][key]
        admission = read(admission_path)
        receipt_path = Path(raw["execution_receipt"]).resolve()
        if not receipt_path.is_relative_to((rejudge_root / "executions").resolve()):
            raise ValueError("Supplemental execution receipt escapes authorized directory")
        if (
            admission.get("key") != key
            or admission.get("attempt") != 2
            or admission.get("canonical_prompt_sha256") != job["canonical_prompt_sha256"]
            or Path(admission["execution"]).resolve() != receipt_path.parent
        ):
            raise ValueError("Supplemental admission does not match the sole new answer")
        receipt = read(receipt_path)
        if (
            receipt.get("run_id") != run_id
            or receipt.get("config") != proposal["judge_config"]
            or receipt.get("proposal_sha256") != proposal_sha
            or receipt.get("authorization_sha256") != sha(rejudge_root / "authorization.json")
            or receipt.get("maximum_extra_judge_calls") != 13
            or receipt.get("editor_calls") != 0
            or receipt.get("calibration_calls") != 0
            or receipt.get("frozen")
            or receipt.get("test_started")
        ):
            raise ValueError("Supplemental execution receipt authorization/config mismatch")
        if (
            sha(receipt_path.parent / "runner.py") != receipt["source_sha256"]
            or sha(receipt_path.parent / "canonical.py")
            != proposal["judge_config"]["source_sha256"]
            or sha(receipt_path.parent / "repair.py") != policy["source_sha256"]
        ):
            raise ValueError("Supplemental execution source snapshot mismatch")
        execution_counts[str(receipt_path)] += 1
        execution_receipts[str(receipt_path)] = receipt
        effective_path = dirs["effective_records"].get(key)
        effective = read(effective_path) if effective_path else raw
        repaired = False
        if effective_path:
            chain = {
                **expected,
                "raw_record_sha256": old_sha,
                "retry_raw_record_sha256": sha(raw_path),
                "repair_inference_calls": 0,
            }
            if any(effective.get(k) != v for k, v in chain.items()):
                raise ValueError("Supplemental effective-answer hash/call chain mismatch: " + key)
            if (
                Path(effective["retry_raw_record_path"]).resolve() != raw_path.resolve()
                or effective["raw_response"] != raw["raw_response"]
            ):
                raise ValueError(
                    "Supplemental effective record changed raw response or source path"
                )
            if effective["repair_policy"] != policy["policy"]:
                raise ValueError("Supplemental repair policy is not the approved unchanged policy")
            if raw["status"] == "scored":
                if (
                    effective["status"] != "scored"
                    or effective["scores"] != raw["scores"]
                    or effective.get("deterministic_repair_used")
                ):
                    raise ValueError("Canonical-valid supplemental answer must be used unchanged")
            elif effective["status"] == "scored":
                if (
                    effective.get("deterministic_repair_used") is not True
                    or raw["raw_response"]["finish_reason"] != "stop"
                ):
                    raise ValueError(
                        "Supplemental recovery is not an approved deterministic stop-answer recovery"
                    )
                validate_raw_atoms(effective, raw)
                repaired = True
            elif effective["status"] != "judge-failed":
                raise ValueError("Unresolved supplemental record has an unexpected status")
        if effective["status"] == "scored":
            validate_scores(effective["scores"], [u["id"] for u in public[job["case_id"]]["units"]])
        canonical_counts[raw["status"]] += 1
        effective_counts[effective["status"]] += 1
        deterministic_count += int(repaired)
        result[key] = effective
        chain_paths = [raw_path, admission_path, receipt_path] + (
            [effective_path] if effective_path else []
        )
        file_hashes.update({str(p): sha(p) for p in chain_paths})
        by_key[key].update(
            effective_status=effective["status"],
            effective_reason=effective.get("repair_reason", effective.get("reason")),
            effective_source="authorized-attempt-2-recovered"
            if repaired
            else "authorized-attempt-2",
            rejudge={
                "raw_path": str(raw_path),
                "raw_sha256": sha(raw_path),
                "effective_path": str(effective_path) if effective_path else None,
                "effective_sha256": sha(effective_path) if effective_path else None,
                "admission_path": str(admission_path),
                "execution_receipt": str(receipt_path),
                "canonical_prompt_sha256": job["canonical_prompt_sha256"],
                "first_pass_record_sha256": old_sha,
                "repair_overlay_sha256": repair_sha,
                "deterministic_repair_used": repaired,
                "additional_judge_calls": 1,
            },
        )
    for path, receipt in execution_receipts.items():
        if label == "final" and (
            receipt["status"] not in ("completed", "drained")
            or receipt["production_calls_this_execution"] != execution_counts[path]
        ):
            raise ValueError(
                "Supplemental execution call count does not reconcile with raw records"
            )
    summary_path = rejudge_root / "summary.json"
    if summary_path.exists():
        summary = read(summary_path)
        if (
            summary["run_id"] != run_id
            or summary["additional_judge_calls"] != len(dirs["records"])
            or summary["counts"] != dict(effective_counts)
            or summary["canonical_retry_counts"] != dict(canonical_counts)
            or summary["deterministic_repair_used"] != deterministic_count
            or summary["remaining_authorized_not_started"] != 13 - len(dirs["records"])
        ):
            raise ValueError("Supplemental final summary/call counts do not reconcile")
        file_hashes[str(summary_path)] = sha(summary_path)
    elif label == "final":
        raise ValueError("Supplemental terminal summary not yet present")
    accounting = {
        "enabled": True,
        "root": str(rejudge_root),
        "proposal_path": str(proposal_path),
        "proposal_sha256": proposal_sha,
        "authorized_keys": list(jobs),
        "maximum_extra_judge_calls": 13,
        "admitted_unique_keys": len(dirs["admitted"]),
        "raw_answers": len(dirs["records"]),
        "actual_extra_judge_calls": len(dirs["admitted"]),
        "new_image_generation_calls": 0,
        "canonical_counts": dict(canonical_counts),
        "effective_counts": dict(effective_counts),
        "deterministic_repair_used": deterministic_count,
        "file_hashes": file_hashes,
        "selection_rule": "sole new valid answer; no best-of; old first-pass and 183 repairs remain immutable",
    }
    return result, list(by_key.values()), accounting


def history_snapshot():
    """Retain bytes of every existing historical repair artifact in rejudge mode."""
    return {str(p): sha(p) for p in sorted(REPAIR.rglob("*")) if p.is_file()}


class Bootstrap:
    def __init__(self, ks, operations):
        self.ks = np.asarray(ks, dtype=int)
        self.operations = operations
        self.indices = np.random.default_rng(SEED).integers(0, len(ks), (REPLICATES, len(ks)))
        self.den = self.ks[self.indices].sum(axis=1)
        self.k_indices = {}
        for k in (2, 3, 4, 5):
            source_indices = np.flatnonzero(self.ks == k)
            self.k_indices[k] = (
                (
                    source_indices,
                    np.random.default_rng(SEED).choice(
                        source_indices, (REPLICATES, len(source_indices)), replace=True
                    ),
                )
                if len(source_indices)
                else (source_indices, None)
            )

    def rate(self, numerator, denominator, indices=None):
        ix = self.indices if indices is None else indices
        num = np.asarray(numerator)[ix].sum(axis=1)
        den = np.asarray(denominator)[ix].sum(axis=1)
        result = np.full(REPLICATES, np.nan)
        np.divide(num, den, out=result, where=den != 0)
        return result


def dimension_summary(values, pass_counts, case_denominators, missing):
    observed = values[np.isfinite(values)]
    full_denominator = int(np.sum(case_denominators))
    complete = not np.any(missing & (np.asarray(case_denominators) > 0))
    return {
        "numeric_observed_denominator": int(len(observed)),
        "mean_numeric_among_scored_only": float(observed.mean()) if len(observed) else None,
        "score_histogram_among_scored_only": dict(Counter(map(int, observed))),
        "full_denominator": full_denominator,
        "strict_pass_rate": float(np.sum(pass_counts) / full_denominator)
        if complete and full_denominator
        else None,
        "numeric_means_do_not_impute_generation_failures_or_missing_judgments": True,
    }


def bounds_summary(known_pass, missing_capacity, denominator):
    return {
        "lower": float(known_pass / denominator),
        "upper": float((known_pass + missing_capacity) / denominator),
        "kind": "mathematical_identification_bounds_not_observed_scores",
        "assumption": "Every unresolved case/unit may pass or fail; known generation failures remain failures.",
    }


def make_row(model, candidate, setting, context, boot):
    plan, records, aliases, bindings, judges, public = (
        context[k] for k in ("plan", "records", "aliases", "bindings", "judges", "public")
    )
    n, maxk = len(plan["case_ids"]), int(max(boot.ks))
    counts = Counter()
    unit_bits = np.zeros((n, maxk), dtype=bool)
    dims = np.full((n, maxk, 3), np.nan)
    global_dims = np.full((n, 2), np.nan)
    unknown = np.zeros(n, dtype=bool)
    genfail = np.zeros(n, dtype=bool)
    joint = np.zeros(n, dtype=int)
    missing_keys = Counter()
    proof = []
    for i, cid in enumerate(plan["case_ids"]):
        logical = f"{model}/{candidate['id']}/{setting}/{cid}"
        target = aliases.get(logical, logical)
        record = records.get(target)
        key = None
        if record is None:
            counts["generation-pending"] += 1
            unknown[i] = True
            key = "unresolved-generation:" + target
        elif record["status"] == "generated":
            rp = str(ROOT / "runs" / target / "result.json")
            key = bindings.get(rp)
            judgment = judges.get(key)
            if judgment is None:
                counts["judge-pending"] += 1
                unknown[i] = True
                key = key or "unbound-generated:" + target
            elif judgment["status"] == "scored":
                counts["scored"] += 1
                scores = judgment["scores"]
                validate_scores(scores, [u["id"] for u in public[cid]["units"]])
                values = np.array([[u[d]["score"] for d in "EPQ"] for u in scores["units"]])
                dims[i, : len(values)] = values
                unit_bits[i, : len(values)] = (
                    (values[:, 0] == 4) & (values[:, 1] >= 3) & (values[:, 2] >= 3)
                )
                global_dims[i] = [scores["global_" + d]["score"] for d in "PQ"]
                joint[i] = int(unit_bits[i, : len(values)].all() and (global_dims[i] >= 3).all())
            else:
                counts[judgment["status"]] += 1
                unknown[i] = True
        elif record["status"] in FAILURES:
            counts[record["status"]] += 1
            genfail[i] = True
        else:
            counts[record["status"]] += 1
            unknown[i] = True
            key = "unresolved-generation:" + target
        if unknown[i]:
            missing_keys[key] += 1
        proof.append(
            {
                "case_id": cid,
                "logical_key": logical,
                "physical_key": target,
                "judge_key": key,
                "generation_status": record["status"] if record else "pending",
                "K": int(boot.ks[i]),
                "unknown": bool(unknown[i]),
                "UnitPass_count": None if unknown[i] else int(unit_bits[i].sum()),
                "JointPass": None if unknown[i] else int(joint[i]),
            }
        )
    upcounts = unit_bits.sum(axis=1)
    den = int(boot.ks.sum())
    complete = not unknown.any()
    row = {
        "model": model,
        "candidate": candidate["id"],
        "role": candidate["role"],
        "setting": setting,
        "complete": bool(complete),
        "status_counts": dict(counts),
        "case_denominator": n,
        "unit_denominator": den,
        "generation_failed_cases": int(genfail.sum()),
        "unresolved_cases": int(unknown.sum()),
        "unresolved_units": int(boot.ks[unknown].sum()),
        "UnitPass": float(upcounts.sum() / den) if complete else None,
        "JointPass": float(joint.sum() / n) if complete else None,
        "UnitPass_bounds": bounds_summary(upcounts.sum(), boot.ks[unknown].sum(), den),
        "JointPass_bounds": bounds_summary(joint.sum(), unknown.sum(), n),
        "dimensions": {},
        "by_K": {},
        "by_operation": {},
    }
    distributions = {}
    if complete:
        distributions = {
            "UnitPass": boot.rate(upcounts, boot.ks),
            "JointPass": boot.rate(joint, np.ones(n, dtype=int)),
        }
        row["bootstrap"] = {name: quantiles(v) for name, v in distributions.items()}
    else:
        row["bootstrap"] = None
    valid_slots = np.arange(maxk)[None, :] < boot.ks[:, None]
    dimension_bits = [(dims[:, :, 0] == 4), (dims[:, :, 1] >= 3), (dims[:, :, 2] >= 3)]
    for d, bit, values in zip("EPQ", dimension_bits, np.moveaxis(dims, 2, 0)):
        row["dimensions"][d] = dimension_summary(values[valid_slots], bit.sum(1), boot.ks, unknown)
    for i, d in enumerate("PQ"):
        row["dimensions"]["global_" + d] = dimension_summary(
            global_dims[:, i], global_dims[:, i] >= 3, np.ones(n, dtype=int), unknown
        )
    for k, (src, ix) in boot.k_indices.items():
        if not len(src):
            row["by_K"][str(k)] = {"case_denominator": 0, "UnitPass": None, "JointPass": None}
            continue
        ok = not unknown[src].any()
        bucket = {
            "case_denominator": len(src),
            "unit_denominator": int(boot.ks[src].sum()),
            "complete": bool(ok),
            "unresolved_cases": int(unknown[src].sum()),
            "UnitPass": float(upcounts[src].sum() / boot.ks[src].sum()) if ok else None,
            "JointPass": float(joint[src].mean()) if ok else None,
            "generation_failed_cases": int(genfail[src].sum()),
        }
        if ok:
            bucket["bootstrap"] = {
                "UnitPass": quantiles(boot.rate(upcounts, boot.ks, ix)),
                "JointPass": quantiles(boot.rate(joint, np.ones(n, dtype=int), ix)),
            }
        else:
            bucket["bootstrap"] = None
        bucket["dimensions"] = {}
        for d, bit, values in zip("EPQ", dimension_bits, np.moveaxis(dims, 2, 0)):
            bucket["dimensions"][d] = dimension_summary(
                values[src][valid_slots[src]], bit[src].sum(1), boot.ks[src], unknown[src]
            )
        for di, d in enumerate("PQ"):
            bucket["dimensions"]["global_" + d] = dimension_summary(
                global_dims[src, di],
                global_dims[src, di] >= 3,
                np.ones(len(src), dtype=int),
                unknown[src],
            )
        row["by_K"][str(k)] = bucket
    for operation in ("add", "replace", "remove", "attribute"):
        mask = np.zeros_like(unit_bits)
        for i, cid in enumerate(plan["case_ids"]):
            mask[i, : boot.ks[i]] = [u["operation"] == operation for u in public[cid]["units"]]
        ds = mask.sum(axis=1)
        numerator = (unit_bits & mask).sum(axis=1)
        ok = not (unknown & (ds > 0)).any()
        bucket = {
            "unit_denominator": int(ds.sum()),
            "complete": bool(ok),
            "unresolved_units": int(ds[unknown].sum()),
            "UnitPass": float(numerator.sum() / ds.sum()) if ok and ds.sum() else None,
            "bootstrap": quantiles(boot.rate(numerator, ds)) if ok and ds.sum() else None,
            "dimensions": {},
        }
        for d, bit, values in zip("EPQ", dimension_bits, np.moveaxis(dims, 2, 0)):
            bucket["dimensions"][d] = dimension_summary(
                values[mask], (bit & mask).sum(1), ds, unknown
            )
        row["by_operation"][operation] = bucket
    arrays = {
        "UnitPass_count": upcounts,
        "JointPass": joint,
        "unknown": unknown,
        "missing_keys": missing_keys,
        "known_joint_total": int(joint.sum()),
        "bootstrap": distributions,
        "case_evidence": proof,
    }
    return row, arrays


def derived_metrics(candidate_rows, arrays, role):
    definitions = [
        (f"Delta_lang_{m}", [f"S2-{m}", f"S3-{m}"], "difference") for m in ("point", "box", "mask")
    ]
    definitions += [
        (f"G_region_{m}", [f"S2-{m}", "S1"], "difference") for m in ("point", "box", "mask")
    ]
    definitions += [
        ("R_mod", ["S3-point", "S3-box", "S3-mask"], "ratio"),
        ("C_mix", ["S3-point", "S3-box", "S3-mask", "S4-noref"], "mix"),
    ]
    result = []
    for metric in ("UnitPass", "JointPass"):
        for name, settings, kind in definitions:
            item = {
                "metric": metric,
                "diagnostic": name,
                "settings": settings,
                "value": None,
                "bootstrap": None,
                "unavailable_reason": None,
            }
            if role == "discard":
                item["unavailable_reason"] = (
                    "discard-region supplement excluded from paired region interpretation"
                )
            elif not all(candidate_rows[s][metric] is not None for s in settings):
                item["unavailable_reason"] = (
                    "incomplete common full denominator; no subset substitution"
                )
            else:
                point = np.array([candidate_rows[s][metric] for s in settings])
                bs = np.array([arrays[s]["bootstrap"][metric] for s in settings])
                if kind == "difference":
                    value, distribution = point[0] - point[1], bs[0] - bs[1]
                elif kind == "mix":
                    value, distribution = point[:3].mean() - point[3], bs[:3].mean(0) - bs[3]
                else:
                    value = point.min() / point.max() if point.max() else None
                    distribution = np.full(REPLICATES, np.nan)
                    np.divide(bs.min(0), bs.max(0), out=distribution, where=bs.max(0) != 0)
                    if value is None:
                        item["unavailable_reason"] = "maximum modality rate is zero"
                item["value"] = float(value) if value is not None else None
                item["bootstrap"] = quantiles(distribution)
            result.append(item)
    return result


def pairwise_bounds(left, right, denominator):
    """Sharp JP difference bounds for free binary unknowns, shared by Judge key.

    Unknown scores are not assigned or persisted. Same Judge-key aliases cancel.
    This is an identification interval, not a sampling CI or measured score.
    """
    constant = left["known_joint_total"] - right["known_joint_total"]
    coefficients = Counter(left["missing_keys"])
    coefficients.subtract(right["missing_keys"])
    lo = constant + sum(v for v in coefficients.values() if v < 0)
    hi = constant + sum(v for v in coefficients.values() if v > 0)
    return {
        "lower": lo / denominator,
        "upper": hi / denominator,
        "constant_known_joint_count_difference": constant,
        "nonzero_unknown_key_coefficients": {k: v for k, v in coefficients.items() if v},
        "denominator": denominator,
        "kind": "mathematical_bounds_not_observed_difference_or_CI",
    }


def summarize_selection(model, plan, rows, arrays):
    settings = plan["selection"]["settings"][model]
    candidates = plan["candidates"][model]
    stats, totals = [], {}
    for priority, c in enumerate(candidates):
        cr = [rows[(model, c["id"], s)] for s in settings]
        ar = [arrays[(model, c["id"], s)] for s in settings]
        full = all(r["complete"] for r in cr)
        total = {
            "known_joint_total": sum(a["known_joint_total"] for a in ar),
            "missing_keys": Counter(),
        }
        for a in ar:
            total["missing_keys"].update(a["missing_keys"])
        totals[c["id"]] = total
        n = len(plan["case_ids"]) * len(settings)
        # Same case denominator in every registered setting: sum integer JP counts
        # before division so exact ties cannot be broken by floating summation order.
        value = total["known_joint_total"] / n if full else None
        distribution = np.array([a["bootstrap"]["JointPass"] for a in ar]).mean(0) if full else None
        stats.append(
            {
                "candidate": c["id"],
                "role": c["role"],
                "registered_priority": priority,
                "settings": settings,
                "complete_settings": [r["setting"] for r in cr if r["complete"]],
                "incomplete_settings": [r["setting"] for r in cr if not r["complete"]],
                "complete": full,
                "mean_JointPass": value,
                "mean_JointPass_bootstrap": quantiles(distribution) if full else None,
                "mean_JointPass_bounds": bounds_summary(
                    total["known_joint_total"], sum(total["missing_keys"].values()), n
                ),
            }
        )
    primary = [s for s in stats if s["role"] == "primary"]
    ready = bool(primary) and all(s["complete"] for s in primary)
    chosen = (
        min(
            primary, key=lambda c: (-c["mean_JointPass"], c["registered_priority"], c["candidate"])
        )["candidate"]
        if ready
        else None
    )
    comparisons = []
    for a in primary:
        for b in primary:
            if a["candidate"] >= b["candidate"]:
                continue
            item = {
                "left": a["candidate"],
                "right": b["candidate"],
                "difference_bounds": pairwise_bounds(
                    totals[a["candidate"]],
                    totals[b["candidate"]],
                    len(plan["case_ids"]) * len(settings),
                ),
            }
            if a["complete"] and b["complete"]:
                ab = np.array(
                    [arrays[(model, a["candidate"], s)]["bootstrap"]["JointPass"] for s in settings]
                ).mean(0)
                bb = np.array(
                    [arrays[(model, b["candidate"], s)]["bootstrap"]["JointPass"] for s in settings]
                ).mean(0)
                item.update(
                    observed_difference=a["mean_JointPass"] - b["mean_JointPass"],
                    paired_bootstrap=quantiles(ab - bb),
                )
            else:
                item.update(observed_difference=None, paired_bootstrap=None)
            comparisons.append(item)
    robust = []
    if len(primary) > 1:
        for a in primary:
            if all(
                pairwise_bounds(
                    totals[a["candidate"]],
                    totals[b["candidate"]],
                    len(plan["case_ids"]) * len(settings),
                )["lower"]
                > 0
                for b in primary
                if b != a
            ):
                robust.append(a["candidate"])
    s2 = {}
    for setting in ("S2-point", "S2-box", "S2-mask"):
        eligible = [
            rows[(model, c["id"], setting)]
            for c in candidates
            if c["role"] in ("primary", "discard")
        ]
        full = all(r["complete"] for r in eligible)
        priority = {c["id"]: i for i, c in enumerate(candidates)}
        winner = (
            min(
                eligible,
                key=lambda r: (
                    -r["JointPass"],
                    r["role"] == "discard",
                    priority[r["candidate"]],
                    r["candidate"],
                ),
            )
            if full
            else None
        )
        equal_groups = defaultdict(list)
        for r in eligible:
            if r["JointPass"] is not None:
                equal_groups[r["JointPass"]].append(r["candidate"])
        observed_ties = [
            {"JointPass": value, "candidates": cs, "all_eligible_complete": full}
            for value, cs in equal_groups.items()
            if len(cs) > 1
        ]
        best_ties = (
            [r["candidate"] for r in eligible if r["JointPass"] == winner["JointPass"]]
            if winner
            else []
        )
        s2[setting] = {
            "complete": full,
            "candidate": winner["candidate"] if winner else None,
            "discard_region": winner["role"] == "discard" if winner else None,
            "JointPass": winner["JointPass"] if winner else None,
            "tied_best_candidates": best_ties,
            "observed_equal_score_groups": observed_ties,
            "tie_break": "retain region first, then registered candidate order, then candidate id",
            "tie_break_alignment_note": "Analysis implementation aligned with preregistered order; old dev_report uses candidate-name order. No original records or old reports changed.",
            "eligible": [
                {
                    k: r[k]
                    for k in ("candidate", "role", "JointPass", "complete", "JointPass_bounds")
                }
                for r in eligible
            ],
        }
    return {
        "candidates": stats,
        "primary_score_complete": ready,
        "proposed_primary": chosen,
        "primary_pairwise_comparisons": comparisons,
        "bound_robust_primary_if_missing": robust[0] if not ready and len(robust) == 1 else None,
        "bound_robust_note": "Not a completed measured selection; no freeze authorization. Shared-key unknowns cancel in differences.",
        "sole_primary_candidate": primary[0]["candidate"] if len(primary) == 1 else None,
        "S2_best_adapted": s2,
    }


def thumbnail(path):
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((390, 290))
        buffer = io.BytesIO()
        im.save(buffer, "JPEG", quality=78)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def representative_images(plan, records):
    """Fixed first dev source, S1/S3-point/S3-mask/S5, first primary per model.

    No score-dependent selection. Existing source/output images are only resized
    for the report; no output generation or alteration of evaluation images.
    """
    cid = plan["case_ids"][0]
    result = []
    for model, candidates in plan["candidates"].items():
        candidate = next(c for c in candidates if c["role"] == "primary")
        for setting in ("S1", "S3-point", "S3-mask", "S5"):
            key = f"{model}/{candidate['id']}/{setting}/{cid}"
            r = records.get(key)
            call_path = ROOT / "runs" / key / "call.json"
            call = read(call_path) if call_path.exists() else {}
            result.append(
                {
                    "model": model,
                    "candidate": candidate["id"],
                    "setting": setting,
                    "case_id": cid,
                    "source": call.get("source", {}).get("path"),
                    "output": r.get("output_image") if r else None,
                    "generation_status": r.get("status") if r else "pending",
                    "call_path": str(call_path),
                    "prompt": call.get("prompt"),
                    "actual_input_images": call.get("images", []),
                }
            )
    return result


def pct(x):
    return "缺分 / N/A" if x is None else f"{100 * x:.2f}%"


def ci_text(row, metric):
    value = row[metric]
    if value is None:
        b = row[metric + "_bounds"]
        return f"缺分；数学界[{pct(b['lower'])}, {pct(b['upper'])}]"
    ci = row["bootstrap"][metric]["CI95"]
    return f"{pct(value)} [{pct(ci[0])}, {pct(ci[1])}]"


def render(report, samples):
    md = "# IF-Bench dev：确定性修复overlay后的完整分析\n\n"
    if report["supplemental_judge"]["enabled"]:
        md += (
            "本报告依次读取不可变首轮Judge、183条确定性恢复及获准13-key一次补评层；新层只替换原先仍缺失的授权key。"
            f"新增Judge调用 {report['supplemental_judge']['actual_extra_judge_calls']} 次；统计工具自身0次推理、0次图像生成，不在多个有效回答间挑选。"
            "旧修复报告和原始评分保留。尚未冻结、未启动test。\n\n"
        )
    else:
        md += (
            "本报告使用不可变原始Judge记录加经授权的独立修复overlay；只替换原judge-failed且原记录SHA256匹配的条目。"
            "无新推理，无重采样，不改原分数文件。分数修复不意味着编辑图像改变。未冻结、未启动test。\n\n"
        )
    md += (
        "**快照阶段："
        + report["snapshot_label"]
        + "。preliminary表示修复边界仍由主审核查，不能当最终修复版。**\n\n"
    )
    md += f"生成时间：{report['created_at_utc']}。当前范围：{', '.join(report['models'])}；MaskFlow按既有scope排除。\n\n"
    md += (
        "严格UP：E=4、P≥3、Q≥3，按单元微平均。JP：一图全部单元通过且global P/Q≥3，按源图平均。"
        "每setting固定108图/386单元；生成失败留在分母。尚未恢复的Judge失败不补0、不换子集。"
        "全部模型/settings共享10000次源图cluster bootstrap索引，seed=20261027，95% percentile CI；K桶内重采样。\n\n"
    )
    md += "## 原始与修复覆盖\n\n|模型|唯一Judge原始状态|有效状态|overlay恢复数|一次补评恢复数|物理生成状态|\n|---|---|---|---|---|---|\n"
    for m, cov in report["coverage_by_model"].items():
        md += f"|{m}|{cov['original_unique_judge_statuses']}|{cov['effective_unique_judge_statuses']}|{cov['repaired_unique_records']}|{cov['rejudged_unique_records']}|{cov['physical_generation_statuses']}|\n"
    md += "\n唯一Judge key、物理生成绑定和候选逻辑行分别计数；复用相同key不是新增Judge调用。\n\n"
    md += "### 未恢复记录（保持缺分）\n\n|key|模型|case|拒绝恢复原因|\n|---|---|---|---|\n"
    for missing in report["unresolved_judgments"]:
        reason = str(missing.get("effective_reason") or "").replace("|", " / ").replace("\n", " ")
        md += f"|{missing['key']}|{', '.join(missing['models'])}|{missing['case_id']}|{reason}|\n"
    md += "\n下列候选数学界及逐逻辑图证据显示这些key的影响；同key在候选/settings间复用时以同一未知JP变量处理，不当独立缺失项。\n\n"
    md += "## 候选均JP与建议（仅完整候选比较）\n\n"
    md += "候选以预登记适用settings的平均JP选择；平分按注册顺序。官方PE/PUP只单列，不参加受控主行选择。缺分时数学界不是实测分数，稳健性证据不能替代冻结前审批。\n\n"
    for model, selection in report["selection"].items():
        md += (
            "\n### "
            + model
            + "\n\n|模型|候选|角色|均JP及95% CI / 数学界|完整settings|\n|---|---|---|---|---|\n"
        )
        for c in selection["candidates"]:
            if c["complete"]:
                ci = c["mean_JointPass_bootstrap"]["CI95"]
                score = f"{pct(c['mean_JointPass'])} [{pct(ci[0])}, {pct(ci[1])}]"
            else:
                b = c["mean_JointPass_bounds"]
                score = f"缺分；数学界[{pct(b['lower'])}, {pct(b['upper'])}]"
            md += f"|{model}|{c['candidate']}|{c['role']}|{score}|{len(c['complete_settings'])}/{len(c['settings'])}|\n"
        md += (
            f"\n{model}：拟选主配置 **{selection['proposed_primary'] or '阻塞：主候选分数不齐'}**。"
        )
        if selection["bound_robust_primary_if_missing"]:
            md += f" 数学界证明{selection['bound_robust_primary_if_missing']}在所有剩余JP取值下严格领先，但这仍不是完整实测选型。"
        md += "\n\n"
    md += "## S2 best-adapted补充\n\n|模型|setting|建议候选|discard-region|JP|并列情况|\n|---|---|---|---|---|---|\n"
    for model, selection in report["selection"].items():
        for setting, result in selection["S2_best_adapted"].items():
            tie_note = (
                "; ".join(
                    ", ".join(g["candidates"]) + " 同为 " + pct(g["JointPass"])
                    for g in result["observed_equal_score_groups"]
                )
                or "无已知同分"
            )
            if not result["complete"] and result["observed_equal_score_groups"]:
                tie_note += "；其他候选缺分，非最终并列胜者"
            md += f"|{model}|{setting}|{result['candidate'] or '缺分，不选择'}|{result['discard_region']}|{pct(result['JointPass'])}|{tie_note}|\n"
    md += "\ndiscard-region候选只在S2丢弃区域；其S1/S3/S4/S5行均复用首个主候选的原请求，绝不表示在S3或S4-noref丢弃区域。\n\n"
    md += "\n丢弃区域胜出只属于S2-best-adapted补充；不进入保留区域主配对行或Δ_lang/G_region解释。S2同分先保留区域，再按预登记候选顺序；这里修正旧dev_report的候选名字母序实现以与预登记对齐，未修改原评分或旧报告。已知部分候选同分而其他候选缺分时，仍不作最终选择。\n\n"
    md += "## 全部候选×setting\n\n|模型|候选|setting|UP（95% CI）|JP（95% CI）|未恢复图数|\n|---|---|---|---|---|---|\n"
    for row in report["rows"]:
        md += f"|{row['model']}|{row['candidate']}|{row['setting']}|{ci_text(row, 'UnitPass')}|{ci_text(row, 'JointPass')}|{row['unresolved_cases']}|\n"
    md += "\n## 指标解释与限制\n\n"
    md += (
        "Δ_lang=S2−S3、G_region=S2−S1、R_mod=min(S3)/max(S3)、C_mix=mean(S3)−S4-noref，UP/JP均计算；"
        "任一相关setting缺完整相同分母则N/A，R_mod最大值为0则N/A。每次bootstrap重新计算派生式，记录有效与零分母次数。"
        "原生planner模型的G_region是系统差异，非纯区域因果增益；C_mix仅描述性。discard补充不计算主配对派生式。\n\n"
        "E/P/Q及global数值均值只用已有数值，不为生成失败或缺分虚构数值；通过率完整时使用全分母。"
        "K和操作桶缺分时也不报实测通过率。跨模型图像不是随机人审，本报告不估计残留率或人工κ。"
        "配置尚未冻结；即使数分齐全，仍须停在冻结/test前审批门。\n"
    )
    (OUT / "SUMMARY.md").write_text(md)
    try:
        from markdown_it import MarkdownIt

        body = MarkdownIt("commonmark", {"html": False}).enable("table").render(md)
    except ImportError:
        body = "<pre>" + html.escape(md) + "</pre>"
    parts = [
        '<!doctype html><html lang="zh"><meta charset="utf-8"><title>IF-Bench repaired dev analysis</title>'
        "<style>body{font:15px system-ui;line-height:1.55;margin:30px auto;padding:0 20px;max-width:1600px;color:#172b3a}"
        "table{border-collapse:collapse;font-size:13px}th,td{border:1px solid #ccd6dd;padding:6px;vertical-align:top}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f5f8;padding:14px}"
        "details{border:1px solid #d1d9df;padding:12px;margin:12px 0}.imgs{display:flex;flex-wrap:wrap;gap:10px}"
        "figure{margin:4px}img{max-width:390px}summary{cursor:pointer}</style>",
        body,
        '<p><a href="ANALYSIS.json">完整机器统计</a> · <a href="PROVENANCE.json">原始/overlay哈希证据</a>'
        ' · <a href="CASE_EVIDENCE.json">逐逻辑图分母与通过数</a></p>',
    ]
    for model in report["models"]:
        parts.append("<h2>" + html.escape(model) + "：E/P/Q、global、K/操作桶及派生指标</h2>")
        for row in [r for r in report["rows"] if r["model"] == model]:
            details = {k: row[k] for k in ("dimensions", "by_K", "by_operation")}
            parts.append(
                "<details><summary>"
                + html.escape(row["candidate"] + " / " + row["setting"])
                + "</summary><pre>"
                + html.escape(json.dumps(details, ensure_ascii=False, indent=2))
                + "</pre></details>"
            )
        parts.append(
            "<details><summary>全部候选派生指标与排名稳健性区间</summary><pre>"
            + html.escape(
                json.dumps(
                    {"derived": report["derived"][model], "selection": report["selection"][model]},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            + "</pre></details>"
        )
    parts.append(
        "<h2>固定代表图：原plan首图，首个注册主候选，S1/S3-point/S3-mask/S5</h2>"
        "<p>所有图均为既有dev产物，不按新分数挑选。图示不构成总体定性结论。实际prompt可展开。</p>"
    )
    cache = {}
    for sample in samples:
        parts.append(
            "<h3>"
            + html.escape(
                " / ".join(sample[k] for k in ("model", "candidate", "setting", "case_id"))
            )
            + '</h3><div class="imgs">'
        )
        for label, path in [("源图", sample["source"]), ("实际输出", sample["output"])]:
            if path and Path(path).exists():
                if path not in cache:
                    cache[path] = thumbnail(path)
                parts.append(
                    '<figure><img src="'
                    + cache[path]
                    + '"><figcaption>'
                    + label
                    + "</figcaption></figure>"
                )
            else:
                parts.append("<p>" + label + "缺失；不替换样例。</p>")
        parts.append(
            "</div><details><summary>实际prompt及可追溯输入路径</summary><pre>"
            + html.escape(json.dumps(sample, ensure_ascii=False, indent=2))
            + "</pre></details>"
        )
    parts.append("</html>")
    (OUT / "REPORT.html").write_text("".join(parts))


def analyze(label="preliminary", rejudge_root=None):
    global OUT
    if rejudge_root is not None:
        rejudge_root = Path(rejudge_root).resolve()
        if rejudge_root != REJUDGE_ROOT.resolve():
            raise ValueError("Only the authorized judge_rejudge13_v1 root is supported")
        OUT = rejudge_root / "analysis"
    else:
        OUT = REPAIR / "analysis"
    historical_hashes = history_snapshot() if rejudge_root is not None else {}
    if not (REPAIR / "records").is_dir():
        raise RuntimeError(
            "Repair overlay not yet supplied; refusing to run a purported repaired analysis"
        )
    plan = active_plan()
    if "maskflow" in plan["candidates"]:
        raise ValueError("Active scope unexpectedly includes excluded MaskFlow")
    current = read(ROOT / "judge/current.json")
    judge_root = ROOT / "judge" / current["run_id"]
    raw_bindings = read(judge_root / "bindings.json")
    bindings = {b["record"]: b["key"] for b in raw_bindings}
    tasks = {t["key"]: t for t in plan["tasks"]}
    records = {
        key: read(ROOT / "runs" / key / "result.json")
        for key in tasks
        if (ROOT / "runs" / key / "result.json").exists()
    }
    public = {cid: read(SHARED / "requests/S1" / cid / "public.json") for cid in plan["case_ids"]}
    key_models, key_case = defaultdict(set), {}
    for key, record in records.items():
        if record["status"] != "generated":
            continue
        rp = str(ROOT / "runs" / key / "result.json")
        if rp not in bindings:
            continue
        judge_key = bindings[rp]
        key_models[judge_key].add(record["task"]["model"])
        if judge_key in key_case and key_case[judge_key] != record["task"]["case_id"]:
            raise ValueError("Same Judge key mapped to different canonical cases")
        key_case[judge_key] = record["task"]["case_id"]
    extras = {p.stem for p in (REPAIR / "records").glob("*.json")} - set(key_models)
    if extras:
        raise ValueError(f"Overlay contains keys outside active scope: {sorted(extras)[:4]}")
    judges, originals, provenance = {}, {}, []
    for key in key_models:
        raw_path = judge_root / "records" / (key + ".json")
        if not raw_path.exists():
            continue
        original = read(raw_path)
        if original["key"] != key or original["run_id"] != current["run_id"]:
            raise ValueError("Original Judge binding mismatch")
        effective, overlay = overlay_record(key, original, raw_path, REPAIR / "records")
        if effective["status"] == "scored":
            validate_scores(effective["scores"], [u["id"] for u in public[key_case[key]]["units"]])
        originals[key], judges[key] = original, effective
        provenance.append(
            {
                "key": key,
                "models": sorted(key_models[key]),
                "case_id": key_case[key],
                "raw_path": str(raw_path),
                "raw_sha256": sha(raw_path),
                "original_status": original["status"],
                "effective_status": effective["status"],
                "original_reason": original.get("reason"),
                "effective_reason": effective.get("repair_reason", effective.get("reason")),
                "overlay": overlay,
            }
        )
    repair_judges = dict(judges)
    supplemental = {
        "enabled": False,
        "actual_extra_judge_calls": 0,
        "new_image_generation_calls": 0,
    }
    if rejudge_root is not None:
        judges, provenance, supplemental = load_rejudge_layer(
            rejudge_root, judges, originals, provenance, current["run_id"], public, label
        )
    context = {
        "plan": plan,
        "records": records,
        "aliases": {a["key"]: a["target"] for a in plan["aliases"]},
        "bindings": bindings,
        "judges": judges,
        "public": public,
    }
    boot = Bootstrap([len(public[c]["units"]) for c in plan["case_ids"]], public)
    rows, arrays = {}, {}
    for model, candidates in plan["candidates"].items():
        for candidate in candidates:
            for setting in plan["settings"]:
                key = model, candidate["id"], setting
                rows[key], arrays[key] = make_row(model, candidate, setting, context, boot)
        print(
            json.dumps(
                {"model": model, "rows_calculated": len(candidates) * len(plan["settings"])}
            ),
            flush=True,
        )
    derived, selection, coverage = {}, {}, {}
    for model, candidates in plan["candidates"].items():
        derived[model] = {}
        for c in candidates:
            derived[model][c["id"]] = derived_metrics(
                {s: rows[(model, c["id"], s)] for s in plan["settings"]},
                {s: arrays[(model, c["id"], s)] for s in plan["settings"]},
                c["role"],
            )
        selection[model] = summarize_selection(model, plan, rows, arrays)
        model_keys = {k for k, ms in key_models.items() if model in ms}
        model_records = [r for k, r in records.items() if tasks[k]["model"] == model]
        coverage[model] = {
            "unique_judge_keys": len(model_keys),
            "original_unique_judge_statuses": dict(
                Counter(originals[k]["status"] if k in originals else "pending" for k in model_keys)
            ),
            "effective_unique_judge_statuses": dict(
                Counter(judges[k]["status"] if k in judges else "pending" for k in model_keys)
            ),
            "repaired_unique_records": sum(
                k in originals
                and originals[k]["status"] == "judge-failed"
                and repair_judges[k]["status"] == "scored"
                for k in model_keys
            ),
            "repair_layer_unique_judge_statuses": dict(
                Counter(
                    repair_judges[k]["status"] if k in repair_judges else "pending"
                    for k in model_keys
                )
            ),
            "rejudged_unique_records": sum(
                k in repair_judges
                and repair_judges[k]["status"] != "scored"
                and judges[k]["status"] == "scored"
                for k in model_keys
            ),
            "physical_generation_statuses": dict(Counter(r["status"] for r in model_records)),
            "physical_tasks_registered": sum(t["model"] == model for t in tasks.values()),
            "logical_aliases_registered": sum(a["model"] == model for a in plan["aliases"]),
        }
    report = {
        "schema": "ifbench.repaired-dev-analysis.v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_label": label,
        "models": list(plan["candidates"]),
        "plan_digest": plan["digest"],
        "scope": plan.get("scope"),
        "judge_run_id": current["run_id"],
        "overlay_directory": str(REPAIR / "records"),
        "analysis_code_sha256": sha(Path(__file__)),
        "coverage_by_model": coverage,
        "supplemental_judge": supplemental,
        "analysis_output_root": str(OUT),
        "bootstrap": {
            "cluster": "source image",
            "seed": SEED,
            "replicates": REPLICATES,
            "numpy_version": np.__version__,
            "generator": "numpy.random.default_rng",
            "same_indices_all_models_settings": True,
            "indices_sha256": hashlib.sha256(boot.indices.tobytes()).hexdigest(),
            "case_ids": plan["case_ids"],
            "K_buckets_resampled_within_bucket": True,
        },
        "rows": list(rows.values()),
        "derived": derived,
        "selection": selection,
        "unresolved_judgments": [p for p in provenance if p["effective_status"] != "scored"],
        "unique_judge_records_total": len(provenance),
        "global_original_unique_statuses": dict(Counter(p["original_status"] for p in provenance)),
        "global_effective_unique_statuses": dict(
            Counter(p["effective_status"] for p in provenance)
        ),
        "global_repair_layer_unique_statuses": dict(
            Counter(r["status"] for r in repair_judges.values())
        ),
        "all_rows_score_complete": all(r["complete"] for r in rows.values()),
        "all_primary_selection_scores_complete": all(
            s["primary_score_complete"] for s in selection.values()
        ),
        "mathematical_bounds_are_not_observed_scores_or_confidence_intervals": True,
        "frozen": False,
        "test_started": False,
        "new_inference_calls": 0,
        "analysis_inference_calls": 0,
        "additional_judge_calls_in_data_layer": supplemental["actual_extra_judge_calls"],
        "user_freeze_approval_still_required": True,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    dump("ANALYSIS.json", report)
    dump("PROVENANCE.json", {"judge_run_id": current["run_id"], "records": provenance})
    dump(
        "CASE_EVIDENCE.json",
        {
            "rows": [
                {"model": k[0], "candidate": k[1], "setting": k[2], "cases": v["case_evidence"]}
                for k, v in arrays.items()
            ]
        },
    )
    samples = representative_images(plan, records)
    dump(
        "SAMPLES.json",
        {
            "rule": "first registered case, first primary candidate per model, four predeclared key settings; never selected by scores",
            "samples": samples,
        },
    )
    proposed = {
        "status": "awaiting-user-freeze-approval"
        if report["all_rows_score_complete"]
        else "blocked-incomplete-judge",
        "plan_digest": plan["digest"],
        "judge_run_id": current["run_id"],
        "analysis": str(OUT / "ANALYSIS.json"),
        "primary_recommendations": {
            m: {
                "candidate": s["proposed_primary"],
                "registered_configuration": next(
                    (c for c in plan["candidates"][m] if c["id"] == s["proposed_primary"]), None
                ),
                "candidate_statistics": s["candidates"],
            }
            for m, s in selection.items()
        },
        "S2_best_adapted": {m: s["S2_best_adapted"] for m, s in selection.items()},
        "additional_judge_calls": supplemental["actual_extra_judge_calls"],
        "frozen": False,
        "freeze_authorized": False,
        "test_started": False,
    }
    dump("PROPOSED_SELECTION.json", proposed)
    render(report, samples)
    # A final immutable-input verification also catches concurrent source updates.
    for p in provenance:
        if sha(p["raw_path"]) != p["raw_sha256"]:
            raise ValueError("Original Judge record changed during analysis")
        if p["overlay"] and sha(p["overlay"]["path"]) != p["overlay"]["sha256"]:
            raise ValueError("Overlay changed during analysis")
    for path, expected in supplemental.get("file_hashes", {}).items():
        if sha(path) != expected:
            raise ValueError("Supplemental artifact changed during analysis: " + path)
    for path, expected in historical_hashes.items():
        if sha(path) != expected:
            raise ValueError("Historical repair artifact changed: " + path)
    if historical_hashes:
        dump("HISTORY_VERIFICATION.json", {"files": historical_hashes, "all_unchanged": True})
    dump(
        "RECEIPT.json",
        {
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "analysis_complete": True,
            "snapshot_label": label,
            "all_rows_score_complete": report["all_rows_score_complete"],
            "original_records_verified_unchanged": len(provenance),
            "overlay_records_verified_unchanged": sum(p["overlay"] is not None for p in provenance),
            "new_inference_calls": 0,
            "additional_judge_calls_in_data_layer": supplemental["actual_extra_judge_calls"],
            "historical_repair_files_verified_unchanged": len(historical_hashes),
            "original_score_writes": 0,
            "freeze_test_actions": 0,
            "artifacts": {
                name: sha(OUT / name)
                for name in (
                    "ANALYSIS.json",
                    "PROVENANCE.json",
                    "CASE_EVIDENCE.json",
                    "REPORT.html",
                    "SUMMARY.md",
                    "SAMPLES.json",
                    "PROPOSED_SELECTION.json",
                )
            },
        },
    )
    print(
        json.dumps(
            {
                "report": str(OUT / "REPORT.html"),
                "selection": {m: s["proposed_primary"] for m, s in selection.items()},
                "all_rows_score_complete": report["all_rows_score_complete"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run only after overlay schema/records are confirmed complete",
    )
    parser.add_argument(
        "--rejudge-root",
        type=Path,
        help="Authorized second-attempt root; output goes to its analysis/ and repair history stays read-only",
    )
    parser.add_argument("--label", choices=("preliminary", "final"), default="preliminary")
    args = parser.parse_args()
    if not args.run:
        parser.error("Explicit --run is required after overlay schema confirmation")
    analyze(args.label, args.rejudge_root)
