# 细粒度交互式编辑 Benchmark：构建进度与格式约定

最后更新：2026-09-07

## 1. 当前状态

当前已经完成三个源数据集的下载与完整性检查、全量自动特征扫描、v0 构建，以及增强多实例和精确局部编辑的 v1 重平衡、正式导出和自动验证。

最终数据位于：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v1/
```

其中 `benchmark.jsonl` 是 500 条最终统一记录；源图、目标参考图、输入区域 mask 和 evaluation mask 均已转换为可移植的相对路径资产。仓库中的 `benchmark_v1/` 保存 manifest、metadata、验证报告和示例图，不重复提交 544 MB 的完整图片资产。原 v0 仍保留，便于审计版本差异。

## 2. 数据集下载

三个数据集均下载到：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/
```

| 数据集 | Hugging Face 仓库 | 固定 revision | 本地目录 | 当前规模 |
|---|---|---|---|---:|
| CompBench | `BohanJia/CompBench` | `a4c5a4d1854056d24aad43a494772dc90588d426` | `CompBench/` | 3,481 条 |
| HumanEdit | `BryanW/HumanEdit` | `dbc60b9ba3c17adf59e1effd8a9d92bdf2f14041` | `HumanEdit/` | 5,751 条 |
| ReShapeBench | `3087richard/ReShapeBench` | `6250f37e29552b33a07f18f4c9a93156435ac027` | `ReShapeBench/` | 120 张源图、240 个编辑 case |

三个目录均已完成文件数和字节数校验。

## 3. 候选筛选进度

自动筛选代码位于当前目录：

- `select_candidates.py`：提取特征并按配额筛选。
- `rebalance_multi_instance.py`：将 v0 确定性重平衡为多实例增强 v1，并输出完整增删审计。
- `render_review_sheets.py`：生成候选可视化页面。
- `validate_selection.py`：检查数量、配额、路径和关键约束。

候选结果位于 `output/`。初始 v0 从 5,106 条符合任务类型的预选样本中选出 500 条：

| 来源 | 数量 | 组成 |
|---|---:|---|
| CompBench | 220 | add 50、remove 60、replace 50、multi-object add 30、multi-object remove 30 |
| HumanEdit | 180 | add 42、remove 60、replace 60、counting 18 |
| ReShapeBench | 100 | multi-object scene 70、single-object scene 30 |
| 合计 | 500 | 480 张不同源图、394 个不同场景组 |

v0 难度配额统计：

- 小目标（区域面积小于 2%）：125 条，占 25.0%。
- 多编辑目标：78 条，占 15.6%。
- 同类多实例代理标签：363 条，占 72.6%。
- 多显著物体场景：308 条。

CompBench 的选择优先覆盖不同 MOSE 视频前缀，避免从少量视频连续抽取大量相邻帧。

### 3.1 多实例增强 v1

v1 纳入全部 116 条通过严格质量检查的 CompBench 显式多实例 case，并用以下 56 条替换另外 56 条：

- 18 条无法可靠生成 `region_only` 指令的 HumanEdit counting case。
- 20 条与另一 case 共享完全相同 source/region 的 ReShapeBench 冗余目标变体；每组保留目标描述更简洁的一条。
- 18 条剩余单目标样本中最终 region 面积最大的 case。

重平衡后的组成：

| 来源 | 数量 | 组成 |
|---|---:|---|
| CompBench | 269 | add 50、remove 58、replace 45、multi-object add 58、multi-object remove 58 |
| HumanEdit | 154 | add 40、remove 56、replace 58 |
| ReShapeBench | 77 | multi-object scene 49、single-object scene 28 |
| 合计 | 500 | 500 张不同源图 |

关键变化：

| 指标 | v0 | v1 |
|---|---:|---:|
| 显式双实例编辑 | 60（12.0%） | 116（23.2%） |
| 小目标（最终 mask 面积小于 2%） | 144（28.8%） | 137（27.4%） |
| region 面积不超过 10% | 347 | 367 |
| region 面积超过 20% | 51 | 26 |
| region 面积中位数 | 6.47% | 5.89% |
| 不同源图 | 480 | 500 |
| 可用 `region_only` 指令 | 482 | 500 |

完整增删 ID、删除原因和前后统计记录在 `output/multi_instance_rebalance_report.json`。

