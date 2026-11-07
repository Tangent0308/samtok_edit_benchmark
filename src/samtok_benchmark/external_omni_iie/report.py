from samtok_benchmark.external_pilot.report import report

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--previews", required=True)
    p.add_argument("--doc")
    a = p.parse_args()
    report(a.root, a.previews, "Omni IIE Bench",
           {"LPIPS": "LPIPS ↓", "PSNR": "PSNR ↑", "SSIM": "SSIM ↑", "CLIP_I": "CLIP-I ↑",
            "FG_LPIPS": "FG LPIPS ↓", "FG_CLIP_I": "FG CLIP-I ↑", "BG_LPIPS": "BG LPIPS ↓", "BG_CLIP_I": "BG CLIP-I ↑"},
           ["四个完整 high/low 配对，共 8 请求；区域 mask 与目标图均仅用于评分。",
            "官方固定 768×768 评分，LPIPS-vgg、CLIP ViT-B/32。BG LPIPS/CLIP 和 FG LPIPS 按原生区域面积权重聚合，其余逐例平均。",
            "官方 BG_CLIP_I 仅把背景 mask 写入 alpha，CLIPProcessor 转 RGB 后忽略 alpha；逐例与全图 CLIP-I 相同，汇总使用背景面积权重。保留原实现，不将它解释为独立的纯背景指标。",
            "QA 和 Overall 均 N/A：发布数据及官方可执行入口缺少 QA，用户已确认；不自行造题。"], a.doc,
           weights={"BG_LPIPS": "_BG_Weight", "BG_CLIP_I": "_BG_Weight", "FG_LPIPS": "_FG_Weight"})
