# GIE-Bench 进度

- 2026-11-07 09:55 UTC：用户确认八 benchmark 子集计划；创建独立 `eval-gie` worktree，基于 MagicBrush 已验证适配器。
- 官方源码冻结至 `06953ba0faa2be70ac814b26a7ba0a0ae13c497e`，完成五个评分脚本阅读。未运行官方数据下载脚本。
- 本机 GPU 4/5 正被其他任务占用；6/7 各 1605 MiB。后续只在再次确认空闲后使用 6/7。
- 当前：准备官方数据与固定子集；尚无本 benchmark 的模型输出或分数。

- 完成：9 条固定请求 × 两模型，18/18 生成，18/18 官方保持指标，18/18 GPT-5.4 问答，未重采样、无评分丢失。
- SITEdit 问答 4/9、rest CLIP 0.986843、SSIM 0.981691；底座 5/9、0.983467、0.940446。是小子集观察，不能视为全量排名。
- 结果：`experiments2/SAMTokEdit/external_gie/pilot_20261107/report/REPORT.json`。全部逐例图及 Markdown：`/opt/tiger/tanyue/visualization_tmp/GIE-Bench_20261107/REPORT.md`。
- 验证：2 项 CPU 输入/缓存合约测试通过；新增代码 Ruff 通过。
