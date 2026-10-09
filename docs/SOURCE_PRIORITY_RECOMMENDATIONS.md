# Benchmark 数据源优先级建议

整理日期：2026-10-06。依据 2026-10-03 至 10-05 已保存的本地数据调查、图像复核、来源审计和 v1 构建记录；本次没有重新下载数据或开展新一轮模型评测。

## 1. 选择目标与结论

目标是用少量高质量 case 考察 SAMTokEdit 所针对的细粒度区域编辑：同类实例选择、对象部件绑定、遮挡后的断开可见区域、细杆/窄边/孔洞，以及紧邻其他对象时的内容保持。目标需要清晰可辨、mask 正确，编辑也必须自然合理；模糊、小到看不清或错误标注不应作为有价值的难度。

用户后续明确要求新增 case 不从训练数据取样。因此，SAMTok 的数据文件在这里主要用于了解标注形式和排查训练重叠；实际新增源应从独立的验证/测试数据中寻找。某数据集出现在 SAMTok 的训练来源列表中，不代表它的所有 split 都已参与训练；反过来，官方 split 名叫 test/val，也不能证明没有其他来源别名或训练曝光。

**PACO/LVIS 是已建立候选池中优先继续深挖的主源。**在 PACO 之外，当时更新后的补充源调查顺序为：

**SA-V 官方 test/val → ADE20K-Part-234 validation → MOSEv2 valid → BURST 原视频来源已核实的 test 子集 → 对应的 val 子集 → EntitySeg held-out → Pascal-Part validation。**

这是一份选图和审查资源的优先级，不是各数据集的自动准入名单，也不是对各来源最终产量的承诺。最终 v1 的实际入选结果见第 5 节。

## 2. 优先级总表

| 层级 | 数据源 | 与目标场景的主要契合点 | 使用条件与建议 |
|---|---|---|---|
| 已有主源，优先继续深挖 | PACO/LVIS，当前使用 COCO val2017 原图 | 有对象/部件标注；托盘内表面、把手、支撑管等部件与遮挡、邻接保护可以同时成立 | 只取标注正确、目标可辨、实例/部件范围有难点的候选；继续核对已知训练 ID、图像与场景重叠 |
| 补充源 1 | SA-V 官方 test/val | 原生对象及局部区域 masklet；手持、遮挡、断片和不规则边界较适配 | 优先清晰且语义明确的局部 mask；官方 train/held-out ID 已核验，但完整 tokenizer 训练清单仍不可重建 |
| 补充源 2 | ADE20K-Part-234 validation | 原生部件层级；家具扶手、抽屉、交错支架等室内细部 | 适合小量精挑；部件 mask 的完整性、孔洞与父实例归属需逐例确认，早期看图产出较低 |
| 补充源 3 | MOSEv2 valid | 多实例拥挤、遮挡、可见区域断开及相似近邻 | 以有正式 GT 的首帧为候选；优先可辨对象，拒绝模糊、小到不可编辑和泛化整对象任务 |
| 补充源 4/5 | BURST test/val 中已核实原视频 held-out 的子集 | 手持小物体、同类干扰、复杂接触和可见轮廓 | 必须检查 HACS/LaSOT/Charades 等底层视频 split；不能直接将整个 BURST test 当成无训练来源数据 |
| 有条件补充 | MeViS valid_u | 同类干扰与遮挡场景，语言能提供实例线索 | 单帧指令必须能解析，不能依赖视频运动；原视频别名与实际训练清单仍有审计范围限制 |
| 后备调查 | EntitySeg held-out | 对象接触与精细边界；缺少原生部件层级 | 当时未取得并检查本地原图；先核实来源 URL、split 与训练身份，再判断实际场景 |
| 后备调查 | Pascal-Part-116 validation | 人体、动物或车辆部件 | 当时未检查本地原图；先关联 VOC 原始 split、SBD 增广训练身份及其他训练池 |
| 暂不优先 | PartImageNet | 有部件层级，但大量场景可能为单对象、较粗部件 | 当时未发现可用本地资产；需先核实原始 ImageNet 图片身份和 split，再看真实难度 |
| 停止投入扩量 | GroundingSuiteEval | 仅剩的无已知 ID 重叠样本较简单 | 2,727 张源图中 2,726 张与已知 SAMTok 训练 ID 重叠，不适合作为新增主源 |

