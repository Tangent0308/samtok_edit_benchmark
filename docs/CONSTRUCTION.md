# 源数据与构建方法

## 1. 两个冻结输入 release

v1 从两个已经完成筛选的 release 物化资产，而不是把源数据原有的编辑文字直接当成新增任务：

```text
# 旧 656 条中的 hard/relevant 子集（150 条）
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/PACO_benchmark_candidates/
  original_656_hard_relevant_v1/benchmark/benchmark.jsonl

# 外部新增集（300 条）
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/PACO_benchmark_candidates/
  goal_1k/benchmark_goal1k_v1_300/benchmark.jsonl
```

`data/v1/provenance.jsonl` 的 450 条记录保存原 ID、原 release、原图/mask 路径、哈希、逐例筛选理由与审阅证据。`asset_manifest.jsonl` 保存全部 1,413 个资产的原始路径、当前相对路径、尺寸、SHA256。旧指令及 300 条最终修订对应关系在 `instruction_revisions.jsonl`。

源数据提供**原图与对象/部件分割**；benchmark 另行定义**在该原始区域上做什么编辑**。例如 PACO 的 tray 类别或部件标签不能授权编辑桌上所有托盘；若 mask 覆盖前景托盘的可见内表面，就只能为该内表面设计编辑。

## 2. 实际源数据

### 2.1 旧集来源：150 条

