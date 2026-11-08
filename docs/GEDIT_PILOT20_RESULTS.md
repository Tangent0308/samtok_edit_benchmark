# GEdit-Bench 扩展小样本结果

固定 22 条请求：保留上轮 11 条，新增 11 条。SITEdit 与 Qwen-Image-2.1 使用相同清单；旧结果逐条核验后复用，未重新生成或评分。

方法、权重、输入映射、原生评分和 GPT-5.4 配置与前轮一致。抽样 seed 20261107，生成 seed 42。本结果是分层小样本观察，不作为全量排名或显著性结论。

| 指标 | SITEdit | Qwen-Image-2.1 | 有效数（SITEdit / Base） |
|---|---:|---:|---|
| 语义一致 SC ↑ | 7.1364 | 8.2727 | 22/22；22/22 |
| 感知质量 PQ ↑ | 6.6364 | 7.3636 | 22/22；22/22 |
| Overall ↑ | 6.7348 | 7.7097 | 22/22；22/22 |

生成完成仅表示正常出图。失败、缺分和受理未作答保留；没有填零，没有按分数筛选样例。

- 英文 11 类各 2 条，使用 input_image_raw 与原始公开指令。
- 使用官方 VIEScore 提示、图像预处理和 min/几何平均聚合，GPT-5.4 替代官方 GPT-4.1。
- 范围 0–10；SC/PQ 各取子分最小值，Overall=√(SC×PQ)。解析失败不猜随机分。

- 全部逐例记录及来源：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_gedit/pilot20_20261108/report/REPORT.json`。
- 新增 API 响应：44；旧新合计响应：88；未作答受理：0。
