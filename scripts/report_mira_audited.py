#!/usr/bin/env python3
"""Report fixed MIRA source subsets and explicitly conditional paired intervals."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

MODELS = ('qwen2511', 'qwen21', 'replan', 'mirage', 'sitedit')
METRICS = ('PF', 'Cons', 'PQ')
FIELDS = ('prompt_following', 'consistency', 'perceptual_quality')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def overall(means):
    means = np.asarray(means)
    return np.sqrt(np.minimum(means[..., 0], means[..., 1]) * means[..., 2])


def summarize(values, case_ids, replicates=10000, seed=20261027):
    """Missing scores stay missing; partial comparisons name their conditional population."""
    cases = sorted(case_ids)
    if not cases or len(cases) != len(set(cases)):
        raise ValueError('Source IDs must be nonempty and unique')
    for by_case in values.values():
        for vector in by_case.values():
            a = np.asarray(vector, dtype=float)
            if a.shape != (3,) or not np.isfinite(a).all() or not ((0 <= a) & (a <= 10)).all():
                raise ValueError('Expected three finite scores in [0, 10]')
    draws = {}

    def distribution(model, keys):
        key = tuple(keys)
        if key not in draws:
            draws[key] = np.random.default_rng(seed).integers(0, len(keys), size=(replicates, len(keys)))
        a = np.array([values[model][k] for k in keys], dtype=float)
        return overall(a[draws[key]].mean(axis=1))

    rows = []
    for model, by_case in values.items():
        scored = [case for case in cases if case in by_case]
        row = {'model': model, 'total': len(cases), 'scored': len(scored),
               'missing_cases': [case for case in cases if case not in by_case],
               'complete': len(scored) == len(cases), 'Overall_CI95': None}
        if scored:
            means = np.array([by_case[k] for k in scored], dtype=float).mean(axis=0)
            row.update(zip(METRICS, means.tolist()))
            row['Overall'] = float(overall(means))
            if row['complete'] and len(scored) > 1:
                row['Overall_CI95'] = np.quantile(distribution(model, scored), [.025, .975]).tolist()
        rows.append(row)

    pairs = []
    if 'sitedit' in values:
        for model in values:
            if model == 'sitedit':
                continue
            keys = [case for case in cases if case in values['sitedit'] and case in values[model]]
            pair = {'baseline': model, 'n_pairs': len(keys), 'requested_sources': len(cases),
                    'population': 'full_selected_source_set' if len(keys) == len(cases) else 'common_scored_subset',
                    'omitted_cases': [case for case in cases if case not in keys],
                    'delta': None, 'CI95': None}
            if keys:
                ours = np.array([values['sitedit'][k] for k in keys], dtype=float).mean(axis=0)
                other = np.array([values[model][k] for k in keys], dtype=float).mean(axis=0)
                pair['delta'] = float(overall(ours) - overall(other))
                if len(keys) > 1:
                    delta = distribution('sitedit', keys) - distribution(model, keys)
                    pair['CI95'] = np.quantile(delta, [.025, .975]).tolist()
            pairs.append(pair)
    return {'source_ids': cases, 'rows': rows, 'paired_sitedit_minus_baseline': pairs,
            'bootstrap': {'unit': 'source image', 'replicates': replicates, 'seed': seed},
            'interpretation': 'Partial means use their stated scored denominator. Common-scored-subset intervals are conditional diagnostics, not full-benchmark estimates. No missing value is imputed.'}


def load_scores(root, cases):
    values, evidence, coverage = {}, {}, {}
    canonical = set()
    judge_configs = set()
    for model in MODELS:
        directory = root / 'scores_gpt54_001' / model
        job = read(directory / 'JOB.json')
        judge = read(directory / 'JUDGE.json')
        if judge['job_sha256'] != sha(directory / 'JOB.json') or job['model'] != model:
            raise ValueError('Judge/job identity mismatch')
        bindings = {Path(r['image']).stem: r for r in job['bindings']}
        unscorable = {r['case_id']: r['status'] for r in job['unscorable']}
        if (len(bindings) != job['valid_outputs'] or len(bindings) != len(job['bindings'])
                or set(bindings) & set(unscorable) or set(bindings) | set(unscorable) != set(cases)
                or job['total'] != len(cases)):
            raise ValueError('Generation coverage does not match the fixed source denominator')
        score_path = directory / 'scores/per_image_results.jsonl'
        rows = [json.loads(line) for line in score_path.read_text().splitlines() if line.strip()]
        by_case = {}
        for row in rows:
            case = Path(row['image']).stem
            if case not in bindings or case in by_case or row['num_crops'] != 5:
                raise ValueError('Unexpected or duplicate scored source')
            by_case[case] = [row[key] for key in FIELDS]
        values[model] = by_case
        canonical.add(job['canonical_sha256'])
        judge_configs.add(json.dumps(job['evaluator'], sort_keys=True))
        coverage[model] = {'generation_unscorable': unscorable,
                           'judge_missing': sorted(set(bindings) - set(by_case))}
        evidence[model] = {'job_sha256': sha(directory / 'JOB.json'),
                            'judge_sha256': sha(directory / 'JUDGE.json'),
                            'scores_sha256': sha(score_path)}
    if len(canonical) != 1 or len(judge_configs) != 1:
        raise ValueError('Methods differ in canonical annotations or Judge configuration')
    return values, coverage, evidence


def markdown(report):
    lines = ['# MIRA / GPT-5.4：完整分母与重合审计后报告', '',
             '沿用冻结的逐图分数和官方聚合公式：先计算 PF、Cons、PQ 均值，再计算 Overall = sqrt(min(PF, Cons) × PQ)。所有分数均为 0–10。', '',
             '官方 200 图结果全部保留；198 图子集仅根据训练重合证据排除 138、175。失败及缺失保留在对应分母中，未填零或补采样。原流水线 TABLE.md / SCORES.json 不被修改。']
    for title, subset in report['subsets'].items():
        lines += ['', f'## {title}', '',
                  '| 方法 | PF | Cons | PQ | Overall | Overall 95% CI | 已评分/分母 |',
                  '|---|---:|---:|---:|---:|---|---:|']
        for row in subset['rows']:
            metrics = [f'{row[k]:.3f}' if k in row else '缺失' for k in (*METRICS, 'Overall')]
            ci = row['Overall_CI95']
            interval = f'[{ci[0]:.3f}, {ci[1]:.3f}]' if ci else '不提供完整分母 CI'
            lines.append('| ' + ' | '.join([row['model'], *metrics, interval,
                                            f"{row['scored']}/{row['total']}"]) + ' |')
        lines += ['', 'SITEdit − 基线的配对 Overall 差值：', '',
                  '| 基线 | 差值 | 95% CI | 配对数/分母 | 估计对象 |',
                  '|---|---:|---|---:|---|']
        for pair in subset['paired_sitedit_minus_baseline']:
            ci = pair['CI95']
            interval = f'[{ci[0]:.3f}, {ci[1]:.3f}]' if ci else '不可用'
            delta = f"{pair['delta']:.3f}" if pair['delta'] is not None else '缺失'
            population = ('完整选定源图集合' if pair['population'] == 'full_selected_source_set'
                          else '共同可评分子集；条件诊断')
            lines.append(f"| {pair['baseline']} | {delta} | {interval} | {pair['n_pairs']}/{pair['requested_sources']} | {population} |")
        for pair in subset['paired_sitedit_minus_baseline']:
            if pair['omitted_cases']:
                lines += ['', f"{pair['baseline']} 的共同可评分比较不含：{', '.join(pair['omitted_cases'])}。"]
    lines += ['', '## 覆盖与解释', '',
              '```json', json.dumps(report['coverage'], indent=2), '```', '',
              '完整覆盖的方法提供其完整选定源图集合的区间。若某个基线有缺失，另列双方共同可评分源图上的配对差值，并明确这是条件诊断；它不能替代包含失败样本的完整基准结论。所有区间均按源图进行 10,000 次配对 bootstrap，seed 20261027，相同源图集合共享采样索引。', '',
              '198 图表示排除已确认重合后的子集；有限感知哈希不保证识别任意裁剪或镜像，基础模型预训练和未记录的开发使用不在审计范围。MIRA 衡量公开文本驱动的多项联合编辑，不能替代交互输入及按独立目标数 K 分组的主实验。']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if read(root / 'STATUS.json')['status'] not in ('complete', 'finished_with_missing'):
        raise ValueError('Wait for the original full pipeline to reach its terminal state')
    audit = read(root / 'overlap_audit/REPORT.json')
    subset_path = root / 'overlap_audit/SOURCE_SUBSETS.json'
    sets = read(subset_path)
    if audit['status'] != 'complete' or audit['source_subsets_sha256'] != sha(subset_path):
        raise ValueError('The adjudicated source subsets are not fixed')
    run = read(root / 'run_001/RUN.json')
    if sets['bundle_digest'] != run['bundle_digest'] or sorted(run['case_ids']) != sets['official_200']:
        raise ValueError('Source subsets belong to a different run')
    values, coverage, evidence = load_scores(root, sets['official_200'])
    report = {'schema': 'mira.audited.report.v1', 'coverage': coverage, 'evidence': evidence,
              'source_subset_sha256': sha(subset_path), 'script_sha256': sha(__file__),
              'subsets': {name: summarize(values, sets[name])
                          for name in ('official_200', 'without_confirmed_overlap_198')}}
    output = args.output or root / 'audited_report'
    output.mkdir(parents=True, exist_ok=True)
    for name, content in [('REPORT.json', json.dumps(report, indent=2) + '\n'), ('TABLE.md', markdown(report))]:
        path = output / name
        if path.exists() and path.read_text() != content:
            raise ValueError(f'Preserve previous report; use a new output directory: {path}')
        if not path.exists():
            with path.open('x') as stream:
                stream.write(content)
    print(output / 'TABLE.md')


if __name__ == '__main__':
    main()
