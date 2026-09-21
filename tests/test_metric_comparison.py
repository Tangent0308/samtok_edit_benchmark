import pytest
from evaluation.common import BASELINE_VISUAL_PROTOCOL
from evaluation.metrics.compare import cohorts, interval


def record(method,index,cohort='full656',score=4,setting='text_only'):
    return {'sample':{'method':method,'eval_index':index,'setting':setting,
                      'protocol':BASELINE_VISUAL_PROTOCOL,'cohort':cohort},'scores':{'edit':score}}


def test_comparison_matches_coverage_and_rejects_other_protocols():
    rows=[record('qwen21',0),record('qwen21',1),record('replan_qwen',0),record('replan_qwen',1),
          record('qwen',1,cohort='subset')]
    groups=cohorts(rows)
    assert len(groups['current_full656'])==4
    assert len(groups['current_common'])==3
    assert {r['sample']['eval_index'] for r in groups['current_common']}=={1}
    rows[0]['sample']['protocol']='not_the_benchmark_protocol'
    with pytest.raises(ValueError):cohorts(rows)


def test_interval_resamples_cases_not_settings():
    rows=[record('qwen21',i,score=i%5) for i in range(10)]
    duplicated=[dict(r,sample=dict(r['sample'],setting=s)) for r in rows for s in ('text_only','mask_annotation','box_annotation','point_annotation')]
    assert interval(rows,'edit')==interval(duplicated,'edit')
    assert interval([record('qwen21',1)],'edit')==[4,4]
