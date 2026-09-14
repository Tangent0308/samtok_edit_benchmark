# SAMTok 细粒度交互式编辑 Benchmark 说明

本文档是当前 benchmark 唯一的详细说明，记录评测目标、数据构建、两个基模
的推理实现、运行方式与结果位置。当前阶段只包含
Qwen-Image-Edit-2511 和 FLUX.2-klein-4B，不计算质量指标，也不调用 judge。

## 1. 评测目标

本 benchmark 关注同类多实例场景中的指代性、细粒度局部编辑：当一张图中
存在多个外观相近的实例时，模型能否只编辑被文字或交互信号指向的一个或
多个目标，并保持其他实例和背景不变。

每个 case 提供四种输入 setting：

| Setting | 定位信息 | 主要考察内容 |
| --- | --- | --- |
| `text_only` | 原始空间/指代 instruction | 模型能否理解“第二个、最右侧、中间、位于两者之间”等文字指代 |
| `mask_annotation` | 精确或人工笔刷 mask | 显式区域能否帮助模型完成局部编辑 |
| `box_annotation` | 目标外接框 | 较弱区域提示下的实例选择与编辑能力 |
| `point_annotation` | 目标内部点 | 最稀疏交互下的目标定位能力 |

人工检查时主要观察：目标是否选对、编辑内容是否正确、编辑是否外溢、非目标
区域是否保持，以及模型是否错误保留了临时 mask/box/point。指标设计和 judge
不属于当前阶段，推理脚本也不会触发它们。

## 2. 当前数据

正式 benchmark 位于：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark/
```

| 统计项 | 数量 |
| --- | ---: |
| case / 唯一 ID | 556 / 556 |
| 唯一 source image | 555 |
| CompBench / HumanEdit | 532 / 24 |
| add / remove / replace | 258 / 265 / 33 |
| 单 region / 双 region | 516 / 40 |
| input region mask / evaluation mask | 596 / 556 |
| target reference image | 556 |

两个不同编辑任务共享一张像素相同的 source，因此唯一 source 数为 555。
ReShapeBench 已排除，不属于当前 benchmark。

### 2.1 源数据

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/CompBench/
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/HumanEdit/
```

| 数据集 | Hugging Face 仓库 | 固定 revision | 入选数 |
| --- | --- | --- | ---: |
| CompBench | `BohanJia/CompBench` | `a4c5a4d1854056d24aad43a494772dc90588d426` | 532 |
| HumanEdit | `BryanW/HumanEdit` | `dbc60b9ba3c17adf59e1effd8a9d92bdf2f14041` | 24 |

入选 case 强调相邻同类实例及位置/方向指代，包括极值位置、序数、中间、两者
之间、相对方位和 `all except ...` 等排除式子集编辑。选择只使用源图片、原始
instruction、原始标注和 target 做数据一致性检查，没有使用任何模型输出或
judge 分数。最终选择记录位于 `selection/selected_cases.jsonl`，统计位于
`selection/selection_stats.json`。

### 2.2 统一字段

`benchmark/benchmark.jsonl` 每行是一条编辑任务，顶层字段固定为：

```text
id, source_dataset, edit_type, source_image, instruction,
regions, evaluation_mask, target, difficulty
```

核心结构如下：

```json
{
  "id": "case id",
  "source_dataset": "compbench | humanedit",
  "edit_type": "add | remove | replace",
  "source_image": "images/source/...png",
  "instruction": {
    "with_location_reference": "原始位置/指代 instruction",
    "region_only": "使用 {region_1}, {region_2} 绑定交互区域的 instruction"
  },
  "regions": [
    {
      "mask": "regions/input/...png",
      "box": [0, 0, 100, 100],
      "point": [50, 50]
    }
  ],
  "evaluation_mask": "regions/evaluation/...png",
  "target": {
    "reference_image": "images/target/...png",
    "expected_local_content": "期望的编辑后局部内容",
    "expected_global_description": null
  },
  "difficulty": {
    "same_class_multi_instance": true,
    "multi_object_scene": true
  }
}
```

所有路径相对于正式 benchmark 根目录。box 使用半开区间像素坐标
`[x1, y1, x2, y2)`，point 使用像素坐标 `[x, y]`。`regions` 的数组顺序
对应 `{region_1}`、`{region_2}` 以及可视化中的 R1、R2。

`target.*` 和 `evaluation_mask` 只用于人工检查或未来评价。推理结果 sidecar
可以记录这些路径作为 provenance，但它们不会进入模型的图片列表或 prompt。