PACO-Ego4D 当时也曾被考虑，但原图访问授权/本地可用性未落实，未进入当前 v1。若以后获得可用原图，应另做标注、来源和场景审计后再评估，不能把 PACO/LVIS 的调查结果直接套用过去。

## 3. 主要来源的实际调查依据

### 3.1 PACO/LVIS：继续精挑已有部件候选

当前使用 COCO val2017 原图及 PACO 发布的对象/部件 segmentation。适配优势在于：可以明确区分整物体和局部部件，并找到一个部件被其他物体遮挡、可见区域分成多片、周边还有相似实例的场景。

优先找托盘露出的内表面、杯柄、台灯支撑管、窄侧壳、家具结构件等目标。类别标签仅作线索，必须对照原图和 mask 确认实际语义；标成某种物体并不意味着 mask 覆盖整个物体。只有一个简单完整轮廓、没有实例或范围难点的图不应仅凭“有 part 标签”就入选。

早期 PACO 复核记录有 186 个确认的视觉候选，按场景分为 156 个 formal 候选和 30 个 development 候选。后续扩充取舍又有变化，当前外部 300 条中 PACO/LVIS 为 153 条，不能将早期候选总量直接当作最终数量。扩充记录还包含原先标为 development 的部分 ID，历史标签保留在审计中。

本地入口：

```text
/mnt/bn/strategy-mllm-train/intern/common_datasets/coco/val2017/
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/PACO_benchmark_candidates/selection_v2/
```

### 3.2 SA-V：局部 mask 适配，但清晰度与目标语义必须过关

SA-V 的优势是对象和局部区域 masklet，可以提供遮挡、细边界、手持接触及断开的可见部分。当时准备了 427 个目标卡，涉及 419 张源图、256 个视频组；这些数字是候选队列规模，不是独立 case 的最终接受数。

优先选择清晰帧，确认 mask 对应的到底是完整对象还是具体部件。备用帧用于替换当前不清晰帧，不能把大量相邻帧重复计为新的困难 case。一个视频/场景组最终应去重选择；不要用模糊、含义不明的局部标注增加数量。

审计曾检查 99,018 份官方 train 元数据，得到 50,583 个独立 train video ID；官方 test 的 150 个与 val 的 155 个 video ID 均与它们无交集。另对 `sam_info.json` 的 11,182,625 项核查发现该文件只索引 SA1B，不能把它当成 SAMTok 所有训练源的完整清单。

因此，早期“因为 SAMTok 文档提到 SAV 就暂时阻塞”的判断后来更新为：官方 held-out 可继续选图，但须保留完整 tokenizer 实际 split 无法独立复原，以及同场景/裁剪别名未全覆盖的限制。

本地入口：

```text
/mnt/bn/strategy-mllm-train/intern/common_datasets/SAM2-Data/sav_test/
/mnt/bn/strategy-mllm-train/intern/common_datasets/SAM2-Data/sav_val/
```

### 3.3 ADE20K-Part：部件语义强，适合小量补充

后来已取得 ADE20K-Part-234 的 1,016 张 validation 原图和部件标注，并准备了 1,000 个候选目标，涉及 607 张源图。部件区域按官方父实例归属提取，同名部件的断开可见部分保留为 union；不是凭 bbox 重画一个区域。

40 图的早期分层视觉初审仅留下 5 个待独立复核，其中 2 个同时具备细部可辨、遮挡和同类干扰。适合继续看的例子包括被遮挡的床头柜抽屉、藤椅扶手、交错家具腿、沙发靠垫和灯座结构。

需要重点剔除真实孔洞被填满、highlight 类别与可编辑部件不对应、同部件 union 不完整、遮挡物误纳入 mask、低分辨率细条，以及无遮挡简单矩形/圆盘区域。早期样本说明必须精挑，不能据此推算整个候选池的通过率。

