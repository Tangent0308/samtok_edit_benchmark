# SAMTok 细粒度交互式图像编辑 Benchmark

本文介绍 benchmark 的构造、评测方法和使用方式。模型运行记录、评分状态与案例分析见 [MODEL_RESULTS.md](MODEL_RESULTS.md)。

## 1. 目标与任务

考察同类多实例场景中的指代性局部编辑：在多个外观相似的对象中，能否选对目标、完成要求，并保持其他实例和背景不变。656 个 case 每个提供四种输入设置；每种被测系统生成 2,624 张图。

| 设置 | 定位信息 | 考察内容 |
| --- | --- | --- |
| `text_only` | 文字空间与指代关系 | 第几个、最左/右、中间、between、排除式指代 |
| `mask_annotation` | 区域 mask locator | 精确区域指向后的局部编辑 |
| `box_annotation` | 矩形框 locator | 较弱的区域指向 |
| `point_annotation` | 目标内的点 locator | 稀疏定位信号 |

仓库保留构造选择记录、656-case 清单、源 mask 核验、图示、三种基模与 RePlan 的评测代码，以及双图单次 MLLM judge。图像、权重和大规模推理产物放在挂载盘；本仓库保存对应路径、配置与摘要。

## 2. 数据与构造

正式 benchmark 位于：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark/
```

| 统计项 | 数量 |
| --- | ---: |
| case / 唯一 ID | 656 / 656 |
| 唯一 source image | 655 |
| CompBench / HumanEdit / MIRAGE | 532 / 24 / 100 |
| add / remove / replace / mixed | 260 / 268 / 94 / 34 |
| 单 region / 双 region | 517 / 139 |
| input region mask / evaluation mask | 795 / 656 |
| target reference image | 556 |

CompBench 中两个不同任务共享一张 source，因此唯一 source 数为 655。全部
CompBench/HumanEdit case 有 target；MIRAGE 未发布编辑后 GT，100 条的
`target.reference_image` 均为 `null`。ReShapeBench 已排除。

### 2.1 源数据

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/CompBench/
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/HumanEdit/
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/MIRAGE/benchmark/
```

| 数据集 | Hugging Face 仓库 | 固定 revision | 入选数 |
| --- | --- | --- | ---: |
| CompBench | `BohanJia/CompBench` | `a4c5a4d1854056d24aad43a494772dc90588d426` | 532 |
| HumanEdit | `BryanW/HumanEdit` | `dbc60b9ba3c17adf59e1effd8a9d92bdf2f14041` | 24 |
| MIRAGE | `ziqiangoodgood/MIRAGE` | `11eff1e3f396e189e61bd1f0ca596286d8a0b183` | 100 |

所有筛选只使用源图片、原始 instruction、发布标注，以及 CompBench/HumanEdit
的 target 做数据一致性检查；没有使用任何模型输出、指标或 judge 分数。

#### CompBench（532 条）

先按文本检索极值位置、序数、中间、between、相对方位和 `all except ...` 等
指代，再逐图检查：同类比较实例确实存在，文字能够唯一解析目标，发布 mask
与 target 的局部变化一致。add/remove/replace 分别为 255/255/22，其中 40 条
是双实例编辑。选择与源 parquet 行号记录在
`selection/selected_cases.jsonl`。

#### HumanEdit（24 条）

从候选中只保留同类多实例、小部件或排除式编辑，并核对 source、人工笔刷
mask、target 的尺寸和语义一致性。保留原始 `MASK_IMG` 的人工 alpha 笔刷，
不使用 SAM 精修。add/remove/replace 为 3/10/11；全部为单 region。选择记录
与 CompBench 共用 `selection/selected_cases.jsonl`。

#### MIRAGE（100 条）

MIRAGE 每张 1024×1024 source 发布 5 个候选编辑及其 polygon。这里对全部 100
张逐条做 five-to-one/two 筛选，而不执行原始 5 区域联合指令：优先选择眼、鼻、
喙、衣物局部等小部件，remove/replace 等结构敏感任务，以及 `leftmost`、
`middle`、`first/second from the left/right` 这类容易混淆的指代。只有当两个
编辑落在不同同类实例上、组合会增加“编辑内容—实例”绑定难度时才组成双
region；否则保留单 region。最终为 99 条双 region、1 条单 region，共 199 个
region；34 条跨操作组合用 `edit_type=mixed` 表示。