### 2.3 Mask、box、point 构建

- CompBench 保留发布的二值 mask。
- HumanEdit 使用 `MASK_IMG` 中 `alpha < 128` 的原始人工笔刷区域，不做 SAM
  精修。
- 39 条双目标 CompBench case 的两个连通分量直接成为 R1/R2。
- 另有一条双鸟 case 的发布 mask 是连通 union。构建时使用固定版本的
  Grounding DINO 与 SAM2 只在原 union 内进行语义分区；两个子 mask 不重叠，
  union 与发布 mask 逐像素一致，没有添加或删除 mask 像素。
- box 是 mask 紧致外接框向外扩张图像短边的 2%。
- point 是 mask 内到边界欧氏距离最大的像素；距离变换前在画布外补一圈背景，
  从而同时考虑图像边界。
- evaluation mask 是所有 input mask 的 union，再向外膨胀短边的 2%。

用于唯一一次连通 union 分区的模型固定为：

```text
IDEA-Research/grounding-dino-tiny@a2bb814dd30d776dcf7e30523b00659f4f141c71
facebook/sam2.1-hiera-small@e07df6aa19f5c6545121551bf89957b7663ee715
```

`verify_source_masks.py` 已重新读取全部源 parquet；556 条 case 的物化 region
union 与源 mask mismatch 为 0。`benchmark/validation_report.json` 状态为
`passed`，检查了 schema、ID、资源路径、图片尺寸、二值 mask、box、point、
region placeholder 和 target reference。

### 2.4 数据重建

```bash
cd /opt/tiger/tanyue/finegrained_edit_benchmark_selection
CUDA_VISIBLE_DEVICES=0 python build_unified_benchmark.py
python verify_source_masks.py
python render_unified_examples.py --output benchmark/visual_examples
```

代表性原始数据：

![CompBench 示例](benchmark/visual_examples/compbench_examples.png)

![HumanEdit 示例](benchmark/visual_examples/humanedit_examples.png)

## 3. 两个基模的评测实现

### 3.1 模型与代码

| 模型 | 本地权重 | DiffSynth pipeline |
| --- | --- | --- |
| Qwen-Image-Edit-2511 | `/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/Qwen-Image-Edit-2511/` | `QwenImagePipeline` |
| FLUX.2-klein-4B | `/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/FLUX.2-klein-4B/` | `Flux2ImagePipeline` |

两者均使用下列 vendored DiffSynth：

```text
/opt/tiger/tanyue/samtok_edit/DiffSynth-Studio/
```

Qwen 直接从本地 transformer、text encoder、VAE、tokenizer 和 processor
构造 `QwenImagePipeline`；FLUX.2 直接从本地 text encoder、transformer、
VAE 和 tokenizer 构造 `Flux2ImagePipeline`。运行前会检查模型索引和权重分片。

### 3.2 最终双图 locator 协议

基模没有 benchmark 所需的统一原生 mask/box/point control 参数。最终协议
使用两个模型均支持的多参考图接口，并把干净内容与临时标记分开：

| Setting | 传入 DiffSynth 的有序 `edit_image` |
| --- | --- |
| `text_only` | `[clean_source]` |
| `mask_annotation` | `[clean_source, mask_locator]` |
| `box_annotation` | `[clean_source, box_locator]` |
| `point_annotation` | `[clean_source, point_locator]` |

locator 是 source 的独立副本：单 region 使用无编号红色标记，双 region 按
benchmark 顺序使用红色 R1、绿色 R2。mask 使用半透明填充和实线边界；box
使用矩形；point 使用大小适中的实心圆点和细白色描边，圆心严格等于
`regions[].point`。

交互 prompt 明确说明：第一张参考图是需要编辑的干净 source，第二张只用于
定位；编辑必须作用在第一张图的对应对象或位置；不得复制第二张图中的 mask、
轮廓、box、point 或 R 标签；其他内容来自第一张图并应保持不变。target
reference 从不作为第三张输入图。

该调用方式位于模型支持范围内：Qwen 2511 的 DiffSynth 示例将其定义为
multi-image editing model，并要求 `edit_image` 使用 list；FLUX.2-klein-4B
模型说明和 DiffSynth pipeline 均支持 multi-reference。需要区分的是，“第二张
图仅用于定位”是本 benchmark 的 prompt 约定，不是模型原生的 mask-control
张量。若模型仍复制 marker，则作为模型失败保留，不做事后擦除。

