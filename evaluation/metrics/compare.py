"""Comparable-cohort tables, case-clustered intervals, and aggregate plots."""
from __future__ import annotations
import argparse
from collections import defaultdict, Counter
import html
import json
from pathlib import Path
import numpy as np
from evaluation.common import BASELINE_VISUAL_PROTOCOL, atomic_write_json, read_jsonl
from evaluation.metrics.report import summarize

AXES = ('edit', 'preservation', 'quality')
NAMES = {'qwen': 'Qwen-Edit-2511', 'flux': 'FLUX.2-klein-4B', 'qwen21': 'Qwen-Image-2.1',
         'replan_qwen': 'RePlan + Qwen', 'replan_flux': 'RePlan + FLUX'}
ORDER = list(NAMES)
COHORT_NAMES = {'current_full656': '656-case benchmark', 'current_common': 'Shared cases and settings'}
SETTINGS = ('text_only', 'mask_annotation', 'box_annotation', 'point_annotation')

def interval(records, axis):
    groups = defaultdict(list)
    for r in records:
        value = r.get('scores', {}).get(axis)
        if value is not None:
            groups[r['sample']['eval_index']].append(value)
    if not groups:
        return None
    # Resample source cases, preserving dependence among their four settings.
    values = np.array([[np.sum(v), len(v)] for v in groups.values()])
    rng = np.random.default_rng(20260920)
    draws = rng.integers(0, len(values), (2000, len(values)))
    totals = values[draws].sum(axis=1)
    means = totals[:,0] / totals[:,1]
    return [float(x) for x in np.quantile(means, [.025, .975])]

def groups_for(records):
    by_method = defaultdict(list)
    for r in records:
        by_method[r['sample']['method']].append(r)
    return {m: {'cases': len({r['sample']['eval_index'] for r in rs}), **summarize(rs),
                'ci95_case_bootstrap': {a: interval(rs, a) for a in AXES}}
            for m, rs in sorted(by_method.items(), key=lambda kv: ORDER.index(kv[0]))}

def cohorts(records):
    result = {}
    if any(r['sample']['protocol'] != BASELINE_VISUAL_PROTOCOL for r in records):
        raise ValueError('Generation inputs do not match the benchmark protocol')
    current = records
    full = [r for r in current if r['sample'].get('cohort') == 'full656']
    if full:
        result['current_full656'] = full
    methods = set(r['sample']['method'] for r in current)
    if len(methods) >= 2:
        keys = {m: {(r['sample']['eval_index'], r['sample']['setting']) for r in current
                    if r['sample']['method'] == m} for m in methods}
        common = set.intersection(*keys.values())
        if any(v != common for v in keys.values()) or len(full) != len(current):
            result['current_common'] = [r for r in current if
                (r['sample']['eval_index'], r['sample']['setting']) in common]
    return result