固定索引、原子编辑、最终 instruction 和逐条理由位于
`selection/mirage_selected_regions.jsonl`，生成器为
`selection/build_mirage_selection.py`，统计为
`selection/mirage_selection_stats.json`。五页全量审查图可用
`selection/render_mirage_selection.py` 生成到临时目录。总统计位于
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
  "source_dataset": "compbench | humanedit | mirage",
  "edit_type": "add | remove | replace | mixed",
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
    "reference_image": "images/target/...png | null",
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

`mixed` 仅用于 MIRAGE 双 region 中包含不同原子操作的 case。MIRAGE 没有
编辑后 GT，因此 `reference_image=null`，`expected_local_content` 保存所选局部
编辑的目标语义；不得据此计算需要 GT 图的指标。

`target.*` 和 `evaluation_mask` 不进入编辑模型输入。judge 使用原图、输出、
任务指令和 `regions[].mask`，不使用参考答案图。输出 sidecar 可记录参考路径以便复核。

### 2.3 Mask、box、point 构建

- CompBench 保留发布的二值 mask。
- HumanEdit 使用 `MASK_IMG` 中 `alpha < 128` 的原始人工笔刷区域，不做 SAM
  精修。
- MIRAGE 只栅格化入选的 1/2 个发布 polygon，方法与官方 metric 相同：PIL
  `ImageDraw.polygon(..., outline=1, fill=1)`；不改写或精修区域。
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

`verify_source_masks.py` 已重新读取 CompBench/HumanEdit 源 parquet，并读取
MIRAGE 发布 polygon；656 条 case 的物化 region union 与对应发布标注 mismatch
为 0。`benchmark/validation_report.json` 状态为
`passed`，检查了 schema、ID、资源路径、图片尺寸、二值 mask、box、point、
region placeholder，以及按数据源约束的 target reference。

### 2.4 数据重建

```bash
cd /opt/tiger/tanyue/samtok_edit_benchmark
BUILD_PY=/opt/tiger/tanyue/sam3-crispedit/.venv-prefilter-improved/bin/python
CUDA_VISIBLE_DEVICES=0 "$BUILD_PY" build_unified_benchmark.py \
  --output /tmp/samtok_benchmark_rebuild \
  --repo-manifest-dir /tmp/samtok_benchmark_manifest
"$BUILD_PY" verify_source_masks.py \
  --benchmark-root /tmp/samtok_benchmark_rebuild \
  --output /tmp/samtok_benchmark_manifest/source_mask_verification.json
"$BUILD_PY" render_unified_examples.py \
  --benchmark-root /tmp/samtok_benchmark_rebuild --output /tmp/samtok_benchmark_examples
```

该构造环境含 `cv2`、`pyarrow` 和 `transformers` 中的 Grounding DINO / SAM2 实现；基模推理环境不含 `cv2`，因此重建与推理分别使用上述两个 Python。完整重建会为一条连通 union mask 加载固定 revision 的 Grounding DINO 和 SAM2。评测使用已冻结的数据；重建写入独立目录，不覆盖正在运行的输入。

代表性原始数据：

![CompBench 示例](benchmark/visual_examples/compbench_examples.png)

![HumanEdit 示例](benchmark/visual_examples/humanedit_examples.png)

![MIRAGE 示例](benchmark/visual_examples/mirage_examples.png)

## 3. 编辑模型的输入与输出

### 3.1 冻结输入

text 设置输入一张干净原图；mask/box/point 设置输入有序的 `[clean source, annotated locator]`。locator 是原图的副本，单 region 使用红色标记，双 region 用红色 R1、绿色 R2：mask 为半透明填充和边界、box 为矩形、point 为带描边圆点。

交互 prompt 要求编辑 Image 1，用 Image 2 的标记绑定目标，并保持其余内容、禁止复现标记。例如：

```text
Edit Image 1. For R1 (red mask) in Image 2, <edit 1>.
For R2 (green mask) in Image 2, <edit 2>. Keep everything else unchanged.
Return only the edited Image 1 without any markers from Image 2.
```

