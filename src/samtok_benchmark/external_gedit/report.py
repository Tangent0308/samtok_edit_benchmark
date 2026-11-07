from samtok_benchmark.external_pilot.report import report

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--previews", required=True)
    p.add_argument("--doc")
    a = p.parse_args()
    report(a.root, a.previews, 'GEdit-Bench', {'SC': '语义一致 SC ↑', 'PQ': '感知质量 PQ ↑', 'Overall': 'Overall ↑'}, ['英文 11 类各 1 条，使用 input_image_raw 与原始公开指令。', '使用官方 VIEScore 提示、图像预处理和 min/几何平均聚合，GPT-5.4 替代官方 GPT-4.1。', '范围 0–10；SC/PQ 各取子分最小值，Overall=√(SC×PQ)。解析失败不猜随机分。'], a.doc)
