# Omni IIE Bench 扩展小样本结果

固定 20 条请求：保留上轮 8 条，新增 12 条。SITEdit 与 Qwen-Image-2.1 使用相同清单；旧结果逐条核验后复用，未重新生成或评分。

方法、权重、输入映射、原生评分和 GPT-5.4 配置与前轮一致。抽样 seed 20261107，生成 seed 42。本结果是分层小样本观察，不作为全量排名或显著性结论。

| 指标 | SITEdit | Qwen-Image-2.1 | 有效数（SITEdit / Base） |
|---|---:|---:|---|
| LPIPS ↓ | 0.3138 | 0.3730 | 20/20；20/20 |
| PSNR ↑ | 17.8748 | 17.7359 | 20/20；20/20 |
| SSIM ↑ | 0.5997 | 0.5706 | 20/20；20/20 |
| CLIP-I ↑ | 0.9179 | 0.9278 | 20/20；20/20 |
| FG LPIPS ↓ | 0.2013 | 0.1801 | 20/20；20/20 |
| FG CLIP-I ↑ | 0.8997 | 0.9186 | 20/20；20/20 |
| BG LPIPS ↓ | 0.2468 | 0.3055 | 20/20；20/20 |
| BG CLIP-I ↑ | 0.9189 | 0.9271 | 20/20；20/20 |

生成完成仅表示正常出图。失败、缺分和受理未作答保留；没有填零，没有按分数筛选样例。

- 官方固定 768×768 评分，LPIPS-vgg、CLIP ViT-B/32。BG LPIPS/CLIP 和 FG LPIPS 按原生区域面积权重聚合，其余逐例平均。
- 官方 BG_CLIP_I 仅把背景 mask 写入 alpha，CLIPProcessor 转 RGB 后忽略 alpha；逐例与全图 CLIP-I 相同，汇总使用背景面积权重。保留原实现，不将它解释为独立的纯背景指标。
- QA 和 Overall 均 N/A：发布数据及官方可执行入口缺少 QA，用户已确认；不自行造题。

- 全部逐例记录及来源：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_omni_iie/pilot20_20261108/report/REPORT.json`。
- 新增 API 响应：0；旧新合计响应：0；未作答受理：0。
