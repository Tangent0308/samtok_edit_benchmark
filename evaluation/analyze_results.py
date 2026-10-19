from __future__ import annotations
import csv, html, json, math, re, shutil
from pathlib import Path
from collections import Counter, defaultdict
from PIL import Image, ImageChops, ImageFilter, ImageDraw, ImageFont

EXP = Path('/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/benchmark_v2_2.6.0_baselines')
OUT = EXP / 'analysis'
FIG = OUT / 'figures'
CASE = OUT / 'case_studies'
ASSET = CASE / 'assets'
MODELS = {
    'qwen_image_21': 'Qwen-Image-2.1',
    'qwen_image_edit_2511': 'Qwen-Image-Edit-2511',
    'flux2_klein_4b': 'FLUX.2 Klein-4B',
    'flux3_klein': 'FLUX.3 Klein',
}
PATHS = {
    'qwen_image_21': ('qwen_image_21', 'qwen_image_21'),
    'qwen_image_edit_2511': ('qwen_image_edit_2511', 'qwen_image_edit_2511'),
    'flux2_klein_4b': ('flux2_klein_4b', 'flux2_klein_4b'),
    'flux3_klein': ('flux3_klein', 'flux3_klein'),
}
COLORS = {'qwen_image_21':'#4472c4','qwen_image_edit_2511':'#ed7d31','flux2_klein_4b':'#70ad47','flux3_klein':'#7030a0'}
DIM_COLORS = {'E':'#4472c4','P':'#ed7d31','Q':'#70ad47','unit_joint':'#7030a0'}


def read_jsonl(p):
    with open(p) as f:
        return [json.loads(x) for x in f if x.strip()]

jobs_by_model = {
    m: {x['job_id']: x for x in read_jsonl(EXP / 'judge_inputs' / paths[0] / 'judge_jobs.jsonl')}
    for m, paths in PATHS.items()
}
case_jobs = {m: {x['case_id']: x for x in jobs_by_model[m].values()} for m in MODELS}
reports = {
    m: json.load(open(EXP / 'judge' / paths[1] / 'Qwen3.8-Flash-Next-FP8' / 'report.json'))
    for m, paths in PATHS.items()
}
rows = {m: {x['job_id']: x for x in reports[m]['case_results']} for m in MODELS}
case_rows = {m: {x['case_id']: x for x in reports[m]['case_results']} for m in MODELS}
outputs = {
    m: {x['job_id']: x for x in read_jsonl(EXP / 'runs' / paths[1] / 'outputs.jsonl')}
    for m, paths in PATHS.items()
}

# Unit-level records joined to frozen public/private judge metadata.
unit_records = {m: [] for m in MODELS}
for m in MODELS:
    for job_id, cr in rows[m].items():
        job = jobs_by_model[m][job_id]
        pub_units = {u['id']: u for u in job['public_job']['units']}
        details = {d['id']: d for d in job['private_evaluation_details']}
        for u in cr['units']:
            pu = pub_units[u['id']]
            unit_records[m].append({
                'job_id': job_id, 'case_id': cr['case_id'], 'K': cr['expected_units'], 'unit_id': u['id'],
                'has_ref': bool(pu['has_ref']), 'locator': pu['locator'], 'operation': pu['operation'],
                'instruction': pu['instruction'], 'gold_ref': details[u['id']].get('gold_ref',''),
                'E': u['E'], 'P': u['P'], 'Q': u['Q'],
                'unit_joint': bool(u['E']['pass'] and u['P']['pass'] and u['Q']['pass']),
                'global_P': bool(cr.get('global_P',{}).get('pass',False)),
                'global_Q': bool(cr.get('global_Q',{}).get('pass',False)),
                'evidence': ' '.join([u['E'].get('evidence',''),u['P'].get('evidence',''),u['Q'].get('evidence',''),cr.get('global_P',{}).get('evidence',''),cr.get('global_Q',{}).get('evidence','')]),
            })


def pct(x): return f'{100*x:.2f}%'
def f3(x): return f'{x:.3f}'

def write_csv(path, rows_, fields):
    fields = list(fields)
    for row in rows_:
        for key in row:
            if key not in fields:
                fields.append(key)
    with open(path,'w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows_)

def esc(x): return html.escape(str(x), quote=True)

def svg_text(x,y,s,size=16,fill='#222',anchor='start',weight='normal'):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" font-family="Arial, sans-serif" font-weight="{weight}">{esc(s)}</text>'

def svg_chart(path, body, width=1100, height=650):
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/>{body}</svg>'
    path.write_text(svg)

def axes(x0,y0,w,h,ymax=1.0, ylabel='Rate'):
    s=[]
    for i in range(6):
        v=ymax*i/5; y=y0+h-h*v/ymax
        s.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x0+w}" y2="{y:.1f}" stroke="#dddddd"/>')
        s.append(svg_text(x0-10,y+5,f'{v:.1f}',13,'#666','end'))
    s.append(f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y0+h}" stroke="#555"/><line x1="{x0}" y1="{y0+h}" x2="{x0+w}" y2="{y0+h}" stroke="#555"/>')
    s.append(svg_text(x0-52,y0+h/2,ylabel,14,'#444','middle'))
    return ''.join(s)