这些是模型支持的多参考图接口上的视觉定位提示，不是模型原生 mask 张量控制。标记若被模型复制进输出，作为失败保留，不事后擦除。参考 target 和 evaluation mask 从不输入编辑模型；不使用粘贴回原图的后处理。

`evaluation/prepare_inputs.py` 冻结每条任务实际使用的图片顺序、图片角色和完整 prompt。所有系统读取同一份清单：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/
  referential_finegrained_edit_benchmark_656_two_image_locator/
    prepared/benchmark_baseline_eval_inputs.jsonl
    inputs/{mask_annotation,box_annotation,point_annotation}/
```

清单 SHA-256：`8a46bb7a2693984132ca203fcf7dc8f118b2563497dbea8c70497552865c56e2`。路径、协议标识和内容摘要用于核验与断点继续，不应在正在运行时重命名或覆盖。

### 3.2 三个基模

权重根目录为 `/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/`。

| 模型 / 权重子目录 | 官方 DiffSynth pipeline | 采样参数 |
| --- | --- | --- |
| `Qwen-Image-Edit-2511` | `QwenImagePipeline` | 40 步，CFG=4，`zero_cond_t=True` |
| `FLUX.2-klein-4B` | `Flux2ImagePipeline` | 4 步，CFG=1，embedded guidance=4 |
| `Qwen-Image-2.1` | `QwenImage21Pipeline` | 40 步，CFG=1，KV cache 开启 |

均为 BF16、每例固定 seed=0、无 prompt rewrite。输出保持源图比例，约 1024² 像素且对齐 32，保存时以 Lanczos 恢复源图尺寸。Qwen 使用 CPU 随机数，FLUX 使用 worker CUDA 随机数。

Qwen-2511/FLUX 的 DiffSynth 位于 `/opt/tiger/tanyue/samtok_edit/DiffSynth-Studio`，commit `6268a9c808584fc866d2e78d9cbe9afab9e8a5d5`。Qwen-Image-2.1 使用独立 checkout `/opt/tiger/tanyue/DiffSynth-Studio-qwen21`，commit `d2d684ad1f912949eae08453b9411ae40c5ec0ab`，调用方式见[官方示例](https://github.com/modelscope/DiffSynth-Studio/blob/d2d684ad1f912949eae08453b9411ae40c5ec0ab/examples/qwen_image_21/model_inference/Qwen-Image-2.1.py)。

Qwen-Image-2.1 原生输出 RGBA，保存在 `native_rgba/qwen21/<setting>/<index>.png`；白底合成 RGB 后恢复源尺寸，供统一评分。adapter 在 pipeline 返回或异常后清理该次新增的 norm hook，防止官方文本编码器遗留 hook 累积保留中间张量；不改变前向计算。

### 3.3 RePlan

RePlan 以 Qwen2.5-VL planner 生成 bbox、局部 hint 和 global prompt，再由区域注意力 editor 编辑。分别搭配 Qwen-2511 和 FLUX.2，作为两种系统单独报告。

- Planner 权重：`/mnt/bn/strategy-mllm-train/user/tanyue/models/posttrain_models/replan_qwen2_5_vl_7b`；`TainU/RePlan-Qwen2.5-VL-7B` revision `518f82339520058d043c4fbc270481876d8463e4`。
- 方法代码：`/opt/tiger/tanyue/RePlan`，上游 commit `6c9b12f0c619cc8ca6f50b536b24aff377525f8c`。
- Planner 接收与基模相同的图片和 prompt；editor 只接收干净原图与规划结果，不接收 locator、GT 框或参考图。
- 兼容补丁位于 `evaluation/replan/replan_pipeline_compat.patch`，支持有序双图 planner 输入、SDPA、坏 bbox 单项跳过、generator 透传。坏框不会被替换成 GT 框。
- 应用补丁后的 `replan/pipelines/replan.py` SHA-256 为 `3fa5d0e0d03001b8b01cb520c120a6a49011bd644843682b657cf95e802dacc0`，runner 在推理前核验。

| 参数 | RePlan + Qwen | RePlan + FLUX |
| --- | --- | --- |
| seed / dtype | 0 / BF16 | 0 / BF16 |
| steps | 40 | 4 |
| guidance | true CFG=4，guidance=1 | guidance=4 |
| bbox expansion | 0 | 0.15 |
| attention switch ratio | 0.5 | 0.05 |
| 原生输出尺寸 | 约 1024²、32 对齐 | source 尺寸 |

这是端到端系统对比；基模与 RePlan 使用的推理实现和部分原生尺寸路径不同，不能把所有差异单独归因于 planner。

## 4. 评分方法

### 4.1 两张图，一次调用

每个 case × 系统 × 设置调用 Qwen3.8-27B 一次，所有目标共同评分。输入只有：

1. BEFORE：原图，绘制真实 region mask 的外轮廓。
2. AFTER：编辑结果，在相同原始位置绘制相同轮廓。
3. 编辑指令、region 指令、颜色/R1/R2 对应关系与固定评分标准。

轮廓不填充目标内部；细黑描边提高可读性。图片先按比例缩小到最多 1,048,576 像素再描边。没有 crop、第三张定位图、参考答案、坐标、模型名称或预期分数。轮廓保留不代表被删除对象仍然存在；mask 也不授权任意修改轮廓内的属性。

完整英文 prompt 和渲染代码为 [evaluation/metrics/simple.py](evaluation/metrics/simple.py)。模型每维给 1–2 句图像证据和一个 0–4 整数；无法判断返回 null 和理由。

### 4.2 评分标准

| 分数 | 编辑完成度 E | 内容保持度 P | 视觉质量 Q |
| --- | --- | --- | --- |
| 4 | 所有目标、操作、明确属性均完成 | 未要求改变的内容保持，允许合理修补融合 | 无明显新增缺陷 |
| 3 | 主要操作全部完成，只有轻微要求细节偏差 | 轻微色调、纹理或边缘变化，无明确额外对象/属性变化 | 轻微局部瑕疵 |
| 2 | 只完成部分主要操作，或属性/数量/范围明显错误 | 明确局部误改，如衬衫被额外改色 | 明显接缝、光晕、涂抹或结构缺陷 |
| 1 | 正确目标有相关变化，但没有实现主要操作 | 多对象、身份、布局或背景大范围误改 | 严重或广泛缺陷 |
| 0 | 未改、只改错实例、无相关进展或结果相反 | 场景大部分被替换或破坏 | 图像不可用 |

新增须核对对象数量；原对象换色/转身不算删除；保留原对象并在旁边增加新对象不算替换；棕色不能单独证明木材质。未完成任何主要操作时 E≤1，只完成部分主要操作时 E≤2。

附带误改扣 P，渲染缺陷扣 Q；只有它们也破坏了要求的结果时才同时影响 E。允许删除后补全背景或调整持物手势；不扣原图本来已有的模糊、画风或缺陷。

| 示例 | E | P | Q |
| --- | ---: | ---: | ---: |
| 要求编辑但输出原图 | 0 | 4 | 4 |
| 两个对象只干净删除一个，其他内容未变 | 2 | 4 | 4 |
| 血迹去掉，但白衬衫被改成蓝色，无渲染缺陷 | 4 | 2 | 4 |

主报告分别展示 E/P/Q 的均值和分布，不构造加权总分。辅助统计为 E=4 的比例、E=4 且 P/Q≥3 的比例。缺少编辑输出记为交付失败；judge 错误、标注冲突、无法判断单列 unknown，不偷偷计为模型失败。0321 已知存在文字与标注冲突，全设置隔离复核。

### 4.3 固定运行设置与可靠性

权重：`/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/Qwen3.8-27B`。

- 官方本地 processor/chat template，vLLM 多图接口。
- BF16、TP=1、每卡一个副本；thinking 开启、reasoning effort=low。
- temperature=0、top_p=1、seed=0，最多 4096 输出 token、16384 上下文；图片 min_pixels=65536、max_pixels=1048576。
- 正式只跑 `pair_v2`；`pair_v2_r1` 使用同一规则独立重跑，供稳定性检查，不参与投票。
- 仅格式错误/截断时最多一次格式重试，不要求模型改分；保存全部原始尝试。
- 保存清单与图片/mask SHA、源码快照、模型配置与权重文件身份、包版本、prompt、回答和 token 数。权重文件身份由大小/mtime 描述，不冒充全权重 SHA 校验。
- GPU 调度只检查足够的空闲显存，不检查利用率，不停止其他进程。

按 case 重采样计算置信区间，保留同一个 case 四设置的相关性。分输入设置、编辑类型、单/双目标汇总。置信区间不能覆盖 judge 的系统误判；开发样例的重复一致也不等于人工准确率。真实调试和已知误判见实验记录。

## 5. 使用方法

### 5.1 环境与目录

```bash
cd /opt/tiger/tanyue/samtok_edit_benchmark
BASELINE_PY=/opt/tiger/tanyue/samtok_edit_eval_stage2/.venv/bin/python
REPLAN_PY=/opt/tiger/tanyue/RePlan/.venv/bin/python
QWEN21_PY=/opt/tiger/tanyue/DiffSynth-Studio-qwen21/.venv/bin/python
JUDGE_PY=/opt/tiger/tanyue/sam3-crispedit/.venv-scaleedit-vllm/bin/python
BENCH_RUNS=/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit
```

Qwen-2.1 环境通过 `.pth` 复用 baseline 的基础依赖，在独立环境覆盖 transformers 5.17.0、tokenizers 0.23.2；torch=2.8.0+cu128。迁移机器时须同时重建基础环境或重新安装依赖。其本地缓存 `/opt/tiger/tanyue/.cache/benchmark_models/Qwen-Image-2.1` 的 `cache_provenance.json` 保存源路径、revision 和逐文件 SHA-256。

数据根目录为 `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark`，权重和大型输出无需复制进 Git 仓库。

### 5.2 输入准备与预检

```bash
"$BASELINE_PY" evaluation/prepare_inputs.py --resume
"$BASELINE_PY" evaluation/run_inference.py --model qwen --dry_run
"$BASELINE_PY" evaluation/run_inference.py --model flux2 --dry_run
"$QWEN21_PY" evaluation/run_inference.py --model qwen21 \
  --diffsynth_repo /opt/tiger/tanyue/DiffSynth-Studio-qwen21 --dry_run
