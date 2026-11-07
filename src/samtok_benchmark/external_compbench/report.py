from samtok_benchmark.external_pilot.report import report

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--previews", required=True)
    p.add_argument("--doc")
    a = p.parse_args()
    report(a.root, a.previews, "CompBench", {"LC-T": "局部 CLIP-T ↑", "LC-I": "局部 CLIP-I ↑",
           "PSNR": "背景 PSNR ↑", "SSIM": "背景 SSIM ↑", "LPIPS": "背景 LPIPS ↓"},
           ["使用官方 eval_all.py：512×512、CLIP ViT-L/14、LPIPS squeeze；原始 mask/目标图只进入评分。",
            "用户确认六个可评分类别共 8 条；action/location/view 缺少官方 mask/评分实现，不在本轮范围。",
            "多目标指令作为完整公开指令输入，一次 Pass1 和一次联合编辑，不按目标串行编辑。",
            "背景误差保留官方将编辑区置零后在全图求值的定义。"], a.doc)
