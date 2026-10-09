# v1 数据集说明

## 1. 评测目标与当前状态

评测细粒度、指代明确的局部图像编辑：在同类多实例、遮挡、紧邻其他对象、细杆/窄边/孔洞、断开的可见区域和对象部件等场景下，模型能否选对实例与部件，完成修改，并保持未获指令授权的内容。

这些场景对应 SAMTokEdit 希望利用精确区域表示解决的实例绑定与局部边界问题。难点应来自选目标、部件范围和邻近内容保护，不能仅靠不自然的编辑内容制造困难。v1 是针对这些能力构建的挑战集；不是对自然场景分布的随机抽样。旧集的 150 条利用既有基线失败筛选，因此必须披露选集偏差；不能据此预先宣称 SAMTokEdit 已成功，也不能宣称所有基线在每条新增数据上都失败。

| 项目 | 当前状态 |
|---|---|
| case 汇总与资产校验 | 450 条，已冻结并通过校验 |
| 全量指令 | 450 条逐例对照原图/原始 mask 编写或复核，当前 release `mask_grounded_single_ops_v4` |
| 本次移除混合任务 | 47 条逐例比较两块 mask，保留更难的一块并改写指令；其余 403 条不变 |
| 已有视觉复核 | AI 逐例检查，非人工标注 |
| 独立人工准入审核 | 未提供实际审核结果；通过工具逐条记录后才能声明完成 |
| 当前指令下的 Qwen-Image-2.1 纯文本推理 | 450/450 完成；AI 逐图复核为 good 202、bad 232、uncertain 16，见 [当前结果](V1_REPORT.md) |
| 后续扩充 | 新测 433，完整审核池 883；建议困难候选 504，尚未替换正式 450 |
| 评分依据 | 上述是 AI 直接视觉分类，非全量自动 VLM 数值分或独立人工金标准 |

截至 2026-10-09，正式版本、候选扩充和模型结果的统一介绍见 [v1 报告](V1_REPORT.md)。本页以下统计描述正式 450 条；审核池和困难子集不可混用。

## 2. 统计

统计以仓库唯一当前 manifest [`data/v1/cases.jsonl`](../data/v1/cases.jsonl) 为准，完整机器可读统计在 [`statistics.json`](../data/v1/statistics.json)。

| 统计项 | 数量 |
|---|---:|
| 总 case / 唯一 ID / 唯一源图内容 SHA256 | 450 / 450 / 450 |
| A 类 v0 过滤 / B 类 SAMTok 相关源数据新增 | 150 / 300 |
| 当前保留的原始 region mask | 466 |
| 单 region / 双 region case | 434 / 16 |
| 属性修改 / 添加 / 移除 / 替换 | 112 / 113 / 112 / 113 |
| mixed / composite | 0 / 0 |
| 资产清单 | 1,366：450 原图 + 466 region mask + 450 历史 evaluation mask |

来源按两大类组织；B 类指数据源层级关联，实际取自验证/测试等 held-out 划分，不从训练样本取图。正式 v1 为 A 150 + B 300；完整审核池为 A 150 + B 733（包含后续 433），详细批次见 [v1 报告](V1_REPORT.md)。

### A 类：v0 过滤保留（150 条）

| 下属数据源 | 数量 |
|---|---:|
| CompBench | 114 |
| HumanEdit | 1 |
| MIRAGE | 35 |

### B 类：SAMTok 相关源数据新增选取（正式 v1 中 300 条）

| 下属数据源 | 数量 |
|---|---:|
| PACO/LVIS | 153 |
| BURST | 58 |
| ADE20K-Part | 43 |
| MeViS-valid_u | 26 |
| SA-V | 14 |
| MOSEv2 | 6 |

### 两类合并后的任务与区域统计

本版只允许 add/remove/replace/attribute 四种单项类型，数量为 113/112/113/112。原有 47 条 Mixed（CompBench 18、MIRAGE 29）逐条比较两块原始 mask 的实例歧义、遮挡邻接、目标大小、部件范围和边界难度，保留一块并改写为单项编辑；27 条保留原 R1、20 条保留原 R2。具体理由与前后区域映射见 [`instruction_revisions_single_ops_v4.jsonl`](../data/v1/instruction_revisions_single_ops_v4.jsonl)。这属于 AI 视觉难度判断，没有用本轮模型结果证明逐块难度。

434 条为单 region；剩余 16 条双 region 为 add 11、attribute 5，每条只执行同一种操作，因此不属于混合编辑。外部新增 300 条未改动，仍为 add 35、remove 75、replace 95、attribute 95。全量指令 5–26 个词，平均 13.50 个词，均句首大写。无指令历史 catalog 和历史 audit 中的 mixed 仅是追溯记录，不是当前任务。

## 3. 路径与获取

