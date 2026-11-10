"""Separate method outcomes from engineering faults in immutable correction records.

Only run control uses this module. It reads the write-once records produced by the
frozen workers and never changes them, retries a request or substitutes an output.

* ``completed``: Pass1 returned an ordered U1..UK request (2–5 units) bound to the
  original public instruction, S2 rendered every unit with the native numbered
  template, and official scoring produced metrics.
* ``native_failure``: the method answered normally but the request cannot be
  completed. The only case allowed here is the user-approved native enumeration
  returning an answer that the frozen validator rejects (for example one collective
  target). The saved raw answer must reproduce exactly the recorded error, S2 must be
  recorded as ``blocked_dependency`` without an editor call, and scoring as
  ``generation_failed`` without metrics.
* ``engineering_failure``: anything else (missing or unreadable records, load/CUDA
  errors, fatal flags, S2 or scorer exceptions, inconsistent bindings). These stop
  the smoke gate and are reported explicitly after formal inference.
"""

from collections import Counter
import json
from pathlib import Path

DEPENDENCY_ERROR = "Previous native stage failed; no editor call made"


def _read(path):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return {"status": "unreadable"}


def _native_enumeration_failure(row, stage_dir, tokens):
    """True only if the saved native answer reproduces the recorded validation error."""
    from .adapters import parse_enumeration

    if row["mode"] != "native_enumeration" or tokens.get("fatal"):
        return False, "not an authorized native enumeration failure"
    extra = _read(stage_dir / "enumeration.json")
    if not extra or not isinstance(extra.get("raw"), str):
        return False, "enumeration.json with the raw native answer is missing"
    if extra.get("prompt", "").rsplit("Instruction: ", 1)[-1] != row["instruction"]:
        return False, "enumeration prompt does not carry the original public instruction"
    if (stage_dir / "request.json").exists():
        return False, "a grounding request exists although enumeration failed"
    try:
        parse_enumeration(extra["raw"])
    except ValueError as error:
        if repr(error) != tokens.get("error"):
            return False, f"recorded error {tokens.get('error')!r} differs from {error!r}"
        return True, repr(error)
    return False, "the saved enumeration is valid, so the failure is not a native outcome"


def _check_units(row, native):
    units = native.get("units") or []
    if not 2 <= len(units) <= 5:
        return "Pass1 record does not hold 2–5 units"
    if [u.get("id") for u in units] != [f"U{i}" for i in range(1, len(units) + 1)]:
        return "Pass1 units are not ordered U1..UK"
    if native.get("original_instruction") != row["instruction"]:
        return "Pass1 record is not bound to the original public instruction"
    instructions = [u.get("instruction") for u in units]
    if not all(isinstance(s, str) and s for s in instructions):
        return "a Pass1 unit has no instruction"
    if row["mode"] == "text" and instructions != row["units"]:
        return "Pass1 units differ from the frozen text decomposition"
    for unit in units:
        if unit.get("token") is None and unit.get("source") != "fallback_text":
            return f"{unit['id']} has neither a region code nor a recorded fallback"
    return None


def _check_edit(units, edit):
    placement = edit.get("placement") or {}
    if [u.get("id") for u in placement.get("units", [])] != [u["id"] for u in units]:
        return "S2 placement does not list every Pass1 unit in order"
    prompt = (edit.get("native") or {}).get("conditioning_prompt") or ""
    lines = prompt.split("\n")
    for i, unit in enumerate(units, 1):
        line = next((x for x in lines if x.startswith(f"U{i}: ")), None)
        if line is None:
            return f"S2 prompt has no line for U{i}"
        if unit["token"] and unit["token"] not in line:
            return f"U{i} region code is not on its own instruction line"
        others = [u["token"] for u in units if u["token"] and u["id"] != unit["id"]]
        if any(t in line for t in others):
            return f"U{i} line carries another unit's region code"
    if not edit.get("output_image"):
        return "S2 record has no output image"
    return None