# Main table.
main=[]
for m,label in MODELS.items():
    g=reports[m]['groups']['mixed/all']
    main.append({'model':label,'cases':g['cases'],'joint_pass':g['joint_pass'],'joint_rate':g['joint_success_rate'],
                 'E_unit_rate':g['dimension_rates']['E']['unit_micro_rate'],'P_unit_rate':g['dimension_rates']['P']['unit_micro_rate'],
                 'Q_unit_rate':g['dimension_rates']['Q']['unit_micro_rate'],'global_P_rate':g['global_P_rate'],'global_Q_rate':g['global_Q_rate']})
write_csv(OUT/'main_table.csv',main,list(main[0]))

# K analysis: per-position p_u = all E/P/Q pass for that unit position.
krows=[]
for m,label in MODELS.items():
    for K in range(2,6):
        crs=[x for x in rows[m].values() if x['expected_units']==K]
        if not crs: continue
        pos=[]
        for i in range(1,K+1):
            vals=[]
            for cr in crs:
                u=next((u for u in cr['units'] if u['id']==f'U{i}'),None)
                if u: vals.append(bool(u['E']['pass'] and u['P']['pass'] and u['Q']['pass']))
            pos.append(sum(vals)/len(vals) if vals else 0)
        prod=math.prod(pos)
        gp=sum(bool(x.get('global_P',{}).get('pass')) for x in crs)/len(crs)
        gq=sum(bool(x.get('global_Q',{}).get('pass')) for x in crs)/len(crs)
        measured=sum(bool(x['joint_pass']) for x in crs)/len(crs)
        krows.append({'model':label,'model_key':m,'K':K,'cases':len(crs),'measured_joint_rate':measured,'p_u_product':prod,'global_adjusted_independence':gp*gq*prod,'global_P_rate':gp,'global_Q_rate':gq,**{f'p_U{i}':pos[i-1] for i in range(1,K+1)}})
write_csv(OUT/'k_jointpass.csv',krows,list(krows[0]))

# Ref/no-ref and locator aggregation.
locrows=[]
for m,label in MODELS.items():
    for group_key, vals in [('ref',[x for x in unit_records[m] if x['has_ref']]),('no-ref',[x for x in unit_records[m] if not x['has_ref']])]:
        n=len(vals); locrows.append({'model':label,'model_key':m,'group':group_key,'n_units':n,'unit_joint_rate':sum(x['unit_joint'] for x in vals)/n,'E_rate':sum(x['E']['pass'] for x in vals)/n,'P_rate':sum(x['P']['pass'] for x in vals)/n,'Q_rate':sum(x['Q']['pass'] for x in vals)/n})
    for loc in ['point','box','mask']:
        vals=[x for x in unit_records[m] if x['locator']==loc]
        n=len(vals); locrows.append({'model':label,'model_key':m,'group':loc,'n_units':n,'unit_joint_rate':sum(x['unit_joint'] for x in vals)/n,'E_rate':sum(x['E']['pass'] for x in vals)/n,'P_rate':sum(x['P']['pass'] for x in vals)/n,'Q_rate':sum(x['Q']['pass'] for x in vals)/n})
write_csv(OUT/'locator_impact.csv',locrows,list(locrows[0]))

# Failure classifier. Priority keeps stacked categories mutually exclusive.
def classify_failure(x):
    t=(x['evidence']+' '+x['instruction']+' '+x['gold_ref']).lower()
    marker_positive=r'leaked|visible (?:locator|annotation|edit|u[1-5])|(?:locator|annotation) (?:box|marker|label)|overlay (?:artifact|appears|is|spills|painted)|marker (?:drawn|appears|visible|leaked)|labelled? ["\']?u[1-5]|translucent (?:blue|red|yellow|green) (?:box|rectangle)|yellow box (?:with|labelled)|blue box (?:with|labelled)|red box (?:with|labelled)|green box (?:with|labelled)|colored box|rectangle (?:overlay|artifact)'
    marker_negative=r'(?:no|without|none|not) (?:visible )?(?:locator|annotation|edit|u[1-5])? ?(?:markers?|overlays?|boxes?|labels?)'
    if re.search(marker_positive,t) and not (re.search(marker_negative,t) and not re.search(r'leaked|artifact|spills|painted|drawn|appears|visible',t)):
        return 'locator marker in output'
    noexec=r'not (?:execut|perform|done|completed|present|visible|added|changed|removed|recolou?r)|no (?:visible )?(?:change|edit|addition)|unchanged|still (?:present|the same|original)|fails? to|did not|does not|absent|missing|nothing was|no usable'
    if x['E']['score']<=1 and re.search(noexec,t): return 'not executed'
    occ=r'occlud|occlusion|behind|hidden|partially|fragment|leftover|remaining|missed|covered|obscur|visible pieces|visible fragment|under the'
    if re.search(occ,t): return 'occluded fragments/leftovers'
    wrong=r'wrong (?:instance|person|object|target|part)|other (?:person|object|instance)|different (?:person|object|instance)|another (?:person|object|instance)|selected .* (?:wrong|incorrect)|incorrect (?:instance|target)|edited the wrong'
    if re.search(wrong,t): return 'wrong instance'
    gran=r'whole|entire|full (?:garment|coat|shirt|dress|jacket|body|object)|all of|rest of|over-?edit|too much|larger region|recolored .* (?:coat|shirt|jacket|garment) instead|changed .* entire|entire .* instead|sleeve.*(?:coat|jacket|shirt)|coat.*(?:sleeve|part)'
    if re.search(gran,t): return 'wrong granularity'
    return 'other E failure'

