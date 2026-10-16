# SAMTok Benchmark release 2.6.0 发布记录

发布日期：2026-10-16。当前分支：`v2branch`。本次用户在完成逐 case 修复后明确要求更新 benchmark、整理文档并提交推送，因此执行正式构建；早期修复 prompt 中“不运行全量构建、不提交”的要求仅记录当时修复阶段。

## 1. 当前版本与边界

- 1,084 张唯一 SA-1B 源图，3,872 个单元；每图 2–5 个目标，至少两种交互形式。源图、case 和单元数量不变，没有删除 case 或单元。
- 指令协议 2.0、mask 语义 2.0、写作风格 `benchmark-concise-3-blind-1`。no-ref 从 spec 自动生成，统一盲指代 `the selected region`；不手写 no-ref。
- 804 个修复任务全部完成，280 个无专项修复任务的 case 统一迁移协议。299 个协议要求的部件/site mask 均已提供；共发布 708 张经过复核的新版 mask。
- 所有原始 `U#.png` 与 2.5.0 元数据保留。新版是 `U#_v2.png`，box/point 重新计算，旧定位保留于 `mask_v1`、`box_v1`、`point_v1`。
- 构建与全量资产校验通过不等于语义人工验收。`independent_human_verified=false`、`semantic_signoff=false`；没有模型编辑结果或成功率数据。训练数据暴露也尚未审计。

## 2. 路径与文件职责

所有命令均在仓库根目录 `/opt/tiger/tanyue/samtok_edit_benchmark` 运行。本机 Python：`/opt/tiger/envs/gen/bin/python`。

数据根：`/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2`。

| 文件或目录 | 用途 |
|---|---|
| `data/current.json` | 当前版本指针；路径相对 `data/` |
| `data/v2_2.6.0/cases.jsonl` | 2.6.0 唯一正式标注入口，所有评测从这里 prepare |
| `data/v2_2.6.0/release.json` | 版本、协议、基线及 manifest SHA256、人工验收状态 |
| `data/v2_2.6.0/statistics.json` | 操作、交互、面积、case 目标数统计 |
| `data/v2_2.6.0/validation.json` | 构建后全量源图、mask、几何及资产清单校验回执 |
| `data/v2_2.6.0/asset_manifest.jsonl` | 当前运行所需资产的相对路径、大小和 SHA256 |
| `data/v2_2.6.0/revisions_applied.jsonl` | 构建器实际应用的动作记录；不是人工日志动作计数 |
| `data/v2_2.6.0/known_issues.json` | 构建器记录的 mask 豁免；当前无豁免，不代表所有主观判断已获人工验收 |
| `data/v2_2.6.0/unit_changes.jsonl` | 全部 3,872 单元的旧/新 Ref、no-ref、操作、mask、box、point 和变化标志 |
| `data/v2_2.6.0/comparison_summary.json` | 与 2.5.0 的机器可读比较汇总 |
| `data/v2_2.6.0/mask_patch/assets/<case>/U#_v2.png` | 随 Git 发布的新 mask，约 3.2 MB |
| `data/v2_2.6.0/mask_patch_manifest.jsonl` | 708 张补丁的 SHA256、大小及分割配方，用于安装及恢复 work 输入 |
| `<数据根>/benchmark/` | 当前正式元数据镜像，与仓库 2.6.0 manifest 哈希一致 |
| `<数据根>/benchmark_history/2.5.0/` | 数据根原有 2.5.0 元数据及根目录旧文档备份 |
| `data/v2_2.6.0/data_root_sync.json` | 数据根镜像同步回执，列出文件 SHA256 |
| `<数据根>/assets/<case>/` | 正式运行的原图、旧 mask、新 mask 和历史审核卡；路径以 manifest 为准 |
| `<数据根>/release_2_6_work/<case>/` | mask 候选、final.jpg、已审 PNG、分割配方；分割过程资料，不是正式输入 |
| `<数据根>/release_2_6_work/_audit_views/` | 2.5.0 审查视图，仅供追溯 |
| `construction/release_2_6/revisions/` | 804 个 case 修订；最后 196 例 reviewer 为 round2 |
| `construction/release_2_6/{audit,assignments,logs}/` | 原审查发现、历史任务分配、完整审图与修复日志 |
| `construction/release_2_6/{status.json,remaining_work.jsonl}` | 从磁盘重新计算的进度，剩余清单为空 |
| `data/v2_1084/` | 2.5.0 冻结基线，未改写 |
| `data/v2/` / `data/v2_1k/` | 原版 200 张 / 早期未验收草稿，均不是当前入口 |

