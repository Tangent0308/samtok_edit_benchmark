# MIRA 正式结果入口

结果已统一收录到独立文档 **[MIRA_EVALUATION.md](MIRA_EVALUATION.md)**：第 8 节是官方 200 图、排除已确认训练重合的 198 图、配对区间与分量差异；第 9–10 节是实际图例及 SITEdit 分析；第 11 节列出全部结果路径。本页保留作为旧链接入口，不维护另一份表格。

本次 1,000 个生成请求均已终结，999 张有效输出全部完成 GPT-5.4 评分；RePlan 154 的失败保留。其[独立恢复测试](MIRA_REPLAN_FAILURE.md) 没有进入正式成绩。

原始证据仍位于 `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira`。经审计的两套表为 `audited_report_v2/TABLE.md`，统计及分数身份为 `audited_report_v2/REPORT.json`；该 v2 仅修正首份报告的 Markdown 显示，数值不变。原始流水线 `TABLE.md/TABLE.csv` 和 `scores_gpt54_001/SCORES.json` 均保留。

运行命令与复算方式见 [MIRA.md](MIRA.md)，实际执行审计见 [MIRA_FULL_RUN.md](MIRA_FULL_RUN.md)。
