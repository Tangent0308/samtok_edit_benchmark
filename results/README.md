# 当前正式评测结果索引

实验根：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/benchmark_v2_2.6.0_baselines/`。

正式结果报告：[RESULT_ANALYSIS_2_6_0_ZH.md](../docs/reports/2.6.0/RESULT_ANALYSIS_2_6_0_ZH.md)。换机恢复、环境和备份：[交接清单](../docs/RECOVERY_HANDOFF_2_6_0_ZH.md)。

正式输入为 `inputs/visual_locator_v2_mixed/jobs.jsonl`，保留各 U 的 point/box/mask。该目录链接到本机 `/tmp`，共享备份与兼容路径恢复方式见交接清单。

七个 model_key：`flux3_klein`、`qwen_image_21`、`flux2_klein_4b`、`longcat_image_edit`、`qwen_image_edit_2511`、`hidream_o1_image`、`step1x_edit`。每个模型有 1,084 个输出和 1,084 条有效评分。

| 内容 | 实验根下路径 |
|---|---|
| 生成配置 / registry / 原图 | `runs/<model_key>/{config.json,outputs.jsonl,shards/}` |
| Judge 输入与裁剪证据 | `judge_inputs/<model_key>/` |
| Judge 原始记录、分数、报告 | `judge/<model_key>/Qwen3.8-Flash-Next-FP8/{records/,scores.jsonl,report.json}` |
| 当前 HiDream 队列与配置证据 | `launch/hidream_2k_20261021/` |
| 输入诊断与压缩 gallery | `mask_pilot/` |
| 飞书发布回读 / 备份 | `publication/lark_hidream_corrected_20261022/` |
| 回收前恢复包 | `recovery/2026-10-22/` |

HiDream 使用官方约 4 MP 分桶修正配置，JointPass=13/1084；旧配置只保留诊断和审计证据。Hunyuan 只有快速检查，未纳入正式表。

仓库 CSV、图表和选例绑定由 `evaluation/analyze_results.py`、`render_current_report.py`、`render_model_case_studies.py` 生成。历史诊断目录不作为当前分数来源，不能把不同 input digest 的 registry/score 混在一起。
