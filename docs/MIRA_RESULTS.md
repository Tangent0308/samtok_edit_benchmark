# MIRA 正式结果入口

**最新结果见 [MIRA_R2.md](MIRA_R2.md)**：R2@1000 全量 200/200 张已评分，PF / Cons / PQ / Overall = **7.881 / 7.830 / 6.748 / 7.269**。该页提供与四个其他方法及 v4 的六行对比、置信区间、配对差值和全部结果路径。

当前对比表：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira/r2_20261110/ALL_MODELS_COMPARISON.md`，机器可读文件为同目录 `ALL_MODELS_COMPARISON.json`。R2/v4 四项统计及逐图分数为 `REPORT.json`；权重和推理核验为 `VERIFICATION.json`，实际配置为 `run_001/CONFIG.json`。

公共协议、历史 v4 结果及诊断保留于 **[MIRA_EVALUATION.md](MIRA_EVALUATION.md)**：第 8.1 节已加入当前 R2 行，第 8.2–10 节明确属于 v4 历史分析，不将其结论套用于 R2。本页只维护入口。

原五行 1,000 个生成请求均已终结，999 张有效输出全部完成 GPT-5.4 评分；RePlan 154 的失败保留。其[独立恢复测试](MIRA_REPLAN_FAILURE.md) 没有进入正式成绩；新增 R2 的 200 张独立保存。

原始证据仍位于 `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira`。经审计的两套表为 `audited_report_v2/TABLE.md`，统计及分数身份为 `audited_report_v2/REPORT.json`；该 v2 仅修正首份报告的 Markdown 显示，数值不变。原始流水线 `TABLE.md/TABLE.csv` 和 `scores_gpt54_001/SCORES.json` 均保留。

运行命令与复算方式见 [MIRA.md](MIRA.md)，实际执行审计见 [MIRA_FULL_RUN.md](MIRA_FULL_RUN.md)。