旧审核卡的哈希继续用于来源证据校验，**卡片内的旧 mask 和指令不代表 2.6.0 标注**。新版可视化以 [修复前后报告](RELEASE_2_6_BEFORE_AFTER_ZH.md)及当前 manifest 为准。修复阶段工具索引见 [construction README](../construction/release_2_6/README.md)。

## 3. 变更记录

基线 manifest SHA256：`f90849e776ce6269d4851f4c4b1380226de65ce68a7ce4739c4769e2be609d38`。

当前 manifest SHA256：`818ce524a1d1f363dc8ea5caa7a887b2dd0355c17a5600d1cbd696cffcf263fb`。

与基线逐单元比较：1,552 条 Ref 改写，3,872 条 no-ref 重渲染；708 张新版 mask 中 691 张像素改变，17 张在复核后采用与旧版相同的像素；24 个单元改变操作类型。源图哈希全部不变。完整统计见 `comparison_summary.json`。

原审查覆盖 645 个 case、1,363 条问题。合并协议区域迁移和尾段 #945–#1083 逐图重写后，任务并集为 804 个 case。接续时完成 608 例，196 例未完成（todo 182、partial 2、done_unlogged 12）；现已全部完成。最后一轮 758 单元的日志动作：keep 450（含 96 个仅换 mask）、revise 299、retarget 9、drop 0；确认 229 张 v2 mask，其中新增 224 张，复核已有 5 张。

全库操作从 replace 969 / attribute 988 / remove 935 / add 980，变为 replace 969 / attribute 1,002 / remove 921 / add 980。操作净数相同不代表没有单元改类；逐单元转换以 `comparison_summary.json` 和 `unit_changes.jsonl` 为准。

最后一轮 14 条审查被否定或部分否定，包括独立佩戴/手持配件的独立性、原 mask 已排除包带/手部等。完整证据在 `logs/round2.jsonl` 的 `round2_final_report` 事件；日志有补充和更正，同一 case 按最后一条完整记录解释，不累加重复记录。全库统计器共识别 41 条否定日志条目（该统计按日志条目计数，不去重）。

发布时先快进合并上游 `9e63e4f`。共享 `instruction_protocol.py` 保持该上游版本；历史 1.0 的构造入口通过新增 `instruction_compat.py` 分派，修复工具用兼容层调用 canonical `validate_noref`，不在共享文件中增加私有 API。合并后发现 `v2-sa_7184680 U4` 的 `making it an ankle boot` 不属于可分类 qualifier，回看已审靴筒 mask 后改为标准部件移除，并同步中文；操作与 mask 不变，记录已追加到原日志。

[对照报告](RELEASE_2_6_BEFORE_AFTER_ZH.md)列出 8 组图例、完整 Ref/no-ref 前后文本、17 个最后一轮建议人工抽查的判断。早期分片的主观判断另外保留在[修复完成记录](RELEASE_2_6_REPAIR_STATUS_ZH.md)，没有因自动检查通过而抹除。

## 4. 构建与校验

### 直接使用已发布数据

准备基线原始资产后，安装 708 张新版 mask：

```bash
/opt/tiger/envs/gen/bin/python construction/release_2_6/materialize_masks.py \
  --dataset-root /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2
```

安装器校验 Git 内的 PNG，拒绝覆盖内容不同的同名文件。当前正式元数据已在 `data/v2_2.6.0/`，使用时无需重新构建。

### 恢复输入并复现构建

```bash
/opt/tiger/envs/gen/bin/python construction/release_2_6/materialize_masks.py \
  --dataset-root /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2 --restore-work
/opt/tiger/envs/gen/bin/python construction/release_2_6/build.py
/opt/tiger/envs/gen/bin/python construction/release_2_6/status.py
/opt/tiger/envs/gen/bin/python construction/release_2_6/publish.py \
  --dataset-root /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2
```

