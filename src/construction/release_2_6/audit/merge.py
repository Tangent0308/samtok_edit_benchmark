import json, glob, collections, re
A = '/tmp/samtok_audit'
cases = [json.loads(l) for l in open('/opt/tiger/tanyue/samtok_edit_benchmark/data/provenance/construction_inputs/base1084/cases.jsonl')]
order = {c['id']: i for i, c in enumerate(cases)}
byid = {c['id']: c for c in cases}
VALID_CAT = set('person_clothing_level category_mismatch wrong_instance_spatial ambiguous_ref mask_quality replace_is_attribute ill_posed_edit add_anchor attribute_value independence_violation ref_noref_mismatch translation grammar_style'.split())
SEV = {'blocking': 0, 'major': 1, 'minor': 2}
finds = []; bad = 0
for f in sorted(glob.glob(A + '/agent_out/batch_*.findings.jsonl')):
    for l in open(f):
        l = l.strip()
        if not l: continue
        try: o = json.loads(l)
        except Exception: bad += 1; continue
        o['batch'] = f.split('/')[-1][:8]
        finds.append(o)
reviewed = {}
for f in sorted(glob.glob(A + '/agent_out/batch_*.reviewed.jsonl')):
    for l in open(f):
        l = l.strip()
        if not l: continue
        try: o = json.loads(l)
        except Exception: bad += 1; continue
        reviewed[o['case_id']] = o
text = [json.loads(l) for l in open(A + '/text_findings.jsonl')]
print('agent findings', len(finds), 'reviewed', len(reviewed), 'bad lines', bad, 'text', len(text))
# normalize
for o in finds:
    if o.get('category') not in VALID_CAT:
        print('cat?', o.get('category'), o['case_id']);
    if o.get('severity') not in SEV: print('sev?', o.get('severity'), o['case_id'])
    o.setdefault('verified_visually', True)
    if o['case_id'] not in reviewed: print('finding for unreviewed', o['case_id'])
# merge text findings (skip if agent recorded grammar_style on same unit with its)
allf = finds + text
# attach instruction text
for o in allf:
    c = byid.get(o['case_id'])
    if not c: print('unknown case', o['case_id']); continue
    u = next((u for u in c['units'] if u['id'] == o.get('unit_id')), None)
    o['current_instruction_ref'] = u['instruction_ref'] if u else None
    o['current_instruction_noref'] = u['instruction_noref'] if u else None
    o['operation'] = u['operation'] if u else None
    o['formal_input'] = (('ref' if u['interaction']['has_ref'] else 'noref') + '+' + u['interaction']['locator']) if u else None
allf.sort(key=lambda o: (order.get(o['case_id'], 9999), o.get('unit_id') or '', SEV.get(o['severity'], 3)))
with open(A + '/findings.jsonl', 'w') as fo:
    for o in allf:
        fo.write(json.dumps(o, ensure_ascii=False) + '\n')
with open(A + '/reviewed.txt', 'w') as fo:
    for cid in sorted(reviewed, key=lambda c: order[c]): fo.write(cid + '\n')
json.dump(reviewed, open(A + '/reviewed_meta.json', 'w'), ensure_ascii=False, indent=0)
# stats
sample = set(json.load(open(A + '/unflagged_sample.json')))
vis = [o for o in allf if o.get('verified_visually')]
def worst(lst):
    return min((SEV[o['severity']] for o in lst), default=9)
bycase = collections.defaultdict(list); byunit = collections.defaultdict(list)
for o in vis:
    bycase[o['case_id']].append(o)
    if o.get('unit_id'): byunit[(o['case_id'], o['unit_id'])].append(o)
print('visual findings', len(vis), collections.Counter(o['severity'] for o in vis))
print('cases with visual findings', len(bycase), 'units', len(byunit))
for s, k in SEV.items():
    print(s, 'cases(worst)', sum(1 for c, l in bycase.items() if worst(l) == k), 'units(worst)', sum(1 for u, l in byunit.items() if worst(l) == k))
print('cat x sev', collections.Counter((o['category'], o['severity']) for o in vis).most_common())
# residual on unflagged sample
sv = [c for c in sample if c in reviewed]
print('sample reviewed', len(sv))
for k, s in [(0, 'blocking'), (1, 'major'), (2, 'minor')]:
    n = sum(1 for c in sv if worst(bycase.get(c, [])) <= k)
    print(f'sample cases with >= {s}:', n, f'{n / len(sv):.3f}')
su = [(c, u['id']) for c in sv for u in byid[c]['units']]
for k, s in [(0, 'blocking'), (1, 'major')]:
    n = sum(1 for x in su if worst(byunit.get(x, [])) <= k)
    print(f'sample units with >= {s}:', n, len(su), f'{n / len(su):.3f}')
print('sample cat', collections.Counter((o['category'], o['severity']) for c in sv for o in bycase.get(c, [])).most_common())
# region breakdown
for lo, hi in [(0, 200), (200, 869), (869, 945), (945, 1084)]:
    rc = [c for c in reviewed if lo <= order[c] < hi]
    bl = [c for c in rc if worst(bycase.get(c, [])) == 0]
    mj = [c for c in rc if worst(bycase.get(c, [])) <= 1]
    print(f'range {lo}-{hi}: reviewed {len(rc)}, blocking {len(bl)}, >=major {len(mj)}')
# full unflagged census
d = json.load(open(A + '/auto_checks.json'))
flagged = set()
for f in d['flags']:
    if f['auto_severity'] == 'info' and f['check'] not in ('box_contained', 'person_remove', 'person_add_anchor'): continue
    flagged.add(f['case_id'])
unf = [c['id'] for c in cases if c['id'] not in flagged]
print('unflagged total', len(unf), 'reviewed', sum(1 for c in unf if c in reviewed))
for k, s in [(0, 'blocking'), (1, 'major'), (2, 'minor')]:
    n = sum(1 for c in unf if worst(bycase.get(c, [])) <= k)
    print(f'UNFLAGGED census cases >= {s}:', n, f'{n / len(unf):.3f}')
uu = [(c, u['id']) for c in unf for u in byid[c]['units']]
for k, s in [(0, 'blocking'), (1, 'major')]:
    n = sum(1 for x in uu if worst(byunit.get(x, [])) <= k)
    print(f'UNFLAGGED census units >= {s}:', n, len(uu), f'{n / len(uu):.3f}')
fl = [c for c in flagged]
for k, s in [(0, 'blocking'), (1, 'major'), (2, 'minor')]:
    n = sum(1 for c in fl if worst(bycase.get(c, [])) <= k)
    print(f'FLAGGED cases >= {s}:', n, len(fl))
