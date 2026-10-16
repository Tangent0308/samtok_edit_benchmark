import json,sys
# usage: python add.py <jsonfile-with-{"findings":[...],"reviewed":{...}}>
d=json.load(open(sys.argv[1]))
with open('/tmp/samtok_audit/agent_out/batch_13.findings.jsonl','a') as f:
    for x in d.get('findings',[]):
        x.setdefault('verified_visually',True); f.write(json.dumps(x,ensure_ascii=False)+'\n')
r=d['reviewed']; r.setdefault('viewed',True); r['n_findings']=len(d.get('findings',[]))
sev=[x['severity'] for x in d.get('findings',[])]
r['worst']=next((s for s in ['blocking','major','minor'] if s in sev),'none')
r.setdefault('rejected_auto_flags',[])
with open('/tmp/samtok_audit/agent_out/batch_13.reviewed.jsonl','a') as f: f.write(json.dumps(r,ensure_ascii=False)+'\n')
print('ok',r['case_id'],r['worst'])
