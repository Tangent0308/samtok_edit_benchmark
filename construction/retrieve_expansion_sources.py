"""Retrieve additional indexed SA-1B sources; heuristic ranking is NOT acceptance."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import sys

BASE=Path('/mnt/bn/strategy-mllm-train/user/tanyue/datasets')
ROOT=BASE/'samtok_edit_benchmark_v2_expansion_20261014'
SELECTION=BASE/'samtok_edit_benchmark_v2/sa1b_source_selection'
sys.path.insert(0,str(SELECTION/'scripts'))
import retrieve
retrieve.BASE=Path('/mnt/hdfs/sg_byte_ttlive_strategy_llm/user/haobo.yuan/datasets')
from PIL import Image
from pycocotools import mask as M

EVERYDAY=re.compile(r'\b(shirt|jacket|coat|dress|skirt|sweater|garment|scarf|bag|backpack|basket|bottle|cup|mug|bowl|plate|pot|pan|chair|stool|table|umbrella|hat|helmet|shoe|bicycle|bike|toy|fruit|book|lamp|glove|vase|suitcase|flowerpot)s?\b')
PEOPLE=re.compile(r'\b(person|man|woman|child|boy|girl|player|worker|pedestrian)s?\b')
BG=re.compile(r'window|building|railing|balcony|roof|column|facade')

def main():
 p=argparse.ArgumentParser();p.add_argument('--count',type=int,default=300);a=p.parse_args()
 index=json.loads((SELECTION/'sample_index.json').read_text())['selection']
 original={json.loads(l)['source']['family_id'] for l in (Path(__file__).resolve().parents[1]/'data/v2/cases.jsonl').open()}
 existing={json.loads(l)['source_id'] for l in (BASE/'sa1b_edit_work/disjoint_pool/candidates.jsonl').open()}
 training={json.loads(l)['source_id'] for l in (BASE/'sa1b_samtok_edit_50k_20261014/inputs/reservoir.jsonl').open()}
 old=json.loads((SELECTION/'retrieval.json').read_text());rows=old['rows'] if isinstance(old,dict) else old
 rows+=json.loads((SELECTION/'retrieval_round2.json').read_text())
 scored=[]
 for row in rows:
  sid=row['key']
  if sid in original|existing|training:continue
  objects=row['objects'];useful=[o for o in objects if EVERYDAY.search(o['category'])]
  categories={o['category'].split(',')[0] for o in useful}
  people=sum(bool(PEOPLE.search(o['category'])) for o in objects)
  background=sum(bool(BG.search(o['category'])) for o in objects)
  score=min(len(useful),12)*2+len(categories)*3+min(people,5)*2-min(background,20)*.2
  if len(useful)>=2:scored.append((score,sid))
 scored=sorted(set(scored),reverse=True)[:a.count]
 print('Additional ranked sources:',len(scored),flush=True)
 manifest=ROOT/'additional_candidates.jsonl';completed={}
 if manifest.exists():completed={r['source_id']:r for r in map(json.loads,manifest.open())}
 errors=[]
 def one(sid):
  if sid in completed:return completed[sid]
  directory=ROOT/'raw_extra'/sid;directory.mkdir(parents=True,exist_ok=True)
  dense_path=SELECTION/'candidates'/sid/'dense.json';dense=json.loads(dense_path.read_text())
  path=directory/'image.jpg'
  if not path.exists():
   record=retrieve.read(index[sid]['image'],'sa1b_tfd_1k')
   if record['key'].decode()!=sid:raise ValueError('source TFRecord key mismatch')
   tmp=path.with_suffix('.jpg.tmp');tmp.write_bytes(record['jpg']);tmp.replace(path)
  with Image.open(path) as im:im.verify()
  objects=[]
  for o in dense['objects']:
   # Export original encoded mask unchanged. Bounding boxes here are only hints.
   x,y,w,h=M.toBbox(o['segmentation'])
   objects.append({'object_id':str(o['object_id']),'category':o['category'],'description':o.get('gar_caption',''),'bbox':[float(x),float(y),float(x+w),float(y+h)],'rle':o['segmentation'],'metadata':{'score':o.get('score')}})
  return {'source_id':sid,'image_path':str(path),'image_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'caption':dense['caption'],'tags':dense['merged_tags'],'objects':objects,'provenance':{'dense_record':str(dense_path),'dense_sha256':hashlib.sha256(dense_path.read_bytes()).hexdigest(),'tfrecord_index':index[sid],'selection_status':'unreviewed_requires_direct_visual_review','retrieval_method':'everyday_object_recall_only'}}
 with manifest.open('a') as stream, ThreadPoolExecutor(8) as pool:
  futures={pool.submit(one,sid):sid for _,sid in scored if sid not in completed}
  for i,future in enumerate(as_completed(futures),1):
   try:
    row=future.result();stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush();completed[row['source_id']]=row
   except Exception as e:errors.append({'source_id':futures[future],'error':repr(e)})
   if i%20==0:print('Retrieved',i,'/',len(futures),flush=True)
 (ROOT/'additional_retrieval.json').write_text(json.dumps({'retrieved':len(completed),'ranked':len(scored),'errors':errors,'admitted':0},ensure_ascii=False,indent=2)+'\n')
 print('Done:',len(completed),'retrieved;',len(errors),'errors; zero automatically admitted.',flush=True)
if __name__=='__main__':main()
