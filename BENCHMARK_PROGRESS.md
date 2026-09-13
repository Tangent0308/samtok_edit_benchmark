# SAMTok 细粒度交互式编辑 Benchmark 构建进度

## 1. 当前状态

三个源数据集已完成固定 revision 下载、候选筛选、区域规范化、统一格式导出和自动验证。当前只维护一份正式数据，不再使用版本后缀：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark/
```

仓库中的 `benchmark/` 保存轻量级 manifest、metadata、验证报告和可视化；完整图片与 mask 资产保存在上述外部目录。当前正式 benchmark 共 500 条，每条使用不同的 source image。

| 统计项 | 数量 |
| --- | ---: |
| 总 case / 唯一 source image | 500 / 500 |
| CompBench / HumanEdit / ReShapeBench | 269 / 154 / 77 |
| add / remove / replace | 148 / 172 / 180 |
| 单区域 / 双区域 case | 384 / 116 |
| 小目标 case | 137（27.4%） |
| target reference image | 423 |
| input region mask | 616 |
| evaluation mask | 500 |

## 2. 数据来源与固定 revision

三个原始数据目录：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/CompBench/
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/HumanEdit/
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/ReShapeBench/
```

| 数据集 | Hugging Face 仓库 | Revision | 当前用途 |
| --- | --- | --- | --- |
| CompBench | `BohanJia/CompBench` | `a4c5a4d1854056d24aad43a494772dc90588d426` | add、remove、replace；含显式双实例编辑 |
| HumanEdit | `BryanW/HumanEdit` | `dbc60b9ba3c17adf59e1effd8a9d92bdf2f14041` | 高质量局部 add、remove、replace |
| ReShapeBench | `3087richard/ReShapeBench` | `6250f37e29552b33a07f18f4c9a93156435ac027` | reference-free replace；补充复杂场景和形状变化 |

涉及语义实例区域推导时，固定使用：

- Grounding DINO：`IDEA-Research/grounding-dino-tiny@a2bb814dd30d776dcf7e30523b00659f4f141c71`
- SAM2：`facebook/sam2.1-hiera-small@e07df6aa19f5c6545121551bf89957b7663ee715`

## 3. Case 选择策略

选择目标是突出细粒度、小目标、精确定位和多实例编辑，同时维持数据集来源与编辑类型的覆盖。

- 纳入全部 116 条通过严格自动检查的 CompBench 显式双实例 add/remove case；统一拆成两个独立 `regions`，使模型明确接收两个编辑目标。
- 用局部目标替换了非局部 counting、区域过大、指令冗余或精确性较弱的样本。最终不包含 counting。
- 保留 137 条小目标样本；367 条样本的编辑区域不超过图像面积的 10%，仅 26 条超过 20%。区域面积中位数为 5.89%。
- CompBench 与 HumanEdit 只保留 source、target、mask 尺寸一致且变化主要落在标注区域内的样本。
- ReShapeBench 的官方 locator 仅作为弱定位先验；最终输入 mask、box 和 evaluation mask 由语义 grounding 与 SAM2 实例分割生成。
- 每条 case 使用唯一 source image，避免相同输入图造成评测泄漏或单一场景权重过高。

完整选择记录位于 `selection/selected_500.jsonl`，便于构建脚本回溯源数据；便于人工浏览的列子集位于 `selection/selected_500.csv`，全局统计位于 `selection/selection_stats.json`。

## 4. 最终统一数据格式

`benchmark/benchmark.jsonl` 每行是一条独立编辑任务，只保留实际评测所需信息：

```json
{
  "id": "case id",
  "source_dataset": "compbench | humanedit | reshape_bench",
  "edit_type": "add | remove | replace",
  "source_image": "relative/path/to/source.png",
  "instruction": {
    "with_location_reference": "original spatial instruction",
    "region_only": "instruction using {region_1}, {region_2}, ..."
  },
  "regions": [
    {
      "mask": "relative/path/to/input_mask.png",
      "box": [0, 0, 100, 100],
      "point": [50, 50]
    }
  ],
  "evaluation_mask": "relative/path/to/evaluation_mask.png",
  "target": {
    "reference_image": "relative/path/to/target.png or null",
    "expected_local_content": "expected content inside the edited region",
    "expected_global_description": "expected post-edit scene description or null"
  },
  "difficulty": {
    "same_class_multi_instance": false,
    "multi_object_scene": true
  }
}
```

字段语义如下：

- `source_image`：模型需要编辑的输入图片。
- `instruction.with_location_reference`：保留源数据中的空间关系描述。
- `instruction.region_only`：将位置绑定到 `{region_N}`，适合显式 mask/box/point 交互评测。
- `regions`：模型输入区域；数组顺序对应 `{region_1}`、`{region_2}`。`box` 为像素坐标的半开区间 `xyxy`，`point` 位于 mask 内部。
- `evaluation_mask`：指标计算使用的区域，比输入 mask 略有扩张，以容纳合理的边界变化。
- `target.reference_image`：期望的编辑后参考图。CompBench 和 HumanEdit 有参考图，ReShapeBench 为 `null`。
- `target.expected_local_content`：编辑后应在目标区域出现的内容，不是源图中待移除内容。
- `target.expected_global_description`：编辑后整图的目标描述；当前主要由 ReShapeBench 提供。
- `difficulty`：可直接用于多物体场景和同类多实例子集统计。

`target` 下的三个字段全部描述编辑完成后的期望结果，只供 evaluator 使用，不应作为模型输入。统一格式避免了三个源数据集在图片列、mask 表示、任务命名和参考信息方面的差异。

