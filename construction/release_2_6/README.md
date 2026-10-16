# Release 2.6.0 构建与修复记录

当前 804 个修复任务均已完成，剩余为零。正式入口为仓库 `data/current.json` → `data/v2_2.6.0/cases.jsonl`。[发布说明](../../docs/RELEASE_2_6_0_ZH.md)记录绝对路径、构建与校验回执；[修复前后](../../docs/RELEASE_2_6_BEFORE_AFTER_ZH.md)展示区域及指令差异。

| 工具/目录 | 职责 |
|---|---|
| `build.py` | 将冻结 2.5.0、修订和已审 work mask 合并成 2.6.0；`--check-only --cases ...` 只校验 |
| `status.py` | 从修订、日志、work mask 重新计算进度与剩余清单；不重新看图 |
| `segment.py` | 修复阶段分割、组合及审图；现有发布不需要重新分割 |
| `materialize_masks.py` | 校验并安装 Git 中的 708 张 mask 补丁；`--restore-work` 恢复构建所需 PNG 和配方 |
| `sync_data_root.py` | 将经过校验的正式元数据与文档同步至数据根；先保留 2.5.0 元数据和根文档 |
| `publish.py` | 全量构建后导出补丁、逐单元比较、current.json 和 8 组对照图；不生成模型编辑结果 |
| `revisions/` | 804 个 case 的修订，保留 reviewer 与处理理由 |
| `logs/` | 原分片日志、round2 修复日志和抽查；同一 case 按最后一条完整记录解释 |
| `audit/` | 原始审查问题、自动检查、批次文字记录；反映修复前状态 |
| `assignments/` | 历史分配表；round2_all.txt 共 196 个 case |
| `status.json` / `remaining_work.jsonl` | 当前进度 / 剩余 case，后者为空 |
| `AGENT_INSTRUCTIONS.md` / `NEXT_AGENT_PROMPT.md` | 历史修复阶段规则与交接，不是待执行的新任务 |

本机所有命令在仓库根目录执行，Python 为 `/opt/tiger/envs/gen/bin/python`。正式使用只依赖原始资产、新 mask 与当前 manifest，不依赖候选截图或分割模型。GPU 仅用于重新分割；构建、安装、状态、发布及校验均使用 CPU。