failure_rows=[]
for m,label in MODELS.items():
    c=Counter()
    examples=defaultdict(list)
    for x in unit_records[m]:
        if not x['E']['pass']:
            cat=classify_failure(x); c[cat]+=1
            if len(examples[cat])<5: examples[cat].append({'case_id':x['case_id'],'unit_id':x['unit_id'],'instruction':x['instruction'],'evidence':x['E']['evidence']})
    for cat,n in c.items(): failure_rows.append({'model':label,'model_key':m,'category':cat,'count':n})
    (OUT/f'failure_examples_{m}.json').write_text(json.dumps(examples,ensure_ascii=False,indent=2))
write_csv(OUT/'failure_modes.csv',failure_rows,['model','model_key','category','count'])

# SVG charts. All labels are English so the figures render consistently without CJK font fallback.
def chart_axes(x0,y0,w,h,ylabel='Rate',ticks=5):
    s=[]
    for i in range(ticks+1):
        v=i/ticks; y=y0+h-h*v
        s.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x0+w}" y2="{y:.1f}" stroke="#e5e7eb" stroke-width="1"/>')
        s.append(svg_text(x0-12,y+5,f'{v:.0%}',13,'#4b5563','end'))
    s.append(f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y0+h}" stroke="#374151" stroke-width="1.5"/><line x1="{x0}" y1="{y0+h}" x2="{x0+w}" y2="{y0+h}" stroke="#374151" stroke-width="1.5"/>')
    s.append(f'<text x="{x0-62}" y="{y0+h/2}" font-size="14" fill="#374151" text-anchor="middle" font-family="Arial, sans-serif" transform="rotate(-90 {x0-62} {y0+h/2})">{esc(ylabel)}</text>')
    return ''.join(s)

# K chart: measured lines and dashed unit-independence baselines share one aligned axis.
W,H=1200,700; x0,y0,w,h=105,115,1015,450
body=svg_text(W/2,42,'JointPass vs. Number of Targets',26,'#111827','middle','bold')
body+=svg_text(W/2,68,'Solid = measured; dashed = unit-independent expectation ∏ pᵤ',14,'#4b5563','middle')
body+=chart_axes(x0,y0,w,h,'JointPass rate')
xs={k:x0+(k-2)*w/3 for k in range(2,6)}
for k,x in xs.items(): body+=svg_text(x,y0+h+32,f'K={k}',15,'#374151','middle')
for m,label in MODELS.items():
    vals=[next(r for r in krows if r['model_key']==m and r['K']==k)['measured_joint_rate'] for k in range(2,6)]
    pts=' '.join(f'{xs[k]:.1f},{y0+h*(1-v):.1f}' for k,v in zip(range(2,6),vals))
    body+=f'<polyline points="{pts}" fill="none" stroke="{COLORS[m]}" stroke-width="3" stroke-linejoin="round"/>'
    for k,v in zip(range(2,6),vals): body+=f'<circle cx="{xs[k]:.1f}" cy="{y0+h*(1-v):.1f}" r="5" fill="{COLORS[m]}"/>'
for m,label in MODELS.items():
    vals=[next(r for r in krows if r['model_key']==m and r['K']==k)['p_u_product'] for k in range(2,6)]
    pts=' '.join(f'{xs[k]:.1f},{y0+h*(1-v):.1f}' for k,v in zip(range(2,6),vals))
    body+=f'<polyline points="{pts}" fill="none" stroke="{COLORS[m]}" stroke-width="2" stroke-dasharray="8,6" opacity="0.75"/>'
for i,(m,label) in enumerate(MODELS.items()):
    xx=110+i*245; body+=f'<line x1="{xx}" y1="625" x2="{xx+28}" y2="625" stroke="{COLORS[m]}" stroke-width="4"/>'+svg_text(xx+38,630,label,13)
