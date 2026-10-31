# IF-Bench

IF-Bench（原 SAMTok Edit Benchmark）评测真实场景中的多目标、细粒度图像编辑。数据 release 2.6.0 包含 **1,084 张源图、3,872 个编辑单元，每图 2–5 个目标**。数据与评测协议分别管理；为兼容已有数据和命令，保留 `samtok_benchmark` 包名及旧 CLI。

当前采用已确认的 **fairness v2.1 固定方案**：7 个模型、10 个 setting、相同 20 张 dev 图。v2.1 将 Qwen2.1 改为作者推荐的 2K，并缩短 MICE 固定标注说明、检查原生 200-token 条件完整性；后续本机显存修复使用官方 CPU offload，不再改变这些参数。只使用该 setting 的公开信息与方法自身流程，不外接输入增强组件，不继续搜索候选。正式冻结和 976 图 test 仍需 dev 汇报后确认；旧协议分数不能作为新协议成绩。

## 当前评测

| 阅读目的 | 文档 |
|---|---|
| 每个模型、每个 setting 如何输入、运行、评分 | **[详细评测方式](docs/protocol/if-bench-v1/CURRENT_EVALUATION_ZH.md)** |
| 已确认修复、公平性与失败规则 | [v2.1 修订协议](docs/protocol/if-bench-v1/PROTOCOL.fairness-v2.1.dev20.md) · [继承的 v2 规则](docs/protocol/if-bench-v1/PROTOCOL.fairness-v2.dev20.md) |
| 8 卡启动、环境、进度和图文报告 | [启动指南](docs/protocol/if-bench-v1/DEV20_RUN_ZH.md) |
| Qwen2.1 原生 offload 修复、补齐 Judge 与最新带图报告 | **[修复运行记录](docs/protocol/if-bench-v1/DEV20_RECOVERY_RUN_ZH.md)** |
| 修订记录、官方接口核对、历史协议 | [协议索引](docs/protocol/if-bench-v1/README.md) |
| 模块组织与检查 | [运行代码](samtok_benchmark/ifbench/README.md) · [审计与打包工具](evaluation/protocol_audit/README.md) |

当前模型为 Qwen-Image-Edit-2511、Qwen-Image-2.1、FLUX.3 Klein distilled、RePlan（Qwen-2511）、MIRAGE（Qwen-2511）、MICE（Klein-4B）和 FLUX.2 Klein-9B distilled。MaskFlow 因未验证联合多目标路径暂缓，不以 K 次顺序编辑补齐成绩。

dev 启动包、输出和图文报告保存在共享 `.ifbench-tmp/`，不放入 Git 或正式 `experiments2/IF-Bench/`。启动包自带固定源码快照，更新本仓库不会改变正在运行的实验。

## 数据与历史结果

| 内容 | 入口 |
|---|---|
| 当前数据版本 | [data/current.json](data/current.json) · [manifest](data/v2_2.6.0/cases.jsonl) |
| 数据目标、规模与任务 | [Benchmark overview 2.6.0](docs/BENCHMARK_OVERVIEW_2_6_0_ZH.md) |
| 数据构造、指令与 mask 语义 | [Construction 2.6.0](docs/CONSTRUCTION_2_6_0_ZH.md) · [construction/](construction/) |
| **旧输入协议**的结果与恢复说明 | [历史结果](docs/reports/2.6.0/RESULT_ANALYSIS_2_6_0_ZH.md) · [历史恢复清单](docs/RECOVERY_HANDOFF_2_6_0_ZH.md) |
| 文档索引与外部结果目录 | [docs/](docs/README.md) · [results/](results/README.md) |

数据资产根为 `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2`。2.6.0 已通过构建、资产、几何和协议校验；独立人工语义终审仍未完成。

## 开发检查

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check samtok_benchmark/ifbench evaluation/protocol_audit tests/test_ifbench_*.py
```

这些检查不加载模型。生成与 Judge 使用各自打包的固定环境，不能用开发环境替代。更多约束见 [AGENTS.md](AGENTS.md)。
