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
    'flux3_klein': 'FLUX.3 Klein',
    'qwen_image_21': 'Qwen-Image-2.1',
    'flux2_klein_4b': 'FLUX.2 Klein-4B',
    'longcat_image_edit': 'LongCat-Image-Edit',
    'qwen_image_edit_2511': 'Qwen-Image-Edit-2511',
    'hidream_o1_image': 'HiDream-O1-Image',
    'step1x_edit': 'Step1X-Edit',
}
PATHS = {m: (m, m) for m in MODELS}
COLORS = dict(zip(MODELS, ['#8A61AF','#3575B4','#419881','#B65B74','#D18A26','#846B55','#697A9C']))
for directory in (OUT, FIG, ASSET):
    directory.mkdir(parents=True, exist_ok=True)
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
        w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n"); w.writeheader(); w.writerows(rows_)

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

# Keep the current report artifacts next to the repository report.
destination = Path('docs/reports/2.6.0')
destination.mkdir(parents=True, exist_ok=True)
for path in list(OUT.glob('*.csv')) + list(OUT.glob('failure_examples_*.json')):
    shutil.copy2(path, destination / path.name)
print(json.dumps({'models': len(MODELS), 'cases_per_model': 1084, 'destination': str(destination)}))

# Reviewed selections live in case_study_notes.json. Rendering never selects a
# replacement example automatically or changes any frozen generation/judge files.
if '--tables-only' not in __import__('sys').argv:
    import subprocess, sys
    subprocess.run([sys.executable, 'evaluation/render_model_case_studies.py'], check=True)
    subprocess.run([sys.executable, 'evaluation/render_current_report.py'], check=True)
