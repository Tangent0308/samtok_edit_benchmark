from samtok_benchmark.ifbench.dev_review_queue import state_for


def test_unfinished_judge_does_not_trigger_model_review():
    r = state_for("m", {"a", "b"}, {"a": "scored"}, {"generated": 2})
    assert not r["judge_attempts_complete"]
    assert not r["score_complete"]
    assert r["judge_counts"]["pending"] == 1


def test_judge_failures_allow_diagnostic_review_but_block_selection():
    r = state_for("m", {"a", "b"}, {"a": "scored", "b": "judge-failed"}, {"generated": 2})
    assert r["judge_attempts_complete"] and not r["score_complete"]
    assert r["state"] == "ready_with_judge_failures"


def test_generation_failure_is_preserved_separately_from_judge_failure():
    r = state_for("m", {"a"}, {"a": "scored"}, {"generated": 1, "failed": 1})
    assert r["score_complete"]
    assert r["generation_counts"]["failed"] == 1
    assert r["judge_counts"]["judge-failed"] == 0
