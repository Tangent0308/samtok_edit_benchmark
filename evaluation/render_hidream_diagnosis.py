"""Render original PNG evidence from the HiDream resolution diagnosis."""
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
EXP = Path('/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/benchmark_v2_2.6.0_baselines')
DIAG = EXP / 'diagnostics/hidream_noise_20261021'
OUT = ROOT / 'docs/reports/2.6.0/hidream_diagnosis'
CASES = ['v2-sa_10006079', 'v2-sa_5033895', 'v2-sa_10063996']
FONT = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 19)
SMALL = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 16)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tile(canvas, path, x, y, width, height):
    with Image.open(path) as image:
        image = ImageOps.contain(image.convert('RGB'), (width, height))
        canvas.paste(image, (x + (width - image.width) // 2, y + (height - image.height) // 2))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    legacy = EXP / 'launch/hidream_2k_20261021/legacy_metadata'
    job_path = legacy / 'judge_inputs/judge_jobs.jsonl' if legacy.exists() else EXP / 'judge_inputs/hidream_o1_image/judge_jobs.jsonl'
    run_path = legacy / 'runs/outputs.jsonl' if legacy.exists() else EXP / 'runs/hidream_o1_image/outputs.jsonl'
    jobs = {j['case_id']: j['public_job'] for j in map(json.loads, job_path.open())}
    runs = {j['case_id']: j for j in map(json.loads, run_path.open())}
    evidence = {'cases': [], 'probes': [], 'diagnostic_root': str(DIAG),
                'original_runs_untouched': not legacy.exists(),
                'legacy_metadata': str(legacy) if legacy.exists() else None,
                'original_images': 'three byte-identical diagnostic reproductions retained' if legacy.exists() else 'original full run'}
    canvas = Image.new('RGB', (1960, 1258), '#f7f8fa')
    draw = ImageDraw.Draw(canvas)
    headings = ['Clean source', 'Locator input', 'Original run: ~1 MP', 'Only resolution changed: ~4 MP']
    for col, label in enumerate(headings):
        draw.text((16 + col * 488, 15), label, fill='#182333', font=FONT)
    for row, cid in enumerate(CASES):
        job, run = jobs[cid], runs[cid]
        base = DIAG / 'diffsynth_baseline' / cid / 'output.png'
        fixed = DIAG / 'diffsynth_native_resolution' / cid / 'output.png'
        native_size = json.loads((fixed.parent / 'result.json').read_text())['native_size']
        y = 52 + row * 400
        draw.text((16, y), cid, fill='#49566b', font=SMALL)
        original = base if legacy.exists() else Path(run['output_image'])
        for col, path in enumerate([*job['images'], original, fixed]):
            tile(canvas, path, 10 + col * 488, y + 30, 474, 355)
        evidence['cases'].append({
            'case_id': cid, 'input_files': job['input_files'],
            'input_hashes_verified': all(digest(f['path']) == f['sha256'] for f in job['input_files']),
            'original_run_key': run['run_key'], 'original_output': run['output_image'],
            'retained_original_evidence': str(original),
            'original_output_hash_verified': digest(original) == run['output_sha256'],
            'baseline_pixel_file_reproduction': digest(base) == run['output_sha256'],
            'fixed_output': str(fixed), 'fixed_output_sha256': digest(fixed),
            'fixed_native_size': native_size,
            'visual_review': 'Severe full-image noise / dense colored artifacts removed; edit success not implied.',
        })
    canvas.save(OUT / 'resolution_comparison.jpg', quality=86, optimize=True)

    variants = [
        ('diffsynth_baseline', 'DiffSynth / 1 MP', 'Original configuration'),
        ('diffsynth_fp32_math', 'DiffSynth / 1 MP', 'FP32 time, CFG and step math'),
        ('diffsynth_official_scheduler', 'DiffSynth / 1 MP', 'UniPC + FP32 math'),
        ('official_same_resolution', 'Original repo / 1 MP', 'UniPC + FP32; SDPA attention'),
        ('diffsynth_simple_single', 'DiffSynth / 1 MP', 'Single clean image; simple prompt'),
        ('diffsynth_cpu_noise', 'DiffSynth / 1 MP', 'CPU FP32 initial random noise'),
        ('diffsynth_low_resolution_highref', 'DiffSynth / 1 MP', 'Larger reference images only'),
        ('diffsynth_native_resolution_lowref', 'DiffSynth / 4 MP', 'References kept at original size'),
        ('diffsynth_native_resolution', 'DiffSynth / 4 MP', 'Official resolution buckets'),
        ('official_baseline', 'Original repo / 4 MP', 'Official buckets; SDPA attention'),
    ]
    controls = Image.new('RGB', (2040, 748), '#f7f8fa')
    draw = ImageDraw.Draw(controls)
    for i, (variant, title, subtitle) in enumerate(variants):
        x, y = (i % 5) * 408 + 10, (i // 5) * 374 + 8
        draw.text((x, y), title, fill='#182333', font=FONT)
        draw.text((x, y + 27), subtitle, fill='#49566b', font=SMALL)
        tile(controls, DIAG / variant / CASES[0] / 'output.png', x, y + 54, 388, 300)
    controls.save(OUT / 'controlled_probes.jpg', quality=86, optimize=True)
    for path in sorted(DIAG.glob('*/*/result.json')):
        result = json.loads(path.read_text())
        result['result_file'] = str(path)
        result['output_sha256'] = digest(path.parent / 'output.png')
        evidence['probes'].append(result)
    (OUT / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'cases': len(evidence['cases']), 'probes': len(evidence['probes']),
                      'all_baselines_identical': all(c['baseline_pixel_file_reproduction'] for c in evidence['cases']),
                      'figures': [str(p.relative_to(ROOT)) for p in OUT.glob('*.jpg')]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