def draw_charts(cohort, records, table, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    methods = list(table)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5), sharey=True)
    for ax, key in zip(axes, AXES):
        means = [table[m].get(key, {}).get('mean_on_decidable') or 0 for m in methods]
        bounds = [table[m]['ci95_case_bootstrap'][key] or [v, v] for m, v in zip(methods, means)]
        errors = np.array([[max(0, v-b[0]), max(0, b[1]-v)] for v, b in zip(means, bounds)]).T
        ax.barh(range(len(methods)), means, xerr=errors, color='#427caa', capsize=3)
        ax.set_xlim(0, 4.35); ax.set_xticks(range(5)); ax.set_title(key.capitalize()+' (0-4)')
        ax.set_yticks(range(len(methods)), [NAMES[m] for m in methods]); ax.invert_yaxis()
        for y, v in enumerate(means): ax.text(v+.08, y, f'{v:.2f}', va='center', fontsize=9)
    fig.suptitle(COHORT_NAMES[cohort]+' | Qwen3.8-27B judge, pair_v2\n95% source-case bootstrap intervals; not human gold', fontsize=11)
    fig.tight_layout(); fig.savefig(output/(cohort+'_axes.png'), dpi=170); plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(14, max(3.6, len(methods)*.65)))
    for ax, key in zip(axes, AXES):
        matrix = [[np.mean([r['scores'][key] for r in records if r['sample']['method']==m
                           and r['sample']['setting']==s and r.get('scores', {}).get(key) is not None])
                   for s in SETTINGS] for m in methods]
        im = ax.imshow(matrix, vmin=0, vmax=4, cmap='YlGnBu')
        ax.set_xticks(range(4), ['Text', 'Mask', 'Box', 'Point']); ax.set_yticks(range(len(methods)), [NAMES[m] for m in methods])
        ax.set_title(key.capitalize())
        for y, row in enumerate(matrix):
            for x, v in enumerate(row): ax.text(x,y,f'{v:.2f}',ha='center',va='center',color='white' if v>2.6 else 'black')
    fig.suptitle(COHORT_NAMES[cohort]+' | Mean scores by input setting', fontsize=11)
    fig.tight_layout(); fig.savefig(output/(cohort+'_settings.png'), dpi=170); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, max(3.8,len(methods)*.6)))
    for ax, group_key, labels in zip(axes, ('edit_type','region_count'),
                                   (['add','remove','replace','mixed'],[1,2])):
        matrix=[]
        for m in methods:
            row=[]
            for label in labels:
                rs=[r for r in records if r['sample']['method']==m and
                    (r['sample']['edit_type'] if group_key=='edit_type' else len(r['sample']['regions']))==label]
                vs=[r['scores']['edit'] for r in rs if r.get('scores',{}).get('edit') is not None]
                row.append(np.mean(vs) if vs else np.nan)
            matrix.append(row)
        ax.imshow(matrix,vmin=0,vmax=4,cmap='YlGnBu')
        ax.set_yticks(range(len(methods)),[NAMES[m] for m in methods])
        ax.set_xticks(range(len(labels)),[str(x) for x in labels]);ax.set_title('Edit score by '+group_key)
        for y,row in enumerate(matrix):
            for x,v in enumerate(row):ax.text(x,y,f'{v:.2f}',ha='center',va='center',color='white' if v>2.6 else 'black')
    fig.suptitle(COHORT_NAMES[cohort]+' | Operation and target-count breakdown',fontsize=11)
    fig.tight_layout();fig.savefig(output/(cohort+'_operations.png'),dpi=170);plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();config=json.loads((args.run/'config.rank0.json').read_text()); records=[]
    for file in sorted((args.run/'records').glob('*.json')):
        r=json.loads(file.read_text())
        if r['run_id']==config['run_id'] and r['variant']=='pair_v2':records.append(r)
    expected=set(config['selected_sample_ids']); actual={r['sample_id'] for r in records}
    if actual != expected or len(records)!=len(actual): raise ValueError('Comparison requires one completed record per selected sample')
    args.output.mkdir(parents=True,exist_ok=True);tables={};breakdowns={};md=['# Qwen3.8-27B pair_v2 scores','',
        'Three axes are reported separately (0–4). These are model judgments, not human ground truth.',
        'Compare all systems on the same source cases and settings.',
        'Case 0321 has an annotation conflict and is excluded from score means. Missing/unknown counts remain visible.','']
    for name,rs in cohorts(records).items():
        table=groups_for(rs);tables[name]=table
        md += ['## '+COHORT_NAMES[name],'','| Method | Cases | Images | Status | Edit | Preservation | Quality | E=4 | E=4,P/Q≥3 |',
               '|---|---:|---:|---|---:|---:|---:|---:|---:|']
        for method,t in table.items():
            values=[f"{t.get(a,{}).get('mean_on_decidable',0):.3f}" for a in AXES]
            rates=[f"{100*(t[k]['rate_on_decidable'] or 0):.1f}%" for k in ('all_edits_success','strict_success')]
            md.append('| '+' | '.join([NAMES[method],str(t['cases']),str(t['n']),str(t['status'])]+values+rates)+' |')
        md += ['', 'Intervals resample source cases, preserving correlations between four settings; they do not capture judge bias.','']
        draw_charts(name,rs,table,args.output)
        breakdowns[name]={}
        for key in ('edit_type','region_count','setting'):
            grouped=defaultdict(list)
            for r in rs:
                label=len(r['sample']['regions']) if key=='region_count' else r['sample'][key]
                grouped[label].append(r)
            breakdowns[name][key]={str(k):groups_for(v) for k,v in grouped.items()}
        md += ['### Breakdown by operation and number of targets','',
               '| Group | Method | Images | Edit | Preservation | Quality |',
               '|---|---|---:|---:|---:|---:|']
        for key in ('edit_type','region_count'):
            for label,group in breakdowns[name][key].items():
                for method,t in group.items():
                    values=[f"{t.get(a,{}).get('mean_on_decidable',0):.3f}" for a in AXES]
                    md.append('| '+' | '.join([key+'='+label,NAMES[method],str(t['n'])]+values)+' |')
        md += ['']
    atomic_write_json(args.output/'comparison.json',{'run_id':config['run_id'],'tables':tables,
        'breakdowns':breakdowns,'status':dict(Counter(r['status'] for r in records))})
    (args.output/'RESULTS.md').write_text('\n'.join(md)+'\n')
    for stale in args.output.glob('cases_*.jpg'):
        stale.unlink()
    selection = args.output/'case_selection.json'
    if selection.exists():
        selection.unlink()
    figures = sorted(args.output.glob('*.png'))
    page = "<!doctype html><meta charset='utf-8'><title>Benchmark results</title>" \
           "<style>body{max-width:1500px;margin:24px auto;font-family:sans-serif}" \
           "img{max-width:100%;height:auto}pre{white-space:pre-wrap}</style>" \
           "<h1>Benchmark results</h1><pre>" + html.escape('\n'.join(md)) + "</pre>"
    page += ''.join(
        f"<h2>{item.name}</h2><a href='{item.name}'><img loading='lazy' src='{item.name}'></a>"
        for item in figures
    )
    (args.output/'index.html').write_text(page)
    print(json.dumps({'records':len(records),'output':str(args.output)},indent=2))

if __name__=='__main__': main()