def classify(row, run, scores):
    """Outcome of one planned request from its immutable tokens/edit/score records."""
    cid = row["case_id"]
    tokens_dir = Path(run) / "sitedit/tokens" / cid
    tokens = _read(tokens_dir / "result.json")
    edit = _read(Path(run) / "sitedit/edit" / cid / "result.json")
    score = _read(Path(scores) / "sitedit" / cid / "local.json")
    out = {"case_id": cid, "mode": row["mode"]}

    def fault(stage, reason):
        return {**out, "outcome": "engineering_failure", "stage": stage, "reason": reason}

    for stage, record in (("tokens", tokens), ("edit", edit), ("score", score)):
        if record is None:
            return fault(stage, "record is missing")
        if record.get("status") == "unreadable":
            return fault(stage, "record is not valid JSON")
    if tokens["status"] == "completed":
        problem = _check_units(row, tokens.get("native") or {})
        if problem:
            return fault("tokens", problem)
        units = tokens["native"]["units"]
        if edit["status"] != "completed":
            return fault("edit", f"S2 {edit['status']}: {edit.get('error')}")
        problem = _check_edit(units, edit)
        if problem:
            return fault("edit", problem)
        if score["status"] != "completed" or not score.get("metrics"):
            return fault("score", f"scoring {score['status']}: {score.get('error')}")
        return {
            **out,
            "outcome": "completed",
            "units": [
                {"id": u["id"], "instruction": u["instruction"], "token": u["token"]}
                for u in units
            ],
            "coded_units": sum(u["token"] is not None for u in units),
            "inference_seconds": tokens["inference_seconds"] + edit["inference_seconds"],
            "peak_reserved_bytes": max(
                tokens["peak_gpu_reserved_bytes"], edit["peak_gpu_reserved_bytes"]
            ),
        }
    if tokens["status"] != "failed":
        return fault("tokens", f"unexpected status {tokens['status']}")
    native, reason = _native_enumeration_failure(row, tokens_dir, tokens)
    if not native:
        return fault("tokens", f"{tokens.get('error')} ({reason})")
    if (
        edit["status"] != "blocked_dependency"
        or edit.get("fatal")
        or DEPENDENCY_ERROR not in (edit.get("error") or "")
        or edit.get("output_image")
    ):
        return fault("edit", "S2 is not recorded as a dependency failure of the native answer")
    if (
        score["status"] != "generation_failed"
        or score.get("generation_status") != "blocked_dependency"
        or score.get("metrics") is not None
    ):
        return fault("score", "scoring is not recorded as generation_failed without metrics")
    return {
        **out,
        "outcome": "native_failure",
        "stage": "tokens",
        "error": reason,
        "downstream": {"edit": edit["status"], "score": score["status"]},
    }


def summarize(plan, run, scores, case_ids=None):
    rows = {r["case_id"]: r for r in plan["cases"]}
    items = [classify(rows[c], run, scores) for c in (case_ids or plan["case_ids"])]
    done = [i for i in items if i["outcome"] == "completed"]
    return {
        "expected": len(items),
        "counts": dict(Counter(i["outcome"] for i in items)),
        "completed": len(done),
        "native_failures": [i for i in items if i["outcome"] == "native_failure"],
        "engineering_failures": [i for i in items if i["outcome"] == "engineering_failure"],
        "cases": items,
        # Timing and memory use completed requests only; failures carry no such fields.
        "inference_seconds": [i["inference_seconds"] for i in done],
        "peak_reserved_bytes": [i["peak_reserved_bytes"] for i in done],
    }


def smoke_gate(summary):
    """Engineering faults stop the run; a recorded native failure does not."""
    if summary["engineering_failures"]:
        raise RuntimeError(
            "Smoke has engineering failures; formal inference has not started: "
            + json.dumps(summary["engineering_failures"], ensure_ascii=False)
        )
    if not summary["completed"]:
        raise RuntimeError(
            "No smoke request completed end to end; formal inference has not started"
        )
    if summary["completed"] + len(summary["native_failures"]) != summary["expected"]:
        raise RuntimeError("Smoke outcomes do not cover every fixed smoke request")
