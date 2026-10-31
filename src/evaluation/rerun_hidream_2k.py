"""Resume corrected HiDream generation, prepare evidence, judge, and report.

This launcher never deletes results. Legacy cleanup is separately audited under
launch/hidream_2k_20261021. All children run from the repository root.
"""
import datetime
import fcntl
import json
import os
from pathlib import Path
from samtok_benchmark.paths import repository_root
import subprocess
import time

ROOT = repository_root()
EXP = Path('/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/benchmark_v2_2.6.0_baselines')
LAUNCH = EXP / 'launch/hidream_2k_20261021'
RUN = EXP / 'runs/hidream_o1_image'
INPUTS = EXP / 'inputs/visual_locator_v2_mixed/jobs.jsonl'
PREPARED = EXP / 'judge_inputs/hidream_o1_image'
JUDGE_MODEL = Path('/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/Qwen3.8-Flash-Next-FP8')
JUDGED = EXP / 'judge/hidream_o1_image' / JUDGE_MODEL.name
MANIFEST = ROOT / 'data/v2_2.6.0/cases.jsonl'
DATA = '/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2'
GEN = '/opt/tiger/envs/gen_tf457/bin/python'
PY = '/opt/tiger/envs/gen/bin/python'
JP = '/opt/tiger/envs/judge/bin/python'
ENV = {**os.environ, 'PYTHONUNBUFFERED': '1', 'CUDA_VISIBLE_DEVICES': '0,1,2,3,4,5,6,7',
       'PYTHONPATH': os.pathsep.join([str(ROOT), '/opt/tiger/envs/DiffSynth-Studio', str(ROOT / 'evaluation/diffsynth')])}


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def atomic(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def snapshot(state):
    state = dict(state, updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    counts = {p.name: len(list((p / 'images').glob('*.png'))) for p in sorted((RUN / 'shards').glob('shard*'))}
    state.update(generated_images=sum(counts.values()), per_gpu_images=counts,
                 generation_count_is_approximate=state['stage'].startswith('generation'))
    if state['stage'].startswith('judge') or state['stage'] in ('report', 'complete'):
        parsed = []
        for path in (JUDGED / 'records').glob('*.json'):
            try:
                parsed.append(json.loads(path.read_text()))
            except (OSError, ValueError):
                continue
        state['judge_ok'] = sum(r['status'] == 'ok' for r in parsed)
        state['judge_parse_errors'] = sum(r['status'] != 'ok' for r in parsed)
    if (JUDGED / 'scores.jsonl').exists():
        state['scores_exported'] = len(rows(JUDGED / 'scores.jsonl'))
    atomic(LAUNCH / 'status.json', state)
    return state


def run(stage, command, attempt=1):
    state = dict(stage=stage, model='hidream_o1_image', total=1084, attempt=attempt,
                 gpu_ids=list(range(8)), resolution_policy='hidream_official_2k_buckets_v1',
                 command=command, started_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    print(json.dumps(state), flush=True)
    with (LAUNCH / f'{stage}_{attempt}.log').open('a') as log:
        proc = subprocess.Popen(command, cwd=ROOT, env=ENV, stdout=log, stderr=subprocess.STDOUT)
        state['child_pid'] = proc.pid
        while proc.poll() is None:
            snapshot(state)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                pass
        state['exit_code'] = proc.returncode
        snapshot(state)
    return proc.returncode


def cli(python, *args):
    return [python, '-m', 'samtok_benchmark.v2.cli', *map(str, args)]


def verify_generation():
    expected = {j['job_id'] for j in rows(INPUTS)}
    outputs = rows(RUN / 'outputs.jsonl')
    if len(outputs) != 1084 or {j['job_id'] for j in outputs} != expected:
        raise RuntimeError('generation coverage is incomplete')
    if any(j['status'] != 'ok' or j['config'].get('resolution_policy') != 'hidream_official_2k_buckets_v1' for j in outputs):
        raise RuntimeError('generation error or legacy configuration detected')
    return {j['job_id']: j for j in outputs}


def main():
    LAUNCH.mkdir(parents=True, exist_ok=True)
    lock = (LAUNCH / 'queue.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('The corrected HiDream queue is already running.', flush=True)
        return
    (LAUNCH / 'queue.pid').write_text(str(os.getpid()) + '\n')
    if len(rows(INPUTS)) != 1084:
        raise RuntimeError('unexpected benchmark size')
    if not (LAUNCH / 'cleanup_manifest.json').exists():
        raise RuntimeError('legacy cleanup audit missing')
    for attempt in range(1, 4):
        code = run('generation', [GEN, '-u', 'src/evaluation/diffsynth/run_sharded.py', '--jobs', str(INPUTS),
                     '--output', str(RUN), '--model', 'hidream_o1_image', '--gpus', '0,1,2,3,4,5,6,7'], attempt)
        if code == 0:
            break
    if code:
        raise RuntimeError('generation failed after three resumable attempts')
    outputs = verify_generation()
    code = run('prepare_judge', cli(PY, 'prepare-judge', '--manifest', MANIFEST, '--dataset-root', DATA,
                '--inputs', INPUTS, '--outputs', RUN / 'outputs.jsonl', '--output', PREPARED))
    if code:
        raise RuntimeError('judge evidence preparation failed')
    jobs = rows(PREPARED / 'judge_jobs.jsonl')
    if len(jobs) != 1084 or {j['job_id'] for j in jobs} != set(outputs):
        raise RuntimeError('judge input coverage is incomplete')
    for job in jobs:
        if any(job[k] != outputs[job['job_id']][k] for k in ('run_key', 'input_digest', 'output_sha256', 'manifest_sha256')):
            raise RuntimeError('judge inputs are bound to different outputs')
    for attempt in range(1, 4):
        code = run('judge', cli(JP, 'judge', '--judge-dir', PREPARED, '--output', JUDGED,
                   '--model', JUDGE_MODEL, '--tensor-parallel-size', 8, '--gpu-memory-utilization', 0.85,
                   '--max-tokens', 12288, '--reasoning-effort', 'low'), attempt)
        if code == 0 and (JUDGED / 'scores.jsonl').exists() and len(rows(JUDGED / 'scores.jsonl')) == 1084:
            break
    else:
        raise RuntimeError('judge incomplete after three resumable attempts; see judge logs')
    # Strict reporting checks every output hash and output/input/score binding.
    code = run('report', cli(PY, 'report', '--manifest', MANIFEST, '--inputs', INPUTS,
               '--outputs', RUN / 'outputs.jsonl', '--scores', JUDGED / 'scores.jsonl', '--output', JUDGED / 'report.json'))
    if code:
        raise RuntimeError('strict final report failed')
    snapshot(dict(stage='complete', model='hidream_o1_image', total=1084, judge_ok=1084,
                  report=str(JUDGED / 'report.json'), resolution_policy='hidream_official_2k_buckets_v1'))
    print('COMPLETE: 1084 generated, 1084 judged, strict report passed', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        state = json.loads((LAUNCH / 'status.json').read_text()) if (LAUNCH / 'status.json').exists() else {}
        state.update(stage='failed', error=f'{type(exc).__name__}: {exc}')
        snapshot(state)
        raise
