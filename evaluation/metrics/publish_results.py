"""Publish complete benchmark scores into the experiment record."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from evaluation.common import atomic_write_json


def replace_section(body: str, name: str, content: str) -> str:
    start, end = f'<!-- {name}_BEGIN -->', f'<!-- {name}_END -->'
    if body.count(start) != 1 or body.count(end) != 1:
        raise ValueError(f'Expected exactly one {name} section')
    before, rest = body.split(start, 1)
    _, after = rest.split(end, 1)
    return before + start + '\n' + content.strip() + '\n' + end + after


def validate_complete(result: dict) -> None:
    table = result['tables']['current_full656']
    expected = {'qwen', 'flux', 'qwen21', 'replan_qwen', 'replan_flux'}
    if set(table) != expected or any(t['cases'] != 656 or t['n'] != 2624 for t in table.values()):
        raise ValueError('Refusing to publish incomplete benchmark coverage')
    if sum(result['status'].values()) != 13120:
        raise ValueError('Expected 13,120 judge records')
    if any(k not in {'ok', 'annotation_conflict'} and n for k, n in result['status'].items()):
        raise ValueError('Resolve missing outputs or judge failures before publishing')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--comparison', type=Path, required=True)
    p.add_argument('--repo', type=Path, required=True)
    args = p.parse_args()
    result = json.loads((args.comparison / 'comparison.json').read_text())
    validate_complete(result)
    figures = sorted(args.comparison.glob('*.png'))
    content = (args.comparison / 'RESULTS.md').read_text()
    # Nest the generated report inside section 2 of MODEL_RESULTS.md.
    content = '\n'.join('##' + line if line.startswith('#') else line for line in content.splitlines())
    content += '\n\n### 数据范围与可靠性\n\n'
    content += '656 例 × 四设置 × 五种系统，三个基模和 RePlan 的两个 editor 分开报告。'
    content += '评分使用固定 Qwen3.8-27B，每条两张轮廓图、一次调用。E/P/Q 分别报告，0321 标注冲突单列 unknown。\n\n'
    content += '小目标、数量与绑定仍可能误判；应结合本文的代表性 case study 解读。\n\n'
    for file in figures:
        content += f'![{file.stem}](docs/assets/full_models_pair_v2/{file.name})\n\n'
    content += f'完整数值与原始评分位置：`{args.comparison.parent}`。\n'
    status = '五种系统各 2,624 张出图均已通过结构校验，共 13,120 条评分记录齐备。标注冲突单列，完整统计见第 2 节。'
    doc = args.repo / 'MODEL_RESULTS.md'
    body = replace_section(doc.read_text(), 'RUN_STATUS', status)
    body = replace_section(body, 'SCORES', content)
    case_source = args.comparison / 'setting_case_study'
    if not case_source.is_dir():
        raise ValueError('Missing final setting case study')
    assets = args.repo / 'docs/assets/full_models_pair_v2'
    assets.mkdir(parents=True, exist_ok=True)
    for stale in assets.iterdir():
        if stale.is_dir():
            shutil.rmtree(stale)
        else:
            stale.unlink()
    for file in figures:
        shutil.copy2(file, assets / file.name)
    case_assets = args.repo / 'docs/assets/setting_case_study'
    if case_assets.exists():
        shutil.rmtree(case_assets)
    shutil.copytree(case_source, case_assets)
    atomic_write_json(args.repo / 'docs/data/full_models_pair_v2.json', result)
    temp = doc.with_suffix('.md.tmp')
    temp.write_text(body)
    temp.replace(doc)
    print('Published scores and figures into MODEL_RESULTS.md')


if __name__ == '__main__':
    main()