| 来源 | 数量 | 已冻结源版本 | 原始项目路径 |
|---|---:|---|---|
| [CompBench](https://huggingface.co/datasets/BohanJia/CompBench) | 114 | `a4c5a4d1854056d24aad43a494772dc90588d426` | `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/CompBench/` |
| [HumanEdit](https://huggingface.co/datasets/BryanW/HumanEdit) | 1 | `dbc60b9ba3c17adf59e1effd8a9d92bdf2f14041` | `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/HumanEdit/` |
| [MIRAGE](https://huggingface.co/datasets/ziqiangoodgood/MIRAGE) | 35 | `11eff1e3f396e189e61bd1f0ca596286d8a0b183` | `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/MIRAGE/benchmark/` |

这部分从旧冻结 benchmark 复制，原根目录为 `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark/`。CompBench ID 中的 `train-...` 是上游发布 parquet 的名字，不能将其解释为这张图已用于 SAMTokEdit 训练。新增数据“不从训练数据取样”的要求针对本次新增 300 条；此处没有重新替换用户要求保留的 150 条。

### 2.2 外部来源：300 条

没有从 `/datasets/SAMTok_Training_Data/` 抽取新增图片。使用本地官方 held-out 图像/视频帧及发布的可见区域标注：

| 来源 | 数量 | 采用的 split 与标注 | 本地原图/标注入口 |
|---|---:|---|---|
| PACO/LVIS | 153 | COCO `val2017` 原图；PACO 对象/部件可见分割 | `/mnt/bn/strategy-mllm-train/intern/common_datasets/coco/val2017/`；解码后的选中 mask 在 `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/PACO_benchmark_candidates/selection_v2/masks/`，完整路径见逐例 provenance |
| BURST | 58 | BURST val/test 可见实例；只取已核实原始视频 held-out ID 的候选 | `/mnt/bn/strategy-mllm-train/intern/common_datasets/TAO-Amodel/` 的帧与 `BURST_annotations/`；来源含 Charades/LaSOT/HACS，不能仅凭 BURST split 推断原视频 held-out |
| ADE20K-Part | 43 | `ADE20KPart234/images/validation`；所选对象的部件标注 | `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/PACO_benchmark_candidates/goal_1k/ade20k_part234/official/ADE20KPart234/` |
| MeViS | 26 | `valid_u` 目标对应视频帧和可见 mask | `/mnt/bn/strategy-mllm-train/intern/common_datasets/MeViS/valid_u/` |
| SA-V | 14 | 官方 `sav_val`/`sav_test` 帧和 masklet | `/mnt/bn/strategy-mllm-train/intern/common_datasets/SAM2-Data/` |
| MOSEv2 | 6 | `valid` 视频第一标注帧与实例 mask | `/mnt/bn/strategy-mllm-train/intern/common_datasets/MOSEv2/valid/` |

以上路径用于追溯。实际运行只依赖 v1 已复制的 `assets/`，不依赖这些原始目录。

split/训练重叠审计的实际范围：

- SA-V 检查 99,018 份 manual/auto train 元数据，得到 50,583 个 train video ID；官方 val/test ID 与它们无交集。ADE 本地已知 SAMTok 会话首图的 20,196 个 ADE 路径均来自 training；选中的 part 图来自 validation。BURST 检查原视频 Charades/LaSOT/HACS 的官方 split，原 split 未确定或为 train 的候选不进入相应 held-out 队列。
- 缓存项目编辑训练集覆盖 175,101 张图。933 张候选的字节/像素/pHash 审计没有发现精确命中；两个感知命中经图像复核被判为假匹配。release 级 admission 记录认为新增 300 条已通过该覆盖范围内的重叠检查。
- 逐例源 audit 有些 `provenance_status` / `training_overlap_status` 仍保留早期 `pending` 字样，仓库保留原值；不能把 `admitted=true` 当成所有来源别名、裁剪图、邻近视频帧和整个 tokenizer/基模预训练都已清除的证明。MeViS/MOSE 的原视频别名等范围仍不能完整重建。
- SA-V/ADE 的公开训练配置或已知会话文件并不等于 SAMTok 实际所有训练图的完整清单。没有对未知基模预训练作无重叠承诺。

具体证据在 `data/v1/audits/`：`project_training_overlap.json`、`sav_split.json`、`burst_origin_splits.json`、`ade_training_names.json` 及各图像重叠报告。构建和评分代码不读取训练集；这些训练路径仅用于排除和审计。

源图、标注和模型权重遵循各自上游条款；本仓库不会为它们赋予统一的再分发许可。发布全量图像前应由数据维护者核实源数据条款；当前 Git 仅携带元数据与少量样例。

## 3. 旧 656 条的过滤

原冻结 656 manifest SHA256：`280f3c5050cce156173dff31f841328f51b373c83eaf6190b3c1ce3409276022`。过滤的全量决定保存在 `data/v1/selection/v0_filter_decisions.jsonl`，摘要在 `v0_filter_summary.json`。

使用已存在、固定 seed 的五系统结果：Qwen-2511、FLUX、Qwen-2.1、RePlan+Qwen、RePlan+FLUX；每系统四种输入，共 20 个判定/旧 case。strict-success 定义与三维 judge 一致。结果先用于排优先队列，再结合原图/mask 判断场景是否适配；不是只按模型低分机械收集所有困难图。

| 入选队列 | 保留数 | 含义 |
|---|---:|---|
| confirmed common failure seed | 13 | 既有公共失败分析确认的候选 |
| text-hard | 64 | 五个 text-only 严格成功数为 0 或 1 的候选 |
| low-success | 20 | 跨设置整体成功数低的队列；入选行总成功数 2–4/20 |
| supplement / remaining review | 53 | text-only 严格成功数为 2 的补充候选 |

共对 243 个优先候选直接检查源图与 mask 叠加，保留 150。过滤门槛：

1. 排除原 eval index 321、511 两条已知标注冲突。
2. 单条最大目标 region 面积占源图小于 8%。
3. 至少有一个定位/范围难点：多 region、MIRAGE 局部编辑、局部 replace/mixed，或目标面积小于 2.5%。
4. 视觉上指代能解析，mask 与所编辑实例/部件对应；难度确实涉及实例选择、小部件、遮挡或邻接范围。
5. 排除 MIRAGE 中主要依靠材质、纹理、羽毛/毛发、反光、屏幕内容等操作内容来增加难度、而区域选择不突出的任务。

最终为 CompBench 114、HumanEdit 1、MIRAGE 35；单 region 87、双 region 63；add/remove/replace/mixed 为 67/48/24/11。其余 504 条是未达到当前严格准入或暂存，另 2 条标注冲突；不能把它们全部描述为“简单”。筛选分数只说明已观察到的固定 seed 结果，不能当成模型的多次采样成功概率。

## 4. 新增 300 条的筛选

目标是收集源图与区域结构，编辑指令是后续另行编写的任务。处理过程：

1. 从本地可用 held-out 标注中抽取候选可见对象/部件；通过图像/mask 解码、相同尺寸、非空二值区域等基础检查。
2. 检查来源 split、已知训练重叠与视频原始来源；对同图、同视频/同场景分组去重，避免大量邻近帧重复计数。
3. 对原图、mask 叠加图、带上下文的局部放大图逐例复核：应有可解释的实例混淆、细粒度部件、断开/细长/有孔区域、遮挡、邻接保护等机制。目标必须可见且可辨认。无可见证据、错误 mask、仅类别简单定位、标注边界冲突的候选拒绝或暂存。
4. 用启发式难度分数排列复核顺序。其组成是机制线索、区域面积/断片/孔洞/轮廓复杂度/bbox 稀疏度、具体审阅证据、来源审计和第二轮 AI 复核；它不是模型分数。公式保存在 `src/samtok_benchmark/selection.py`，需要可选 `construction` 依赖。最终保留行的记录分数为 38–65，**没有全体 ≥45 的统一准入门槛**。
5. 初次 300 shortlist 因 80 条来源 split 未确认被缩减到 220；从剩余合适候选补充 80 条，形成当前 300。补充来源为 PACO 32、BURST 20、ADE 12、MeViS 13、SA-V 3。逐例理由、source group、审阅记录与 admission evidence 均保留。

最终 300 来自 300 张唯一源图和 300 个记录中的 source group。对跨来源同场景曝光的识别仍受已有审计范围限制。历史 30-case Qwen-2.1/FLUX pilot 是诊断性开发实验，原记录明确不用于逐条准入；它用的是旧指令，不能作为修订后 300 条的失败证明。扩充记录中另有 18 个 PACO ID 原先被标作 development 候选；该历史标签保留，不能宣称全部图片从未参与过任何开发审阅。

## 5. Mask、box 与 point 来源

v1 不根据编辑模型输出重新分割，不训练或调用 SAMTok 去生成目标 mask，不手工改变 region 像素。物化后全部 513 个 region 与输入 release 的文件哈希一致。

| 来源 | mask 如何得到 |
|---|---|
| CompBench | 沿用发布的二值编辑区域；旧构建阶段多目标 union 的连通分量/语义分区继承自 v0，v1 不重新处理 |
| HumanEdit | v0 从上游 `MASK_IMG` 人工笔刷 alpha 提取（`alpha < 128`）；不做 SAM 精修 |
| MIRAGE | v0 将选中发布 polygon 用 PIL `ImageDraw.polygon(..., outline=1, fill=1)` 栅格化；不是重画新边界 |
| PACO/LVIS | 选中发布对象/部件的 segmentation 解码为二值图 |
| ADE20K-Part | 选中官方对象部件标注 ID 的二值区域 |
| BURST / MeViS / SA-V / MOSEv2 | 对应帧的发布可见实例/masklet 解码或提取；不用 amodal 不可见补全区域 |

所保留的 CompBench `cb_train-00006-of-00007_0351` 是一条明确例外：上游发布的是连通双鸟 union，v0 曾用 Grounding DINO + SAM2 在 union 内分成两个 region。两个子区域不重叠、union 与发布 mask 逐像素一致；单独子区域是派生分区，不能称为上游直接发布的实例 mask。固定版本分别为 `IDEA-Research/grounding-dino-tiny@a2bb814dd30d776dcf7e30523b00659f4f141c71` 和 `facebook/sam2.1-hiera-small@e07df6aa19f5c6545121551bf89957b7663ee715`。v1 直接继承已复核分区，不再调用这些模型。

box、point 也继承输入 release，不重估。旧 v0 的 box 为紧致框向外扩张短边 2%，point 为 mask 内到边界距离最大处；外部 source release 的实际数值以冻结记录为准。v1 校验检查框包含 mask、点在 mask 内。

`evaluation_mask` 是历史辅助评价范围，旧 v0 构造为 region union 向外膨胀短边 2%；外部 release 的文件直接继承。它不是编辑目标标注。当前 VLM judge 使用原始 region 轮廓定位，保留性按指令授权判断，完全不读取 evaluation mask；模型输入与审阅 UI 也不读取/展示它。

## 6. 指令编写

新增数据的编辑目标必须就是原始 mask 覆盖的实例/部件。对全部 300 条逐条看干净原图、原始 mask 叠加、上下文放大图，并对 5 条有疑义的图额外看干净放大图。没有从 source 类别名机械拼接整物体替换模板。

风格参考 SAMTokEdit 的实际训练记录：

```text
/opt/tiger/tanyue/samtok_edit/docs/04_SAMTokEdit_Qwen21_训练数据盘点.md
/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/
  qwen21_full4_20260928/data/sources.jsonl
```

参考任务类型包括 attribute、remove、replace、add、action、text、composite；实际 v1 只使用符合每张图的类型，不为了比例强制塞入动作/文字任务。编写要求：

- 简短英文祈使句：明确对象/部件 + 必要实例定位 + 一项具体编辑。
- mask 是杯柄就写杯柄；mask 是手机侧壳就写侧壳；不能扩成整杯或整手机。
- 近邻、桌面、手等仅作消歧描述，不同时要求编辑它们。无需重复罗列所有应保持的对象。
- 属性修改选择合理颜色、材质或表面细节；整对象才考虑合理移除/替换。新增 5 条 add 是轮胎白边/皮肤雀斑等 mask 覆盖表面的细节，不在 mask 外新增对象。
- 清晰指代优先于固定长度；避免只有“this object”“marked region”的模板。指令描述需与静态帧一致，不能沿用视频运动描述。

修订例子：

| case index | 目标 | 当前指令 |
|---|---|---|
| 150 | 前景托盘露出的内表面 | Change the exposed inner surface of the foreground doughnut tray to dark blue. |
| 170 | 右侧台灯支撑管 | Change the support tubes of the desk lamp to the right of the monitors to turquoise. |
| 178 | 台球桌可见袋口配件 | Change the billiard table's visible pocket fittings to tan leather. |
| 362 | 最右手机左/下窄侧壳 | Change the narrow side casing along the rightmost phone's left and bottom edges to red. |

前 150 条旧任务保留原指令；旧 add 的 mask 可以是放置区域，而新增表面 add 指向被标对象表面，二者不能混淆。所有自然语言任务没有编辑后 GT；source segmentation 不能作为编辑后参考答案。

## 7. 人工审核与发布状态

已有复核是 AI 视觉复核；“independent” 指第二轮 AI 检查，不能写成真人双盲标注。没有收到实际人工审核结果，因此当前发布为待独立人工批准的 450-case 挑战集。

数据人工审核应对 **全部 450 条** 执行以下逐例检查：原图可用、mask 正确且含全部目标可见区域、指令唯一指向 mask 对象/部件、编辑自然合理、无额外未标对象操作、场景满足细粒度需求、来源/重复问题有记录。检查失败应丢弃或明确修正并重新审批；不能因为自己的方法表现好而接受错误标注。建议疑义和修改条目由第二位审核者复核，保留 reviewer、时间、理由和指令版本。

运行 `samtok-benchmark review` 生成本地工具，记录通过/丢弃、备注、指令修改；`export-reviewed --reviewer ...` 生成通过子集及审核 sidecar。未审核和丢弃行不进入该导出。修改指令会清除当前通过状态，重新通过后导出独立 revision，并要求重新准备模型输入和评测；冻结 release 不覆盖。工具不自动推断指令变更后的操作类型；若修改 add/remove 等主操作，维护者还需在新版本中明确更新 `edit_type` 与审计。不要将数据准入的“通过”当成某编辑模型的成功评分。

## 8. 可复现范围

确定性可复现：已选择 450 条的身份、顺序、指令、资产文件和哈希、区域几何、输入渲染和评测协议。

人工/视觉判断不由一个分数完全决定。保留逐例证据与决定可以审计当时为何取舍，但运行启发式排序不能自动复现主观准入。`build` 按冻结 release 复制并校验，避免在他人重建时改变 case 或替换 mask。

```bash
# 用现有 v1 资产物化新目录
samtok-benchmark build --assets-root /path/to/v1 --output local_data/v1
# 或在具有原始资产的项目机器上，按记录的 original_path 物化
samtok-benchmark build --output local_data/v1_from_original
```

当前规范 manifest 与正式目录原始指令导出逐条保持 ID、源图、regions、evaluation mask、instruction、edit_type 一致。规范化只统一字段名称、移除过期目标描述，并为未改动的 150 条补充 `v0_preserved` 指令版本。
