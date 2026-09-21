"""Publication must preserve manual findings and reject unfinished runs."""
import pytest

from evaluation.metrics.publish_results import replace_section, validate_complete


def test_update_preserves_case_study_and_is_idempotent():
    body = 'intro\n<!-- SCORES_BEGIN -->\npending\n<!-- SCORES_END -->\nmanual cases'
    result = replace_section(body, 'SCORES', 'complete scores')
    assert result.startswith('intro\n')
    assert result.endswith('\nmanual cases')
    assert 'pending' not in result
    assert replace_section(result, 'SCORES', 'complete scores') == result
    with pytest.raises(ValueError):
        replace_section('manual cases', 'SCORES', 'complete scores')


def test_publication_requires_all_systems_and_valid_records():
    result = {
        'tables': {'current_full656': {
            method: {'cases': 656, 'n': 2624}
            for method in ('qwen', 'flux', 'qwen21', 'replan_qwen', 'replan_flux')
        }},
        'status': {'ok': 13100, 'annotation_conflict': 20},
    }
    validate_complete(result)
    result['status'] = {'ok': 13099, 'annotation_conflict': 20, 'judge_error': 1}
    with pytest.raises(ValueError):
        validate_complete(result)
    result['status'] = {'ok': 13100, 'annotation_conflict': 20}
    result['tables']['current_full656']['flux']['n'] = 60
    with pytest.raises(ValueError):
        validate_complete(result)