## 4. 自动质量检查与区域构建

CompBench 和 HumanEdit 共 423 条 v1 样本全部通过当前的严格自动检查：

- 每个编辑目标的面积和连通域数量满足规则。
- GT 与源图之间至少 80% 的显著变化像素落在膨胀后的编辑区域内。
- 同一区域至少包含 40% 的 RGB 绝对差异总量。
- HumanEdit mask 从 `MASK_IMG` 的 alpha 通道恢复，使用 `alpha < 128`，而不是根据黑色 RGB 像素判断。

GT 局部一致性统计：

- 最低变化像素区域内比例：0.80004。
- 中位变化像素区域内比例：0.97739。

ReShapeBench 的 77 条 v1 记录已使用固定 revision 的 Grounding DINO 与 SAM2 生成语义实例 mask。检查中发现部分官方 locator 过粗或明显偏位，因此 locator 仅用于候选排序的弱先验；最终 `regions[].mask`、`box` 和 `evaluation_mask` 均由语义定位后的实例区域生成。ReShapeBench 没有目标 GT 图片，使用局部/全局目标文本进行 reference-free 评测。

CompBench 的 116 条显式多目标记录均导出为两个 `regions`。其中 100 条可直接从官方 union mask 的主要连通域拆分；两条记录各抑制了 5 个孤立编码噪声像素。14 条粘连实例使用 Grounding DINO + SAM2 辅助分区；另有一组成对的 add/remove 鱼类 case 根据指令中的 left/right 关系进行确定性空间分区。粘连分区强制两个区域互斥且并集保持官方 mask 不变。

最终自动验证结果：

- 500 条记录、500 个唯一 ID。
- 500 张不同源图、423 张目标参考图。
- 616 个输入区域 mask、500 个 evaluation mask。
- 500 条记录均提供 `region_only` 指令。
- 所有引用路径存在；图像/mask 尺寸一致；mask 均为 0/255 二值图。
- 所有 box 均使用合法的半开区间坐标，point 均落在对应 mask 内。
- 验证状态：`passed`，错误数为 0。

## 5. 当前产物

```text
finegrained_edit_benchmark_selection/
├── build_unified_benchmark.py
├── rebalance_multi_instance.py
├── render_unified_examples.py
├── select_candidates.py
├── render_review_sheets.py
├── validate_selection.py
├── BENCHMARK_PROGRESS.md
├── benchmark_v0/
│   ├── benchmark.jsonl
│   ├── benchmark_meta.json
│   ├── validation_report.json
│   └── visual_examples/
├── benchmark_v1/
│   ├── benchmark.jsonl
│   ├── benchmark_meta.json
│   ├── validation_report.json
│   └── visual_examples/
└── output/
    ├── selected_500.jsonl
    ├── selected_500.csv
    ├── selected_500_multi_instance_v1.jsonl
    ├── selected_500_multi_instance_v1.csv
    ├── multi_instance_rebalance_report.json
    ├── selection_stats.json
    ├── all_preselection_features.jsonl
    ├── human_review_template.csv
    └── review_sheets/
```

原始 v0 可视化审核页共 21 张，覆盖其全部 500 条候选：

- CompBench：9 张。
- HumanEdit：8 张。
- ReShapeBench：4 张。

最终 benchmark manifest 的 SHA256：

```text
a795cf1b935e5a55d9122dad1ca9cd77e2a268dd70b515f24e6e2a2484ec4507
```

完整 v1 数据目录大小约 544 MB；构建诊断保存在数据目录的 `build_report.json`，不会进入最终逐条 manifest。

## 6. 最终 benchmark 的精简统一格式

一条 JSONL 记录表示一个编辑 case。最终记录只保留模型输入、评测目标、评测区域以及分组报告所必需的信息。下面为字段结构示意：

```json
{
  "id": "reshape_000101_1",
  "source_dataset": "reshape_bench",
  "edit_type": "replace",
  "source_image": "images/source/reshape/000101.jpg",
  "instruction": {
    "with_location_reference": "Change the classic street lamp into a modern solar-powered light pole",
    "region_only": "Change {region_1} into a modern solar-powered light pole"
  },
  "regions": [
    {
      "mask": "regions/input/reshape_000101_1_1.png",
      "box": [114, 197, 387, 453],
      "point": [250, 320]
    }
  ],
  "evaluation_mask": "regions/evaluation/reshape_000101_1.png",
  "target": {
    "reference_image": null,
    "expected_local_content": "a modern solar-powered light pole",
    "expected_global_description": "A vintage steam locomotive ... A modern solar-powered light pole ..."
  },
  "difficulty": {
    "same_class_multi_instance": false,
    "multi_object_scene": true
  }
}
```