项目机器上的正式资产目录：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v1/
```

| 路径 | 用途 |
|---|---|
| 本仓库 `data/v1/cases.jsonl` | 当前规范任务 manifest；所有评测命令默认读取它 |
| 正式目录 `assets/` | 可独立使用的原图和 mask；路径与仓库 manifest 一致 |
| 正式目录 `benchmark/benchmark.jsonl` | 历史无指令 catalog，只用于身份/几何追溯 |
| 正式目录 `benchmark/benchmark_with_instructions.jsonl` | 当前规范 manifest 的副本；与仓库逐字节一致 |
| 正式目录 `benchmark/instruction_review_evidence/` | `mask_grounded_single_ops_v4/` 含本轮 47 条的 8 张双 mask 比较拼图、选择理由与指令表；v3 子目录保留上一轮全量视觉复核。图头仅为历史对照，最终看当前 manifest |
| `/opt/tiger/tanyue/samtok_v1_450_case_review.tar.gz` | 可下载解压、用 Python 3 在本地运行的审阅包，大小以实际压缩包为准 |
| `/opt/tiger/tanyue/samtok_v1_450_case_review/` | 上述包的项目机器展开目录 |

Git 提供元数据、代码和少量可视化样例；目前没有公开托管的全量图像下载地址。项目机器上可直接用正式资产目录，也可将审阅包解压目录作为 `--dataset-root`。其他使用者需要获得该包或按源数据条款取得资产。重建工具可从现有资产根目录复制，或从 `asset_manifest.jsonl` 记录的原始文件物化；跨机器可用 `--source-map OLD_PREFIX=NEW_PREFIX` 转换原始前缀。不会自动下载数据、申请访问权或猜测路径。

```bash
python -m pip install -e .
samtok-benchmark build --assets-root /path/to/extracted/review_package --output local_data/v1
samtok-benchmark validate --dataset-root local_data/v1
```

构建得到 `local_data/v1/assets/` 和 `local_data/v1/benchmark/`。默认 manifest 仍是仓库 `data/v1/cases.jsonl`；脱离仓库运行时显式传 `--manifest /path/to/local_data/v1/benchmark/cases.jsonl` 和对应资产清单。

## 4. 规范 schema

每行是一条 case，所有图像路径相对 `--dataset-root`，没有编辑后参考答案图：

```json
{
  "id": "v1-goal1k_v1_300-0000-goal1k-paco_lvis_v1_35682_1738683",
  "original_id": "goal1k-paco_lvis_v1_35682_1738683",
  "source_release": "goal1k_v1_300",
  "source_dataset": "goal1k/PACO-LVIS",
  "source_image": "assets/goal1k_v1_300/0000/source.jpg",
  "regions": [
    {
      "mask": "assets/goal1k_v1_300/0000/region_1.png",
      "box": [
        7,
        418,
        479,
        632
      ],
      "point": [
        453,
        547
      ]
    }
  ],
  "evaluation_mask": "assets/goal1k_v1_300/0000/evaluation_mask.png",
  "difficulty": {
    "same_class_multi_instance": true,
    "multi_object_scene": true
  },
  "instruction": "Add a thin gold border to the exposed inner surface of the foreground doughnut tray.",
  "edit_type": "add",
  "instruction_source": "AI_individual_source_and_original_region_mask_review_balanced",
  "schema_version": "1.0",
  "instruction_revision": "mask_grounded_balanced_v3",
  "region_instruction": "Add a thin gold border to the exposed inner surface of the foreground doughnut tray."
}
```

上例为真实第 150 条 case（index 从 0 开始）。字段定义：

| 字段 | 含义 |
|---|---|
| `id` | v1 唯一身份，含来源 release、原 release 行号和原 ID |
| `original_id`, `source_release` | 回溯两份输入 release，不依赖评测过程重新编号 |
| `instruction` | 清楚指明实例/部件的最终英文编辑任务 |
| `region_instruction` | 同一任务的区域绑定版本；双 region 的 16 条明确对应 `{region_1}`/`{region_2}`，单 region 与 instruction 相同 |
| `regions` | 原始输入区域；数组顺序对应 R1 红色、R2 绿色 |
| `box` | 半开像素坐标 `[x1,y1,x2,y2)`；继承 source release 的几何 |
| `point` | mask 内的像素坐标 `[x,y]`，继承 source release |
| `difficulty` | 来源保留的场景标签；不替代逐例难度证据，详见 provenance |
| `evaluation_mask` | 兼容追溯所保留的历史辅助区域；当前模型、VLM judge 和页面均不使用它 |
| `instruction_revision` | 本轮 47 条为 `mask_grounded_single_ops_v4`，未改动 403 条保留 `mask_grounded_balanced_v3`；人工修改另建导出版本 |

`regions[*].mask` 才是目标区域依据。47 条中的未选区域不再输入模型、judge 或页面；它对应的对象属于应保护内容。保留原 R2 时，它在当前数组中成为唯一 R1，文件名仍可为 `region_2.png`，避免复制或修改原像素。对象轮廓、遮挡空洞和多个断开的可见片段均可能属于同一个目标。不能把 mask 的 bbox 当成目标，也不能把整对象类别标签当成部件指令。

完整 JSON Schema 见 [`data/schema.json`](../data/schema.json)。运行时还会检查二值/非空 mask、尺寸、box 包含 mask、point 在 mask 内、evaluation mask 包含 region union，以及全部资产 SHA256。

## 5. 可视化与人工筛选

![四类单项操作与同类型双区域示例：源图、原始 region 叠加、region mask](assets/v1_examples.jpg)

图中展示托盘新增饰边、遮挡灰鹅移除、手持剪贴板替换、狗鼻改色，以及两个放置区同时新增鸟类的同类型双区域任务。文字只负责明确指代与修改内容；目标范围由原始 region mask 固定。可视化不会展示 evaluation mask。

```bash
samtok-benchmark review --dataset-root /path/to/v1 --output outputs/data_review
python outputs/data_review/run_review.py
```

在浏览器打开 `http://127.0.0.1:8765/index.html`。初始不加载图片，左侧选择后加载当前 case。通过/丢弃、指令修改、备注会保存到 `review_results.json`；按钮可导出结果。`reviewed_cases.json` 是带审核状态的副本，不能与冻结 release 混为一谈。

本地旧审阅包仍可运行。仓库结构调整后的 `review` 命令可重新生成同功能工具；继续已有审核时先备份并复制自己的 `review_results.json`，再启动新包。历史默认指令的自动 override 会失效；用户自定义修改、备注和旧决定保留。本轮 47 条区域/指令变化后旧通过/丢弃计为未审核，需要重新确认；403 条未改变的 case 不会因为 release 名称变化而失去原有指令身份。
