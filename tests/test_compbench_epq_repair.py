import json

import pytest

from samtok_benchmark.external_compbench.epq_repair.syntax import recover


def fields(e=4):
    return {
        k: {"score": score, "evidence": 'Visible text includes "quotes", braces } and commas.'}
        for k, score in (("E", e), ("P", 3), ("Q", 4))
    }


def response(text, finish="stop"):
    return {"text": text, "finish_reason": finish}


@pytest.mark.parametrize("e", [0, 1, 2, 3, 4])
def test_recovery_preserves_all_scores_and_evidence(e):
    value = fields(e)
    malformed = json.dumps(value)[:-1] + ', "" }'
    raw = response("reasoning is not parsed </think>\n```json\n" + malformed + "\n```")
    result = recover(raw)
    assert {k: result["scores"][k] for k in value} == value
    assert result["scores"]["all_edit_pass"] == (e == 4)
    start, end = result["removed_span"]
    assert result["removed_text"] == malformed[start:end]
    assert result["corrected_json"] == malformed[:start] + malformed[end:]
    assert json.loads(result["corrected_json"]) == value
    assert raw["text"].endswith(malformed + "\n```")


def test_ambiguous_or_unfinished_answers_are_rejected():
    good = json.dumps(fields())
    candidates = [
        response(good),
        response(good[:-1] + ',""}', "length"),
        response(good[:-1] + ',"extra"}'),
        response(good[:-1] + ',"":0}'),
        response(good[:-1] + ',"E":{"score":0,"evidence":"other"},""}'),
        response(good[:-1] + ',"E":0}'),
        response('{"E":{"score":4,"evidence":"ok",""}}'),
        response(json.dumps({"E": fields()["E"], "P": fields()["P"]})[:-1] + ',""}'),
    ]
    for candidate in candidates:
        with pytest.raises(ValueError):
            recover(candidate)
    for invalid in (True, 2.5, 5, None):
        value = fields(invalid)
        with pytest.raises(ValueError):
            recover(response(json.dumps(value)[:-1] + ',""}'))


def test_same_value_scalar_summaries_and_notes_keep_the_complete_objects():
    value = fields(2)
    complete = json.dumps(value)
    variants = [
        complete[:-1] + ',"E":2,"P":3,"Q":4}',
        complete[:-1] + ',"E_note":"additional explanation"}',
        complete[:-1] + ',"}',
    ]
    for text in variants:
        recovered = recover(response(text))
        assert {k: recovered["scores"][k] for k in value} == value
    with pytest.raises(ValueError, match="Conflicting"):
        recover(response(complete[:-1] + ',"E":3}'))
    with pytest.raises(ValueError, match="Unsupported"):
        recover(response(complete[:-1] + ',"E_revised":4}'))
    note = recover(response(variants[1]))
    assert note["retained_auxiliary_notes"] == {"E_note": "additional explanation"}


def test_same_statistics_as_frozen_report_and_no_changes_to_good_cases(tmp_path):
    from samtok_benchmark.external_compbench.epq_repair.run import per_case
    from samtok_benchmark.external_compbench.epq_repair.statistics import aggregate
    from samtok_benchmark.external_compbench.vlm_judge.common import digest, read, save
    from samtok_benchmark.external_compbench.vlm_judge.report import report
    from samtok_benchmark.external_compbench.vlm_judge.rubric import fingerprint
    from samtok_benchmark.external_compbench.vlm_judge.worker import effective

    cases = [
        {
            "case_id": str(i),
            "task": "multi_object_add" if i < 2 else "multi_object_remove",
            "cluster": "a" if i % 2 else "b",
        }
        for i in range(4)
    ]
    bindings = [
        {"model": m, "case_id": c["case_id"], "request_key": m + c["case_id"]}
        for m in ("sitedit", "qwen21")
        for c in cases
    ]
    plan = {
        "cases": cases,
        "models": ["sitedit", "qwen21"],
        "bindings": bindings,
        "bootstrap": {"seed": 20261110, "replicates": 100},
        "configuration": {"rubric": fingerprint()},
    }
    plan["digest"] = digest(plan)
    bundle = tmp_path / "bundle"
    save(bundle / "PLAN.json", plan)
    root = tmp_path / "original"
    save(
        root / "CONFIGURATION.json",
        {"plan_digest": plan["digest"], "identity": "i", "smoke": False},
    )
    records, raw_answers = {}, {}
    for i, b in enumerate(bindings):
        key = b["request_key"]
        text = json.dumps(fields(i % 5))
        if i == 7:
            text = text[:-1] + ',""}'
        raw = {"identity": "i", "request_key": key, "answer": response(text)}
        record = effective(raw, "i", key)
        for kind, obj in (
            ("admissions", {"identity": "i", "request_key": key}),
            ("raw", raw),
            ("effective", record),
        ):
            save(root / kind / f"{key}.json", obj)
        records[key], raw_answers[key] = record, raw["answer"]
    report(bundle, root, tmp_path / "frozen-report")
    original = read(tmp_path / "frozen-report/REPORT.json")
    rows = per_case(plan, records)
    assert rows == original["per_case"]
    stats = aggregate(rows, plan)
    assert all(stats[k] == original[k] for k in stats)
    key = bindings[-1]["request_key"]
    records[key] = {"status": "scored", "scores": recover(raw_answers[key])["scores"]}
    updated = per_case(plan, records)
    assert updated[:-1] == rows[:-1]
    result = aggregate(updated, plan)
    assert result["bootstrap"] == stats["bootstrap"]
    assert all(x["complete"] for x in result["rows"])
    assert all(a == b for a, b in zip(stats["rows"], result["rows"]) if a["complete"])