### 6.1 Source 与 target 的命名边界

- `source_image`：编辑前、实际输入模型的图片。
- `target.reference_image`：编辑后期望得到的 GT 图片，只用于评测；ReShapeBench 为 `null`。
- `target.expected_local_content`：编辑完成后，目标区域内期望出现的内容，用于区域文本对齐和 judge。
- `target.expected_global_description`：编辑完成后整张图片的期望描述；没有可靠全局描述时允许为 `null`。

因此，所有 `target.*` 字段都描述编辑后的期望结果，不描述 source 中原有的内容，也不会作为编辑模型输入。

### 6.2 三种区域输入的统一表达

每个 `regions` 元素对应一个编辑目标，并同时保存：

- `mask`：与源图同尺寸、取值为 0/255 的单通道 PNG。
- `box`：`[x1, y1, x2, y2)` 像素坐标。
- `point`：mask 内距离边界最远的点 `[x, y]`。

数组顺序就是区域编号。`{region_1}`、`{region_2}` 等模型无关占位符由运行适配器转换为 SAMTok 的 `⟨M1⟩`、`⟨M2⟩`，或者基模可理解的 marked object 编号。

`len(regions)` 可直接得到编辑目标数，因此最终格式不再重复保存 `target_count` 和 `multi_target`。

### 6.3 三个数据集的映射

| 统一字段 | CompBench | HumanEdit | ReShapeBench |
|---|---|---|---|
| `source_image` | `input_image` | `INPUT_IMG` | `file_name` |
| `target.reference_image` | `edited_image` | `OUTPUT_IMG` | `null` |
| `instruction.with_location_reference` | `instruction` | `EDITING_INSTRUCTION` | `instruction` |
| `instruction.region_only` | 自动去指代改写 | 自动去指代改写 | 使用 `{region_1}` 绑定目标 |
| `edit_type` | add/remove/replace | add/remove/replace；counting 在 v1 中排除 | 统一映射为 replace |
| `regions[].mask` | 官方实例 mask；多目标 union 拆为逐实例区域 | 手绘 alpha mask | 文本 grounding 后经 SAM2 得到的实例 mask |
| `regions[].box` | mask 外接框加 padding | mask 外接框加 padding | SAM2 mask 外接框加 padding |
| `regions[].point` | mask 最内点 | mask 最内点 | SAM2 mask 最内点 |
| `evaluation_mask` | 区域并集膨胀 2% | 区域并集膨胀 2% | grounded SAM2 mask 外接矩形膨胀 2% |
| `target.expected_local_content` | `caption` | `OUTPUT_DESCRIPTION` | `foreground_target` |
| `target.expected_global_description` | 无可靠描述时为 `null` | `OUTPUT_CAPTION_BY_LLAMA` | `target_prompt` |

CompBench 的 `multi_object_add` 和 `multi_object_remove` 分别归一化为 `add` 和 `remove`，多目标信息由 `regions` 数组表达。ReShapeBench 的 `single_object` 和 `multi_object` 描述的是场景复杂度，不作为编辑类型。

## 7. 不进入最终 manifest 的构建信息

以下字段仅服务于筛选、诊断或审核，不进入最终 benchmark JSONL：

- `source_shard`、`source_row`、选择分数和候选排序。
- 面积、连通域、像素变化比例等自动质量检查中间量。
- 审核状态、审核意见和审核人。
- SAM2 运行状态、置信度和诊断信息。
- 渲染图路径、审核页路径。

全局固定信息，例如 benchmark 版本、坐标格式、小目标阈值、mask 取值、区域膨胀比例和标记渲染参数，统一存入 `benchmark_meta.json`，不在每条记录中重复。

## 8. 后续可选工作

当前多实例增强 v1 已可用于评测。冻结公开版本前仍可进行一次人工 spot-check，并补充具体模型运行适配器与 metric 实现；这些工作不改变当前统一字段设计。
