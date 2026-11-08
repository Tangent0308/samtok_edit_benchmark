# Inter-Edit 扩展小样本结果

固定 20 条请求：保留上轮 8 条，新增 12 条。SITEdit 与 Qwen-Image-2.1 使用相同清单；旧结果逐条核验后复用，未重新生成或评分。

方法、权重、输入映射、原生评分和 GPT-5.4 配置与前轮一致。抽样 seed 20261107，生成 seed 42。本结果是分层小样本观察，不作为全量排名或显著性结论。

| 指标 | SITEdit | Qwen-Image-2.1 | 有效数（SITEdit / Base） |
|---|---:|---:|---|
| 全图 LPIPS ↓ | 0.2316 | 0.2580 | 20/20；20/20 |
| 区域内 AlphaCLIP ↑ | 0.9730 | 0.9680 | 20/20；20/20 |
| 区域外 AlphaCLIP ↑ | 0.9791 | 0.9680 | 20/20；20/20 |
| BSS ↓ | 2.9655 | 21.3317 | 20/20；20/20 |

生成完成仅表示正常出图。失败、缺分和受理未作答保留；没有填零，没有按分数筛选样例。

- 原始公开 mask 同时提供给两方法，SITEdit 直接用原生 codec 编码，不调用 Pass1 定位。
- 四项均为官方客观指标，AlphaCLIP ViT-L/14 grit1m 8xe，LPIPS-alex。
- S_ref_AlphaCLIP / VLM 为 N/A：官方数据缺少 reference_image，用户已确认该口径。

- 全部逐例记录及来源：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_interedit/pilot20_20261108/report/REPORT.json`。
- 新增 API 响应：0；旧新合计响应：0；未作答受理：0。
