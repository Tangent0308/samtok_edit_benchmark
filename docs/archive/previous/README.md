# Documentation map

当前工作：**[IF-Bench fairness v2.1：七模型 × 十 setting 的详细评测方式](protocol/if-bench-v1/CURRENT_EVALUATION_ZH.md)**。相同 20 图 dev 的 Qwen2.1 2K 请求已通过原生 CPU offload 补齐，全部成功输出的 Judge 已完成；最新带图报告与执行边界见 **[修复运行记录](protocol/if-bench-v1/DEV20_RECOVERY_RUN_ZH.md)**。正式 freeze/test 尚未授权。另见 [8 卡启动指南](protocol/if-bench-v1/DEV20_RUN_ZH.md)和[协议索引](protocol/if-bench-v1/README.md)。

以下是数据 release 2.6.0 与旧评测协议的文档；其中历史成绩不属于当前 fairness v2.1。

换机/回收前先读：[接手与恢复清单](RECOVERY_HANDOFF_2_6_0_ZH.md)，包含当前状态、持久存储、临时依赖、环境版本、工作区快照和恢复步骤。

最新整合稿：[SAMTok Edit Benchmark 2.6.0：多目标区域指令图像编辑](publication/2.6.0/SAMTOK_BENCHMARK_2_6_0_ZH.md)。包含构造标准、冻结数据统计、实际彩色定位输入、七模型运行结果（HiDream 已替换为官方约 4 MP 配置的完整重评结果）和带局部评分的案例图；补充了独立性基线、定位子组和启发式失败分类的解释边界。Lark 同步状态见该目录的 `publication_status.json`。

当前 release 的主文档：

1. [Benchmark overview 2.6.0](BENCHMARK_OVERVIEW_2_6_0_ZH.md)：任务目标、统计、输入方式、模型评测入口、rubric、代表性 case 和路径。
2. [Construction 2.6.0](CONSTRUCTION_2_6_0_ZH.md)：源数据、case 选择、instruction/spec、协议 2.0、mask 精修、审查、发布和复现。
3. [Results analysis 2.6.0](reports/2.6.0/RESULT_ANALYSIS_2_6_0_ZH.md)：旧协议七个模型的正式运行及 judge 结果、组合目标分析、定位方式对比、E 失败模式和案例研究。

[HiDream 噪声排查](reports/2.6.0/HIDREAM_NOISE_DIAGNOSIS_2_6_0_ZH.md)：分辨率根因、三例前后对照、修正配置及历史分数的使用限制。

其他文档按用途归档：

- `archive/RELEASE_2_6_0_ZH.md`：发布时的完整路径、构建回执和资产说明；
- `archive/BENCHMARK_EVALUATION_2_6_0_ZH.md`：旧版评测流水线细节，模型入口以 `evaluation/` 当前代码为准；
- `archive/INSTRUCTION_PROTOCOL_ZH.md`、`archive/07_*.md`：协议 2.0 定稿和历史协议说明；
- `archive/BENCHMARK_EXPANSION_1K_ZH.md`：扩充审核过程；
- `archive/BENCHMARK_AUDIT_20261015_ZH.md`、`archive/RELEASE_2_6_REPAIR_STATUS_ZH.md`、`archive/RELEASE_2_6_REMAINING_CASES_ZH.md`：修复与审查过程；
- `archive/RELEASE_2_6_BEFORE_AFTER_ZH.md`：修订前后图例；
- `archive/INSTRUCTION_ALIGNMENT_20261013_ZH.md`、`archive/INSTRUCTION_PROTOCOL_1.0_ZH.md`：旧版本迁移和兼容记录。

大体积实验 gallery、模型输出和 judge records 在 [results/README.md](../../../results/README.md) 指向的外部实验根目录，不复制进 Git 文档。
