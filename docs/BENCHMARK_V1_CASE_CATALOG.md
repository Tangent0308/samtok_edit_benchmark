# Benchmark v1：450 个带 mask 的 case 汇总

当前工作在本地 Git 分支 `v1branch` 上进行。远程 `dev` 分支没有被修改。原有 656-case benchmark 作为 v0 保留在：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark/
```

新的 v1 case 数据集位于：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v1/
```

该版本目前只冻结 case、源图、evaluation mask、region mask、box 和 point。`instruction` 与 `target` 字段暂时刻意省略，因此它是 instruction-free staging catalog，不能直接交给旧的 evaluator；后续完成指令后再生成 evaluator-ready manifest。

## 数据来源

### v0 hard-relevant 子集：150 个

输入 manifest：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/PACO_benchmark_candidates/original_656_hard_relevant_v1/benchmark/benchmark.jsonl
```

它来自原始冻结 656-case v0 benchmark：

- 原始 656 清单保持不变，SHA256 为 `280f3c5050cce156173dff31f841328f51b373c83eaf6190b3c1ce3409276022`。
- 先使用已有固定 seed 多模型 judge 结果建立失败优先队列，再对 243 个优先候选做 source/mask contact-sheet 逐例视觉复核。
- 150 个准入 case 来自 confirmed failure seed、text-hard、low-success 和 text-only 严格成功数为 2 的补充队列。
- 过滤要求目标区域最大面积小于 8%，并且至少具有多区域、局部 replace/mixed、MIRAGE 局部编辑或小目标区域等区域定位难点。
- MIRAGE 中主要依赖材质、纹理、毛发、反光、屏幕等操作难度的 case 被排除。
- 两个已知标注冲突 case 被隔离，不进入 v1。

原始筛选记录：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/PACO_benchmark_candidates/original_656_hard_relevant_v1/summary.json
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/PACO_benchmark_candidates/original_656_hard_relevant_v1/decisions_656.jsonl
```

### 外部新增集：300 个

输入 manifest：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/PACO_benchmark_candidates/goal_1k/benchmark_goal1k_v1_300/benchmark.jsonl
```

这些 case 不从 SAMTok 训练数据中采样，来自已完成源图、mask、场景和训练重叠审计的外部数据候选池。其来源分布为：

| 来源 | 数量 |
|---|---:|
| PACO/LVIS | 153 |
| BURST | 58 |
| ADE20K-Part | 43 |
| MeViS-valid_u | 26 |
| SA-V | 14 |
| MOSEv2 | 6 |

该 300-case release 的逐例审计与筛选说明在：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/PACO_benchmark_candidates/goal_1k/benchmark_goal1k_v1_300/case_audit.jsonl
```

当前合并只取该 release 的 source image 和 mask 标注，不取其中已有的 instruction 和 target reference。

## v1 合并统计

| 统计项 | 数量 |
|---|---:|
| 总 case | 450 |
| v0 hard-relevant / external 300 | 150 / 300 |
| 唯一源图 | 450 |
| 总 region mask | 450 |
| 1 region / 2 regions | 387 / 63 |
| add / remove / replace / mixed | 67 / 48 / 324 / 11 |

按 source dataset：

| 数据集 | 数量 |
|---|---:|
| compbench | 114 |
| humanedit | 1 |
| mirage | 35 |
| goal1k/PACO-LVIS | 153 |
| goal1k/BURST | 58 |
| goal1k/ADE20K-Part | 43 |
| goal1k/MeViS-valid_u | 26 |
| goal1k/SA-V | 14 |
| goal1k/MOSEv2 | 6 |

合并时生成新的唯一 ID，例如：

```text
v1-v0_hard_relevant_150-0000-<original_id>
v1-goal1k_v1_300-0000-<original_id>
```

每条记录同时保留 `original_id` 和 `source_release`，可以回溯到两个输入 manifest。450 个源图的内容 SHA256 无重复。

## 数据目录和 schema

```text
samtok_edit_benchmark_v1/
├── README.md
├── case_gallery.html            # VSCode Preview 可直接打开的 case 浏览器
├── dataset_summary.json
├── assets/
│   ├── v0_hard_relevant_150/<local case assets>
│   └── goal1k_v1_300/<local case assets>
└── benchmark/
    ├── benchmark.jsonl          # 当前无 instruction/target 的 case catalog
    ├── case_audit.jsonl         # 原始输入、来源 manifest 和资产哈希回溯
    ├── asset_manifest.jsonl     # 1,413 个本地资产的 SHA256 与尺寸
    └── validation_report.json   # 最后一次完整校验结果
```

`benchmark/benchmark.jsonl` 每行字段为：

```text
id, original_id, source_release, source_dataset, edit_type, difficulty,
source_image, evaluation_mask, regions
```

其中 `regions` 的每个元素包含：

```text
mask, box, point
```

所有路径都是相对于 `samtok_edit_benchmark_v1` 的本地路径；不再依赖 PACO、COCO 或 v0 数据目录。没有生成新的 mask，也没有改变任何原始 mask、box 或 point。

## 复现和校验

在仓库根目录执行：

```bash
python selection/build_v1_case_dataset.py --overwrite
python selection/validate_v1_case_dataset.py \
  --root /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v1
python selection/build_v1_gallery.py \
  --root /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v1
```

本次校验结果：450 行、450 个唯一 ID、450 个唯一源图，共检查 1,413 个 source/evaluation/region 图像资产，全部通过尺寸和解码检查。

在 VSCode 中直接打开下面的文件并选择 **Open Preview** 即可浏览：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v1/case_gallery.html
```

页面支持 case 下拉选择、ID/数据集搜索、source release 筛选、region 数筛选、前后切换以及键盘左右键。图片使用相对于 HTML 的路径，因此不需要启动 Web 服务。

## 当前边界

v1 目前是 case 与标注资产的汇总版本。由于用户要求暂不写 instruction，不能在当前版本上直接运行原有的文本/区域编辑评测；后续 instruction 生成必须保持 `original_id`、mask、box、point 和 source release 不变，并在新的变换记录中保留原始与最终指令。
