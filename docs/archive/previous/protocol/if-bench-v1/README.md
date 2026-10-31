# IF-Bench 协议与评测索引

**当前有效版本：2026-10-30 已确认的 fairness v2.1 / dev20。** Qwen2.1 使用推荐 2K，MICE 使用固定短标注说明并检查原生 200-token 条件完整性。2026-10-31 本机修复运行通过原生 CPU offload 补齐 Qwen2.1 的 177 条解码 OOM，并完成全部缺失 Judge。七模型仍各固定一套方案，相同 20 张 dev、10 个 setting，不再选候选。23 条 Qwen 原成功输出与其余模型终态精确复用；全部历史失败和成本保留，仍停在正式冻结/test 之前。

## 当前文档

| 文档 | 内容 |
|---|---|
| **[CURRENT_EVALUATION_ZH.md](CURRENT_EVALUATION_ZH.md)** | 七模型 × 十 setting 实际输入、原生 API/组件、prompt、参数、版本、UP/JP、CI、失败和缓存规则 |
| [PROTOCOL.fairness-v2.1.dev20.md](PROTOCOL.fairness-v2.1.dev20.md) | 已确认修订、284 条重跑、精确终态复用与完整性检查 |
| [PROTOCOL.fairness-v2.dev20.md](PROTOCOL.fairness-v2.dev20.md) | v2.1 继承的 setting、方法边界、Judge、20 图范围与后续交付边界 |
| [DEV20_RUN_ZH.md](DEV20_RUN_ZH.md) | 8 卡前台入口、依赖、启动阶段、进度与实际图文报告位置 |
| **[DEV20_RECOVERY_RUN_ZH.md](DEV20_RECOVERY_RUN_ZH.md)** | 最新修复运行、真实新增/复用计数、全部 Judge、70 行主表及 700 例插图材料入口 |
| [ENGINEERING_REPAIR_20261030_ZH.md](ENGINEERING_REPAIR_20261030_ZH.md) | 解码显存与 Judge 缓存根因、原生修复和两例诊断边界 |
| [FAIRNESS_V2_CHANGELOG_ZH.md](FAIRNESS_V2_CHANGELOG_ZH.md) | 与旧输入的逐项差别 |
| [运行模块](../../../../../src/samtok_benchmark/ifbench/README.md) · [工具索引](../../../../../src/evaluation/protocol_audit/README.md) | 代码组织、检查与历史脚本边界 |

目录名 `if-bench-v1` 为兼容旧引用而保留；当前版本以文件中的 fairness v2.1/dev20 标识为准。

## 历史协议与证据

以下文件按记录日期解释，不能覆盖当前方式，也不能将旧配置分数搬到新配置。

- [两图验证时的提案](PROTOCOL.fairness-v2.proposed.md)：后来已确认，并把下一轮范围改成 20 图。
- [早期修订协议](PROTOCOL.revised.md) · [原始协议副本](PROTOCOL.original.md)：保留原文和历史决策。
- [逐方法核对](METHOD_AUDIT_ZH.md) · [23 方法 × 10 setting 审计矩阵](SETTING_MATRIX_ZH.md) · [CSV](SETTING_MATRIX.csv)：阶段 1 假设核对，不是当前七模型适配表。
- [附录核对](APPENDIX_AUDIT_ZH.md) · [全局问题](GLOBAL_ISSUES_ZH.md) · [早期修订记录](CHANGELOG_ZH.md) · [决策](DECISIONS_ZH.md) · [环境](RUNTIME_ZH.md) · [官方来源](SOURCE_INDEX.md)。
- [历次执行记录](EXECUTION_STATUS_ZH.md) · [归档会话记录](archive/SESSION_HISTORY.md)：历史 PID、计数和授权只用于追溯，不代表当前进度。

## 实验材料位置（仓库外）

| 材料 | 临时路径 |
|---|---|
| 最新修复运行的固定名单、请求、源码与记录 | `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v21-qwen-repaired-dev20-20261031/` |
| 当前进度 / Judge / 完成后的 Markdown 插图报告 | 上述目录的 `results/PROGRESS.md`、`results/judge/`、`results/report/REPORT.md` |
| 修复前 v2.1 原终态及单独恢复的 Judge（均须保留） | `.ifbench-tmp/fairness-v21-dev20-20261030/`、`.ifbench-tmp/fairness-v21-recovery-20261031/` |
| v2 父运行、原结果、复用证据及共用环境归档（需保留） | `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v2-dev20-20261030/` |
| 前置两图验证与全 setting 图册 | `/tmp/ifbench/fairness_v2_20261030/FINAL_EVALUATION_METHODS.md`、`ALL_MODELS_ALL_SETTINGS_GALLERY.md` |
| 旧 108 图候选分数与逐 setting 图文文档 | `/tmp/ifbench/tiered_v1/dev_selection/judge_rejudge13_v1/`、`setting_document/IF-Bench_dev_setting_report.md` |
| 旧输入适当性复核 | `/tmp/ifbench/tiered_v1/dev_selection/input_suitability_review/` |

这些绝对路径需要实验机器挂载权限，不是 GitHub 附件。仓库保存协议、官方证据链接和代码；输出图片、权重、日志不提交。只有最终确认并冻结的正式产物进入 `experiments2/IF-Bench/`。
