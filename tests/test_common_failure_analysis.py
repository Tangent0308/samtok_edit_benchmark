from evaluation.analyze_common_failures import select, summarize_case


def record(
    *,
    index=7,
    method="qwen",
    setting="text_only",
    status="ok",
    edit=4,
    preservation=3,
    quality=3,
):
    return {
        "status": status,
        "scores": {
            "edit": edit,
            "preservation": preservation,
            "quality": quality,
        },
        "sample": {
            "eval_index": index,
            "case_id": f"case-{index}",
            "source_dataset": "fixture",
            "edit_type": "remove",
            "regions": [{}],
            "instruction": "remove the target",
            "method": method,
            "setting": setting,
        },
    }


def test_summary_separates_edit_success_from_strict_success():
    rows = [
        record(preservation=2),
        record(method="flux", setting="mask_annotation", edit=2),
    ]
    summary = summarize_case(rows)
    assert summary["edit_successes"] == 1
    assert summary["strict_successes"] == 0
    assert summary["strict_outputs"] == []
    assert summary["method_best_edit"]["qwen"] == 4
    assert summary["method_best_edit"]["qwen21"] is None


def test_summary_handles_annotation_conflicts_without_scores():
    row = record(status="annotation_conflict", edit=None, preservation=None, quality=None)
    summary = summarize_case([row])
    assert summary["usable_records"] == 0
    assert summary["edit_mean"] is None
    assert summary["edit_max"] is None
    assert summary["status"] == {"annotation_conflict": 1}


def test_selection_keeps_only_complete_cases_and_exposes_review_tiers():
    base = {
        "eval_index": 7,
        "usable_records": 20,
        "edit_max": 4,
        "edit_successes": 3,
        "strict_successes": 3,
        "method_strict_successes": {
            "qwen": 3,
            "flux": 0,
            "qwen21": 0,
            "replan_qwen": 0,
            "replan_flux": 0,
        },
        "strict_outputs": [
            {"method": "qwen", "setting": setting, "scores": {}}
            for setting in ("text_only", "mask_annotation", "box_annotation")
        ],
        "setting_best_edit": {
            "text_only": 4,
            "mask_annotation": 1,
            "box_annotation": 0,
            "point_annotation": 2,
        },
    }
    incomplete = {**base, "eval_index": 8, "usable_records": 19, "strict_successes": 0}
    high_risk = {
        **base,
        "eval_index": 9,
        "strict_successes": 5,
        "method_strict_successes": {
            "qwen": 3,
            "flux": 0,
            "qwen21": 2,
            "replan_qwen": 0,
            "replan_flux": 0,
        },
        "strict_outputs": [
            {"method": method, "setting": "text_only", "scores": {}}
            for method in ("qwen", "qwen", "qwen", "qwen21", "qwen21")
        ],
        "setting_best_edit": dict.fromkeys(
            ("text_only", "mask_annotation", "box_annotation", "point_annotation"), 4
        ),
    }
    candidates = select([base, incomplete, high_risk])
    assert candidates["at_most_3_strict_successes"] == [7]
    assert candidates["at_most_4_strict_successes"] == [7]
    assert candidates["at_most_2_strict_successes"] == []
    assert candidates["strict_at_least_5_in_at_most_2_methods"] == [9]
    assert candidates["strict_at_least_5_in_one_setting"] == [9]
    assert candidates["high_risk_concentrated_strict_success"] == [9]
    assert candidates["shared_setting_edit_at_most_1"] == {
        "text_only": [],
        "mask_annotation": [7],
        "box_annotation": [7],
        "point_annotation": [],
    }
