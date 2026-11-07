import pytest

from samtok_benchmark.external_complexbench_edit.score import aggregate


def test_official_dependency_score_keeps_order():
    assert aggregate([5, 0, 5], "two-chain") == 0.5
    assert aggregate([5, 5, 0], "two-chain") == 0.5
    assert aggregate([5, 0, 5], "three-chain") == 0
    assert aggregate([5, 0, 5], "COCO-three-obj") == pytest.approx(2/3)


def test_missing_or_invalid_units_are_not_silently_averaged():
    with pytest.raises(ValueError):
        aggregate([5, 5], "COCO-three-obj")
    with pytest.raises(ValueError):
        aggregate([5, 6, 5], "three-chain")
