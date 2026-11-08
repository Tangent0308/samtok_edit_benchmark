# GIDE-Bench 扩展小样本结果

固定 20 条请求：保留上轮 8 条，新增 12 条。SITEdit 与 Qwen-Image-2.1 使用相同清单；旧结果逐条核验后复用，未重新生成或评分。

方法、权重、输入映射、原生评分和 GPT-5.4 配置与前轮一致。抽样 seed 20261107，生成 seed 42。本结果是分层小样本观察，不作为全量排名或显著性结论。

| 指标 | SITEdit | Qwen-Image-2.1 | 有效数（SITEdit / Base） |
|---|---:|---:|---|
| 指令遵循 ↑ | 3.7250 | 3.7250 | 20/20；20/20 |
| 视觉自然度 ↑ | 3.5500 | 3.1500 | 20/20；20/20 |

生成完成仅表示正常出图。失败、缺分和受理未作答保留；没有填零，没有按分数筛选样例。

- SITEdit 通过原生 codec/box locator/文字定位处理公开区域；一次联合 Pass1、一次联合 S2。
- Judge 保留官方 evaluation 指令和两编辑评分规则，GPT-5.4 替代 GPT-5.1；两项范围均为 1–5。
- 原始 RGBA 另行保留；RGB 评分中的部分紫色背景来自原生预测的透明区域，没有回贴源图或补背景。该现象需与指令遵循得分一起分析。

- 全部逐例记录及来源：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_gide/pilot20_20261108/report/REPORT.json`。
- 新增 API 响应：24；旧新合计响应：40；未作答受理：0。