body+=f'<line x1="110" y1="657" x2="138" y2="657" stroke="#374151" stroke-width="3"/>'+svg_text(148,662,'Measured',13)+f'<line x1="255" y1="657" x2="283" y2="657" stroke="#374151" stroke-width="3" stroke-dasharray="8,6"/>'+svg_text(293,662,'Independent baseline',13)
svg_chart(FIG/'k_jointpass.svg',body,W,H)

# Locator impact: two panels use exactly the same y scale and chart geometry.
def grouped_panel(x0,title,groups,metric='unit_joint_rate'):
    pw,py,ph=500,115,420; plot_x=x0+62; plot_w=pw-82; base=py+ph
    s=svg_text(x0+pw/2,48,title,20,'#111827','middle','bold')+chart_axes(plot_x,py,plot_w,ph,'Unit joint-pass rate')
    centers=[plot_x+plot_w*(i+0.5)/len(groups) for i in range(len(groups))]
    bw=24; gap=7; total=len(MODELS)*bw+(len(MODELS)-1)*gap
    for gi,g in enumerate(groups):
        gx=centers[gi]; s+=svg_text(gx,base+32,g,15,'#374151','middle')
        for mi,(m,label) in enumerate(MODELS.items()):
            val=next(r for r in locrows if r['model_key']==m and r['group']==g)[metric]
            bx=gx-total/2+mi*(bw+gap); by=base-ph*val
            s+=f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw}" height="{ph*val:.1f}" rx="2" fill="{COLORS[m]}"/>'
    return s
