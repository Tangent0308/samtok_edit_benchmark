# 细粒度交互式编辑 Benchmark：构建进度与格式约定

最后更新：2026-09-07

## 1. 当前状态

当前已经完成三个源数据集的下载与完整性检查、全量自动特征扫描、500 条候选样本的配额筛选，以及全部候选样本的可视化审核页生成。

当前的 `selected_500.jsonl` 是 **自动筛选候选集**，还不是最终冻结的 benchmark。最终统一格式已经完成字段设计，但尚未执行图片、mask 和 manifest 的正式导出。

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
- `render_review_sheets.py`：生成候选可视化页面。
- `validate_selection.py`：检查数量、配额、路径和关键约束。

候选结果位于 `output/`。当前从 5,106 条符合任务类型的预选样本中选出 500 条：

| 来源 | 数量 | 组成 |
|---|---:|---|
| CompBench | 220 | add 50、remove 60、replace 50、multi-object add 30、multi-object remove 30 |
| HumanEdit | 180 | add 42、remove 60、replace 60、counting 18 |
| ReShapeBench | 100 | multi-object scene 70、single-object scene 30 |
| 合计 | 500 | 480 张不同源图、394 个不同场景组 |

当前难度配额统计：

- 小目标（区域面积小于 2%）：125 条，占 25.0%。
- 多编辑目标：78 条，占 15.6%。
- 同类多实例代理标签：363 条，占 72.6%。
- 多显著物体场景：308 条。

CompBench 的选择优先覆盖不同 MOSE 视频前缀，避免从少量视频连续抽取大量相邻帧。

## 4. 自动质量检查

CompBench 和 HumanEdit 共 400 条候选全部通过当前的严格自动检查：

- 每个编辑目标的面积和连通域数量满足规则。
- GT 与源图之间至少 80% 的显著变化像素落在膨胀后的编辑区域内。
- 同一区域至少包含 40% 的 RGB 绝对差异总量。
- HumanEdit mask 从 `MASK_IMG` 的 alpha 通道恢复，使用 `alpha < 128`，而不是根据黑色 RGB 像素判断。

GT 局部一致性统计：

- 最低变化像素区域内比例：0.80004。
- 中位变化像素区域内比例：0.97707。

ReShapeBench 当前仍有以下待处理项：

- 100 条都需要将官方 box locator 通过 SAM2 转换为实例 mask。
- 其中 30 条官方 box 区域面积超过实例 mask 的目标阈值。
- 其中 16 条官方 locator 的连通域数量偏多。
- ReShapeBench 没有目标 GT 图片，后续使用文本目标描述和 reference-free 指标评测。

## 5. 当前产物

```text
finegrained_edit_benchmark_selection/
├── select_candidates.py
├── render_review_sheets.py
├── validate_selection.py
├── BENCHMARK_PROGRESS.md
└── output/
    ├── selected_500.jsonl
    ├── selected_500.csv
    ├── selection_stats.json
    ├── all_preselection_features.jsonl
    ├── human_review_template.csv
    └── review_sheets/
```

可视化审核页共 21 张，覆盖全部 500 条候选：

- CompBench：9 张。
- HumanEdit：8 张。
- ReShapeBench：4 张。

当前候选 manifest 的 SHA256：

```text
bd6fbf2ae0c227590c089c208dfbf3db6e6fd741605851be426db8e887c32ae3
```

## 6. 最终 benchmark 的精简统一格式

一条 JSONL 记录表示一个编辑 case。最终记录只保留模型输入、评测目标、评测区域以及分组报告所必需的信息。下面仅为字段示意，其中坐标不是已冻结的真实标注：

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
    "same_class_instances": 1,
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
| `instruction.region_only` | 自动去指代改写 | 自动去指代改写；不适用时为 `null` | 使用 `{region_1}` 绑定目标 |
| `edit_type` | add/remove/replace | add/remove/replace/counting | 统一映射为 replace |
| `regions[].mask` | 官方实例 mask | 手绘 alpha mask | 官方 box 经 SAM2 得到的实例 mask |
| `regions[].box` | mask 外接框加 padding | mask 外接框加 padding | 官方 box |
| `regions[].point` | mask 最内点 | mask 最内点 | SAM2 mask 最内点 |
| `evaluation_mask` | 区域并集膨胀 2% | 区域并集膨胀 2% | 官方 box 膨胀 2% |
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

## 8. 下一步

1. 对 100 条 ReShapeBench case 执行 box-to-SAM2，并确认实例 mask。
2. 将 CompBench 多目标样本恢复为逐实例 `regions`。
3. 生成 `instruction.region_only`，并保留不适合去指代样本的 `null` 状态。
4. 补全三个数据集统一的 `target.expected_local_content` 与可用的全局目标描述。
5. 导出 source、target reference、逐实例 mask 和 evaluation mask。
6. 生成精简版 `benchmark.jsonl` 与全局 `benchmark_meta.json`。
7. 对最终 manifest 做路径、数量、区域坐标和可复现性校验后冻结版本。