"$REPLAN_PY" evaluation/replan/runner.py --model qwen2511 --dry-run
"$REPLAN_PY" evaluation/replan/runner.py --model flux2_klein4b --dry-run
```

数据已物化时无需重建。运行目录有固定配置，断点继续必须匹配输入、模型、参数；不要覆盖冻结文件来绕过检查。

### 5.3 RePlan 出图

本机已应用兼容补丁。另建干净 RePlan checkout 时可用 `git apply /opt/tiger/tanyue/samtok_edit_benchmark/evaluation/replan/replan_pipeline_compat.patch`，在方法仓库中执行并核对前述源码 SHA。

```bash
tmux new-session -d -s benchmark_replan -c /opt/tiger/tanyue/samtok_edit_benchmark \
  'bash evaluation/replan/launch_8gpu.sh'
"$REPLAN_PY" evaluation/replan/validate_outputs.py
```

已有 5,248 张验证通过的 RePlan 输出可直接复用。需要生成时，先完成此阶段，再运行占用相同 GPU 的基模与 judge 阶段。

### 5.4 基模出图与统一评分

下列控制器依次运行 Qwen-Image-2.1、Qwen-2511、FLUX，逐模型验证，再冻结三个基模和两种 RePlan 的 13,120 条评分任务，启动 8 卡 judge，生成图表并更新 `MODEL_RESULTS.md`。启动前应已完成 RePlan 出图。

```bash
tmux new-session -d -s benchmark_full -c /opt/tiger/tanyue/samtok_edit_benchmark \
  'QWEN21_MODEL=/opt/tiger/tanyue/.cache/benchmark_models/Qwen-Image-2.1 bash evaluation/run_qwen21_and_judge.sh'
