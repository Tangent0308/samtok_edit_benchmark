"""Authorized deterministic recovery of existing Judge answers, without inference.

Only complete, uniquely attributed score/evidence atoms from the final answer
are retained. Structural wrappers may be broken; missing or conflicting score
atoms are never inferred. Raw records and the original canonical parser stay
immutable. This module writes a separately versioned overlay with provenance.
"""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import time

from samtok_benchmark.io import sha256_file, write_json
from samtok_benchmark.v2.judge import parse
from .dev_plan import ROOT, read

POLICY = "ifbench.deterministic-score-atoms.v1"
OUT = ROOT / "judge_repair_v1"


class Unrecoverable(ValueError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Unrecoverable(f"Duplicate JSON property inside score atom: {key}")
        result[key] = value
    return result


def lex(raw):
    decoder = json.JSONDecoder(object_pairs_hook=unique_object)
    tokens = []
    i = 0
    while i < len(raw):
        if raw[i].isspace():
            i += 1
            continue
        if raw[i] in "{}[]:,":
            tokens.append((raw[i], raw[i], i, i + 1))
            i += 1
            continue
        bare = re.match(r"(E|P|Q|global_P|global_Q)\s*(?=:)", raw[i:])
        if bare:
            end = i + len(bare[1])
            tokens.append(("string", bare[1], i, end))
            i = end
            continue
        try:
            value, end = decoder.raw_decode(raw, i)
        except (ValueError, TypeError) as exc:
            raise Unrecoverable(f"Invalid lexical value at offset {i}: {exc}") from exc
        if isinstance(value, (dict, list)):
            raise Unrecoverable("Unexpected aggregate token")
        tokens.append(("string" if isinstance(value, str) else "value", value, i, end))
        i = end
    return tokens


def recover(text, unit_ids):
    final = text.rsplit("</think>", 1)[-1].strip()
    if final.startswith("```"):
        final = final.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    start = final.find("{")
    if start < 0:
        raise Unrecoverable("No final answer object")
    raw = final[start:]
    tokens = lex(raw)
    stack, objects, owners = [], {}, {}
    for index, token in enumerate(tokens):
        owners[index] = stack[-1] if stack else None
        if token[0] == "{":
            objects[index] = {"parent": owners[index], "start": token[2], "end": None, "ids": []}
            stack.append(index)
        elif token[0] == "}":
            if not stack:
                raise Unrecoverable("Unmatched closing object")
            objects[stack.pop()]["end"] = token[3]
    # Unclosed outer wrappers are harmless only if all actual score atoms below
    # are balanced, complete and uniquely assigned. No atom is auto-completed.
    id_tokens = []
    for i in range(len(tokens) - 2):
        if (
            tokens[i][:2] == ("string", "id")
            and tokens[i + 1][0] == ":"
            and tokens[i + 2][0] == "string"
        ):
            owner = owners[i]
            if owner is None:
                raise Unrecoverable("Unit id outside any object")
            uid = tokens[i + 2][1]
            if uid not in set(unit_ids) | {"global_P", "global_Q", "E", "P", "Q"}:
                raise Unrecoverable(f"Unknown id: {uid}")
            objects[owner]["ids"].append(uid)
            id_tokens.append((i, owner, uid))

    def unit_owner(object_index):
        while object_index is not None:
            ids = objects[object_index]["ids"]
            if ids:
                if len(set(ids)) != 1:
                    raise Unrecoverable(f"Ambiguous enclosing unit ids: {ids}")
                uid = ids[0]
                if uid in ("E", "P", "Q"):
                    object_index = objects[object_index]["parent"]
                    continue
                if uid not in unit_ids:
                    raise Unrecoverable("Unit metric enclosed by global id")
                return uid
            object_index = objects[object_index]["parent"]
        raise Unrecoverable("Score atom has no enclosing unit id")

    occurrences = defaultdict(list)
    consumed = []
    audit = []

    def add(label, object_index, rule, uid=None, drop_id=False):
        obj = objects[object_index]
        if obj["end"] is None:
            raise Unrecoverable(f"Incomplete score atom: {label}")
        a, b = obj["start"], obj["end"]
        try:
            value = json.loads(raw[a:b], object_pairs_hook=unique_object)
        except ValueError as exc:
            raise Unrecoverable(f"Invalid score atom {label}: {exc}") from exc
        if drop_id:
            value = {k: v for k, v in value.items() if k != "id"}
        if set(value) - {"score", "pass", "evidence"}:
            raise Unrecoverable(f"Unexpected score atom properties: {label}")
        if (
            type(value.get("score")) is not int
            or not 0 <= value["score"] <= 4
            or not isinstance(value.get("evidence"), str)
            or not value["evidence"].strip()
        ):
            raise Unrecoverable(f"Missing/invalid numeric score or evidence: {label}")
        if "pass" in value and type(value["pass"]) is not bool:
            raise Unrecoverable(f"Non-boolean pass field: {label}")
        if label in ("global_P", "global_Q"):
            name = label
        else:
            name = f"{uid or unit_owner(obj['parent'])}.{label}"
        threshold = 4 if label == "E" else 3
        normalized = {
            "score": value["score"],
            "pass": value["score"] >= threshold,
            "evidence": value["evidence"].strip(),
        }
        occurrences[name].append(normalized)
        consumed.append((a, b))
        audit.append(
            {
                "field": name,
                "rule": rule,
                "final_answer_span": [a + start, b + start],
                "literal_atom": raw[a:b],
                "original_pass": value.get("pass"),
                "pass_present": "pass" in value,
                "derived_pass": normalized["pass"],
                "score_unchanged": True,
                "evidence_unchanged_except_trim": True,
            }
        )

    for i in range(len(tokens) - 2):
        if tokens[i][0] == "string" and tokens[i][1] in ("E", "P", "Q", "global_P", "global_Q"):
            if i >= 2 and tokens[i - 2][:2] == ("string", "id") and tokens[i - 1][0] == ":":
                continue
            if tokens[i + 1][0] == ":" and tokens[i + 2][0] == "{":
                add(tokens[i][1], i + 2, "explicit_metric_key_and_nearest_enclosing_id")
    for i, owner, uid in id_tokens:
        if uid in ("global_P", "global_Q"):
            # Alternate root/global representation: {"id":"global_P","score":...}.
            add(uid, owner, "explicit_global_id_score_object", drop_id=True)
        elif uid in ("E", "P", "Q"):
            if i + 4 < len(tokens) and tokens[i + 3][0] == ":" and tokens[i + 4][0] == "{":
                add(uid, i + 4, "explicit_metric_id_double_colon")
            else:
                add(uid, owner, "metric_id_in_enclosing_unit_score_object", drop_id=True)
        elif i + 4 < len(tokens) and tokens[i + 3][0] == ":" and tokens[i + 4][0] == "{":
            # Narrow typo: {"id":"U2": {score atom}, "P":..., "Q":...}.
            # The only unlabeled atom follows the id immediately; labeled P/Q
            # must both exist below and E must be otherwise absent.
            add("E", i + 4, "missing_E_key_after_id_double_colon", uid=uid)
    anonymous = defaultdict(list)
    for index, obj in objects.items():
        if obj["end"] is None or (obj["start"], obj["end"]) in consumed:
            continue
        try:
            value = json.loads(raw[obj["start"] : obj["end"]], object_pairs_hook=unique_object)
        except ValueError:
            continue
        if (
            isinstance(value, dict)
            and "score" in value
            and set(value) <= {"score", "pass", "evidence"}
        ):
            uid = unit_owner(obj["parent"])
            anonymous[uid].append(index)
    for uid, blocks in anonymous.items():
        missing = [m for m in "EPQ" if f"{uid}.{m}" not in occurrences]
        if len(blocks) != 1 or len(missing) != 1:
            raise Unrecoverable(
                f"Ambiguous unlabeled score atoms: {uid}, blocks={len(blocks)}, missing={missing}"
            )
        add(missing[0], blocks[0], "single_anonymous_atom_and_single_missing_metric", uid=uid)
    fields = {}
    for name, values in occurrences.items():
        if any(value["score"] != values[0]["score"] for value in values[1:]):
            raise Unrecoverable(f"Conflicting duplicate score atoms: {name}")
        # Same numeric assessment repeated with different evidence: preserve
        # every distinct literal evidence string, in original source order.
        evidence = list(dict.fromkeys(value["evidence"] for value in values))
        fields[name] = {**values[0], "evidence": "\n\n".join(evidence)}
    required = {f"{uid}.{metric}" for uid in unit_ids for metric in "EPQ"} | {
        "global_P",
        "global_Q",
    }
    if set(fields) != required:
        raise Unrecoverable(
            f"Missing={sorted(required - set(fields))}; extra={sorted(set(fields) - required)}"
        )
    # Every literal numeric score must belong to exactly one recovered atom.
    # This prevents silently ignoring an alternative/conflicting assessment.
    for i, token in enumerate(tokens[:-1]):
        if token[:2] == ("string", "score") and tokens[i + 1][0] == ":":
            if sum(a <= token[2] < b for a, b in consumed) != 1:
                raise Unrecoverable("Unclaimed or overlapping numeric score atom")
    # An inferred E slot must be the sole E occurrence and have explicit P/Q.
    for atom in audit:
        if atom["rule"] == "missing_E_key_after_id_double_colon":
            uid = atom["field"].split(".")[0]
            if len(occurrences[atom["field"]]) != 1 or any(
                not any(
                    a["field"] == f"{uid}.{m}"
                    and a["rule"] == "explicit_metric_key_and_nearest_enclosing_id"
                    for a in audit
                )
                for m in "PQ"
            ):
                raise Unrecoverable("Unlabeled E slot is not uniquely determined")
    value = {
        "units": [{"id": uid, **{m: fields[f"{uid}.{m}"] for m in "EPQ"}} for uid in unit_ids],
        "global_P": fields["global_P"],
        "global_Q": fields["global_Q"],
    }
    validated, _ = parse(json.dumps(value, ensure_ascii=False), unit_ids)
    return validated, audit


def run():
    from . import dev_judge as canonical

    run_id = read(ROOT / "judge/current.json")["run_id"]
    root = ROOT / "judge" / run_id
    cases = canonical.cases()
    associations = defaultdict(list)
    for binding in read(root / "bindings.json"):
        record = read(Path(binding["record"]))
        associations[binding["key"]].append(record["task"])
    before = {p.name: sha256_file(p) for p in (root / "records").glob("*.json")}
    OUT.mkdir(parents=True, exist_ok=True)
    policy = {
        "policy": POLICY,
        "authorized_by": "直接进行修复，修复后进行完整的分析总结。",
        "run_id": run_id,
        "source_sha256": sha256_file(Path(__file__)),
        "numeric_scores": "copy literal original final-answer integers only",
        "evidence": "copy original final-answer evidence only; whitespace trim allowed",
        "pass": "derive E from score==4; P/Q/global from score>=3",
        "ambiguity": "reject missing/conflicting atoms, unknown ids, unclaimed score atoms",
        "inference_calls": 0,
        "original_records_modified": 0,
        "freeze_authorized": False,
        "test_started": False,
    }
    write_json(OUT / "policy.json", policy)
    counts, per_model = Counter(), defaultdict(Counter)
    original_scored = 0
    failures = []
    for name, original_hash in sorted(before.items()):
        original = read(root / "records" / name)
        if original["status"] != "judge-failed":
            original_scored += original["status"] == "scored"
            continue
        key = original["key"]
        task = associations[key][0]
        unit_ids = [u["id"] for u in cases[task["case_id"]]["units"]]
        result = {
            **original,
            "raw_record_sha256": original_hash,
            "raw_record_path": str(root / "records" / name),
            "original_status": original["status"],
            "original_reason": original.get("reason"),
            "repair_policy": POLICY,
            "repair_source_sha256": policy["source_sha256"],
            "repair_inference_calls": 0,
        }
        try:
            if original["raw_response"]["finish_reason"] != "stop":
                raise Unrecoverable("Non-stop termination")
            scores, audit = recover(original["raw_response"]["text"], unit_ids)
            result.update(status="scored", scores=scores, repair_audit=audit)
            result.pop("reason", None)
            counts["recovered"] += 1
            per_model[task["model"]]["recovered"] += 1
        except (ValueError, KeyError, TypeError) as exc:
            result.update(status="judge-failed", repair_reason=str(exc))
            counts["unrecoverable"] += 1
            per_model[task["model"]]["unrecoverable"] += 1
            failures.append(
                {
                    "key": key,
                    "model": task["model"],
                    "case_id": task["case_id"],
                    "reason": str(exc),
                    "bindings": associations[key],
                }
            )
        write_json(OUT / "records" / name, result)
    assert all(sha256_file(root / "records" / name) == sha for name, sha in before.items())
    write_json(OUT / "original_hashes.json", before)
    summary = {
        "policy": policy,
        "updated_at": time.time(),
        "counts": dict(counts),
        "per_model": {m: dict(c) for m, c in per_model.items()},
        "unrecoverable": failures,
        "original_records_verified": len(before),
        "original_scored_unchanged": original_scored,
    }
    write_json(OUT / "summary.json", summary)
    print(
        json.dumps({k: summary[k] for k in ("counts", "per_model")}, ensure_ascii=False), flush=True
    )


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
