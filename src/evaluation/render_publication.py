"""Render the frozen visual-locator benchmark brief; CPU only, no inference.
Run from repository root with the plotting dependencies on PYTHONPATH.
"""
from pathlib import Path
from collections import Counter
import csv, json, math, importlib.util
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageFilter

ROOT=Path.cwd()
OUT=ROOT/'docs/publication/2.6.0'
AS=OUT/'assets'; AS.mkdir(parents=True,exist_ok=True)
EXP=Path('/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/benchmark_v2_2.6.0_baselines')
DATA=Path('/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2')
REPORT=ROOT/'docs/reports/2.6.0'
MODELS={'qwen_image_21':'Qwen-Image-2.1','qwen_image_edit_2511':'Qwen-Image-Edit-2511','flux2_klein_4b':'FLUX.2 Klein-4B','flux3_klein':'FLUX.3 Klein'}
SHORT=['Qwen 2.1','Qwen Edit 2511','FLUX.2 Klein','FLUX.3 Klein']
COLORS=['#3575B4','#D18A26','#419881','#8A61AF']
def jl(p):return [json.loads(x) for x in p.open() if x.strip()]
cases=jl(ROOT/'data/v2_2.6.0/cases.jsonl'); case_by={x['id']:x for x in cases}
jobs={m:{x['case_id']:x for x in jl(EXP/'judge_inputs'/m/'judge_jobs.jsonl')} for m in MODELS}
reports={m:json.loads((EXP/'judge'/m/'Qwen3.8-Flash-Next-FP8/report.json').read_text()) for m in MODELS}
scores={m:{x['case_id']:x for x in r['case_results']} for m,r in reports.items()}
main=list(csv.DictReader((REPORT/'main_table.csv').open()))
kdata=list(csv.DictReader((REPORT/'k_jointpass.csv').open()))
loc=list(csv.DictReader((REPORT/'locator_impact.csv').open()))
fail=list(csv.DictReader((REPORT/'failure_modes.csv').open()))
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':12,'axes.labelsize':10,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#A3ABB7','text.color':'#202C3D','axes.labelcolor':'#334155','xtick.color':'#475569','ytick.color':'#475569','figure.facecolor':'white','savefig.facecolor':'white','pdf.fonttype':42})
def save(fig,name):
 fig.savefig(AS/(name+'.png'),dpi=175,bbox_inches='tight');fig.savefig(AS/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
def grid(ax):ax.set_axisbelow(True);ax.grid(axis='y',color='#E8EDF2',lw=.7)
def bars(ax,labels,counts,title,color):
 b=ax.bar(labels,counts,color=color,width=.62);ax.bar_label(b,padding=4,fontsize=10);ax.set_ylim(0,max(counts)*1.22);ax.set_title(title,loc='left',fontweight='bold');grid(ax)
fig,axs=plt.subplots(2,2,figsize=(11,6.6),layout='constrained')
ks=Counter(len(c['units']) for c in cases);ops=Counter(u['operation'] for c in cases for u in c['units'])
bars(axs[0,0],['K=2','K=3','K=4','K=5'],[ks[k] for k in range(2,6)],'a  Targets per image · 1,084 cases','#3575B4')
bars(axs[0,1],['Add','Replace','Remove','Attribute'],[ops[k] for k in ['add','replace','remove','attribute']],'b  Edit operations · 3,872 units',COLORS)
inter=Counter(('ref' if u['interaction']['has_ref'] else 'no-ref')+' / '+u['interaction']['locator'] for c in cases for u in c['units'])
labels=['ref / none','ref / point','ref / box','ref / mask','no-ref / point','no-ref / box','no-ref / mask']
a=axs[1,0];b=a.barh(labels[::-1],[inter[x] for x in labels[::-1]],color=['#72AFCE']*3+['#B2C4D8']*4);a.bar_label(b,padding=4,fontsize=9);a.set_xlim(0,650);a.set_title('c  Seven balanced interaction combinations',loc='left',fontweight='bold');a.spines['left'].set_visible(False)
areas=np.array([u['target']['geometry']['area_fraction']*100 for c in cases for u in c['units']]);a=axs[1,1];a.hist(areas,bins=np.geomspace(.002,60,28),color='#419881',edgecolor='white',linewidth=.5);a.set_xscale('log');a.axvline(1,color='#B75E4A',ls='--',lw=1.2);a.set_xlabel('Target area / image area (%)');a.set_ylabel('Units');a.set_title('d  Small targets dominate',loc='left',fontweight='bold');a.text(.96,.94,'68.4% below 1%\nMedian: 0.466%',transform=a.transAxes,ha='right',va='top',bbox=dict(facecolor='white',edgecolor='none',alpha=.9));grid(a)
save(fig,'dataset_profile')
fig,axs=plt.subplots(1,2,figsize=(11,3.8),gridspec_kw={'width_ratios':[1,1.65]},layout='constrained')
y=np.arange(4);a=axs[0];v=[float(r['joint_rate'])*100 for r in main];b=a.barh(y,v,color=COLORS,height=.58);a.set_yticks(y,SHORT);a.invert_yaxis();a.bar_label(b,fmt='%.2f%%',padding=5);a.set_xlim(0,31);a.set_xlabel('Cases passing all checks (%)');a.set_title('a  JointPass',loc='left',fontweight='bold')
a=axs[1];vals=np.array([[float(r[k])*100 for k in ['E_unit_rate','P_unit_rate','Q_unit_rate','global_P_rate','global_Q_rate']] for r in main]);a.imshow(vals,vmin=0,vmax=100,cmap='Blues',aspect='auto');a.set_xticks(range(5),['Unit E','Unit P','Unit Q','Global P','Global Q']);a.set_yticks(range(4),SHORT);a.tick_params(length=0);a.set_title('b  Where performance is lost · pass rate (%)',loc='left',fontweight='bold')
for i in range(4):
 for j in range(5):a.text(j,i,f'{vals[i,j]:.1f}',ha='center',va='center',color='white' if vals[i,j]>60 else '#16314D',fontsize=12)
for sp in a.spines.values():sp.set_visible(False)
save(fig,'main_results')
fig,axs=plt.subplots(1,4,figsize=(12,3.7),sharey=True,layout='constrained')
for i,(m,label) in enumerate(MODELS.items()):
 a=axs[i];r=[x for x in kdata if x['model_key']==m];x=[int(z['K']) for z in r];actual=[float(z['measured_joint_rate'])*100 for z in r];prod=[float(z['p_u_product'])*100 for z in r];unit_all=[100*np.mean([all(all(u[d]['pass'] for d in 'EPQ') for u in z['units']) for z in scores[m].values() if z['expected_units']==k]) for k in x];a.plot(x,actual,'o-',color=COLORS[i],lw=2,label='JointPass');a.plot(x,prod,'s--',color='#566476',lw=1.3,ms=4,label='Product of unit marginals');a.plot(x,unit_all,':',color=COLORS[i],lw=1.3,label='All units pass (no globals)');a.set_title(SHORT[i],loc='left',fontweight='bold');a.set_xticks(x,[f'{k}\n(n={ks[k]})' for k in x]);a.set_xlabel('Number of targets K');a.set_ylim(-1,58);grid(a)
axs[0].set_ylabel('Pass rate (%)');handles,labels=axs[0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=3,frameon=False,fontsize=9);save(fig,'composition')
fig,axs=plt.subplots(1,2,figsize=(11,4),layout='constrained')
for a,groups,title in [(axs[0],['ref','no-ref'],'a  Textual reference vs. blind reference'),(axs[1],['point','box','mask'],'b  Visual locator types')]:
 w=.18
 for i,m in enumerate(MODELS):
  vs=[float(next(r for r in loc if r['model_key']==m and r['group']==g)['unit_joint_rate'])*100 for g in groups];a.bar(np.arange(len(groups))+(i-1.5)*w,vs,width=w,color=COLORS[i],label=SHORT[i])
 a.set_xticks(range(len(groups)),groups);a.set_ylim(0,80);a.set_ylabel('Unit E&P&Q pass rate (%)');a.set_title(title,loc='left',fontweight='bold');grid(a)
h,l=axs[0].get_legend_handles_labels();fig.legend(h,l,loc='outside lower center',ncol=4,frameon=False);save(fig,'localization')
cats=['locator marker in output','not executed','occluded fragments/leftovers','wrong instance','wrong granularity','other E failure'];names=['Marker residue','Not executed','Fragments / leftovers','Wrong instance','Wrong granularity','Other'];palette=['#C6635C','#E2B468','#7097BA','#8D78B4','#78A391','#C9CED5']
fig,axs=plt.subplots(1,4,figsize=(11,3.9),sharey=True,layout='constrained')
for i,m in enumerate(MODELS):
 a=axs[i];d={r['category']:int(r['count']) for r in fail if r['model_key']==m};total=sum(d.values());bottom=0
 for cat,name,col in zip(cats,names,palette):
  v=d.get(cat,0)/total*100;a.bar([0],[v],bottom=bottom,color=col,width=.65,label=name)
  if v>=7:a.text(0,bottom+v/2,f'{v:.0f}%',ha='center',va='center',fontsize=10)
  bottom+=v
 a.set_xlim(-.8,.8);a.set_xticks([]);a.set_title(f'{SHORT[i]}\n{total:,} E-failed units',fontsize=11);a.set_ylim(0,100)
axs[0].set_ylabel('Share of E-failed units (%)');h,l=axs[0].get_legend_handles_labels();fig.legend(h,l,loc='outside lower center',ncol=3,frameon=False,fontsize=9);save(fig,'failure_modes')

FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf';BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
def font(n,b=False):return ImageFont.truetype(BOLD if b else FONT,n)
def fit(im,w,h):
 im=im.convert('RGB');im.thumbnail((w,h),Image.Resampling.LANCZOS);return im
def put(panel,im,x,y,w,h):
 im=fit(im,w,h);panel.paste(im,(x+(w-im.width)//2,y+(h-im.height)//2))
def jpg(im,name):im.save(AS/(name+'.jpg'),quality=88,optimize=True,progressive=True)
selected=json.loads((REPORT/'selected_cases.json').read_text())
# The actual two-image input; a case containing point, box AND mask.
cid='v2-sa_10044652';j=jobs['qwen_image_21'][cid];p=Image.new('RGB',(1800,780),'white');d=ImageDraw.Draw(p)
d.text((36,20),'ACTUAL MODEL INPUT  /  visual_locator_v2 · mixed',font=font(30,True),fill='#183249')
for i,(path,title) in enumerate(zip(j['public_job']['images'],['Image 1 · clean source','Image 2 · point + box + mask'])):
 d.text((36+900*i,80),title,font=font(26,True),fill='#334155');put(p,Image.open(path),30+900*i,128,840,570)
d.text((36,722),'Qwen-Image-2.1  ·  Qwen-Image-Edit-2511  ·  FLUX.2 Klein-4B  ·  FLUX.3 Klein',font=font(23),fill='#475569');jpg(p,'actual_inputs')
# Construction scope examples, using frozen current source masks only.
rep=[('v2-sa_3397098','U1','Shortening: only the removed segment'),('v2-sa_5794853','U1','Add: existing attachment surface'),('v2-sa_6720037','U1','Remove: preserve foreground occluders'),('v2-sa_1254142','U4','Replace: top, excluding bag strap')]
p=Image.new('RGB',(1800,600),'white');d=ImageDraw.Draw(p)
for i,(cid,uid,title) in enumerate(rep):
 c=case_by[cid];u=next(u for u in c['units'] if u['id']==uid);im=Image.open(DATA/c['source']['image']).convert('RGB');mm=Image.open(DATA/u['target']['mask']).convert('L');box=mm.getbbox();pad=int(max(box[2]-box[0],box[3]-box[1])*.25)+16;box=(max(0,box[0]-pad),max(0,box[1]-pad),min(im.width,box[2]+pad),min(im.height,box[3]+pad));im=im.crop(box);mm=mm.crop(box);cont=ImageChops.subtract(mm.filter(ImageFilter.MaxFilter(7)),mm);im.paste('#F44A45',mask=cont);put(p,im,i*450+12,75,426,440);d.text((i*450+16,18),f'{uid} | {cid}',font=font(19,True),fill='#183249');words=title.split(': ');d.text((i*450+16,528),words[0]+':',font=font(20,True),fill='#334155');d.text((i*450+16,558),words[-1],font=font(17),fill='#475569')
jpg(p,'scope_examples')
# A light workflow diagram.
fig,ax=plt.subplots(figsize=(12,2.1));ax.axis('off')
from matplotlib.patches import FancyBboxPatch
steps=[('SOURCE','SA-1B images\n+ dense masks'),('SELECT','2–5 target units\nDistinct parent objects'),('AUTHOR','Structured edit specs\nRef / blind no-ref'),('CORRECT','Scope, masks, semantics\n708 updated masks'),('FREEZE','Assets + geometry checks\nManifest + hashes')]
for i,(title,body) in enumerate(steps):
 x=.015+i*.199
 ax.add_patch(FancyBboxPatch((x,.15),.16,.75,boxstyle='round,pad=.008',fc='#F0F5FA',ec='#CCD8E4',transform=ax.transAxes))
 body=body.replace('Distinct parent objects','Distinct parents').replace('Scope, masks, semantics','Scope + masks').replace('Assets + geometry checks','Asset + geometry checks')
 ax.text(x+.08,.69,title,transform=ax.transAxes,ha='center',va='center',fontsize=10,fontweight='bold')
 ax.text(x+.08,.40,body,transform=ax.transAxes,ha='center',va='center',fontsize=9)
 if i<4:ax.annotate('',xy=(x+.185,.52),xytext=(x+.17,.52),xycoords='axes fraction',arrowprops=dict(arrowstyle='->',color='#75879B'))
save(fig,'construction')
# Overview is UNANNOTATED output; details intentionally add mask outline and score strip.
for tag,cid in selected.items():
 j=jobs['qwen_image_21'][cid];p=Image.new('RGB',(2400,460),'white');d=ImageDraw.Draw(p);items=[('Clean source',j['source_image']),('Actual locator input',j['public_job']['images'][1])]+[(SHORT[i],jobs[m][cid]['output_image']) for i,m in enumerate(MODELS)]
 for i,(label,path) in enumerate(items):
  d.text((i*400+14,12),label,font=font(22,True),fill='#183249');put(p,Image.open(path),i*400+12,55,376,340)
  if i>=2:
   m=list(MODELS)[i-2];passed=scores[m][cid]['joint_pass'];d.text((i*400+14,416),'JointPass: '+('PASS' if passed else 'FAIL'),font=font(21,True),fill='#26836F' if passed else '#B84B49')
 jpg(p,tag+'_overview')
 for detail in j['private_evaluation_details']:
  uid=detail['id'];p=Image.new('RGB',(2000,455),'white');d=ImageDraw.Draw(p)
  for i,m in enumerate([None]+list(MODELS)):
   md=detail if m is None else next(x for x in jobs[m][cid]['private_evaluation_details'] if x['id']==uid)
   im=Image.open(md['source_crop'] if m is None else md['output_crop']).convert('RGB');mm=Image.open(md['gold_source_mask']).convert('L').crop(md['crop_box_xyxy']);width=max(1,round(max(im.size)/250));cont=ImageChops.subtract(mm.filter(ImageFilter.MaxFilter(2*width+1)),mm);im.paste('#F44A45',mask=cont);put(p,im,i*400+12,53,376,330)
   d.text((i*400+12,12),f'{uid} · '+('Source' if m is None else SHORT[i-1]),font=font(21,True),fill='#183249')
   if m is None:d.text((12,405),'Red outline: source mask',font=font(19),fill='#B84B49')
   else:
    u=next(x for x in scores[m][cid]['units'] if x['id']==uid)
    for di,dim in enumerate('EPQ'):d.text((i*400+15+di*127,405),f'{dim} {u[dim]["score"]} '+('PASS' if u[dim]['pass'] else 'FAIL'),font=font(18,True),fill='#26836F' if u[dim]['pass'] else '#B84B49')
  jpg(p,tag+'_'+uid)
# Store actual adapter prompts for audit, no private fields.
spec=importlib.util.spec_from_file_location('pubprompt',ROOT/'src/evaluation/diffsynth/prompt.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
prompts={tag:{m:mod.build_prompt(jobs[m][cid]['public_job'],'picture' if m=='qwen_image_edit_2511' else 'image') for m in MODELS} for tag,cid in selected.items()}
(OUT/'actual_adapter_prompts.json').write_text(json.dumps(prompts,ensure_ascii=False,indent=2))
(OUT/'figure_provenance.json').write_text(json.dumps({'manifest_sha256':reports['qwen_image_21']['case_results'][0].get('manifest_sha256',json.loads((ROOT/'data/v2_2.6.0/statistics.json').read_text())['manifest_sha256']),'experiment_root':str(EXP),'protocol':'visual_locator_v2','variant':'mixed','case_ids':selected,'model_keys':list(MODELS),'overview_images':'original outputs, downsampled only; no mask outlines added','detail_images':'fixed-coordinate evaluator crops, source mask outline added in red','charts':'frozen report CSV; composition additionally shows all-unit pass without global gates'},ensure_ascii=False,indent=2))
print('Rendered',len(list(AS.glob('*.jpg'))),'JPEGs and',len(list(AS.glob('*.png'))),'charts to',OUT)
