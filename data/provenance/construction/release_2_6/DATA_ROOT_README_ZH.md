# SAMTok Benchmark release 2.6.0 数据目录

当前数据根：`/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2`。

当前正式 manifest 为 **`benchmark/cases.jsonl`**，从仓库 `data/v2_2.6.0/` 镜像而来。1,084 张源图、3,872 个单元，指令协议和 mask 语义均为 2.0。仓库为 `/opt/tiger/tanyue/samtok_edit_benchmark`，分支 `v2branch`。

| 路径 | 内容 |
|---|---|
| `storage.json` | 当前版本、manifest SHA256、路径指针 |
| `benchmark/` | 当前正式标注、资产清单、校验、统计、逐单元比较 |
| `assets/<case>/` | 原图、旧 U#.png、新 U#_v2.png、历史审核卡 |
| `benchmark_history/2.5.0/` | 发布前旧元数据、旧根目录文档与 storage.json 的备份 |
| `release_2_6_work/` | 分割候选、final.jpg、已审 mask、配方；正式运行不依赖 |
| `docs/RELEASE_2_6_0_ZH.md` | 当前发布说明及复现步骤 |
| `docs/RELEASE_2_6_BEFORE_AFTER_ZH.md` | 8 组修复前后区域与指令对照，非模型编辑结果 |
| `audit/` | **2.5.0 历史** ZIP、PDF、回执，不作为 2.6.0 审核包 |

所有 manifest 资产路径均相对本数据根解析。原始源图、旧 mask 及 2.5.0 仓库数据未改写；新增 708 张 v2 mask。原审查修复任务全部完成，无 case/单元删除；独立人工验收仍未完成，没有模型编辑结果。

当前代码和可恢复 mask 补丁见 [GitHub v2branch](https://github.com/Tangent0308/samtok_edit_benchmark/tree/v2branch)。运行模型时须用本版 manifest 重新 prepare，不复用 2.5.0 的 no-ref 输入或结果。
