"""Render model-ordered visual-locator case studies from frozen outputs (CPU only)."""
from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont,ImageChops,ImageFilter
ROOT=Path.cwd();PUB=ROOT/'docs/publication/2.6.0';OUT=PUB/'assets/model_cases';OUT.mkdir(parents=True,exist_ok=True)
EXP=Path('/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/benchmark_v2_2.6.0_baselines')
MODELS={'flux3_klein':'FLUX.3 Klein','qwen_image_21':'Qwen-Image-2.1','flux2_klein_4b':'FLUX.2 Klein-4B','longcat_image_edit':'LongCat-Image-Edit','qwen_image_edit_2511':'Qwen-Image-Edit-2511','hidream_o1_image':'HiDream-O1-Image','step1x_edit':'Step1X-Edit'}
SHORT=['FLUX.3 Klein','Qwen 2.1','FLUX.2 Klein','LongCat','Qwen Edit 2511','HiDream-O1','Step1X-Edit']
NOTES=json.loads((PUB/'case_study_notes.json').read_text())
SELECT={m:[c['case_id'] for c in NOTES['models'][m]['cases']] for m in MODELS}
GROUPS=[list(MODELS)[:4],list(MODELS)[4:]]
def jl(p):return [json.loads(x) for x in p.open() if x.strip()]
jobs={m:{x['case_id']:x for x in jl(EXP/'judge_inputs'/m/'judge_jobs.jsonl')} for m in MODELS};scores={m:{x['case_id']:x for x in json.loads((EXP/'judge'/m/'Qwen3.8-Flash-Next-FP8/report.json').read_text())['case_results']} for m in MODELS}
def font(n,b=False):return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if b else '')+'.ttf',n)
def paste(panel,im,x,y,w,h):
 im=im.convert('RGB');im.thumbnail((w,h),Image.Resampling.LANCZOS);panel.paste(im,(x+(w-im.width)//2,y+(h-im.height)//2))
def save(im,path):im.save(path,quality=88,optimize=True,progressive=True)
manifest=[]
for model,cids in SELECT.items():
 for cid in cids:
  j=jobs[model][cid];stem=model+'_'+cid;p=Image.new('RGB',(2400,900),'white');d=ImageDraw.Draw(p)
  for row,group in enumerate(GROUPS):
   dy=row*450
   items=[('Clean source',j['source_image'],None),('Color locator',j['public_job']['images'][1],None)]+[(SHORT[list(MODELS).index(m)],jobs[m][cid]['output_image'],m) for m in group]
   for i,(label,path,m) in enumerate(items):
    if m==model:d.rounded_rectangle((i*400+6,dy+4,(i+1)*400-6,dy+444),radius=8,fill='#EEF4FA',outline='#447DB1',width=3)
    d.text((i*400+15,dy+14),label+(' *' if m==model else ''),font=font(22,True),fill='#183249');paste(p,Image.open(path),i*400+12,dy+55,376,330)
    if m:
     passed=scores[m][cid]['joint_pass'];d.text((i*400+15,dy+410),'JointPass: '+('PASS' if passed else 'FAIL'),font=font(21,True),fill='#26836F' if passed else '#B84B49')
   if row==1:
    for k,line in enumerate(['Actual input:', 'LongCat / Step1X:', 'color locator only.', 'Other five models:', 'clean source + locator.', '', '* Analyzed model', 'Raw outputs; no overlay.']):
     d.text((2020,dy+64+k*35),line,font=font(20),fill='#475569')
  save(p,OUT/(stem+'_overview.jpg'))
  for de in j['private_evaluation_details']:
   uid=de['id'];p=Image.new('RGB',(2000,880),'white');d=ImageDraw.Draw(p)
   for row,group in enumerate(GROUPS):
    dy=row*440
    for i,m in enumerate([None]+group):
     if m==model:d.rounded_rectangle((i*400+6,dy+4,(i+1)*400-6,dy+435),radius=8,fill='#EEF4FA',outline='#447DB1',width=3)
     item=de if m is None else next(v for v in jobs[m][cid]['private_evaluation_details'] if v['id']==uid)
     im=Image.open(item['source_crop'] if m is None else item['output_crop']).convert('RGB');mask=Image.open(item['gold_source_mask']).convert('L').crop(item['crop_box_xyxy']);w=max(1,round(max(im.size)/250));contour=ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(2*w+1)),mask);im.paste('#F44A45',mask=contour);paste(p,im,i*400+12,dy+52,376,324)
     d.text((i*400+14,dy+13),uid+' | '+('Source' if m is None else SHORT[list(MODELS).index(m)])+(' *' if m==model else ''),font=font(21,True),fill='#183249')
     if m is None:d.text((14,dy+398),'Red outline: source mask',font=font(19),fill='#B84B49')
     else:
      u=next(v for v in scores[m][cid]['units'] if v['id']==uid)
      for k,dim in enumerate('EPQ'):d.text((i*400+14+127*k,dy+398),f"{dim} {u[dim]['score']} "+('PASS' if u[dim]['pass'] else 'FAIL'),font=font(18,True),fill='#26836F' if u[dim]['pass'] else '#B84B49')
   save(p,OUT/(stem+'_'+uid+'.jpg'))
  manifest.append({'model':model,'case_id':cid,'unit_ids':j['public_job']['unit_ids'],'overview':str((OUT/(stem+'_overview.jpg')).relative_to(PUB)),'instructions':j['public_job']['units'],'scores':scores[model][cid],'raw_output':j['output_image'],'input_digest':j['input_digest'],'output_sha256':j['output_sha256']})
(PUB/'model_case_studies.json').write_text(json.dumps({'column_order':list(MODELS),'row_model_groups':GROUPS,'selection':SELECT,'cases':manifest,'selection_method':NOTES['selection_method'],'overview':'Original outputs, resized only; no evaluator contour added. Blue frame and asterisk identify the analyzed model. Sources repeat in each row for readability.','details':'Fixed-coordinate crops with red source-mask contour added for comparison.'},ensure_ascii=False,indent=2)+'\n')
print('Rendered',len(list(OUT.glob('*.jpg'))),'images; cases',len(manifest))
