"""Two-image judge invariants: score separation, unknowns, evidence and call count."""
import json
from argparse import Namespace
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from evaluation.common import sha256_file
from evaluation.metrics import simple, runner
from evaluation.metrics.report import summarize


def verdict(**changes):
    return dict(edit=4,preservation=4,quality=4,edit_evidence='Both requested objects are removed.',
                preservation_evidence='Unrequested content is unchanged.',quality_evidence='No new defects.',**changes)


def test_scores_separate_completion_from_collateral_changes():
    result=simple.derive(dict(edit=4,preservation=2,quality=4))
    assert result['all_edits_success'] is True
    assert result['strict_success'] is False
    assert simple.derive(dict(edit=0,preservation=4,quality=4))['all_edits_success'] is False
    assert simple.derive(dict(edit=2,preservation=4,quality=4))['strict_success'] is False


def test_unknown_scores_do_not_become_failures():
    assert simple.derive(dict(edit=None,preservation=4,quality=4))['strict_success'] is None
    assert simple.derive(dict(edit=4,preservation=None,quality=4))['strict_success'] is None
    assert simple.derive(dict(edit=0,preservation=None,quality=4))['strict_success'] is False


def test_parser_requires_integer_scores_and_visible_evidence():
    good=verdict()
    assert simple.parse('thought</think>\n```json\n'+json.dumps(good)+'\n```')==good
    for invalid in ('4',True,5,-1):
        with pytest.raises(ValueError):simple.parse(json.dumps({**good,'edit':invalid}))
    for invalid in ({**good,'quality_evidence':''},{k:v for k,v in good.items() if k!='edit'}):
        with pytest.raises(ValueError):simple.parse(json.dumps(invalid))
    with pytest.raises(ValueError):simple.parse(json.dumps(good)+' another answer')


def test_uses_two_true_mask_outlines_without_filling_interiors(tmp_path):
    Image.new('RGB',(100,100),'white').save(tmp_path/'source.png')
    mask=Image.new('L',(100,100),0);draw=ImageDraw.Draw(mask)
    draw.rectangle((30,30,40,70),fill=255);draw.rectangle((30,60,70,70),fill=255)
    mask.save(tmp_path/'mask.png')
    row=dict(source_image=str(tmp_path/'source.png'),output_image=str(tmp_path/'source.png'),
             regions=[dict(mask=str(tmp_path/'mask.png'))])
    views=simple.make_views(row,1048576)
    assert len(views)==2
    assert views[0][1].tobytes()==views[1][1].tobytes()
    assert views[0][1].getpixel((35,50))==(255,255,255)
    assert views[0][1].getpixel((65,40))==(255,255,255)
    assert views[0][1].getpixel((42,50))==simple.COLORS[0]


def test_missing_outputs_fail_but_judge_errors_are_unknown():
    records=[{'status':'missing_output'},{'status':'judge_parse_error'},{'status':'pending'},
             {'status':'ok','scores':simple.derive(dict(edit=4,preservation=4,quality=4))}]
    summary=summarize(records)['strict_success']
    assert (summary['success'],summary['failure'],summary['unknown'])==(1,1,2)
    assert (summary['lower_bound'],summary['upper_bound'])==(.25,.75)


def test_prompt_does_not_leak_model_paths_or_expected_labels():
    row=dict(instruction='replace cat with cup',region_instruction='Replace region_1',
             regions=[dict(mask='secret_method',box=[1,2,10,20])],
             method='secret_method',expected={'strict_success':False})
    text=simple.prompt(row)
    assert 'secret_method' not in text and 'strict_success' not in text


@pytest.mark.parametrize('bad_first',[False,True])
def test_joint_targets_use_one_call_with_format_only_retry(tmp_path,monkeypatch,bad_first):
    source=tmp_path/'source.png';mask=tmp_path/'mask.png'
    Image.new('RGB',(64,64),'white').save(source)
    Image.new('L',(64,64),255).save(mask)
    row=dict(sample_id='case',input_digest='frozen',source_image=str(source),output_image=str(source),
             source_sha256=sha256_file(source),output_sha256=sha256_file(source),
             instruction='Remove both objects',region_instruction='Remove R1 and R2',
             regions=[dict(mask=str(mask),mask_sha256=sha256_file(mask)) for _ in range(2)],
             delivery_status='available',annotation_status='imported_not_human_calibrated')
    manifest=tmp_path/'manifest.jsonl';manifest.write_text(json.dumps(row)+'\n')
    calls=[]
    class Backend:
        def __init__(self,args):pass
        def generate(self,conversations,**kwargs):
            calls.append((conversations,kwargs))
            text='bad JSON' if bad_first and len(calls)==1 else json.dumps(verdict())
            return [{'text':text,'finish_reason':'stop'}]
    monkeypatch.setattr(runner,'Backend',Backend)
    monkeypatch.setattr(runner,'fingerprint',lambda args:{'decode':{'temperature':0}})
    args=Namespace(rank=0,world_size=1,batch_size=2,max_pixels=1048576,max_tokens=4096,max_model_len=16384,
                   variants=['pair_v2'],manifest=manifest,split='all',limit=None,output=tmp_path/'run',dry_run=False,
                   thinking=False,reasoning_effort='xhigh')
    assert runner.run(args)==0
    assert len(calls)==(2 if bad_first else 1)
    content=calls[0][0][0][0]['content']
    assert sum(p['type']=='image' for p in content)==2
    assert calls[0][1]=={'thinking':True,'effort':'low'}
    result=json.loads(next((args.output/'records').glob('*.json')).read_text())
    assert len(result['passes'])==1 and result['passes'][0]['region'] is None
    assert result['scores']['edit']==4
