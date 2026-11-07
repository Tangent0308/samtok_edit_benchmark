from samtok_benchmark.external_pilot.report import report

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--previews", required=True)
    p.add_argument("--doc")
    a = p.parse_args()
    report(a.root, a.previews, 'ComplexBench-Edit', {'instruction_score': '指令得分 ↑', 'L1': '区域外 L1 ↓', 'L2': '区域外 L2 ↓'}, ['五组各 2 条，公开的原始多行指令作为三个联合目标；一次定位和一次联合编辑。', '指令评分使用官方 rubric 与依赖聚合规则；GPT-5.4 替代 Gemini。', 'L1/L2 的源图目标框由官方 GroundingDINO 评分流程产生，仅用于评分。'], a.doc)
