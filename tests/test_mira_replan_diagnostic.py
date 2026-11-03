import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    'mira_replan_diagnostic', Path(__file__).resolve().parents[1] / 'scripts/diagnose_mira_replan_failure.py')
DIAG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAG)


def test_repair_requires_only_invalid_coordinates_to_change():
    old = [{'bbox_2d': [5, 5, 9, 9], 'hint': 'recolor'},
           {'bbox_2d': [10, 5, 10, 15], 'hint': 'remove'}]
    fixed = [old[0], {'bbox_2d': [10, 5, 20, 15], 'hint': 'remove'}]
    DIAG.validate_correction(old, fixed, 'keep', 'keep', {1}, [30, 30])
    changed = [dict(old[0], hint='replace'), fixed[1]]
    with pytest.raises(ValueError, match='already-valid region'):
        DIAG.validate_correction(old, changed, 'keep', 'keep', {1}, [30, 30])
    with pytest.raises(ValueError, match='hint or another region field'):
        DIAG.validate_correction(old, [old[0], dict(fixed[1], hint='replace')], 'keep', 'keep', {1}, [30, 30])
    with pytest.raises(ValueError, match='global instruction'):
        DIAG.validate_correction(old, fixed, 'keep', 'change', {1}, [30, 30])


def test_invalid_and_outside_boxes_remain_rejected():
    assert DIAG.invalid_boxes([{'bbox_2d': [630, 65, 630, 417]}], [832, 1248])[0]['reason'] == 'non-positive area'
    assert DIAG.invalid_boxes([{'bbox_2d': [1, 1, 40, 30]}], [30, 30])[0]['reason'] == 'outside public canvas'
    for box in ([1, 2, float('nan'), 4], [True, 2, 3, 4], [1, 2, 3]):
        assert DIAG.invalid_boxes([{'bbox_2d': box}], [30, 30])


def test_single_region_projection_cannot_rewrite_other_edits():
    old = [{'bbox_2d': [5, 5, 9, 9], 'hint': 'recolor'},
           {'bbox_2d': [10, 5, 10, 15], 'hint': 'remove'}]
    response = '<think>original</think><gen_image>keep</gen_image><region>[]</region>'
    proposed = [{'bbox_2d': [10, 5, 20, 15], 'hint': 'remove'}]
    text, merged = DIAG.merge_single_region(response, old, proposed, {1}, [30, 30])
    assert merged[0] == old[0] and merged[1] == proposed[0]
    assert old[1]['bbox_2d'] == [10, 5, 10, 15]
    assert text.startswith('<think>original</think><gen_image>keep</gen_image>')
    with pytest.raises(ValueError, match='changed the requested operation'):
        DIAG.merge_single_region(response, old, [dict(proposed[0], hint='replace')], {1}, [30, 30])
    with pytest.raises(ValueError, match='exactly one'):
        DIAG.merge_single_region(response, old, proposed * 2, {1}, [30, 30])
