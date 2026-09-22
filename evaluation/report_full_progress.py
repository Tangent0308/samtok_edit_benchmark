#!/usr/bin/env python3
"""Count benchmark generation outputs and judge records."""
import json
from pathlib import Path
from datetime import datetime, timezone
from common import BASE_SETTING_KEYS, EXPECTED_CASES

base=Path('/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit')
roots={
    'qwen2511':base/'referential_finegrained_edit_benchmark_656_two_image_locator/inference/qwen',
    'flux2':base/'referential_finegrained_edit_benchmark_656_two_image_locator/inference/flux2',
    'qwen21':base/'qwen21_656/inference/qwen21',
    'replan_qwen':base/'replan_656/inference/qwen2511',
    'replan_flux':base/'replan_656/inference/flux2_klein4b'}
def count(directory):
    if not directory.is_dir(): return 0
    names={p.name for p in directory.iterdir()}
    return sum(name[:-4]+'.json' in names for name in names if name.endswith('.png'))
counts={m:{s:count(r/s) for s in BASE_SETTING_KEYS} for m,r in roots.items()}
print(datetime.now(timezone.utc).isoformat())
for m,c in counts.items():print(f'{m:16s} {sum(c.values()):4d}/{EXPECTED_CASES*4} '+str(c))
print('generation total:',sum(sum(c.values()) for c in counts.values()),'/',EXPECTED_CASES*4*5)
judge=base/'metrics_qwen38_all_models_pair_v2/all/records'
print('judge completed records:',len(list(judge.glob('*.json'))),'/',EXPECTED_CASES*4*5)
status=base/'qwen21_656/workflow.status'
if status.exists():print(status.read_text().strip())
