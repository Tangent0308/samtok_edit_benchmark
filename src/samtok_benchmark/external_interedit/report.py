from samtok_benchmark.external_pilot.report import report

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--previews", required=True)
    p.add_argument("--doc")
    a = p.parse_args()
    report(a.root, a.previews, 'Inter-Edit', {'S_global_LPIPS': '全图 LPIPS ↓', 'S_in_AlphaCLIP': '区域内 AlphaCLIP ↑', 'S_out_AlphaCLIP': '区域外 AlphaCLIP ↑', 'BSS_Laplacian': 'BSS ↓'}, ['原始公开 mask 同时提供给两方法，SITEdit 直接用原生 codec 编码，不调用 Pass1 定位。', '四项均为官方客观指标，AlphaCLIP ViT-L/14 grit1m 8xe，LPIPS-alex。', 'S_ref_AlphaCLIP / VLM 为 N/A：官方数据缺少 reference_image，用户已确认该口径。'], a.doc)
