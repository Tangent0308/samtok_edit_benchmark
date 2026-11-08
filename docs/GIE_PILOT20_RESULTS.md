# GIE-Bench 扩展小样本结果

固定 18 条请求：保留上轮 9 条，新增 9 条。SITEdit 与 Qwen-Image-2.1 使用相同清单；旧结果逐条核验后复用，未重新生成或评分。

方法、权重、输入映射、原生评分和 GPT-5.4 配置与前轮一致。抽样 seed 20261107，生成 seed 42。本结果是分层小样本观察，不作为全量排名或显著性结论。

| 指标 | SITEdit | Qwen-Image-2.1 | 有效数（SITEdit / Base） |
|---|---:|---:|---|
| 编辑正确率 ↑ | 0.6667 | 0.7778 | 18/18；18/18 |
| 区域外 CLIP ↑ | 0.9830 | 0.9802 | 18/18；18/18 |
| 区域外 SSIM ↑ | 0.9688 | 0.9214 | 18/18；18/18 |
| 官方 MSE ↓ | 952.6646 | 1346.8982 | 18/18；18/18 |
| 官方 PSNR ↑ | 20.7558 | 18.9299 | 18/18；18/18 |

生成完成仅表示正常出图。失败、缺分和受理未作答保留；没有填零，没有按分数筛选样例。

- Published MSE/PSNR threshold selects all pixels on released 0/1 masks; these are not corrected background scores.

- 全部逐例记录及来源：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_gie/pilot20_20261108/report/REPORT.json`。
- 新增 API 响应：18；旧新合计响应：36；未作答受理：0。
