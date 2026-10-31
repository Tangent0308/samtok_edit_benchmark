"""Resumable expansion: candidate cards and manually recorded visual decisions.

Candidate ranking is a recall aid, never an admission decision. No source is
accepted without an explicit reviewed authoring record. Original v2 is immutable.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from samtok_benchmark.paths import repository_root
import re
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pycocotools import mask as coco
from scipy.ndimage import distance_transform_edt, label

REPO = repository_root()
sys.path.insert(0, str(REPO / "src"))
from samtok_benchmark.v2.instruction_protocol import make_spec, render, mask_contract, length_advice
from samtok_benchmark.v2.dataset import validate

BASE = Path('/mnt/bn/strategy-mllm-train/user/tanyue/datasets')
ROOT = BASE / 'samtok_edit_benchmark_v2_expansion_20261014'
POOL = BASE / 'sa1b_edit_work/disjoint_pool/candidates.jsonl'
ADDITIONAL = ROOT / 'additional_candidates.jsonl'
ORIGINAL = BASE / 'samtok_edit_benchmark_v2'
MODES = [(False,'point'),(True,'box'),(False,'mask'),(True,'none'),(True,'mask'),(False,'box'),(True,'point')]
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
USEFUL = re.compile(r'bag|backpack|bottle|cup|bowl|chair|stool|shirt|jacket|dress|skirt|sleeve|strap|handle|wheel|hat|cap|helmet|shoe|boot|basket|pot|vase|lamp|car|bike|bicycle|umbrella|plate|tray|glass|boat|canopy|pillow|cushion|box|suitcase|sign|flower|fruit|dog|cat|bird|bench|coat|scarf|tie|apron|bucket|rail|door|window|shelf|book|cloth|garment|banner|flag|vest|towel|headpiece|jerrycan')
BROAD = re.compile(r'^(person|man|woman|people|hand|arm|leg|face|head|hair|sky|ground|wall|water|tree|grass|road|background)(,|$)')

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n')
def fit(im, size):
    im=im.copy(); im.thumbnail(size)
    out=Image.new('RGB',size,'#f1f3f6'); out.paste(im,((size[0]-im.width)//2,(size[1]-im.height)//2)); return out

def records():
    original={r['source']['family_id'] for r in map(json.loads,(REPO/'data/v2/cases.jsonl').open())}
    production=BASE/'sa1b_samtok_edit_50k_20261014/inputs/reservoir.jsonl'
    train={r['source_id'] for r in map(json.loads,production.open())} if production.exists() else set()
    rows=[]; seen=set()
    for path in [POOL, ADDITIONAL]:
        if not path.exists():continue
        for r in map(json.loads,path.open()):
            sid=r['source_id']
            if sid in original|train|seen:continue
            rows.append(r);seen.add(sid)
    return rows

def shortlist(row, n=16):
    counts=Counter(o['category'].split(',')[0] for o in row['objects'])
    scored=[]
    for o in row['objects']:
        area=float(coco.area(o['rle'])); h,w=o['rle']['size']; frac=area/(h*w)
        if frac<.00035 or frac>.65: continue
        cat=o['category'].lower()
        score=5*bool(USEFUL.search(cat))-7*bool(BROAD.search(cat))+min(counts[cat.split(',')[0]],3)+(.001<frac<.12)
        scored.append((score,int(o['object_id']),o))
    ordered = [o for _,_,o in sorted(scored,key=lambda x:(-x[0],x[1]))]
    chosen=[]; categories=Counter()
    for o in ordered:
        category=o['category'].split(',')[0]
        if categories[category]>=3: continue
        chosen.append(o);categories[category]+=1
        if len(chosen)==n:break
    return chosen + [o for o in ordered if o not in chosen][:n-len(chosen)]

def card(row, objects, output):
    im=Image.open(row['image_path']).convert('RGB'); arr=np.asarray(im)
    canvas=Image.new('RGB',(1600,510+((len(objects)+3)//4)*300),'white'); draw=ImageDraw.Draw(canvas)
    f=ImageFont.truetype(FONT,19); fs=ImageFont.truetype(FONT,15)
    draw.text((16,12),row['source_id']+' | exact source masks | pending visual review',font=f,fill='#15263f')
    canvas.paste(fit(im,(1570,450)),(15,46))
    for j,o in enumerate(objects):
        m=coco.decode(o['rle']).astype(bool); x,y,w,h=coco.toBbox(o['rle']); pad=max(20,.18*max(w,h))
        box=(max(0,int(x-pad)),max(0,int(y-pad)),min(im.width,int(x+w+pad)),min(im.height,int(y+h+pad)))
        # Keep target colors readable; brighten boundary and dim non-target context.
        overlay=(arr*.55).astype('uint8'); overlay[m]=arr[m]
        boundary=np.asarray(Image.fromarray(m.astype('uint8')*255).filter(ImageFilter.MaxFilter(5)))>0
        overlay[boundary & ~m]=(255,45,100)
        xx=(j%4)*400; yy=510+(j//4)*300
        canvas.paste(fit(Image.fromarray(overlay).crop(box),(394,260)),(xx+3,yy+32))
        draw.text((xx+8,yy+5),f"ID {o['object_id']} | {o['category'][:30]}",font=fs,fill='#182a40')
    output.parent.mkdir(parents=True,exist_ok=True);canvas.save(output,quality=93)
    return output

def prepare(start,count):
    rows=records()[start:start+count]
    def one(row):
        d=ROOT/'candidates'/row['source_id']; p=d/'candidate.jpg'
        if not p.exists():
            chosen=shortlist(row);card(row,chosen,p)
            write(d/'source.json',row)
            write(d/'candidate.json',{'status':'pending','source_id':row['source_id'],'source_sha256':sha(row['image_path']),'card_sha256':sha(p),'object_ids':[o['object_id'] for o in chosen]})
        return str(p)
    with ThreadPoolExecutor(4) as pool:
        for p in pool.map(one,rows):print(p,flush=True)

def build():
    # Only explicit authoring ledgers can authorize admission; proposal files are ignored.
    accepted=[]
    allowed_sources={r['source_id'] for r in records()}
    original_hashes={r['source']['sha256'] for r in map(json.loads,(REPO/'data/v2/cases.jsonl').open())}
    for p in sorted((ROOT/'decisions').glob('*.json')):
        r=json.loads(p.read_text())
        if r.get('decision')!='accept':continue
        if r.get('review_kind')!='ai_direct_visual' or not r.get('source_viewed') or not r.get('selected_mask_overlays_viewed'):
            raise ValueError(f'incomplete direct review evidence: {p}')
        if r['source_id'] not in allowed_sources:raise ValueError('source overlaps original benchmark or frozen production reservoir')
        d=ROOT/'candidates'/r['source_id'];row=json.loads((d/'source.json').read_text())
        review_card=d/r.get('review_card_name','candidate.jpg')
        if sha(review_card)!=r['review_card_sha256']:raise ValueError('review card changed')
        if sha(row['image_path'])!=r['source_sha256']:raise ValueError('source changed')
        if r['source_sha256'] in original_hashes:raise ValueError('duplicate original source bytes')
        original_hashes.add(r['source_sha256'])
        targets=r['targets']; assert 2<=len(targets)<=5
        assert len({t['parent'] for t in targets})==len(targets)
        assert len({t['operation'] for t in targets})==min(4,len(targets))
        dense_path=Path(row['provenance']['dense_record'])
        if sha(dense_path)!=row['provenance']['dense_sha256']:
            raise ValueError('original dense annotation changed')
        dense_objects={str(o['object_id']):o for o in json.loads(dense_path.read_text())['objects']}
        objects={str(o['object_id']):o for o in row['objects']}
        for t in targets:
            oid=str(t['object_id'])
            if objects[oid]['rle']!=dense_objects[oid]['segmentation']:
                raise ValueError(f'candidate RLE differs from original dense annotation: {oid}')
        import itertools
        for first,second in itertools.combinations(targets,2):
            ma,mb=[objects[str(t['object_id'])]['rle'] for t in (first,second)]
            overlap=float(coco.area(coco.merge([ma,mb],intersect=True)))/min(float(coco.area(ma)),float(coco.area(mb)))
            if overlap>.04:
                raise ValueError(f"{r['source_id']} masks {first['object_id']}/{second['object_id']} overlap {overlap:.6f} exceeds 0.04")
        cid='v2-'+r['source_id'];base=Path('assets')/cid; out=ROOT/'release'
        (out/base).mkdir(parents=True,exist_ok=True)
        import shutil
        shutil.copyfile(row['image_path'],out/base/'source.jpg');shutil.copyfile(review_card,out/base/'selection_review.jpg')
        units=[]
        for j,t in enumerate(targets):
            o=objects[str(t['object_id'])];m=coco.decode(o['rle']).astype(bool)
            uid=f'U{j+1}';mp=base/(uid+'.png');Image.fromarray(m.astype('uint8')*255).save(out/mp)
            yy,xx=np.where(m);dist=distance_transform_edt(np.pad(m,1));py,px=np.unravel_index(dist.argmax(),dist.shape);px-=1;py-=1
            spec=make_spec(t['operation'],t['ref'],t['scope'],t.get('payload',''),attribute_kind=t.get('attribute_kind'),placement=t.get('placement'))
            ref=render(spec);noref=render(spec,False)
            has_ref,loc=MODES[(785+sum(len(c['units']) for c in accepted)+j)%7]
            units.append(dict(id=uid,operation=t['operation'],instruction_protocol_version='1.0',instruction_spec=spec,mask_semantics=mask_contract(spec),instruction_length_advice=length_advice(ref,noref),attribute_kind=t.get('attribute_kind'),target=dict(parent_instance_id=r['source_id']+':'+t['parent'],physical_parent_zh=t['parent_zh'],annotation_id=int(o['object_id']),source_category=o['category'],category=t['scope'],mask=str(mp),mask_sha256=sha(out/mp),box=[int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)],point=[int(px),int(py)],geometry={'area_fraction':float(m.mean()),'significant_components':int(sum(v>=max(16,m.sum()*.005) for v in np.bincount(label(m)[0].ravel())[1:]))},ref=t['ref'],ref_zh=t['ref_zh'],scope=t['scope'],scope_zh=t['scope_zh'],annotation_origin='SA-1B dense objects_json; unchanged visible mask'),interaction={'has_ref':has_ref,'locator':loc},instruction_ref=ref,instruction_noref=noref,instruction_ref_zh=t['instruction_zh'],instruction_noref_zh=t['instruction_noref_zh'],completion_requirement=ref+' Apply the edit only to this selected instance; preserve unrelated content.',preserve=[r['protected_content_zh']],edit_contract={'locator_semantics':'addition_support' if t['operation']=='add' else 'existing_edit_target','source_mask_role':'visible semantic selector, not output difference ground truth','scope_relation':'attachment_to_selected_object' if t['operation']=='add' else 'selected_visible_object_or_part','definition':ref,'allowed_local_effects':'Only physically necessary local attachment, revealed background, occlusion, edge, lighting or shadow changes.'},instruction_design={'version':'2.5.0-draft','review_kind':'ai_direct_visual','key':cid+':'+uid}))
        im=Image.open(out/base/'source.jpg')
        accepted.append(dict(schema_version='2.0',id=cid,selection_index=201+len(accepted),source={'dataset':'SA-1B','annotation_dataset':'SA-1B companion dense labels','family_id':r['source_id'],'image_id':r['source_id'],'image':str(base/'source.jpg'),'sha256':sha(out/base/'source.jpg'),'size':list(im.size),'training_catalog_member':True},units=units,difficulty=r['difficulty'],review={'decision':'accept','kind':'ai_direct_visual','reviewer':'assistant','evidence':r['evidence_zh'],'card':str(base/'selection_review.jpg'),'card_sha256':r['review_card_sha256'],'independent_human_verified':False},instruction_review={'version':'2.5.0-draft','source_viewed':True,'selected_mask_overlays_viewed':True,'scene_specific_design':True,'authoring_record_sha256':sha(p)}))
    if not accepted:raise ValueError('no accepted new cases')
    out=ROOT/'release';meta=out/'benchmark';meta.mkdir(parents=True,exist_ok=True)
    manifest=meta/'cases.jsonl';manifest.write_text(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in accepted))
    inventory=[]
    for c in accepted:
        paths=[c['source']['image'],c['review']['card']]+[u['target']['mask'] for u in c['units']]
        for rel in paths:inventory.append({'path':rel,'sha256':sha(out/rel),'bytes':(out/rel).stat().st_size})
    (meta/'asset_manifest.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in inventory))
    write(meta/'provenance.json',{'pool':str(POOL),'pool_sha256':sha(POOL),'additional_pool':str(ADDITIONAL) if ADDITIONAL.exists() else None,'additional_pool_sha256':sha(ADDITIONAL) if ADDITIONAL.exists() else None,'decisions':str(ROOT/'decisions'),'independent_human_verified':False,'original_cases':200,'new_cases':len(accepted),'status':'increment_only'})
    report=validate(manifest,out);report['status']='validated_increment_not_1000_release';write(meta/'validation.json',report);print(json.dumps(report,ensure_ascii=False,indent=2))
    cumulative(accepted)

def cumulative(new_cases):
    import os
    import shutil
    original = [json.loads(line) for line in (REPO/'data/v2/cases.jsonl').open()]
    cases = original + new_cases
    output = ROOT/'cumulative'
    metadata = output/'benchmark'
    metadata.mkdir(parents=True, exist_ok=True)
    inventory = []
    for case, source_root in [(c, ORIGINAL) for c in original] + [(c, ROOT/'release') for c in new_cases]:
        paths = [case['source']['image'], case['review']['card']]
        paths.extend(u['target']['mask'] for u in case['units'])
        for rel in paths:
            source, destination = source_root/rel, output/rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                try: os.link(source, destination)
                except OSError: shutil.copyfile(source, destination)
            if sha(source) != sha(destination):
                raise ValueError(f'Cumulative asset changed: {rel}')
            inventory.append({'path':rel,'sha256':sha(destination),'bytes':destination.stat().st_size})
    manifest = metadata/'cases.jsonl'
    manifest.write_text(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in cases))
    (metadata/'asset_manifest.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in inventory))
    report = validate(manifest, output)
    report['status'] = 'partial_expansion_not_final_release'
    report['goal_images'] = 1000
    report['remaining_images'] = max(0, 1000-len(cases))
    write(metadata/'validation.json', report)
    decisions = [json.loads(p.read_text()) for p in (ROOT/'decisions').glob('*.json')]
    write(ROOT/'progress.json', dict(goal_images=1000, original_images=len(original),
          accepted_new_images=len(new_cases), verified_images=len(cases),
          remaining_images=max(0,1000-len(cases)), status='in_progress',
          decisions=dict(Counter(r['decision'] for r in decisions)),
          validation=str(metadata/'validation.json'),
          note_zh='候选、模型提议和旧单目标模板草稿不计入通过数；尚未达到1000张。'))
    print(f'Cumulative validated images: {len(cases)} / 1000', flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','build']);p.add_argument('--start',type=int,default=0);p.add_argument('--count',type=int,default=16);a=p.parse_args()
    prepare(a.start,a.count) if a.action=='prepare' else build()