本地已知 SAMTok 会话中的 20,196 个 ADE 首图路径均来自 training，当前所选 part 图来自 validation；仍需保留实际 tokenizer ADE 清单和 SUN/Places 来源别名没有完整重建的限制。

本地入口：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/PACO_benchmark_candidates/
  goal_1k/ade20k_part234/official/ADE20KPart234/
```

### 3.4 MOSEv2：用于实例混淆与复杂遮挡，不自动提供部件任务

本地 valid 有 433 个视频及对应首帧正式 mask；调查时只有首帧 GT 可用，不能把全部 66,526 帧都当作带标注源图。几何与质量预筛曾得到 111 张候选。

拥挤海狮、同类相邻目标和遮挡复杂的可见边界较适配。它主要提供实例 mask，没有原生 part 层级；必须让编辑任务对应整个被标实例，不能自行把整对象 mask 当作某个未标部件。

自己的 3,666 个 train 与 433 个 valid video ID 无交集，但匿名原视频身份仍可能与其他视频来源存在别名，需要结合图像/场景审计判断。优先保留可看清的局部对象与接触关系，拒绝夜景模糊、雾中车辆、过小鸟类等只有成像困难的案例。

本地入口：

```text
/mnt/bn/strategy-mllm-train/intern/common_datasets/MOSEv2/valid/
```

### 3.5 BURST：只从底层原视频来源已核实的子集取样

BURST 有较多可见实例 mask，但其 test/val 可能来自其他数据集的原始 train 视频。已有审计结果为：

| BURST split | 总视频段 | 已证原来源 train，应排除 | 已证原来源 held-out | 原来源 split 未核实 |
|---|---:|---:|---:|---:|
| test | 1,421 | 673 | 122 | 626 |
| val | 988 | 485 | 87 | 416 |

上述核查覆盖 HACS、LaSOT、Charades 的已取得官方来源清单；BDD、ArgoVerse、AVA、YFCC 等来源仍有待核范围。扩充时先看严格 held-out 子池，再对 test/val 的原视频与场景去重。不得把 LVIS 类别 ID 当作图像来自 COCO 或某特定 split 的证据。

值得选择的是手指附近的小物体、遮挡中的物体、细结构及同类干扰；部件标签较少，不能靠大量整人/整车增加细粒度任务数。候选 mask 沿用发布的可见区域 RLE，不能改用 amodal 不可见区域补全。

本地入口：

```text
/mnt/bn/strategy-mllm-train/intern/common_datasets/TAO-Amodel/
  BURST_annotations/{test,val}/all_classes_visibility.json