`build.py` 的源数据根固定为本机上述路径；在其他机器直接使用发布元数据和安装器即可，若重建需提供相同挂载路径。`status.py` 更新 status.json、remaining_work.jsonl 及自动剩余清单；不会改写静态完成报告。`publish.py` 在构建后生成补丁、比较记录、图例和 current.json。它不生成编辑结果。文档整理完成后运行以下命令同步数据根的当前入口，同时保留其原 2.5.0 元数据：

```bash
/opt/tiger/envs/gen/bin/python construction/release_2_6/sync_data_root.py \
  --dataset-root /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2
```

数据根 `storage.json`、`benchmark/` 和根文档随之指向 2.6.0；旧元数据备份在 `benchmark_history/2.5.0/`，旧审核 ZIP/PDF 不改写。

全量资产校验命令：

```bash
PYTHONPATH=src /opt/tiger/envs/gen/bin/python -m samtok_benchmark.v2.cli validate \
  --manifest data/v2_2.6.0/cases.jsonl \
  --dataset-root /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2 \
  --minimum-cases 1000 --output data/v2_2.6.0/validation.json
```

本次调用同一 `dataset.validate` 函数直接执行发布校验，回执存入上述路径。检查了唯一源图哈希、尺寸、二值非空 mask、point/box 几何、独立目标重叠、指令版本与成对渲染、资产大小与 SHA256。执行结果：

```text
{"status": "built", "cases": 1084, "units": 3872}
{"status": "passed", "manifest_sha256": "818ce524a1d1f363dc8ea5caa7a887b2dd0355c17a5600d1cbd696cffcf263fb", "cases": 1084, "unique_sources": 1084, "units": 3872, "checked_assets": 6040, "inventory_checked": 6040, "unit_counts": {"2": 147, "3": 255, "5": 85, "4": 597}, "source_counts": {"SA-1B": 1084}, "unit_operations": {"replace": 969, "attribute": 1002, "remove": 921, "add": 980}, "unit_interactions": {"noref+point": 554, "ref+box": 553, "noref+mask": 553, "ref+none": 553, "ref+mask": 553, "noref+box": 553, "ref+point": 553}, "review_kinds": {"ai_direct_visual": 1084}}
{"generated_at": "2026-10-16T07:47:31+00:00", "cases": 1084, "status": {"not_needed": 280, "done": 804}, "work_list_cases": 804, "per_shard": {"main-session": {"done": 2}, "shard0": {"done": 81}, "shard0b": {"done": 81}, "shard1": {"done": 141}, "shard1b": {"done": 80}, "shard2": {"done": 151}, "shard2b": {"done": 70}, "shard3": {"done": 73}, "shard4": {"done": 32}, "shard5": {"done": 32}, "shard6": {"done": 33}, "shard7": {"done": 28}}, "open_findings": {}, "open_findings_by_category": {}, "open_part_mask_units": 0, "part_mask_units_total": 299, "v2_masks_committed": 708, "operations_now": {"replace": 969, "attribute": 1002, "remove": 921, "add": 980}, "operations_2_5_0": {"add": 980, "replace": 969, "remove": 935, "attribute": 988}, "units_now": 3872, "rejected_findings_logged": 41}
```

本次未运行单元测试；这里的回执是正式数据构建与资产校验结果。

## 5. 资产与历史审核材料

原始资产沿用 2.5.0 审核包：

- [2.5.0 原始审核 ZIP](https://huggingface.co/datasets/TTangenty/samtok_edit/resolve/main/samtok_edit_benchmark_v2_review_1084_20261015.zip?download=true)。历史收据在 `data/v2_1084/review_package.json`。
- ZIP 大小 3,297,929,970 bytes，SHA256 `c2db3b7c8cf5184a82d8f54bac7cf2ed3d9b0bb227e5122838085b9378f2bc94`。
- 解压后原始资产在 `review_1084/assets/`；可以将 `review_1084/` 作为自己的数据根，再运行补丁安装器。不要用包内旧 manifest 覆盖仓库的 2.6.0 manifest。
- 包内 HTML、PDF、旧 `BENCHMARK_V2_ZH.md`、selection_review.jpg 和提示图均是 **2.5.0 历史材料**。本次没有生成或上传 2.6.0 全量审核 ZIP/PDF；Git 内提供当前标注、mask 补丁及 8 例对比图。

当前版本远程指 GitHub 的 `origin/v2branch`，没有把历史 Hugging Face 文件改名为新版。重新运行模型应从当前 manifest 生成新的 prepare 输入，不沿用旧提示图。