W,H=1250,700
body=svg_text(W/2,38,'Locator Impact on Unit Joint-Pass Rate',26,'#111827','middle','bold')
body+=grouped_panel(55,'Reference vs. no-reference',['ref','no-ref'])+grouped_panel(650,'Locator type',['point','box','mask'])
for i,(m,label) in enumerate(MODELS.items()):
    xx=95+(i%2)*260; yy=610+(i//2)*32; body+=f'<rect x="{xx}" y="{yy-12}" width="14" height="14" rx="2" fill="{COLORS[m]}"/>'+svg_text(xx+23,yy,label,13)
svg_chart(FIG/'locator_impact.svg',body,W,H)

# Failure modes: normalized stacked bars with a two-row legend outside the plot.
cat_order=['wrong instance','wrong granularity','occluded fragments/leftovers','not executed','locator marker in output','other E failure']
cat_labels=['Wrong instance','Wrong granularity','Occluded / leftover','Not executed','Locator marker','Other']
cat_colors=['#c2413b','#e98b37','#e3b341','#4f81bd','#8064a2','#9ca3af']
W,H=1250,760; x0,y0,w,h=130,95,1000,450
body=svg_text(W/2,40,'E-Failure Modes',26,'#111827','middle','bold')
body+=svg_text(W/2,68,'Mutually exclusive categories; labels show counts',14,'#4b5563','middle')+chart_axes(x0,y0,w,h,'Share of E failures')
centers=[260,510,760,1010]; barw=105
for i,(m,label) in enumerate(MODELS.items()):
    xx=centers[i]; total=sum(r['count'] for r in failure_rows if r['model_key']==m); cur=y0+h
    for cat,col in zip(cat_order,cat_colors):
        n=next((r['count'] for r in failure_rows if r['model_key']==m and r['category']==cat),0); frac=n/total if total else 0; hh=h*frac; cur-=hh
        body+=f'<rect x="{xx-barw/2}" y="{cur:.1f}" width="{barw}" height="{hh:.1f}" fill="{col}"/>'
        if frac>=.08: body+=svg_text(xx,cur+hh/2+5,str(n),13,'white','middle','bold')
    body+=svg_text(xx,y0+h+30,label,14,'#374151','middle')+svg_text(xx,y0+h+50,f'n={total}',12,'#6b7280','middle')
for i,(label,col) in enumerate(zip(cat_labels,cat_colors)):
    xx=100+(i%3)*360; yy=625+(i//3)*35; body+=f'<rect x="{xx}" y="{yy-12}" width="14" height="14" rx="2" fill="{col}"/>'+svg_text(xx+23,yy,label,13)
svg_chart(FIG/'failure_modes.svg',body,W,H)

# Case selection.
case_ids=sorted(case_rows['flux3_klein'])
def is_joint(m,cid): return bool(case_rows[m][cid]['joint_pass'])
selected={}
all_fail=[cid for cid in case_ids if not any(is_joint(m,cid) for m in MODELS)]
one_success=[cid for cid in case_ids if sum(is_joint(m,cid) for m in MODELS)==1]
selected['all_models_fail']=all_fail[0]
selected['only_one_model_success']=one_success[0]
# Granularity: rank cases with a classified granularity E failure, favor several models and K>=2.
gran=[]
for cid in case_ids:
    hits=[]
    for m in MODELS:
        for x in unit_records[m]:
            if x['case_id']==cid and not x['E']['pass'] and classify_failure(x)=='wrong granularity': hits.append((m,x['unit_id']))
    if hits: gran.append((len(hits), cid, hits))
gran.sort(reverse=True)
explicit_gran=[]
for _, cid, _ in gran:
    for m in MODELS:
        for x in unit_records[m]:
            if x['case_id']==cid and not x['E']['pass'] and classify_failure(x)=='wrong granularity' and re.search(r'whole|entire|all of|instead of|support',x['E']['evidence'],re.I):
                explicit_gran.append(cid); break
        if explicit_gran and explicit_gran[-1]==cid: break
    if explicit_gran: break
selected['granularity_error']='v2-sa_6392020' if 'v2-sa_6392020' in case_ids else (explicit_gran[0] if explicit_gran else (gran[0][1] if gran else all_fail[0]))
# No-ref localization: favor a no-ref E failure with ref success in same model, and multiple model failures.
loccand=[]
for cid in case_ids:
    j=case_jobs['flux3_klein'][cid]
    units=j['public_job']['units']; noids={u['id'] for u in units if not u['has_ref']}; refids={u['id'] for u in units if u['has_ref']}
    if not noids: continue
    score=0; detail=[]
    for m in MODELS:
        cr=case_rows[m][cid]
        us={u['id']:u for u in cr['units']}
        nf=sum(not us[i]['E']['pass'] for i in noids); rp=sum(us[i]['E']['pass'] for i in refids)
        score += 2*nf + rp
        detail.append((m,nf,rp))
    loccand.append((score,cid,detail))
loccand.sort(reverse=True)
selected['no_ref_localization_failure']=loccand[0][1] if loccand else all_fail[1]
(OUT/'selected_cases.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2))

# Render case studies.
def font(size=22):
    try: return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',size)
    except: return ImageFont.load_default()
def thumb(im,size=(360,260)):
    x=im.copy().convert('RGB'); x.thumbnail(size,Image.Resampling.LANCZOS); return x
def outlined(crop, mask_path, box, color=(255,0,0)):
    with Image.open(mask_path) as mm: mask=mm.convert('L').crop(tuple(box)).point(lambda v:255 if v>0 else 0)
    width=max(2,round(max(crop.size)/180)); contour=ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(2*width+1)),mask)
    y=crop.copy().convert('RGB'); y.paste(color,mask=contour); return y

def case_job(cid): return case_jobs['flux3_klein'][cid]
for tag,cid in selected.items():
    j=case_job(cid); ifolder=ASSET/tag; ifolder.mkdir(parents=True,exist_ok=True)
    shutil.copy2(j['source_image'],ifolder/'source.jpg')
    shutil.copy2(j['public_job']['images'][1],ifolder/'locator.png')
    # overview
    imgs=[('Source',j['source_image']),('Locator input\n(visual_locator_v2)',j['public_job']['images'][1])]
    for m,label in MODELS.items():
        mj=case_jobs[m][cid]
        imgs.append((label,outputs[m][mj['job_id']]['output_image']))
    cells=[]
    for label,p in imgs:
        im=thumb(Image.open(p)); cell=Image.new('RGB',(380,300),'white'); cell.paste(im,((380-im.width)//2,28)); ImageDraw.Draw(cell).text((10,6),label,fill='black',font=font(18)); cells.append(cell)
    ov=Image.new('RGB',(380*len(cells),300),'white')
    for i,c in enumerate(cells): ov.paste(c,(i*380,0))
    ov.save(ifolder/'overview.jpg',quality=90)
    # details
    for d in j['private_evaluation_details']:
        uid=d['id']; rowhtml=[]
        source_plain=Image.open(d['source_crop']).convert('RGB')
        source=outlined(source_plain,d['gold_source_mask'],d['crop_box_xyxy'])
        cols=[('Source + mask',source)]
        for m,label in MODELS.items():
            # Use the crop built from the model's own input/output binding.
            mj=case_jobs[m][cid]
            md=next(x for x in mj['private_evaluation_details'] if x['id']==uid)
            outplain=Image.open(md['output_crop']).convert('RGB')
            cols.append((label+' + mask',outlined(outplain,md['gold_source_mask'],md['crop_box_xyxy'])))
        cw,ch=330,260; panel=Image.new('RGB',(cw*len(cols),ch),'white'); draw=ImageDraw.Draw(panel)
        for i,(label,im) in enumerate(cols):
            im.thumbnail((cw-10,ch-35),Image.Resampling.LANCZOS); panel.paste(im,(i*cw+(cw-im.width)//2,30)); draw.text((i*cw+8,5),label,fill='black',font=font(15))
        panel.save(ifolder/f'{uid}_detail.jpg',quality=90)

# Case HTML with status badges and evidence.
html_parts=['<!doctype html><meta charset="utf-8"><title>SAMTok v2.6.0 case studies</title><style>body{font-family:Arial,sans-serif;margin:24px;color:#222}h1{margin-top:0}.case{border-top:2px solid #444;margin-top:36px;padding-top:20px}.overview{max-width:100%;border:1px solid #aaa}.detail{max-width:100%;border:1px solid #aaa}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.ok{color:#087f23;font-weight:bold}.bad{color:#b00020;font-weight:bold}.small{font-size:13px;color:#555}.evidence{font-size:13px;line-height:1.35}</style><h1>SAMTok Edit Benchmark 2.6.0 案例研究</h1>']
for tag,cid in selected.items():
    j=case_job(cid); html_parts.append(f'<section class="case"><h2>{esc(tag)} — {esc(cid)}</h2><p class="small">{esc(j["public_job"]["prompt"])}</p><img class="overview" src="assets/{tag}/overview.jpg">')
    for d in j['private_evaluation_details']:
        uid=d['id']; html_parts.append(f'<h3>{uid}: {esc(d["actual_instruction"])}</h3><img class="detail" src="assets/{tag}/{uid}_detail.jpg"><div class="grid">')
        for m,label in MODELS.items():
            mj=case_jobs[m][cid]
            cr=rows[m][mj['job_id']]; u=next(u for u in cr['units'] if u['id']==uid); cls='ok' if u['E']['pass'] and u['P']['pass'] and u['Q']['pass'] else 'bad'
            statuses=' '.join(f'{dimm}: {"PASS" if u[dimm]["pass"] else "FAIL"} ({u[dimm]["score"]})' for dimm in 'EPQ')
            html_parts.append(f'<div><b>{esc(label)}</b><div class="{cls}">{esc(statuses)}</div><p class="evidence"><b>E:</b> {esc(u["E"]["evidence"])}<br><b>P:</b> {esc(u["P"]["evidence"])}<br><b>Q:</b> {esc(u["Q"]["evidence"])}</p></div>')
        html_parts.append('</div>')
    html_parts.append('</section>')
(CASE/'index.html').write_text('\n'.join(html_parts))

# Human-checked Chinese translations for the four selected case prompts.
PROMPT_ZH = {
    ('v2-sa_10044652','U1'):'将选定区域替换为海军蓝飞行员夹克。',
    ('v2-sa_10044652','U2'):'将受损车辆后方的白色汽车改为银色。',
    ('v2-sa_10044652','U3'):'移除选定区域。',
    ('v2-sa_10006079','U1'):'将女性的黄色图案背心改为青绿色。',
    ('v2-sa_10006079','U2'):'移除选定区域。',
    ('v2-sa_6392020','U1'):'移除选定区域。',
    ('v2-sa_6392020','U2'):'将中间背对镜头、长发女性的红色上衣替换为短袖连帽上衣。',
    ('v2-sa_6392020','U3'):'在左侧坐着男子的 T 恤上缝制一个小翻盖胸袋。',
    ('v2-sa_6392020','U4'):'将选定区域改为橙色。',
    ('v2-sa_6392020','U5'):'移除左后方双手背在身后的人的 T 恤袖子。',
    ('v2-sa_7813406','U1'):'将选定区域改为深红色。',
    ('v2-sa_7813406','U2'):'将前景黄色衣服男子图像右侧的鞋替换为黑色过膝靴。',
    ('v2-sa_7813406','U3'):'在选定区域添加一个矩形侧袋。',
    ('v2-sa_7813406','U4'):'将最右侧表演者图像左侧的红色靴子替换为白色低帮帆布鞋。',
    ('v2-sa_7813406','U5'):'移除选定区域，使其达到膝盖长度。',
}
LOC_ZH={'point':'点定位','box':'框定位','mask':'掩码定位','none':'无额外定位'}
def prompt_zh(job):
    head='编辑第一张图并保持原始尺寸。执行所有编号指令。第二张图（如有）只提供带标签的定位信息，输出中不得保留定位标记。定位器选择源图实例；命名部件进一步限定编辑范围。添加操作中，定位器选择支撑物或空间参考，不是新物体的轮廓。保留所有未请求内容。'
    lines=[head]
    for u in job['public_job']['units']:
        ref='有参考图' if u['has_ref'] else '无参考图'
        lines.append(f"{u['id']} [{ref}；{LOC_ZH.get(u['locator'],u['locator'])}]：{PROMPT_ZH.get((job['case_id'],u['id']),u['instruction'])}")
    return '\n'.join(lines)

# Actual input example for the formal full evaluation. Both images are the
# files passed to the editor; Image 2 is the color locator rendered on source
# coordinates, not an evaluator overlay.
def input_setting_example():
    cid = 'v2-sa_10006079'
    job = case_jobs['qwen_image_21'][cid]['public_job']
    source_path, locator_path = job['images'][:2]
    with Image.open(source_path) as src, Image.open(locator_path) as loc:
        source = src.convert('RGB')
        locator = loc.convert('RGB')
    W, H = 1100, 430
    canvas = Image.new('RGB', (W, H), 'white')
    draw = ImageDraw.Draw(canvas)
    try:
        title_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 22)
        label_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 17)
    except OSError:
        title_font = label_font = ImageFont.load_default()
    draw.text((18, 14), 'Actual visual_locator_v2 input', fill='#111827', font=title_font)
    for x, im, label in [(40, source, 'Image 1: clean source'), (570, locator, 'Image 2: color locator on source coordinates')]:
        draw.text((x, 55), label, fill='#374151', font=label_font)
        im.thumbnail((490, 330), Image.Resampling.LANCZOS)
        canvas.paste(im, (x + (490 - im.width) // 2, 85 + (330 - im.height) // 2))
    canvas.save(FIG / 'input_setting_visual_locator_v2.jpg', quality=88, optimize=True)

input_setting_example()

# Markdown report.
md=['# SAMTok Edit Benchmark 2.6.0 结果分析','',f'生成时间：2026-10-19；四个模型均为完整 1084/1084 judge 评分。Judge 模型：`Qwen3.8-Flash-Next-FP8`。','', '## 1. 主表','', '| 模型 | JointPass | E 单元通过率 | P 单元通过率 | Q 单元通过率 | global_P | global_Q |','|---|---:|---:|---:|---:|---:|---:|']
for r in main: md.append(f"| {r['model']} | {r['joint_pass']}/{r['cases']} ({pct(r['joint_rate'])}) | {pct(r['E_unit_rate'])} | {pct(r['P_unit_rate'])} | {pct(r['Q_unit_rate'])} | {pct(r['global_P_rate'])} | {pct(r['global_Q_rate'])} |")
md += ['', 'JointPass 要求每个单元的 E/P/Q 都通过，同时 global_P 与 global_Q 通过。E 反映执行是否完成，P 反映非目标内容保持，Q 反映编辑质量。整体难度由 JointPass 体现；从单元级指标看，模型之间的主要差异可按 E、P、Q 三列比较。', '', '## 1.1 评测方式与输入 setting', '', '- 每个 job 来自 `data/v2_2.6.0/cases.jsonl`，编辑模型收到两张图和一段公开 instruction，并只输出完整 RGB 图片。', '- Image 1 是干净 source image。Image 2 是 `visual_locator_v2` / `mixed` 的彩色 locator：point、box、mask 和 U 标签直接绘制在 source 的对应坐标上。', '- prompt 明确要求第二张图只用于定位，输出中不得保留 point、box、mask、颜色或 U 标签。`ref` 只表示 unit 的语义属性，不会增加第三张图片。', '', '![实际评测输入 setting](figures/input_setting_visual_locator_v2.jpg)', '', '图中展示的是编辑模型实际收到的两张输入图；局部案例图中的红色轮廓属于 evaluator 对齐可视化，不是模型输入或模型输出。', '', '### 1.2 评分与结果绑定', '', '- Judge 使用 `Qwen3.8-Flash-Next-FP8`，通过 vLLM 以 tensor parallel size 8、temperature 0、seed 0 运行。每个 U 评分 E/P/Q；E=4、P/Q≥3 视为单元通过，整图还要求 global_P/global_Q 通过。', '- 本报告主表使用完整 1,084/1,084 judge 结果；结果与输入 manifest、输出图和 prompt 通过 job/input digest 绑定。', '- 外部评测结果根：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/benchmark_v2_2.6.0_baselines/`。以下表格路径均相对于该目录；仓库内报告为 `docs/reports/2.6.0/RESULT_ANALYSIS_2_6_0_ZH.md`。', '', '| 模型 | 输入 job | 生成输出 | Judge report |', '|---|---|---|---|', '| Qwen-Image-2.1 | `judge_inputs/qwen_image_21/judge_jobs.jsonl` | `runs/qwen_image_21/outputs.jsonl` | `judge/qwen_image_21/Qwen3.8-Flash-Next-FP8/report.json` |', '| Qwen-Image-Edit-2511 | `judge_inputs/qwen_image_edit_2511/judge_jobs.jsonl` | `runs/qwen_image_edit_2511/outputs.jsonl` | `judge/qwen_image_edit_2511/Qwen3.8-Flash-Next-FP8/report.json` |', '| FLUX.2 Klein-4B | `judge_inputs/flux2_klein_4b/judge_jobs.jsonl` | `runs/flux2_klein_4b/outputs.jsonl` | `judge/flux2_klein_4b/Qwen3.8-Flash-Next-FP8/report.json` |', '| FLUX.3 Klein | `judge_inputs/flux3_klein/judge_jobs.jsonl` | `runs/flux3_klein/outputs.jsonl` | `judge/flux3_klein/Qwen3.8-Flash-Next-FP8/report.json` |', '', '## 2. 多目标组合代价','', '![JointPass 随 K 变化](figures/k_jointpass.svg)','', '实线是实测 JointPass，虚线是各单元 E/P/Q 联合通过率乘积 `∏u p_u`。对 K 个目标，令 `p_u` 为位置 Uu 的单元联合通过率；实测曲线低于虚线表示多个请求之间存在额外干扰。图和 `k_jointpass.csv` 另外给出 `global_P × global_Q × ∏u p_u`，用于解释全图保持与整体质量对最终 JointPass 的额外压缩。', '', '## 3. 定位方式的影响','', '![定位方式影响](figures/locator_impact.svg)','', '单元级 `unit_joint` 定义为该单元 E、P、Q 同时通过。左图先比较 ref 和 no-ref；no-ref 指令只写 `the selected region`，模型必须从 locator 选择实例。右图再比较 point、box、mask 三种 locator。完整 E/P/Q 与样本数见 `locator_impact.csv`。','', '| 模型 | ref unit-joint | no-ref unit-joint | no-ref - ref |','|---|---:|---:|---:|']
for m,label in MODELS.items():
    ref=next(r for r in locrows if r['model_key']==m and r['group']=='ref')['unit_joint_rate']
    noref=next(r for r in locrows if r['model_key']==m and r['group']=='no-ref')['unit_joint_rate']
    md.append(f"| {label} | {pct(ref)} | {pct(noref)} | {pct(noref-ref)} |")
md += ['', '| 模型 | point | box | mask |','|---|---:|---:|---:|']
for m,label in MODELS.items():
    vals={r['group']:r['unit_joint_rate'] for r in locrows if r['model_key']==m}
    md.append(f"| {label} | {pct(vals['point'])} | {pct(vals['box'])} | {pct(vals['mask'])} |")
md += ['', '## 4. E 失败模式','', '![E 失败模式](figures/failure_modes.svg)','', '失败模式只统计 E 未通过的单元，按 judge 证据关键词和指令语义做互斥归类，优先级为：定位框/U 标签泄漏、未执行、遮挡碎片/残留、错误实例、粒度错误、其他。该统计用于定位问题，原始证据保存在每个模型的 `failure_examples_*.json`；`other E failure` 代表证据无法可靠映射到前五类。','', '| 模型 | 失败单元数 | 定位标记 | 未执行 | 遮挡碎片/残留 | 错误实例 | 粒度错误 | 其他 |','|---|---:|---:|---:|---:|---:|---:|---:|']
for m,label in MODELS.items():
    d={r['category']:r['count'] for r in failure_rows if r['model_key']==m}; total=sum(d.values())
    md.append(f"| {label} | {total} | {d.get('locator marker in output',0)} | {d.get('not executed',0)} | {d.get('occluded fragments/leftovers',0)} | {d.get('wrong instance',0)} | {d.get('wrong granularity',0)} | {d.get('other E failure',0)} |")
md += ['', '## 案例研究','', '以下内容已直接嵌入本报告。每个案例的总览图从左到右依次为原图、实际发送的 visual locator 输入和四个模型输出；每个 U 的局部图均叠加源 mask 轮廓。状态表中的 E/P/Q 是该 U 的逐维 judge 结果；HTML 版 [`case_studies/index.html`](case_studies/index.html) 保留了更宽的排版和完整证据。选例分别覆盖所有模型失败、只有一个模型成功、实例/部件粒度错误和 no-ref 定位失败。']
for tag,cid in selected.items():
    j=case_job(cid)
    md += ['', f'### {tag}：`{cid}`','', 'English prompt:', '', '```text', j['public_job']['prompt'], '```', '', '中文翻译：', '', '```text', prompt_zh(j), '```', '', f'![{cid} 原图、定位图和模型输出总览](case_studies/assets/{tag}/overview.jpg)','']
    for d in j['private_evaluation_details']:
        uid=d['id']; md += [f'#### {uid}：{d["actual_instruction"]}','',f'![{cid} {uid} 局部图（源 mask 轮廓）](case_studies/assets/{tag}/{uid}_detail.jpg)','', '| 模型 | E | P | Q |','|---|---:|---:|---:|']
        for m,label in MODELS.items():
            mj=case_jobs[m][cid]
            cr=rows[m][mj['job_id']]; u=next(u for u in cr['units'] if u['id']==uid)
            def mark(dim): return f'{"PASS" if u[dim]["pass"] else "FAIL"} ({u[dim]["score"]})'
            md.append(f'| {label} | {mark("E")} | {mark("P")} | {mark("Q")} |')
        md.append('')
md += ['### 产物','', '- `main_table.csv`：主表数据','- `k_jointpass.csv`：K 曲线与独立基线数据','- `locator_impact.csv`：ref/no-ref、point/box/mask 单元级数据','- `failure_modes.csv`：失败模式计数','- `figures/*.svg`：三张可直接打开的 SVG 图','- `case_studies/index.html`：同一批案例的宽屏版页面','']
(OUT/'RESULT_ANALYSIS_2_6_0_ZH.md').write_text('\n'.join(md))
print(json.dumps({'main':main,'selected_cases':selected,'k_rows':len(krows),'locator_rows':len(locrows),'failure_rows':len(failure_rows)},ensure_ascii=False,indent=2))
