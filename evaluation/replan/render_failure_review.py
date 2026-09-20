#!/usr/bin/env python3
"""Render the fixed 2026-09-20 manual audit; consumes existing outputs only."""
import html
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path('/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/replan_656')
REPORT = ROOT / 'reports/qualitative_expanded_20260920'
OUT = ROOT / 'visualizations/qualitative_expanded_20260920'
REVIEW_INPUT = Path(__file__).resolve().parent / 'reviews/20260920'
MANIFEST = Path('/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/referential_finegrained_edit_benchmark_656_two_image_locator/prepared/benchmark_baseline_eval_inputs.jsonl')
SETTINGS = ['text_only', 'mask_annotation', 'box_annotation', 'point_annotation']
MODELS = ['qwen2511', 'flux2_klein4b']


def font(size, bold=False):
    return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans' + ('-Bold' if bold else '') + '.ttf', size)


def sheet(name, title, examples, rows):
    canvas = Image.new('RGB', (1296, 76 + len(examples) * 420), 'white')
    d = ImageDraw.Draw(canvas)
    d.text((18, 16), title, font=font(25, True), fill='#142131')
    for k, (index, setting, want, observed, crop) in enumerate(examples):
        row = rows[index]
        y = 72 + k * 420
        d.text((18, y), f'#{index:04d} | {setting} | Request: {want}', font=font(18, True), fill='#243c58')
        paths = [Path(row['prepared']['baseline_inputs']['text_only']['images'][0]),
                 Path(row['prepared']['baseline_inputs'][setting if setting != 'text_only' else 'box_annotation']['images'][-1])]
        paths += [ROOT / f'inference/{m}/{setting}/{index:04d}.png' for m in MODELS]
        labels = ['Source', 'Locator' if setting != 'text_only' else 'Locator (reference; not used in T)', 'RePlan + Qwen', 'RePlan + FLUX.2']
        for j, (path, label) in enumerate(zip(paths, labels)):
            im = Image.open(path).convert('RGB')
            if crop:
                w, h = im.size
                im = im.crop(tuple(round(v * [w, h, w, h][a]) for a, v in enumerate(crop)))
            im = ImageOps.contain(im, (306, 300), Image.Resampling.LANCZOS)
            x = 18 + j * 320
            d.text((x, y + 30), label, font=font(14, True), fill='#415063')
            d.rectangle((x, y + 54, x + 306, y + 354), fill='#f1f3f5')
            canvas.paste(im, (x + (306 - im.width) // 2, y + 54 + (300 - im.height) // 2))
        for a, line in enumerate(textwrap.wrap(observed, 134)):
            d.text((18, y + 362 + 21 * a), line, font=font(16), fill='#8b3028')
    canvas.save(OUT / name, quality=94)


def main():
    rows = {r['eval_index']: r for r in map(json.loads, MANIFEST.read_text().splitlines())}
    notes = json.loads((REVIEW_INPUT / 'observations.json').read_text())
    selection = json.loads((REVIEW_INPUT / 'selection.json').read_text())
    assert {x['index'] for x in notes} == {x['eval_index'] for x in selection['selection']}
    OUT.mkdir(parents=True, exist_ok=True)
    groups = [
        ('failure_binding.jpg', 'Wrong instance and local-edit spill', [
            (632, 'mask_annotation', 'Duck 1: red beak; duck 3: blue feet', 'Both models give the red beak to duck 3. The planner assigned both edits the same box.', None),
            (597, 'point_annotation', 'Right man: green scarf; middle woman: green pants', 'Both models swap the intended roles: scarf on the woman, green pants on the right man.', None),
            (611, 'box_annotation', 'Horse 3 head: snow; horse 4 head: lava', 'Qwen applies lava to both horses and beyond the heads. FLUX puts snow on horse 3; the lava edit is weak.', None),
        ]),
        ('failure_operations.jpg', 'Incomplete edits and operation confusion', [
            (488, 'box_annotation', 'Replace the right cat with a cup', 'Qwen retains a cat and adds a cup; FLUX recolors the cat without completing the replacement.', None),
            (586, 'box_annotation', 'Middle cat to dog; remove right cat', 'Qwen only removes the right cat; FLUX only replaces the middle cat. Neither completes both.', None),
            (549, 'text_only', 'Remove everyone except blue-swimsuit swimmers', 'Both models retain people who should be removed. This panel uses the full text exclusion instruction.', None),
        ]),
        ('failure_addition_material.jpg', 'Addition geometry and material fidelity', [
            (150, 'text_only', 'Add a small zebra on the right', 'Qwen produces a clipped zebra at the edge; FLUX produces a more complete added zebra.', None),
            (533, 'text_only', 'Add a white cat next to the grey cat', 'Both models turn the existing right kitten white; the requested new cat is not added.', None),
            (635, 'box_annotation', 'Hat 3: blue; hat 4: wood (detail crop)', 'Hat 4 becomes brown but remains knitted in both outputs. Qwen also changes the shape of hat 3.', (.45, .08, .83, .28)),
        ]),
    ]
    for args in groups:
        sheet(*args, rows)
    evidence = {}
    cards = []
    case_md = []
    esc = html.escape
    for n in notes:
        i = n['index']; row = rows[i]; case = f'{i:04d}'
        evidence[case] = {}
        snippets = []
        for s in SETTINGS:
            evidence[case][s] = {}
            for model in MODELS:
                path = ROOT / f'inference/{model}/{s}/{case}.json'
                p = json.loads(path.read_text())
                evidence[case][s][model] = {k: p[k] for k in ['planner_prompt', 'planner_response', 'predicted_boxes', 'region_guidance', 'global_prompt']}
                snippets.append(f'<details><summary>{esc(model)} / {s}</summary><p>{esc(p["planner_prompt"])}</p><pre>{esc(json.dumps(p["predicted_boxes"], ensure_ascii=False, indent=2))}</pre><a href="../../inference/{model}/{s}/{case}.png">原始输出 PNG</a> · <a href="../../inference/{model}/{s}/{case}.json">完整 sidecar</a></details>')
        panel = f'../replan_comparison/cases/{case}.jpg'
        detail = f'<a href="detail_{case}.jpg">局部放大</a>' if (OUT / f'detail_{case}.jpg').exists() else ''
        instruction = row['instruction']['with_location_reference']
        cards.append(f'<article id="case-{case}" data-dataset="{row["source_dataset"]}" data-tags="{esc(" ".join(n["tags"]))}" data-search="{esc((case + " " + instruction + " " + n["qwen"] + " " + n["flux"]).lower())}"><h2>#{case} · {row["source_dataset"]} · {row["edit_type"]}</h2><p>{esc(instruction)}</p><p class="tags">{esc(" / ".join(n["tags"]))}</p><p><b>RePlan + Qwen：</b>{esc(n["qwen"])}</p><p><b>RePlan + FLUX：</b>{esc(n["flux"])}</p><p>{detail}</p><a href="{panel}"><img loading="lazy" src="{panel}" alt="Case {case}：原图、定位图、参考图及八种输出"></a><details><summary>实际输入指令与规划证据</summary>{"".join(snippets)}</details></article>')
        case_md.append(f'| [#{case}]({ROOT}/visualizations/replan_comparison/cases/{case}.jpg) | {row["source_dataset"]} / {row["edit_type"]} | {n["qwen"]} | {n["flux"]} |')
    (REPORT / 'planner_evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    (REPORT / 'per_case_table.md').write_text('| Case | 来源 / 操作 | RePlan + Qwen | RePlan + FLUX.2 |\n|---|---|---|---|\n' + '\n'.join(case_md) + '\n')
    tags = sorted({t for n in notes for t in n['tags']})
    options = ''.join(f'<option>{esc(t)}</option>' for t in tags)
    nav = ''.join(f'<a href="{name}">{esc(title)}</a> ' for name, title, _ in groups)
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RePlan 扩展人工失败分析 · 42 例</title><style>body{font:16px/1.6 system-ui,sans-serif;background:#f1f4f7;color:#1b2939;margin:0}header{background:white;padding:20px 4vw;position:sticky;top:0;z-index:1;box-shadow:0 2px 8px #0002}h1{font-size:24px;margin:0}h2{font-size:22px}p{margin:.5em 0}main{max-width:1450px;margin:auto;padding:20px}article{background:white;padding:24px;margin:20px 0;border-radius:10px}article[hidden]{display:none}img{width:100%;height:auto}a{color:#245e9e}input,select{font-size:16px;padding:7px;margin:5px}pre{white-space:pre-wrap;background:#f1f4f7;padding:12px}.tags{color:#755739}details{padding:6px}nav a{display:inline-block;margin:6px 18px 6px 0}</style><header><h1>RePlan 扩展人工抽样：42 个新增 case / 336 张输出</h1><p>与前轮 16 例合计 58 例。先抽样后看图；CompBench 18、HumanEdit 8、MIRAGE 16。T/M/B/P = 文本 / mask / box / point。结论用于定位失败模式，不能估计全 benchmark 成功率。</p><input id="q" placeholder="搜索编号、指令、中文观察"><select id="d"><option value="">全部数据集</option><option>compbench</option><option>humanedit</option><option>mirage</option></select><select id="t"><option value="">全部观察标签</option>''' + options + '''</select><span id="count"></span></header><main><nav>''' + nav + '''</nav><p>点击大图查看全部八种输出；展开证据可查看各设置实际指令及两套 planner 输出。判例仅反映本次配置。#0321 存在文字与定位/参考图目标冲突；#0581、#0642 的语义有歧义，单独保留。定位版 all-except 任务可能丢失多实例集合信息，详见报告。</p>''' + '\n'.join(cards) + '''</main><script>const q=document.querySelector('#q'),d=document.querySelector('#d'),t=document.querySelector('#t'),cards=[...document.querySelectorAll('article')];function filter(){let n=0;for(const c of cards){let ok=(!q.value||c.dataset.search.includes(q.value.toLowerCase()))&&(!d.value||d.value===c.dataset.dataset)&&(!t.value||c.dataset.tags.split(' ').includes(t.value));c.hidden=!ok;if(ok)n++;}document.querySelector('#count').textContent=n+' / 42 cases';}for(const e of [q,d,t])e.addEventListener('input',filter);filter();</script></html>'''
    (OUT / 'index.html').write_text(page)
    print(f'Rendered {len(notes)} reviewed cases, {len(groups)} evidence sheets: {OUT / "index.html"}')


if __name__ == '__main__':
    main()
