# SAMTok Edit Benchmark 2.6.0

SAMTok Edit 是一个面向真实场景、多目标、细粒度图像编辑的 benchmark。当前 release 包含 1,084 张 SA-1B 源图、3,872 个编辑单元，每图 2–5 个目标，指令协议和 mask 语义均为 2.0；no-ref 由结构化 spec 自动生成盲指代 `the selected region`。

## 先读这两份文档

- [Benchmark overview 2.6.0](docs/BENCHMARK_OVERVIEW_2_6_0_ZH.md)：评测目标、任务形式、统计信息、区域输入方式、rubric、代表性 case 和路径。
- [Construction 2.6.0](docs/CONSTRUCTION_2_6_0_ZH.md)：源数据、case 选择、instruction/protocol 设计、mask 精修和发布校验。

## 当前入口

| 内容 | 路径 |
|---|---|
| 当前版本指针 | [data/current.json](data/current.json) |
| 正式 manifest | [data/v2_2.6.0/cases.jsonl](data/v2_2.6.0/cases.jsonl) |
| 数据构造 | [construction/](construction/) |
| 模型评测与输入 builder | [evaluation/](evaluation/) |
| 当前 Python 包 | [samtok_benchmark/](samtok_benchmark/) |
| 评测运行索引 | [results/README.md](results/README.md) |
| 文档索引与归档 | [docs/README.md](docs/README.md) |

数据根固定为 `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2`。运行代码时在仓库根目录使用 `/opt/tiger/envs/gen/bin/python` 和 `PYTHONPATH=.`；模型评测命令见 [evaluation/README.md](evaluation/README.md)。

2.6.0 已通过构建、资产、几何和协议校验；独立人工语义终审仍标记为未完成。模型全量 judge 结果在四个目录完成前不会写入正式 benchmark 说明。
