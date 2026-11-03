import importlib.util
from pathlib import Path

import numpy as np

SPEC = importlib.util.spec_from_file_location(
    'mira_audited_report', Path(__file__).resolve().parents[1] / 'scripts/report_mira_audited.py')
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


def test_identical_methods_have_zero_paired_uncertainty():
    a = {'001': [1, 9, 2], '002': [8, 5, 9], '003': [4, 9, 5]}
    b = dict(reversed(list(a.items())))
    report = REPORT.summarize({'qwen21': b, 'sitedit': a}, ['003', '001', '002'], replicates=500)
    pair = report['paired_sitedit_minus_baseline'][0]
    assert pair['delta'] == 0
    assert pair['CI95'] == [0, 0]
    assert pair['population'] == 'full_selected_source_set'


def test_missing_source_is_retained_and_pair_is_explicitly_conditional():
    baseline = {'001': [1, 1, 1], '002': [4, 4, 4]}
    ours = {**baseline, '003': [10, 10, 10]}
    report = REPORT.summarize({'replan': baseline, 'sitedit': ours}, list(ours), replicates=500)
    other, ours_row = report['rows']
    assert (other['scored'], other['total'], other['missing_cases']) == (2, 3, ['003'])
    assert other['Overall_CI95'] is None and other['Overall'] == 2.5
    assert ours_row['Overall'] == 5 and ours_row['Overall_CI95'] is not None
    pair = report['paired_sitedit_minus_baseline'][0]
    assert pair['population'] == 'common_scored_subset'
    assert pair['n_pairs'] == 2 and pair['requested_sources'] == 3
    assert pair['omitted_cases'] == ['003']
    assert pair['delta'] == 0 and pair['CI95'] == [0, 0]


def test_official_formula_aggregates_components_before_overall():
    values = {'sitedit': {'001': [0, 10, 10], '002': [10, 0, 10]}}
    report = REPORT.summarize(values, ['001', '002'], replicates=500)
    assert np.isclose(report['rows'][0]['Overall'], np.sqrt(50))
    subset = REPORT.summarize(values, ['001'], replicates=500)
    assert subset['rows'][0]['Overall'] == 0
    assert subset['rows'][0]['total'] == 1