```

正在运行的同一任务不应重复启动。控制器支持完成项复用，源码快照和结果配置保存在实验目录；不会停止既有占卡进程。Qwen-2.1 使用本地缓存时需要该缓存已完整生成，也可不设置 `QWEN21_MODEL` 以直接读取权重根目录。

只运行出图阶段：

```bash
bash evaluation/launch_qwen21.sh "$BENCH_RUNS/qwen21_656"
bash evaluation/launch_baseline_inference.sh
```

这些长任务同样应放到 tmux 中。编辑完成后，可单独运行评分：

```bash
JUDGE_RUN="$BENCH_RUNS/metrics_qwen38_all_models_pair_v2"
"$JUDGE_PY" -m evaluation.metrics.prepare --require-complete --output "$JUDGE_RUN/pilot.jsonl"
tmux new-session -d -s benchmark_judge -c /opt/tiger/tanyue/samtok_edit_benchmark \
  "bash evaluation/metrics/launch_pilot.sh $JUDGE_RUN --split all"

# Judge 完成后生成汇总、代表性 setting case study，并发布到文档
"$QWEN21_PY" -m evaluation.metrics.compare \
  --run "$JUDGE_RUN/all" --output "$JUDGE_RUN/comparison"
"$QWEN21_PY" evaluation/render_setting_case_study.py \
  528 345 181 488 586 608 632 635 \
  --judge-root "$JUDGE_RUN" \
  --prepared-manifest "$BENCH_RUNS/referential_finegrained_edit_benchmark_656_two_image_locator/prepared/benchmark_baseline_eval_inputs.jsonl" \
  --output "$JUDGE_RUN/comparison/setting_case_study"
