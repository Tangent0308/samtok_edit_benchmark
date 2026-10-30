import json

import pytest

from samtok_benchmark.ifbench.judge_repair import Unrecoverable, recover


def field(score=4, evidence="literal source/output observation", passed=True):
    return json.dumps({"score": score, "pass": passed, "evidence": evidence})


def answer(unit):
    return '{"units":[' + unit + '],"global_P":' + field() + ',"global_Q":' + field() + "}"


def test_same_unit_anonymous_wrapper_and_fixed_thresholds():
    raw = answer(
        '{"id":"U1","E":'
        + field(3, passed=True)
        + ',{"id":"U1","P":'
        + field()
        + ',"Q":'
        + field()
        + "}}"
    )
    scores, audit = recover(raw, ["U1"])
    assert scores["units"][0]["E"]["score"] == 3
    assert scores["units"][0]["E"]["pass"] is False
    assert len(audit) == 5


def test_single_anonymous_atom_has_unique_missing_dimension():
    raw = answer(
        '{"id":"U1",' + field(2, passed=False) + ',"P":' + field() + ',"Q":' + field() + "}"
    )
    scores, audit = recover(raw, ["U1"])
    assert scores["units"][0]["E"]["score"] == 2
    assert any(a["rule"] == "single_anonymous_atom_and_single_missing_metric" for a in audit)


def test_multiple_anonymous_atoms_cannot_be_assigned_by_order_or_prose():
    raw = answer(
        '{"id":"U1","E":'
        + field()
        + ","
        + field(2, evidence="Preservation", passed=False)
        + ","
        + field(3, evidence="Quality")
        + "}"
    )
    with pytest.raises(Unrecoverable, match="Ambiguous unlabeled"):
        recover(raw, ["U1"])


def test_metric_id_double_colon_wrapper_is_not_a_unit():
    raw = answer(
        '{"id":"U1","E":'
        + field()
        + ',"P":'
        + field()
        + ',{"id":"Q":'
        + field(2, passed=False)
        + "}}"
    )
    scores, audit = recover(raw, ["U1"])
    assert scores["units"][0]["Q"]["score"] == 2
    assert any(a["rule"] == "explicit_metric_id_double_colon" for a in audit)


def test_conflicting_duplicate_numbers_are_rejected():
    raw = answer(
        '{"id":"U1","E":'
        + field()
        + ',{"id":"U1","E":'
        + field(2)
        + ',"P":'
        + field()
        + ',"Q":'
        + field()
        + "}}"
    )
    with pytest.raises(Unrecoverable, match="Conflicting duplicate"):
        recover(raw, ["U1"])


def test_equal_duplicate_numbers_preserve_both_literal_evidence_strings():
    raw = answer(
        '{"id":"U1","E":'
        + field(evidence="First original evidence")
        + ',{"id":"U1","E":'
        + field(evidence="Second original evidence")
        + ',"P":'
        + field()
        + ',"Q":'
        + field()
        + "}}"
    )
    scores, audit = recover(raw, ["U1"])
    assert (
        scores["units"][0]["E"]["evidence"] == "First original evidence\n\nSecond original evidence"
    )
    assert sum(a["field"] == "U1.E" for a in audit) == 2


def test_missing_unit_metric_cannot_borrow_global_or_other_unit_score():
    raw = answer('{"id":"U1","E":' + field() + ',"P":' + field() + "}")
    with pytest.raises(Unrecoverable, match="Missing="):
        recover(raw, ["U1"])


def test_missing_final_score_cannot_borrow_thinking():
    raw = answer('{"id":"U1","E":' + field() + ',"P":' + field() + "}")
    with pytest.raises(Unrecoverable, match="Missing="):
        recover('<think>"Q":' + field() + "</think>" + raw, ["U1"])


def test_python_expression_is_not_executed_or_selected():
    raw = answer(
        '{"id":"U1","E":'
        + field()
        + " if False else "
        + field()
        + ',"P":'
        + field()
        + ',"Q":'
        + field()
        + "}"
    )
    with pytest.raises(Unrecoverable, match="Invalid lexical"):
        recover(raw, ["U1"])


def test_unquoted_metric_key_and_missing_pass_keep_literal_numbers():
    raw = answer(
        '{"id":"U1","E":'
        + field()
        + ',P: {"score":2,"evidence":"Existing evidence"},"Q":'
        + field()
        + "}"
    )
    scores, _ = recover(raw, ["U1"])
    assert scores["units"][0]["P"] == {"score": 2, "pass": False, "evidence": "Existing evidence"}
