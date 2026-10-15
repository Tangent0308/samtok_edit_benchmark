"""Record explicit assistant-authored decisions after direct image inspection.
No target selection, inferred approval, or operation fallback is performed here.
"""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from expand_reviewed_v2 import ROOT, sha, write


def target(oid,op,ref,refzh,scope,scopezh,parent,parentzh,payload='',payloadzh='',kind=None,relation=None,site='',sitezh=''):
    t=dict(object_id=oid,operation=op,ref=ref,ref_zh=refzh,scope=scope,scope_zh=scopezh,parent=parent,parent_zh=parentzh,payload=payload)
    if kind:t['attribute_kind']=kind
    if relation:t['placement']={'relation':relation,'site':site,'anchor_mode':'support'}
    def zh(s):
        if op=='remove':return '移除'+s+'。'
        if op=='replace':return '将'+s+'替换为'+payloadzh+'。'
        if op=='attribute':
            property_zh={'color':'颜色','material':'材质','finish':'表面效果','pattern':'图案','texture':'纹理','text':'文字','tint':'色调','opacity':'不透明度'}[kind]
            return '将'+s+'的'+property_zh+'改为'+payloadzh+'。'
        return '在'+s+sitezh+'加上'+payloadzh+'。'
    t['instruction_zh']=zh(refzh);t['instruction_noref_zh']=zh('选中的'+scopezh)
    return t


def record(sid,decision,scene,evidence,mechanisms=None,protect='',targets=None,card_name='candidate.jpg',rejected=None):
    folder=ROOT/'candidates'/sid
    source=json.loads((folder/'source.json').read_text())
    if decision=='accept':
        import itertools
        from pycocotools import mask as coco
        assert targets and 2<=len(targets)<=5
        assert len({t['parent'] for t in targets})==len(targets)
        assert len({t['operation'] for t in targets})==min(4,len(targets))
        objects={str(o['object_id']):o for o in source['objects']}
        for first,second in itertools.combinations(targets,2):
            a,b=[objects[str(t['object_id'])]['rle'] for t in (first,second)]
            overlap=float(coco.area(coco.merge([a,b],intersect=True)))/min(float(coco.area(a)),float(coco.area(b)))
            if overlap>.04:raise ValueError(f'{sid}: masks {first["object_id"]}/{second["object_id"]} overlap {overlap:.6f}')
    r=dict(source_id=sid,decision=decision,review_kind='ai_direct_visual',reviewer='assistant',review_date='2026-10-14',independent_human_verified=False,source_viewed=True,selected_mask_overlays_viewed=True,source_sha256=sha(source['image_path']),review_card_sha256=sha(folder/card_name),review_card_name=card_name,evidence_zh=evidence,difficulty={'mechanisms':mechanisms or [],'scene_zh':scene,'evidence_zh':evidence,'specific_protection_zh':protect},protected_content_zh=protect,targets=targets or [],rejected_targets=rejected or [])
    proposal=ROOT/'proposals'/f'{sid}.json'
    if proposal.exists():r['assisted_proposal_sha256']=sha(proposal)
    dest=ROOT/'decisions'/f'{sid}.json'
    if dest.exists():
        if json.loads(dest.read_text())!=r:raise ValueError('Explicit revision required for existing decision: '+sid)
    else:write(dest,r)
    return r


def freeze(batch, records):
    path=Path(__file__).with_name(batch+'.json')
    if path.exists() and json.loads(path.read_text())!=records:raise ValueError('Frozen batch differs')
    write(path,records)
