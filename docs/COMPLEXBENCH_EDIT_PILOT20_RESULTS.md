# ComplexBench-Edit 扩展小样本结果

固定 20 条请求：保留上轮 10 条，新增 10 条。SITEdit 与 Qwen-Image-2.1 使用相同清单；旧结果逐条核验后复用，未重新生成或评分。

方法、权重、输入映射、原生评分和 GPT-5.4 配置与前轮一致。抽样 seed 20261107，生成 seed 42。本结果是分层小样本观察，不作为全量排名或显著性结论。

| 指标 | SITEdit | Qwen-Image-2.1 | 有效数（SITEdit / Base） |
|---|---:|---:|---|
| 指令得分 ↑ | 0.3958 | 0.5700 | 20/20；20/20 |
| 区域外 L1 ↓ | 0.0466 | 0.0733 | 20/20；20/20 |
| 区域外 L2 ↓ | 0.0202 | 0.0222 | 20/20；20/20 |

生成完成仅表示正常出图。失败、缺分和受理未作答保留；没有填零，没有按分数筛选样例。

- 指令评分使用官方 rubric 与依赖聚合规则；GPT-5.4 替代 Gemini。
- L1/L2 的源图目标框由官方 GroundingDINO 评分流程产生，仅用于评分。

- 全部逐例记录及来源：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_complexbench_edit/pilot20_20261108/report/REPORT.json`。
- 新增 API 响应：60；旧新合计响应：120；未作答受理：0。