"$QWEN21_PY" -m evaluation.metrics.publish_results \
  --comparison "$JUDGE_RUN/comparison" --repo "$PWD"
```

### 5.5 查看进度与产物

```bash
watch -n 30 '/opt/tiger/tanyue/RePlan/.venv/bin/python /opt/tiger/tanyue/samtok_edit_benchmark/evaluation/report_full_progress.py'
# Qwen-2511 / FLUX 的完成数量与 tqdm
tail -f "$BENCH_RUNS/referential_finegrained_edit_benchmark_656_two_image_locator/logs/baseline_progress.log"
tail -f "$BENCH_RUNS/referential_finegrained_edit_benchmark_656_two_image_locator/logs/baseline_inference.log"
# Qwen-2.1
tail -f "$BENCH_RUNS/qwen21_656/logs/generation.log"
# Judge 调度与分片映射
tail -F "$BENCH_RUNS/metrics_qwen38_all_models_pair_v2/logs/controller.log"
# 具体 rankN.gpuM.log 以 controller.log 为准
```

| 产物 | 实验根目录下的位置 |
| --- | --- |
| Qwen-2511 / FLUX 输出 | `referential_finegrained_edit_benchmark_656_two_image_locator/inference/{qwen,flux2}/<setting>/` |
| Qwen-2.1 输出 | `qwen21_656/inference/qwen21/<setting>/` |
| RePlan 输出 | `replan_656/inference/{qwen2511,flux2_klein4b}/<setting>/` |
| Judge 原始记录 | `metrics_qwen38_all_models_pair_v2/all/records/` |
| Judge 覆盖报告 | `metrics_qwen38_all_models_pair_v2/all/report/` |
| 对比图、统计与案例页 | `metrics_qwen38_all_models_pair_v2/comparison/` |

每张输出一个 PNG 和 JSON sidecar；每模型保留 `run_config.json` 与验证报告。RePlan sidecar 还保存原始 planner 回复、预测 bbox 和 editor 输入。评分全部完成并通过完整性检查后，数值与案例图写入 [MODEL_RESULTS.md](MODEL_RESULTS.md)。

### 5.6 检查与图库

```bash
"$REPLAN_PY" -m pytest -q
"$BASELINE_PY" evaluation/validate_baseline_outputs.py
"$QWEN21_PY" evaluation/validate_baseline_outputs.py --models qwen21 \
  --experiment_root "$BENCH_RUNS/qwen21_656"
"$REPLAN_PY" evaluation/replan/audit_planner.py
"$QWEN21_PY" evaluation/render_setting_case_study.py \
  528 345 181 488 586 608 632 635
```

结构验证确认产物和输入来源；模型是否完成要求由图像检查与三个评分轴分别衡量。
