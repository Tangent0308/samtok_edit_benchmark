from samtok_benchmark.external_pilot.report import report

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--previews", required=True)
    p.add_argument("--doc")
    a = p.parse_args()
    report(a.root, a.previews, 'Complex-Edit', {'instruction_following': 'IF ↑', 'identity_preservation': 'IP ↑', 'perceptual_quality': 'PQ ↑', 'overall': 'Overall ↑'}, ['real/syn 各 1 张原图，在 K=1/2/4/8 的原始复合指令上评测；不是 8 张独立源图。', '两模型只获得公开 compound_instruction，不用私有 sequence/reasoning 或外部指令拆分。', '官方提示与结构化评分，GPT-5.4；每项每输出重复 20 次后平均，全部保留。', 'IF/IP/PQ 范围 0–10，Overall 为三项平均。'], a.doc)
