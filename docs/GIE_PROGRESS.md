# GIE-Bench 进度

当前扩展评测（2026-11-08）：见 [GIE_PILOT20.md](GIE_PILOT20.md)。原小子集记录保留如下。

2026-11-07：固定 9 条请求 × 两模型已全部生成和评分。18/18 输出，18/18 官方客观分数，18/18 GPT-5.4 答案；没有重采样或评分丢失。

- 输入和协议：[GIE_EVALUATION.md](GIE_EVALUATION.md)。
- 实际分数：[GIE_RESULTS.md](GIE_RESULTS.md)。
- 八 benchmark 总结：[EXTERNAL_PILOT_SUMMARY.md](EXTERNAL_PILOT_SUMMARY.md)。
- 结果根：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_gie/pilot_20261107`。
- 全部逐例图：`/opt/tiger/tanyue/visualization_tmp/GIE-Bench_20261107/REPORT.md`。
- 数据和官方评分版本为 `06953ba0faa2be70ac814b26a7ba0a0ae13c497e`；2 项 CPU 输入/缓存合约测试及 Ruff 通过。
- 本轮所有生成均已退出，GPU 已释放；没有修改其他任务或 IF-Bench 冻结记录。

## 汇总与只读核对

`audit_external_pilots.py` 从原始逐例分数独立复算八项目全部 68 个汇总值，核验输出 SHA、受理/完成记录与评分绑定；结果全部一致。`diagnose_pilot_outputs.py` 只读取原始 RGBA 的 alpha，不改任何图像或分数。`summarize_external_pilots.py` 生成总报告和分支索引。

```bash
python -I scripts/audit_external_pilots.py --results /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit --output /opt/tiger/tanyue/visualization_tmp/ExternalBenchPilots_20261107/AUDIT.json
python -I scripts/summarize_external_pilots.py --results /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit --previews /opt/tiger/tanyue/visualization_tmp --output /opt/tiger/tanyue/visualization_tmp/ExternalBenchPilots_20261107 --doc docs/EXTERNAL_PILOT_SUMMARY.md
```