## 5. 区域构造

- CompBench：使用发布的实例 mask；双目标 union 被拆为两个实例区域。对相连的实例使用 Grounding DINO + SAM2 进行语义分区，密集重叠且语义检测不稳定的鱼类 case 使用指令约束的空间分割。小于显著性阈值的孤立编码噪点会被抑制。
- HumanEdit：从 `MASK_IMG` 的 alpha 通道提取原始人工笔刷区域。
- ReShapeBench：以前景文本进行 grounding，再通过 SAM2 得到精确实例 mask。
- `box`：由实例 mask 的包围框向外扩张短边的 2%。
- `point`：mask 内欧氏距离变换最大的像素，即离边界最远的稳定交互点。
- `evaluation_mask`：CompBench/HumanEdit 使用输入区域 union 的 2% 扩张；ReShapeBench 使用 grounded 实例框的 2% 扩张矩形。

## 6. 可视化结果

下图直接来自当前 `benchmark.jsonl` 与其完整资产。红色/绿色表示不同输入实例区域，蓝色淡层表示 evaluation mask；有 GT 的数据集在右侧显示目标参考图。

### CompBench：显式多实例与精确 add/remove

![CompBench 当前示例](benchmark/visual_examples/compbench_examples.png)

### HumanEdit：局部 add/remove/replace

![HumanEdit 当前示例](benchmark/visual_examples/humanedit_examples.png)

### ReShapeBench：语义定位后的 reference-free replace

![ReShapeBench 当前示例](benchmark/visual_examples/reshape_bench_examples.png)

## 7. 当前目录结构

```text
finegrained_edit_benchmark_selection/
├── BENCHMARK_PROGRESS.md
├── README.md
├── benchmark/
│   ├── benchmark.jsonl
│   ├── benchmark_meta.json
│   ├── validation_report.json
│   └── visual_examples/
│       ├── compbench_examples.png
│       ├── humanedit_examples.png
│       └── reshape_bench_examples.png
├── selection/
│   ├── selected_500.jsonl
│   ├── selected_500.csv
│   └── selection_stats.json
├── build_unified_benchmark.py
└── render_unified_examples.py
```

完整数据目录：

```text
samtok_edit_benchmark/
├── benchmark.jsonl
├── benchmark_meta.json
├── validation_report.json
├── build_report.json
├── images/
│   ├── source/
│   └── target/
├── regions/
│   ├── input/
│   └── evaluation/
└── visual_examples/
```

## 8. 验证结果与复现命令

`benchmark/validation_report.json` 当前状态为 `passed`，已检查：

- 500 条记录与 500 个唯一 ID；
- 500 张唯一 source image；
- 所有相对路径存在且不越出 benchmark root；
- 图片、input mask、evaluation mask 尺寸一致；
- mask 为单通道二值 PNG 且非空；
- box/point 合法，point 位于对应实例 mask 内；
- `{region_N}` 与 `regions` 数量一致；
- 顶层字段严格等于统一精简 schema；
- `reference_image = null` 只出现在 ReShapeBench。

从固定源数据重新物化并生成可视化：

```bash
python build_unified_benchmark.py
python render_unified_examples.py
python render_unified_examples.py --output benchmark/visual_examples
```

## 9. 推理评测实现与状态

`evaluation/` 已实现 Qwen-Image-Edit-2511、FLUX.2-klein-4B 与 Refined 四机
SAMTokEdit 的 15-setting DiffSynth 推理协议、交互输入预处理、逐图 sidecar、严格断点续跑和
八卡启动器。正式输出与日志统一写到：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/finegrained_edit_benchmark/
```

预处理已经完成，冻结的 prepared manifest 为
`prepared/benchmark_eval_inputs.jsonl`，共 500 条，SHA256 为
`a50721359ecc1ac79986dc7959cc76a90bc47e550215d946e57379c4894e66e9`。其中包含
1,500 张可视化交互输入、1,232 张 box/point 提示产生的 SAM2 mask，以及 1,848 个
region/modality SAMTok span。具体统计与 SAM2 IoU 诊断见
`prepared/preparation_report.json`。

两个基模都使用 `/opt/tiger/tanyue/samtok_edit/DiffSynth-Studio`。FLUX.2-dev 的 Hugging
Face 仓库对当前账号不可访问，因此按照方案允许的 dev/klein 二选一，固定为公开的
`black-forest-labs/FLUX.2-klein-4B@e7b7dc27f91deacad38e78976d1f2b499d76a294`。
Refined 四机 SAMTokEdit 的两阶段 LoRA 路径和文件哈希均在启动前严格校验。

全量协议已经完成并产生 7,500 个结果图与 sidecar，其中 6,500 次为随机生成，另
1,000 个 paste-back 结果由对应的 mask-annotation 输出确定性合成。完整性验证和
inference protocol 审计均为 `passed`：15 个 setting 各 500 条、无缺失，1,000 个
paste-back 结果逐像素一致。结果和审计报告位于：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/finegrained_edit_benchmark/
```

当前尚未计算任何质量指标，也未调用 judge。构建/标注流程、模型与 checkpoint、
15 个 setting、运行命令、完整结果目录、审计结论及代表性可视化统一记录在
[`BENCHMARK_CONSTRUCTION_AND_EVALUATION.md`](BENCHMARK_CONSTRUCTION_AND_EVALUATION.md)；
简要运行说明见 [`evaluation/README.md`](evaluation/README.md)。
