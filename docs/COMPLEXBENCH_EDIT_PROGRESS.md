# ComplexBench-Edit 小子集进度

2026-11-07：五类各 2 条 × 两方法已完成，20/20 正常生成，20/20 完成三项指令评分和区域外 L1/L2。共 60 个正常 GPT-5.4 评分答案；前两条端到端冒烟后复用，不重新采样。无生成失败，无解析补判。

- [固定方案](COMPLEXBENCH_EDIT_EVALUATION.md)、[结果](COMPLEXBENCH_EDIT_RESULTS.md)。
- 结果根：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_complexbench_edit/pilot_20261107`。
- 完整图文：`/opt/tiger/tanyue/visualization_tmp/ComplexBench-Edit_20261107/REPORT.md`。
- 数据身份：bundle `9d599e2c80e828acb4a8bd0d2830e209c85e89ddb6da09e10297a7528eaca0da`。
- CPU 合同/依赖聚合测试 4 项通过，新增 Python 通过 Ruff。
- 官方输入多行映射为三个联合目标，评分用 edits 与 GroundingDINO 框未进入编辑器。
- 观察：SITEdit 指令均分 0.4004，底座 0.6692；背景 L1 更低。小子集不足以作全量统计结论，也不据此调参或换样。
