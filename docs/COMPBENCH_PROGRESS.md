# CompBench 小子集进度

当前正在准备的 3,481 条全量评测见 [COMPBENCH_FULL_RUN.md](COMPBENCH_FULL_RUN.md)。以下仅为已完成的八条 pilot 记录。

2026-11-07：8 条 × 2 方法已全部生成和评分，16/16 成功。前两条完成端到端冒烟后复用，剩余六条各仅生成一次。CPU 合同测试通过，新增 Python 通过 Ruff；全部案例对照已经生成。

- 结果：[COMPBENCH_RESULTS.md](COMPBENCH_RESULTS.md)。
- 原始根：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/pilot_20261107`。
- 含全部图片的报告：`/opt/tiger/tanyue/visualization_tmp/CompBench_20261107/REPORT.md`。
- 用户确认：缺少官方可评分接口的 action/location/view 不纳入本轮，六类八条。
- 工程问题：评分依赖与本地 CLIP 权重路径已修复，无模型或指标变更，无失败请求重采样，无付费 API。
