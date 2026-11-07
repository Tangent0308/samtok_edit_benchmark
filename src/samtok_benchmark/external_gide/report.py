from samtok_benchmark.external_pilot.report import report

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--previews", required=True)
    p.add_argument("--doc")
    a = p.parse_args()
    report(a.root, a.previews, 'GIDE-Bench', {'Prompt_Compliance': '指令遵循 ↑', 'Visual_Naturalness': '视觉自然度 ↑'}, ['公开 polygon 2、xywh box 2、text 4，共 8 条，覆盖六种编辑组合。', 'SITEdit 通过原生 codec/box locator/文字定位处理公开区域；一次联合 Pass1、一次联合 S2。', 'Judge 保留官方 evaluation 指令和两编辑评分规则，GPT-5.4 替代 GPT-5.1；两项范围均为 1–5。'], a.doc)