```

### 3.6 MeViS 与其他后备来源

MeViS `valid_u` 的同类干扰与遮挡可以作为补充，当时本地有 50 个带可用标注的 held-out 视频。指代若依赖“正在转身”“从左向右运动”等时间信息，单张源图无法唯一解析，必须改成可从静态图像确认的实例定位。原视频别名与实际训练 split 仍有未完整核验的范围。

EntitySeg、Pascal-Part、PartImageNet 的建议来自标注类型和来源信息调查，当时没有完成本地原图的逐例检查。它们应先获取并验证官方元数据、图片身份和原始 split，再决定是否投入图像复核，不应视为已经通过场景验证的可用候选池。

GroundingSuiteEval 则有明确排除依据：2,727 张原图中 2,726 张与已知 SAMTok 训练 ID 重叠；仅剩样本的场景较简单，不值得继续投入扩量。

## 4. 所有来源共用的选择条件

1. **来源可追溯。**记录原数据集、split、图像/视频/实例 ID；已证原训练来源的新增候选排除，未确定的来源单独暂存。
2. **原图与 mask 正确。**同尺寸、非空、可解码，并确认发布 mask 对应实际目标；保留其细边、空洞和断片，不用 bbox 代替。
3. **困难机制可见。**实例混淆、局部部件、复杂遮挡、细结构或近邻保护必须能从原图与叠加图看出；不能只用自动面积分数决定。
4. **可编辑且任务自然。**目标细节清楚到足以观察要求的编辑；不能通过不存在的物体或不合理变换制造难度。
5. **指令严格对应 mask。**明确被标实例/部件，简短且无歧义；其他对象可以作定位参照，不能成为额外编辑目标。
6. **图像与场景去重。**同图不同目标、同视频相邻帧和跨来源同场景需记录并去重，防止重复案例增加规模。
7. **实际审核与模型验证分开。**AI 看图不是人工批准；适配方法的困难机制也不等于 SAMTokEdit 已成功或其他模型必然失败。人工准入与新指令下的模型评测仍需实际记录。

训练重叠核查覆盖已知 ID/会话路径，以及缓存的 175,101 张项目编辑训练图的字节、像素和感知指纹。没有命中只证明相应检查未发现重叠；不能证明未知 tokenizer/基模训练图、任意裁剪和同场景其他帧全都未出现。完整审计范围见 [来源与构建说明](CONSTRUCTION.md)。

## 5. 与最终 v1 的关系

外部新增的 300 条实际来源如下，与旧集过滤保留的 150 条合并为 450 条 v1：

| 外部来源 | 最终进入新增集的 case 数 |
|---|---:|
| PACO/LVIS | 153 |
| BURST | 58 |
| ADE20K-Part | 43 |
| MeViS-valid_u | 26 |
| SA-V | 14 |
| MOSEv2 | 6 |
| **合计** | **300** |

调查优先级与最终数量衡量不同事情。SA-V 局部 mask 的适配潜力较高，但实际仍需经过清晰度、语义、边界与来源筛选；ADE 的早期低产出也不等于后续不能精挑出合适 case。队列目标数、源图数、视频组数与最终 case 数不能混算，也不能直接拿表中的数量作通过率分子。

旧 TXT/JSON 里的 `admitted_cases=0`、规划范围及候选规模是当时阶段性状态，不能覆盖最终 release。当前 300 条新增指令已对照原图与原始 mask 逐例修订；截至 2026-10-09，已完成包含这 300 条在内的正式 450 条 Qwen-Image-2.1 纯文本测试及后续 433 条扩充测试，统计与可视化见 [v1 报告](V1_REPORT.md)；结果是 AI 视觉复核，独立人工确认仍待提供。

因此，如果继续扩充，建议先回看已有 PACO 部件池，再按上述补充源优先级寻找少量符合共同条件的案例。已经入选的源图/场景必须去重排除；一个来源剩余好样本少时转向下一来源，不按数据集配额补数量。

## 6. 原始记录与后续使用入口

| 记录 | 用途 |
|---|---|
| [原中文优先级建议](/mnt/bn/strategy-mllm-train/user/tanyue/datasets/PACO_benchmark_candidates/goal_1k/source_priority_recommendations.txt) | 阶段性简短建议；包含部分后来被更新的可用性状态 |
| [数据源详细盘点](/mnt/bn/strategy-mllm-train/user/tanyue/datasets/PACO_benchmark_candidates/goal_1k/source_priority_inventory.json) | 更新后的来源排序、路径、看图发现、审计范围和后备源 |
| [候选池与 release 进度](/mnt/bn/strategy-mllm-train/user/tanyue/datasets/PACO_benchmark_candidates/goal_1k/candidate_pool_status_20261004.md) | 从候选池、220 条 release 到扩充 300 条的记录 |
| [ADE 初审建议](/mnt/bn/strategy-mllm-train/user/tanyue/datasets/PACO_benchmark_candidates/goal_1k/ade20k_part234/source_review/pilot_recommendation.txt) | 部件数据的具体失败模式与小量补充建议 |
| [v1 逐例来源追溯](../data/v1/provenance.jsonl) | 最终 450 条的原图、mask、原 ID、筛选理由与来源 release |
| [v1 数据集说明](DATASET.md) | 当前数据统计、正式资产路径、schema 与审阅工具 |
| [v1 构建方法](CONSTRUCTION.md) | 筛选、mask 来源、指令编写与人工准入 |

原始调查文件保留了不同阶段的判断，例如 SA-V 曾暂缓、ADE validation 曾未在本地，后来都有追加审计或数据准备。理解更新后的结论时，优先读详细盘点中的 `final_next_source_order` 和补充审计，再结合最终逐例 provenance；不要运行早期生成脚本覆盖这些调查记录。