选择双图而不是只输入标注图，是因为单图协议把 marker 覆盖在唯一的待编辑
图像上，同时要求模型保留原图又去掉 marker，容易产生 mask 轮廓、box 或
point 残留。代表性 smoke test 表明双图通常能减轻这一问题，但并非完全消除。

### 3.3 冻结输入

`evaluation/prepare_inputs.py` 并行渲染三种 locator，并为每个 case 冻结四个
setting。每个 setting 保存：

- `images`：模型接收的绝对路径列表，顺序不可交换；
- `image_roles`：与图片逐项对应的角色；
- `prompt`：实际传入模型的完整文本。

正式输入位于：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/
  referential_finegrained_edit_benchmark_two_image_locator/
    inputs/mask_annotation/                 # 556 locator images
    inputs/box_annotation/                  # 556 locator images
    inputs/point_annotation/                # 556 locator images
    prepared/baseline_inputs.jsonl
    prepared/benchmark_baseline_eval_inputs.jsonl
    prepared/baseline_input_report.json
```

当前冻结输入协议为 `baseline_two_image_locator_inputs_v1`。共有 1,668 张
locator，556 行 inference manifest，每行四个 setting。输入准备不读取任何
target 内容来构造图片或 prompt。

### 3.4 Inference 参数与输出

| 参数 | Qwen-Image-Edit-2511 | FLUX.2-klein-4B |
| --- | ---: | ---: |
| seed | 0 | 0 |
| sampling steps | 40 | 4 |
| CFG | 4.0 | 1.0 |
| 额外参数 | `zero_cond_t=True` | `embedded_guidance=4.0` |

生成尺寸保持 source 宽高比、面积约为 1024×1024，并对齐到 32；生成后使用
Lanczos resize 回 source 的准确尺寸。8 卡运行时每个 worker 只加载一次模型，
case 按 `rows[rank::world_size]` 确定性切分。

每张输出同时写入 PNG 和 JSON sidecar。sidecar 包含 case/model/setting、实际
有序输入路径与角色、完整 prompt、seed、原生生成尺寸、保存尺寸、耗时和输出
路径。`run_config.json` 固定整个运行的模型、manifest hash、参数与并行配置，
因此 `--resume` 不会混入不同协议生成的结果。

相关代码只保留当前两基模所需部分：

```text
evaluation/common.py                    协议、渲染和公共校验
evaluation/prepare_inputs.py             构造双图输入与冻结 manifest
evaluation/run_inference.py              两个 DiffSynth inference adapter
evaluation/launch_baseline_inference.sh  8 卡 tmux 任务入口
evaluation/report_baseline_progress.py   实时进度
evaluation/validate_baseline_outputs.py  输出结构与 provenance 校验
```

## 4. 运行方式

### 4.1 准备输入

```bash
cd /opt/tiger/tanyue/finegrained_edit_benchmark_selection
/opt/tiger/tanyue/samtok_edit/.venv/bin/python \
  evaluation/prepare_inputs.py --resume
```

### 4.2 配置检查和单模型运行

```bash
# 不加载模型，只检查 Qwen 配置、权重和全部冻结输入。
/opt/tiger/tanyue/samtok_edit/.venv/bin/python \
  evaluation/run_inference.py --model qwen --dry_run

# 独立实验目录中的单 case smoke test。
CUDA_VISIBLE_DEVICES=0 \
/opt/tiger/tanyue/samtok_edit/.venv/bin/python \
  evaluation/run_inference.py \
  --model flux2 --settings all --max_samples 1 \
  --experiment_root /tmp/samtok_flux2_smoke
```

### 4.3 8 卡全量推理

```bash
tmux new-session -d -s samtok_baselines_two_image_556 \
  -c /opt/tiger/tanyue/finegrained_edit_benchmark_selection \
  'bash evaluation/launch_baseline_inference.sh'
```

controller 依次运行 Qwen 和 FLUX.2，每个模型包含 556 × 4 个 setting；总计
4,448 张输出。任务可恢复，并在两个模型结束后自动运行结构验证。它不会运行
paste-back、质量指标或 judge。

### 4.4 查看进度与验证

```bash
python evaluation/report_baseline_progress.py

tail -f /mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/\
referential_finegrained_edit_benchmark_two_image_locator/logs/baseline_progress.log

tail -f /mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/\
referential_finegrained_edit_benchmark_two_image_locator/logs/baseline_inference.log

# 全部完成后检查 4,448 张图片、sidecar、输入顺序、prompt 和 run config。
python evaluation/validate_baseline_outputs.py
```

## 5. 基模评测结果

待全量 inference 完成并经过人工检查后补充。
