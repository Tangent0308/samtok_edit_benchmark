# Complex-Edit 扩展小样本结果

固定 24 条请求：保留上轮 8 条，新增 16 条。SITEdit 与 Qwen-Image-2.1 使用相同清单；旧结果逐条核验后复用，未重新生成或评分。

方法、权重、输入映射、原生评分和 GPT-5.4 配置与前轮一致。抽样 seed 20261107，生成 seed 42。本结果是分层小样本观察，不作为全量排名或显著性结论。

| 指标 | SITEdit | Qwen-Image-2.1 | 有效数（SITEdit / Base） |
|---|---:|---:|---|
| IF ↑ | 8.8771 | 9.8083 | 24/24；24/24 |
| IP ↑ | 6.3750 | 6.9958 | 24/24；24/24 |
| PQ ↑ | 7.7500 | 8.5375 | 24/24；24/24 |
| Overall ↑ | 7.6674 | 8.4472 | 24/24；24/24 |

生成完成仅表示正常出图。失败、缺分和受理未作答保留；没有填零，没有按分数筛选样例。

- real 3 张、syn 3 张原图，在 K=1/2/4/8 的原始复合指令上评测；共 24 条请求、6 张独立源图。
- 两模型只获得公开 compound_instruction，不用私有 sequence/reasoning 或外部指令拆分。
- 官方提示与结构化评分，GPT-5.4；每项每输出重复 20 次后平均，全部保留。
- IF/IP/PQ 范围 0–10，Overall 为三项平均。

- 全部逐例记录及来源：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_complex_edit/pilot20_20261108/report/REPORT.json`。
- 新增 API 响应：256；旧新合计响应：384；未作答受理：0。
