# SAMTok Benchmark v2（1,084 case）指令与标注全量审查报告

> 历史快照：本报告描述修复前的 2.5.0，不是 2.6.0 当前问题清单。修复任务现已全部完成，见 [发布记录](RELEASE_2_6_0_ZH.md)及[前后对比](RELEASE_2_6_BEFORE_AFTER_ZH.md)。原 `/tmp/samtok_audit/` 文本产物已持久化到 `construction/release_2_6/audit/`，审图持久化到 `<数据根>/release_2_6_work/_audit_views/`。正文保留当时的协议 1.0 审查口径。

审查日期：2026-10-15。审查对象：`data/v2_1084/cases.jsonl`（1,084 case / 3,872 个编辑单元 U1–U5），数据根 `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2/`。本次审查**未修改** manifest 或任何已有数据文件；全部中间产物在 `/tmp/samtok_audit/`。

> 重要说明：本次“目视审查”由 assistant（主审）与其分派的 28 个并行视觉审查子代理完成，属于**模型目视复核**，不是独立人工验收。主审本人另外抽查了 10 个 case 用于校准（与子代理结论 10/10 一致）。所有结论均附具体证据，可在 `/tmp/samtok_audit/views/<case_id>.jpg` 复核。

## 0. 结论摘要

- **全部 1,084 个 case 均已打开合成审图（原图 + 各 U 的 mask 轮廓/box/point + 局部放大）逐一目视复核**；3,872 个单元全部经过自动规则检查。
- 经目视确认存在问题的 case：**645 / 1,084（59.5%）**；其中最严重级别为阻断（blocking）的 **158** 个、严重（major）**349** 个、仅轻微（minor）**138** 个。另有 40 个 case 仅有自动文本规则发现的轻微措辞问题。
- 按单元计：目视确认问题单元 **1123 / 3872（29.0%）**，其中阻断 **242**、严重 **630**、轻微 **251**；文本规则另记 154 条轻微问题（涉及 154 个单元，部分与目视问题重叠）。
- **问题高度集中在扩充集尾段**：manifest #945–#1083（139 case）几乎全部由模板化指令构成（“the X at the left / near the center”，94% 的 ref 是此模板），其中 93 个 case 有阻断问题、137 个有严重及以上问题。#869–#944 的 76 个 case 也明显退化（42 个阻断）。已知问题 `v2-sa_9357354`、`v2-sa_9345888` 只是这一批系统性缺陷的两个例子。
- 最主要问题类别：①replace 实为换色/换材质/换图案（应归 attribute）；②指代歧义（同类实例多、ref 不能唯一确定）；③方位词/序数与 mask 实际位置矛盾；④对“整个人”改色或把人替换成衣服（人物/服装层级错误）；⑤ref 名词与 mask 实际物体不符（如 “officer” 实为衬衫、“bottle” 实为水母）。
- 未被任何自动规则命中的 628 个 case 全部目视复核后，仍有 **22（3.5%）** 个含阻断问题、**198（31.5%）** 个含严重及以上问题——说明现有规则只能抓住模板化的显性错误，细粒度指代/歧义问题必须靠视觉复核。
- 建议：正式评测前**排除全部阻断 case**，并将 #869–#1083 尾段整体退回重新撰写/复核；其余严重问题按第 4 节清单逐条修订后重新跑构建校验与目视复核。

## 1. 审查范围与方法

### 1.1 阶段 A：全量自动检查（3,872 单元）

脚本 `/tmp/samtok_audit/phaseA.py`，完整输出 `/tmp/samtok_audit/auto_checks.json`（含每单元 mask 统计与全部 flag）。检查项：

1. 人物/服装层级：ref 头名词或 scope 为人物词（person/man/woman/dancer/officer/child/player/worker/vendor… 约 80 个）且未提及服装/部件时的 attribute/replace/remove/add；人物被替换为服装 payload；add 锚点为整个人。
2. 方位一致性：ref 中 left/right/top/bottom/upper/lower/center/far left/leftmost 等与 box 中心（相对图宽高）的矛盾（如 left 但 cx>0.6W、center 但偏离中心>0.3W）；同 case 同类名词 left/right 的相对次序矛盾。关系短语（left of / behind 等）降级为 major。
3. Ref/No-ref 等价：No-ref 是否严格等于把 `spec.ref` 替换为 `the selected <scope>`；payload 是否出现在两种指令中；No-ref 是否泄露方位词、是否出现 “the selected X of the selected Y”、“handle of the handle” 类重复。
4. 操作语义：replace payload 与原物同类且只差颜色/材质/图案修饰词；replace payload 无名词（“with blue”）；attribute 缺值、值无色相（“to dark”）、值为物体短语、值与 ref 中现有颜色相同；remove 范围（contents/hem/part）是否写明；移除穿着中的服装、移除建筑/大面积区域；add 是否有 relation、是否 support 锚点、payload 是否有悬空 its、是否笼统（a small logo）、是否非实物（glow）。
5. mask/几何：mask 可读、尺寸一致、空/极小、mask 外接框与 stored box 一致、point 是否在 mask 内、同 case 两 mask IoU>0.3 或包含>50%、box 包含关系、部件级指令 mask>40% 图像、远距离多碎块。
6. 文本质量：重复词、双空格、句末标点、a/an、异常字符、长度（Ref>26 词、No-ref>16 词）、`which/located/the one` 从句；中文与英文的颜色、数量、操作动词、左右方位一致性。
7. 独立性与重复：同 case `physical_parent_zh`/`parent_instance_id`/annotation_id/mask 哈希重复；同 case 及全库重复指令。

结构性检查全部通过：No-ref 与 Ref 的模板等价（0 例不一致）、mask 尺寸/外接框/point 位置、同 case mask 显著重叠均 0 例。这说明问题主要是**语义层面**的，现有构建校验（结构/哈希）无法发现。

自动规则命中情况（命中单元数 / 被目视确认 / 被目视否定；其余为未明确表态）：

| 规则 | 命中 | 确认 | 否定 | 说明 |
|---|---:|---:|---:|---|
| `replace_is_recolor` | 139 | 134 | 3 |  |
| `spatial_contradiction` | 115 | 78 | 35 | 约 30% 为相对群组/父物体的合理描述 |
| `add_dangling_its` | 95 | 0 | 62 | 文本问题，约定由主审集中记录（全部计为轻微文本问题），子代理“否定”仅表示未重复记录 |
| `add_generic_payload` | 59 | 1 | 46 | 同上；笼统 payload 记为轻微 |
| `box_contained` | 52 | 0 | 43 | 仅提示信息，多数 mask 本身不重叠 |
| `person_level_attribute` | 37 | 37 | 0 |  |
| `person_replaced_by_clothing` | 25 | 25 | 0 |  |
| `noref_location_leak` | 23 | 0 | 23 | 多为安装部位 site（如 upper-right corner），非定位泄露 |
| `remove_worn_garment` | 22 | 15 | 6 |  |
| `zh_op_mismatch` | 22 | 0 | 22 | “剪去/系”等译法正确，规则误报 |
| `mask_far_fragments` | 19 | 4 | 15 | 多为被遮挡物体的合法分离可见块 |
| `add_nonobject_payload` | 17 | 2 | 14 |  |
| `replace_bare_color` | 14 | 14 | 0 |  |
| `remove_scope_missing` | 13 | 0 | 13 | “including its contents/to make it knee-length”已写明范围，规则误报 |
| `noref_too_long` | 9 | 0 | 9 |  |
| `zh_side_extra` | 9 | 1 | 8 |  |
| `person_remove` | 9 | 0 | 6 |  |
| `zh_color_missing` | 8 | 1 | 7 |  |
| `relative_lr_contradiction` | 7 | 0 | 5 |  |
| `odd_char` | 7 | 0 | 7 |  |
| `remove_structural` | 7 | 6 | 0 |  |
| `mask_huge` | 5 | 1 | 4 |  |
| `person_add_anchor` | 5 | 0 | 1 |  |
| `add_on_whole_person` | 5 | 5 | 0 |  |
| `add_no_quantity` | 4 | 0 | 4 |  |
| `remove_huge_region` | 3 | 3 | 0 |  |
| `attribute_noop` | 2 | 1 | 1 |  |
| `person_replace` | 2 | 1 | 1 |  |
| `attribute_value_vague` | 2 | 2 | 0 |  |
| `zh_side_flip` | 1 | 1 | 0 |  |
| `ref_too_long` | 1 | 0 | 0 |  |
| `repeated_word` | 1 | 0 | 1 |  |
| `attribute_value_is_object` | 1 | 0 | 0 |  |
| `mask_tiny` | 1 | 1 | 0 |  |

### 1.2 阶段 B：目视复核

- 为每个 case 渲染合成审图 `/tmp/samtok_audit/views/<case_id>.jpg`（原图缩放至 ~1600px，U1 红/U2 蓝/U3 金/U4 紫/U5 绿 mask 轮廓 + box + point，下方为每个 U 的放大裁剪），渲染脚本 `/tmp/samtok_audit/render.py`。必要时子代理另开原图/原 mask 局部核对颜色、文字、号码。
- **第一轮**：阶段 A 命中的全部 **456** 个 case（排除纯 info 规则）+ 在未命中 case 中**按 manifest 顺序等间隔抽取的 180 个**对照样本，共 636 个，分 16 批由并行子代理逐 case 目视，逐条确认/否定自动 flag 并记录新问题。
- **第二轮**：剩余 448 个未命中 case 全部目视（12 批）。因此**全部 1,084 case 均被目视**；残余错误率既可用第一轮随机样本估计，也可用全部 628 个未命中 case 的普查值。
- 主审抽查：主审本人打开 10 个 case（含 9357354、9345888、7810159、6823812、1093348、6534458、6859686、8043384、8364417、9681021）核对子代理结论，10/10 一致（记录 `/tmp/samtok_audit/lead_spotcheck.jsonl`）。
- 每条问题记录：case、unit、严重度、类别、具体证据（指令所说 vs 图像/mask 实际，含坐标）、具体修改建议（重写后的 ref/no-ref 或 mask/spec/操作修改）、是否目视核验。
- 严重度：**阻断**=该单元错误/不可评分（错实例、层级错误、ref 与 mask 位置或类别矛盾、无对象的 replace、无变化的编辑、两单元同一物体）；**严重**=有歧义或可能误导模型/评审（ref 可指多个实例、replace 实为换色、移除穿着衣物/整栋建筑、mask 含明显邻居或漏大块）；**轻微**=措辞、颜色词、翻译等不改变目标的问题。

### 1.3 未覆盖/局限（如实说明）

- 目视复核由模型完成，不等同独立人工验收；子代理之间的严重度尺度可能有轻微差异（主审抽查一致，但样本仅 10 个）。“指代歧义”“replace 是否算真实结构变化”等判断存在主观边界。
- 合成审图为缩放图；极细小目标（<0.05% 图像）、轻微 mask 边缘误差、遮挡后的少量漏标未系统检查；未逐像素比对 mask 与原 RLE（构建校验已做）。
- 未检查：模型实际可编辑性/生成结果（尚无模型输出）、训练集泄露与近重复、difficulty 标签准确性、completion_requirement/preserve 文本的逐字正确性（仅检查与 instruction 一致）、中文翻译的全部细节（只做规则检查 + 目视中顺带发现）。
- 未发现问题 ≠ 无问题：未命中且目视未记录问题的 case 仍可能存在细小歧义。

## 2. 总体统计

### 2.1 按严重度（目视确认）

| 级别 | case 数（按最严重问题计） | 单元数（按最严重问题计） | 问题条数 |
|---|---:|---:|---:|
| 阻断 | 158 | 242 | 252 |
| 严重 | 349 | 630 | 693 |
| 轻微 | 138 | 251 | 264 |
| 合计 | 645 | 1123 | 1209 |

另有自动文本规则发现、未单独目视判定的轻微问题 154 条（add 指令悬空 its 95 条、笼统 add payload 59 条），见 4.4 节。

### 2.2 按类别 × 严重度（目视确认问题条数）

| 类别 | 阻断 | 严重 | 轻微 | 合计 | 涉及 case |
|---|---:|---:|---:|---:|---:|
| 指代歧义 (`ambiguous_ref`) | 3 | 225 | 70 | 298 | 230 |
| replace 实为属性修改 (`replace_is_attribute`) | 7 | 261 | 7 | 275 | 275 |
| 方位/序数/实例指代错误 (`wrong_instance_spatial`) | 109 | 43 | 18 | 170 | 140 |
| mask 质量 (`mask_quality`) | 6 | 44 | 60 | 110 | 105 |
| 人物/服装层级错误 (`person_clothing_level`) | 71 | 1 | 0 | 72 | 50 |
| 指代类别与 mask 不符 (`category_mismatch`) | 31 | 19 | 14 | 64 | 58 |
| 属性值问题（无变化/含糊） (`attribute_value`) | 10 | 25 | 22 | 57 | 57 |
| 编辑不合理/不可执行 (`ill_posed_edit`) | 11 | 40 | 4 | 55 | 52 |
| 多单元同一物理对象/相互冲突 (`independence_violation`) | 4 | 27 | 9 | 40 | 40 |
| 措辞/文法/描述细节 (`grammar_style`) | 0 | 0 | 39 | 39 | 38 |
| 中文翻译不一致 (`translation`) | 0 | 1 | 18 | 19 | 18 |
| add 锚点不当 (`add_anchor`) | 0 | 7 | 1 | 8 | 8 |
| Ref/No-ref 不等价 (`ref_noref_mismatch`) | 0 | 0 | 2 | 2 | 2 |

### 2.3 按 manifest 区段

| 区段 | case 数 | 有阻断 | 严重及以上 | 任意问题 | 阻断率 |
|---|---:|---:|---:|---:|---:|
| 原版 #0–#199（200 case） | 200 | 7 | 59 | 104 | 3.5% |
| 扩充 #200–#868（669 case） | 669 | 16 | 238 | 328 | 2.4% |
| 扩充 #869–#944（76 case） | 76 | 42 | 73 | 74 | 55.3% |
| 扩充尾段 #945–#1083（139 case） | 139 | 93 | 137 | 139 | 66.9% |

尾段 #945–#1083 的特征：`instruction_review.version=2.5.0-draft`、`instruction_design` 无 recipe；`difficulty.evidence_zh` 多为“X、Y、Z 和 W 是四个不同对象”，`specific_protection_zh` 为“保留……”泛化句；ref 94% 为 “the <noun> at/near the <方位>” 模板，方位词与实际位置大量矛盾，attribute 常直接对人改色，replace 常为“同类换色”或“人→衣服”“X→裸颜色”。这与 README 中“每张图具有 assistant 直接视觉审核依据”的表述不符。

### 2.4 残余错误率（自动规则未命中部分）

| 口径 | 样本 | case 含阻断 | case 含严重及以上 | case 含任意问题 | 单元含阻断 | 单元含严重及以上 |
|---|---:|---:|---:|---:|---:|---:|
| 第一轮等间隔系统抽样（180 case / 616 单元） | 180 | 9 (5.0%) | 68 (37.8%) | 95 (52.8%) | 11 (1.8%) | 80 (13.0%) |
| 全部未命中 case 普查（628 case / 2161 单元） | 628 | 22 (3.5%) | 198 (31.5%) | 298 (47.5%) | 25 (1.2%) | 246 (11.4%) |
| 对照：自动命中 case（456） | 456 | 136 (29.8%) | 309 (67.8%) | 347 | | |

按等间隔抽样样本估计（近似随机样本处理），自动规则漏掉的 case 中约 5.0%（95% 区间约 ±3.2%）含阻断问题、约 37.8%（±7.1%）含严重及以上问题；全量普查值（3.5% / 31.5%）与之相符。未命中部分的主要问题是 replace 实为换色、同类实例歧义、同一人身上取多个单元、颜色词/类别词与图像不符等细粒度问题。

## 3. 问题类别说明与示例

### 3.1 人物/服装层级错误（`person_clothing_level`，72 条）

对整个人做 attribute（“Change the color of the person to blue”）、把人 replace 成服装（“Replace the officer with a black uniform”），或指令说“衬衫”但 mask 是整个人。违反协议“不得把给人改色含糊代指衣服”“新旧对应同一层级”。集中在尾段模板 case；而且相当多此类单元的 mask 其实只是衣服（`category=person` 是错标），需同时修 ref 与 scope。

- `v2-sa_7231402` U2（阻断）：当前 “Change the color of the child seated behind the foreground student to a red shirt.”。问题：U2 mask（box [1788,950,2104,1500]）是整个坐着的孩子（头加身体）；REF 'Change the color of the child ... to a red shirt' 对人物应用了颜色属性，并把物体短语用作值。 建议：“Change the color of the beige uniform shirt of the child seated behind the foreground student to red.”；重新 mask 到孩子的米色衬衫上；范围 child -> shirt
- `v2-sa_7362739` U3（阻断）：当前 “Replace the passenger seated near the right side of the boat with a yellow raincoat.”。问题：U3 mask 是一位完整的坐着的乘客(穿丁香色上衣和牛仔裤的年轻女子,box x 1198-1277);'Replace the passenger ... with a yellow raincoat' 是用一件衣服替换整个人。此外 'near the right side of the boat' 也不对:她坐在乘客区左/前端,紧靠驾驶舱后方,更右侧还有许多乘客。 建议：“Change the color of the lilac top of the passenger sitting just behind the boat's cabin to yellow.”；re-mask to the passenger's lilac top (garment level), or keep whole-person mask and use a person-level edit such as 'Replace the passenger sitting just behind the cabin with an empty seat'

### 3.2 方位/序数/实例指代错误（`wrong_instance_spatial`，170 条）

ref 的 left/right/center/upper/nearest/序数/号码/身体左右与 mask 实际位置不符，导致 ref-only 输入指向别的实例，并污染 completion_requirement/edit_contract。

- `v2-sa_7103552` U1（阻断）：当前 “Remove the image-right sock of the leftmost white-clad player.”。问题：最左侧白衣球员（#3）：U1 mask（box x 177-223，cx=200）是他画面左侧的长袜；他的另一只袜子在更靠右的位置（原图约 x 265）。REF/ZH 写的是“image-right sock”。 建议：“Remove the image-left sock of the leftmost white-clad player.”；ZH: 移除最左侧白衣球员画面左侧的长袜。
- `v2-sa_1580699` U3（阻断）：当前 “Add one red ribbon bow tied around the upper end of the long package behind and left of the large blue shopping bag.”。问题：REF 称包裹“behind and left of the large blue shopping bag”,但 U3 mask(box x 2021-2106,中心 0.92W)位于蓝色购物袋的右侧(袋子跨越约 x1870-2025);紧邻袋子左侧的包裹是 U4 的目标,因此 REF 指向了错误的实例。 建议：“Add one red ribbon bow tied around the upper end of the long pale package hanging just right of the large blue shopping bag.”；ZH 左后方 -> 右侧

### 3.3 指代类别与 mask 不符（`category_mismatch`，64 条）

ref 名词与 mask 实际物体不同类（“officer”实为白衬衫、“bottle”实为水母、“sign”实为灯、“belfry”实为方尖碑），或颜色/属性描述与原图明显不符导致指向错误。

- `v2-sa_7725244` U2（阻断）：当前 “Replace the pale bag visible behind the red bags on the left with a tied brown paper sack.”。问题：REF/ZH 称目标为 'pale (light-gray) bag visible behind the red bags',但 U2 mask(box [232,707,375,865])覆盖的是堆叠最左端一个饱和的橙红/鲑鱼色塑料袋,位于其他红色袋子前方/之间,而不是它们后面的浅色袋子。 建议：“Replace the orange-red plastic bag near the left end of the pile with a tied brown paper sack.”；fix REF and ZH description to orange-red bag (ZH: 将左侧橙红色塑料袋替换为扎口牛皮纸袋。)
- `v2-sa_2734741` U3（阻断）：当前 “Remove the discarded plastic bottle on the sand.”。问题：REF 说“discarded plastic bottle”,但被 mask 的物体(box [1573,1091,1640,1150])是沙滩上一只带放射状纹路、半透明的圆形搁浅水母,不是瓶子。 建议：“Remove the stranded jellyfish on the sand.”；将 scope/类别从瓶子改为水母;ZH:移除沙滩上搁浅的水母。

### 3.4 指代歧义（`ambiguous_ref`，298 条）

图中有多个同类实例都符合 ref（“the banner at the left”有两面并排横幅；“the shuttered window”有 40 扇），ref-only 或评审无法唯一确定目标。

- `v2-sa_7279175` U4（阻断）：当前 “Add a small flower box on the shuttered window on the building.”。问题：正式输入是 ref+none，所以 REF 是唯一的定位器，但“the shuttered window on the building”适用于议会大楼立面上约 40 个相同的带百叶窗的窗户。被 mask 的 [1489,519,1539,602] 位于右翼二层（上层），在中央门廊块右侧的第一个窗户。 建议：“Add a small flower box under the upper-floor shuttered window just right of the central portico block of the building.”；或将正式输入改为定位器（box/point/mask）。
- `v2-sa_805201` U3（阻断）：当前 “Remove the beach chair at the lower left.”。问题：甲板左下方摆满了许多躺椅；被 mask 的那个（box 296-508 x, 907-1002 y，~0.18W,0.64H）是左中部一张有日光浴女子躺着的躺椅，并不是最左下的那张。mask 只是两个很小的碎片（头枕和脚托，面积 0.0008），且移除有人坐着的椅子本身也是不合理的。；删除该单元，或改为选择一张无人占用、清晰可辨且 mask 完整的躺椅。

### 3.5 replace 实为属性修改（`replace_is_attribute`，275 条）

replace 的新物与原物同类、只改颜色/材质/图案/文字（“Replace the boat with a blue boat”“puffer jacket → leather jacket”），或干脆是裸颜色/与原物相同（“with black”、红色敞篷车→红色敞篷车）。协议要求“单纯换色归 attribute”。

- `v2-sa_8871336` U2（阻断）：当前 “Replace the lamp post at the left with black.”。问题：'Replace the lamp post at the left with black.' 用单纯的颜色作为 replace payload，而华丽的双灯笼灯柱本来就是黑色，因此该编辑格式错误且实质无效。 建议：“Replace the ornate double-lantern lamp post at the left with a modern single-arm steel streetlight.”；ZH: 将左侧的华丽双灯头灯柱替换为一根现代单臂钢制路灯。
- `v2-sa_9013170` U2（阻断）：当前 “Replace the convertible at the lower left with a red convertible.”。问题：被 mask 的敞篷车 [210,1081,376,1201] 本来就是红色经典敞篷车（野马风格）；'Replace ... with a red convertible' 实质无效，无法评分。 建议：“Replace the red convertible at the lower left with a white delivery van.”

### 3.6 编辑不合理/不可执行（`ill_posed_edit`，55 条）

编辑本身不合理或不可评分：移除穿在身上的衬衫/外套、移除整栋建筑/桥/屋顶、移除载人的婴儿车/轮椅、给已戴头盔者“加头盔”、给植物“加花盆”、加“a warm glow”等。

- `v2-sa_7420848` U4（阻断）：当前 “Add a yellow helmet on the cyclist on the road near the center.”。问题：被 mask 的骑行者（cx=0.27，偏离中心靠左，并非 'near the center'）本来就戴着白/灰色头盔，因此 'Add a yellow helmet on the cyclist' 与现有头盔冲突；锚点是整个人加自行车，没有给出位置。 建议：“Add a small red flag on a pole mounted on the rear of the bicycle of the cyclist approaching on the left side of the road.”；或改为属性编辑：Change the color of the helmet of the cyclist ... to yellow（使用头盔 mask）
- `v2-sa_7698269` U4（阻断）：当前 “Add a ceramic pot on the potted plant at the lower left.”。问题：U4 mask 覆盖的是本来就种在深色方形花盆中的造型树;'Add a ceramic pot on the potted plant' 不合理(它已经有盆,而且盆不能放在植物上)。 建议：“Add a small wooden birdhouse hanging in the topiary tree in the planter at the lower left.”

### 3.7 属性值问题（无变化/含糊）（`attribute_value`，57 条）

目标属性值与现状相同或几乎相同（白车改白、黑灯改 matte black），或值无色相（“to dark”），无法判断是否完成。

- `v2-sa_7698269` U1（阻断）：当前 “Change the color of the street lamp on the left to black.”。问题：U1 mask 是左侧立面上带卷轴支架的壁挂灯笼,它本来就是黑色;“Change the color ... to black”是空操作编辑。 建议：“Change the color of the wall-mounted lantern on the left facade to brass gold.”；scope -> wall lantern
- `v2-sa_7854521` U1（阻断）：当前 “Change the color of the boat at the lower center to white.”。问题：被 mask 的船“GRAFIN COSEL”(box [897,2189,1500,2527])船体和上层建筑本来就是白色;“Change the color ... to white”实质上是空操作,无法评分。 建议：“Change the color of the hull of the white passenger boat at the lower right to dark green.”

### 3.8 mask 质量（`mask_quality`，110 条）

mask 覆盖了错误/多余对象（整个人而非衬衫、两个人、气球+毯子当婴儿车、桥栏当桥），或只覆盖目标的一小部分、碎片化严重。

- `v2-sa_7116219` U3（阻断）：当前 “Remove the orange costume on the person at the right.”。问题：U3 mask(box x 1284-1468, y 460-980, comps=2)勾勒了两个完整的人 —— 穿橙色长袍、拿粉色布的成人,以及站在他前面、穿橙色束腰衣、背着单肩包的男孩 —— 包括头部,而不是单一的服装。REF 'the person at the right' 也不精确(cx=0.61;更右侧还有许多人)。 建议：“Change the color of the orange tunic and trousers of the boy with the small shoulder bag to light blue.”；re-cut mask to one garment of one person (e.g. the boy's orange tunic) and change op away from remove
- `v2-sa_7506005` U1（阻断）：当前 “Change the color of the shirt on the foreground runner to bright blue.”。问题：REF 的目标是 'the shirt on the foreground runner'，但 mask/box [602,919,959,1987] 覆盖整个跑者（从头到鞋），即对衣物编辑使用了人物级 mask。 建议：“Change the color of the white-and-red singlet on the foreground runner to bright blue.”；重新 mask 到背心上。

### 3.9 多单元同一物理对象/相互冲突（`independence_violation`，40 条）

同一 case 两个单元落在同一物理对象（同一人的帽子和包、衬衫和袖子），或编辑相互冲突（U3 删除的人手里拿着 U2 要替换的镰刀）。违反“每图 2–5 个不同实物”。

- `v2-sa_7677069` U2（阻断）：当前 “Replace the sickle near the center with a wooden tool.”。问题：U2 镰刀(box [917,953,1053,1301])握在中间那位女子手中,她是 U3 且将被移除;U2 box 位于 U3 box 之内。这两个编辑相互冲突(移除女子会使被替换的工具悬在空中),且不是独立的物体。；删除 U2(或删除 U3 并保留镰刀编辑);选择独立的物体,如女子左侧地面上的金属托盘
- `v2-sa_8586145` U4（阻断）：当前 “Add a small logo on the cap near the left.”。问题：U4 mask 是绿色棒球帽（box 1953-2007 x），由 U2 的T恤所属的同一名男子佩戴；一个人身上有两个单元。REF 'the cap near the left' 也是错的（0.88W，在右侧）。 建议：“Add a small white logo on the green cap at the front right.”；删除 U4，或把 U2 移到另一个人身上。

### 3.10 add 锚点不当（`add_anchor`，8 条）

add 锚点不合适：锚点是整个人且无部位、座椅被人占据无可见座面、屋顶在画外等。

- `v2-sa_7311948` U4（严重）：当前 “Add a red seat cushion on the folding chair at the right tables.”。问题：U4 mask（box [1720,907,1787,1007]）是一把青绿色折叠椅，上面坐着穿灰色 T 恤的男子；mask 围绕他的身体呈碎片状，座面完全被遮住，因此 'Add a red seat cushion on the folding chair' 没有可见的座面可附着。；选择右侧桌子旁的空折叠椅作为锚点，或更改 op（例如 'Change the color of the folding chair ... to red'）
- `v2-sa_8043384` U4（严重）：当前 “Add a small badge on the man at the far left.”。问题：U4 mask 是行走人群最左侧一个远处的整个小人（box [46,639,129,837]）；“Add a small badge on the man”没有给出可附着的衣物/身体部位。 建议：“Add a small badge on the chest of the gray jacket of the man at the far left.”；重新对夹克做 mask

### 3.11 中文翻译不一致（`translation`，19 条）

中文与英文不一致（操作范围、颜色、方位不同）或中文错乱。

- `v2-sa_8139733` U1（严重）：当前 “Remove the bow tie from the front-center rabbit figurine holding a pocket watch.”。问题：EN：移除前排中央拿怀表的兔子的领结。ZH：“移除前排中央拿怀表兔子摆件的身体主体，不含怀表和标签的领结”——表述混乱，读起来像是移除身体；操作范围不一致。；ZH: 移除前排中央拿怀表兔子摆件的领结。
- `v2-sa_4594747` U2（轻微）：当前 “Add one small red navigation light at the tip of the vertical tail of the front airplane.”。问题：ZH REF 写的是“垂直尾翼及根部过渡”（尾翼及根部过渡），而英文只说“the vertical tail of the front airplane”。；ZH: 给前方飞机的垂直尾翼顶端加上一盏小红色航行灯。

### 3.12 措辞/文法/描述细节（`grammar_style`，39 条）

措辞/描述细节错误但目标仍可识别（颜色词偏差、手机写成相机、T 恤写成衬衫等）。

- `v2-sa_604524` U4（轻微）：当前 “Replace the orange inner top of the woman at the lower left with a white blouse with a ruffled neckline.”。问题：REF 把被 mask 的内层上衣称为 'orange'，但像素显示是左下方棕色夹克下的芥末黄上衣（North Face logo）；目标仍然唯一。 建议：“Replace the yellow inner top of the woman at the lower left with a white blouse with a ruffled neckline.”；ZH 橙色 -> 黄色
- `v2-sa_1411984` U3（轻微）：当前 “Change the color of the white T-shirt of the passerby behind the tree on the left to pale green.”。问题：被 mask 的衣物是白色翻领短袖衬衫,而不是 T 恤;该男子走在树的左侧(仅轻微被遮挡),“behind the tree”表述不够准确。 建议：“Change the color of the white short-sleeved shirt of the man walking on the far left to pale green.”；scope=shirt

### 3.13 Ref/No-ref 不等价（`ref_noref_mismatch`，2 条）

No-ref 的 scope 与 Ref 层级不同（“the selected lantern” vs ref 只指灯头）。

- `v2-sa_11150954` U1（轻微）：当前 “Replace the entrance wall lantern’s light head with an opal globe light.”。问题：REF 指向 "the entrance wall lantern's light head"(mask 仅为灯头,不含支架),ZH NOREF 写的是 选中的灯头,但 EN NOREF 写的是 "Replace the selected lantern",可能被理解为包括支架在内的整盏灯。
- `v2-sa_7773451` U3（轻微）：当前 “Remove the person at the far left.”。问题：REF 写 'the person at the far left'，而 NOREF 写 'the selected man'（scope 'man'）；ZH 用的是 人物。 建议：“Remove the man sitting at the far left.”

## 4. 完整问题清单

说明：按 case 分组；先列含阻断问题的 case，再列最严重为“严重”的 case，最后列仅含轻微问题的 case；组内按 manifest 顺序。“输入”为该单元正式评测输入形式（ref/noref + 定位）。“核验”列：**目视**=已在审图上核实；**文本**=仅自动文本规则发现。证据为中文译述（保留原英文指令、坐标）；建议中的英文为可直接替换的新指令。

### 4.1 含阻断问题的 case（158 个）

#### `v2-sa_7103552`（#43，原版 #0–#199，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | ref+box | Remove the image-right sock of the leftmost white-clad player. | 最左侧白衣球员（#3）：U1 mask（box x 177-223，cx=200）是他画面左侧的长袜；他的另一只袜子在更靠右的位置（原图约 x 265）。REF/ZH 写的是“image-right sock”。 | Ref: Remove the image-left sock of the leftmost white-clad player.<br>ZH: 移除最左侧白衣球员画面左侧的长袜。 | 目视 |
| U2 | 严重 | 方位/序数/实例指代错误 | noref+mask | Replace the sock on the leftward-extended leg of yellow-shirted player 14 with a short black ankle sock. | 被 mask 的伸腿的黄衣球员穿 15 号(衬衫和短裤上均可见);不存在黄衣 14 号球员。REF/ZH 写的是 'player 14'。 | Ref: Replace the sock on the leftward-extended leg of yellow-shirted player 15 with a short black ankle sock.<br>ZH: 14号 -> 15号 | 目视 |
| U4 | 轻微 | mask 质量 | ref+mask | Change the color of the image-left sock of white-shirted player 5 to bright blue. | U4 mask 在其 box 右边缘附近有一个很小的零散分量（位于另一名球员的脚踝上，约源图 x 1135）；主分量正确。 | 删除零散的 mask 碎片 | 目视 |

#### `v2-sa_1580699`（#69，原版 #0–#199，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+mask | Add one red ribbon bow tied around the upper end of the long package behind and left of the large blue shopping bag. | REF 称包裹“behind and left of the large blue shopping bag”,但 U3 mask(box x 2021-2106,中心 0.92W)位于蓝色购物袋的右侧(袋子跨越约 x1870-2025);紧邻袋子左侧的包裹是 U4 的目标,因此 REF 指向了错误的实例。 | Ref: Add one red ribbon bow tied around the upper end of the long pale package hanging just right of the large blue shopping bag.<br>ZH 左后方 -> 右侧 | 目视 |

#### `v2-sa_719433`（#95，原版 #0–#199，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+mask | Change the material of the tall lidded jug body in the central shelf compartment to glazed white porcelain. | 'the tall lidded jug body in the central shelf compartment' 符合该格中多个带盖高壶/水罐(银色和铜色,x~1100-1240)。被 mask 的是该格最右端、紧靠 x~1250 处隔板左侧的铜色带盖壶。mask 也覆盖了整只壶,而不仅是壶身。 | Ref: Change the material of the copper lidded jug at the right end of the central shelf compartment, next to the red divider, to glazed white porcelain.<br>No-ref: Change the material of the selected jug to glazed white porcelain.<br>scope 'jug' instead of 'jug body' since the mask covers the whole jug | 目视 |
| U1 | 轻微 | 中文翻译不一致 | ref+mask | Change the material of the tall lidded jug body in the central shelf compartment to glazed white porcelain. | ZH '中央货架左侧'（中央货架的左侧）与图像矛盾：被 mask 的铜壶位于中央隔间的右端；英文中没有方位词。 | ZH: 将中央货架隔间右端、紧靠红色隔板的铜色带盖壶的材质改为白色釉面瓷。 | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+point | Add one short red ribbon bow around the neck of the small pedestal vase just right of the left shelf divider. | REF 说花瓶 'just right of the left shelf divider'。在原图中（box x 1004-1051），被 mask 的银色带底座花瓶紧邻 x~1057 处红色竖向货架隔板的左侧，其左边是大雕花壶和盘子列；其左侧没有隔板。该短语指向的是隔板右侧的物体（悬挂的银壶/铜壶），即另一个实例。ZH '靠左下方' 也不是有效的定位表述。 | Ref: Add one short red ribbon bow around the neck of the small silver pedestal vase just left of the red shelf divider, right of the large engraved jug.<br>ZH: 给红色货架隔板左侧紧邻、大雕花壶右边的小银色带底座花瓶的瓶颈系上一个短红丝带蝴蝶结。 | 目视 |

#### `v2-sa_1539716`（#111，原版 #0–#199，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+point | Replace the dark cap of the white-shirted person farther back on the right with a navy bucket hat. | U2 mask（box [1379,733,1468,826]）是穿 BLUE 'BMW АВТОЦЕНТР' 上衣（号码布 1863）的跑者所戴的深色帽子；REF 却称他为 'the white-shirted person'。白衣者是他右边的那个人（没戴帽子）。 | Ref: Replace the dark cap of the runner in the blue BMW shirt on the right with a navy bucket hat.<br>ZH: 将右侧穿蓝色BMW上衣跑者的深色棒球帽替换为藏蓝色渔夫帽。 | 目视 |

#### `v2-sa_1980337`（#118，原版 #0–#199，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+none | Replace the gray patterned scarf hanging directly behind the grill with a triangular fringed shawl. | REF/ZH 描述的是 'gray patterned scarf',但 U2 mask(box x745-834, y213-506)是挂在烧烤架左部上方、紧邻一条洋红色围巾的青绿色圆点围巾;真正的灰色/浅色花纹围巾挂得更靠右,所以 REF 指向了另一个实例。 | Ref: Replace the teal dotted scarf hanging beside the magenta scarf above the left end of the grill with a triangular fringed shawl.<br>ZH 灰色花纹 -> 青绿色圆点; fix physical_parent_zh | 目视 |
| U3 | 轻微 | 中文翻译不一致 | ref+mask | Add one small pearl brooch pinned to the top fold of the scarf between the two yellow scarves at the back right. | U3 的 physical_parent_zh 写的是 蓝绿悬挂围巾，但被 mask 的围巾实际是夹在两条黄色围巾之间的浅粉/米色围巾（标签似乎与 U2 对调了）；REF 文本本身没问题。 | physical_parent_zh -> 浅粉色悬挂围巾 | 目视 |

#### `v2-sa_2194487`（#121，原版 #0–#199，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Change the color of the hat of the man holding a French horn on the right to navy blue. | Mask/box [1796,748,2037,858] 是梳着两条长辫的女孩的帽子(帽子正下方是脸,辫子垂到胸前)。圆号由站在她身后右侧的男子拿着(原图中圆号约在 x2000-2140, y870-1050),他自己的帽子更高且未被 mask。因此 REF 'the man holding a French horn on the right' 指的是另一个人。 | Ref: Change the color of the hat of the braided girl on the right, in front of the French horn player, to navy blue.<br>Also fix physical_parent_zh (右侧编辫子女孩) and ZH ref text accordingly. | 目视 |

#### `v2-sa_7725244`（#184，原版 #0–#199，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 指代类别与 mask 不符 | noref+point | Replace the pale bag visible behind the red bags on the left with a tied brown paper sack. | REF/ZH 称目标为 'pale (light-gray) bag visible behind the red bags',但 U2 mask(box [232,707,375,865])覆盖的是堆叠最左端一个饱和的橙红/鲑鱼色塑料袋,位于其他红色袋子前方/之间,而不是它们后面的浅色袋子。 | Ref: Replace the orange-red plastic bag near the left end of the pile with a tied brown paper sack.<br>fix REF and ZH description to orange-red bag (ZH: 将左侧橙红色塑料袋替换为扎口牛皮纸袋。) | 目视 |

#### `v2-sa_10602261`（#249，扩充 #200–#868，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+none | Replace the blue hatchback behind the two pedestrians with a cream-colored vintage coupe. | REF/ZH 称目标为 'blue hatchback'（蓝色两厢车），但两名行人后方被 mask 的汽车（box [1730,1072,2011,1168]）明显是银色/浅灰色（已在源图裁剪中核实）。那里不存在蓝色汽车，因此 ref 文本描述的是一个不存在的实例。 | Ref: Replace the silver hatchback behind the two pedestrians with a cream-colored vintage coupe.<br>ZH: 将两名行人后方的银色两厢车替换为一辆奶油色复古双门轿车。 | 目视 |

#### `v2-sa_10631376`（#253，扩充 #200–#868，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+mask | Change the color of the backpack on the red-hooded tourist to forest green. | REF 说“the backpack on the red-hooded tourist”,但被 mask 的深色背包(box [142,2204,187,2250])是由一名从背后看到的、戴灰色兜帽/围巾的光头男子背着的;穿红色衣服的人是站在他右后方的另一名游客,看不到背包。REF 指向了错误的主人。 | Ref: Change the color of the dark backpack on the bald tourist with a gray hood at the bottom left to forest green.<br>No-ref: Change the color of the selected backpack body to forest green.<br>ZH:红兜帽游客 -> 左下角灰色兜帽光头游客 | 目视 |

#### `v2-sa_1112483`（#305，扩充 #200–#868，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+point | Change the color of the rightmost white parasol on the left bank to navy blue. | U2 mask 是近处左岸咖啡馆中 box [252,890,388,920]（cx=0.16）的大白色遮阳伞。在原图中，同一左岸更靠右约 x=570-770、y=890、中央桥旁还有更多白色遮阳伞，因此被 mask 的是最近/最左的一把，而不是最右的。 | Ref: Change the color of the nearest white parasol on the left bank to navy blue.<br>同时修正 ZH: 将左岸最近的白色遮阳伞的颜色改为藏蓝色。 | 目视 |

#### `v2-sa_2734741`（#478，扩充 #200–#868，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 阻断 | 指代类别与 mask 不符 | ref+box | Remove the discarded plastic bottle on the sand. | REF 说“discarded plastic bottle”,但被 mask 的物体(box [1573,1091,1640,1150])是沙滩上一只带放射状纹路、半透明的圆形搁浅水母,不是瓶子。 | Ref: Remove the stranded jellyfish on the sand.<br>No-ref: Remove the selected jellyfish.<br>将 scope/类别从瓶子改为水母;ZH:移除沙滩上搁浅的水母。 | 目视 |

#### `v2-sa_2981106`（#508，扩充 #200–#868，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 方位/序数/实例指代错误 | noref+point | Change the color of the uppermost lampshade on the left to white. | 左侧挂在支架上有三盏深色灯罩；U2 mask（box y 1274-1373，~0.59H）是中间那盏。另一盏灯罩明显在其上方（~0.52H，上支架处），一盏在其下方（~0.65H）。"uppermost lampshade on the left"（ZH 最上方）指的是上面那盏灯，而不是被 mask 的这盏。 | Ref: Change the color of the middle of the three lampshades on the left to white.<br>ZH: 将左侧三盏灯中间那盏的灯罩颜色改为白色。 | 目视 |

#### `v2-sa_3662681`（#573，扩充 #200–#868，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 属性值问题（无变化/含糊） | ref+none | Change the color of the wall lantern above the pizza sign to black. | U2 披萨招牌上方的壁挂灯笼本身已经是深灰/黑色金属框架；'change the color to black' 几乎没有可见变化。 | Ref: Change the color of the wall lantern above the pizza sign to bright red.<br>No-ref: Change the color of the selected lantern to bright red. | 目视 |
| U4 | 阻断 | 指代类别与 mask 不符 | noref+box | Remove the small blue hanging sign in the distance. | U4 mask（box [1014,1968,1088,2039]）是安装在蓝色锻铁支架顶部的蓝色装饰街灯 LANTERN（带玻璃窗格的灯罩），不是“small blue hanging sign”。它也不是悬挂的。 | Ref: Remove the small blue lantern on the wrought-iron bracket in the distance.<br>No-ref: Remove the selected lantern.<br>scope sign -> lantern; ZH: 移除远处铁艺支架上的蓝色小灯笼式路灯。 | 目视 |

#### `v2-sa_4441086`（#659，扩充 #200–#868，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 指代类别与 mask 不符 | noref+point | Remove the empty wheelchair beside the low wall. | box [1261,1335,1352,1428] 处的轮椅并不是空的：一名穿灰衬衫的男子坐在里面，前倾祈祷。mask 同时覆盖了轮椅和该男子的上半身。REF“the empty wheelchair”与图像矛盾，移除时还会同时移除一个人。 | Ref: Remove the purple bag hanging on the back of the wheelchair beside the low wall.<br>No-ref: Remove the selected bag.<br>要么将目标改为悬挂的紫色包（新 mask），要么删除该 unit；若保留为轮椅，REF 不得说“empty”，且 mask 必须排除坐着的男子（remove 不适定）。 | 目视 |
| U2 | 严重 | 指代歧义 | ref+box | Change the color of the light gray shirt left of the teal shirt in the lower row to pale blue. | U2 mask(box [839,1339,888,1375])是靠墙俯身叩拜的男子的白/浅灰色衬衫,位于青绿色衬衫礼拜者左侧两人处(中间坐着一个橄榄色衬衫男子)。另一位浅灰衬衫礼拜者就在青绿色衬衫左侧更近/更下一排(~x=930-970, y=1380-1420),更符合 'left of the teal shirt in the lower row'。 | Ref: Change the color of the white shirt of the worshipper prostrating closest to the wall, two places left of the teal shirt, to pale blue. | 目视 |

#### `v2-sa_4582303`（#675，扩充 #200–#868，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+mask | Replace the narrow beige shutter above the awning’s left tip with a blue wooden louvered shutter. | 被 mask 的百叶窗 [603,1445,630,1616] 是 'Salon de Coiffure' 立面上两扇窄米色百叶窗中的左边那扇,位于遮阳篷左端(~x770, y1580)左侧约 150px 处。真正位于 '遮阳篷左端上方' 的百叶窗是粉色建筑上约 x727-790, y1495-1650 的那些。街上有很多相同的窄米色百叶窗,所以 REF 指向了另一个实例。 | Ref: Replace the narrow beige shutter on the left side of the window above the SALON DE COIFFURE sign with a blue wooden louvered shutter.<br>Better: pick a more distinctive target, and see replace_is_attribute finding. | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the narrow beige shutter above the awning’s left tip with a blue wooden louvered shutter. | 现有百叶窗本来就是木质百叶窗；'a blue wooden louvered shutter' 只改变颜色。 | No-ref: Change the color of the selected shutter to blue.<br>改为属性编辑 color=blue，或替换为不同结构（例如 'a small wrought-iron balcony door'）。 | 目视 |

#### `v2-sa_5072835`（#721，扩充 #200–#868，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+box | Replace the brown shirt on the middle mannequin with a navy linen blazer. | 橱窗里站着三个人体模特:左(棕色衬衫、红色裤子,box 中心 0.38W)、中(牛仔夹克配碎花裙)、右(针织上衣、牛仔短裤 = U1)。U2 mask 是左侧模特的棕色衬衫,但 REF/ZH 说的是“the middle mannequin”(中间模特);physical_parent_zh 本身写的是 左模特。 | Ref: Replace the brown shirt on the leftmost mannequin with a navy linen blazer.<br>ZH:将最左侧模特的棕色衬衫替换为一件藏蓝色亚麻西装外套。 | 目视 |

#### `v2-sa_5074342`（#722，扩充 #200–#868，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+point | Add a small wooden birdhouse on the tree trunk immediately left of the thickest trunk. | 被 mask 的树干（box [725,751,797,1188]）是最粗树干（x~950-1050）左侧的第二根树干；另一根树干（x~795-860）正好位于二者之间。因此 "the tree trunk immediately left of the thickest trunk" 指的是 x~795-860 的树干，而不是被 mask 的这根。 | Ref: Add a small wooden birdhouse on the second tree trunk to the left of the thickest trunk.<br>或将 mask/指向移到 x~795-860 的树干 | 目视 |
| U4 | 严重 | replace 实为属性修改 | noref+point | Replace the small triangular tiled roof behind the nearest brick house with a dark gray slate roof. | 将小三角形瓦屋顶替换为“a dark gray slate roof”保持相同的屋顶形状/结构，仅改变材质/颜色。 | Ref: Change the material of the small triangular tiled roof behind the nearest brick house to dark gray slate.<br>No-ref: Change the material of the selected roof to dark gray slate.<br>将 op 改为 attribute（material） | 目视 |

#### `v2-sa_538938`（#746，扩充 #200–#868，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | ref+none | Add a small white POOL RULES plaque on the blue curved fence panel just right of the entrance gate. | 入口大门是 x~740-880（显示坐标）处笔直的蓝色大门。紧挨其右侧的围栏板是 x~880-1250 处的大弧形板。U1 mask（原图 box 1635-1823，显示坐标约 x 1250-1395）是再往右的下一块较小的弧形板，因此 REF 指的是与 mask 不同的板。 | Ref: Add a small white POOL RULES plaque on the second blue curved fence panel to the right of the entrance gate.<br>或将 mask 改为紧邻大门的那块板 | 目视 |
| U2 | 轻微 | 指代歧义 | ref+mask | Change the color of the three-light streetlamp immediately left of the central arched doorway to bronze. | 露台上排列着许多相同的三头路灯。被 mask 的那盏正好立在深色圆顶圆形大厅前,而“immediately left of the central arched doorway”很难从图像中核实。 | Ref: Change the color of the three-light streetlamp standing in front of the dark domed rotunda to bronze. | 目视 |

#### `v2-sa_5405364`（#750，扩充 #200–#868，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 措辞/文法/描述细节 | ref+none | Replace the conical potted evergreen beside the flagpoles with a small olive tree. | 锥形常青树（box [893,1752,980,2033]）看起来是种在矮墙旁的地里，根部另有一个单独的小花盆；'potted' 值得商榷。 | Ref: Replace the conical evergreen beside the flagpoles with a small olive tree. | 目视 |
| U4 | 阻断 | 方位/序数/实例指代错误 | ref+point | Add a small planter of red flowers on the nearest balcony railing at the upper left. | REF 说 'the nearest balcony railing at the upper left'，但 U4 mask（box [643,918,779,1112]，中心 0.47W,0.44H）是立面远端、靠近图像中部树木的一个小阳台。最近的阳台是图像左边缘（x<300）较大的那些。REF 选的是另一个实例。 | Ref: Add a small planter of red flowers on the farthest visible balcony railing of the building, at the end of the facade near the trees.<br>ZH: 在楼房立面末端靠近树木的最远处阳台栏杆加上一个种有红花的小花箱。 | 目视 |

#### `v2-sa_626400`（#831，扩充 #200–#868，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Change the color of the turquoise T-shirt on the woman at the right to coral pink. | REF/ZH 称 'the turquoise T-shirt on the woman at the right'（右侧女子），但被 mask 的青绿色T恤（box [2095,712,2184,818]）是由一位短发、戴墨镜的壮实男子穿着；他旁边的长发者是穿着不同上衣的女子。REF 描述了一个不匹配的人。 | Ref: Change the color of the turquoise T-shirt on the man in sunglasses at the right edge to coral pink.<br>ZH: 将右侧戴墨镜男子的青绿色T恤的颜色改为珊瑚粉色。 physical_parent_zh -> 右侧男子 | 目视 |
| U3 | 严重 | replace 实为属性修改 | ref+none | Replace the large American flag above the cable car with a plain dark blue flag. | U3 把美国国旗(box [1387,220,1518,406])替换为“a plain dark blue flag”——同一物体类别(旗帜),仅颜色/图案变化。 | Ref: Replace the large American flag above the cable car with a hanging round lantern.<br>No-ref: Replace the selected flag with a hanging round lantern.<br>或转换为 attribute:将旗帜的图案改为纯深蓝色。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+mask | Add a small white accessibility decal in its upper corner on the left front window of the cable car. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small white accessibility decal in the upper corner of the left front window of the cable car.<br>No-ref: Add a small white accessibility decal in the upper corner of the selected window. | 文本 |

#### `v2-sa_6283149`（#836，扩充 #200–#868，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 指代类别与 mask 不符 | ref+point | Change the color of the green trim of the foreground wooden boat to navy blue. | REF/NOREF 的目标是 'the green trim of the foreground wooden boat'，但 U1 mask（box 0-1390 x 50-2000，面积 0.36）覆盖了整个船体和船头结构：白色木板、红条纹、'Barche' 字样、彩绘装饰板和红色系缆桩；存储的点落在白色船头板上，而非绿色饰边。将选中区域改成藏青色会重涂整个船体。 | Ref: Change the color of the hull of the foreground wooden boat to navy blue.<br>No-ref: Change the color of the selected boat to navy blue.<br>要么把 scope 改为船体，要么只对绿色舷缘/饰边条重新做 mask，并把点移到绿色上。 | 目视 |

#### `v2-sa_6534458`（#853，扩充 #200–#868，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | ref+box | Remove the white flowers on the upper-left windowsill. | REF 称 'the white flowers on the upper-left windowsill'，但 U1 mask（box [86,1755,288,1873]，cy=0.80H）是左下方、'PENSIONE WILDNER' 字样正上方的花箱。左侧更高的花箱（例如约 0.18W,0.36H 和约 0.20W,0.24H）更符合 'upper-left'。 | Ref: Remove the white flowers on the lower-left windowsill just above the PENSIONE WILDNER lettering.<br>ZH: 移除PENSIONE WILDNER字样左上方、左下侧窗台上的白花。 | 目视 |
| U2 | 严重 | 指代歧义 | noref+mask | Replace the white flowers on the upper-right windowsill with a cluster of purple geraniums. | “the white flowers on the upper-right windowsill”：被 mask 的花箱（box [879,707,1078,829]，0.65W）位于中心偏右的顶层，但另一个顶层花箱在更靠右处（~0.88W, 0.30H），更符合“upper-right”。 | Ref: Replace the white flowers under the top-floor window just right of the closed green shutter with a cluster of purple geraniums. | 目视 |

#### `v2-sa_6665557`（#863，扩充 #200–#868，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | noref+box | Remove the stack of chairs below the leftmost large arched window. | U1 mask 是台阶最右侧的一小摞塑料椅（cx=0.93W, cy=0.83H），位于最右侧窗户/拱门下方；REF 说 'below the leftmost large arched window'（该窗户即 U2，位于 0.46W）。另外台阶上排列着许多相同的椅子堆，因此 REF 无法唯一指向这一摞。 | Ref: Remove the rightmost stack of chairs at the top of the steps on the right.<br>ZH: 移除右侧台阶顶部最右边的一摞椅子。 | 目视 |
| U2 | 严重 | 指代歧义 | ref+point | Change the color of the frame of the leftmost large arched window to dark bronze. | “the leftmost large arched window”——立面左侧开间更靠左处(约 0.18W,0.45H)还有一个更大的亮灯拱形窗;U2 是中央柱子之间最靠左的拱形窗(0.46W)。此外 mask 覆盖了整个窗户(玻璃和窗棂),而不仅是窗框。 | Ref: Change the color of the frame of the leftmost arched window between the central columns to dark bronze.<br>mask 覆盖整个窗户;要么将 mask 限制在窗框,要么改称“window frame and mullions” | 目视 |
| U3 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a small blue EXIT arrow sign near its center on the long white barrier in the foreground. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small blue EXIT arrow sign near the center of the long white barrier in the foreground.<br>No-ref: Add a small blue EXIT arrow sign near the center of the selected barrier. | 文本 |

#### `v2-sa_6769026`（#875，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 属性值问题（无变化/含糊） | noref+point | Change the finish of the double streetlamp at the right to matte black. | 双头路灯本来就被涂成黑色/深炭灰色。把其表面处理改为“matte black”几乎没有可见变化,因此该编辑难以评判。 | Ref: Change the color of the double streetlamp at the right to dark green.<br>No-ref: Change the color of the selected streetlamp to dark green.<br>或使用材质变化,如“polished brass”。 | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Remove the wooden bench beside the right planter. | 右侧有两条相同的木长椅。被 mask 的一条（2000 宽中的 x 1263-1402，~0.67W）站在 WOK TO WALK 售货亭前。第二条长椅（~0.72-0.80W）紧靠右侧砖砌花槽。因此 'The wooden bench beside the right planter' 指向的是另一条长椅。 | Ref: Remove the wooden bench in front of the WOK TO WALK kiosk, the left one of the two benches on the right. | 目视 |
| U4 | 严重 | 编辑不合理/不可执行 | ref+none | Add a small blue cushion on its seat on the wheelchair in the center walkway. | 轮椅上有人：一名穿深色背心的男子坐在里面，背对镜头。“Add a small blue cushion on its seat”针对的座位被人完全遮住，因此该编辑无法自然放置或验证。 | Ref: Add a small blue flag on a thin pole attached to the back of the wheelchair on the walkway at the left.<br>No-ref: Add a small blue flag on a thin pole attached to the back of the selected wheelchair. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+none | Add a small blue cushion on its seat on the wheelchair in the center walkway. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small blue cushion on the seat of the wheelchair in the center walkway.<br>No-ref: Add a small blue cushion on the seat of the selected wheelchair. | 文本 |

#### `v2-sa_6776835`（#877，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | ref+box | Remove the front landing wheel of the helicopter. | 直升机机头朝左;前(机头)起落轮位于驾驶舱下方 x~0.23W 处。mask/box [1218,993,1351,1120] 是燃油箱下方近侧的后主起落架轮。 | Ref: Remove the near-side main landing wheel under the helicopter's fuel tank.<br>或将 mask 移到机头轮上。 | 目视 |

#### `v2-sa_6779549`（#878，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+mask | Change the color of the window on the right-hand building to dark green. | 被 mask 的窗户 [759,447,833,571]（cx=0.35）位于街道左侧，在深色前景立面之外的奶油色建筑上（上层，'SOLICIT...' 檐口下方）。'the window on the right-hand building' 与此矛盾，且右侧建筑有几十扇窗，因此 REF 无法识别目标。 | Ref: Change the color of the window frame of the upper-floor window on the cream corner building on the left side of the street, just below its curved cornice, to dark green.<br>No-ref: Change the color of the window frame of the selected window to dark green.<br>同时需说明改变颜色的是哪一部分（窗框还是玻璃）。 | 目视 |
| U3 | 轻微 | 中文翻译不一致 | noref+box | Add a thin yellow edge line on the curb along the right side in the foreground. | physical_parent_zh 是“左路缘”（left curb），但被 mask 的路缘 [1631,1145,2177,1500] 位于前景右侧，与英文/ZH 指令（“右侧”）一致。 | 将 physical_parent_zh 设为 右侧路缘。 | 目视 |

#### `v2-sa_6791309`（#879，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 方位/序数/实例指代错误 | ref+point | Remove the large white woven sack in the foreground. | U1 mask(box [1104,493,1293,702])是高脚屋下中景处带绿色条纹的直立白色编织袋;真正的前景(右下,~y>900)有一个更大的白色编织袋/布,而且另一个白袋就立在 U1 旁边,所以 'in the foreground' 有误导性。 | Ref: Remove the upright white woven sack with a green stripe in the middle of the scene.<br>ZH: 移除画面中部带绿色条纹的直立白色编织袋。 | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+box | Replace the dark garment hanging at the upper right with a pale blue shirt. | U3 mask（box [421,0,567,143], cx=0.22）是挂在图像左上方、绿色房屋前木柱旁的晾晒衣物；REF/ZH 写的是 'upper right'（右上方），指向图像相反的一侧，而那里没有被 mask 的悬挂衣物。 | Ref: Replace the dark garment hanging at the top left beside the wooden post with a pale blue shirt.<br>ZH: 将左上方木柱旁晾挂的深色衣物替换为一件浅蓝色衬衫。 | 目视 |
| U3 | 严重 | mask 质量 | ref+box | Replace the dark garment hanging at the upper right with a pale blue shirt. | U3 mask 同时覆盖了挂在一起的深红色衣物和深灰/黑色衣物（带黑色袖口的红布加一只单独的深色袖子），因此并不明确是单一的 'dark garment'。 | 将 mask 限制为一件悬挂的衣物（例如深灰色那件），或描述为 'the red-and-black hanging garments' | 目视 |

#### `v2-sa_679629`（#880，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+none | Change the color of the light blue coat on the woman near the left to burgundy. | REF 说“the woman near the left”(ZH 左侧附近女子),但被 mask 的浅蓝色牛仔夹克属于 box x 1298-1420(中心 0.60W)处走远的女子,即人群中图像中心偏右的位置;左侧还有许多其他行人。REF 与 mask 位置矛盾。该衣物也是牛仔夹克而不是大衣。 | Ref: Change the color of the light blue denim jacket on the woman walking away in the middle of the crowd to burgundy.<br>No-ref: Change the color of the selected jacket to burgundy.<br>相应修正 ZH 中的方位词 | 目视 |
| U3 | 严重 | replace 实为属性修改 | ref+mask | Replace the gray padded coat on the man at the right with a dark green parka. | 右侧站立者（0.83W）身上被 mask 的衣物是带毛边兜帽的橄榄绿/卡其绿派克大衣，不是 'gray padded coat'。将其替换为 'a dark green parka' 得到的基本是同一件衣物，因此编辑几乎无变化/仅轻微改色。 | Ref: Replace the olive-green parka with a fur-trimmed hood on the person standing at the right with a red wool duffle coat.<br>No-ref: Replace the selected coat with a red wool duffle coat. | 目视 |

#### `v2-sa_6823812`（#882，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the plaid shirt on the person near the center with a plain black shirt. | U2 mask 的是深红/海军蓝格子衬衫;将其替换为 'a plain black shirt' 保持服装类别,只去掉图案并改变颜色。 | Ref: Replace the plaid shirt on the person near the center with a gray zip-up hoodie.<br>No-ref: Replace the selected shirt with a gray zip-up hoodie.<br>Or convert to attribute: 'Change the color of the plaid shirt on the person near the center to black.' | 目视 |
| U4 | 阻断 | 指代类别与 mask 不符 | ref+point | Add a small gold star sticker on the Christmas banner above the center stall. | U4 mask（box 1491-1565 x, 694-760 y）是挂在艺术摊位前上方的一幅小方形画作（带人物的橙/黄色日落场景）。它不是圣诞横幅；唯一的圣诞文字（'HAVE A HAPPY AND SAFE CHRISTMAS'）是右侧救生员塔上的一块牌子。 | Ref: Add a small gold star sticker on the small sunset painting hanging at the top of the art stall in the center.<br>No-ref: Add a small gold star sticker on the selected painting.<br>将 scope/类别从 banner 改为 painting。 | 目视 |

#### `v2-sa_6850445`（#886，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+point | Replace the small woven basket at the right of the doorway with a pale blue basket. | REF/ZH 把小编篮放在 '门口右侧'（at the right of the doorway）。被 mask 的篮子（box [613,966,1003,1385]）实际上站在门口的 LEFT 侧（门口在源图中约占 x=1000-1750），并在大编篮的右侧。门口右边没有任何匹配的东西，因此该描述与 mask 矛盾。 | Ref: Replace the small woven basket to the left of the doorway, beside the large basket, with a round plastic laundry basket.<br>No-ref: Replace the selected basket with a round plastic laundry basket.<br>ZH: 将门口左侧、大编篮旁的小编篮替换为一个圆形塑料洗衣篮。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the small woven basket at the right of the doorway with a pale blue basket. | Payload 'a pale blue basket' 保持篮子类别，没有结构变化，因此这是一个被标为 replace 的改色。 | 使用结构不同的 payload（例如上文所述的圆形塑料洗衣篮），或转为属性 'Change the color of ... to pale blue.' | 目视 |

#### `v2-sa_6888719`（#890，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+box | Change the color of the fishing boat near the center-left to navy blue. | U2 mask 是最左边缘被部分截断的船(box x=0-346 / 3587,cx=0.05),但 REF 说“the fishing boat near the center-left”。中心偏左的船是 U3 中被 mask 的那艘;U2 和 U3 的空间描述似乎对调了。 | Ref: Change the color of the partially visible fishing boat at the far left edge to navy blue.<br>ZH:将最左侧边缘露出一部分的渔船的颜色改为藏蓝色。 | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Replace the smaller fishing boat at the far left with a red-and-white boat. | U3 mask 是图像中间带高 A 形架的深色船体拖网渔船（box x=1522-2362, cx=0.54），但 REF 称 'the smaller fishing boat at the far left'。它既不在最左边，也并不明显更小。 | Ref: Replace the dark-hulled fishing boat with the tall A-frame in the center, left of the large white boat, with a red-and-white sailing yacht.<br>No-ref: Replace the selected boat with a red-and-white sailing yacht.<br>修正 ZH（中间的深色船体渔船） | 目视 |
| U3 | 严重 | replace 实为属性修改 | noref+mask | Replace the smaller fishing boat at the far left with a red-and-white boat. | 将渔船替换为“a red-and-white boat”保持类别，只指定了配色方案。 | 使用结构上不同的 payload，例如 'a red-and-white sailing yacht' | 目视 |
| U4 | 严重 | mask 质量 | ref+none | Add a small red warning marker on the stone breakwater behind the boats. | U4 mask(box 3464-3587 x 1001-1056,面积 0.0011)覆盖右边缘的单个石块,而 REF 指的是 'the stone breakwater behind the boats',它横跨 U1 后方的背景并延伸到右侧。 | Ref: Add a small red warning marker on the flat stone block of the breakwater at the far right edge.<br>or extend the mask to the visible breakwater | 目视 |

#### `v2-sa_6895502`（#891，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | ref+mask | Remove the patrol boat at the left horizon. | REF 是 'the patrol boat at the left horizon'，但 mask（box [1354,715,1590,798]，中心 x=0.60）是偏右的一艘带篷小木质客船；左侧地平线上类似巡逻艇的船是 x~0.15 处码头旁的大船。REF 指向了另一个实例。 | Ref: Remove the canopied wooden boat moored just right of center.<br>或保留 REF，并重新 mask 左侧码头旁的大船 | 目视 |
| U3 | 严重 | replace 实为属性修改 | ref+point | Replace the orange platform edge in the foreground with a dark wooden edge. | 被 mask 的物体是左下前景中粗糙的混凝土/石质站台边缘；'Replace ... with a dark wooden edge' 保持相同结构（边缘/壁架），仅改变材质/颜色。 | Ref: Change the material of the orange platform edge in the foreground to dark wood.<br>No-ref: Change the material of the selected ledge to dark wood.<br>转为属性 | 目视 |

#### `v2-sa_6896269`（#892，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 方位/序数/实例指代错误 | noref+point | Remove the rectangular hedge above the central storefront. | U1 绿篱(box [1441,805,1637,868],中心 0.77W)是右侧 Cheesecake Factory 店面上方的绿色绿篱板;真正的中心(约 0.57-0.68W)大屏幕下方有一块类似的矩形绿篱板。“above the central storefront”指向了错误的那个。 | Ref: Remove the rectangular hedge panel above the Cheesecake Factory storefront on the right.<br>ZH:移除右侧芝士蛋糕工厂店铺上方的矩形绿篱。 | 目视 |
| U2 | 阻断 | 指代类别与 mask 不符 | ref+box | Change the finish of the hanging speaker near the upper right to matte black. | U2 mask（box [1736,652,1801,753]）是挂在右上方白色桁架上的黑色摇头舞台灯（轭架式灯头），是并排的两个相同灯具之一；它不是音箱。 | Ref: Change the finish of the left of the two moving-head stage lights hanging from the white truss at the upper right to glossy silver.<br>No-ref: Change the finish of the selected stage light to glossy silver.<br>范围 speaker -> stage light；注意当前灯具已经是哑光黑色，因此值必须改变 | 目视 |
| U3 | 严重 | 方位/序数/实例指代错误 | noref+mask | Replace the floral dress on the seated woman at the right with a solid navy dress. | U3 坐着的女士（box [520,1406,585,1494]，中心 0.28W,0.97H）位于图像左下方，坐在喷泉边缘一位白衬衫男子的右边。“the seated woman at the right”与图像位置矛盾（仅相对于该男子才成立）。 | Ref: Replace the red patterned dress on the woman seated beside the man in a white shirt at the lower left with a navy blazer and trousers.<br>ZH 侧 右侧 -> 左下方 | 目视 |
| U3 | 严重 | replace 实为属性修改 | noref+mask | Replace the floral dress on the seated woman at the right with a solid navy dress. | U3 将碎花/图案连衣裙替换为 'a solid navy dress' —— 同一服装类型,只改变图案和颜色。 | Ref: Replace the floral dress on the woman seated beside the man in a white shirt at the lower left with a navy pantsuit.<br>No-ref: Replace the selected dress with a navy pantsuit.<br>or convert to attribute (color/pattern) | 目视 |

#### `v2-sa_6935352`（#894，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | mask 质量 | ref+box | Remove the red tram in the left background. | U1 电车 mask 在其左边缘的绿色站台栏杆上有一个杂散碎片(约 x 120-170 src,y 1000-1100)。 | 从 U1 mask 中移除杂散的栏杆碎片 | 目视 |
| U2 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Change the color of the silver tram at the right to dark blue. | U2 mask（box x 420-640, cx=0.27）是左中部的银色后车厢，位于红尾电车 1102 与杆子之间。占主导的 'silver tram at the right' 是大型前景电车 1108（显示图 x ~650-1330）；因此 REF 指向的物体与 mask 不同，且大得多。 | Ref: Change the color of the silver tram car just right of the red-backed tram in the left background to dark blue.<br>ZH: 左后方红尾电车右侧的银色电车车厢; 核实 U2 是独立电车还是电车 1108 连挂的后车厢 - 若是连挂，则重新绑定或删除 | 目视 |
| U3 | 严重 | replace 实为属性修改 | ref+none | Replace the patterned shirt on the passenger at the right with a plain yellow shirt. | U3 将右侧平台上女士的灰色花纹衬衫替换为“a plain yellow shirt”——相同衣物类型，仅颜色/图案变化。 | Ref: Replace the patterned shirt on the passenger at the right with a yellow hooded raincoat.<br>No-ref: Replace the selected shirt with a yellow hooded raincoat.<br>或转为 attribute：颜色 -> 黄色 | 目视 |

#### `v2-sa_6937647`（#895，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+box | Tint the large rectangular window on the upper facade warm amber. | 立面上层有多扇相同的大格栅矩形窗(顶排约在 ~0.48W、~0.64W、~0.86W,下方还有二层一排)。'The large rectangular window on the upper facade' 无法唯一指出 0.48W 处被 mask 的顶层窗。 | Ref: Tint the top-floor rectangular window directly above the 'Forge' patio sign warm amber. | 目视 |
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+point | Replace the patio umbrella at the left with a dark green umbrella. | REF 写 'the patio umbrella at the left'，但被 mask 的伞位于 x~0.54W（2250 中的 box 1017-1434），在露台中央。另一把黑色露台伞明显更靠左（~0.37W），因此仅用 ref 的模型会选错。 | Ref: Replace the black patio umbrella in the center of the patio, in front of the 'Forge' sign, with a large rectangular canvas sail shade.<br>No-ref: Replace the selected umbrella with a large rectangular canvas sail shade. | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the patio umbrella at the left with a dark green umbrella. | 被 mask 的物体是一把黑色庭院遮阳伞。'A dark green umbrella' 是同一物体类型，仅改变颜色。 | 使用结构不同的 payload（例如遮阳帆，见空间位置修正）或转为属性：'Change the color of the black patio umbrella in the center to dark green.' | 目视 |
| U3 | 严重 | mask 质量 | noref+point | Remove the EXIT sign above the patio. | 该 mask 有 2 个分量,覆盖两个独立的标志:最左侧停车库的“P Exit”标志和相邻的“Enter”标志(U3 放大图)。REF 只提到 EXIT 标志。这些标志也位于车库入口上方,而不是“above the patio”。 | Ref: Remove the EXIT sign above the parking garage entrance at the far left.<br>将 mask 仅限于“P Exit”标志(去掉“Enter”标志分量)。 | 目视 |
| U4 | 严重 | 指代歧义 | ref+box | Add a small red cushion on the chair beside the front table. | 露台上有许多相似的深色金属椅围着几张桌子。'The chair beside the front table' 无法识别被 mask 的小椅子（x~0.44W，部分被栏杆遮挡），且 mask 是粗糙、不完整的斑块。 | Ref: Add a small red cushion on the dark metal chair just left of the center umbrella pole, behind the patio railing.<br>考虑选择更可见、mask 更干净的椅子。 | 目视 |

#### `v2-sa_6943290`（#896，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+none | Replace the orange jacket on the spectator near the center with a navy raincoat. | REF 写的是“the spectator near the center”，但被 mask 的橙色夹克（box [1795,1056,1900,1224]，cx=0.82W）属于右侧人群中的一名观众；图像中心被花车占据。 | Ref: Replace the orange jacket on the spectator in the crowd at the right with a navy raincoat.<br>ZH: 将右侧人群中观众的橙色夹克替换为一件藏蓝色雨衣。 | 目视 |
| U3 | 阻断 | 指代类别与 mask 不符 | ref+mask | Remove the small price sign on the float. | REF:'the small price sign on the float',但 U3 mask(box [1970,832,2040,911])是固定在右侧建筑旁街灯杆上的印刷装卸限制/时间告示,不在花车上,也不是价格牌。 | Ref: Remove the small white notice sign on the street pole at the right.<br>No-ref: Remove the selected sign.<br>ZH: 移除右侧路灯杆上的白色小告示牌。 | 目视 |
| U4 | 严重 | 指代歧义 | noref+box | Add a small silver ribbon on the flower decoration on the float. | 'the flower decoration on the float' 适用于花车上的几十个花饰；mask（box [959,182,1103,250]）是最顶部发光环上的一朵浅色花。 | Ref: Add a small silver ribbon on the pale flower ornament on the highest lit ring at the top of the float. | 目视 |

#### `v2-sa_6977563`（#897，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+box | Remove the white shirt on the man near the center. | REF 'the man near the center'，但被 mask 的白衬衫（box 中心 0.91W）属于最右侧面包店门旁的灰发男子；有几位穿浅色衬衫的男子靠近中心。 | Ref: Remove the white shirt on the gray-haired man at the far right.<br>另见不适定的衣物移除问题。 | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | ref+box | Remove the white shirt on the man near the center. | 移除该男子所穿的白衬衫会留下不确定的裸露躯干。 | Ref: Change the color of the white shirt on the gray-haired man at the far right to light blue.<br>No-ref: Change the color of the selected shirt to light blue.<br>将操作改为 attribute 或 replace。 | 目视 |
| U4 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Add a small white stitched patch on the back pocket on the jeans on the man at the right. | REF 'jeans on the man at the right'，但被 mask 的浅蓝色牛仔裤（中心 0.39W）穿在中左侧人群中穿青绿色 T 恤的男子身上。 | Ref: Add a small white stitched patch on the back pocket of the light-blue jeans on the man in the teal T-shirt. | 目视 |

#### `v2-sa_7052077`（#901，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+point | Remove the covered boat in the foreground. | U1 是停靠在码头、盖着防水布的船（box 891-1156 x, 1231-1431 y），但底边的 U3 帆布顶船离镜头更近且同样被覆盖，因此 'the covered boat in the foreground' 有歧义。 | Ref: Remove the tarp-covered boat moored along the quay just right of the white-cabin boat. | 目视 |
| U2 | 严重 | 指代歧义 | ref+box | Change the color of the dark car parked at the left to red. | 左侧码头停着几辆深色车；x~0.05-0.21W 处较大的深色旅行车比被 mask 的深色轿车（box 668-857 x）更靠左。'the dark car parked at the left' 两者都适用。mask 的左边缘还包住了粉色自行车筐。 | Ref: Change the color of the dark sedan parked behind the bicycles near the quay edge, right of the dark station wagon, to red.<br>从车辆 mask 中去掉粉色自行车筐。 | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Replace the covered boat near the center with a blue canal boat. | U3 mask(box 714-934 x,1390-1500 y)是被图像底边截断的白色帆布顶船,是离镜头最近的船。“the covered boat near the center”更符合 U1 的防水布覆盖船(中心约 0.45W,0.89H);由于两者都是有覆盖的船,REF 指向了错误的实例。 | Ref: Replace the white-cabin boat cut off at the bottom edge with a blue canal boat. | 目视 |

#### `v2-sa_7116219`（#902，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 方位/序数/实例指代错误 | noref+box | Replace the pink skirt on the person at the left with a deep blue skirt. | REF 称 'the person at the left'，但被 mask 的粉色裙子（带条纹腰带）穿在最右侧人群中的一个女孩身上（box x 1824-1970, cx=0.84）。左侧有其他穿粉色的人（例如 x~0.05W 处穿粉色服装的孩子），因此 REF 指向了错误的一侧/实例。 | Ref: Replace the pink skirt of the girl in the crowd at the right, next to the child in the Batman T-shirt, with a pair of dark blue cropped trousers.<br>No-ref: Replace the selected skirt with a pair of dark blue cropped trousers.<br>ZH: 将右侧人群中、穿蝙蝠侠T恤孩子旁边女孩的粉色裙子替换为一条深蓝色七分裤。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the pink skirt on the person at the left with a deep blue skirt. | 用“a deep blue skirt”替换粉色裙子是对同一衣物的纯颜色变化。 | 使用结构上不同的 payload（例如裤子），或改为 attribute 颜色编辑 | 目视 |
| U3 | 阻断 | mask 质量 | ref+point | Remove the orange costume on the person at the right. | U3 mask(box x 1284-1468, y 460-980, comps=2)勾勒了两个完整的人 —— 穿橙色长袍、拿粉色布的成人,以及站在他前面、穿橙色束腰衣、背着单肩包的男孩 —— 包括头部,而不是单一的服装。REF 'the person at the right' 也不精确(cx=0.61;更右侧还有许多人)。 | Ref: Change the color of the orange tunic and trousers of the boy with the small shoulder bag to light blue.<br>re-cut mask to one garment of one person (e.g. the boy's orange tunic) and change op away from remove | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | ref+point | Remove the orange costume on the person at the right. | 移除整件橙色服装（长袍/套装，人们的主要衣物）会留下未定义的身体。 | 使用 attribute 或 replace，而不是 remove | 目视 |
| U4 | 阻断 | 指代类别与 mask 不符 | noref+point | Add a small white emblem on the vertical flag behind the performer. | REF 的目标是 'the vertical flag behind the performer'，但 U4 mask（box x 2078-2153, y 549-599）是右侧人群中一个孩子头上的小浅粉色帽子。唯一的竖旗（泰国国旗）在左上角粉丝身后（x~0.13W）。 | Ref: Add a small white flower on the pale pink cap of the child at the far right of the crowd.<br>No-ref: Add a small white flower on the selected cap.<br>要么保留 mask 并把 scope 改为 'cap'，要么对左上角的竖向泰国国旗重新做 mask | 目视 |

#### `v2-sa_7125342`（#903，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+none | Replace the black car parked at the right with a white compact car. | REF 说“the black car parked at the right”,但被 mask 的汽车(box x438-704,cx=0.25W)停在街道左侧、左边踏板车旁;右侧没有黑色汽车(右侧是踏板车 U1)。ZH 也写作 右侧。 | Ref: Replace the black car parked on the left side of the street with a white compact car.<br>ZH:将街道左侧停放的黑色轿车替换为... | 目视 |
| U3 | 严重 | replace 实为属性修改 | ref+none | Replace the black car parked at the right with a white compact car. | 把黑色汽车替换为 'a white compact car' 本质上是同一类别的改色。 | Ref: Replace the black car parked on the left side of the street with a white delivery van.<br>No-ref: Replace the selected car with a white delivery van. | 目视 |

#### `v2-sa_7191982`（#906，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 指代类别与 mask 不符 | noref+box | Remove the no-parking sign near the entrance. | REF 说 'the no-parking sign near the entrance'，但 U2 mask（box [604,671,703,728]）是主入口左侧杆子上带文字（'Dojazd do ulicy Swietokrzyskiej...'）的黄色矩形指示牌。真正的禁停标志是右侧灯杆上的 U4 mask。 | Ref: Remove the yellow information sign near the entrance.<br>同时修正 ZH 和 physical_parent（黄色指示牌） | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+point | Replace the tan jacket on the pedestrian at the right with a dark blue coat. | REF 说“the pedestrian at the right”,但 U3 mask 是场景中左偏中位置一名戴黑帽老年男子的棕褐色/驼色夹克(box [531,870,622,954],cx=0.26),他旁边是一位穿粉色外套的女子。更靠右还有数名行人。 | Ref: Replace the tan jacket on the older man in a black cap walking at the left of the entrance with a dark blue coat.<br>将棕褐色夹克替换为深蓝色大衣也接近于重新着色;考虑使用差异更明显的衣物,例如“a red puffer vest” | 目视 |
| U4 | 阻断 | 指代类别与 mask 不符 | noref+point | Add a small roof sign on the white car at the left curb. | REF 称 'the white car at the left curb'，但 U4 mask（box [1538,629,1612,710]）是安装在右侧 U1 灯杆上的红蓝圆形禁停标志。白色汽车在最左边（x 约 0-0.14），未被 mask。该标志还附着在 U1 路灯上，因此并不独立于 U1。 | Ref: Remove the round no-parking sign on the streetlamp at the right.<br>No-ref: Remove the selected sign.<br>要么把 U4 重新 mask 到最左边的白色汽车（保留 add roof sign 编辑），要么把文本改为该标志；若保留标志，请注明对 U1 灯杆的依赖 | 目视 |

#### `v2-sa_7205265`（#907，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | noref+mask | Remove the tire behind the fire bowl. | 左侧火盆后面叠放着两只轮胎；U2 mask 只是上面那只，但 REF 只说“the tire behind the fire bowl”。 | Ref: Remove the upper tire of the two stacked tires behind the fire bowl.<br>更新 ZH: 移除火盆后方两只叠放轮胎中上面的那只。 | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+none | Replace the window on the building at the upper right with a bright blue window. | U3 mask 是图像左上方白色建筑的上层窗洞(box [0,90,189,331],cx=0.06);REF 却写 'the building at the upper right'。正式输入为 ref-only(ref+none),所以 REF 指向了图像错误的一侧。 | Ref: Replace the upper window on the white building at the upper left with an arched stained-glass window.<br>No-ref: Replace the selected window with an arched stained-glass window.<br>update ZH (左上方) | 目视 |
| U3 | 严重 | replace 实为属性修改 | ref+none | Replace the window on the building at the upper right with a bright blue window. | 'Replace the window with a bright blue window' 保持类别不变，只改变颜色。 | Ref: Replace the upper window on the white building at the upper left with an arched stained-glass window.<br>No-ref: Replace the selected window with an arched stained-glass window. | 目视 |
| U4 | 阻断 | 指代类别与 mask 不符 | ref+mask | Add a small warning sign on the red truck panel at the far right. | U4 mask 是最右边缘的一根带红色底座的细竖直白/灰色立柱（box [1465,131,1500,948]）；REF 说 'the red truck panel at the far right'，而类别/NOREF 说的是 'post'。REF 点名了错误的物体（红色卡车是立柱左边的另一个物体）。 | Ref: Add a small warning sign on the thin metal post at the far right edge.<br>No-ref: Add a small warning sign on the selected post.<br>更新 ZH：在最右侧边缘的细金属立柱加上一个小警示牌。 | 目视 |

#### `v2-sa_720948`（#908，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 人物/服装层级错误 | noref+box | Change the color of the red coat on the woman to deep purple. | U1“red coat”mask 基本覆盖了整个女子:红色头巾和模糊的脸直至下摆(仅排除了黑色手提包),而不只是大衣。 | 将 mask 限制在深红色长大衣上(排除头巾、脸、手) | 目视 |
| U2 | 严重 | 指代歧义 | ref+point | Remove the white car on the road. | 背景道路上有多辆白色汽车（被 mask 的一辆在左侧建筑附近约 x=345-430，另有约 x=510-560、575-615、635-665 的）。'the white car on the road' 无法识别 U2。 | Ref: Remove the white car on the left side of the road in the distance, nearest the shopfronts. | 目视 |
| U3 | 严重 | replace 实为属性修改 | noref+point | Replace the gray canopy across the top with a blue striped canopy. | U3 将灰色遮阳篷替换为“a blue striped canopy”——同一物体，仅颜色/图案变化。ZH 还额外加了“white”（蓝白条纹），EN 中没有。 | Ref: Change the color of the gray canopy across the top to blue.<br>No-ref: Change the color of the selected canopy to blue.<br>op replace->attribute，或替换为结构上不同的物体（例如 'a wooden pergola'） | 目视 |
| U4 | 阻断 | 方位/序数/实例指代错误 | ref+box | Add a warm yellow glow on the window on the building at the left. | U4 窗户位于图像右上方的灰色建筑上(2250 宽中 box x=1796-1851,cx=0.81),但 REF 写的是 'the building at the left'。此外 payload 'a warm yellow glow' 是光照效果,不是具体物体。 | Ref: Add a small potted plant on the windowsill of the window on the gray building at the upper right.<br>No-ref: Add a small potted plant on the windowsill of the selected window.<br>fix ZH (右上方建筑) | 目视 |

#### `v2-sa_7229007`（#909，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Change the color of the front wheel of the tuk-tuk to white. | REF 是 'the front wheel of the tuk-tuk'，但嘟嘟车朝左（摩托车前叉和前轮在 x~0.41W）；被 mask 的车轮（box [1288,1302,1415,1430], x=0.68W）是乘客舱下方的后轮。 | Ref: Change the color of the rear right wheel of the tuk-tuk to white. | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the plaid shirt on the pedestrian with a plain blue shirt. | 被 mask 的物体是右侧行走男子的短袖格子衬衫；替换为 'a plain blue shirt' 保持衣物类型，仅图案/颜色改变。 | Ref: Change the pattern of the plaid shirt on the pedestrian walking behind the tuk-tuk to plain blue.<br>No-ref: Change the pattern of the selected shirt to plain blue.<br>转为属性 | 目视 |

#### `v2-sa_7231402`（#910，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+box | Replace the beige shirt on the student just right of center with a blue shirt. | U1 把“the beige shirt”替换为“a blue shirt”——仅颜色变化。 | Ref: Replace the beige shirt on the student just right of center with a blue hooded sweatshirt.<br>No-ref: Replace the selected shirt with a blue hooded sweatshirt.<br>或转换为 attribute:将颜色改为蓝色 | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | ref+point | Change the color of the child seated behind the foreground student to a red shirt. | U2 mask（box [1788,950,2104,1500]）是整个坐着的孩子（头加身体）；REF 'Change the color of the child ... to a red shirt' 对人物应用了颜色属性，并把物体短语用作值。 | Ref: Change the color of the beige uniform shirt of the child seated behind the foreground student to red.<br>No-ref: Change the color of the selected shirt to red.<br>重新 mask 到孩子的米色衬衫上；范围 child -> shirt | 目视 |

#### `v2-sa_7237977`（#911，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+box | Replace the white entrance door on the left with a dark green door. | U1“Replace the white entrance door on the left with a dark green door”保持相同的镶板门，仅改变其颜色。 | Ref: Replace the white entrance door on the left with a dark wooden plank door with iron hinges.<br>No-ref: Replace the selected door with a dark wooden plank door with iron hinges.<br>或转为 attribute：颜色 -> 深绿色 | 目视 |
| U2 | 严重 | 指代歧义 | noref+mask | Change the color of the flower box beside the storefront to white. | 广场上店面旁至少有三个深色花箱(中间约 x 820-930 显示坐标,右侧约 x 1080-1190,以及底部中间 x 890-1080 种紫花的 U2 那个)。'the flower box beside the storefront' 三个都符合。 | Ref: Change the color of the flower box with purple flowers at the bottom center to white.<br>ZH: 将画面底部中间种紫色花的花箱改为白色。 | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+none | Remove the small sign above the storefront. | U3 mask（box 953-989, 1191-1282）是立在青绿色楼房一层拱形窗内、窗户高度处的一张小咖啡馆菜单海报——不是 '店面上方' 的标牌（店面上方的标牌例如红色的 'wüstenrot' 标牌）。 | Ref: Remove the small café menu poster in the arched window of the teal building.<br>ZH: 移除青绿色楼房拱形橱窗里的小咖啡菜单海报。 | 目视 |
| U4 | 阻断 | 指代类别与 mask 不符 | ref+mask | Add a warm yellow glow on the wall lamp above the shop. | U4 mask（box 1108-1145, 1103-1272）是咖啡馆露台旁杆子上的独立灯笼式路灯，而不是 'wall lamp above the shop'。 | Ref: Add a small hanging flower basket on the post of the lantern street lamp by the café terrace.<br>No-ref: Add a small hanging flower basket on the post of the selected street lamp.<br>scope -> street lamp | 目视 |
| U4 | 严重 | 编辑不合理/不可执行 | ref+mask | Add a warm yellow glow on the wall lamp above the shop. | Payload “a warm yellow glow”是一种光照效果,而不是具体物体;add 需要附着在宿主上的实物。 | 使用具体的 payload(例如悬挂花篮),或转换为 attribute“turn the lamp on” | 目视 |

#### `v2-sa_7247537`（#913，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 方位/序数/实例指代错误 | noref+mask | Replace the chalkboard menu at the lower left with a red menu board. | REF 写 'the chalkboard menu at the lower left'，但被 mask 的 A 字形黑板（box [1078,1352,1174,1493], cx=0.56W）位于底部中央、自行车旁；其他黑板标牌沿酒吧更靠左（合成图中约 x 450-520）。 | Ref: Replace the chalkboard A-frame menu next to the bicycle in front of The Bankers pub with a red menu board. | 目视 |
| U1 | 严重 | replace 实为属性修改 | noref+mask | Replace the chalkboard menu at the lower left with a red menu board. | 将黑板菜单牌替换为 'a red menu board' 保持相同物体类别（菜单牌）；仅颜色/材质改变。 | Ref: Replace the chalkboard A-frame menu next to the bicycle with a potted bay tree.<br>No-ref: Replace the selected menu board with a potted bay tree. | 目视 |
| U2 | 严重 | 指代歧义 | ref+none | Tint the tall window on the stone building warm amber. | “the tall window on the stone building”适用于砂岩建筑上许多相同的高窗;mask(box [1549,653,1607,780])是二层一排中从左数第二扇窗。 | Ref: Tint the second window from the left on the upper floor of the sandstone building, above the balcony, warm amber. | 目视 |
| U3 | 阻断 | 指代类别与 mask 不符 | ref+mask | Remove the white SUV at the left. | REF：'Remove the white SUV at the left'，但 U3 mask（box [842,1277,936,1500]）覆盖的是站在酒吧入口、穿黑色外套的长发女子。那里没有白色 SUV；mask 和文本描述的是不同物体。 | 删除该单元或改写以匹配 mask，例如属性：'Change the color of the black coat of the long-haired woman at the pub entrance to camel.'（此时 mask 需只含外套）。 | 目视 |
| U4 | 阻断 | 指代类别与 mask 不符 | noref+box | Add a hanging flower basket on the streetlamp beside the red pub. | REF：“Add a hanging flower basket on the streetlamp beside the red pub”，但 U4 mask（box [1068,989,1118,1061]）是安装在红色立面上的圆形 O'Hara's pub 招牌，不是路灯。 | Ref: Add a small hanging flower basket below the round O'Hara's sign on the red pub facade.<br>No-ref: Add a small hanging flower basket below the selected sign.<br>scope -> sign | 目视 |

#### `v2-sa_725238`（#914，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+point | Replace the green T-shirt on the person in front with a white T-shirt. | 将深绿色 T 恤替换为 'a white T-shirt' 纯属改色。 | Ref: Change the color of the dark green T-shirt on the man walking toward the camera in the center to white.<br>No-ref: Change the color of the selected T-shirt to white.<br>Change op to attribute. | 目视 |
| U1 | 严重 | 指代歧义 | ref+point | Replace the green T-shirt on the person in front with a white T-shirt. | 在密集人群中 'the person in front' 有歧义；左前景坐着两位穿亮绿色 polo 衫的男子。Mask 是底部中央（0.53W）朝镜头走来的男子的深绿色 T 恤。 | Ref: ... the dark green T-shirt on the man walking toward the camera at the bottom center ... | 目视 |
| U2 | 严重 | 指代歧义 | noref+point | Tint the lit window on the right building deep blue. | 'the lit window on the right building' ——右侧黄色建筑有几扇相似的橙框窗户；被 mask 的那扇（右上，box [1947,184,2174,475]）并非唯一亮灯的。 | Ref: Tint the topmost window on the yellow building at the upper right deep blue. | 目视 |
| U3 | 阻断 | 指代类别与 mask 不符 | ref+box | Remove the blue Sunshine sign. | REF 称“the blue Sunshine sign”,但被 mask 的青绿色标牌写的是“Krungthai Bank”(泰文 + KRUNGTHAI BANK);看不到“Sunshine”文字,因此 ref-only 描述无法解析。 | Ref: Remove the teal Krungthai Bank sign hanging over the street.<br>相应修正 ZH。 | 目视 |
| U4 | 严重 | 指代歧义 | noref+mask | Add a red seat cushion on the white chair at the lower left. | 'the white chair at the lower left' —— 左下就餐区摆满了白色塑料椅；被 mask 的椅子位于 x~0.28W 底边、食客之间（physical_parent_zh 甚至写的是 右下）。 | Ref: Add a red seat cushion on the empty white plastic chair beside the man in the green polo at the bottom left.<br>修正 physical_parent_zh。 | 目视 |

#### `v2-sa_7279175`（#916，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+point | Remove the pigeon in the foreground. | 地上有 15+ 只鸽子，有几只同样处于前景（视图中左边的鸽群约 x100-350,y850-990；右边一只约 x1425,y975）。'the pigeon in the foreground' 无法指向底部中央被 mask 的孤立鸽子 [982,1296,1082,1386]。 | Ref: Remove the lone pigeon on the ground at the bottom center, just below the man in the gray jacket. | 目视 |
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+box | Change the color of the white sneaker near the center to red. | 被 mask 的运动鞋 [1864,1286,1974,1338](cx=0.85)是最右侧行走者向前迈出的白色运动鞋,并不“near the center”。还有其他白色运动鞋(例如约 x0.78 处穿深色夹克的女子穿着白色运动鞋),因此 REF 指向了别处。 | Ref: Change the color of the white sneaker on the forward foot of the walking person at the far right to red.<br>ZH:将最右侧行走者前脚的白色运动鞋的颜色改为红色。 | 目视 |
| U3 | 严重 | replace 实为属性修改 | noref+mask | Replace the brown backpack on the woman at the right with a black backpack. | 被 mask 的物体是棕色皮革背包/斜挎包；载荷 'a black backpack' 是同一物体，只改变颜色。 | Ref: Replace the brown backpack on the woman at the right with a small woven straw tote bag.<br>No-ref: Replace the selected backpack with a small woven straw tote bag.<br>或改为属性 color=black。 | 目视 |
| U4 | 阻断 | 指代歧义 | ref+none | Add a small flower box on the shuttered window on the building. | 正式输入是 ref+none，所以 REF 是唯一的定位器，但“the shuttered window on the building”适用于议会大楼立面上约 40 个相同的带百叶窗的窗户。被 mask 的 [1489,519,1539,602] 位于右翼二层（上层），在中央门廊块右侧的第一个窗户。 | Ref: Add a small flower box under the upper-floor shuttered window just right of the central portico block of the building.<br>或将正式输入改为定位器（box/point/mask）。 | 目视 |

#### `v2-sa_7311948`（#918，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+box | Replace the wooden bench in the foreground with a dark green bench. | U1 mask 是前景的棕色木条长椅；payload 'a dark green bench' 仅改变颜色（同一类别，无结构变化）。 | Ref: Change the color of the wooden bench in the foreground to dark green.<br>No-ref: Change the color of the selected bench to dark green.<br>将 op 转为属性，或替换为结构不同的物体（例如 'a stone bench with a backrest'） | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+none | Change the pattern of the blue patio umbrella in the middle to yellow and white. | U3 mask(box [0,703,271,839],cx=0.06)是图像最左边缘的浅蓝色庭院遮阳伞;REF/ZH 称其为“the blue patio umbrella in the middle”(中间的蓝色遮阳伞),与其位置矛盾。 | Ref: Change the pattern of the blue patio umbrella at the far left to yellow and white.<br>ZH:将最左侧的蓝色遮阳伞的图案改为黄白相间。 | 目视 |
| U4 | 严重 | add 锚点不当 | ref+mask | Add a red seat cushion on the folding chair at the right tables. | U4 mask（box [1720,907,1787,1007]）是一把青绿色折叠椅，上面坐着穿灰色 T 恤的男子；mask 围绕他的身体呈碎片状，座面完全被遮住，因此 'Add a red seat cushion on the folding chair' 没有可见的座面可附着。 | 选择右侧桌子旁的空折叠椅作为锚点，或更改 op（例如 'Change the color of the folding chair ... to red'） | 目视 |

#### `v2-sa_7362739`（#921，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 方位/序数/实例指代错误 | noref+box | Change the color of the turquoise billboard at the left to orange. | REF 称 'the turquoise billboard at the left'，但被 mask 的 CHINTAI 广告牌位于上方中央（cx=0.49）；浅青色的大型 Glico 跑者广告牌占据图像左侧，因此 'at the left' 指向了错误的招牌。 | Ref: Change the color of the turquoise CHINTAI billboard at the top center to orange.<br>ZH: 将上方中央青绿色CHINTAI广告牌的颜色改为橙色。 | 目视 |
| U2 | 严重 | 编辑不合理/不可执行 | ref+point | Remove the purple tour boat in the center. | 游船上约有 40 名坐着的乘客，船 mask 将他们排除在外；“Remove the purple tour boat”会让乘客悬空（或必须一并移除，而这与 U3 编辑其中一名乘客冲突）。这艘船是大型结构（面积 0.115）。 | Ref: Change the color of the purple hull of the tour boat in the center to dark green.<br>No-ref: Change the color of the selected boat to dark green.<br>将 op 从 remove 改为 attribute，或删除该 unit | 目视 |
| U3 | 阻断 | 人物/服装层级错误 | noref+point | Replace the passenger seated near the right side of the boat with a yellow raincoat. | U3 mask 是一位完整的坐着的乘客(穿丁香色上衣和牛仔裤的年轻女子,box x 1198-1277);'Replace the passenger ... with a yellow raincoat' 是用一件衣服替换整个人。此外 'near the right side of the boat' 也不对:她坐在乘客区左/前端,紧靠驾驶舱后方,更右侧还有许多乘客。 | Ref: Change the color of the lilac top of the passenger sitting just behind the boat's cabin to yellow.<br>No-ref: Change the color of the selected top to yellow.<br>re-mask to the passenger's lilac top (garment level), or keep whole-person mask and use a person-level edit such as 'Replace the passenger sitting just behind the cabin with an empty seat' | 目视 |
| U4 | 轻微 | mask 质量 | ref+box | Add a small blue sign on the metal railing along the river. | 栏杆 mask 是一条长带，还包含了安装在上面的橙色救生圈以及部分步道边缘。 | 从栏杆 mask 中排除救生圈 | 目视 |

#### `v2-sa_7365220`（#922，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Replace the black information sign at the left with a red OPEN sign. | REF 'the black information sign at the left'，但被 mask 的牌子（深色 POE 铭牌，box x2003-2063，cx=0.90W）在图像最右侧，位于白色门左边的壁柱上。ZH 也写的是 左侧。 | Ref: Replace the small black POE plaque on the white pilaster at the right, beside the white door, with a red OPEN sign.<br>ZH: 将右侧白门旁白色壁柱上的黑色POE小铭牌替换为一块红色OPEN招牌。 | 目视 |
| U2 | 严重 | 指代歧义 | ref+none | Change the color of the gray jacket on the pedestrian to deep green. | “the pedestrian”——街上有很多行人;被 mask 的那位(x1389-1524)是走过白色店面的穿灰色羽绒服男子。“gray jacket”有帮助,但数名行人穿着深色/灰色外套。 | Ref: Change the color of the gray puffer jacket on the man walking past the white KNOW & LOVE shopfront to deep green. | 目视 |

#### `v2-sa_7381987`（#925，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+point | Change the color of the brown dye in the foreground vat to deep blue. | 前景有许多装着棕色染料的染缸。U1 mask 是右下角的椭圆形染缸（box [1829,1324,1988,1402]），但“the foreground vat”适用于图像底部的多个棕色染缸。 | Ref: Change the color of the brown dye in the oval vat at the bottom-right corner to deep blue. | 目视 |
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+box | Remove the hanging hide on the left. | REF 说 'the hanging hide on the left',但 U2 mask 是挂在最右边缘墙上的一张兽皮(box [2165,424,2245,567],cx=0.97)。其左侧还挂着许多其他兽皮。 | Ref: Remove the hide hanging alone on the wall at the far right edge. | 目视 |
| U3 | 严重 | replace 实为属性修改 | noref+mask | Replace the stone staircase in the center with a wooden staircase. | U3 mask 的是右中偏右（box [1597,555,1708,703], cx=0.73）处的一段狭窄石阶，位于两名男子和一堵墙之间。'A wooden staircase' 只改变材质。'In the center' 也不准确，因为楼梯在中心偏右，且其左侧紧邻另一段楼梯。 | Ref: Change the material of the narrow stone staircase right of center, beside the two standing men, to wood.<br>No-ref: Change the material of the selected staircase to wood.<br>将 op 改为 attribute | 目视 |
| U4 | 严重 | 指代歧义 | ref+none | Add a small red flag on the pale building in the distance. | U4 mask 是左上角一栋浅色多层建筑（box [193,172,835,850]）。背景中几乎每栋建筑都是浅色，所以 'the pale building in the distance' 无法唯一指向它。mask 底部还向下延伸到了大桶平台上。 | Ref: Add a small red flag on the pale building with a pink-tinted roof terrace at the upper left.<br>收紧 mask 底部以排除大桶 | 目视 |

#### `v2-sa_7420848`（#927，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+none | Remove the no-parking sign near the center. | U3 mask 是右侧人行道蓝色公寓楼前的 'NO PARKING THIS SIDE' 标志(cx=0.86),但 REF 写的是 'near the center'。图像中心附近(合成图约 x=945, y=385)还有另一块小白牌,所以 REF 可能指向错误的实例。 | Ref: Remove the 'NO PARKING THIS SIDE' sign on the right sidewalk in front of the blue apartment building.<br>ZH: 移除右侧人行道蓝色公寓楼前的禁停标志。 | 目视 |
| U4 | 阻断 | 编辑不合理/不可执行 | ref+mask | Add a yellow helmet on the cyclist on the road near the center. | 被 mask 的骑行者（cx=0.27，偏离中心靠左，并非 'near the center'）本来就戴着白/灰色头盔，因此 'Add a yellow helmet on the cyclist' 与现有头盔冲突；锚点是整个人加自行车，没有给出位置。 | Ref: Add a small red flag on a pole mounted on the rear of the bicycle of the cyclist approaching on the left side of the road.<br>No-ref: Add a small red flag on a pole mounted on the rear of the selected bicycle.<br>或改为属性编辑：Change the color of the helmet of the cyclist ... to yellow（使用头盔 mask） | 目视 |

#### `v2-sa_7448541`（#929，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 属性值问题（无变化/含糊） | noref+mask | Change the color of the Ukrainian flag beside the vehicle to white and blue. | “Change the color of the Ukrainian flag ... to white and blue”没有说明哪条条纹变成哪种颜色;此外更右侧(x~0.68W)的车辆上还可见第二面乌克兰国旗,且被 mask 的那面是安装在车辆后视镜杆上,而不是在其“beside”。 | Ref: Change the color of the yellow lower stripe of the Ukrainian flag on the pole by the vehicle's side mirror to white.<br>No-ref: Change the color of the yellow stripe of the selected flag to white. | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | ref+none | Replace the helmeted head above the vehicle with a blue helmet. | REF 'Replace the helmeted head above the vehicle with a blue helmet' 指的是头（身体/人物层级），而 mask 只是迷彩头盔（box [578,275,733,369]）；用头盔替换头部毫无意义。 | Ref: Change the color of the camouflage helmet of the soldier in the vehicle's turret to blue.<br>No-ref: Change the color of the selected helmet to blue.<br>将 op 改为 attribute（helmet->blue helmet 是改色） | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the helmeted head above the vehicle with a blue helmet. | Payload“a blue helmet”是用头盔替换头盔；只有颜色变化。 | Ref: Change the color of the camouflage helmet of the soldier in the vehicle's turret to blue.<br>No-ref: Change the color of the selected helmet to blue. | 目视 |

#### `v2-sa_7452479`（#930，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 方位/序数/实例指代错误 | ref+mask | Change the color of the flag at the bow of the boat to red. | U1 mask 是从岸边围栏后升起的高杆上的黄色王旗(box x1566-1712, y343-473);它不在船上。REF 'the flag at the bow of the boat' 不实,而且附近还飘着第二面旗(泰国三色旗,U2),所以该引用不可靠。 | Ref: Change the color of the yellow flag on the tall pole at the right, behind the fence, to red.<br>fix physical_parent_zh (岸边黄旗) | 目视 |
| U2 | 阻断 | 指代类别与 mask 不符 | noref+box | Replace the cloth hanging on the boat with a blue patterned cloth. | U2 mask（box x1261-1333, y411-577）是栅栏后杆子上的红白蓝泰国国旗，而不是 'the cloth hanging on the boat'；REF/ZH 说错了物体类型和位置。 | Ref: Replace the red-white-blue Thai flag on the pole behind the fence with a white pennant banner.<br>No-ref: Replace the selected flag with a white pennant banner.<br>scope cloth -> flag；physical_parent_zh -> 泰国国旗 | 目视 |
| U3 | 严重 | 指代类别与 mask 不符 | ref+point | Remove the wooden barrel in the foreground. | U3 mask 是立在船甲板上的一个蓝色塑料桶（box x905-1017, y885-1056）；REF/ZH 称其为 'in the foreground' 的 'wooden barrel'（木桶）。它是唯一的桶，但材质描述有误，会误导评判者。 | Ref: Remove the blue plastic barrel on the boat deck.<br>ZH 木桶 -> 蓝色塑料桶 | 目视 |
| U4 | 阻断 | 方位/序数/实例指代错误 | noref+point | Add a small yellow sticker on the sign on the riverbank. | U4 mask(box x613-803,y984-1038)是安装在船木质船体侧面的带泰文的蓝色名牌,但 REF/ZH 说的是“the sign on the riverbank”(河岸上的标牌);位置错误,会把模型引向岸边。 | Ref: Add a small yellow sticker on the blue name plate on the side of the boat's hull.<br>No-ref: Add a small yellow sticker on the selected sign.<br>physical_parent_zh -> 船身名牌 | 目视 |

#### `v2-sa_7464946`（#931，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 人物/服装层级错误 | noref+mask | Replace the shirt on the child at the far left with a blue jacket. | U2 mask（box [0,0,1451,1500]，占图像 54%）覆盖整个男孩，包括头、头发、耳朵和手，而不仅是衣物。衣物是带红色条纹的藏青色连帽衫，REF 称之为 'shirt'；'child at the far left' 因为他是唯一的孩子而成立。 | Ref: Replace the navy hoodie with red stripes on the boy with a blue denim jacket.<br>No-ref: Replace the selected hoodie with a blue denim jacket.<br>重新 mask 到连帽衫上（排除头/手）；范围 shirt -> hoodie | 目视 |
| U3 | 阻断 | 指代类别与 mask 不符 | ref+none | Change the color of the white sleeve on the child near center to blue. | U3 mask（box [921,486,1268,656]）是男孩下巴后面白色混凝土墙/女儿墙的一块，不是袖子。此外图像中只有一个孩子（穿带红条的藏青色连帽衫），所以“the white sleeve on the child near center”并不存在。 | Ref: Change the color of the white concrete parapet block behind the boy's chin to light gray.<br>No-ref: Change the color of the selected wall block to light gray.<br>或删除该 unit；scope sleeve -> wall | 目视 |
| U4 | 轻微 | 属性值问题（无变化/含糊） | ref+mask | Add a red symbol on the small sign above the crowd. | U4 小标志是蓝色人行横道标志,本身已有符号;'Add a red symbol' 对于加什么符号含糊不清。 | Ref: Add a small red triangular warning sticker on the blue pedestrian-crossing sign beyond the railing.<br>No-ref: Add a small red triangular warning sticker on the selected sign. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+mask | Add a red symbol on the small sign above the crowd. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_7470032`（#932，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+box | Change the color of the bench near the lower center to dark green. | U1 是停放自行车旁的一张小石/木长椅（cx=0.67W）。围绕树的分层圆形木长椅才更符合 'lower center'；'the bench near the lower center' 指向了错误/有歧义的长椅。 | Ref: Change the color of the small bench beside the parked bicycles to dark green.<br>ZH: 将停放自行车旁的小长椅改为深绿色。 | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | ref+point | Replace the coat on the person at the right with a beige coat. | U2 mask（box 1934-2011, 1239-1408）勾勒的是右侧走远的整个女子——粉色帽子、黑外套、腿和靴子——而不只是外套，而 REF/NOREF 说的是 'the coat'。 | Ref: Replace the black puffer coat on the woman pulling a shopping trolley at the right with a beige trench coat.<br>No-ref: Replace the selected coat with a beige trench coat.<br>重新 mask 为仅黑色外套 | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the coat on the person at the right with a beige coat. | “Replace the coat ... with a beige coat”仅在同一衣物类别内改变颜色。 | Ref: Replace the black puffer coat on the woman pulling a shopping trolley at the right with a beige trench coat.<br>payload 必须改变衣物结构(例如风衣 / 斗篷) | 目视 |
| U4 | 阻断 | 指代类别与 mask 不符 | ref+box | Add a small flower box on the narrow plaque on the left facade. | U4 mask（box 210-244, 885-949）是左侧建筑上带小遮阳篷的窄窗，不是牌匾。 | Ref: Add a small flower box under the narrow awninged window on the left facade.<br>No-ref: Add a small flower box under the selected window.<br>范围 -> window | 目视 |

#### `v2-sa_7493523`（#933，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Change the color of the costume on the foreground person to deep blue. | REF 写的是“the costume on the foreground person”，但 mask（box 269-680 x 584-1073，左上）覆盖的是蓝色桌子后面背景中坐着的女士。前景的人是右侧穿蓝夹克红裙子的花边制作者。mask 还覆盖了包括头部和头饰在内的整个上半身，不仅仅是服装。 | Ref: Change the color of the dark red sarafan dress of the woman seated behind the blue table to deep blue.<br>No-ref: Change the color of the selected dress to deep blue.<br>仅对背景女士的裙子重新做 mask（排除面部和头饰）。 | 目视 |
| U2 | 阻断 | 指代类别与 mask 不符 | ref+none | Replace the chair at the lower left with a wooden stool. | Mask(box 91-793 x 1558-2620)覆盖的是支撑花边枕的木质 X 形支架,上面还搭着一条刺绣毛巾。它不是椅子,所以 'the chair at the lower left' 指的是一个不存在的物体。 | Ref: Replace the wooden X-frame stand at the lower left with a small round wooden side table.<br>No-ref: Replace the selected stand with a small round wooden side table.<br>Change the spec scope to 'stand'. | 目视 |
| U3 | 阻断 | 指代类别与 mask 不符 | ref+mask | Remove the cloth on the table. | REF 'Remove the cloth on the table'，但 mask（box 874-1359 x 843-1349）覆盖的是前景织花边女子所戴的、带红色面纱的红金色科科什尼克头饰。mask 中没有桌布。移除所戴的头饰也属于移除衣物类编辑。 | Ref: Change the color of the red headdress with gold trim of the lace-maker in the blue jacket to white.<br>No-ref: Change the color of the selected headdress to white.<br>将操作改为 attribute（或仅在 scope 说明显示头发时才保留 remove），并将 scope 设为 'headdress'。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a small bead on the hanging textile at the upper left. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_7494564`（#934，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | ref+point | Change the color of the café umbrella near the center to yellow. | REF 说 'the café umbrella near the center'，但被 mask 的收起的红色伞（box [1158,1272,1232,1457]，cx=0.80W）在右侧，处于露台上约 6 把相似的收起的红/粉色伞之列。'Near the center' 是错误的，也无法选出其中一把。 | Ref: Change the color of the large closed red café umbrella on the terrace below the wooden balcony, third from the left among the umbrellas, to yellow.<br>ZH: 将木阳台下方露台上左数第三把收起的大红色咖啡伞的颜色改为黄色。 | 目视 |
| U4 | 严重 | mask 质量 | noref+mask | Add a white emblem on the small flag above the roof. | 旗帜 mask 很小(box [825,622,849,642],329 px,面积 0.0001):圆顶上方杆子上的一面红白小旗(其中央本来就有徽记)。给它添加“a white emblem”几乎看不见,难以验证。 | 删除该单元,或改为更大的目标物体,例如在棕褐色木塔的灰色炮塔屋顶上进行 add。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a white emblem on the small flag above the roof. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_7506005`（#935，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | mask 质量 | ref+none | Change the color of the shirt on the foreground runner to bright blue. | REF 的目标是 'the shirt on the foreground runner'，但 mask/box [602,919,959,1987] 覆盖整个跑者（从头到鞋），即对衣物编辑使用了人物级 mask。 | Ref: Change the color of the white-and-red singlet on the foreground runner to bright blue.<br>重新 mask 到背心上。 | 目视 |
| U2 | 阻断 | mask 质量 | ref+mask | Replace the shirt on the runner at the right with a red jersey. | REF 要替换“the shirt on the runner at the right”，但 mask 覆盖了右侧跑者的整个身体（box [1213,978,1437,1526]）。现有的背心已经是白/红色，所以“a red jersey”也接近改色。 | Ref: Replace the white-and-red singlet on the runner at the right with a red long-sleeved cycling jersey.<br>No-ref: Replace the selected singlet with a red long-sleeved cycling jersey.<br>仅对背心重新做 mask。 | 目视 |

#### `v2-sa_7522810`（#936，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+point | Change the color of the shop sign on the left to dark blue. | 左侧有两块 'Pretto' 店招:最左边缘拐角店铺上方的大拱形招牌,以及第二个拱窗上方被 mask 的较小招牌 [437,787,570,896]。'the shop sign on the left' 更自然地符合最左侧较大的那块。 | Ref: Change the color of the smaller Pretto sign above the second arched shop window on the left to dark blue. | 目视 |
| U3 | 阻断 | 指代类别与 mask 不符 | noref+mask | Remove the dark coat on the person at the lower right. | Mask/box [2052,965,2248,1013] 覆盖的是右边缘（用餐桌上方）一把白色咖啡馆市集伞的顶部，而不是外套。REF 'the dark coat on the person at the lower right' 指的是未被 mask 的衣物；移除外套也属于所穿衣物的移除。 | Ref: Remove the white cafe umbrella at the far right edge.<br>No-ref: Remove the selected umbrella.<br>将类别改为 umbrella/parasol，并修正 physical_parent_zh（右侧遮阳伞）。 | 目视 |
| U4 | 严重 | 指代歧义 | ref+none | Add a flower box on the window on the upper left building. | 正式输入为 ref+none；'the window on the upper left building' 适用于那座宫殿上的许多带百叶窗的窗户。被 mask 的 [251,219,378,404] 是带栏杆阳台上方、有灰色百叶窗的左上角可见窗户。 | Ref: Add a flower box on the topmost window with gray shutters at the upper-left corner of the building on the left. | 目视 |

#### `v2-sa_7542458`（#938，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | ref+box | Change the color of the shirt on the foreground visitor to dark blue. | U1 mask 是中景处走向大门的男子的黄/蓝格子衬衫(box 585-662 x, 1744-1857 y,在 2250 高图像中约 ~0.80H)。明显的前景游客是穿蓝色无袖上衣的白发女子(以及左下边缘一个戴帽的人),所以 'the foreground visitor' 指向了另一个人。 | Ref: Change the color of the plaid shirt on the man walking toward the gate, left of the woman in the floral top, to dark blue. | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the backpack on the visitor near the center with a red backpack. | U2 mask 的是一个深红/黑色背包；'Replace ... with a red backpack' 类别不变，本质上是换色（该包本来就偏红）。 | Ref: Replace the backpack on the visitor near the center with a brown leather messenger bag.<br>No-ref: Replace the selected backpack with a brown leather messenger bag. | 目视 |
| U3 | 轻微 | 方位/序数/实例指代错误 | ref+none | Remove the flag on the tower. | 被 mask 的红旗插在两座塔之间带垛口的门墙上方的杆子上，而不是在塔上；它是唯一的旗帜，因此目标仍可识别。 | Ref: Remove the red flag above the gate's battlements. | 目视 |

#### `v2-sa_7563964`（#940，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Change the color of the digital display panel near the center to blue. | U1 mask(box 378-701,中心 0.27W,0.38H)是最左边的小黄色显示屏,部分位于时钟旁悬挂的站台标牌后面。右侧还有一排类似的黄色屏;下一块(~0.42-0.47W)和右侧的大屏都更靠近图像中心,所以 "the digital display panel near the center" 指向了另一块屏。 | Ref: Change the color of the small yellow display panel behind the hanging platform signs, right of the clock, to blue.<br>ZH: 将时钟右侧、站台指示牌后方的黄色小电子屏改为蓝色。 | 目视 |

#### `v2-sa_7567943`（#942，扩充 #869–#944，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 编辑不合理/不可执行 | ref+mask | Replace the streetlight on the left with a modern lamp. | U2 把路灯替换为 'a modern lamp'。现有的双臂路灯本身已经很现代，因此载荷含糊，没有给出具体的目标结构。 | Ref: Replace the streetlight on the left with an ornate black cast-iron lamppost with a single lantern.<br>No-ref: Replace the selected streetlight with an ornate black cast-iron lamppost with a single lantern. | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | noref+box | Remove the building at the right. | U3 移除天际线中整栋长公寓楼（box [1097,601,1535,715]）。按协议，移除整栋建筑或大型结构是不适定的。 | 将操作改为 attribute，例如 'Change the color of the facade of the long apartment block on the right to pale yellow.'，或删除该 unit。 | 目视 |
| U4 | 阻断 | 方位/序数/实例指代错误 | ref+point | Add a rooftop sign on the building near the center. | REF 说 'the building near the center',但被 mask 的建筑(box [247,538,476,706],cx=0.16W)是最左边、紧靠路灯右侧的白色高层楼。真正靠近中心的建筑是约 x=850-1100(原图)的酒店群和长条形的 U3 楼。 | Ref: Add a rooftop sign on the white high-rise apartment block on the left, just right of the streetlight.<br>ZH: 在左侧路灯右边的白色高层公寓楼顶加上一个屋顶标牌。 | 目视 |

#### `v2-sa_7650202`（#947，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Change the color of the car at the far left to red. | U1 mask 的是 x~230-385(合成图)处的深色旅行出租车,但更靠左(x~0-165,图像边缘)至少还有另一辆深色汽车。因此“the car at the far left”指向了另一辆车。 | Ref: Change the color of the dark taxi wagon parked in front of the left wing of the station, second car from the left, to red.<br>相应修正 ZH | 目视 |
| U2 | 严重 | 指代歧义 | ref+none | Replace the car near the right with a blue hatchback. | 右侧附近有很多车（深色车在 x~1020-1220，被 mask 的深色旅行车在 x~1240-1375，银色出租车在 x~1395-1515 和 ~1550+）。'the car near the right' 无法识别 U2。 | Ref: Replace the dark taxi wagon in front of the modern glass building on the right with a blue hatchback. | 目视 |
| U3 | 严重 | 指代歧义 | ref+mask | Remove the pedestrian near the center. | 喷泉和出租车旁的中心附近站着几名行人（例如被 mask 女士紧左侧穿白衬衫的男子、喷泉附近的人）；“the pedestrian near the center”不唯一。 | Ref: Remove the woman in a patterned outfit walking on the paved circle right of the fountain, beside the man in a white shirt. | 目视 |
| U4 | 严重 | mask 质量 | noref+box | Add a shop sign on the building at the right. | U4 mask 是现代玻璃车站建筑后方远处背景建筑顶部/屋顶上的一个细楔形(box 1814-1967 x 735-785),而 REF 说 'the building at the right';右侧显眼的建筑是未被 mask 的大型深色玻璃建筑。 | Ref: Add a shop sign on the beige building behind the modern glass building on the right.<br>or re-mask to the glass building at the right | 目视 |

#### `v2-sa_7677069`（#949，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 多单元同一物理对象/相互冲突 | ref+mask | Replace the sickle near the center with a wooden tool. | U2 镰刀(box [917,953,1053,1301])握在中间那位女子手中,她是 U3 且将被移除;U2 box 位于 U3 box 之内。这两个编辑相互冲突(移除女子会使被替换的工具悬在空中),且不是独立的物体。 | 删除 U2(或删除 U3 并保留镰刀编辑);选择独立的物体,如女子左侧地面上的金属托盘 | 目视 |
| U2 | 严重 | 编辑不合理/不可执行 | ref+mask | Replace the sickle near the center with a wooden tool. | 载荷 'a wooden tool' 不是具体物体；结果无法验证。 | Ref: Replace the sickle near the center with a wooden mallet.<br>No-ref: Replace the selected sickle with a wooden mallet. | 目视 |
| U3 | 严重 | mask 质量 | noref+box | Remove the woman near the center. | U3 女士 mask 包含她正在劈的长竹条（向右延伸到 x~0.6W 的细黄色条纹）以及左下方的若干零散地面/稻草碎片（comps=2，约 x~0.36-0.42W, y~0.85-0.95H 的不规则斑块）。 | 将 mask 清理为仅女士的身体和衣物；排除竹条和地面碎片 | 目视 |

#### `v2-sa_7698269`（#951，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 属性值问题（无变化/含糊） | ref+mask | Change the color of the street lamp on the left to black. | U1 mask 是左侧立面上带卷轴支架的壁挂灯笼,它本来就是黑色;“Change the color ... to black”是空操作编辑。 | Ref: Change the color of the wall-mounted lantern on the left facade to brass gold.<br>No-ref: Change the color of the selected street lamp to brass gold.<br>scope -> wall lantern | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the door near the center with a blue door. | 'Replace the door ... with a blue door' 只是对同一类别的门改色。 | Ref: Replace the green slatted door of the corner building in the background with an arched wooden double door.<br>No-ref: Replace the selected door with an arched wooden double door.<br>或改为属性：color -> blue | 目视 |
| U2 | 严重 | 方位/序数/实例指代错误 | noref+box | Replace the door near the center with a blue door. | U2（box 1147-1220，cx=0.79W）是街道右端白色转角楼上的一扇绿色小百叶门，位于禁止驶入标志旁。中央的蓝色建筑沿线有许多深色门；“the door near the center”无法识别它。 | Ref: Replace the green slatted door of the white corner building next to the no-entry sign with an arched wooden double door.<br>ZH: 禁止驶入标志旁白色转角楼的绿色百叶门 | 目视 |
| U4 | 阻断 | 编辑不合理/不可执行 | noref+point | Add a ceramic pot on the potted plant at the lower left. | U4 mask 覆盖的是本来就种在深色方形花盆中的造型树;'Add a ceramic pot on the potted plant' 不合理(它已经有盆,而且盆不能放在植物上)。 | Ref: Add a small wooden birdhouse hanging in the topiary tree in the planter at the lower left.<br>No-ref: Add a small wooden birdhouse hanging in the selected potted plant. | 目视 |

#### `v2-sa_7716977`（#953，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 属性值问题（无变化/含糊） | noref+box | Change the surface texture of the plant near the upper center to green and fuller. | 'Change the surface texture of the plant ... to green and fuller' 不是清晰的属性/值对（阳台上的盆栽，box [1027,247,1195,495]，本身已是绿色）；含糊且难以评分。 | Ref: Change the color of the leaves of the potted plant on the balcony near the upper center to autumn orange.<br>No-ref: Change the color of the leaves of the selected plant to autumn orange. | 目视 |
| U2 | 严重 | 指代歧义 | ref+point | Replace the sign near the lower center with a blue sign. | “the sign near the lower center”适用于这条密集街道上的数十个标牌；mask（box [1253,1267,1329,1341]）是带红星的黑色小圆形“VIET DREAM TRAVEL”标牌。 | Ref: Replace the round VIET DREAM TRAVEL sign with the red star near the lower center with a small square lantern.<br>No-ref: Replace the selected sign with a small square lantern. | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the sign near the lower center with a blue sign. | 替换 payload 'a blue sign' 保持相同类别(标志),只指定了颜色 —— 实质上是改色。 | Use a different-category payload (see above) or convert to attribute color change. | 目视 |
| U3 | 严重 | 指代歧义 | noref+point | Remove the window at the upper right. | 'the window at the upper right' 适用于右上方高层楼房和建筑上的数百扇窗户；mask 是浅蓝色建筑上的一扇很小的窗户（box [2033,385,2067,438]，面积 0.0004）。 | Ref: Remove the single small window on the plain pale-blue wall at the upper right, left of the tall glass tower.<br>考虑删除：目标太小。 | 目视 |
| U4 | 阻断 | 方位/序数/实例指代错误 | ref+box | Add a sale sticker on the vertical sign on the left storefront. | REF：'the vertical sign on the left storefront'，但 U4 mask（box [714,995,894,1092]）是左中部一块横向的深绿色 'HOTEL' 招牌。左侧确实有几块竖向招牌（例如高高的 'KAKA SPA' 招牌、红色的 'Saigon' 竖向招牌），所以 REF 指向的是另一个实例。 | Ref: Add a sale sticker on the horizontal green HOTEL sign at the left center.<br>ZH: 在左中部绿色横向HOTEL招牌上加上一个促销贴纸。 | 目视 |

#### `v2-sa_77343`（#954，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | ref+none | Replace the picture frame at the upper left with a round frame. | 左上角挂着数个小相框纪念画(至少三个);mask 是板上最右边的小相框。Box [89,0,254,184] 的范围也超出了被 mask 的相框。 | Ref: Replace the rightmost small framed picture on the souvenir board at the upper left with a round frame.<br>将 box 收紧到被 mask 的相框。 | 目视 |
| U3 | 阻断 | 指代类别与 mask 不符 | ref+mask | Remove the bowl of green fruit on the right. | REF 'the bowl of green fruit on the right'，但 mask 是白衣玩偶前的绿色毛毡花饰（黄绿色花瓣，米色花心）；没有水果碗。 | Ref: Remove the green felt flower ornament in front of the white-dressed doll.<br>No-ref: Remove the selected ornament.<br>将范围从 'fruit bowl' 改为 'felt flower'；修正 ZH。 | 目视 |
| U4 | 严重 | 指代歧义 | noref+box | Add a small garnish on the food on the table near the center. | “the food on the table near the center”适用于数百颗 churchkhela 珠子；mask 是单个深色珠子（box [889,767,961,847]）。在 churchkhela 珠子上放“a small garnish”这个 payload 也不自然。 | Ref: Add a small mint leaf on the single dark churchkhela bead at the right end of the left basket.<br>考虑改选整串 churchkhela 而不是单个珠子。 | 目视 |

#### `v2-sa_7735833`（#955，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | ref+point | Change the color of the worker near the center to blue. | Mask [581,216,1391,1047] 覆盖整个蹲着的焊工(头、头盔、黑色长袖上衣、裤子、手套);'Change the color of the worker to blue' 是对整个人施加颜色属性。 | Ref: Change the color of the black long-sleeved shirt of the welder near the center to blue.<br>No-ref: Change the color of the selected shirt to blue.<br>Re-mask to the shirt only (or change op to a person-level edit such as remove). | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+point | Replace the gas cylinder at the right with a red cylinder. | 被 mask 的物体是带链条的青绿色/蓝色气瓶；payload 'a red cylinder' 只改变颜色。 | Ref: Replace the gas cylinder at the right with a red fire extinguisher.<br>No-ref: Replace the selected gas cylinder with a red fire extinguisher.<br>或改为属性编辑 color=red。 | 目视 |
| U3 | 轻微 | 指代歧义 | ref+box | Remove the wheel near the right. | 'the wheel near the right' 很含糊：被 mask 的轮子 [1300,652,1488,897] 是焊工右边 x~0.62 处的气瓶推车轮子，并不靠近右边缘。 | Ref: Remove the black trolley wheel just right of the welder, in front of the gas cylinders. | 目视 |
| U4 | 轻微 | 指代类别与 mask 不符 | noref+mask | Add a small warning label on the metal assembly at the left. | Mask [63,852,470,1077] 是斜放在框架上的一根细长闪亮钢棒,而不是“assembly”;该名词对基于 ref 的模型有误导性。 | Ref: Add a small warning label on the thin steel rod at the left.<br>No-ref: Add a small warning label on the selected steel rod.<br>将 scope 设为“steel rod”。 | 目视 |

#### `v2-sa_777091`（#958，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 方位/序数/实例指代错误 | noref+box | Replace the car at the lower left with a white sedan. | REF 称 'the car at the lower left'，但被 mask 的汽车是黄色公交车前方右下方的白色小型掀背车（box x 981-1177, cx=0.72）。左下方是其他汽车（x~0.2-0.4W 的红色出租车和白色轿车），因此 REF 指向了不同的汽车。 | Ref: Replace the white hatchback in front of the yellow bus at the lower right with a red pickup truck.<br>No-ref: Replace the selected car with a red pickup truck.<br>ZH: 将右下方黄色公交车前的白色掀背车替换为一辆红色皮卡。（将白色掀背车的载荷设为 'a white sedan' 也几乎无变化；请使用明显不同的车辆） | 目视 |
| U3 | 严重 | 方位/序数/实例指代错误 | ref+point | Remove the bus near the center. | REF“the bus near the center”——被 mask 的黄色公交车位于右下方（cx=0.76, cy=0.92），远离图像中心/纪念碑。它是唯一的公交车，所以该实例仍可恢复，但空间措辞是错误的。 | Ref: Remove the yellow bus at the lower right.<br>ZH: 移除右下方的黄色公交车。 | 目视 |

#### `v2-sa_7797481`（#960，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+box | Change the color of the woman at the left to blue. | U1 mask 是整个女子（box [348,816,457,1169]），指令是 'Change the color of the woman at the left to blue'。这是对人整体的改色，没有指明衣物。她穿着荧光黄绿色安全背心/上衣和黑色裤子。 | Ref: Change the color of the neon yellow-green vest of the woman at the left to blue.<br>No-ref: Change the color of the selected vest to blue.<br>将 mask 重做为仅背心，并设置 category=vest。 | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | ref+point | Replace the boy near the left with a red jacket. | “Replace the boy near the left with a red jacket”把整个人(男孩的 mask,box [127,908,207,1144])替换成了一件衣物。男孩穿着橙色 T 恤和蓝色短裤。 | Ref: Replace the orange T-shirt of the boy near the left with a red zip-up jacket.<br>No-ref: Replace the selected T-shirt with a red zip-up jacket.<br>重新对橙色 T 恤做 mask,并设置 category=T-shirt。 | 目视 |
| U3 | 阻断 | mask 质量 | noref+point | Remove the fruit cart in the foreground. | U3 mask 覆盖的叠加图显示它覆盖的是草地：左侧的草坪带以及桌腿下方和周围的草。它没有覆盖木制西瓜展示桌、西瓜或三角旗。所指物体也是固定的木制展示桌/摊架，而不是 'fruit cart'。因此 mask 覆盖了错误区域，名词也不合适。 | Ref: Remove the wooden watermelon display table in the foreground.<br>No-ref: Remove the selected table.<br>重新 mask 到前景木桌及其西瓜和三角旗串；设 category=display table。ZH: 移除前景装满西瓜的木制展示台。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+box | Add a small arrow on the sign behind the stall. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_7810159`（#962，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | ref+point | Change the color of the shirt on the person at the right to yellow. | U1 mask(box 1332-1500 x 684-2101)覆盖了整个右边缘男子——头、白色 T 恤、牛仔裤和腿——但 REF 只重新着色“the shirt”。 | Ref: Change the color of the white T-shirt of the man at the right edge to yellow.<br>重新 mask 为仅含白色 T 恤 | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | noref+point | Replace the shirt on the person at the left with a blue shirt. | U2 mask 覆盖左侧整个男子（戴眼镜的头、黑色 T 恤、短裤、腿和鞋；被背包男子分成 2 个连通块），而不仅是他的衬衫。 | Ref: Replace the black T-shirt on the man with glasses at the left with a blue denim button-up shirt.<br>No-ref: Replace the selected shirt with a blue denim button-up shirt.<br>重新 mask 到黑色 T 恤上 | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+point | Replace the shirt on the person at the left with a blue shirt. | 将黑色 T 恤替换为“a blue shirt”只是颜色变化。 | Ref: Replace the black T-shirt on the man with glasses at the left with a blue denim button-up shirt.<br>No-ref: Replace the selected shirt with a blue denim button-up shirt. | 目视 |
| U4 | 阻断 | mask 质量 | noref+mask | Add a small label on the device near the lower center. | U4 'device' mask 覆盖两个分开的扩音器:挂在男子髋部的白色那个,以及他手里拿的蓝/白 CC.OO 那个;'the device' 不是单个实例,名词也含糊。 | Ref: Add a small red sticker on the white megaphone hanging at the hip of the man in the green helmet.<br>No-ref: Add a small red sticker on the selected megaphone.<br>re-mask to one megaphone only; category -> megaphone | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small label on the device near the lower center. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_7835850`（#964，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the backpack on the person at the right with a blue backpack. | U2 是右侧人物的红色背包;“replace with a blue backpack”仅改变颜色。 | Ref: Replace the red backpack on the person at the right with a brown leather messenger bag.<br>No-ref: Replace the selected backpack with a brown leather messenger bag. | 目视 |
| U3 | 阻断 | 指代类别与 mask 不符 | noref+point | Remove the cable car tower near the center. | U3 mask 是大型高压输电铁塔（带横担和绝缘子的格构塔，box [779,410,1398,1455]，cx=0.73W）。真正的缆车塔（带承载吊厢缆索的滑轮组）位于图像中心附近 x~0.47W；因此 'the cable car tower near the center' 指的是与 mask 不同的物体。 | Ref: Remove the large steel power-line pylon on the right side of the street.<br>No-ref: Remove the selected pylon.<br>将范围改名为 'power pylon'；注意移除如此大的结构也难以评分（考虑改用属性编辑，例如把铁塔颜色改为红色） | 目视 |
| U4 | 阻断 | 方位/序数/实例指代错误 | ref+box | Add a route number on the banner near the center. | U4 mask 是右边缘砖楼上的一个小竖幅/海报（box [1345,1151,1397,1309]，cx=0.91W）；REF 写的是“the banner near the center”。 | Ref: Add a route number on the vertical banner on the brick building at the right edge.<br>更新 ZH: 在右侧边缘砖楼上的竖幅加上一个线路编号。 | 目视 |

#### `v2-sa_7854521`（#966，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 属性值问题（无变化/含糊） | ref+point | Change the color of the boat at the lower center to white. | 被 mask 的船“GRAFIN COSEL”(box [897,2189,1500,2527])船体和上层建筑本来就是白色;“Change the color ... to white”实质上是空操作,无法评分。 | Ref: Change the color of the hull of the white passenger boat at the lower right to dark green.<br>No-ref: Change the color of the hull of the selected boat to dark green. | 目视 |
| U1 | 严重 | 方位/序数/实例指代错误 | ref+point | Change the color of the boat at the lower center to white. | REF 'the boat at the lower center'，但被 mask 的船位于右下方（中心 x=0.80W，延伸到右边缘）；左下方还有另一艘白色船，因此 'lower center' 与哪艘都不太吻合。 | Ref: Change the color of the hull of the passenger boat GRAFIN COSEL at the lower right to dark green. | 目视 |
| U2 | 严重 | 指代歧义 | noref+point | Replace the dome at the upper left with a copper dome. | REF“the dome at the upper left”：最显眼的左上圆顶是左上边缘的大型带肋玻璃圆顶（y~0.15-0.21H）；mask 是位置更低的建筑立面上的一个灰色小圆顶（box [56,1425,342,1561]，y=0.56H）。 | Ref: Replace the small gray dome on the left building facade, below the large glass dome, with a pointed copper spire.<br>No-ref: Replace the selected dome with a pointed copper spire. | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+point | Replace the dome at the upper left with a copper dome. | 'Replace the dome ... with a copper dome' 保持圆顶类别;只改变材质/颜色。 | Ref: Replace the small gray dome on the left building facade with a pointed copper spire.<br>No-ref: Replace the selected dome with a pointed copper spire.<br>or convert to attribute (material copper) | 目视 |

#### `v2-sa_7892712`（#967，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | ref+none | Change the color of the child near the left to yellow. | U1 mask（box [882,671,1096,940]）是一整个孩子（头+白色 T 恤）；'Change the color of the child ... to yellow' 是给人换色，而不是指明衣物。 | Ref: Change the color of the white T-shirt of the boy seated at the right of the pair in the boat to yellow.<br>No-ref: Change the color of the selected T-shirt to yellow.<br>重新 mask 为仅白色 T 恤 | 目视 |
| U1 | 阻断 | 方位/序数/实例指代错误 | ref+none | Change the color of the child near the left to yellow. | U1（中心 0.44W）被称为 'the child near the left'，而 U2（中心 0.34W）被称为 'the child near the center'；U1 实际上在 U2 的右侧，所以空间词被调换了。 | Ref: ... the boy in a white T-shirt seated to the right of the boy in a striped tank top ...<br>对调/改写 U1/U2 的空间描述 | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | ref+mask | Replace the child near the center with a blue jacket. | U2 mask(box [627,673,895,1039])是整个穿黑白条纹背心的孩子;“Replace the child near the center with a blue jacket”把一个人替换成了一件衣物。 | Ref: Replace the black-and-white striped tank top of the boy seated in the middle of the boat with a blue jacket.<br>No-ref: Replace the selected tank top with a blue jacket.<br>重新 mask 为仅含背心 | 目视 |
| U3 | 严重 | 多单元同一物理对象/相互冲突 | noref+box | Remove the boat in the center. | U3 移除整艘长尾船（占图像 17%），船上载着 U1 和 U2 的孩子（他们的 box 位于船 box 内）；移除船与编辑船上的乘客冲突，且是巨大的、不合理的修补区域。 | Ref: Remove the red-and-white flower garland on the bow of the boat in the center.<br>或改为属性（例如把船的绿色顶篷颜色改为红色）；避免移除载有其他单元目标的船 | 目视 |

#### `v2-sa_7945941`（#969，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+mask | Change the color of the woman near the center to green. | U1 mask 是中心附近背向走远的整个女子（白色上衣、青绿色短裤、斜挎包）；'Change the color of the woman to green' 把颜色应用到了整个人。 | Ref: Change the color of the teal shorts of the woman walking near the center to green.<br>No-ref: Change the color of the selected shorts to green.<br>重新 mask 为她的青绿色短裤（或白色上衣 -> 'white top ... to green'） | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | ref+none | Replace the man at the right with a gray coat. | U2 mask 是整个穿藏青T恤、灰短裤、在偏右处行走的男子；'Replace the man at the right with a gray coat' 是把一个人替换成一件衣服。 | Ref: Replace the navy T-shirt of the man walking right of center with a gray coat.<br>No-ref: Replace the selected T-shirt with a gray coat.<br>将 mask 重做为其藏青T恤 | 目视 |

#### `v2-sa_7985091`（#970，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | ref+point | Change the color of the man on the bridge to blue. | 该 mask 覆盖了整个新郎(头、藏青西装外套、裤子)。“Change the color of the man to blue”是针对人整体的颜色编辑,含义不明确(皮肤?衣服?)。他的西装本来就是藏青色,所以即使理解为衣物也几乎没有变化。 | Ref: Change the color of the navy suit jacket of the groom on the bridge to light gray.<br>No-ref: Change the color of the selected suit jacket to light gray.<br>重新 mask 为仅含西装外套,并将 scope 设为“suit jacket”。 | 目视 |
| U2 | 严重 | 编辑不合理/不可执行 | noref+point | Remove the bridge structure. | mask 横跨整座悬索桥（栏杆、桥面、缆索；占图像 0.22，4 个连通块），新郎新娘就站在桥上。移除整个桥结构会让人物悬空，并需要修补巨大的区域，因此编辑不合理。 | Ref: Remove the cluster of love padlocks attached to the bridge railing post.<br>No-ref: Remove the selected padlocks.<br>选择更小的桥上附属物（挂锁），或改为属性：'Change the color of the white bridge railings to dark green.' | 目视 |

#### `v2-sa_7991555`（#971，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 人物/服装层级错误 | noref+mask | Replace the person at the right with a red jacket. | U2 将整个人（右边缘穿棕色蜡染衬衫的男子，box [1414,1937,1500,2098]）替换为“a red jacket”——用衣服替换人是不合理的。 | Ref: Change the color of the brown patterned shirt of the man at the right edge behind the taxi to red.<br>No-ref: Change the color of the selected shirt to red.<br>仅对衬衫重新做 mask 并将 op 改为 attribute（或将该人替换为 'a tall potted palm'）。 | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+none | Remove the door near the center. | REF:'Remove the door near the center',但 U3 mask(box [1081,1993,1309,2245],cx=0.80W)是右侧蓝色 Bluebird 出租车的后乘客门。文字没有提到出租车,可能被理解为航站楼的门。移除车门还会留下不明确的开口。 | Ref: Add a white roof-mounted TAXI sign on the roof above the rear door of the blue Bluebird taxi.<br>Better: change op to attribute, e.g. 'Change the color of the rear door of the blue Bluebird taxi to white.' | 目视 |

#### `v2-sa_8012456`（#972，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+box | Change the color of the man at the right to blue. | 'Change the color of the man at the right to blue' 配合的是整个人的 mask；颜色属性被应用到了一个人身上。 | Ref: Change the color of the black T-shirt of the man at the right to blue.<br>No-ref: Change the color of the selected T-shirt to blue.<br>重新 mask 为 T 恤。 | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | ref+point | Replace the child at the lower right with a red jacket. | 'Replace the child at the lower right with a red jacket' 是把一个人替换成一件衣服。 | Ref: Change the color of the dark star-print top of the child at the lower right to red.<br>No-ref: Change the color of the selected top to red.<br>将 mask 重做为上衣，op=attribute。 | 目视 |
| U3 | 轻微 | mask 质量 | noref+point | Remove the bench at the lower center. | 长椅 mask(comps=2)是被底边截断的一条细暗带,加上其左端的一个杂散弯曲线;该物体几乎无法辨认。 | 移除杂散分量;若长椅无法辨认,考虑删除该单元。 | 目视 |
| U4 | 严重 | 指代歧义 | ref+box | Add a rooftop flag on the building at the right. | 'the building at the right' 既符合高大的白色塔楼（被 mask 的），也符合其下方右侧较低的弧形白色建筑。 | Ref: Add a rooftop flag on the tall white tower at the upper right. | 目视 |

#### `v2-sa_8018927`（#973，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+mask | Change the color of the person at the left to green. | Mask [1289,791,1609,1500] 是整个背身走远的秃头男子（灰毛衣、蓝牛仔裤）；“Change the color of the person to green”是对整个人上色。 | Ref: Change the color of the gray sweater of the bald man walking away in the right foreground to green.<br>No-ref: Change the color of the selected sweater to green.<br>重新对毛衣做 mask。 | 目视 |
| U1 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Change the color of the person at the left to green. | 被 mask 的男子(cx=0.64)在右前景,位于长发女子旁边;图像左侧有许多其他人(冰淇淋队伍)。'the person at the left' 与 mask 矛盾。 | Ref: Change the color of the gray sweater of the bald man walking away in the right foreground to green. | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | ref+none | Replace the person at the right with a blue coat. | Mask [1939,816,2130,1354] 是一整个穿灰色夹克和牛仔裤的男子；'Replace the person at the right with a blue coat' 是把一个人替换为一件衣物。'the person at the right' 也有歧义（更靠右还站着一名穿白衬衫的男子）。 | Ref: Replace the gray jacket of the man standing with hands in pockets at the right with a blue wool coat.<br>No-ref: Replace the selected jacket with a blue wool coat.<br>重新 mask 为灰色夹克。 | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+mask | Remove the building at the left. | Mask [804,469,1066,877] 是图像中央街道尽头的白色华丽建筑（cx=0.42），而不是 'the building at the left'（占据左侧的大型黄色建筑）。此外，移除整栋建筑本身就是不适定的。 | Ref: Add a red flag on the roof of the white ornate building at the far end of the street.<br>No-ref: Add a red flag on the roof of the selected building.<br>将 op 从 remove 改为 add/attribute；把空间措辞改为 'at the far end of the street'。 | 目视 |

#### `v2-sa_8043384`（#974，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 属性值问题（无变化/含糊） | ref+point | Change the color of the carriage in the center to dark green. | 马车的顶篷(U1 可见的主要表面,box [889,460,1914,1315])本来就是青绿色/绿色防水布;目标“dark green”几乎是空操作,难以评判。mask 还包含透过后窗看到的乘客的斑点碎片。 | Ref: Change the color of the green canopy of the carriage in the center to red.<br>No-ref: Change the color of the selected carriage to red.<br>选择一个明显不同的颜色;从 mask 中清理窗内的斑点 | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | noref+point | Replace the driver near the center with a blue jacket. | U2 mask 是一个完整的人（box [1015,681,1241,1158]）；'Replace the driver ... with a blue jacket' 是用衣物替换人。此外，被 mask 的人是坐在车厢后部侧踏板上、穿绿/橄榄色夹克的乘客，而不是车夫（穿米色夹克的车夫坐在马匹后方的前部）。 | Ref: Change the color of the olive jacket of the passenger sitting on the side step of the carriage to blue.<br>No-ref: Change the color of the selected jacket to blue.<br>重新 mask 到夹克上并改为属性；将 'driver' 改为 'passenger on the side step' | 目视 |
| U4 | 严重 | add 锚点不当 | noref+mask | Add a small badge on the man at the far left. | U4 mask 是行走人群最左侧一个远处的整个小人（box [46,639,129,837]）；“Add a small badge on the man”没有给出可附着的衣物/身体部位。 | Ref: Add a small badge on the chest of the gray jacket of the man at the far left.<br>No-ref: Add a small badge on the chest of the selected jacket.<br>重新对夹克做 mask | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small badge on the man at the far left. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_805201`（#975，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | mask 质量 | ref+mask | Replace the metal railing at the left with a wooden fence. | REF 说 'the metal railing at the left',但 U2 mask(box 242-659 x, 518-910 y)勾勒了整段上层楼梯,包括台阶和走在上面的两个人(穿红短裤的男子、顶部的女子)。将此区域替换为 'a wooden fence' 会删掉楼梯和人。 | Ref: Replace the metal railing of the staircase at the left with a wooden railing.<br>Re-mask only the white stair railing, excluding steps and people. | 目视 |
| U3 | 阻断 | 指代歧义 | noref+box | Remove the beach chair at the lower left. | 甲板左下方摆满了许多躺椅；被 mask 的那个（box 296-508 x, 907-1002 y，~0.18W,0.64H）是左中部一张有日光浴女子躺着的躺椅，并不是最左下的那张。mask 只是两个很小的碎片（头枕和脚托，面积 0.0008），且移除有人坐着的椅子本身也是不合理的。 | 删除该单元，或改为选择一张无人占用、清晰可辨且 mask 完整的躺椅。 | 目视 |

#### `v2-sa_8064958`（#977，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 编辑不合理/不可执行 | noref+box | Replace the street lamp at the left with black. | “Replace the street lamp at the left with black.”——payload 只是一个颜色,而不是物体;并且被 mask 的鹅颈路灯位于图像右侧(box x 1541-1946,cx=0.76),不是左侧。 | Ref: Replace the swan-neck street lamp at the right with a tall wooden flagpole.<br>No-ref: Replace the selected street lamp with a tall wooden flagpole.<br>或转换为 attribute:“Change the color of the swan-neck street lamp at the right to bronze.”(该灯本来就是黑色,因此把颜色改为“black”是空操作)。ZH:将右侧的鹅颈路灯替换为一根高木旗杆。 | 目视 |
| U2 | 阻断 | 方位/序数/实例指代错误 | noref+box | Replace the street lamp at the left with black. | REF 'at the left' 与 mask 矛盾：路灯位于钟楼右侧 cx=0.76；左侧没有路灯。 | Ref: (see previous finding) use 'the swan-neck street lamp at the right' | 目视 |
| U3 | 轻微 | 措辞/文法/描述细节 | ref+point | Remove the fabric at the lower right. | 右下方被 mask 的“fabric”是挂在欧盟旗旁边的、部分可见的黄色旗帜；“fabric”对它来说是个含糊的名词。 | Ref: Remove the yellow flag at the lower right, next to the EU flag.<br>No-ref: Remove the selected flag.<br>ZH: 移除右下方欧盟旗旁的黄色旗帜。 | 目视 |

#### `v2-sa_807381`（#979，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 属性值问题（无变化/含糊） | ref+mask | Change the color of the van at the left to white. | U1 把 FedEx 厢式车的颜色改为白色,但被 mask 的厢式车(box [242,1805,879,2182])本来就是白色/浅银色。该编辑是空操作,无法评分。 | Ref: Change the color of the white FedEx van at the left to dark green.<br>No-ref: Change the color of the selected van to dark green.<br>ZH:将左侧白色FedEx厢式车的颜色改为深绿色。 | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | ref+point | Remove the building on the left. | U3 移除左侧一整栋多层办公楼（box [0,794,478,1955]，约占图像 10%）。按协议，移除整栋建筑是不合理的。 | 改为属性编辑，例如 'Change the color of the facade of the building on the left to light gray.'，或删除该单元。 | 目视 |
| U4 | 严重 | 指代歧义 | noref+point | Add a flowering plant on the planter at the lower right. | 右下方有一排几乎相同的木质花箱。被 mask 的（box [1197,2106,1367,2166]）是前排中间的那个，另一个相同的箱子在更靠右约 x=1370-1500 处。“the planter at the lower right”不能识别被 mask 的箱子，更自然的理解是指最右边那个。 | Ref: Add a flowering plant on the middle wooden planter box in the front row at the lower right.<br>ZH: 在右下方前排中间的木质花箱上加上一株开花植物。 | 目视 |

#### `v2-sa_8092195`（#980，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 指代类别与 mask 不符 | ref+box | Change the color of the bridge on the left to dark gray. | U1 mask(box [0,837,1099,1108],comps=2)是沿左侧运河岸的绿色金属栏杆(外加远处小人行桥栏杆的一小条),其轮廓还包住了靠在栏杆上的人;并不存在 'bridge on the left' —— 唯一的桥是远处的小人行桥。REF 'the bridge on the left' 与被 mask 的物体矛盾。 | Ref: Change the color of the green metal railing along the left canal bank to dark gray.<br>No-ref: Change the color of the selected railing to dark gray.<br>Set scope to 'railing'; drop the far footbridge component and exclude the leaning people from the mask. | 目视 |
| U2 | 严重 | 指代歧义 | noref+mask | Remove the flower at the upper right. | 右上区域覆盖着几十朵红/橙色凌霄花；被 mask 的那朵（box [2166,39,2221,90]）是最右上角一簇很小的花。'the flower at the upper right' 适用于许多花。 | Ref: Remove the small red flower cluster at the very top-right corner of the image.<br>考虑选择更大、更独特的目标。 | 目视 |

#### `v2-sa_8099809`（#981，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 属性值问题（无变化/含糊） | ref+none | Change the color of the lamp post at the left to black. | 左侧的华丽灯柱本来就是深色/黑色；'change ... to black' 近乎无效。 | Ref: Change the color of the lamp post at the left to dark green.<br>No-ref: Change the color of the selected lamppost to dark green. | 目视 |
| U2 | 阻断 | 指代类别与 mask 不符 | ref+mask | Replace the belfry near the center with a white tower. | U2 mask(cx=0.87W)是右侧喷泉上的埃及方尖碑,而不是钟楼;真正的钟楼是左上方的教堂塔楼。REF 还说“near the center”,但方尖碑位于右边缘。 | Ref: Replace the obelisk on top of the fountain at the right with a white tower.<br>No-ref: Replace the selected obelisk with a white tower.<br>category -> obelisk;ZH:将右侧喷泉顶上的方尖碑替换为一座白色塔楼。 | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | noref+box | Remove the coat near the lower center. | U3 是人群中某人（背对镜头）所穿的浅蓝色连帽夹克；移除所穿外套会留下未定义的身体/内层衣物。此外它位于 0.76W，不是 'near the lower center'。 | Ref: Change the color of the light blue hooded jacket of the person in the crowd near the fountain to red.<br>No-ref: Change the color of the selected coat to red.<br>将 op 改为 attribute | 目视 |
| U4 | 轻微 | 指代类别与 mask 不符 | ref+point | Add a small plaque on the sculpture at the lower right. | U4 金色人像站在游客之间的人行道上，显然是涂金漆的活雕像街头艺人，而非喷泉雕塑；因此“add a plaque on the sculpture”可能很奇怪。 | Ref: Add a small plaque at the feet of the golden statue figure at the lower right.<br>核实该人像是否为表演者；若是，则选择其他目标 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a small plaque on the sculpture at the lower right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8188123`（#982，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+point | Change the color of the person near the center to blue. | U1 mask 是站在小路上浑身泥巴的整个男子(box [1162,788,1299,1182])。'Change the color of the person to blue' 对整个人施加属性;他只穿黑色泳裤。 | Ref: Change the color of the black swim trunks of the mud-covered man standing on the path to blue.<br>No-ref: Change the color of the selected swim trunks to blue.<br>re-mask to the swim trunks | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | ref+box | Replace the person at the upper right with a green shirt. | U2 mask 是右上方（box [1613,432,1807,595]）一整个穿黑色泳衣、俯身在躺椅上的女子。'Replace the person ... with a green shirt' 是把一个人替换为衣物，且 'the person at the upper right' 在躺椅使用者中也含糊不清。 | Ref: Change the color of the black swimsuit of the gray-haired woman bending over a sun lounger at the upper right to green.<br>No-ref: Change the color of the selected swimsuit to green.<br>重新 mask 为泳衣并将 op 改为 attribute，或删除 | 目视 |
| U3 | 阻断 | 指代类别与 mask 不符 | noref+mask | Remove the tarp at the upper left. | REF 说 'the tarp at the upper left'，但 U3 mask（box [714,356,835,631]，cx=0.39）是立在中偏左的一把收起的白色沙滩伞，不是防水布，也不在左上。mask 还包含了其正下方日光浴女子的头部。 | Ref: Remove the closed white parasol in front of the wooden changing cabins.<br>No-ref: Remove the selected parasol.<br>将类别修正为 parasol，并把女子的头部从 mask 中剔除 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+none | Add a small sign on the metal railing at the right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8219544`（#983，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | ref+mask | Change the color of the person at the left to blue. | U1 mask 是街道左侧部分走远的整个男子(深色格子衬衫、蓝色牛仔裤);“Change the color of the person to blue”是针对人整体的 attribute,没有指明衣物。 | Ref: Change the color of the checked shirt of the man in jeans walking at the left to blue.<br>No-ref: Change the color of the selected shirt to blue.<br>重新 mask 为仅含格子衬衫;scope='shirt' | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | noref+box | Replace the person at the right with a red jacket. | U2 mask 是右边缘一名穿奶油/米色衬衫的整个男子；'Replace the person at the right with a red jacket' 是用衣物替换人。 | Ref: Replace the cream shirt of the man at the right edge with a red jacket.<br>No-ref: Replace the selected shirt with a red jacket.<br>重新 mask 到衬衫上；scope='shirt' | 目视 |
| U4 | 阻断 | 方位/序数/实例指代错误 | noref+point | Add a small badge on the person near the center. | U4 mask 是右侧人群中一名穿橙色衬衫的男子（box [1138,516,1299,784]，cx=0.81W）；REF 写的是“the person near the center”，而人群中许多人更靠近中心。 | Ref: Add a small round badge pinned on the chest of the orange shirt of the man in the crowd at the right, in front of the decorated float.<br>No-ref: Add a small round badge pinned on the chest of the selected shirt.<br>重新对橙色衬衫做 mask | 目视 |
| U4 | 严重 | add 锚点不当 | noref+point | Add a small badge on the person near the center. | Add anchor 是整个人,没有附着位置('Add a small badge on the person')。 | anchor on the orange shirt chest (see fix above) | 目视 |
| U4 | 严重 | mask 质量 | noref+point | Add a small badge on the person near the center. | U4 mask 形状奇特，呈十字形：除了该男子的头部和橙色衬衫外，其下部的叶瓣还覆盖了他前面两个人的橙色帽子（约源图 y~700-780）。 | 仅对目标男子/衬衫重新分割，排除邻近者的帽子 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a small badge on the person near the center. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8243132`（#984，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 人物/服装层级错误 | noref+mask | Replace the person at the lower right with a blue shirt. | U2 mask 是一个完整的行人（穿深色衣服、走在中下偏右的男子），而该编辑把 'the person' 替换为 'a blue shirt' ——把人替换成衣物。'the person at the lower right' 也有歧义：一位女子就走在他旁边，最右边缘还有另一个人。 | Ref: Replace the man in dark clothes walking beside the woman at the lower right with a woman pushing a stroller.<br>No-ref: Replace the selected person with a woman pushing a stroller.<br>或将 mask 重做为他的深色夹克，并使用：Change the color of the dark jacket of the man walking beside the woman at the lower right to blue. | 目视 |
| U4 | 轻微 | 指代歧义 | ref+mask | Add a small arrow on the sign near the center. | 可见数个店铺招牌(“Chez Moss”餐厅招牌、圆形标志牌、被 mask 的“BEST BAGELS”招牌);“the sign near the center”的区分力较弱。 | Ref: Add a small arrow on the illuminated 'BEST BAGELS' sign above the shop. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+mask | Add a small arrow on the sign near the center. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8290161`（#985，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+box | Change the color of the man near the center to blue. | 'Change the color of the man near the center to blue' 对整个人应用颜色属性；mask 覆盖骑滑板车的整个男子（头、格子衬衫、牛仔裤）。 | Ref: Change the color of the plaid shirt of the man riding the white scooter near the center to blue.<br>No-ref: Change the color of the selected shirt to blue.<br>重新 mask 到格子衬衫上 | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the bicycle at the right with a red bicycle. | “Replace the bicycle at the right with a red bicycle”保持类别；只有颜色变化。 | Ref: Replace the bicycle parked by the pole at the upper right with a red kick scooter.<br>No-ref: Replace the selected bicycle with a red kick scooter.<br>或转为 attribute | 目视 |
| U2 | 轻微 | 指代歧义 | ref+point | Replace the bicycle at the right with a red bicycle. | 'the bicycle at the right':最右侧摊位下还可见另一个自行车轮/自行车货车(x~0.95W, y~0.65H);被 mask 的是停在右上角电线杆旁的小自行车(box [1653,372,1792,519])。 | Ref: Replace the bicycle parked beside the utility pole at the upper right with a red kick scooter. | 目视 |
| U3 | 严重 | 多单元同一物理对象/相互冲突 | noref+point | Remove the motorbike near the center. | U1 男子坐在 U3 的白色踏板车上（U3 box [960,711,1435,1500] 与 U1 box [890,536,1377,1468] 大量重叠）；在编辑骑车人的同时移除踏板车，是相互耦合/冲突的组合（骑车人会悬空）。 | 删除 U3 或 U1；例如选择左侧的彩粉车作为独立物体 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+box | Add a blue logo on the poster at the upper left. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8319146`（#986，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+mask | Change the color of the person near the center to green. | U1 mask（box [986,609,1400,1500]）是一个背对镜头、穿深色夹克的整个男子；'Change the color of the person near the center to green' 是给人改色。 | Ref: Change the color of the black jacket of the man walking near the center to green.<br>No-ref: Change the color of the selected jacket to green.<br>将 mask 重做为夹克 | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | ref+none | Replace the person at the right with a blue jacket. | U2 mask(box [1230,549,1381,1087])是整个穿深色大衣的人;“Replace the person at the right with a blue jacket”把一个人替换成了衣物。“at the right”也不够有力:他位于 0.50W,更靠右还有许多人。 | Ref: Replace the dark coat of the man just right of the central man with a blue jacket.<br>No-ref: Replace the selected coat with a blue jacket.<br>重新 mask 为仅含大衣 | 目视 |
| U3 | 严重 | 指代歧义 | ref+mask | Remove the umbrella at the upper right. | 右上方有许多雨伞：U3 是 0.66W 处的黑色雨伞（box [1468,444,1971,607]）；约 0.85W 处的透明雨伞和大型花卉粉色雨伞更靠右。'the umbrella at the upper right' 有歧义。 | Ref: Remove the black umbrella in the middle distance to the right of the central man. | 目视 |
| U4 | 轻微 | 方位/序数/实例指代错误 | noref+box | Add a small logo on the sign above the stall. | U4 是建筑立面上发光的“WOMENS”字样；其下方并没有摊位，所以“the sign above the stall”不准确。 | Ref: Add a small logo on the illuminated WOMENS sign on the building. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a small logo on the sign above the stall. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8321304`（#987，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | ref+point | Change the color of the girl near the center to yellow. | U1 mask 是中间整个女孩(黑 T 恤、黑裤子);'Change the color of the girl ... to yellow' 是对整个人改色。 | Ref: Change the color of the black T-shirt of the long-haired girl walking in the center to yellow.<br>No-ref: Change the color of the selected T-shirt to yellow.<br>re-mask to her black T-shirt | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | noref+point | Replace the girl at the right with a blue shirt. | U2 mask 是路上穿橙色 T 恤和黑色短裤的整个女孩；'Replace the girl ... with a blue shirt' 是把一个人替换为衣物。 | Ref: Replace the orange T-shirt of the girl walking up the path at the right with a blue hooded sweatshirt.<br>No-ref: Replace the selected T-shirt with a blue hooded sweatshirt.<br>重新 mask 为她的橙色 T 恤 | 目视 |
| U3 | 阻断 | 指代类别与 mask 不符 | ref+box | Remove the blue shirt on the child at the left. | U3 mask（box 624-790, 787-1078）是挂在男孩背上肩头的蓝色手提袋，不是衬衫；男孩的衬衫是黑色的。'Remove the blue shirt on the child at the left' 点错了类别。 | Ref: Remove the blue tote bag hanging on the back of the boy at the left.<br>No-ref: Remove the selected tote bag.<br>scope -> tote bag；ZH: 移除左侧男孩背上的蓝色手提袋。 | 目视 |
| U4 | 严重 | 方位/序数/实例指代错误 | noref+mask | Add a small sign on the railing at the right. | U4 mask 是楼梯顶部两根白色立柱之间的蓝色栏杆板,靠近图像中心(cx=0.51);楼梯右侧还有另一段栏杆,因此“the railing at the right”指向了别处。 | Ref: Add a small sign on the blue railing panel at the top of the stairs. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small sign on the railing at the right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_834249`（#989，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+point | Change the color of the person at the left to blue. | U1 'Change the color of the person at the left to blue' 是给整个人上色（mask 覆盖整个志愿者，包括皮肤、帽子、短裤；box [424,323,900,1340]）；他的衣服本来就是蓝色。 | Ref: Change the color of the blue shorts of the volunteer with the backpack at the left to khaki.<br>No-ref: Change the color of the selected shorts to khaki.<br>重新 mask 为仅短裤。 | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | ref+box | Replace the person at the right with a green jacket. | U2 将右侧整个行走的男孩（box [1959,428,2143,960]）替换为 'a green jacket' ——把人替换成衣物。 | Ref: Change the color of the blue hoodie of the boy walking at the far right to green.<br>No-ref: Change the color of the selected hoodie to green.<br>将 mask 重做为连帽衫，并把 op 改为 attribute。 | 目视 |
| U3 | 严重 | 指代歧义 | noref+mask | Remove the backpack near the right. | “the backpack near the right”:被 mask 的藏青色背包(box [1165,547,1367,855],cx=0.56W)背在中间穿牛仔裤的女子身上;最右侧的男孩也背着背包,更符合“near the right”。 | Ref: Remove the navy backpack of the woman in jeans at the center. | 目视 |
| U4 | 严重 | 指代歧义 | ref+none | Add a hanging sign on the streetlight at the left. | 'the streetlight at the left'：左侧有数盏路灯（例如原图约 x 330 处的高黑杆和约 x 210 处的灯）；mask（box [578,120,698,326]）是左侧志愿者头部正上方的 T 形灯。 | Ref: Add a hanging sign on the T-shaped streetlight directly above the head of the volunteer at the left. | 目视 |

#### `v2-sa_8356934`（#991，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 措辞/文法/描述细节 | ref+box | Change the color of the bell tower near the center to warm beige. | 被 mask 的塔带有一个大钟面；它是钟楼而不是钟塔（bell tower）（仍然唯一，因此目标明确）。 | Ref: Change the color of the brick clock tower near the center to warm beige.<br>No-ref: Change the color of the selected clock tower to warm beige. | 目视 |
| U2 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Remove the lamp post at the left. | 被 mask 的灯柱 [1523,444,1684,1030]（cx=0.73）是右侧、市场顶篷前方的高大双头灯柱。'the lamp post at the left' 与此矛盾，而别处还有更矮的灯柱（例如塔左侧大厅前约 x0.39 和 ~x0.64 处）。 | Ref: Remove the tall double-headed lamp post at the right, in front of the market canopy.<br>将 physical_parent_zh 修正为 右侧路灯，ZH 修正为 移除右侧高大的双头路灯。 | 目视 |

#### `v2-sa_8364417`（#993，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 编辑不合理/不可执行 | ref+box | Replace the motorbike at the right with blue. | 'Replace the motorbike at the right with blue.' 没有物体载荷；被 mask 的 Repsol 橙/白摩托车会被替换成单纯的颜色。 | Ref: Replace the orange Repsol motorbike at the right with a blue bicycle.<br>No-ref: Replace the selected motorbike with a blue bicycle.<br>将载荷设为物体名词。 | 目视 |
| U3 | 严重 | 指代歧义 | noref+mask | Remove the chair near the center. | 九重葛下有十几把相同的红色塑料椅；被 mask 的（box x 847-974）是棕色踏板车左侧最前面的椅子，但“the chair near the center”适用于多把椅子。 | Ref: Remove the front red plastic chair just left of the brown scooter. | 目视 |
| U4 | 严重 | add 锚点不当 | ref+none | Add a flower pot on the plant at the left. | U4 mask 是最左侧一株小型多叶灌木,本来就种在白色花盆里(花盆不在 mask 内)。'Add a flower pot on the plant' 不是自然的宿主-payload 关系。 | Ref: Add a small wooden bird feeder hanging on the potted shrub at the left.<br>No-ref: Add a small wooden bird feeder hanging on the selected plant. | 目视 |

#### `v2-sa_8364723`（#996，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 指代类别与 mask 不符 | noref+box | Change the color of the plaque on the left storefront to blue. | REF 说 'the plaque on the left storefront'。被 mask 的物体（box [98,969,1186,1946]）是前景中央杆子上独立的 'STONE TOWN INFORMATION / THE STORY OF THE CANAL' 解说牌；那里没有店面。其主体本来就是深藏青色，所以 'to blue' 近乎无效。 | Ref: Change the color of the frame of the 'Stone Town Information' sign in the foreground to dark green.<br>No-ref: Change the color of the selected sign to dark green.<br>设置 scope=sign。ZH: 将前景“Stone Town Information”信息牌的边框颜色改为深绿色。 | 目视 |

#### `v2-sa_838336`（#998，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 人物/服装层级错误 | noref+point | Replace the person at the left with a blue coat. | U2 mask 是整个穿红色夹克和黑色紧身裤、正在爬台阶的女子（box [839,1741,926,2041], cx=0.59）。'Replace the person at the left with a blue coat' 是把人替换为衣物，而且她在中心偏右，不在左侧（U3 更靠左）。 | Ref: Change the color of the red jacket of the woman climbing the steps just right of center to blue.<br>No-ref: Change the color of the selected jacket to blue.<br>重新 mask 为夹克并将 op 改为 attribute | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+box | Remove the person near the right. | REF 说 'the person near the right'，但 U3 mask 是左侧台阶上背黑色背包的男子（box [407,1735,565,2084]，cx=0.32）。台阶上有几十个人，所以 REF 也有歧义。 | Ref: Remove the man with a black backpack climbing the steps at the lower left. | 目视 |
| U4 | 严重 | add 锚点不当 | noref+mask | Add a small roof sign on the car at the lower right. | 右下角的 U4 汽车(box [1292,2026,1500,2250])只显示前格栅和部分引擎盖,车顶在画面之外。因此“Add a small roof sign on the car”没有可见的附着位置。 | Ref: Add a small round sticker on the hood of the dark car at the lower-right corner.<br>No-ref: Add a small round sticker on the hood of the selected car. | 目视 |

#### `v2-sa_8403002`（#999，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | ref+none | Change the color of the cook near the center to blue. | U1 mask 是整个厨师（戴粉色头巾、穿深棕色上衣的女子，包括脸和手臂）；'Change the color of the cook to blue' 是人物级属性，没有指明任何衣物。 | Ref: Change the color of the pink headscarf of the cook near the center to blue.<br>No-ref: Change the color of the selected headscarf to blue.<br>重新 mask 到头巾（或深棕色上衣）上 | 目视 |
| U2 | 严重 | 指代歧义 | ref+mask | Replace the bottle at the lower right with a glass jar. | 图像下半部分摆满了许多相似的汽水瓶；U2 是右边缘带淡紫色瓶盖的高瓶（box [1967,971,2219,1500]），但“the bottle at the lower right”也适用于它旁边的其他瓶子。 | Ref: Replace the rightmost tall bottle with a lilac cap at the lower-right edge with a glass jar. | 目视 |
| U3 | 严重 | 指代类别与 mask 不符 | noref+box | Remove the bowl at the upper right. | U3 mask 是装满粉色脆片的大型半透明塑料食品容器/桶(右上角有蓝色盖子区域),不是碗。 | Ref: Remove the translucent plastic container of pink crackers at the right.<br>No-ref: Remove the selected container.<br>scope='container' | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a cushion on the wooden bench at the lower left. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8430103`（#1003，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+box | Change the color of the man near the center to blue. | U1 mask(box [286,359,816,1307])是整个行走的男子;“Change the color of the man near the center to blue”是对人重新着色。他穿着米色条纹长袍和蓝色裤子。 | Ref: Change the color of the beige striped tunic of the man walking near the center to light blue.<br>No-ref: Change the color of the selected tunic to light blue.<br>重新 mask 为仅含长袍 | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the narrow sign above the doorway with a red sign. | U2 'Replace the narrow sign above the doorway with a red sign' 只改变颜色（标牌是红/黄色方格条，在顶部边缘被截断）。mask 是图像顶部边缘的一小块不完整区域。 | Ref: Replace the narrow sign above the doorway with a hanging wooden plank sign.<br>No-ref: Replace the selected sign with a hanging wooden plank sign.<br>或改为属性。 | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | noref+point | Remove the bag at the right. | U3 是夹在中间男子腋下的黑色托特包（box [490,680,689,832]，中心 0.39W），不是“at the right”。它也由 U1 男子携带，并且位于 U1 整个人物区域内（mask 相接，重叠 19 像素）。 | Ref: Remove the black bag carried under the arm of the man walking near the center.<br>同时将 U1 重新 mask 为一件衣物，使包保持独立 | 目视 |
| U4 | 严重 | add 锚点不当 | ref+box | Add a small badge on the man at the far left. | U4 锚点是最左侧部分可见的整个男子(box [0,272,91,598]),没有附着位置;'Add a small badge on the man' 提法不当。 | Ref: Add a small round badge on the chest of the dark jacket of the man at the far left.<br>No-ref: Add a small round badge on the chest of the selected jacket.<br>re-mask to the dark jacket | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+box | Add a small badge on the man at the far left. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8430740`（#1004，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Change the color of the banner at the upper left to red. | U1 mask（box 706-991, 593-846; cx=0.39）是入口上方、上部中间的红色桑德斯上校标志牌。真正符合 'the banner at the upper left' 的物体是左墙上的大型 'MIC DEJUN DE LA KFC' 早餐横幅（或 KFC 字母）。REF 指向了不同的物体和类别。 | Ref: Change the background color of the Colonel Sanders logo panel above the entrance to dark blue.<br>No-ref: Change the background color of the selected logo panel to dark blue.<br>scope -> logo panel；ZH: 入口上方的桑德斯上校标志牌 | 目视 |
| U1 | 严重 | 属性值问题（无变化/含糊） | noref+mask | Change the color of the banner at the upper left to red. | Colonel 标志面板本来就以红色为主，所以 'to red' 几乎不产生可见变化。 | 选择对比色，例如深蓝色 | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | ref+none | Replace the person at the right with a blue jacket. | U2 mask 是坐在右侧野餐长椅上的整个穿深色夹克的男子;“Replace the person at the right with a blue jacket”把人替换成了衣物。 | Ref: Replace the dark jacket of the man seated at the right picnic bench with a blue jacket with a white hood.<br>No-ref: Replace the selected jacket with a blue jacket with a white hood.<br>重新 mask 为他的夹克;或使用结构有变化的其他 payload | 目视 |
| U3 | 严重 | mask 质量 | ref+mask | Remove the food at the left. | U3 mask 是早餐海报上鸡肉吐司三明治的印刷图像，不是真实食物；'Remove the food at the left' 对海报图形的描述有误。 | Ref: Remove the printed chicken toast sandwich from the left side of the breakfast banner.<br>No-ref: Remove the selected printed sandwich.<br>范围 -> printed sandwich image | 目视 |
| U4 | 严重 | 指代歧义 | noref+box | Add a small vase on the picnic table near the center. | 露台上有许多桌子和长椅；U4 是穿灰衣男子面前的一张小圆形独脚桌（box 1076-1199）。“the picnic table near the center”适用于多张桌子。 | Ref: Add a small vase on the round pedestal table in front of the man in the gray hoodie near the entrance. | 目视 |

#### `v2-sa_8448822`（#1005，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | ref+point | Change the color of the man at the right to blue. | Mask 覆盖右下角一位完整的坐着的男子(灰色鸭舌帽、黑 T 恤)。'Change the color of the man to blue' 是对人的颜色编辑。'The man at the right' 在右侧有许多男子的人群中也有歧义。 | Ref: Change the color of the black T-shirt of the seated man in a gray flat cap at the lower right to blue.<br>No-ref: Change the color of the selected T-shirt to blue.<br>Re-mask to the T-shirt only; set scope 'T-shirt'. | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | noref+point | Replace the man near the center with a red coat. | 'Replace the man near the center with a red coat' 是把整个人（站立的、穿藏青色长袖上衣、双手叉腰的男子）替换为一件衣物，这是不合理的。在密集人群中 'The man near the center' 也很弱。 | Ref: Replace the navy long-sleeve top of the standing man with hands on hips, near the center, with a red hooded raincoat.<br>No-ref: Replace the selected top with a red hooded raincoat.<br>重新 mask 为仅上衣；将 scope 设为 'top'。 | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | ref+box | Remove the roof at the upper left. | mask 是脚手架侧翼顶部的一条红色瓦屋顶（box 481-845 x 579-677）。移除建筑的屋顶会留下无定义的结构。'The roof at the upper left' 也与最左边缘（约 0.03W）建筑更大的红瓦屋顶产生歧义。 | Ref: Change the color of the red tiled roof strip beside the small green turret at the upper left to slate gray.<br>No-ref: Change the color of the selected roof to slate gray.<br>将 remove 转为 attribute。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small flag on the dome near the upper center. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8489034`（#1006，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | ref+none | Change the color of the person at the left to green. | U1 对整个人应用了“color ... to green”(mask 覆盖了整个穿蓝衬衫、卡其裤的灰发男子,box [1744,755,1948,1227])。 | Ref: Change the color of the light blue shirt of the gray-haired man with hands on hips on the right to green.<br>No-ref: Change the color of the selected shirt to green.<br>重新 mask 为仅含衬衫。 | 目视 |
| U1 | 阻断 | 方位/序数/实例指代错误 | ref+none | Change the color of the person at the left to green. | REF 称 'the person at the left'，但被 mask 的男子在图像右侧 cx=0.82W（只有 U2 更靠右）。 | Ref: ... the gray-haired man with hands on hips on the right ... | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | ref+mask | Replace the person at the right with a blue jacket. | U2 将右边缘的整个女士（黑上衣、牛仔裤；box [2052,800,2234,1292]）替换为“a blue jacket”——用衣服替换人。 | Ref: Replace the black T-shirt of the woman in jeans at the right edge with a blue denim jacket.<br>No-ref: Replace the selected T-shirt with a blue denim jacket.<br>重新对 T 恤做 mask。 | 目视 |
| U3 | 严重 | 指代歧义 | noref+box | Remove the flag near the center. | 'the flag near the center':中心附近飘着几面旗(同一杆上的一面黑旗、美国国旗);mask(box [789,523,888,589])是 0.37W 处旗杆顶端的红色三角旗。 | Ref: Remove the red flag at the top of the tall flagpole above the crowd, left of the Capitol dome. | 目视 |
| U4 | 严重 | 指代歧义 | ref+point | Add a white arrow on the sign near the center. | 'the sign near the center' 适用于人群中高举的许多抗议标牌；mask 是旗杆左侧一块很小的白色标语牌（box [787,743,823,771]，面积 0.0003）。 | Ref: Add a white arrow on the small white 'AGAINST TYRANNY' placard held up in the crowd just below the tall flagpole. | 目视 |

#### `v2-sa_8532764`（#1007，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+point | Change the color of the person near the center to blue. | 'Change the color of the person near the center to blue' ——mask 实际上是蒙眼男子的白色亚麻衬衫；REF 点名的却是人。 | Ref: Change the color of the white linen shirt of the blindfolded man in the center to blue.<br>No-ref: Change the color of the selected shirt to blue.<br>scope='shirt'。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+box | Replace the flag at the left with a yellow flag. | 将红/粉色旗帜替换为“a yellow flag”纯属重新着色。 | Ref: Change the color of the red flag at the left to yellow.<br>No-ref: Change the color of the selected flag to yellow.<br>op=attribute。 | 目视 |
| U3 | 严重 | 指代歧义 | noref+mask | Remove the bicycle at the lower right. | 右侧停着许多自行车；'the bicycle at the lower right' 不唯一。mask 是橙色自行车（并似乎延伸到相邻白色自行车的车轮上）。 | Ref: Remove the orange bicycle at the front of the parked bikes on the right.<br>检查 mask 是否包含相邻白色自行车的车轮。 | 目视 |

#### `v2-sa_8586145`（#1010，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | ref+mask | Change the color of the person in the plaid shirt at the left to blue. | U1 mask 是敞开的棕/黑格子法兰绒衬衫（box 1453-1580 x，中心 0.67W），但 REF 写的是“Change the color of the person in the plaid shirt at the left to blue”（人物级别属性）。它也不在左侧（0.67W，中心偏右）。 | Ref: Change the color of the brown plaid shirt of the man in the Black Sabbath T-shirt right of center to blue.<br>No-ref: Change the color of the selected shirt to blue.<br>scope='shirt'。 | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | noref+box | Replace the person in the shirt left of center with a yellow jacket. | U2 mask 是右前方戴绿帽男子的海军蓝 'Four Aces' T 恤(box 1901-2062 x,中心 0.88W);REF 'Replace the person in the shirt left of center with a yellow jacket' 是用衣服替换一个人,且位置在右侧而不是中心偏左。 | Ref: Replace the navy graphic T-shirt of the man in the green cap at the front right with a yellow jacket.<br>No-ref: Replace the selected T-shirt with a yellow jacket.<br>scope='T-shirt'. | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+point | Remove the bag near the left. | U3 mask 是穿浅色罩衫的女子（中心 0.65W，右半部）所拎的带绿色标志的白色塑料购物袋。'the bag near the left' 是错误的，并且适用于其他袋子（例如 ~0.48W 处拎着的花纹袋）。 | Ref: Remove the white plastic bag with a green logo carried by the woman in the light blouse right of center. | 目视 |
| U4 | 阻断 | 多单元同一物理对象/相互冲突 | noref+point | Add a small logo on the cap near the left. | U4 mask 是绿色棒球帽（box 1953-2007 x），由 U2 的T恤所属的同一名男子佩戴；一个人身上有两个单元。REF 'the cap near the left' 也是错的（0.88W，在右侧）。 | Ref: Add a small white logo on the green cap at the front right.<br>删除 U4，或把 U2 移到另一个人身上。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a small logo on the cap near the left. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8608311`（#1012，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+box | Change the color of the person at the right to blue. | REF 'Change the color of the person at the right to blue' 指向整个人,但 mask 只覆盖长发女子的海军蓝绗缝夹克(x1179-1293);而且夹克本来就是海军蓝,所以 'to blue' 几乎无变化。 | Ref: Change the color of the navy quilted jacket of the long-haired woman at the right to burgundy.<br>No-ref: Change the color of the selected jacket to burgundy.<br>set scope/category to 'jacket' | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the window at the left with a blue window. | 'Replace the window at the left with a blue window' 纯属换色；此外 'the window at the left' 适用于左侧建筑上的几十扇窗户。被 mask 的那扇是一楼/二层带栏杆的窗户（x153-229）。 | Ref: Replace the barred window on the left building with a wooden door.<br>No-ref: Replace the selected window with a wooden door.<br>或使 REF 更具体：'the barred window with vertical bars on the left building' | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+box | Add a small arrow on the sign near the center. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8680793`（#1016，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+point | Change the color of the vendor at the left to blue. | U1 mask 是整个坐着的摊贩（头、紫色格子衬衫、绿色方格上衣、纱笼、双手）；'Change the color of the vendor to blue' 没有指明衣物。而且她坐在中间（cx=0.44W），最左边还有另一个人，所以 'at the left' 不准确。 | Ref: Change the color of the purple plaid shirt of the seated vendor in the center to blue.<br>No-ref: Change the color of the selected shirt to blue.<br>将 mask 重做为仅紫色格子衬衫；scope='shirt' | 目视 |
| U2 | 严重 | 指代歧义 | ref+box | Replace the fish near the lower left with a larger fish. | U2 是柜台前排的一条银鲳,柜台上摆满了几十条类似的鱼(box [350,1519,639,1724]);“the fish near the lower left”不能将其单独指出(模糊的鱼也填满了真正的左下区域)。 | Ref: Replace the round silver pomfret at the front edge of the counter, just below the vendor's left knee, with a red crab.<br>No-ref: Replace the selected fish with a red crab. | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+box | Replace the fish near the lower left with a larger fish. | 'Replace the fish with a larger fish' 保持类别，只改变大小（幅度未指定）；不是结构性替换。 | Ref: Replace the round silver pomfret at the front edge of the counter, just below the vendor's left knee, with a red crab.<br>No-ref: Replace the selected fish with a red crab. | 目视 |

#### `v2-sa_8731521`（#1018，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | ref+box | Change the color of the person at the lower left to blue. | REF “Change the color of the person at the lower left to blue”针对的是整个人,但 mask 只是左侧行走男子的藏青色 T 恤(box [239,1028,385,1204]);该衬衫本来就是藏青色,所以“to blue”也近乎空操作。 | Ref: Change the color of the navy T-shirt of the man walking beside the children's bicycle at the lower left to red.<br>No-ref: Change the color of the selected T-shirt to red.<br>将 scope 设为 T-shirt | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the bicycle at the lower left with a red bicycle. | 'Replace the bicycle at the lower left with a red bicycle'：类别相同，只改变颜色（两个女孩骑的黑色儿童自行车）。 | Ref: Change the color of the black bicycle ridden by two girls at the lower left to red.<br>No-ref: Change the color of the selected bicycle to red.<br>改为属性 | 目视 |
| U3 | 轻微 | 指代歧义 | ref+none | Remove the sign at the right. | “the sign at the right”（ref+none）指的是建筑立面上的一个很小的红色 LED 标牌（box [1976,893,2055,913]）；其他标牌（圆形交通标志、招牌）也在右侧。 | Ref: Remove the red LED sign on the white building at the right, behind the large tree. | 目视 |
| U4 | 轻微 | 指代类别与 mask 不符 | ref+mask | Add a string of lights on the canopy at the right. | REF 称目标为 'canopy',但 mask 是右侧路边撑在人们头上的粉色庭院伞/遮阳伞。 | Ref: Add a string of lights along the edge of the pink umbrella at the right.<br>No-ref: Add a string of lights along the edge of the selected umbrella.<br>scope -> umbrella | 目视 |

#### `v2-sa_876819`（#1021，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | ref+point | Change the color of the performer near the center to green. | Mask 覆盖领舞者的服装裙(亮片紧身上衣加巨大的黄绿和青色褶边裙),而不是她的身体。REF 'Change the color of the performer near the center to green' 在人的层面操作,scope 为 'person'。绿色也已经是裙子的主色之一。 | Ref: Change the color of the ruffled yellow-green skirt of the dancer twirling in the center to royal purple.<br>No-ref: Change the color of the selected dress to royal purple.<br>Set scope to 'dress'. | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | noref+point | Replace the performer at the left with a blue costume. | mask 覆盖的是左侧行走的女子的白色无袖连衣裙（box 387-541）。指令把 'the performer'（一个人）替换为 'a blue costume'（衣物）。'The performer at the left' 在左侧众多表演者中也有歧义。 | Ref: Replace the white sleeveless dress of the curly-haired woman walking in front at the left with a blue sequined samba costume.<br>No-ref: Replace the selected dress with a blue sequined samba costume.<br>将 scope 设为 'dress'。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small logo on the sign at the far right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8802184`（#1023，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+point | Change the color of the athlete at the left to blue. | 'Change the color of the athlete at the left to blue' —— mask 实际是左侧球员的蓝粉相间无袖球衣；REF 指的是整个人（而且球衣已经大部分是蓝色）。 | Ref: Change the color of the blue-and-pink sleeveless jersey of the athlete at the left to white.<br>No-ref: Change the color of the selected jersey to white.<br>scope='jersey'。 | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | ref+box | Replace the athlete near the center with a yellow jersey. | “Replace the athlete near the center with a yellow jersey”是用衣服替换人；mask 是中央球员的栗色守门员球衣。 | Ref: Replace the maroon short-sleeved jersey of the goalkeeper near the center with a yellow hooded training jacket.<br>No-ref: Replace the selected jersey with a yellow hooded training jacket.<br>scope='jersey'。 | 目视 |
| U3 | 严重 | 指代歧义 | noref+mask | Remove the banner at the lower left. | 'the banner at the lower left' —— 球场左侧有几块广告牌;mask 的是草地上小的深色 'Chang' 牌(box [553,959,728,996])。 | Ref: Remove the dark Chang advertising board on the grass at the left. | 目视 |
| U4 | 严重 | 指代歧义 | ref+none | Add a red label on the water bottle near the center. | 'the water bottle near the center'——两个箱子里有大约二十个相同的瓶子；mask 是一个瓶子，位于左边箱子前排左起第二个。 | Ref: Add a red label on the second water bottle from the left in the front row of the left crate. | 目视 |

#### `v2-sa_8809691`（#1024，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 属性值问题（无变化/含糊） | ref+mask | Change the color of the streetlight at the left to black. | 被 mask 的双灯笼路灯 [421,635,516,1154] 本来就是黑色（黑色灯杆和黑色灯笼框）；'change the color ... to black' 无效，无法评分。 | Ref: Change the color of the streetlight at the left to dark green.<br>No-ref: Change the color of the selected streetlight to dark green. | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the glass door at the right with a wooden door. | 被 mask 的物体是木框双开玻璃门;“a wooden door”保持相同的门类型/门框,仅改变门板材质。 | Ref: Replace the glass door at the right with a metal roll-up shutter.<br>No-ref: Replace the selected door with a metal roll-up shutter.<br>或转换为 attribute:material=solid wood。 | 目视 |
| U3 | 轻微 | mask 质量 | ref+point | Remove the planter at the lower left. | 花槽 mask [209,936,368,1041] 只覆盖深色砖纹箱体，不含箱中生长的灌木；用此 mask 移除 'the planter' 会让植物悬空（范围未说明）。 | Ref: Remove the planter at the lower left together with its shrubs.<br>No-ref: Remove the selected planter together with its shrubs.<br>或将 mask 扩展到包含植物。 | 目视 |
| U4 | 严重 | 指代歧义 | noref+point | Add a small bracket on the downspout near the center. | 中心附近有两根几乎并排的落水管：被 mask 的 [1092,265,1126,882] 从上方屋顶通到地面，另一根从较低的瓦屋顶檐口约 x1045（原图）处下来，也在中心附近。“the downspout near the center”对两者都适用。 | Ref: Add a small bracket on the tall downspout that runs from the upper roof edge down to the ground near the center. | 目视 |

#### `v2-sa_8830987`（#1026，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+box | Change the color of the person at the left to blue. | U1 mask 是男子的短袖蓝色亚麻衬衫（box 103-498 x, 251-847 y），但 REF/NOREF 说 'Change the color of the person at the left to blue'。衬衫本来也是蓝色，所以该编辑无效。 | Ref: Change the color of the blue linen shirt of the man at the left to white.<br>No-ref: Change the color of the selected shirt to white.<br>scope='shirt'。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the chair at the right with a red chair. | 将藤编小酒馆椅替换为“a red chair”保持类别不变;仅是重新着色。 | Ref: Replace the bistro chair just behind the right end of the fruit stall with a wooden barrel.<br>No-ref: Replace the selected chair with a wooden barrel. | 目视 |
| U2 | 严重 | 指代歧义 | ref+point | Replace the chair at the right with a red chair. | 摊位后方的咖啡馆右半边有几十把相同的棕色藤制小酒馆椅；'the chair at the right' 无法单独指出被 mask 的椅子（box 1574-1809 x，正好在摊位金属碗后面）。 | Ref: Replace the bistro chair directly behind the stacked metal bowls on the fruit stall with a wooden barrel. | 目视 |
| U3 | 严重 | 指代歧义 | noref+point | Remove the metal bowl near the center. | 摊位上有几个金属碗（被 mask 的在摊主手边的秤旁，另一个就在其右侧，更右处还有一摞）；“the metal bowl near the center”有歧义。 | Ref: Remove the metal bowl on the scale between the two vendors' hands. | 目视 |
| U4 | 严重 | 指代歧义 | ref+box | Add a small price tag on the fruit at the right. | U4 mask 的是一箱相同甜瓜中的一个哈密瓜(box 1715-1836 x),更右侧还有橙子;'the fruit at the right' 有歧义。 | Ref: Add a small price tag on the leftmost cantaloupe in the melon crate on the right. | 目视 |

#### `v2-sa_886183`（#1028，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | ref+point | Change the color of the child at the left to blue. | REF 'Change the color of the child at the left to blue' 针对整个孩子，但 mask 只覆盖左侧长发孩子的白色星星印花短袖衬衫。 | Ref: Change the color of the white star-print shirt of the long-haired child at the left to blue.<br>No-ref: Change the color of the selected shirt to blue.<br>将 scope/category 设为 'shirt' | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | noref+point | Replace the child at the right with a yellow shirt. | REF“Replace the child at the right with a yellow shirt”是用衣服替换人；mask 实际覆盖的是男孩的芥末黄花纹衬衫，所以将其替换为“a yellow shirt”也是无操作的改色。 | Ref: Replace the mustard-yellow shirt of the boy at the right with a green hooded sweatshirt.<br>No-ref: Replace the selected shirt with a green hooded sweatshirt.<br>将 scope/category 设为 'shirt' | 目视 |
| U3 | 轻微 | 指代歧义 | ref+box | Remove the flower at the lower right. | 'the flower at the lower right' —— 右侧有多朵橙色万寿菊(如 ~0.80W,0.75H);被 mask 的是男孩牛仔裤旁一朵失焦的小橙花(0.79W,0.87H)。 | Ref: Remove the small orange flower just right of the boy's jeans at the lower right. | 目视 |

#### `v2-sa_8871336`（#1029，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 属性值问题（无变化/含糊） | ref+none | Change the color of the boat near the center to white. | 'Change the color of the boat near the center to white'：被 mask 的河轮（box [747,413,1629,867]）本来就是带蓝色条纹的白色，所以该编辑是无操作。mask 还包含了站在船体前面的两块黄色 '18 MOORING' 标牌。 | Ref: Change the color of the hull of the white river cruise ship near the center to dark navy blue.<br>No-ref: Change the color of the selected boat to dark navy blue.<br>将两块 '18 MOORING' 标牌从 U1 mask 中排除。 | 目视 |
| U2 | 阻断 | replace 实为属性修改 | ref+mask | Replace the lamp post at the left with black. | 'Replace the lamp post at the left with black.' 用单纯的颜色作为 replace payload，而华丽的双灯笼灯柱本来就是黑色，因此该编辑格式错误且实质无效。 | Ref: Replace the ornate double-lantern lamp post at the left with a modern single-arm steel streetlight.<br>No-ref: Replace the selected lamp post with a modern single-arm steel streetlight.<br>ZH: 将左侧的华丽双灯头灯柱替换为一根现代单臂钢制路灯。 | 目视 |
| U3 | 阻断 | 指代类别与 mask 不符 | noref+box | Remove the small sign at the right. | U3 mask(box [1629,615,1658,667])覆盖的是桥旁远处的三角形玻璃屋顶塔/构筑物,而不是标志。附近真正的小标志(红色“17”牌和约 x=1585-1600 处的竖直白色标志)未被 mask。 | Ref: Remove the small triangular glass tower beside the bridge at the right.<br>No-ref: Remove the selected structure.<br>要么将 scope 改为“glass tower”,要么重新 mask 为红色“17”标志;鉴于其极小的尺寸(面积 0.0003),删除该单元也合理。 | 目视 |

#### `v2-sa_8874867`（#1030，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+point | Change the color of the chair near the lower center to red. | U1 是位于 0.53W,0.92H 的高深色木制吧台凳；下方中部户外桌周围有几张类似的木凳，而且它是凳子而不是椅子。 | Ref: Change the color of the tall wooden stool standing against the green wall to red.<br>No-ref: Change the color of the selected stool to red.<br>category -> stool | 目视 |
| U2 | 阻断 | 编辑不合理/不可执行 | ref+box | Replace the flower at the lower left with yellow. | Replace payload 只是一个单纯的颜色：'Replace the flower at the lower left with yellow.' U2 是左下方叶丛中的一朵粉色美人蕉花。 | Ref: Replace the pink flower at the lower left with a yellow sunflower.<br>No-ref: Replace the selected flower with a yellow sunflower.<br>ZH: 将左下方的粉色花朵替换为一朵黄色向日葵。 | 目视 |
| U4 | 严重 | 编辑不合理/不可执行 | ref+none | Add a warm glow on the globe lamp near the center. | Add payload 'a warm glow' 是光照,不是具体物体。另外屋檐下挂着三个相同的白色球形灯;U4 是最左边那个(0.50W),所以 'near the center' 有歧义。 | Ref: Add a small brass cap on top of the leftmost of the three hanging globe lamps.<br>No-ref: Add a small brass cap on top of the selected globe lamp. | 目视 |

#### `v2-sa_8910733`（#1032，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | mask 质量 | ref+box | Change the color of the bicycle near the center to black. | U1 自行车 mask 还包含附带的前篮和黑色 OXFORD 驮包，并填满了后轮盘，包括透过辐条看到的墙；此时 'change the color of the bicycle to black' 对本来就是黑色的驮包有歧义。 | Ref: Change the color of the white frame of the bicycle near the center to black.<br>可选：从 mask 中排除驮包/车篮 | 目视 |
| U2 | 阻断 | mask 质量 | noref+mask | Replace the brick wall at the right with a white wall. | U2 mask 是墙面右上方的单块砖（box [1847,321,2102,407]，面积 0.0055），而 REF/scope 是“the brick wall at the right”。墙是整个背景；mask 与指令描述的范围不同（一块砖 vs. 一面墙）。 | Ref: Replace the single orange brick at the upper right of the wall, above the round black wall plate, with a small blue ceramic tile.<br>No-ref: Replace the selected brick with a small blue ceramic tile.<br>scope='brick'；或删除该 unit（整面墙的替换是不适定的） | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the brick wall at the right with a white wall. | 'Replace the brick wall with a white wall' 是同一类别的改色/材质变化。 | see fix above (structural replacement of one brick) or convert to attribute | 目视 |

#### `v2-sa_8915261`（#1033，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | ref+none | Change the color of the banner at the upper left to blue. | U1 mask 是右上方（cx=0.94）的竖直 'Burlington Hotel' 横幅，但 REF/ZH 写的是 'upper left'；左上方挂着一条相同的横幅，因此 REF 指向了错误的实例。此外两条横幅本来就是藏青色，所以 'change the color to blue' 近乎无操作。 | Ref: Change the color of the hanging Burlington Hotel banner at the upper right to burgundy.<br>No-ref: Change the color of the selected banner to burgundy.<br>ZH: 将右上方悬挂的Burlington Hotel横幅的颜色改为酒红色。 | 目视 |
| U2 | 阻断 | 编辑不合理/不可执行 | ref+mask | Replace the shoe at the lower center with a white sneaker. | U2 mask 是行走女子的后脚（画面右侧）鞋子，本来就是白色运动鞋；'Replace the shoe ... with a white sneaker' 无效。'the shoe at the lower center' 也适用于她的另一只白色运动鞋（前脚，画面左侧）。 | Ref: Replace the white sneaker on the rear (image-right) foot of the woman walking across the square with a black leather ankle boot.<br>No-ref: Replace the selected shoe with a black leather ankle boot. | 目视 |

#### `v2-sa_8945299`（#1034，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+box | Change the color of the person at the right to blue. | REF “Change the color of the person at the right to blue”点名的是整个人;mask 只是最右侧年轻男子的灰/白色插肩袖 T 恤(box [2083,1014,2190,1209])。 | Ref: Change the color of the raglan T-shirt of the young man standing at the far right to blue.<br>No-ref: Change the color of the selected T-shirt to blue.<br>scope -> T-shirt | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the thatched roof at the left with a dark roof. | 'Replace the thatched roof at the left with a dark roof'：载荷是仅以颜色描述的屋顶；茅草屋顶本来就是深灰色，因此编辑是含糊的改色/近乎无变化。 | Ref: Replace the thatched roof at the left with a red clay-tile roof.<br>No-ref: Replace the selected roof with a red clay-tile roof. | 目视 |
| U4 | 严重 | 指代歧义 | ref+box | Add a small tag on the handbag at the right. | “the handbag at the right”：被 mask 的物体是穿青绿色衬衫男子携带的黑色小单肩包（box [1808,1040,1847,1083]）；走在他旁边的女士提着稍微更靠右的粉色手提包，更符合“handbag at the right”。 | Ref: Add a small tag on the black shoulder bag of the man in the teal shirt walking on the path at the right.<br>No-ref: Add a small tag on the selected bag. | 目视 |

#### `v2-sa_8963199`（#1036，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 属性值问题（无变化/含糊） | ref+point | Change the color of the van near the center to white. | U1 mask 是男孩们身后的白色梅赛德斯 Sprinter 厢式车；它本来就是白色，所以 'Change the color ... to white' 无效。此外，紧靠其左侧还有一辆深灰色厢式车，所以 'the van near the center' 有歧义。 | Ref: Change the color of the white high-roof van behind the boy in the blue T-shirt to dark red.<br>No-ref: Change the color of the selected van to dark red. | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+point | Replace the traffic sign at the upper right with a blue sign. | U2 是绿白相间的自行车路线指示牌;“Replace ... with a blue sign”仅改变颜色。 | Ref: Replace the green cycle-route sign at the upper right with a round blue mandatory-bicycle-path sign.<br>No-ref: Replace the selected traffic sign with a round blue mandatory-bicycle-path sign. | 目视 |
| U3 | 严重 | 指代歧义 | ref+box | Remove the bicycle near the center. | 过街处站着六个带自行车的男孩；U3（box 1088-1189）是看手机的黑 T 恤男孩扶着的自行车。'the bicycle near the center' 至少符合三辆自行车。 | Ref: Remove the bicycle held by the boy in the black T-shirt looking at his phone. | 目视 |
| U4 | 严重 | 指代歧义 | noref+mask | Add a small badge on the shirt near the center. | 中心附近有几个男孩穿着衬衫（红、黑、青柠、蓝）；U4 是灰色面包车前骑在自行车上坐着的男孩的淡青柠绿 T 恤。“the shirt near the center”不唯一。 | Ref: Add a small round badge on the chest of the pale lime-green T-shirt of the boy on the bike in front of the gray van. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small badge on the shirt near the center. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9013170`（#1040，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代歧义 | ref+box | Change the color of the SUV at the lower left to blue. | 左下方还停着其他 SUV（例如更靠左 ~x0.05 处的灰色 SUV）；被 mask 的深灰色 SUV [375,1041,698,1235] 是紧靠公交车后面的那辆。大体上可识别为最近的一辆，但较宽松。 | Ref: Change the color of the dark gray SUV parked directly behind the bus to blue.<br>ZH 也把 SUV 说成 轿车；应使用 SUV/越野车。 | 目视 |
| U2 | 阻断 | replace 实为属性修改 | noref+mask | Replace the convertible at the lower left with a red convertible. | 被 mask 的敞篷车 [210,1081,376,1201] 本来就是红色经典敞篷车（野马风格）；'Replace ... with a red convertible' 实质无效，无法评分。 | Ref: Replace the red convertible at the lower left with a white delivery van.<br>No-ref: Replace the selected convertible with a white delivery van. | 目视 |
| U3 | 阻断 | 指代歧义 | ref+none | Remove the banner at the left. | 正式输入为 ref+none,但左侧灯杆上并排挂着两面相同的红白蓝横幅;mask [271,808,312,924] 是这一对中右边的那面。“the banner at the left”无法挑出它。 | Ref: Remove the right one of the two banners hanging on the lamp pole at the left.<br>ZH:移除左侧灯杆上两面横幅中右边的那一面。 | 目视 |
| U4 | 严重 | 指代歧义 | ref+mask | Add a flower box on the window near the center. | 砖砌立面有一排相同的窄拱窗；'the window near the center' 符合多扇。被 mask 的 [842,586,877,758] 是红砖建筑上层最右边的拱窗，正好在灯排上方。 | Ref: Add a flower box on the rightmost narrow arched window of the red-brick building near the center. | 目视 |

#### `v2-sa_9015358`（#1041，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+point | Replace the sedan near the center with a blue sedan. | U2 mask（box [0,1396,149,1734]，cx=0.05）是图像最左边缘被截断的灰色轿车，位于树干左侧；REF/ZH 写的是“near the center”（中间附近）。树干占据中心。 | Ref: Replace the gray sedan partly visible at the far left edge with a white delivery van.<br>No-ref: Replace the selected sedan with a white delivery van.<br>ZH: 将最左侧边缘露出的灰色轿车替换为一辆白色厢式货车。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the sedan near the center with a blue sedan. | Payload 'a blue sedan' 把灰色轿车替换成另一种颜色的轿车 —— 纯改色。 | use a structurally different payload (e.g. a white delivery van) or convert to attribute (color blue) | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+box | Add a small flower on the stone tile at the lower right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9033026`（#1042，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+mask | Change the color of the person at the right to blue. | U1 mask 是右边缘女子的米色风衣（box 1792-1970 x），但 REF 写的是 'Change the color of the person at the right to blue'。 | Ref: Change the color of the beige coat of the woman at the right edge to blue.<br>No-ref: Change the color of the selected coat to blue.<br>scope='coat'。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the package at the lower left with a blue package. | 'Replace the package ... with a blue package' 保持类别；仅改色。 | Ref: Replace the bottom oat box at the front-left corner of the stack with a wicker basket.<br>No-ref: Replace the selected package with a wicker basket. | 目视 |
| U2 | 严重 | 指代歧义 | ref+none | Replace the package at the lower left with a blue package. | 左下方是由几十个相同的“oat”箱子组成的托盘堆;被 mask 的是左前列的最底下一个箱子(box 64-216 x,1200-1500 y)。“the package at the lower left”适用于许多个。mask 在该列顶部还有一个很小的杂散碎片。 | Ref: Replace the bottom oat box of the front-left column of the stack with a wicker basket.<br>移除 mask 的杂散碎片。 | 目视 |
| U3 | 严重 | 方位/序数/实例指代错误 | ref+mask | Remove the label near the center. | U3 mask 是 KIRKLAND DELI 招牌上方混凝土柱上贴的白色价签（中心 0.26W, 0.51H）；它位于场景左上部，而不是 'near the center'，且还有其他标签/标牌。 | Ref: Remove the white price label on the pillar next to the KIRKLAND DELI sign. | 目视 |
| U4 | 严重 | 指代类别与 mask 不符 | noref+box | Add a small logo on the bag near the center. | U4 mask（box 633-694 x, 1053-1233 y）只是横跨中偏左男子绿色抓绒衣的卡其色肩带；包本身不可见/未被 mask。“Add a small logo on the bag near the center”针对的包并不在 mask 区域内。 | Ref: Add a small metal buckle on the khaki shoulder strap of the man in the green fleece jacket.<br>No-ref: Add a small metal buckle on the selected strap.<br>scope='strap'。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a small logo on the bag near the center. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9042900`（#1044，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代类别与 mask 不符 | ref+none | Change the color of the sedan near the center to red. | REF 称被 mask 的车辆为“the sedan near the center”,但它是 x848-1266 处的白色紧凑型 SUV(Kia Sportage);附近有真正的轿车(深色 Hyundai 等),因此“sedan”可能绑定到另一辆车。 | Ref: Change the color of the white SUV in the front lane near the center to red.<br>No-ref: Change the color of the selected SUV to red.<br>category -> SUV | 目视 |
| U2 | 阻断 | 编辑不合理/不可执行 | ref+mask | Replace the vehicle at the left with blue. | 'Replace the vehicle at the left with blue' —— replace 载荷只是颜色，没有物体；编辑毫无意义。被 mask 的物体是左边缘一辆部分可见的白色小型货车。 | Ref: Replace the white minivan at the left edge with a blue city bus.<br>No-ref: Replace the selected car with a blue city bus.<br>或属性：Change the color of the white minivan at the left edge to blue. | 目视 |
| U3 | 严重 | 指代歧义 | noref+box | Remove the banner near the top. | “the banner near the top”——顶部有两对白色旗杆横幅（U3 一对在 0.44W，U4 一对在 0.10W）；REF 没有区分它们，并且 mask 覆盖的是一根杆上的一对横幅，而不是一面横幅。 | Ref: Remove the pair of white banners on the lamp pole above the white SUV.<br>No-ref: Remove the selected banners.<br>scope -> 'banners'（一对） | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a small logo on the banner at the upper left. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9066871`（#1045，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | replace 实为属性修改 | ref+box | Replace the streetlight at the right with black. | 'Replace the streetlight at the right with black.' 用一个单纯的颜色作为 replace payload,而被 mask 的灯笼式路灯(box [1738,366,1841,1212])本来就是黑色,所以编辑格式错误且无变化。 | Ref: Replace the black lantern streetlight at the right with a modern silver LED streetlight.<br>No-ref: Replace the selected streetlight with a modern silver LED streetlight.<br>ZH: 将右侧的黑色灯笼式路灯替换为一根现代银色LED路灯。 | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | noref+mask | Remove the coat at the lower left. | U3 移除的是左下方女子所穿的黑色羽绒服（box [234,1168,416,1424]）。移除所穿衣物会留下未定义的身体/内层衣物。'the coat at the lower left' 也只说了外套而没有说穿着者。 | Ref: Change the color of the black puffer jacket of the woman at the lower left to burgundy.<br>No-ref: Change the color of the selected coat to burgundy.<br>将操作从 remove 改为 attribute。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+none | Add a small arrow on the sign at the lower right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9071097`（#1048，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+box | Change the color of the performer near the center to blue. | U1 mask 只是表演者的白色长袖衬衫（box [1194,545,1516,835]），但 REF/NOREF/scope 写的是“the performer”/“the selected person”——即人物级别的改色，没有指明衣物，与 mask 层级不匹配。 | Ref: Change the color of the white shirt of the performer with the microphone to blue.<br>No-ref: Change the color of the selected shirt to blue.<br>scope='shirt' | 目视 |
| U2 | 严重 | 指代歧义 | ref+point | Replace the shirt at the left with a red shirt. | U2 mask 是左侧人群中一位年轻女子的黑色 'VICTORIA'S... GIRLS' 印花 T 恤(box [96,641,238,746]);左侧有许多衬衫(牛仔夹克、海军蓝衬衫),所以 'the shirt at the left' 无法识别它。 | Ref: Replace the black graphic T-shirt of the girl with clasped hands at the left of the crowd with a red hooded sweatshirt.<br>No-ref: Replace the selected shirt with a red hooded sweatshirt. | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the shirt at the left with a red shirt. | 'Replace the shirt with a red shirt' 纯属同一衣物类型的换色。 | Ref: Replace the black graphic T-shirt of the girl with clasped hands at the left of the crowd with a red hooded sweatshirt.<br>No-ref: Replace the selected shirt with a red hooded sweatshirt. | 目视 |
| U3 | 严重 | 指代歧义 | noref+point | Remove the sign near the center. | U3 mask 是白色建筑门口上方的金色花体 'Кофейня Ферзь' 字样（cx=0.76W）。'the sign near the center' 不准确，而且同样适用于街道名牌和大型紫色横幅。 | Ref: Remove the gold cursive cafe lettering sign above the doorway on the white building.<br>相应更新 ZH | 目视 |
| U4 | 轻微 | 编辑不合理/不可执行 | ref+box | Add a small flower on the potted plant at the right. | 右边缘的 U4 悬挂花篮本来就开满了红/粉色的花,因此“add a small flower”几乎无法验证。 | Ref: Add a small white butterfly ornament on the hanging flower basket at the right edge.<br>No-ref: Add a small white butterfly ornament on the selected potted plant. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+box | Add a small flower on the potted plant at the right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9086959`（#1049，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 属性值问题（无变化/含糊） | noref+mask | Change the color of the banner near the top to blue. | U1 mask 是靠近顶部粉色建筑上的长方形店铺招牌，它本身已是带白色汉字的蓝色；'Change the color of the banner ... to blue' 无变化，而且它是招牌而不是横幅。 | Ref: Change the color of the blue signboard on the pink building near the top to red.<br>No-ref: Change the color of the selected signboard to red.<br>category banner->signboard | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the shirt at the right with a yellow shirt. | U2 将红色队服替换为“a yellow shirt”——相同衣物类别，只有颜色变化。 | Ref: Change the color of the red shirt of the young man holding a dragon pole at the right of center to yellow.<br>No-ref: Change the color of the selected shirt to yellow.<br>op replace->attribute | 目视 |
| U2 | 严重 | 指代歧义 | ref+none | Replace the shirt at the right with a yellow shirt. | 几乎每位表演者都穿同样的红色队服,其中好几个在右侧(如最右边戴红帽的男子、后面的男孩)。'the shirt at the right' 无法识别被 mask 的年轻男子(cx=0.71,背对镜头,拿着杆子)。 | Ref: Replace the red shirt of the young man with his back to the camera holding a dragon pole, right of center, with a yellow tank top. | 目视 |
| U3 | 严重 | mask 质量 | ref+mask | Remove the dragon decoration near the center. | 这条龙是一整套蜿蜒穿过场景的连续舞龙服；U3 只 mask 了前左段（尾/身段，box 313-1123 x 889-1500），而同一条龙在表演者后方继续向右和背景延伸。对一件被举着的服饰的局部段落做 'Remove the dragon decoration'（杆子仍被握着）定义不清。 | Ref: Remove the green-and-orange dragon body segment lying on the ground in the lower left foreground.<br>或将 op 改为 attribute（给该段重新上色） | 目视 |
| U4 | 严重 | 指代歧义 | noref+box | Add a white stripe on the shoe at the lower right. | U4 mask 的是右下角穿牛仔短裤男子的后脚（左侧）鞋子；他的另一只鞋（黄色鞋底，约 x=1490,y=1100）就紧挨着它，所以 'the shoe at the lower right' 两只都适用。 | Ref: Add a white stripe on the raised rear shoe of the man in denim shorts at the lower right. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a white stripe on the shoe at the lower right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9089846`（#1050，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 属性值问题（无变化/含糊） | ref+point | Change the color of the banner at the right to blue. | 被 mask 的物体是右侧竖直的“SHIBUYA J PLAZA MARUYAMA”标志,它本来就是蓝色;“Change the color ... to blue”是空操作。它也是发光标志而不是横幅。 | Ref: Change the color of the blue vertical J PLAZA sign at the right to red.<br>No-ref: Change the color of the selected sign to red.<br>scope -> sign | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+point | Replace the dress at the lower left with a blue dress. | 'Replace the dress at the lower left with a blue dress'：左下方行走女子的黑色短袖连衣裙被替换为相同的衣物类型；只改变颜色。 | Ref: Change the color of the black dress of the woman carrying a plastic bag at the lower left to blue.<br>No-ref: Change the color of the selected dress to blue.<br>改为属性 | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | ref+box | Remove the skirt near the lower center. | 移除下方中部背身走远的女士所穿的裙子（box [944,1272,1008,1325]）；移除所穿裙子会使她的下半身未定义。 | Ref: Change the color of the skirt of the woman walking away near the lower center to navy blue.<br>No-ref: Change the color of the selected skirt to navy blue.<br>将 remove 转为 attribute | 目视 |

#### `v2-sa_9105975`（#1051，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代歧义 | noref+mask | Change the color of the car at the left to red. | U1 黑色出租车在 0.27W;更靠左(~0.15W)的一辆白色面包车也是 'at the left' 的车辆。'car' 有帮助,但 REF 可以更具体。 | Ref: Change the color of the black taxi at the left to red. | 目视 |
| U2 | 阻断 | replace 实为属性修改 | ref+none | Replace the sign at the right with blue. | U2 'Replace the sign at the right with blue'——payload 只是颜色，没有物体名词。Mask（box [2257,1084,2388,1199]）是右侧弯曲杆子上圆形路牌的背面，被杆子分成两部分。 | Ref: Replace the round sign on the curved pole at the right with a rectangular blue street-name sign.<br>No-ref: Replace the selected sign with a rectangular blue street-name sign.<br>或改为属性编辑：'Change the color of the round sign on the curved pole at the right to blue.' | 目视 |
| U3 | 严重 | 指代歧义 | ref+mask | Remove the traffic signal near the center. | U3 交通信号灯（box [1669,742,1868,857]，中心 0.71W）位于中心偏右；场景中还有其他交通信号灯（例如左侧杆上约 0.11W 处以及更远处）。'the traffic signal near the center' 无法唯一指向它。 | Ref: Remove the large black traffic signal box mounted on the pole at the right edge of the crowded crosswalk. | 目视 |

#### `v2-sa_911936`（#1053，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | ref+none | Change the color of the officer at the right to blue. | mask 覆盖的是站在中心偏右的海军陆战队员的橄榄绿 T 恤（box 805-1131 x 805-1144）。REF 'Change the color of the officer at the right to blue' 是人物级的，scope 为 'person'。'At the right' 也有歧义：更靠右还站着两个穿橄榄色衬衫的人。 | Ref: Change the color of the olive T-shirt of the short-haired marine standing next to the woman, right of center, to blue.<br>No-ref: Change the color of the selected T-shirt to blue.<br>将 scope 设为 'T-shirt'。 | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | ref+mask | Replace the officer near the center with a black uniform. | mask 覆盖的是中心附近海军陆战队员（双臂交叉）的橄榄色T恤。'Replace the officer near the center with a black uniform' 是把人替换成衣物。 | Ref: Replace the olive T-shirt of the marine with crossed arms near the center with a black zip-up hoodie.<br>No-ref: Replace the selected T-shirt with a black zip-up hoodie.<br>将 scope 设为 'T-shirt'；若包含前臂则重新 mask 将其排除。 | 目视 |
| U4 | 严重 | 多单元同一物理对象/相互冲突 | ref+point | Add a reflective stripe on the boots near the lower center. | 该 mask 覆盖一只棕褐色战斗靴(box 825-979 x 1777-1957),根据其在腿下的位置,它似乎是 T 恤为 U1(约 0.55-0.65W)的同一名海军陆战队员的左靴。REF 对一只靴子也用了“boots”(复数),且“near the lower center”适用于人群中的许多棕褐色靴子。 | Ref: Add a reflective stripe on the tan combat boot of the marine standing behind the police dog, just right of the dog.<br>No-ref: Add a reflective stripe on the selected boot.<br>选择未被其他单元使用的人所穿的靴子(例如女子的靴子)或删除 U4。 | 目视 |

#### `v2-sa_9123338`（#1054，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+point | Change the color of the person in the jacket at the left to blue. | REF/NOREF：'Change the color of the person in the jacket at the left to blue' / 'the selected person'，而 mask（box [91,591,331,964]）只覆盖最左边男子的棕色灯芯绒夹克。文本指的是人，而不是衣物。 | Ref: Change the color of the brown corduroy jacket of the man standing at the far left to blue.<br>No-ref: Change the color of the selected jacket to blue.<br>范围 -> jacket | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+box | Replace the stone stool near the center with a wooden stool. | U2 将石凳替换为“a wooden stool”——相同物体类别，仅材质变化。 | Ref: Replace the round stone stool under the man in the black-and-gold jacket with a red plastic crate.<br>No-ref: Replace the selected stool with a red plastic crate.<br>或转为 attribute material -> wood。 | 目视 |
| U2 | 严重 | 指代歧义 | ref+box | Replace the stone stool near the center with a wooden stool. | 'the stone stool near the center':场景中有多个相同的圆形石凳;被 mask 的那个(box [1550,942,1677,1075],cx=0.71W)在中心偏右,上面坐着穿带条纹领黑夹克的男子。 | Ref: ... the round stone stool under the man in the black jacket with a striped hem, at the right ... | 目视 |
| U3 | 严重 | 指代歧义 | noref+mask | Remove the cap at the right. | 'the cap at the right'：被 mask 的蓝色帽子（box [1338,475,1407,524], cx=0.61W）由中右部穿橙色夹克的男子佩戴；其他帽子（一顶灰色平顶帽和一顶白帽）更靠右，左侧还有一顶白帽。 | Ref: Remove the blue cap of the man in the orange jacket. | 目视 |

#### `v2-sa_9131105`（#1055，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | ref+none | Change the color of the plaque at the upper left to dark. | REF 'the plaque at the upper left'，但被 mask 的圆形橙色 'Dirty Bottles' 招牌在立面的右上方（cx=0.79）。 | Ref: Change the color of the round orange Dirty Bottles sign at the upper right to dark green.<br>No-ref: Change the color of the selected plaque to dark green. | 目视 |
| U1 | 严重 | 属性值问题（无变化/含糊） | ref+none | Change the color of the plaque at the upper left to dark. | 颜色值“dark”没有色相。 | 使用具体的颜色,如“dark green”。 | 目视 |
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+mask | Remove the door near the lower center. | REF 'the door near the lower center'，但被 mask 的敞开的淡绿色门扇位于左下方（cx=0.19），在小山形顶篷下。 | Ref: Remove the open pale green door at the lower left under the small gabled canopy. | 目视 |

#### `v2-sa_9136349`（#1056，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+point | Replace the shirt near the center with a red shirt. | 被 mask 的“shirt”[1758,538,1935,706]（cx=0.82）是右侧背包男子身后一个人的黑衬衫/肩部的一小块可见区域，并非“near the center”。人群中有许多衬衫；REF 无法定位这一碎片。 | Ref: Replace the black shirt of the person behind the bearded man at the right, next to the rainbow flag pole, with a red Hawaiian shirt.<br>No-ref: Replace the selected shirt with a red Hawaiian shirt.<br>最好选择更清晰可见的衣物。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the shirt near the center with a red shirt. | 'Replace the shirt ... with a red shirt' 只是改变黑色衬衫的颜色。 | No-ref: Change the color of the selected shirt to red.<br>Convert to attribute or choose a different garment type as payload. | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | noref+point | Remove the umbrella near the upper center. | 被 mask 的伞 [0,147,630,474]（cx=0.14）是在左上边缘被截断的黄色伞。'near the upper center' 的伞是图像中间带杆子的大黄色 Schweppes 伞，它没有被 mask。 | Ref: Remove the yellow umbrella partly visible at the upper left.<br>将 ZH 修正为 移除左上方的黄色雨伞，并同步修正 physical_parent_zh。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+box | Add a small logo on the sign at the right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9142280`（#1057，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Change the color of the boat at the left to yellow. | U1 mask（box [1866,794,2008,869]，cx=0.96）是被截断在图像最右边缘的白色摩托艇；REF/ZH 称其为 'the boat at the left'（左侧的船）。该物体也是摩托艇而非泛指的船。 | Ref: Change the color of the white jet ski at the far right edge to yellow.<br>No-ref: Change the color of the selected jet ski to yellow.<br>ZH: 将最右侧边缘的白色摩托艇的颜色改为黄色。 | 目视 |
| U2 | 严重 | 指代歧义 | ref+none | Replace the life jacket near the center with a red life jacket. | 香蕉船周围约有十人穿着几乎相同的黄红色救生衣;U2 mask(box [1268,774,1336,865])是那名穿深色短裤、短发、正走向香蕉船的男子身上的那件,但“the life jacket near the center”适用于其中好几件。 | Ref: Change the color of the yellow life jacket of the short-haired man in dark shorts climbing toward the banana boat to red.<br>No-ref: Change the color of the selected life jacket to red.<br>同时转换为 attribute(见下一条发现) | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the life jacket near the center with a red life jacket. | 'Replace the life jacket ... with a red life jacket' 只改变同一物体的颜色（现有救生衣为带红条纹的黄色）。 | 将 op 改为 attribute（color red） | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+mask | Remove the shirt at the right. | U3 mask（box [761,811,813,905]，cx=0.39）是站在赤膊男子左边、图像中心左侧的一个人穿的红色上衣/背心；REF/ZH 写的是“the shirt at the right”（右侧的上衣）。 | Ref: Change the color of the red top of the person standing beside the shirtless man in black trunks to white.<br>No-ref: Change the color of the selected shirt to white.<br>同时将 remove 改为 attribute（见下一条发现） | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | ref+mask | Remove the shirt at the right. | U3 从站在水中的人身上移除一件穿着的红色上衣,这会留下未定义的裸露躯干/内层衣物。 | change op to attribute (recolor) or replace with another garment | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a small logo on the hat at the left. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9161358`（#1058，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 属性值问题（无变化/含糊） | ref+point | Change the color of the potted plant at the left to green. | U1 mask 是左下方（box 18-434 x）枝叶繁茂的绿色灌木叶丛；该植物本来就是绿色，所以 'Change the color of the potted plant at the left to green' 是无操作。 | Ref: Change the color of the leaves of the potted plant at the lower left to deep purple.<br>No-ref: Change the color of the selected potted plant to deep purple. | 目视 |
| U2 | 阻断 | 方位/序数/实例指代错误 | noref+point | Replace the plastic bag at the left with a blue bag. | U2 mask 是小巷右侧靠墙的下方白色麻袋/塑料袋（中心 0.61W, 0.89H），不在 'at the left'。 | Ref: Replace the lower white plastic sack on the ground at the foot of the right wall with a wooden crate.<br>No-ref: Replace the selected plastic bag with a wooden crate. | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+point | Replace the plastic bag at the left with a blue bag. | Payload“a blue bag”保持类别不变;仅是重新着色。 | 使用不同类别的 payload,例如木箱(见空间修正)。 | 目视 |
| U4 | 轻微 | mask 质量 | noref+mask | Add a small arrow on the sign at the left. | ÇIÇEKLI 悬挂标牌的 U4 mask 在标牌右侧有第二个连通块（叶丛/支架上的独立斑块），使 box 扩展到 x=944。 | 去除零散连通块；只保留标牌板。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small arrow on the sign at the left. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9169801`（#1059，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+none | Change the color of the car at the left to red. | “the car at the left”适用于左侧的多辆车（最左边缘的银色车、路灯后的白色车）；被 mask 的是在左车道驶离的黑色小掀背车（cx=0.17）。 | Ref: Change the color of the small black hatchback driving away in the road at the left to red. | 目视 |
| U2 | 阻断 | 编辑不合理/不可执行 | ref+mask | Replace the streetlight at the left with black. | 'Replace the streetlight at the left with black.' —— replace payload 是单纯的颜色,不是物体;被 mask 的华丽灯笼式路灯本来就是黑色/深色。 | Ref: Replace the ornate lantern streetlight at the left with a modern slim LED pole light.<br>No-ref: Replace the selected streetlight with a modern slim LED pole light.<br>or convert to attribute: 'Change the color of the ornate lantern streetlight at the left to dark green.' | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | noref+box | Remove the traffic sign at the upper right. | REF 写 'the traffic sign at the upper right'，但 mask（box y 1162-1212, cy=0.79）是 LOWER right 的一块小型白色信息牌，挂在广场上系柱之间的链条附近。右侧杆子上的蓝色圆形自行车/行人交通标志（视图 x~1290,y~635）更符合该文字，因此 REF 指向了不同的物体；被 mask 的信息牌也不明显是交通标志。 | Ref: Remove the small white information plaque by the chain barrier at the lower right.<br>No-ref: Remove the selected plaque.<br>ZH: 移除右下方链条护栏旁的小白色信息牌。 | 目视 |
| U4 | 阻断 | 方位/序数/实例指代错误 | ref+point | Add a flower box on the window at the left. | REF 说 'the window at the left'，但被 mask 的窗户（box x 1904-1943，cx=0.85）是图像右侧黄色酒店立面上的一扇高大的上层窗；还有几十扇其他窗户。 | Ref: Add a flower box under the tall second-floor window at the right end of the yellow hotel facade, at the right of the image.<br>ZH: 在图像右侧黄色酒店立面右端二楼的高窗下加上一个花箱。 | 目视 |

#### `v2-sa_9173282`（#1061，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | ref+mask | Change the color of the railing at the left to white. | REF 写 'the railing at the left'，但 mask（box [1453,325,1732,445], cx=0.71W）是图像右半部堤岸铸铁栅栏的一块面板。该栅栏在花岗岩柱之间约有九块相同的面板，因此 REF 既不匹配位置，也无法单独指出某一块面板。 | Ref: Change the color of the fence panel directly above the boat's cabin, between the fifth and sixth granite posts from the left, to white.<br>或者将 mask 重新设为整段堤岸栅栏，并使用 'the iron fence along the embankment'。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the life jacket near the center with a yellow life jacket. | 挂在船舱窗口的橙色救生衣（box [1407,986,1530,1196]）被替换为 'a yellow life jacket'：同一类别，仅颜色改变。 | Ref: Replace the orange life jacket hanging in the cabin window with a round orange life ring.<br>No-ref: Replace the selected life jacket with a round orange life ring.<br>或转为属性：'Change the color of the orange life jacket hanging in the cabin window to yellow.' | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | ref+point | Remove the window at the right. | “Remove the window at the right”针对的是游船最右侧的船舱窗玻璃(box [2112,981,2247,1261]),其 mask 里充满了透过玻璃看到的堆叠橙色救生衣和虎纹毯子。从船体结构中移除窗户定义不清:不清楚应该移除玻璃、窗框还是内部物品。 | Ref: Remove the stack of orange life jackets behind the rightmost cabin window.<br>No-ref: Remove the selected life jackets.<br>将 scope 改为救生衣堆(mask 已基本覆盖)。 | 目视 |
| U4 | 严重 | 方位/序数/实例指代错误 | noref+point | Add a small badge on the shirt near the center. | REF 'the shirt near the center' 指向的是右侧船舱内一名坐着的乘客所穿的浅蓝色衬衫（box [1748,1142,1843,1225]，cx=0.80W）。它不在中心附近，且可见几十名乘客的上衣，因此 REF 无法识别它。 | Ref: Add a small badge on the light-blue shirt of the passenger seated inside the boat cabin, second window from the right.<br>ZH: 在船舱内右起第二扇窗后乘客的浅蓝色衬衫上加上一个小徽章。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a small badge on the shirt near the center. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9180481`（#1062，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | ref+box | Change the color of the person at the left to blue. | U1 mask 是左侧整个蹲着的乐手（头巾、脸、蓝金夹克、金色裤子、鞋）；“Change the color of the person to blue”是人物级别的改色，没有指明衣物。 | Ref: Change the color of the gold trousers of the musician in the blue turban on the left to blue.<br>No-ref: Change the color of the selected trousers to blue.<br>重新对金色裤子做 mask | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the brass instrument near the center with a silver instrument. | U2 是一把本来就是银色/镀镍的次中音号;'Replace ... with a silver instrument' 是含糊的、仅有颜色的 payload,没有新的乐器类型(而且 'brass' 也不符合其外观)。 | Ref: Replace the euphonium standing in front of the musicians with a large bass drum.<br>No-ref: Replace the selected instrument with a large bass drum. | 目视 |
| U3 | 阻断 | 指代类别与 mask 不符 | ref+none | Remove the brick wall at the left. | U3 mask（cx=0.83W, cy=0.84H）是右侧地面上的一小块粉色铺地，不是砖墙，也不在左侧。移除地面上的一块区域本身也定义不清。 | 删除该单元，或选择真实物体（例如地上的小包装纸：'Remove the small snack wrapper on the floor in front of the euphonium.'） | 目视 |
| U4 | 严重 | 方位/序数/实例指代错误 | ref+mask | Add a small light on the ceiling at the upper center. | U4 mask 是右上角（cx=0.85W）头顶楼梯/天花板的倾斜底面，不在 'at the upper center'。 | Ref: Add a small round ceiling lamp on the sloped ceiling in the upper right corner.<br>No-ref: Add a small round ceiling lamp on the selected ceiling. | 目视 |

#### `v2-sa_9187878`（#1063，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代歧义 | noref+box | Change the color of the banner at the upper left to blue. | U1 红黄相间的火炬传递护栏横幅(box [0,558,232,733])位于左侧中等高度,而不是左上方。它是沿护栏的数条类似横幅中最近、最大的一条。 | Ref: Change the color of the nearest red-and-yellow barrier banner at the far left to blue. | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | noref+point | Remove the shirt near the center. | REF 称 'the shirt near the center'，但 U3 mask 是最左边缘靠着护栏的男子所穿的图案浅色衬衫（box [26,499,143,559]，cx=0.04）。移除所穿衬衫也会留下未定义的身体。 | Ref: Change the color of the patterned white shirt of the man leaning on the barrier at the far left to navy blue.<br>No-ref: Change the color of the selected shirt to navy blue.<br>将 op 从 remove 改为 attribute | 目视 |
| U4 | 严重 | 指代歧义 | ref+box | Add a small logo on the balloon at the right. | U4 mask 的是右侧观众前面的一个大白气球（box [1475,545,1797,870]）。其周围（上方、后方和下方）聚集着数个白气球，栏杆沿线还有更多，所以“the balloon at the right”有歧义。 | Ref: Add a small logo on the largest, nearest white balloon at the right. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+box | Add a small logo on the balloon at the right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9202366`（#1064，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+mask | Change the color of the person at the left to blue. | U1 mask 只是老人的蓝色格子衬衫(box [1396,622,1800,1204]);REF 说 'the person',是未指明服装的人级别改色。 | Ref: Change the color of the plaid shirt of the gray-haired man on the right to blue.<br>No-ref: Change the color of the selected shirt to blue.<br>scope='shirt'; the shirt is already blue/teal plaid, so prefer a clearly different value, e.g. 'to red' | 目视 |
| U1 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Change the color of the person at the left to blue. | 男子（cx=0.71W）坐在女子的 RIGHT 侧；'the person at the left' 会选中该女子。 | Ref: Change the color of the plaid shirt of the gray-haired man on the right to red.<br>No-ref: Change the color of the selected shirt to red. | 目视 |
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+none | Replace the sign at the left with a blue sign. | U2 mask 是右上边缘（cx=0.91W）的深色小 'ÄRZTE' 招牌；REF 说 'the sign at the left'。正式输入为仅 REF。 | Ref: Replace the dark ÄRZTE sign at the top-right edge with a round green pharmacy cross sign.<br>No-ref: Replace the selected sign with a round green pharmacy cross sign.<br>更新 ZH（右上角） | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the sign at the left with a blue sign. | “Replace the sign with a blue sign”仅是重新着色。 | Ref: Replace the dark ÄRZTE sign at the top-right edge with a round green pharmacy cross sign.<br>No-ref: Replace the selected sign with a round green pharmacy cross sign. | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+mask | Remove the chair near the center. | U3 mask 是在右边缘被截断的藤椅（cx=0.97W）；REF 称 'the chair near the center'（实际上许多藤椅在中心/左侧附近）。 | Ref: Remove the rattan chair partly visible at the right edge.<br>更新 ZH: 移除右侧边缘露出一部分的藤椅。 | 目视 |
| U4 | 阻断 | 方位/序数/实例指代错误 | noref+box | Add a string of lights on the umbrella at the upper left. | U4 mask 是男子身后右上方收起的红色雨伞（cx=0.81W）；REF 写的是“the umbrella at the upper left”，这与左上方的大型撑开的红伞相符。 | Ref: Add a string of lights on the closed red umbrella at the upper right.<br>更新 ZH: 在右上方收起的红色雨伞加上一串灯饰。 | 目视 |

#### `v2-sa_9206930`（#1065，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | ref+point | Change the color of the window at the left to blue. | U1 mask 的是右侧粉色建筑上带绿色百叶的窗户(cx=0.87,在小凉亭屋顶右侧),但 REF 说 'the window at the left'。该建筑有许多相同的窗户,所以 REF 既错误又有歧义。 | Ref: Change the color of the green shutters of the upper-floor window at the far right of the pink building, above the yellow flags, to blue.<br>fix ZH (右侧粉色建筑二楼最右的窗户) | 目视 |
| U2 | 阻断 | 编辑不合理/不可执行 | noref+point | Replace the streetlight in the foreground with black. | U2 'Replace the streetlight in the foreground with black' 的 payload 只是颜色。此外，被 mask 的灯柱是左侧远岸背景中的一盏小灯（cx=0.17），不在前景，且 mask（comps=2）是细而断裂的轮廓。 | Ref: Change the color of the lamp post on the far bank at the left, beside the palm tree, to black.<br>No-ref: Change the color of the selected streetlight to black.<br>op replace->attribute；清理 mask | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+box | Remove the flag near the center. | U3 mask 的是右岸小亭子旁的前面那面黄旗（cx=0.82），不在 'near the center'；紧挨着它还有第二面黄旗和一面泰国国旗，所以 REF 是错误且有歧义的。 | Ref: Remove the front yellow flag with a round emblem beside the small pavilion on the right bank.<br>修正 ZH | 目视 |
| U4 | 严重 | add 锚点不当 | noref+mask | Add a small hat on the person at the right. | U4 mask 是贡多拉上整个右侧僧人(僧袍 + 头,comps=2);“Add a small hat on the person”没有给出附着位置,而是把整个人当作锚点。 | Ref: Add a small straw hat on the head of the monk sitting on the right in the hanging gondola.<br>No-ref: Add a small straw hat on the head of the selected person. | 目视 |

#### `v2-sa_9212792`（#1066，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | ref+none | Change the color of the car at the left to red. | REF 'the car at the left'（ref+none），但被 mask 的深灰色汽车位于右边缘（box [1056,906,1500,1415]，中心 x=0.85W）；左侧没有汽车（只有停放的踏板车）。 | Ref: Change the color of the dark gray car at the right edge to red. | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the coat near the center with a blue coat. | “Replace the coat near the center with a blue coat”：正在过马路的女士的白色皮草大衣被替换为同类型衣物；只有颜色变化。 | Ref: Replace the white fur coat of the woman crossing the street with a blue denim jacket.<br>No-ref: Replace the selected coat with a blue denim jacket.<br>或转为 attribute | 目视 |
| U3 | 严重 | 多单元同一物理对象/相互冲突 | noref+box | Remove the handbag at the right. | U3 手提包(银色包,box [1041,892,1137,1110])被同一位女子拿在身侧,她的毛皮大衣是 U2;U3 的 box 位于 U2 的 box 内,且包部分塞在大衣袖子下。同一个人身上有两个单元。 | drop U3 (or U2) and pick an independent object, e.g. the white scooter parked at the left | 目视 |
| U3 | 轻微 | 方位/序数/实例指代错误 | noref+box | Remove the handbag at the right. | 'the handbag at the right'：该包由图像中心的女子拎着（x=0.73W 偏右，但在中心人物身上）；措辞较宽松。 | Ref: Remove the silver handbag held by the woman crossing the street. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a small arrow on the sign at the upper left. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_921334`（#1067，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+point | Change the color of the boat at the left to white. | U1 是较近的白色水上巴士 vaporetto（中心 0.36W）；更靠左有许多系泊的船。'the boat at the left' 较弱。此外该 vaporetto 本来就大部分是白色，所以 'change color to white' 几乎看不出变化。 | Ref: Change the color of the nearer white vaporetto water bus to bright yellow.<br>No-ref: Change the color of the selected boat to bright yellow. | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+box | Replace the boat at the right with a blue boat. | U2“Replace the boat at the right with a blue boat”——同一类别,仅颜色变化。 | Ref: Replace the second vaporetto farther up the canal with a small wooden gondola.<br>No-ref: Replace the selected boat with a small wooden gondola. | 目视 |
| U2 | 严重 | 指代歧义 | ref+box | Replace the boat at the right with a blue boat. | U2 水上巴士位于运河中央（0.49W）；一艘货船（~0.6W）和许多贡多拉更靠右。'the boat at the right' 是错误的/有歧义。 | Ref: ... the vaporetto farther up the canal behind the nearer vaporetto ... | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Remove the balcony near the center. | U3 阳台（box [2048,721,2185,769]，中心 0.94W）是最右侧 Hotel Marconi 立面上的锻铁阳台；REF 写的是“near the center”。移除建筑阳台在结构上也有疑问。 | Ref: Remove the wrought-iron balcony railing below the HOTEL MARCONI sign on the right bank.<br>ZH: 移除右岸HOTEL MARCONI招牌下方的铁艺阳台栏杆。 | 目视 |
| U4 | 严重 | 指代歧义 | ref+none | Add a small sign on the awning at the right. | U4 mask(box [2025,779,2180,824],3 个分量)是一块红色餐厅遮阳篷的一小部分;右岸有一长排相同的红色遮阳篷。'the awning at the right' 有歧义。 | Ref: Add a small sign on the red awning directly below the HOTEL MARCONI balcony. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+none | Add a small sign on the awning at the right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9214653`（#1068，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | ref+mask | Change the color of the car at the left to red. | U1 mask 是右下前景的黑色本田两厢车（box 1390-2073, cx=0.77）；REF 写的是 'the car at the left'。 | Ref: Change the color of the black hatchback in the lower right foreground to red.<br>ZH: 将右下前景的黑色掀背车改为红色。 | 目视 |
| U2 | 阻断 | 方位/序数/实例指代错误 | noref+box | Replace the helmet near the center with blue. | U2 mask 是被截断在最左边缘的摩托车手戴的带黑白方格条纹的白色头盔（box 0-91，cx=0.02）；REF 说 'near the center'。 | Ref: Replace the white checkered-stripe helmet of the rider at the far left edge with a black open-face helmet with goggles.<br>No-ref: Replace the selected helmet with a black open-face helmet with goggles. | 目视 |
| U2 | 阻断 | replace 实为属性修改 | noref+box | Replace the helmet near the center with blue. | “Replace the helmet near the center with blue”——replace 的 payload 只是一个颜色,没有物体。 | Ref: Replace the white checkered-stripe helmet of the rider at the far left edge with a black open-face helmet with goggles.<br>No-ref: Replace the selected helmet with a black open-face helmet with goggles.<br>或转换为 attribute:颜色 -> blue | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a small logo on the sign at the right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_922772`（#1070，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| case | 严重 | 多单元同一物理对象/相互冲突 |  |  | U2（白色衣领）和 U3（黑色裙子）都在同一个拿橙色玫瑰的金发女孩身上；U1（花束）和 U4（绿色背包）都由最左边的同一个男孩拿着/背着。两对单元共享同一个物理母体。 | 重新选取目标，例如 U2 -> 拿蓝黄花束的男孩的藏青色西装外套，U4 -> 右侧女子的薄荷色波点连衣裙。 | 目视 |
| U2 | 阻断 | replace 实为属性修改 | ref+point | Replace the shirt near the center with blue. | 'Replace the shirt near the center with blue' ——replace 的 payload 只是一个颜色，没有物体；此外 mask（box [356,767,479,848]）只是拿橙色花束的金发女孩的白色衬衫领子，位于 0.28W 而不是中心。 | Ref: Change the color of the white blouse collar of the blonde girl holding orange roses to light blue.<br>No-ref: Change the color of the selected collar to light blue.<br>op -> attribute，scope -> collar | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | noref+point | Remove the skirt near the center. | U3 移除金发女孩所穿的黑色裙子/背带裙(box [270,1102,549,1449])——移除所穿衣物会使下半身不确定。“near the center”也不够准确(女孩位于 0.27W,且许多孩子都穿深色裙子)。 | Ref: Change the color of the black skirt of the blonde girl holding orange roses to navy plaid.<br>No-ref: Change the color of the selected skirt to navy.<br>op -> attribute | 目视 |
| U4 | 阻断 | 方位/序数/实例指代错误 | ref+box | Add a small badge on the backpack at the right. | REF 称 'the backpack at the right'，但被 mask 的绿色背包（box [47,798,123,946]，cx=0.06W）属于最左边缘的男孩。 | Ref: Add a small reflective star badge on the green backpack of the boy at the far left.<br>ZH: 在最左侧男孩的绿色背包上加上一个小反光星形徽章。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+box | Add a small badge on the backpack at the right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9229006`（#1071，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| case | 严重 | 多单元同一物理对象/相互冲突 |  |  | U1（圆顶/钟楼）、U3（该圆顶顶上的风向标）和 U2（入口门）都是同一栋砖楼的组成部分；U3 直接位于 U1 之上。 | 保留一个建筑部件（如 U1），并将其他替换为独立物体，如雕像或树。 | 目视 |
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+none | Replace the door at the left with a blue door. | REF 'the door at the left',但被 mask 的拱形门在 x~0.58W,位于建筑中央入口处雕像的右侧。 | Ref: Change the color of the arched entrance door behind the statue to blue.<br>No-ref: Change the color of the selected door to blue.<br>Also op should be attribute (see below). | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the door at the left with a blue door. | 'Replace the door ... with a blue door' 纯属换色。 | op=attribute color blue。 | 目视 |
| U4 | 阻断 | 方位/序数/实例指代错误 | noref+box | Add a small flower on the grass at the lower left. | REF 'the grass at the lower left'，但被 mask 的草坪在砖路右侧（cx=0.80，右下）。 | Ref: Add a small yellow daffodil on the lawn at the lower right.<br>No-ref: Add a small yellow daffodil on the selected grass. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a small flower on the grass at the lower left. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9237516`（#1072，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 属性值问题（无变化/含糊） | ref+point | Change the color of the canopy at the left to blue. | 左下方被 mask 的防水布顶篷 [0,966,1139,1467] 本来就是亮蓝色;“change the color ... to blue”是空操作。 | Ref: Change the color of the blue tarp canopy at the lower left to orange.<br>No-ref: Change the color of the selected canopy to orange. | 目视 |
| U2 | 阻断 | replace 实为属性修改 | noref+point | Replace the car near the center with red. | 'Replace the car near the center with red' 的载荷是单纯的颜色，没有物体。 | Ref: Change the color of the gray sedan partly hidden behind the concrete utility hut at the right to red.<br>No-ref: Change the color of the selected car to red.<br>将 op 转为 attribute（color=red），或替换为具体物体（例如 'a small red pickup truck'）。 | 目视 |
| U2 | 阻断 | 方位/序数/实例指代错误 | noref+point | Replace the car near the center with red. | 被 mask 的汽车 [1615,672,2045,782]（cx=0.81）是右侧的灰色轿车，大部分被涂鸦覆盖的混凝土小屋遮挡；它不在“near the center”，而且还可见其他几辆车/面包车（中间的白色面包车、右上的灰色旅行车）。 | Ref: Change the color of the gray sedan partly hidden behind the concrete utility hut at the right to red. | 目视 |
| U3 | 严重 | 指代歧义 | ref+box | Remove the plastic bag at the right. | 被 mask 的袋子 [1348,1123,1437,1199](cx=0.62)是白色面包车后轮旁地上的半透明红色内容物袋子;紧挨它还有其他塑料袋(其左侧的白色袋子),而且它不在图像右侧。'the plastic bag at the right' 不具识别性。 | Ref: Remove the plastic bag with red contents on the ground beside the white van's rear wheel. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small label on the crate near the lower center. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9241496`（#1073，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+none | Change the color of the motorbike at the left to red. | U1 mask 是米色/奶油色踏板车（box [402,1927,618,2222]）；一辆橙色踏板车停在更靠左、紧挨着它的位置，因此 'the motorbike at the left' 至少同样适用于橙色那辆。 | Ref: Change the color of the cream scooter at the left, beside the orange scooter, to red.<br>ZH: 将左侧橙色摩托车旁的米色踏板车的颜色改为红色。 | 目视 |
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+mask | Replace the box near the center with a blue box. | U2 mask（box [1425,1806,1500,1893]，cx=0.97）是被截断在图像最右边缘的摩托车上载运的纸箱；REF/ZH 说 'the box near the center'（中间附近的纸箱）。实际上中心附近另有一个纸箱（由 U3 骑手载运）。 | Ref: Replace the cardboard box on the motorbike at the far right edge with a stack of plastic crates.<br>No-ref: Replace the selected box with a stack of plastic crates.<br>ZH: 将最右侧边缘摩托车上的纸箱替换为一摞塑料筐。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the box near the center with a blue box. | “Replace the box ... with a blue box”只是改变同一物体的颜色。 | 使用结构不同的 payload 或转换为 attribute | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | noref+box | Remove the coat at the right. | U3 mask 是街道中间骑踏板车、搬着纸箱的骑手所穿的深色外套（box [703,1848,880,1941]）；移除所穿外套会留下未定义的身体/内层衣物。此外骑手位于图像中心（cx=0.53），更右侧还有数名骑手，因此 'the coat at the right' 具有误导性。 | Ref: Change the color of the dark coat of the rider carrying a cardboard box in the middle of the street to red.<br>No-ref: Change the color of the selected coat to red.<br>将 remove 转为 attribute；修正空间短语 | 目视 |
| U4 | 严重 | 指代歧义 | ref+point | Add a small arrow on the sign at the right. | U4 mask 是挂在中心偏右建筑立面上的一块窄竖向店招（box [774,1273,857,1540]，cx=0.54）；可见许多标牌（TRANG NU 遮阳篷、其他竖向招牌），所以“the sign at the right”无法识别它。 | Ref: Add a small arrow on the tall narrow vertical sign hanging high on the building facade above the TRANG NU awning. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a small arrow on the sign at the right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9247733`（#1074，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+point | Change the color of the barber at the left to blue. | U1 mask(box 817-2153 x, 1012-1500 y)是坐着的顾客身上沾满头发的白色理发披肩,但 REF 说 'Change the color of the barber at the left to blue'(人错了,且是人级别属性;mask 中心 0.66W,不在左侧)。 | Ref: Change the color of the white barber cape on the seated customer to blue.<br>No-ref: Change the color of the selected cape to blue.<br>scope='cape'. | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | ref+box | Replace the customer near the center with a white shirt. | U2 mask（box 485-842 x, 358-666 y, 2 个分量）是理发师领口处露出的紫色内衬衣领，但 REF 写的是 'Replace the customer near the center with a white shirt'（人物错误，人被替换为衣物）。 | Ref: Replace the purple undershirt visible at the barber's collar with a gray crew-neck T-shirt.<br>No-ref: Replace the selected undershirt with a gray crew-neck T-shirt.<br>scope='undershirt'。 | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Remove the chair near the center. | U3 mask 是被截断在最左图像边缘的模糊红色理发椅靠背（box 0-127 x，中心 0.03W），不在 'near the center'。 | Ref: Remove the blurred red barber chair at the far left edge. | 目视 |
| U4 | 阻断 | 多单元同一物理对象/相互冲突 | ref+none | Add a small charm on the bracelet at the left. | U4 mask 是理发师右手腕上的银色链条手链(box 852-963 x);U2 也在这名理发师身上(他的内衣),因此两个单元共享同一个物理母体。 | Ref: Add a small charm on the silver chain bracelet on the barber's wrist.<br>删除 U4 或将 U2 移到其他物体上。 | 目视 |

#### `v2-sa_9249460`（#1075，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 属性值问题（无变化/含糊） | ref+mask | Change the color of the wheel at the left to black. | 被 mask 的轮子是黑色轮胎配深色辐条；'change the color ... to black' 基本无变化，也没有指明应改变哪个部分。 | Ref: Change the color of the spokes and rim of the leftmost becak wheel to bright red.<br>No-ref: Change the color of the spokes and rim of the selected wheel to bright red. | 目视 |
| U2 | 阻断 | 编辑不合理/不可执行 | noref+box | Replace the canopy at the left with blue. | “Replace the canopy at the left with blue.”——payload 只是一个单纯的颜色，不是物体。 | Ref: Change the color of the gray canopy of the rightmost becak to blue.<br>No-ref: Change the color of the selected canopy to blue.<br>将 op 改为 attribute；ZH: 将最右侧三轮车的灰色车篷的颜色改为蓝色。 | 目视 |
| U2 | 阻断 | 方位/序数/实例指代错误 | noref+box | Replace the canopy at the left with blue. | REF 说 'the canopy at the left',但被 mask 的灰色篷顶属于最右边的三轮车(box x 1798-2271,cx=0.79)。最左边的三轮车有不同的黑色篷顶,所以 REF 指向了错误的实例。 | Ref: (see previous) 'the gray canopy of the rightmost becak' | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+point | Remove the vine at the left. | REF 写 'the vine at the left'，但 mask 是 TOP-RIGHT 角的一片藤蔓叶丛（box x 2284-2577, y 0-227, cx=0.94）；主要的藤蔓团悬在顶部中央。mask 也是连续枝叶的一个任意碎片。 | Ref: Remove the vine leaves hanging in the top-right corner over the rusty fence.<br>ZH: 移除右上角锈铁皮围栏上方垂下的藤叶。考虑删除该单元，因为这片藤蔓没有清晰的边界。 | 目视 |

#### `v2-sa_926201`（#1076，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+point | Change the color of the window at the left to blue. | 'the window at the left' ——立面有几十扇类似的百叶窗；被 mask 的是 0.26W 处最上排的一扇窗。此外窗户本来就偏蓝，所以 'to blue' 是个很弱的改变。 | Ref: Change the color of the top-floor slatted window left of the blue glass section to red.<br>No-ref: Change the color of the selected window to red. | 目视 |
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+box | Replace the door at the left with a red door. | REF “the door at the left”,但被 mask 的门(x1378-1424,cx=0.62W)是 SALLE D'EXPOSITION 店面中心偏右的一扇窄玻璃门;左侧的 UNI CARL VOGT 入口门才会匹配。此外替换为“a red door”只是重新着色。 | Ref: Replace the narrow glass door of the SALLE D'EXPOSITION shopfront with a red wooden door.<br>No-ref: Replace the selected door with a red wooden door.<br>ZH:将SALLE D'EXPOSITION展厅的窄玻璃门替换为一扇红色木门。 | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Remove the bicycle at the lower center. | REF 'the bicycle at the lower center'，但被 mask 的自行车（box x0-213，cx=0.05W）位于左下角，带一个棕色驮包；下方中部有几十辆自行车。 | Ref: Remove the bicycle with a brown pannier at the lower-left corner.<br>ZH: 移除左下角挂棕色包的自行车。 | 目视 |
| U4 | 阻断 | 方位/序数/实例指代错误 | ref+none | Add a hanging flower basket on the streetlight near the center. | REF 为“the streetlight near the center”，但被 mask 的灯是右上方（0.84W,0.36H）电线上悬挂的小路灯；另一盏悬挂灯实际上更靠近中心（~0.41W,0.52H），所以 REF 绑定了错误的灯。 | Ref: Add a hanging flower basket on the wire-hung streetlight at the upper right.<br>ZH: 在右上方悬挂在电线上的路灯加上一个悬挂花篮。 | 目视 |

#### `v2-sa_927124`（#1077，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | ref+mask | Change the color of the person near the center to blue. | 'Change the color of the person near the center to blue' 是人级别的改色。mask(box [1170,682,1277,871])甚至不是完整的人:它只是被遮挡的游客的深色头发后脑勺,位于戴眼镜的灰发男子的正右侧。'the person near the center' 更自然地指灰发男子本人,所以 REF 也有歧义。 | Ref: Change the color of the black hair of the partly hidden visitor just right of the gray-haired man with glasses to blue.<br>No-ref: Change the color of the selected hair to blue.<br>Set scope=hair (category hair). | 目视 |

#### `v2-sa_9289265`（#1078，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| case | 轻微 | 多单元同一物理对象/相互冲突 |  |  | U1 摩托车、U3 骑手的衬衫和 U4 摩托车拖着的拖车顶篷，都是同一个骑手+嘟嘟车单元的组成部分。 | 优先选用独立物体（例如背景中的白色货车、美国国旗） | 目视 |
| U2 | 阻断 | 编辑不合理/不可执行 | noref+point | Replace the car at the left with blue. | 'Replace the car at the left with blue.' ——replace 的 payload 只是颜色，而被 mask 的汽车是右侧（cx=0.70W）的香槟色雷克萨斯 SUV，不在左边。mask 还包含了摩托车右后视镜上的一块独立碎片。 | Ref: Replace the champagne Lexus SUV on the right with a blue pickup truck.<br>No-ref: Replace the selected car with a blue pickup truck.<br>从 mask 中去掉后视镜碎片；ZH: 将右侧的香槟色雷克萨斯SUV替换为一辆蓝色皮卡。 | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | ref+box | Remove the shirt near the center. | U3 是摩托车骑手穿的米色纽扣衬衫;移除所穿衬衫会使身体不确定。mask 还包裹了摩托车的左后视镜和部分车把。 | Ref: Change the color of the beige shirt of the motorbike rider to dark green.<br>No-ref: Change the color of the selected shirt to dark green.<br>将操作改为 attribute;从 mask 中移除后视镜/车把 | 目视 |
| U4 | 严重 | 方位/序数/实例指代错误 | noref+mask | Add a small logo on the canopy at the right. | U4 顶篷是左上/中部（cx=0.38W）的嘟嘟车车顶，不是 'at the right'。它同时也是连在 U1 摩托车上的拖车车顶，因此 U1/U4 共享同一车辆组合。 | Ref: Add a small red logo on the canopy of the tuk-tuk at the top.<br>考虑与 U1（拉着这辆嘟嘟车的摩托车）的独立性 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small logo on the canopy at the right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9298533`（#1079，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 方位/序数/实例指代错误 | ref+none | Change the color of the streetlight at the left to black. | REF 写的是“the streetlight at the left”，但 U1 mask 是右侧白色栅栏旁树木前的黑色灯笼式灯柱（box [1647,449,1766,929]，cx=0.76）。其他路灯在左侧。 | Ref: Change the color of the tall lantern streetlight at the right, beside the white fence, to black.<br>注意该灯已经是深色；选择其他值，例如 'to dark green' | 目视 |
| U2 | 阻断 | 方位/序数/实例指代错误 | ref+mask | Replace the sign at the left with a blue sign. | REF 说 'the sign at the left',但 U2 mask 是大门右侧墙上的白色信息牌(box [1443,1043,1534,1110],cx=0.66)。Payload 'a blue sign' 也只是改色。 | Ref: Replace the white information board on the wall right of the courtyard gate with a wooden notice board.<br>No-ref: Replace the selected sign with a wooden notice board. | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | noref+box | Remove the coat at the right. | U3 mask 的是走向大门的女子所穿的长款淡紫色连帽外套（box [1354,1089,1442,1286]）。移除所穿外套会留下未定义的身体，且 'the coat at the right' 含糊，因为右边有好几位穿外套的行人。 | Ref: Change the color of the long mauve hooded coat of the woman walking toward the gate to dark green.<br>No-ref: Change the color of the selected coat to dark green.<br>将 op 改为 attribute | 目视 |
| U4 | 阻断 | 方位/序数/实例指代错误 | ref+point | Add a flower box on the window at the right. | REF 说 'the window at the right'，但 U4 mask 是中心偏左（box [913,1019,958,1094]，cx=0.42）庭院墙上的一扇带栅栏小窗。该墙上有许多相同的带栅栏窗户。 | Ref: Add a flower box on the barred window in the courtyard wall just behind the woman taking a photo. | 目视 |

#### `v2-sa_9327453`（#1080，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+box | Replace the game booth at the left with a blue booth. | “Replace the game booth with a blue booth”仅改变颜色。 | Ref: Replace the game booth at the left, behind the toy rifle, with a white food truck.<br>No-ref: Replace the selected game booth with a white food truck. | 目视 |
| U2 | 严重 | mask 质量 | ref+box | Replace the game booth at the left with a blue booth. | U2 'game booth' mask 是背景摊位（'degli Anelli'）的参差区域，被粉色毛绒兔子、玩具步枪和一名男子严重遮挡；其右侧碎成零散的点状碎片，并绕着该男子裁切，因此没有干净地覆盖一个摊位。 | 干净地重新分割 degli Anelli 摊位，或删除该单元 | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | noref+mask | Remove the flag at the upper left. | U3 mask 是最右上边缘彩旗线上一面很小的黑色海盗三角旗（box [2157,339,2204,415]，cx=0.97W）；REF 写的是“the flag at the upper left”。同一条线上挂着许多类似的三角旗，因此即便方向正确也有歧义。 | Ref: Remove the black skull-and-crossbones pennant at the upper-right edge, the largest one on the bunting line.<br>更新 ZH（右上方）；考虑删除这个很小的 unit | 目视 |
| U4 | 严重 | 指代歧义 | ref+none | Add a small logo on the sign at the left. | U4 mask 是下方中央玩具步枪下面悬挂的小黄色 'NON TOCCARE' 标签(cx=0.37W);REF 'the sign at the left'(仅 ref 输入)更符合最左侧的圆形 'POSSONO SPARARE' 及其他标志。 | Ref: Add a small red warning triangle on the yellow tag hanging under the toy rifle.<br>No-ref: Add a small red warning triangle on the selected sign.<br>update ZH accordingly | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+none | Add a small logo on the sign at the left. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9337303`（#1081，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| case | 阻断 | 多单元同一物理对象/相互冲突 |  |  | U2（1 号球员的球衣/短裤）和 U3（他的后脚球鞋）在同一个人身上，违反了单元独立性。 | 删除 U3，或将其改选为另一名球员的球鞋 | 目视 |
| U1 | 阻断 | 人物/服装层级错误 | ref+mask | Change the color of the player at the left to blue. | U1 mask 覆盖了最左边 8 号球员的栗红/天蓝色球衣和短裤，但 REF 说 'Change the color of the player ... to blue'（人物级属性）。球衣本来也已部分是蓝色。 | Ref: Change the color of the maroon-and-sky-blue jersey and shorts of the #8 player at the far left to green.<br>No-ref: Change the color of the selected uniform to green.<br>category person->uniform | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | noref+box | Replace the player near the center with a yellow uniform. | U2 mask 是右侧 1 号球员的红白条纹球衣 + 白色短裤(cx=0.73,并非“near the center”),但 REF 把“the player”替换为“a yellow uniform”(人被替换成衣物)。 | Ref: Change the color of the red-and-white hooped jersey of the #1 player reaching for the ball on the right to yellow.<br>No-ref: Change the color of the selected jersey to yellow.<br>category person->jersey;op replace->attribute | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+point | Remove the shoe at the left. | U3 mask 的是最右边 1 号球员抬起的后脚球鞋（cx=0.88），但 REF 称 'the shoe at the left'。左侧有许多球员的球鞋。 | Ref: Remove the raised rear boot of the #1 player at the right.<br>修正 ZH（右侧1号球员抬起的后脚球鞋） | 目视 |
| U4 | 轻微 | 指代歧义 | noref+point | Add a small logo on the cap near the center. | U4 是后排高个球员的黑色 Puma 帽子（cx=0.30），仅被描述为“the cap near the center”；它是唯一的帽子，所以可识别，但位置词较松散。 | Ref: Add a small logo on the black cap of the tall player in the red-and-white hooped jersey in the back. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a small logo on the cap near the center. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9345888`（#1082，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | ref+box | Change the color of the officer at the left to blue. | REF 'Change the color of the officer at the left to blue' 指向整个人,但 mask(box [817,490,1004,770])只是站在这组人左侧、穿深色长裤的平民男子(并非军官)的白色礼服衬衫。 | Ref: Change the color of the white shirt of the bald civilian man at the left of the standing group to blue.<br>No-ref: Change the color of the selected shirt to blue.<br>scope -> shirt | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | noref+mask | Replace the officer near the center with a black uniform. | REF 'Replace the officer near the center with a black uniform' 把人替换为衣物；mask（box [957,515,1028,769]）只是 U1 旁边第二位平民男子（灰发）的白衬衫，不是军官。 | Ref: Replace the white shirt of the gray-haired civilian man standing behind the bald man with a black suit jacket.<br>No-ref: Replace the selected shirt with a black suit jacket.<br>scope -> shirt | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | ref+none | Remove the hat at the left. | REF 'Remove the hat at the left'（ref+none），但被 mask 的软檐帽是纪念墙旁右侧士兵（box 中心 x=0.82W）戴的；中偏左（x~0.52W）的士兵头上还有另一顶软檐帽，所以 REF 指向了错误的实例。 | Ref: Remove the slouch hat of the soldier standing at the right in front of the memorial wall. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+mask | Add a white stripe on the shoe near the lower center. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9357354`（#1083，扩充尾段 #945–#1083，最严重：阻断）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 阻断 | 人物/服装层级错误 | noref+box | Change the color of the dancer at the left to blue. | U1 mask(box [1460,220,1907,1500])是右侧整个穿黑色波莱罗短外套和铆钉比基尼的舞者;“Change the color of the dancer to blue”是对人重新着色。 | Ref: Change the color of the black bolero jacket of the dancer at the front right to blue.<br>No-ref: Change the color of the selected jacket to blue.<br>重新 mask 为仅含波莱罗短外套 | 目视 |
| U1 | 阻断 | 方位/序数/实例指代错误 | noref+box | Change the color of the dancer at the left to blue. | U1 舞者位于前方右侧（中心 0.75W）；REF 称 'the dancer at the left'。真正位于左侧的舞者在约 0.08W 和约 0.4W。 | Ref: ... the dancer at the front right ... | 目视 |
| U2 | 阻断 | 人物/服装层级错误 | ref+point | Replace the dancer near the center with a red outfit. | U2 mask（box [1006,390,1313,1344]）是一整个穿金色夹克的舞者；“Replace the dancer near the center with a red outfit”是用衣服替换人。 | Ref: Replace the gold cropped jacket of the dancer in the center with a red sequined jacket.<br>No-ref: Replace the selected jacket with a red sequined jacket.<br>重新对金色夹克做 mask | 目视 |
| U3 | 阻断 | 方位/序数/实例指代错误 | noref+point | Remove the speaker near the center. | U3 mask(box [1655,1098,1829,1258],2 个分量)是 U1 舞者双腿之间(0.77W)可见的黑色舞台监听音箱,并不 'near the center';其他音箱位于舞台左/中(~0.2-0.35W)。它还被 U1 严重遮挡,并位于其 box 内。 | Ref: Remove the black floor speaker visible between the legs of the dancer at the front right.<br>or pick a less occluded speaker | 目视 |

### 4.2 最严重为“严重”的 case（349 个）

#### `v2-sa_4394942`（#21，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 编辑不合理/不可执行 | noref+point | Remove the orange outer jacket of the rider behind on the right. | U3 移除了深色骑手身后那位戴紫色头盔的人所穿的橙色外套;移除所穿衣物会使躯干/内层衣物无法确定。 | Ref: Change the color of the orange jacket of the rider behind on the right to navy blue.<br>No-ref: Change the color of the selected jacket to navy blue.<br>将操作由 remove 改为 attribute | 目视 |

#### `v2-sa_4521545`（#22，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 指代歧义 | ref+none | Remove the black helmet of the rider just left of center. | REF 'the black helmet of the rider just left of center'，正式输入为 ref+none；有多名骑手的黑色头盔位于中心附近或偏左（宽度的 x~0.30、0.40（被 mask 者）、0.46、0.48），因此该短语无法唯一指向 box [854,584,933,655] 处被 mask 的头盔。 | Ref: Remove the black helmet of the rider in the olive-green parka directly above the rider with the floral backpack, left of center.<br>或将正式输入改为包含 box/mask | 目视 |

#### `v2-sa_10563539`（#26，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | ref+point | Change the color of the white scoop near the center to red. | 存在多个白色勺子（黑橄榄碗中约 x=1000-1080 src、后方蒜碗中、前方勺子为 U1）。U2 的 mask 是插在中心偏右的洋蓟碗里的白色勺子（box 中心 0.67W）；“near the center”至少同样适合黑橄榄碗中的勺子。 | Ref: Change the color of the white scoop in the artichoke bowl on the right to red. | 目视 |

#### `v2-sa_7474373`（#29，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+mask | Remove the upright sneaker at the front left. | 左前方有一双深色斑点直立运动鞋(视图中 x~50-190);mask 是这双中的右边那只。'the upright sneaker at the front left' 两只都符合,而未被 mask 的那只其实更靠左。 | Ref: Remove the right sneaker of the dark speckled pair at the front left. | 目视 |
| U3 | 严重 | 指代歧义 | ref+point | Change the color of the partly covered shoe at the front right to bright red. | Mask 是位于前方中央（中心 x=0.57W）的一只直立白色运动鞋，上面搭着黄色鞋带；'partly covered shoe at the front right' 较弱——前排更靠右（x 0.6-0.85W）还有许多被部分遮挡的鞋。 | Ref: Change the color of the upright white sneaker partly covered by yellow laces at the front center to bright red. | 目视 |

#### `v2-sa_3206973`（#32，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | ref+point | Replace the skewer partly crossed by another skewer on the right with a long two-pronged metal serving fork. | 右侧红盘（牛肉串）里有许多相互交叉的肉串；被 mask 的那根（box x 1837-1896）是牛肉盘中最左边的肉串，被一根斜向肉串压住。'the skewer partly crossed by another skewer on the right' 适用于该盘中的多根肉串。 | Ref: Replace the leftmost skewer on the right plate of beef skewers with a long two-pronged metal serving fork. | 目视 |

#### `v2-sa_4745279`（#36，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | 编辑不合理/不可执行 | ref+none | Remove the sleeves from the partly visible T-shirt behind the long-haired customer. | U4 mask(box [1381,449,1476,671])只是一个几乎完全藏在长发顾客(U1)身后的人所穿黑色衣物的细窄一角;可见部分中无法明确辨认出袖子,因此“remove the sleeves”没有明确的可见目标,难以判断。 | Ref: Change the color of the partly visible black T-shirt behind the long-haired customer to white.<br>No-ref: Change the color of the selected T-shirt to white.<br>改为 attribute 或删除该单元 | 目视 |

#### `v2-sa_5199668`（#48，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | 编辑不合理/不可执行 | noref+box | Remove the life jacket of the downward-looking swimmer at the left center. | 移除左中部游泳者穿的救生衣（box [713,658,815,706]）；该背心穿在水中的躯干上，移除后躯干/内层衣物未定义。 | Ref: Change the color of the life jacket of the downward-looking swimmer at the left center to sky blue.<br>No-ref: Change the color of the selected life jacket to sky blue.<br>将 remove 改为 attribute 或 add（例如在前面加一个夹着的哨子） | 目视 |

#### `v2-sa_8415518`（#49，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U5 | 严重 | 指代歧义 | ref+mask | Replace the uniform top of the capped person beside the tractor with a short-sleeved work shirt with a square collar. | REF 'the capped person beside the tractor' 符合多个人:U5(迷彩夹克、戴帽,x~0.35W)站在蓝色拖拉机旁,但 U3(黑色制服、戴帽,x~0.83W)同样戴帽且正站在红色拖拉机前;U5 的显著特征是迷彩上衣。 | Ref: Replace the camouflage uniform top of the capped person beside the blue tractor with a short-sleeved work shirt with a square collar. | 目视 |

#### `v2-sa_4817785`（#55，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | mask 质量 | ref+mask | Replace the workwear of the worker farther down the aisle with a two-piece uniform with a short-sleeved shirt. | U3 mask（box [1970,358,2074,550]）勾勒出整个远处工人的轮廓，包括头、帽子和手，而不仅是蓝色工作服；范围（scope）是 'workwear'。 | 细化 mask 以排除头/帽子/手（仅保留衣物），或将该单元的范围改为整个人并配以非服装类编辑。 | 目视 |

#### `v2-sa_7813406`（#58，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U5 | 严重 | mask 质量 | noref+mask | Remove the lower section of the long blue skirt behind and right of the foreground woman to make it knee-length. | REF 指向长蓝裙,但 U5 mask(box [1360,458,1528,829])勾勒的是整个后排女子,包括碎花上衣、披肩和手臂,而不只是蓝裙。 | Re-segment mask to the blue skirt only (below the waist). | 目视 |

#### `v2-sa_2292`（#59，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| case | 轻微 | 中文翻译不一致 |  |  | 两个单元的 NOREF ZH 都把 'horn' 译成了 号角（军号/喇叭），而不是 角/长角。 | ZH NOREF: 移除选中的角 / 将选中的角的材质改为抛光青铜。 | 目视 |
| U1 | 严重 | mask 质量 | ref+none | Remove the upper horn of the beetle sculpture on the left. | REF 说移除左侧甲虫的上角，但红色 mask 除了角之外还覆盖了整个前胸背板/胸甲（约为 box [776,767,1129,974] 的左半部分）；在该 mask 上执行 remove 会删掉甲虫身体的一部分。 | 将 mask 限制在前胸背板以外的弯曲上角，或改写为 'Remove the upper horn of the beetle sculpture on the left, keeping its thorax intact.' | 目视 |
| U2 | 轻微 | mask 质量 | ref+mask | Change the material of the upper horn of the beetle sculpture on the right to polished bronze. | 右侧甲虫上角的蓝色 mask 还包含了整个前胸背板以及下角根部的一小条(另外下角尖端附近有零星杂点)。 | 将 mask 清理为仅含角,去除零星杂点。 | 目视 |

#### `v2-sa_8967676`（#64，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | 方位/序数/实例指代错误 | noref+point | Replace the small silver bauble below and to the girl's left with a hanging silver snowflake ornament. | 被 mask 的小银色装饰球（box x 766-847, y 804-900）位于女孩的画面左侧，即她的右侧。“below and to the girl's left”与按身体左右侧的理解相矛盾。 | Ref: Replace the small silver bauble just image-left of the girl's shoulder, below the elbow-level bauble, with a hanging silver snowflake ornament.<br>相应修正 ZH | 目视 |
| U5 | 严重 | 方位/序数/实例指代错误 | ref+box | Change the material of the partly hidden silver bauble beside the girl's left elbow to polished gold. | 被 mask 的圣诞球(box x 765-850, y 686-775)位于女孩的画面左侧,紧邻她的右肘(她面向镜头)。REF 写的是 'beside the girl's left elbow',按身体左右侧指的是画面右侧的肘部,而那里没有这样的圣诞球。 | Ref: Change the material of the partly hidden silver bauble beside the girl's image-left elbow to polished gold.<br>also fix ZH 左肘 -> 画面左侧手肘 | 目视 |

#### `v2-sa_5842279`（#67，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 编辑不合理/不可执行 | noref+mask | Remove the raised image-left sleeve of the man in front. | U1 移除的是前排男子所穿浅灰色衬衫上抬起的长袖（box [989,285,1133,522]）；移除所穿衣物的一部分会使手臂外观无定义（裸臂？撕裂的衬衫？），该编辑不自然。 | Ref: Change the color of the raised image-left sleeve of the man in front to dark red.<br>No-ref: Change the color of the selected sleeve to dark red.<br>或改述为 'Remove the raised image-left sleeve of the man in front, leaving his bare arm visible.' | 目视 |

#### `v2-sa_2207729`（#70，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 方位/序数/实例指代错误 | ref+point | Remove the tall streetlamp just left of center. | U1 路灯 cx=0.52W 位于图像中心或略偏右，并非 'just left of center'；但作为靠近中心的高大路灯仍然唯一。 | Ref: Remove the tall streetlamp near the center of the image.<br>ZH: 移除画面中间的高街灯。 | 目视 |
| U4 | 严重 | 指代歧义 | noref+mask | Change the color of the slender streetlamp near the canopy at the right rear to matte black. | “slender streetlamp near the canopy at the right rear”——另有一盏路灯（双头，cx~0.76W）位于更靠右、更靠后的位置，同样靠近树冠；U4 是 0.66W 处电影海报亭前的那盏灯。 | Ref: Change the color of the slender streetlamp in front of the movie-poster kiosk to matte black. | 目视 |

#### `v2-sa_3635508`（#73，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 措辞/文法/描述细节 | ref+point | Remove the lower legs of the jeans of the front-left man holding up a camera to make knee-length shorts. | U1 男子举着智能手机拍照,而不是相机。 | Ref: Remove the lower legs of the jeans of the front-left man holding up a phone to take a photo to make knee-length shorts. | 目视 |
| U3 | 严重 | mask 质量 | ref+box | Add one small canvas pouch clipped to the hip of the jeans of the folded-arm man in the middle. | U3 mask 有 3 个分量：抱臂男子的牛仔裤（约源图 x980-1120），以及位于 U2 牛仔裤左边缘、约 x~580 附近的几个零散小碎片；因此 U3 box [577,1110,1122,1421] 横跨了 U2 的牛仔裤和多个人，box 定位（正式 ref+box）无法孤立出目标。 | 删除约 x~580 附近的零散 mask 分量；围绕抱臂男子的牛仔裤重新计算 box，大约为 [978,1110,1122,1300] | 目视 |
| U5 | 严重 | 指代歧义 | ref+none | Remove the lower legs of the trousers of the man partly hidden behind the camera-holder on the left to make knee-length shorts. | U5 的 mask 是位于最左边缘（x~56-143）男子的深色长裤。他站在持相机/手机者（U1 男子，x~230-560）的左侧，下方被戴橙色假发的人遮挡，而不是藏在持相机者身后。仅 REF 输入（ref+none）依赖此描述。 | Ref: Remove the lower legs of the dark trousers of the man standing at the far-left edge, behind the person in an orange wig, to make knee-length shorts.<br>相应更新 ZH | 目视 |

#### `v2-sa_6714451`（#76，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 编辑不合理/不可执行 | noref+point | Remove the raised rim from the red tray of shells and ice at the front center. | U1 移除的是前方红色托盘（堆满冰块和扇贝）的 'the raised rim'；边缘是托盘盛放内容物的侧壁，移除后会留下物理上不合理的平板且冰块外溢；预期结果未定义。 | Ref: Change the color of the red tray of shells and ice at the front center to green.<br>No-ref: Change the color of the selected tray to green.<br>将部分移除（part-remove）改为属性编辑，或替换整个托盘 | 目视 |

#### `v2-sa_8875462`（#82，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | 属性值问题（无变化/含糊） | ref+box | Change the color of the trousers of the striped-shirted man at the far left to dark gray. | 最左侧条纹衬衫男子的裤子（box [0,962,372,1486]）本来就是黑色/很深的颜色；目标深灰色与当前颜色几乎无法区分，因此该编辑近乎无操作，难以判断。 | Ref: Change the color of the trousers of the striped-shirted man at the far left to khaki.<br>No-ref: Change the color of the selected trousers to khaki.<br>更新 spec 值和 ZH 为 卡其色 | 目视 |

#### `v2-sa_9359193`（#86，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | noref+mask | Change the color of the pale-blue T-shirt of the man directly behind him to rust red. | REF “the pale-blue T-shirt of the man directly behind him”使用了代词,只有借助 U1 的句子才能解析;单独存在时(ref-only 消融 / completion_requirement),“him”没有指代。mask 本身是正确的:右侧穿花纹衬衫男孩身后那名男子的浅蓝色“RIP CURL”T 恤。 | Ref: Change the color of the pale-blue T-shirt of the man directly behind the front-right man carrying shopping bags to rust red. | 目视 |

#### `v2-sa_9898846`（#88，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代类别与 mask 不符 | noref+box | Remove the bag of cut fruit at the front left, including its contents. | REF 称其为“bag of cut fruit”，但被 mask 的袋子（box [356,1174,518,1312]）装的是整颗小圆龙眼；真正的切块水果袋（切片杨桃/芒果）就在它后面，所以“cut fruit”会把模型/评判者引向错误的袋子。 | Ref: Remove the plastic bag of longans at the front left, including its contents.<br>No-ref: Remove the selected fruit bag, including its contents.<br>ZH: 移除左前方的一袋龙眼及其中的物品。 | 目视 |
| U3 | 严重 | 指代类别与 mask 不符 | ref+point | Replace the cut-fruit bag partly hidden by loose fruit just left of center with a clear rectangular food box with a lid. | REF 写的是 'cut-fruit bag',但被 mask 的袋子(box [514,1121,679,1293])装的是整颗龙眼,而不是切块水果;旁边装切片黄色水果的袋子更符合 'cut-fruit bag'。另外 'just left of center' 也不精确(中心 x=0.26W)。 | Ref: Replace the bag of longans partly hidden by loose longans, right of the front-left bag, with a clear rectangular food box with a lid.<br>No-ref: Replace the selected fruit bag with a clear rectangular food box with a lid.<br>ZH: replace 切块水果 with 龙眼 | 目视 |

#### `v2-sa_10175525`（#97，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+box | Remove the black sneaker stepping out from behind the foreground person on the right. | REF/ZH 称被 mask 的鞋为 'black sneaker'，但被 mask 的鞋（box [1598,1127,1684,1273]）是带黑色鞋带的灰色帆布高帮鞋。真正的黑色运动鞋（带白色鞋底的黑色 Vans）就在其右侧约 (1840,1350) 处，因此仅凭 ref 的理解很可能选错鞋。 | Ref: Remove the gray high-top sneaker stepping out from behind the foreground person on the right.<br>ZH: 移除右侧从前景人物身后迈出的一只灰色高帮运动鞋。 | 目视 |

#### `v2-sa_10466790`（#100，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+mask | Remove the patterned glove gripping equipment on the child at the front left. | 左前方的孩子戴着两只相同的花纹连指手套,两只都握着滑雪板(上面那只约在合成图 (205,690) 处握着雪板杆,下面被 mask 的那只约在 (140,850))。'the patterned glove gripping equipment' 无法指出下面那只。 | Ref: Remove the lower patterned mitten of the child at the front left.<br>No-ref: Remove the selected mitten. | 目视 |

#### `v2-sa_10691142`（#102，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | 多单元同一物理对象/相互冲突 | ref+box | Add one gray padded shoulder cover over the backpack strap on the image-left shoulder of the fan in dark blue. | U2 是穿深蓝衬衫的粉丝的画面左侧袖子（box [1613,786,1786,992]），U4 是同一粉丝画面左肩上的背包带（box [1728,752,1841,1061]）。背包带 mask 越过并与袖子区域重叠，因此两个编辑作用在同一个人的同一肩部区域。 | 去掉 U4，或将其改为另一个人身上的物体（例如左前方穿绿衬衫粉丝的挂绳/胸牌） | 目视 |

#### `v2-sa_10883561`（#104，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | 指代歧义 | ref+none | Change the color of the back-facing blue chair in the foreground center to light gray. | U4 mask = 位于 box 中心(0.44W,0.65H)的深青色背对椅子,在 U2 后面。另有一把更大的深色背对椅子紧挨着它,位于圆桌 / U1 后面(约 0.50-0.58W,0.55-0.65H),它至少同样符合“the back-facing blue chair in the foreground center”。 | Ref: Change the color of the back-facing dark teal chair directly behind the left foreground chair to light gray. | 目视 |

#### `v2-sa_1165283`（#109，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | mask 质量 | ref+point | Change the color of the red T-shirt of the woman with the green bag to olive green. | U2 T 恤 mask（box [735,594,1121,1047]）的轮廓把斜挎在红色 T 恤上的青绿色腰包一直圈到下摆边缘，因此改色为橄榄色的区域包含了该包。 | 从 T 恤 mask 中去掉青绿色包（和围巾）。 | 目视 |

#### `v2-sa_1810664`（#114，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | 指代歧义 | ref+point | Change the color of the orange top of the reaching child just right of center to pale green. | REF 把该儿童置于“just right of center”,但被 mask 的上衣(box [1614,850,1860,1141],中心 x=0.77W)位于右侧人群中;真正位于中心偏右的儿童是站着的男孩(约 0.55W)和捂着脸的男孩(约 0.65W)。只有“reaching”(伸出双手)能将其区分。 | Ref: Change the color of the orange top of the reaching child in the right group, in front of the bob-haired child, to pale green.<br>No-ref: Change the color of the selected top to pale green. | 目视 |

#### `v2-sa_1901719`（#116，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 措辞/文法/描述细节 | noref+point | Replace the pale trousers of the person pointing at the right rear with knee-length hiking shorts with cargo pockets. | 右后方穿黑衣的孩子是在伸手去够/碰花，并不明显是在指；描述 'person pointing' 较宽泛，但该实例是唯一的。 | Ref: Replace the pale gray trousers of the child in black reaching toward the flowers at the right rear with knee-length hiking shorts with cargo pockets. | 目视 |
| U4 | 严重 | mask 质量 | noref+mask | Add one reflective band around the nearer ankle of the jeans of the bending child in pink at the front right. | U4 针对弯腰的粉衣小孩的牛仔裤，但 mask（box [1206,895,1345,1183]）还圈住了牛仔裤上方粉色夹克的下摆/裙摆区域，不仅仅是裤子。 | 将 mask 修剪为仅蓝色牛仔裤（排除粉色夹克下摆）。 | 目视 |

#### `v2-sa_2127869`（#120，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+none | Tint the front transparent bottle with a white label on the upper shelf pale blue. | 'the front transparent bottle with a white label on the upper shelf' 符合上层货架上数个带白色标签的透明汤力水瓶（紧邻 U1 右侧的那个，以及 U4 左侧的那个）。mask 对应的是 box [1558,126,1666,520] 处的瓶子，即可口可乐瓶右侧的第二个透明瓶。 | Ref: Tint the second clear white-label bottle to the right of the Coca-Cola bottles on the upper shelf pale blue. | 目视 |
| U3 | 轻微 | mask 质量 | noref+box | Replace the yellow-drink bottle just left of the red drink on the upper shelf with a rectangular drink carton with a screw cap. | U3 mask（comps=2）在 box 右边缘相邻的红色饮料瓶上有一小条多余的细长碎片。 | 去掉红色瓶子上的多余碎片。 | 目视 |

#### `v2-sa_2271073`（#122，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | noref+point | Replace the jeans of the long-haired woman in the middle with loose cargo trousers with large thigh pockets. | 被 mask 的牛仔裤属于穿栗色绗缝背心、位于约 0.66W（偏右）、手拿花椰菜的长发女子。另一位穿牛仔裤的长发女子在约 0.40W 处弯腰，更靠近真正的中间，因此 "the long-haired woman in the middle" 可能指向错误的人。 | Ref: Replace the jeans of the long-haired woman in the maroon quilted vest with loose cargo trousers with large thigh pockets. | 目视 |

#### `v2-sa_2315709`（#123，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+mask | Change the color of the dark trousers of the white-shirted man in the middle to light gray. | 这群人中几乎每个男子都穿白衬衫、深色长裤。被 mask 的长裤（box x 859-991，约 0.41W）属于站在 U2 与 U3 男子之间、正在读红色书的白色细条纹衬衫男子；'the white-shirted man in the middle' 无法唯一指向他。 | Ref: Change the color of the dark trousers of the man in the pinstriped white shirt reading a red book, between the two masked white-shirted readers, to light gray. | 目视 |
| U3 | 严重 | 方位/序数/实例指代错误 | ref+point | Add one small pale-blue chest pocket sewn onto the white shirt of the book-holder just right of center. | REF 说“the book-holder just right of center”,但被 mask 的衬衫位于 box x 971-1104(中心 0.46W),即略偏图像中心左侧;其右侧的白胡子男子(约 0.53W)才是中心偏右的那位。每个人也都拿着书。 | Ref: Add one small pale-blue chest pocket sewn onto the white shirt of the book-holder just left of center, standing right of the man in the pinstriped shirt. | 目视 |
| U4 | 严重 | 指代歧义 | noref+point | Remove the black wide-brimmed hat in the upper-left row. | 上排有几十名男子戴着相同的黑色宽檐帽；'the black wide-brimmed hat in the upper-left row' 无法确定被 mask 的帽子（~0.29W,0.07H）。此外，存储的 box [597,115,950,215] 远宽于 mask（mask 仅大致覆盖 x 600-740），因此 box 定位也包含了相邻的头部。 | Ref: Remove the black wide-brimmed hat of the man in the top rows directly above the masked white-shirted reader at left center.<br>将 box 收紧到帽子 mask 的范围 | 目视 |

#### `v2-sa_2506761`（#126，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+mask | Remove the tall pale-drink bottle near the front center, including its contents. | 'the tall pale-drink bottle near the front center' 也符合其正右方偏前的浅色饮料瓶(原图 x~1250-1380,更靠下)以及前排的浅色瓶;被 mask 的瓶子(box x 1031-1271)在中排,底部被前排一只瓶子部分遮挡。 | Ref: Remove the tall pale-drink bottle in the center of the middle row, whose base is hidden behind a capped front bottle.<br>No-ref: Remove the selected bottle.<br>spec remove_mode=contents is inconsistent with removing the whole bottle; set remove_mode=whole and drop 'including its contents' | 目视 |

#### `v2-sa_3397098`（#134，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | 方位/序数/实例指代错误 | noref+mask | Change the color of the jeans visible below the large flag just right of center to dark brown. | U4 mask(cx=0.78W)是图像右侧所举大号土耳其国旗下方的一条深色牛仔裤腿;“just right of center”更符合约 0.57W 处举在女孩上方的另一面大土耳其国旗。 | Ref: Change the color of the jeans visible below the large Turkish flag on the right to dark brown.<br>ZH:将右侧大土耳其国旗下方露出的牛仔裤改为深棕色。 | 目视 |

#### `v2-sa_4132362`（#140，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | ref+box | Change the color of the jacket visible above the chair of the back-facing man to burgundy. | 两个男子背对镜头坐在藤椅上:被 mask 的那位(灰夹克、花纹帽,左中位置的椅子)和右侧另一位(深色头发、橙/栗色夹克)。'the back-facing man' 无法唯一指出 U2 目标。 | Ref: Change the color of the gray jacket of the back-facing man in the patterned cap on the left to burgundy. | 目视 |

#### `v2-sa_4720489`（#147，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U5 | 严重 | 方位/序数/实例指代错误 | ref+mask | Add one small rectangular street-name sign mounted on the pole just below the lamp of the streetlamp in front of the small eaves just right of center. | REF 把灯定位在“in front of the small eaves just right of center”,但被 mask 的路灯位于 x=0.38W(2661 中的 box 996-1045),明显在图像中心左侧;中心右侧唯一的灯是 U1。ref-only 模型会去中心右侧寻找。REF 也过长(27 词)。 | Ref: Add one small rectangular street-name sign mounted on the pole just below the lamp of the streetlamp standing beside the light-blue outdoor chairs, left of the pink building. | 目视 |

#### `v2-sa_4812427`（#149，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 属性值问题（无变化/含糊） | ref+none | Change the color of the jeans of the floral-shirted man on the right to dark blue. | 花衬衫男子的牛仔裤（box [1614,591,1792,1026]）本身已经是中等/深色牛仔蓝；'to dark blue' 几乎无变化，难以评分。 | Ref: Change the color of the jeans of the floral-shirted man on the right to light gray.<br>No-ref: Change the color of the selected trousers to light gray. | 目视 |
| U4 | 严重 | 指代类别与 mask 不符 | ref+point | Add one small back pocket sewn onto the short skirt of the back-facing woman. | REF/NOREF/ZH 称目标为“short skirt”，但 U4 mask（box [1264,377,1470,726]）覆盖的是女士从肩到下摆的橙色连体 T 恤裙。 | Ref: Add one small back pocket sewn onto the short orange dress of the back-facing woman.<br>No-ref: Add one small back pocket sewn onto the selected dress.<br>将 scope/category 设为 dress。 | 目视 |

#### `v2-sa_5585164`（#158，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 方位/序数/实例指代错误 | noref+mask | Add one small round blue elbow patch sewn onto the right-side burgundy sleeve of the pink-hatted child. | REF 写 'right-side burgundy sleeve'，ZH 写 靠画面右侧，但被 mask 的袖子（box [1795,537,2100,1158]）是孩子唯一可见的手臂，位于她（被遮挡的）躯干的图像左侧；该案例中其他单元使用图像侧的措辞（'left-side' = 图像左），因此 'right-side' 与 mask 矛盾。它是她解剖学意义上的右臂。 | Ref: Add one small round blue elbow patch sewn onto the visible burgundy sleeve of the pink-hatted child.<br>将 ZH 改为 粉帽孩子可见的酒红色衣袖。 | 目视 |

#### `v2-sa_5860767`（#161，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | 指代歧义 | ref+mask | Add one small blue cloth patch sewn onto the upper chest below the collar of the white shirt inside the young man's jacket at the back. | “the young man's jacket at the back”适用于背景中的多名年轻男子;U4 是那名年轻男子(左后方,cx=0.24W)身穿藏青外套、芥黄色兜帽内衬的白衬衫衣领。 | Ref: Add one small blue cloth patch sewn onto the upper chest below the collar of the white shirt of the young man in the navy jacket with a mustard hood at the back left. | 目视 |

#### `v2-sa_5904224`（#162，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 方位/序数/实例指代错误 | noref+box | Remove the nearest wicker chair facing the camera with its back to the table. | 被 mask 的最靠前的藤椅是从背面看到的：其编织靠背朝向镜头，座面朝向桌子，与被称为 'back-facing' 的 U2/U3 朝向相同。REF/ZH 的 'facing the camera with its back to the table' 与图像所示相反。 | Ref: Remove the nearest wicker chair, which has its back to the camera and faces the table.<br>ZH -> 移除最靠前、背对镜头面向桌子的藤椅。 | 目视 |

#### `v2-sa_6082361`（#164，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | ref+box | Remove the hood from the white hooded jacket of the bending person at the back. | REF 称目标为 'white hooded jacket',但后排弯腰者被 mask 的衣物(box [935,342,1155,661])是米色/棕褐色;中心稍右(视图中 ~x 830-920)的一个孩子穿的才是真正的白色夹克,所以 'white hooded jacket' 可能误导模型/评审。 | Ref: Remove the hood from the beige hooded jacket of the bending person at the back.<br>No-ref: Remove the hood from the selected jacket.<br>ZH: 白色 -> 米色 | 目视 |

#### `v2-sa_616161`（#165，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | mask 质量 | noref+box | Remove the left-side black short sleeve of the leftmost man. | U1 mask 只是图像左侧的黑色短袖（源图 x~120-205），但存储的 box [120,906,387,993] 横跨整个胸部直到该男子图像右侧的袖子（box 右下角附近有一个零散像素）。正式输入是 noref+box，因此 box 同时覆盖了两只袖子和胸部，无法说明选中的是哪只袖子。 | 删除零散 mask 像素，并围绕左袖重新紧致计算 box，约为 [120,906,205,993] | 目视 |

#### `v2-sa_6330783`（#167，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+point | Remove the top handle of the pale-purple suitcase at the front right. | 被 mask 的把手(box x 1430-1705,y 1015-1122;中心 0.59W,0.71H,合成图约 y 640/900)位于展示区中间一个淡粉/淡紫色箱子上,其前方有两排箱子(深红色罗纹的、大号粉色的)。“the pale-purple suitcase at the front right”并不能描述它:它既不在前方也不在右侧,而且存在多个淡粉/淡紫色箱子。 | Ref: Remove the top handle of the pale-pink suitcase directly behind the dark-red ribbed suitcase at the front center, next to the gray case with a green 'NEW' sticker. | 目视 |
| U2 | 严重 | 指代歧义 | noref+point | Replace the top handle of the bright-pink suitcase at the front center with a looped brown leather handle. | 展示中有很多亮粉色箱包（例如左中带凸起提手的粉色箱子、右前方的大粉色箱子）。被 mask 的提手（中心 0.45W,0.62H）位于中间几排红色棱纹箱子后面的粉色箱子上，并不明显处于 'at the front center'。 | Ref: Replace the top handle of the pink suitcase just behind the front-center dark-red ribbed suitcase, in front of the champagne-colored case, with a looped brown leather handle. | 目视 |
| U4 | 严重 | 指代歧义 | noref+mask | Change the color of the top handle of the pale-pink ribbed suitcase toward the center rear to black. | 中后排摆满了数十个浅粉色罗纹箱子；被 mask 的把手（box x 1498-1687, y 682-741）是众多相同把手中的一个，“the pale-pink ribbed suitcase toward the center rear”适用于多个。 | 用关系锚点重写 REF（例如“directly behind the champagne-colored case”/ 相对于其右侧深红色箱子）或删除该 unit | 目视 |
| U5 | 严重 | 指代歧义 | ref+none | Replace the top handle of the gray suitcase on the right with a curved wooden handle. | 右半边有多个灰色箱子(如 x~0.8-0.9W 的银灰色箱子);被 mask 的把手(中心 0.65W,0.63H)在 U1 右侧中排的一个灰色箱子上。'the gray suitcase on the right' 符合多个实例。 | Ref: Replace the top handle of the gray suitcase with a green 'NEW' sticker, just right of the pale-pink case at the center, with a curved wooden handle. | 目视 |

#### `v2-sa_6371955`（#168，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 编辑不合理/不可执行 | ref+mask | Remove the left-side wide sleeve of the striped-top woman on the left. | U1 移除的是该女子所穿白色图案法被（happi）风格上衣的图像左侧宽袖（box [329,471,531,812]）；移除所穿衣物的一部分会使手臂/肩部处于未定义状态。'left-side' 也没有标明是图像左侧。 | Ref: Change the color of the image-left wide sleeve of the striped-top woman on the left to dark navy.<br>No-ref: Change the color of the selected sleeve to dark navy.<br>或改为替换（例如换成短的盖肩袖） | 目视 |

#### `v2-sa_7223032`（#175，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 方位/序数/实例指代错误 | ref+point | Add a short white fringe along the outer edge of the nearest multicolored umbrella canopy on the left. | U1 mask 是左上方（box y 651-926，中等高度）的红/蓝/绿/黄雨伞。左下角（黄/绿/蓝，约 y 1200-1500）有一把更大的雨伞，明显更靠近镜头，因此 "the nearest multicolored umbrella canopy on the left" 指向了错误的一把。 | Ref: Add a short white fringe along the outer edge of the multicolored umbrella canopy at the upper left over the vegetable stalls. | 目视 |
| U4 | 严重 | 方位/序数/实例指代错误 | noref+mask | Replace the pale long-sleeved top of the white-helmeted customer between the central umbrellas with a short-sleeved striped blouse. | REF 称其为“pale long-sleeved top”，但戴白色头盔的顾客被 mask 的上衣（box 777-852 x 704-772）是深炭灰色。颜色词与图像矛盾。 | Ref: Replace the dark gray long-sleeved top of the white-helmeted customer between the central umbrellas with a short-sleeved striped blouse.<br>相应修正 ZH 颜色词 | 目视 |

#### `v2-sa_7337725`（#176，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | ref+mask | Change the color of the pale saddle pad on the middle horse to navy blue. | 共有四匹马;'the middle horse' 可能指后腿直立的黑马(第 2 匹),也可能指绿/白衣骑手的棕马(第 3 匹,即被 mask 的,box [1491,817,1601,952])。黑马的骑手靴下也露出浅色/白色马鞍垫,所以 'pale saddle pad on the middle horse' 不能唯一指出该 mask。 | Ref: Change the color of the white saddle pad under the rider in the green-and-white shirt, on the second horse from the right, to navy blue. | 目视 |

#### `v2-sa_7434362`（#178，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 措辞/文法/描述细节 | noref+box | Remove the sleeves from the navy shirt of the beret-wearing man beside the blue wall. | 蓝墙旁的 U1 男子戴的是带徽章的深色警帽式鸭舌帽，并不明确是贝雷帽；此外 physical_parent_zh 写的是 中间深红衣者，而衬衫其实是藏青色。 | Ref: Remove the sleeves from the navy uniform shirt of the policeman beside the blue wall.<br>将 physical_parent_zh 改为 蓝墙旁警员 | 目视 |
| U3 | 严重 | 指代歧义 | noref+point | Replace the pale collar visible behind the rightmost man's neck with a short stand-up collar. | U3 mask(box [1903,620,2000,687],最右边缘)覆盖的是部分可见的最右侧人物颈后的深藏青色衣领;REF/ZH 称其为“the pale collar”(浅色衣领)。该属性与像素内容矛盾,评判者会去寻找并不存在的浅色衣领。 | Ref: Replace the dark navy collar visible at the back of the rightmost man's neck with a short stand-up collar.<br>ZH:将最右男子颈后露出的深蓝色衣领替换为短立领。 | 目视 |

#### `v2-sa_7543855`（#180，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U5 | 严重 | 指代歧义 | ref+mask | Replace the pale trousers partly hidden by the table legs at the left rear with loose ankle-length linen trousers. | REF/ZH 称目标为 'pale trousers'（浅色裤子），但左侧桌子后站立者（黑色 T 恤、双手交握、灰色运动鞋）被 mask 的裤子 [534,860,630,1133] 是黑色/非常深的颜色。颜色描述与像素矛盾，可能让仅凭 ref 的模型选到另一件更浅色的衣物。 | Ref: Replace the black trousers partly hidden by the table legs at the left rear with loose ankle-length linen trousers.<br>ZH: 将左后方桌子后被桌腿截断的黑色裤子替换为宽松及踝亚麻长裤。 | 目视 |

#### `v2-sa_7774310`（#185，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 指代歧义 | ref+point | Remove the right-side short sleeve of the black-uniformed person at the far right. | U3 mask（box x 2065-2195）是穿黑色 Adidas polo 衫、挂着工牌挂绳的男子图像右侧的短袖（约 0.80-0.97W）。最右边缘还站着另一位戴帽子、口罩并佩戴 'HAFIS..' 胸牌的黑衣制服人员，因此 'the black-uniformed person at the far right' 指向的是那个人，而不是被 mask 的人。 | Ref: Remove the right-side short sleeve of the man in the black Adidas shirt with a lanyard ID card on the right. | 目视 |

#### `v2-sa_7792022`（#186，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | mask 质量 | ref+none | Change the color of the front fender of the ridden burgundy motorcycle to glossy black. | U2 mask（3 个组件）覆盖了酒红色前挡泥板，但同时也覆盖了叉后方一块独立的深酒红色下整流罩/护腿板（视图 x~575-625，y~660-810），它不属于挡泥板；将其改成黑色会改动多余的部件。 | 将 U2 mask 裁剪为仅车轮上方的前挡泥板（去掉下整流罩组件）。 | 目视 |

#### `v2-sa_8139733`（#189，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 中文翻译不一致 | noref+box | Remove the bow tie from the front-center rabbit figurine holding a pocket watch. | EN：移除前排中央拿怀表的兔子的领结。ZH：“移除前排中央拿怀表兔子摆件的身体主体，不含怀表和标签的领结”——表述混乱，读起来像是移除身体；操作范围不一致。 | ZH: 移除前排中央拿怀表兔子摆件的领结。 | 目视 |
| U2 | 轻微 | 中文翻译不一致 | ref+point | Change the color of the body of the rabbit figurine at the far right foreground to ivory white. | ZH '将最右前排兔子摆件的身体主体,不含挂表改为象牙白色' 含有乱码的 mask 备注文字;U3 的 ZH 同样如此:'身体主体,不含底座和号管的材质'。 | ZH U2: 将最右前排兔子摆件的身体改为象牙白色。 U3: 将左侧前排吹号兔子摆件身体的材质改为拉丝青铜。 | 目视 |
| U3 | 严重 | 指代歧义 | noref+point | Change the material of the body of the trumpet-playing rabbit figurine at the front left to brushed bronze. | 有两只穿爱心图案外套、吹小号的兔子并排；被 mask 的那只（box x 771-1035, y 621-1185）是更靠 BACK 的一只；另一只吹小号的兔子（源图约 x 1000-1250，在深色底座上）站在它前面。'the trumpet-playing rabbit figurine at the front left' 更自然地指向前面那只。 | Ref: Change the material of the body of the rear one of the two trumpet-playing rabbit figurines (the left, farther one) to brushed bronze. | 目视 |
| U4 | 严重 | 指代歧义 | ref+box | Replace the rabbit figurine body in a waistcoat at the center rear with a similarly posed cat figurine body in a waistcoat. | 中后方并排站着两只穿青绿色马甲、金耳朵的兔子（U5 是左边那只，U4 是右边那只）。'the rabbit figurine body in a waistcoat at the center rear' 对两只都适用。 | Ref: Replace the body of the right one of the two gold-eared rabbit figurines in teal waistcoats at the center rear with a similarly posed cat figurine body in a waistcoat. | 目视 |

#### `v2-sa_8310334`（#192，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | 指代歧义 | noref+mask | Add one small flap pocket on the visible outer thigh of the trousers of the camera-holding woman at the upper right. | REF 称主人是“the camera-holding woman at the upper right”,但被 mask 的裤子(box x2029-2224)属于手持金色叶形供奉杖、背黑色绗缝单肩包的青绿上衣女士;源图中看不到相机。该识别属性是错误的(跪在前面的男孩拿的是手机)。 | Ref: Add one small flap pocket on the visible outer thigh of the dark trousers of the teal-shirted woman with a black quilted bag at the upper right.<br>同时更新 ZH:给右上方背黑色绗缝包的青绿上衣女士的深色裤子... | 目视 |

#### `v2-sa_8402603`（#193，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U5 | 严重 | 方位/序数/实例指代错误 | ref+box | Remove the empty orange seat shell visible on both sides of the central pole. | REF 称橙色壳体在 'on both sides of the central pole'。将被 mask 的椅子（box [191,1141,677,1443]）一分为二的杆是位于约 x=450（0.2W）的前景钢杆。该案例自己的 U4 把同一根杆称为 'the pole on the left'。图中真正的中心（约 x=1180）还有另一根镀铬杆，因此 'central pole' 指向了错误的位置。 | Ref: Remove the empty orange seat shell visible on both sides of the foreground pole on the left.<br>ZH: 移除左侧前景立杆两侧露出的橙色空座椅壳。 | 目视 |

#### `v2-sa_8718469`（#195，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | ref+box | Change the color of the left-side backpack shoulder strap of the back-facing soldier in the foreground center to black. | U2 背带（box 中心 x=0.68）位于中心偏右的背对镜头的士兵身上；另一名背着大型迷彩背包的背对士兵站在真正的图像中心（x~0.5），因此“back-facing soldier in the foreground center”指向了错误/有歧义的士兵。 | Ref: Change the color of the left-side backpack shoulder strap of the back-facing soldier right of center, in front of the grey pillar, to black. | 目视 |

#### `v2-sa_8981826`（#199，原版 #0–#199，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 方位/序数/实例指代错误 | ref+mask | Replace the visible ladder-back frame of the second green chair from the left with a rounded wooden backrest frame with two upright slats. | 图中只有一把绿色椅子（总体上是从左数第二把椅子）。'the second green chair from the left' 暗示至少有两把绿色椅子，按字面是错误的。 | Ref: Replace the visible ladder-back frame of the green chair, second from the left, with a rounded wooden backrest frame with two upright slats.<br>同时将 ZH 修正为 左起第二把椅子（绿色椅子） | 目视 |
| U4 | 严重 | 方位/序数/实例指代错误 | noref+point | Add one small cream-colored seat cushion on the seat of the second brown chair from the right. | U4 的目标是红褐色纺锤靠背温莎椅,整体上是从右数第二把椅子;最右边的椅子在 U3 中被称为“black”,因此“the second brown chair from the right”是错误的(右侧只有一把棕/红褐色椅子)。 | Ref: Add one small cream-colored seat cushion on the seat of the reddish-brown spindle-back chair, second from the right.<br>相应修正 ZH | 目视 |

#### `v2-sa_10086904`（#208，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 属性值问题（无变化/含糊） | ref+point | Change the color of the streetlamp beneath the SEIBU sign on the right to matte black. | SEIBU 招牌下被 mask 的路灯杆(box x1873-1927)本来就是深灰/近黑色金属杆,所以 'to matte black' 几乎等于无变化,难以验证。 | Ref: Change the color of the streetlamp beneath the SEIBU sign on the right to bright gold.<br>No-ref: Change the color of the selected streetlamp to bright gold. | 目视 |

#### `v2-sa_10119096`（#210，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| case | 严重 | 多单元同一物理对象/相互冲突 |  |  | 两个单元都在同一位前景女子身上：U1 是她的黑色皮背包（box [1349,370,1564,645]），U2 是她的灰色外套（box [1255,399,1669,931]）；外套 mask 包裹着背包。协议要求各单元位于不同的物理母体上。 | 保留一个单元（例如 U2 外套），把另一个换成位于不同人物上的单元，例如左侧骑滑板车的戴兜帽男子的牛仔裤。 | 目视 |
| U1 | 轻微 | 中文翻译不一致 | noref+box | Replace the foreground woman’s backpack with a tan canvas roll-top backpack. | Payload 'tan' 被翻译为 棕色（brown）；tan 应为 棕褐色/卡其色。 | ZH: 将前景女子的背包替换为一个卡其色帆布卷口背包。 | 目视 |

#### `v2-sa_10425350`（#238，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | ref+point | Remove the blue pedestrian-crossing sign. | REF “the blue pedestrian-crossing sign”,但至少还有另外两个蓝色人行横道标志可见(中心附近 x~0.53,y~0.56 处红绿灯旁的小号标志,以及下方杆子右边缘 x~0.89,y~0.51 处的一个);被 mask 的那个位于右上方杆子高处(box [2017,266,2111,424])。 | Ref: Remove the blue pedestrian-crossing sign mounted high on the pole at the upper right. | 目视 |

#### `v2-sa_1045709`（#244，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | ref+point | Change the color of the purple T-shirt behind the foreground swimmers to coral orange. | U2 mask 是上方河岸上靠着树干、双手叉腰的远处小个子男子的深紫色 T 恤(2268px 图像中 box 1248-1317, 457-532)。'behind the foreground swimmers' 涵盖了岸上数十人的整个人群,其中好几人穿粉/紫色上衣,所以 REF 几乎无法定位他。 | Ref: Change the color of the purple T-shirt of the man standing with hands on hips against a tree trunk on the upper bank to coral orange.<br>ZH: 将上方岸边靠树干双手叉腰男子的紫色T恤改为珊瑚橙色。 | 目视 |

#### `v2-sa_10682062`（#259，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | noref+point | Remove the suspended streetlight left of the church spire. | U2 灯（box 中心 0.15W,0.64H）悬挂在与塔基齐平的线上；教堂尖顶左侧至少还有 4 盏其他悬挂灯（树木上方较低处约 0.2W,0.78H、约 0.17W,0.85H、约 0.08W,0.91H，以及左上角灯 0.0W,0.34H），因此 REF 无法单独指出它。 | Ref: Remove the suspended streetlight hanging on the middle wire at the left, level with the base of the church tower. | 目视 |

#### `v2-sa_10733610`（#265，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代类别与 mask 不符 | ref+mask | Change the color of the mounted statue’s helmet to gold. | U1 mask 是骑马雕像的圆顶礼帽式帽子（圆顶带帽檐），不是头盔；戴头盔的雕像是左边另一尊（罗马/带冠饰的）雕像，所以“helmet”可能误导。 | Ref: Change the color of the bowler hat of the mounted statue to gold.<br>No-ref: Change the color of the selected hat to gold.<br>category: hat; ZH: 将骑马雕像的圆顶礼帽的颜色改为金色。 | 目视 |

#### `v2-sa_10744750`（#266，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | noref+mask | Replace the gray puffer jacket behind the car with a black leather jacket. | U3 mask(box [1322,555,1489,770])覆盖一件深灰色绗缝羽绒服。将其替换为 'a black leather jacket' 保持了夹克类别和结构,只改变了材质/颜色。 | Ref: Replace the gray puffer jacket behind the car with a red hooded sweatshirt.<br>No-ref: Replace the selected jacket with a red hooded sweatshirt.<br>or convert to attribute: 'Change the material of the gray puffer jacket behind the car to black leather.' | 目视 |

#### `v2-sa_10803560`（#277，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | noref+box | Change the color of the leftmost flower cluster along the bottom to white. | 被 mask 的花簇（box x 778-933，y 990-1169，中心 0.32W,0.72H）是中下部中央三簇鲑鱼色花簇中最左边的一簇。其他橙/粉色花簇位于相近或更低的高度、更靠左处（约 x 0.02-0.10W，y ~0.65-0.70H），因此 'the leftmost flower cluster along the bottom' 不能唯一选中它。 | Ref: Change the color of the small salmon-pink bougainvillea cluster at the left end of the low row of three clusters, left of the image center, to white. | 目视 |

#### `v2-sa_10817186`（#280，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代歧义 | noref+point | Change the color of the central person’s red coat to navy blue. | 被 mask 男子（x~0.37W）左侧站着一个动态模糊、穿亮红色夹克的人。'Central person' 仍然指向 0.49W 处穿深红色外套、清晰的男子，但用更具体的 REF 指称他会更稳妥。 | Ref: Change the color of the dark red coat of the gray-haired man standing in the center to navy blue. | 目视 |
| U2 | 严重 | 指代歧义 | ref+box | Replace the short puffer jacket on the right with a tan wool coat. | REF“the short puffer jacket on the right”并不能唯一指出被 mask 的男子（x~0.86W）：就在他左侧，戴毛皮兜帽正在拍照的女子（x~0.77W）也穿着深棕色绗缝羽绒服，右侧人群里还有更多棉服。被 mask 的是那位穿牛仔裤、回头看向镜头的男子。 | Ref: Replace the dark short puffer jacket of the man on the right looking back over his shoulder with a tan wool coat. | 目视 |

#### `v2-sa_1093348`（#288，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | noref+point | Remove the satellite dish below the cruise ship. | 'the satellite dish below the cruise ship' 符合不止一个天线:除了被 mask 的高椭圆形天线 [679,795,735,949],同一屋顶上其右下方还有第二个白色天线(原图约 x760-800, y900-960),同样在邮轮下方。REF 没有区分二者。 | Ref: Remove the large upright satellite dish on the rooftops at the left center, below the cruise ship.<br>ZH: 移除左中屋顶上、邮轮下方那个较大的竖立卫星天线。 | 目视 |

#### `v2-sa_10984053`（#295，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+box | Remove the nearest hanging fruit banner. | 'the nearest hanging fruit banner' 有歧义：悬挂在右侧货架上方（右上，x~1450-2000）的大型水果横幅 'Risparmio Quotidiano' 比悬挂在过道中央上方、被 mask 的竖向 'Ortofrutta' 横幅（box x 946-1078）更靠近镜头；其他水果横幅也挂在更远处。 | Ref: Remove the nearest vertical 'Ortofrutta' fruit banner hanging from the ceiling above the aisle.<br>ZH: 移除过道上方天花板悬挂的最近一面竖幅“Ortofrutta”水果海报。 | 目视 |

#### `v2-sa_11017973`（#297，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+box | Remove the discarded bottle at the lower left. | REF “the discarded bottle at the lower left”——被 mask 的瓶子躺在(约 0.19W,0.82H),但蓝色包装袋旁更靠左(约 0.08W,0.79H)还有另一个被丢弃的塑料瓶,(0.04W,0.68H)附近还有一个小的;“at the lower left”至少同样符合另一个瓶子。 | Ref: Remove the discarded plastic bottle with a dark blue label lying alone on the dirt below the yellow jerrycans, lower left of center.<br>ZH:移除黄色水桶左下方空地上单独躺着的蓝标签塑料瓶。 | 目视 |

#### `v2-sa_11136335`（#307，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+none | Replace the decorative streetlamp at the far left with a black lantern-style streetlamp. | 被 mask 的最左侧路灯已经是带三个灯笼头的深色/黑色铸铁灯杆；把它替换为“a black lantern-style streetlamp”得到的基本是同一物体，因此该编辑不是明确的类别/结构变化，难以评分。 | Ref: Replace the decorative streetlamp at the far left with a modern single-arm LED street light.<br>No-ref: Replace the selected streetlamp with a modern single-arm LED street light. | 目视 |

#### `v2-sa_1118244`（#310，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+point | Replace the nearest blue bench with a wooden slat bench. | 画面最右边缘（原图约 x~2120-2152，y~1150-1200）还可部分看到第三张深蓝色长椅，其在画面中位置比被 mask 的长椅（box [1889,1067,1986,1125]）更低，因此可以说更近；"the nearest blue bench" 因而不唯一。U2（"immediately behind the nearest bench"）继承了这一歧义。 | Ref: Replace the blue bench on the lawn-side walkway at the lower right, next to the curved path, with a wooden slat bench.<br>或者将 U1 改写为 "the fully visible blue bench nearest the camera"；将 U2 调整为 "the blue bench just above it near the steps"。 | 目视 |

#### `v2-sa_1155755`（#317，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 多单元同一物理对象/相互冲突 | noref+point | Add a small waterproof name tag on the boarding passenger’s floral shoulder bag. | U1（草帽，box 1438-1498,844-884）和 U3（花卉单肩包，box 1479-1552,905-1043）都由同一位穿粉色上衣和橙色救生衣的登船乘客佩戴/携带；两个 unit 绑定到同一个人违反了 unit 独立性。 | 删除 U3（或 U1），或将其重新绑定到另一个人的物品，例如站在右侧船中的那个人的橙色救生衣 | 目视 |

#### `v2-sa_1309983`（#339，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | ref+mask | Replace the bent-over worker’s safety vest with an orange reflective safety vest. | U3 mask 是弯腰工人的黄色高可见度反光背心(box x1303-1497);将其替换为“an orange reflective safety vest”仍属同一类别和结构,仅改变颜色。 | Ref: Change the color of the bent-over worker's safety vest to orange.<br>No-ref: Change the color of the selected safety vest to orange.<br>将操作改为 attribute,或替换为结构不同的衣物(例如带兜帽的高可见度雨衣) | 目视 |

#### `v2-sa_1317508`（#340，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 指代歧义 | ref+box | Replace the large waterside shrub just right of the boat with a white-flowering hydrangea bush. | REF 'the large waterside shrub just right of the boat' —— 被 mask 的灌木位于 x~1876-2084（0.90W），远离船尾（~0.66W）；紧邻船右侧（~0.68-0.75W）的灌木/芦苇更符合 'just right of the boat'。 | Ref: Replace the large rounded waterside shrub below the silver car at the right with a white-flowering hydrangea bush.<br>ZH: 将右侧银色汽车下方水边的大圆灌木替换为一丛开白花的绣球。 | 目视 |

#### `v2-sa_1318943`（#341，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | ref+none | Remove the rightmost white car on the quay. | U2 mask 是右前方的银/白色掀背车（box x 2098-2222），但原图显示它正后方还有另一辆白车（部分可见，向右延伸），图像右边缘（x~2240）还有第三辆被截断的白车，因此“the rightmost white car on the quay”不能唯一或正确地指出它。 | Ref: Remove the right one of the two silver hatchbacks parked side by side at the front of the quay beside the boat. | 目视 |

#### `v2-sa_1332464`（#342，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the left elephant rider’s floral hat with a beige straw hat. | 左侧骑手戴着带粉/蓝彩绘图案的宽檐编织帽。将其替换为 "a beige straw hat" 保持了相同的帽子结构,主要只改变颜色/图案,因此接近属性编辑。 | Ref: Replace the left elephant rider’s patterned wide-brim hat with a dark baseball cap.<br>No-ref: Replace the selected hat with a dark baseball cap. | 目视 |

#### `v2-sa_1408122`（#348，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 多单元同一物理对象/相互冲突 | noref+box | Add a small reflective strip on the puffer-jacketed man’s blue backpack. | U3 的蓝色背包（box [1797,1212,1827,1297]）背在 U1（box [1818,1150,1902,1282]）那件黑色羽绒服的穿着者背上。两个 box 相接，且 REF 本身就写着 'the puffer-jacketed man's blue backpack'。 | 删除 U3，或替换为广场上另一个人或物体上的对象 | 目视 |

#### `v2-sa_1458556`（#350，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 编辑不合理/不可执行 | ref+mask | Replace the right bench behind the foreground flowerbed with a wooden slat bench. | 被 mask 的长椅(box [527,878,810,1009])本来就是带黑色金属扶手的深色木条长椅;“Replace ... with a wooden slat bench”基本上没有产生类别/结构变化。 | Ref: Replace the right bench behind the foreground flowerbed with a white stone bench.<br>No-ref: Replace the selected bench with a white stone bench.<br>选择与现有木条长椅结构不同的 payload。 | 目视 |

#### `v2-sa_14654`（#352，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 属性值问题（无变化/含糊） | ref+mask | Change the material of the blue-capped bottle at the left of the middle row to green glass. | U3 瓶子（中排最左，蓝色瓶帽）本身已经是非常深色（可能是深绿/黑色）的玻璃酒瓶；'change the material to green glass' 几乎无变化（glass->glass），评判者无法可靠验证其成功与否。 | Ref: Change the material of the blue-capped bottle at the left of the middle row to clear transparent glass.<br>No-ref: Change the material of the selected bottle to clear transparent glass.<br>或对蓝色瓶帽使用颜色属性，例如改为红色 | 目视 |

#### `v2-sa_1481159`（#357，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the bucket beside the left man’s feet with a red plastic bucket. | 被 mask 的物体是一个灰色镀锌金属桶；'Replace ... with a red plastic bucket' 保持类别（桶）不变，只改变了颜色/材质。 | Ref: Replace the metal bucket beside the left man's feet with a woven bamboo basket.<br>No-ref: Replace the selected bucket with a woven bamboo basket.<br>或改为属性编辑：将桶的材质改为红色塑料 | 目视 |

#### `v2-sa_1490608`（#358，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+box | Change the color of the red stripe along the lower nose of the plane to blue. | 涂装条纹沿下机头的两侧都有（画面右侧镜像的条纹清晰可见）；mask 只覆盖画面左侧那条（box x911-1095），且同时包含蓝色和红色条带，而 REF 说 'the red stripe along the lower nose' 没有指明侧别。 | Ref: Change the color of the blue-and-red stripe along the image-left side of the plane's lower nose to green.<br>No-ref: Change the color of the selected stripe to green.<br>添加侧别限定；或将 mask 限制为仅红色条带 | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the yellow taxiway sign at the lower right with a yellow taxiway sign reading “T2”. | U2 把右下角的黄色滑行道标志替换为“a yellow taxiway sign reading T2”——同一物体类别、形状和颜色;只改变文字内容,这不属于类别/结构替换(而且原文字是模糊的)。 | Ref: Replace the yellow taxiway sign at the lower right with a red-and-white striped traffic cone.<br>No-ref: Replace the selected sign with a red-and-white striped traffic cone.<br>或转换为 attribute/文字编辑 | 目视 |

#### `v2-sa_1571336`（#368，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | replace 实为属性修改 | noref+mask | Replace the deck railing around the brown houseboat on the right with a wooden deck railing. | U4 把棕色船屋的金属甲板栏杆（box [1552,866,1740,925]）替换为 'a wooden deck railing' —— 类别相同（栏杆），仅材质改变；这是属性（材质）编辑，而不是 replace。 | Ref: Replace the deck railing around the brown houseboat on the right with a row of potted shrubs.<br>No-ref: Replace the selected railing with a row of potted shrubs.<br>或改为属性：'Change the material of the deck railing ... to wood.' | 目视 |

#### `v2-sa_161512`（#374，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+mask | Replace the foreground floral shirt with a plain navy linen shirt. | 被 mask 的物体是黑色花卉短袖系扣衬衫；payload“a plain navy linen shirt”属于相同类别和结构（系扣衬衫），仅颜色、图案和材质不同，即以 replace 表达的 attribute 编辑。 | Ref: Replace the foreground floral shirt with a plain white crew-neck T-shirt.<br>No-ref: Replace the selected shirt with a plain white crew-neck T-shirt.<br>或转为 attribute：'Change the pattern of the foreground floral shirt to solid navy.' | 目视 |
| U2 | 轻微 | 属性值问题（无变化/含糊） | noref+box | Change the color of the white T-shirt behind the floral sleeve on the right to light gray. | 背景中模糊的 T 恤 [1129,0,1470,455] 在阴影中本来就呈浅灰白色;改为 'light gray' 几乎看不出变化,难以判断。 | Ref: Change the color of the white T-shirt behind the floral sleeve on the right to red.<br>No-ref: Change the color of the selected T-shirt to red. | 目视 |

#### `v2-sa_1615968`（#375，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | ref+box | Replace the second ice cream tub from the left in the lower row with a chocolate ice cream tub. | U3 mask 是一杯 Haagen-Dazs Mango & Cream 冰淇淋（下排左起第 2 个，box [625,922,1127,1364]）；用 'a chocolate ice cream tub' 替换后，桶的形状/盖子完全相同，只改变了印刷的标签设计，即属于图案/标签变化，而非类别/结构变化。 | Ref: Replace the second ice cream tub from the left in the lower row with a waffle cone of ice cream.<br>No-ref: Replace the selected tub with a waffle cone of ice cream.<br>或改为属性编辑：更改标签文字/口味；如果该桶必须保留作为支撑，则使用同等大小的纸盒 | 目视 |

#### `v2-sa_1647901`（#378，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+mask | Replace the foreground checked shirt facing away with a plain white cotton shirt. | 被 mask 的衣物是长袖格子衬衫；替换为“a plain white cotton shirt”保持相同类别和结构（衬衫到衬衫），仅改变图案/颜色，即 attribute 编辑。 | Ref: Replace the foreground checked shirt facing away with a dark hooded sweatshirt.<br>No-ref: Replace the selected shirt with a dark hooded sweatshirt.<br>或转为 attribute：'Change the pattern of the foreground checked shirt facing away to plain white.' | 目视 |

#### `v2-sa_167566`（#383，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | ref+mask | Replace the black car on the left with a white compact hatchback. | 左边的汽车（box 0-583 x 126-982）本来就是深色紧凑型两厢车。用 "a white compact hatchback" 替换，实际上只是换色。 | Ref: Replace the black car on the left with a white compact van.<br>No-ref: Replace the selected car with a white compact van. | 目视 |

#### `v2-sa_1752343`（#388，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | ref+box | Replace the black estate car immediately right of the minivan with a blue estate car. | U3 把黑色旅行车替换为 'a blue estate car' —— 类别/结构相同，仅改变颜色；应归入属性编辑。 | Ref: Replace the black estate car immediately right of the minivan with a white pickup truck.<br>No-ref: Replace the selected car with a white pickup truck.<br>或改为属性：Change the color of the black estate car immediately right of the minivan to blue. | 目视 |

#### `v2-sa_17741`（#392，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+point | Replace the kneeling vendor’s blue shirt with a white linen shirt. | 被 mask 的衣物是长袖浅蓝格子系扣衬衫；替换为“a white linen shirt”保持相同类别/结构（长袖衬衫），仅改变颜色和材质，即 attribute 编辑。 | Ref: Replace the kneeling vendor's blue checked shirt with a white sleeveless vest.<br>No-ref: Replace the selected shirt with a white sleeveless vest.<br>或转为 attribute：将颜色改为白色。 | 目视 |

#### `v2-sa_178076`（#393，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+mask | Replace the rounded metal helmet on the right platform with a leather helmet. | U1 是平台上圆形铆接的金属头盔;'replace with a leather helmet' 保持了类别和形状,只改变材质(且在这张黑白照片中材质变化几乎看不出)。 | Ref: Replace the rounded metal helmet on the right platform with a conical helmet with a nose guard.<br>No-ref: Replace the selected helmet with a conical helmet with a nose guard.<br>or convert to attribute: change the material of the helmet to leather | 目视 |
| U4 | 轻微 | 指代歧义 | noref+point | Change the finish of the round wooden shield left of the back door to dark-stained wood. | 后门左侧有两个圆形木盾：被 mask 的那个紧靠门框斜靠着（源图 x~667-775），另一个在更靠左的箱子上（源图 x~500-640）。'left of the back door' 对两者都适用；存储的点在 noref 下起区分作用。 | Ref: Change the finish of the round wooden shield leaning immediately left of the back door to dark-stained wood. | 目视 |

#### `v2-sa_190256`（#400，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 多单元同一物理对象/相互冲突 | noref+mask | Add a small reflective patch on the black shoulder bag beside the light purple T-shirt. | U3 的黑色单肩包(box x393-641,y1094-1451)斜挎在下方那名男子身上,其浅紫色 T 恤即 U2(box x353-689,y1058-1298);背带压在 T 恤上,两个 box 大幅重叠,因此 U2 和 U3 在同一个人身上,编辑会相互影响(背带/衬衫边界)。 | 删除 U3 或将其替换为未被穿戴的物体(例如放在 box 中的包 / 上方桌子上的红色手提包) | 目视 |

#### `v2-sa_1915366`（#403，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 方位/序数/实例指代错误 | noref+box | Add a yellow reflective band on the foreground utility pole in the center. | REF 称 'the foreground utility pole in the center'，但被 mask 的电线杆位于 x=0.29W（2250 宽中的 box 626-701），明显偏左；更左侧（~0.15W）还有一根杆，中心偏右（~0.72W）也有一根。'Foreground' 部分起到识别作用（它是最近且最高的杆），但 'in the center' 是错误的。 | Ref: Add a yellow reflective band on the tall foreground wooden utility pole left of center, in front of the building under construction. | 目视 |

#### `v2-sa_1923359`（#404，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| case | 严重 | 多单元同一物理对象/相互冲突 |  |  | 蓝色布质单肩包（U2，box [506,909,601,1085]）挂在穿棕色皮夹克的卷发女士的肩带上，她就是穿花裙子（U1）的同一个人。同一个人身上有两个 unit。 | 将 U2 替换为另一个人身上的目标，例如左侧穿灰夹克男子的牛仔裤，或旋转木马附近孩子的条纹连帽衫。 | 目视 |
| U1 | 严重 | replace 实为属性修改 | noref+point | Replace the floral skirt in the foreground with a plain navy skirt. | 被 mask 的裙子(box [567,1037,694,1191])是带奶油色碎花印花的深海军蓝裙;替换为 'a plain navy skirt' 只是去掉了图案 —— 类别相同,图案变化 = 属性。 | Ref: Replace the floral skirt in the foreground with a pair of navy wide-leg trousers.<br>No-ref: Replace the selected skirt with a pair of navy wide-leg trousers.<br>Or convert to attribute: change the pattern of the floral skirt to plain. | 目视 |

#### `v2-sa_1928951`（#405，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+none | Replace the child’s red sweatshirt with a plain blue sweatshirt. | 把孩子的红色图案卫衣替换为 'a plain blue sweatshirt' 仍属同一衣物类别；只改变了颜色和印花，属于属性编辑。 | Ref: Replace the child's red sweatshirt with a blue zip-up hooded jacket.<br>No-ref: Replace the selected sweatshirt with a blue zip-up hooded jacket.<br>或改为属性编辑：'Change the color of the child's red sweatshirt to plain blue.' | 目视 |
| U1 | 轻微 | mask 质量 | ref+none | Replace the child’s red sweatshirt with a plain blue sweatshirt. | 运动衫 mask 在踏板车女孩图案内部有空洞（围绕踏板车座椅/猫区域的内部红色轮廓），因此衣服的部分区域被排除在外。 | 填补运动衫 mask 的内部空洞。 | 目视 |

#### `v2-sa_1954663`（#408，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | 指代歧义 | ref+none | Change the color of the white shutter at the right edge to pale blue. | 右边缘的奶油色建筑有两扇白色百叶窗：被 mask 的下方一扇 [1354,889,1485,1426] 紧邻绿色 AED 箱，另一扇在上层大致相同的 x 位置（原图约 x~1400-1480, y~270-680）。'the white shutter at the right edge' 两者都符合。 | Ref: Change the color of the lower white shutter at the right edge, beside the green wall box, to pale blue.<br>ZH: 将右边缘下层、绿色壁挂箱旁的白色百叶窗板的颜色改为浅蓝色。 | 目视 |

#### `v2-sa_200777`（#410，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | replace 实为属性修改 | ref+mask | Replace the black motorboat at the front left with a white fiberglass motorboat. | U4 将黑色摩托艇（左前方，box [0,925,244,1106]）替换为“a white fiberglass motorboat”——类别相同（摩托艇），只有颜色/材质变化；这是 attribute 编辑，而非结构性 replace。 | Ref: Replace the black motorboat at the front left with a small wooden rowboat.<br>No-ref: Replace the selected motorboat with a small wooden rowboat.<br>或转为 attribute：Change the color of the black motorboat at the front left to white. | 目视 |

#### `v2-sa_2012261`（#411，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+box | Replace the white hatchback behind the foreground car with a blue compact hatchback. | U1 将白色两厢车(日产 Leaf,box [130,316,540,693])替换为 'a blue compact hatchback' —— 类别相同,实质上是改色。 | Ref: Replace the white hatchback behind the foreground car with a red pickup truck.<br>No-ref: Replace the selected car with a red pickup truck.<br>or convert to attribute color->blue | 目视 |

#### `v2-sa_2052480`（#414，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | ref+mask | Replace the large white plastic bag at the upper right with a crumpled brown paper bag. | 在堆满白色塑料袋的垃圾堆中，'the large white plastic bag at the upper right' 适用于多个袋子（例如视图 x~1400-1460,y~190 和 x~1500-1560,y~300 处旁边的白袋，以及正下方悬挂的白色塑料布）。被 mask 的那个（box x 1922-2102, y 400-550）是搁在泥土脊上的中等大小白袋，并不明显是最大的。 | Ref: Replace the rounded white plastic bag lying on the dirt ridge at the right, above the hanging grey plastic sheet, with a crumpled brown paper bag.<br>或该单元仅依赖 mask/point 输入 | 目视 |

#### `v2-sa_2137778`（#421，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | noref+box | Replace the seated adult’s yellow top with a white linen shirt. | REF 'the seated adult's yellow top' 适用于两个人。一个是坐在蓝色塑料椅上的被 mask 女子（box [577,1004,815,1320]）。另一个是紧挨着她的第二位成年女子（约 x=850-1000，y=1150-1450），穿黄色翻领上衣，低坐/蹲着，腿上抱着一个幼儿。 | Ref: Replace the yellow long-sleeved top of the woman sitting on the blue plastic chair with a white linen shirt.<br>ZH: 将坐在蓝色塑料椅上的女子的黄色长袖上衣替换为一件白色亚麻衬衫。 | 目视 |

#### `v2-sa_215762`（#422，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the second T-shirt from the right with a plain black T-shirt. | U2 是印有白色“KNEEL ... MOVING CAR!”字样的黑色 T 恤;将其替换为“a plain black T-shirt”只是去掉了印花(图案变化),类别和颜色相同。 | Ref: Replace the second T-shirt from the right with a black hooded sweatshirt.<br>No-ref: Replace the selected T-shirt with a black hooded sweatshirt.<br>或转换为 attribute:移除印花图案(图案 -> 纯色) | 目视 |
| U4 | 轻微 | mask 质量 | ref+mask | Add a small wreath on the wooden-framed glass door on the right. | U4 门 mask 在砖墙上方的顶部边缘有零散碎片，右边缘有参差不齐的碎块。 | 清理多余的 mask 碎片 | 目视 |

#### `v2-sa_2192461`（#427，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the nearest person’s dark puffer jacket on the left with a gray wool jacket. | U2 mask 是左前方行人的深海军蓝连帽夹克;将其替换为 'a gray wool jacket' 保持了相同的服装类别/轮廓,主要改变颜色和材质,即属性编辑。 | Ref: Replace the nearest person's dark jacket on the left with a long beige trench coat.<br>No-ref: Replace the selected jacket with a long beige trench coat. | 目视 |

#### `v2-sa_2204968`（#428，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+mask | Replace the cyclist’s gray T-shirt with a red T-shirt. | U1 将骑行者的灰色 T 恤替换为 'a red T-shirt'——同一衣物类别，只是颜色变化。 | Ref: Replace the cyclist's gray T-shirt with a red hooded sweatshirt.<br>No-ref: Replace the selected T-shirt with a red hooded sweatshirt.<br>或改为属性编辑：Change the color of the cyclist's gray T-shirt to red. | 目视 |

#### `v2-sa_2264516`（#431，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 多单元同一物理对象/相互冲突 | noref+point | Replace the photographer’s teal jacket with a beige windbreaker. | U1(黑色背包,box [298,521,620,893])和 U2(青绿色夹克,box [489,508,706,909])都是同一位摄影师穿戴的;背包直接压在夹克上,两个 box 重叠,因此这两个单元不是相互独立的实物。 | 删除 U2(或 U1);例如保留背包的 add,并将 U2 换成另一个独立物体,如左上角的粉青色悬挂灯笼。 | 目视 |

#### `v2-sa_2310142`（#433，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | noref+point | Replace the oncoming gray minivan with a white minivan. | U3 'Replace the oncoming gray minivan with a white minivan' 保持相同类别（minivan），只改变颜色；被 mask 的车辆是一辆深色丰田 Sienna 小型货车。 | Ref: Replace the oncoming gray minivan with a white box truck.<br>No-ref: Replace the selected minivan with a white box truck.<br>或改为属性：'Change the color of the oncoming gray minivan to white.' | 目视 |

#### `v2-sa_2316049`（#435，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 指代歧义 | noref+point | Remove the dark car across the street. | 广场上停着多辆深色汽车:最左边缘一辆(~x 0-90)、U3 那辆(box 340-435),以及 ~x 750-860 处的一辆深蓝色车。'the dark car across the street' 无法指出 U3。 | Ref: Remove the dark car parked behind the wooden bench across the street, left of center.<br>ZH: 移除马路对面左侧长椅后方的深色汽车。 | 目视 |
| U3 | 轻微 | mask 质量 | noref+point | Remove the dark car across the street. | U3 mask 轮廓包含了停在汽车前方的棕色木长椅，因此移除时也会抹掉长椅。 | 从汽车 mask 中排除长椅 | 目视 |

#### `v2-sa_2347182`（#436，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+box | Add a small flower box on the upper central balcony railing. | 被 mask 的栏杆是左侧立面上、紧邻中央塔楼左侧的上层阳台栏杆（box x770-990）。'upper central balcony railing' 同样（甚至更）可能指中央塔楼自身的小阳台（视图 x~780-870,y~270-340），它更高也更居中；两侧立面上还有其他上层阳台。 | Ref: Add a small flower box on the top-floor balcony railing of the left facade, just left of the central tower. | 目视 |

#### `v2-sa_2366400`（#438，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+point | Change the color of the white planter at the foot of the stairs to terracotta orange. | 有两个几乎相同的带棕榈状植物的白色花盆:被 mask 的那个(x~0.37W)位于楼梯左侧矮墙前,另一个位于木制厨师雕像右侧(约 0.46W)、主楼梯脚下。“The white planter at the foot of the stairs”至少同样符合第二个。 | Ref: Change the color of the white planter below the globe lamppost, left of the wooden figure, to terracotta orange. | 目视 |
| U2 | 轻微 | 指代歧义 | ref+box | Replace the globe lamppost beside the stairs with a black lantern lamppost. | 下层台阶左侧（~0.18W）旁还有另一根白色球形灯柱。位于小楼梯顶部、被 mask 的那根更突出，但 'beside the stairs' 并不能严格单独指出它。 | Ref: Replace the globe lamppost at the top of the small stairway, left of the restaurant entrance, with a black lantern lamppost. | 目视 |
| U4 | 严重 | 指代歧义 | ref+none | Add a small brass latch on the paired white shutters at the upper right. | “The paired white shutters at the upper right”也适用于顶层阳台门（~0.74W, 0.22H）上更高处的白色百叶窗，以及 ~0.64W 处的小百叶窗。被 mask 的那一对是餐厅屋顶上方、花箱之上的中层窗户。 | Ref: Add a small brass latch on the paired white shutters of the window just above the restaurant roof, beside the air-conditioning unit. | 目视 |

#### `v2-sa_2405164`（#443，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+mask | Replace the plaid shirt under the gray jacket with a plain white shirt. | 把红/藏青格子衬衫替换为 'a plain white shirt' 仍是同一衣物（有领衬衫）；只有图案/颜色变化，即属于属性编辑。 | Ref: Replace the plaid shirt under the gray jacket with a white crew-neck T-shirt.<br>No-ref: Replace the selected shirt with a white crew-neck T-shirt. | 目视 |

#### `v2-sa_2431352`（#446，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 指代歧义 | ref+point | Add a small bestseller sticker on the cover of the orange book on the front display. | 被 mask 的橙色书立在展示桌左端（box 629-709 x 796-893）。同一张桌子上、紧靠其右侧、女孩旁边还立着几本其他橙色书（原图约 x 1000-1200），因此 "the orange book on the front display" 不唯一。 | Ref: Add a small bestseller sticker on the cover of the orange book standing at the left end of the front display table. | 目视 |

#### `v2-sa_2516758`（#453，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+point | Replace the fruit-patterned apron on the left with a plain white apron. | 被 mask 的物体是左侧工人所穿、印有水果（苹果、葡萄）的白色围裙；'a plain white apron' 保持相同的服装类别和形状，只是去掉印花，即图案属性编辑。 | Ref: Replace the fruit-patterned apron of the worker on the left with a dark rubber fishing apron with a bib.<br>No-ref: Replace the selected apron with a dark rubber fishing apron with a bib.<br>或改为属性：'Change the pattern of the fruit-patterned apron on the left to plain white.' | 目视 |

#### `v2-sa_2527153`（#455，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+point | Replace the silver estate car on the left with a dark-blue estate car. | “Replace the silver estate car with a dark-blue estate car”保持相同类别/车身类型，仅改变颜色；这是 attribute（改色）编辑。 | Ref: Replace the silver car on the left with a dark-blue pickup truck.<br>No-ref: Replace the selected car with a dark-blue pickup truck.<br>或转为 attribute：Change the color of the silver car on the left to dark blue. | 目视 |

#### `v2-sa_2553111`（#457，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+point | Replace the light-purple overshirt on the left with a white cotton overshirt. | 被 mask 的衣物是敞开的浅紫/丁香色外搭衬衫;将其替换为 'a white cotton overshirt' 保持相同的服装类型,只改变颜色/材质,属于属性编辑。 | Ref: Replace the light-purple overshirt on the left with a white hooded cardigan.<br>No-ref: Replace the selected shirt with a white hooded cardigan.<br>Or convert to attribute: change color to white. | 目视 |
| U3 | 轻微 | 多单元同一物理对象/相互冲突 | ref+box | Add a small blue school-logo sticker on the pink package held by the boy. | 粉色包裹（U3）被同一个前景男孩抱在胸前，其米色短裤是 U1；是不同物体，但在同一个人身上。 | 可接受；可选择另一个人身上的目标。 | 目视 |

#### `v2-sa_258181`（#462，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the hanging black bookshop sign with a black sign reading BOOKS in gold. | U2 是一块黑色悬挂招牌，上有白色 'ARCADIAN BOOKS & PRINTS' 字样；将其替换为 'a black sign reading BOOKS in gold' 保持了类别、形状和颜色，仅改变了文字/字母颜色。 | Ref: Replace the hanging black bookshop sign with a round wooden sign shaped like an open book.<br>No-ref: Replace the selected sign with a round wooden sign shaped like an open book.<br>或改写为属性：将字母颜色改为金色 | 目视 |

#### `v2-sa_2608378`（#466，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the maroon shorts across the net with black sports shorts. | 被 mask 的物体是网对面球员穿的一条栗色运动短裤；替换为“black sports shorts”只是颜色变化（相同衣物类型和结构）。 | Ref: Replace the maroon shorts of the player across the net with long black track pants.<br>No-ref: Replace the selected shorts with long black track pants.<br>或转为 attribute：Change the color of the maroon shorts across the net to black. | 目视 |

#### `v2-sa_2618548`（#467，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+point | Replace the white shirt on the foreground stick-holder with a blue checked shirt. | U1 是短袖浅灰/白条纹纽扣衬衫;将其替换为 'a blue checked shirt' 保持相同服装类型,只改变颜色/图案。 | Ref: Replace the white shirt on the foreground stick-holder with a red knitted wool sweater.<br>No-ref: Replace the selected shirt with a red knitted wool sweater.<br>or convert to attribute: change the pattern of the shirt to blue checks | 目视 |

#### `v2-sa_2680554`（#471，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+point | Replace the white van in the foreground with a blue compact van. | 被 mask 的物体本来就是一辆紧凑型白色厢式货车（Peugeot Partner）；'Replace ... with a blue compact van' 类别和尺寸级别不变，实际上只是换色。 | Ref: Replace the white van in the foreground with a red three-wheeled delivery scooter.<br>No-ref: Replace the selected van with a red three-wheeled delivery scooter.<br>或改为属性编辑：将白色货车的颜色改为蓝色 | 目视 |
| U3 | 严重 | 指代歧义 | ref+box | Change the color of the blue hanging streetlamp to black. | 'the blue hanging streetlamp'：小巷左侧沿墙托架挂着许多相似的深蓝色钟形灯笼（例如 x~0.44W,y~0.31H；x~0.45W,y~0.35H）；被 mask 的是左墙上最近/最大的一盏（box [542,918,608,1023]）。 | Ref: Change the color of the nearest hanging streetlamp on the left wall bracket to black. | 目视 |

#### `v2-sa_271071`（#474，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+mask | Replace the black T-shirt on the bubble seller with a plain white T-shirt. | U1 把卖泡泡者的黑色 T 恤替换为“a plain white T-shirt”——同一衣物类型,仅颜色变化。 | Ref: Replace the black T-shirt on the bubble seller with a white button-up blouse.<br>No-ref: Replace the selected T-shirt with a white button-up blouse.<br>或改为 attribute:“Change the color of the black T-shirt on the bubble seller to white.” | 目视 |
| U3 | 轻微 | 多单元同一物理对象/相互冲突 | ref+point | Add a small keychain on the black crossbody bag in the foreground. | U3 黑色斜挎包（box [1971,674,2169,881]）斜挎在卖泡泡者身上，而其 T 恤是 U1；两个 mask 在同一个人身上相邻，尽管包是独立的物体。 | 作为独立物体可以接受；可选择不是 U1 那个人所佩戴的包/物体 | 目视 |

#### `v2-sa_2729470`（#475，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | noref+mask | Change the color of the yellow-and-green taxi to blue. | REF“the yellow-and-green taxi”不唯一：道路更远处还有另一辆黄绿色出租车（视图 x~845,y~405），左侧车道上也有几辆黄色出租车。被 mask 的是道路右侧黄色公交车旁边的那一辆。 | Ref: Change the color of the yellow-and-green taxi right beside the yellow bus on the right to blue. | 目视 |

#### `v2-sa_2732165`（#476，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代类别与 mask 不符 | noref+box | Replace the nearest central runner’s black leggings with navy running tights. | 黑夹克跑步者的 U1 衣物是宽松的黑色运动长裤(脚踝处有小标志),不是紧身裤;替换为 'running tights' 仍然定义明确。 | Ref: Replace the nearest central runner's black track pants with navy running tights.<br>No-ref: Replace the selected track pants with navy running tights.<br>scope -> track pants | 目视 |
| U3 | 严重 | 多单元同一物理对象/相互冲突 | noref+point | Remove the waist pack on the orange-shirted runner. | U2（黑色短裤，box 1128-1245,860-935）和 U3（腰包，box 1152-1202,783-826）都属于同一个穿橙色上衣的跑者；腰包系在他背后腰带上，正好在短裤上方。 | 删除 U3（或 U2），或改绑到另一名跑者，例如小路更远处穿黄色上衣的跑者的黄色上衣 | 目视 |

#### `v2-sa_2733235`（#477，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | ref+mask | Replace the gray sweater with a plain cream sweater. | 被 mask 的衣物是一件带粉/白色针织图案的灰色高领毛衣；将其替换为 'a plain cream sweater' 保持了相同的类别和结构，仅改变了颜色/图案。 | Ref: Replace the gray patterned sweater with a light-blue denim jacket.<br>No-ref: Replace the selected sweater with a light-blue denim jacket.<br>或转为属性：'Change the color of the gray patterned sweater to cream.' | 目视 |

#### `v2-sa_2741974`（#479，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 编辑不合理/不可执行 | noref+box | Replace the curved welcome sign behind the yellow car with a black sign reading Welcome in white. | 被 mask 的标牌（box x 993-1110, y 240-277）本身已经是带白色文字 'Croeso i Bentywyn / Welcome to Pendine' 的深色/黑色弧顶标牌。将其替换为 'a black sign reading Welcome in white' 几乎无变化；变化内容（文字缩短、形状）未明确指定，难以判断成功与否。 | Ref: Replace the curved welcome sign behind the yellow car with a rectangular green wooden sign reading 'PARKING' in white.<br>No-ref: Replace the selected sign with a rectangular green wooden sign reading 'PARKING' in white. | 目视 |

#### `v2-sa_2748410`（#480，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+point | Replace the round purple ornamental cabbage in the foreground center with a white-and-green ornamental cabbage. | U1 将紫色观赏甘蓝（box [941,1142,1127,1267]）替换为“a white-and-green ornamental cabbage”——相同植物类别，仅颜色变化；这是改色。 | Ref: Replace the round purple ornamental cabbage in the foreground center with a small red poinsettia plant.<br>No-ref: Replace the selected plant with a small red poinsettia plant.<br>或转为 attribute：将卷心菜的颜色改为白绿相间。 | 目视 |

#### `v2-sa_2750402`（#481，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+none | Replace the upper window just left of the evergreen tree with a white wooden casement window. | U1(box [101,688,152,743],x~0.06W)被描述为 'just left of the evergreen tree' 的上层窗户,但同一建筑的另一扇上层窗户(原图约 x~230px)位于 U1 与树之间,紧邻树;因此 'just left' 更符合那扇另一窗户。 | Ref: Replace the second upper-floor window from the left on the left white building with a white wooden casement window.<br>or re-target to the window directly next to the tree | 目视 |
| U1 | 严重 | replace 实为属性修改 | ref+none | Replace the upper window just left of the evergreen tree with a white wooden casement window. | 现有窗户本来就是深棕色木质双扇平开窗；替换为 'white wooden casement window' 实际上只是窗框换色。 | Ref: Replace the second upper-floor window from the left on the left white building with an arched stained-glass window.<br>或改为属性编辑：将窗框颜色改为白色 | 目视 |

#### `v2-sa_2755535`（#482，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+box | Replace the round headlight at the lower left of the yellow car with a clear round LED headlight. | U1 mask 是黄色汽车画面左侧的圆形封闭式大灯，它本来就是清晰的圆形大灯；将其替换为 'a clear round LED headlight' 在类别、形状和外观上几乎一致，因此该编辑几乎看不出来/无法评分。 | Ref: Replace the round headlight at the lower left of the yellow car with a rectangular amber fog lamp.<br>No-ref: Replace the selected headlight with a rectangular amber fog lamp. | 目视 |

#### `v2-sa_2827573`（#488，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 指代歧义 | noref+box | Remove the small white wall notice above the motorcycles. | 摩托车上方叠放着两张小白色墙面告示（被 mask 的位于 ~0.49W,0.42H，稍小的一张紧挨其下方 ~0.49W,0.47H）；“the small white wall notice above the motorcycles”对两者都适用。 | Ref: Remove the upper of the two small white wall notices above the motorcycles. | 目视 |

#### `v2-sa_2851659`（#491，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+box | Replace the white umbrella behind the gray coat with a cream canvas umbrella. | 被 mask 的物体是灰大衣持旗者身后一把打开的白伞;'a cream canvas umbrella' 保持相同的类别/结构,只改变颜色(白->奶油色)和材质(帆布)。 | Ref: Replace the white umbrella behind the gray coat with a wide straw sun hat held up on a stick.<br>better: convert to attribute 'Change the color of the white umbrella behind the gray coat to dark green.' or replace with a different structure such as 'a transparent bubble umbrella' | 目视 |

#### `v2-sa_2858888`（#492，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the pale shirt beneath the backpack with a light-blue cotton shirt. | 该男子穿的是浅色/白色短袖衬衫；替换为 "a light-blue cotton shirt" 本质上是同一衣物类型的换色。 | Ref: Replace the pale shirt beneath the backpack with a gray hooded sweatshirt.<br>No-ref: Replace the selected shirt with a gray hooded sweatshirt.<br>或改为属性编辑 color -> light blue | 目视 |
| U3 | 严重 | 多单元同一物理对象/相互冲突 | noref+box | Add a small white rectangular patch on the black backpack. | U2（浅色衬衫，box [1256,815,1632,1292]）和 U3（黑色背包，box [1305,832,1611,1302]）属于同一个站立的男子；背包背在衬衫外面，两个 box 几乎重合。 | 去掉 U2 或 U3；例如把其中一个换成右侧的折叠椅或右侧的泛光灯。 | 目视 |

#### `v2-sa_287526`（#494，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+mask | Tint the rectangular skylight on the foreground roof at the left pale green. | “the rectangular skylight on the foreground roof at the left”——除被 mask 的天窗(约 0.27W,0.80H)外,左侧前景屋顶上、其正下方(约 0.28W,0.97H)还有另一个矩形玻璃天窗,附近也有较小的屋顶窗;该表述不能唯一指向被 mask 的那个。 | Ref: Tint the long rectangular skylight on the sunlit orange-tiled roof at the lower left pale green. | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the cream awning on the terrace at the far left with a charcoal canvas awning. | 将奶油色露台遮阳篷替换为 'a charcoal canvas awning' 保持相同的物体类别；只有颜色/材质改变。 | Ref: Replace the cream awning on the terrace at the far left with a wooden pergola.<br>No-ref: Replace the selected awning with a wooden pergola.<br>或改为属性：Change the color of the cream awning ... to charcoal. | 目视 |

#### `v2-sa_2891743`（#495，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | ref+box | Replace the turquoise T-shirt in the background on the left with a plain white T-shirt. | U3 将青绿色 T 恤（box [749,411,833,554]）替换为“a plain white T-shirt”。衣物类别不变，仅颜色变化，因此这是被标成 replace 的 attribute（改色）编辑。 | Ref: Replace the turquoise T-shirt in the background on the left with a white button-up shirt.<br>No-ref: Replace the selected T-shirt with a white button-up shirt.<br>或者转为 attribute：'Change the color of the turquoise T-shirt in the background on the left to white.' | 目视 |

#### `v2-sa_2901296`（#496，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | mask 质量 | ref+none | Replace the plaid shoulder bag on the nearest visitor with a plain black messenger bag. | U1 的包本身是深灰色单肩包;格子部分是夹在其上的折叠格子伞/布,mask 包含了它。'plaid shoulder bag' 大致准确。 | Ref: Replace the dark shoulder bag with a plaid umbrella attached, carried by the nearest visitor, with a plain black messenger bag. | 目视 |
| U4 | 严重 | 多单元同一物理对象/相互冲突 | ref+point | Remove the black-and-red bag behind the nearest visitor. | 源图裁剪显示，带红色镶边的黑色包（U4，顶边）背在最近的游客（条纹衬衫、藏青色短裤）背上，U1 的单肩包挂在同一游客的身侧；两个单元由同一个人携带。此外 'behind the nearest visitor' 描述有误：它在他的背上。 | Ref: Remove the black backpack with red trim worn by the nearest visitor.<br>删除 U4 或 U1，使各单元位于不同的人身上 | 目视 |

#### `v2-sa_2901819`（#497，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+point | Replace the dark T-shirt on the visitor farther down the aisle with a navy polo shirt. | U1 mask 是中央柱子旁那个人的藏青色T恤（box [1115,582,1201,683]，cx=0.43）。还有其他几个人也站在 “farther down the aisle”：灰衬衫者（U2）、x=0.40 左右的一位白衬衫者，以及 x=0.48 附近的深色衣着购物者。因此 'the visitor farther down the aisle' 无法唯一指向此人。 | Ref: Replace the dark T-shirt on the visitor standing just left of the central pillar down the aisle with a navy polo shirt. | 目视 |

#### `v2-sa_2917269`（#498，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | noref+box | Change the color of the white cylindrical tank above the orange wall to light gray. | 橙色墙壁上方有两个白色圆柱形水箱:被 mask 的那个(box [797,2084,846,2163],紧邻宽窗左侧)和更靠左、太阳能板旁的另一个白色水箱(源图约 x 650-700)。“the white cylindrical tank above the orange wall”两者皆符合。 | Ref: Change the color of the white cylindrical tank just left of the wide window above the orange wall to light gray.<br>相应更新 ZH(宽窗左侧的白色圆柱水罐)。 | 目视 |

#### `v2-sa_2922373`（#499，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | noref+mask | Replace the rightmost folded parasol through the central opening with a folded cream canvas parasol. | 目标是透过中央开口看到的折叠式黑白条纹遮阳伞；载荷 'a folded cream canvas parasol' 保持相同类别和形状，只改变颜色/材质 —— 这是属性编辑，而不是 replace。 | Ref: Replace the rightmost folded parasol through the central opening with a tall potted palm.<br>No-ref: Replace the selected parasol with a tall potted palm.<br>或改为属性：Change the color of ... to cream. | 目视 |

#### `v2-sa_2938886`（#500，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+none | Replace the gray mailbox beside the nearest left-hand door with a dark-green metal mailbox. | U1 是深灰色壁挂金属邮箱；“replace with a dark-green metal mailbox”保持类别、形状和材质，仅改变颜色。 | Ref: Replace the gray mailbox beside the nearest left-hand door with a small wooden birdhouse.<br>No-ref: Replace the selected mailbox with a small wooden birdhouse.<br>或转为 attribute：将邮箱颜色改为深绿色 | 目视 |

#### `v2-sa_2950591`（#501，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 属性值问题（无变化/含糊） | ref+point | Change the color of the orange robe to deep saffron. | 被 mask 的僧袍本来就是明亮的藏红花橙色;改为 'deep saffron' 几乎无变化,难以判断(目标值与原色几乎相同)。 | Ref: Change the color of the orange robe to dark maroon.<br>No-ref: Change the color of the selected robe to dark maroon.<br>ZH: 深藏红花色 -> 深褐红色 | 目视 |

#### `v2-sa_2964423`（#505，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | noref+point | Replace the leftmost runner’s red shirt with a plain white running shirt. | 被 mask 的物体是最左侧跑者的红橙色图案短袖跑步衫（W412）；'Replace ... with a plain white running shirt' 衣物类型相同，只改变颜色/图案。 | Ref: Replace the leftmost runner's red shirt with a white sleeveless running vest.<br>No-ref: Replace the selected shirt with a white sleeveless running vest.<br>或改为属性编辑：将最左侧跑者红色上衣的颜色改为纯白色 | 目视 |

#### `v2-sa_2993378`（#511，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 方位/序数/实例指代错误 | ref+mask | Remove the small white notice below the larger board left of the door. | 该 mask 是门口左侧砖墙上的单张白色告示（x~0.26W），上方没有更大的告示板。唯一的 'larger board with a small notice' 组合在门右侧（x~0.69W），那里的小告示在较大告示板的上方。因此 'the small white notice below the larger board left of the door' 描述的是一个不存在的对象，并会把评审者引向右侧告示（physical_parent_zh 也写成了 右告示）。 | Ref: Remove the small white notice on the brick wall left of the doorway.<br>将 physical_parent_zh 改为 左告示 | 目视 |

#### `v2-sa_3042396`（#514，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+point | Replace the black shorts on the nearest runner on the left with navy running shorts. | U1 将最近的左侧跑者的黑色跑步短裤（box [313,945,534,1087]）替换为 "navy running shorts" ——同一类衣物，仅颜色改变（黑 -> 藏青，差别细微）。 | Ref: Replace the black shorts on the nearest runner on the left with knee-length black running tights.<br>No-ref: Replace the selected shorts with knee-length black running tights.<br>或转为属性：Change the color of the black shorts ... to bright yellow. | 目视 |

#### `v2-sa_305717`（#515，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+mask | Replace the blue-and-orange plaid shirt on the reclining man on the right with a plain navy shirt. | U1 把蓝橙格纹衬衫(box [1249,830,1489,1029])替换为“a plain navy shirt”——同一衣物类别,仅颜色/图案变化。 | Ref: Replace the blue-and-orange plaid shirt on the reclining man on the right with a gray hooded sweatshirt.<br>No-ref: Replace the selected shirt with a gray hooded sweatshirt.<br>或转换为 attribute:将格纹衬衫的图案/颜色改为纯藏青色。 | 目视 |

#### `v2-sa_3084517`（#518，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+box | Replace the suit jacket on the performer on the left with a burgundy velvet blazer. | 被 mask 的物体是深色单排扣西装外套；payload“a burgundy velvet blazer”是相同的衣物类型/结构，因此该编辑只是颜色 + 材质的变化，应属于 attribute。 | Ref: Replace the suit jacket on the performer on the left with a gray zip-up hoodie.<br>No-ref: Replace the selected jacket with a gray zip-up hoodie.<br>或改为 attribute：'Change the material of the suit jacket on the performer on the left to burgundy velvet.' | 目视 |

#### `v2-sa_3125315`（#521，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+point | Replace the pink butterfly phone case with a plain lavender silicone phone case. | 被 mask 的物体是淡粉色蝴蝶印花手机壳;将其替换为“a plain lavender silicone phone case”仍是同一物体/结构,仅改变颜色、图案和材质。 | Ref: Replace the pink butterfly phone case with a brown leather flip-wallet phone case.<br>No-ref: Replace the selected case with a brown leather flip-wallet phone case.<br>或转换为 attribute(图案 -> 纯薰衣草色)。 | 目视 |
| U2 | 轻微 | mask 质量 | noref+point | Change the color of the blue leopard-print phone case to pale pink. | 存储的 box [152,1709,394,2220] 远远延伸到豹纹箱包 mask（约在 y~1950 结束）下方，进入下一排箱子；box 底部附近出现细小的零散 mask 斑点。Box 定位器比物体更宽松。 | 根据主 mask 连通块重新紧凑地计算 box，并去掉零散斑点。 | 目视 |

#### `v2-sa_3126499`（#522，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 方位/序数/实例指代错误 | ref+mask | Change the color of the black T-shirt just right of the stone column to burgundy. | U2 mask（box [668,1847,737,1967]）是戴帽男子的黑色 T 恤，他正走在石柱底座（柱底大致跨 x=685-800）正前方，与其左半部分重叠；他并不是“just right of”石柱。另一名穿深色 T 恤的男子站在石柱正左侧，因此空间线索具有误导性。 | Ref: Change the color of the black T-shirt of the capped man walking in front of the stone column to burgundy.<br>更新 ZH: 将石柱前方戴帽行走男子的黑色T恤的颜色改为酒红色。 | 目视 |

#### `v2-sa_3164185`（#524，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | mask 质量 | ref+mask | Change the color of the front wheel rim on the nearest white sports car to silver. | Scope 是 'wheel rim'(证据备注说只含轮辋,保留轮胎和卡钳),但 U2 mask 轮廓(box x 468-929, y 993-1410)沿轮胎外缘,覆盖了整个车轮:轮胎、黑色轮辋和橙色卡钳。 | shrink mask to the black rim spokes/barrel only, excluding tire and caliper (or change scope to 'wheel') | 目视 |

#### `v2-sa_3165942`（#525，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+point | Replace the minibus at the lower right with a white electric minibus. | 被 mask 的小巴（box [1961,1233,2236,1365]）本来就是白/银色丰田风格货车；替换为 'a white electric minibus' 不会产生可见的类别/结构变化（电驱动看不出来）。 | Ref: Replace the minibus at the lower right with a red double-decker bus.<br>No-ref: Replace the selected minibus with a red double-decker bus.<br>选择外观明显不同的车辆 payload | 目视 |
| U2 | 严重 | 指代歧义 | ref+box | Change the color of the silver sedan in the foreground parking spaces to blue. | 'the silver sedan in the foreground parking spaces' 适用于多辆车：底部中央的停车区有多辆银/白色轿车（例如白色皮卡右边的那辆及其上方的其他车辆）；U2（box [862,1365,975,1447]）只是其中之一。 | Ref: Change the color of the silver sedan parked left of the white pickup at the bottom center to blue. | 目视 |

#### `v2-sa_3171541`（#526，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代歧义 | ref+mask | Replace the coat over the checked shirt in the foreground with a beige trench coat. | “in the foreground”表述不够准确:最右侧穿藏青大衣、围格纹围巾的女子更靠近镜头。凭借格子衬衫和白色包,目标仍可识别。 | Ref: Replace the black coat over the checked shirt of the woman holding a white shopping bag with a beige trench coat. | 目视 |
| U2 | 严重 | mask 质量 | noref+box | Change the color of the dark coat beside the checked-shirt visitor to burgundy. | U2 外套 mask 轮廓（box x 1526-1676）包住了挂在外套上、位于右髋的藏青色斜挎肩包（以及握手杖的手）；包没有被抠除，因此改色时也会把包一起改色。 | 重新裁切外套 mask，排除藏青色斜挎包及其背带和手。 | 目视 |

#### `v2-sa_3183045`（#528，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 指代歧义 | noref+point | Remove the stack of green stools on the right. | U3 mask 是路边 x~0.91 处的黄绿色凳子堆;右侧还有其他绿色凳子堆(一个在摊位附近 ~0.81W,0.75H,一个在最右边缘 ~0.99W,0.80H),所以 "the stack of green stools on the right" 并不唯一。 | Ref: Remove the stack of green stools standing in front of the right food stall, between the two rightmost traffic cones. | 目视 |

#### `v2-sa_3193863`（#530，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+point | Replace the blue blouse with a white collar in the foreground with a cream blouse. | 把蓝色罩衫替换为 'a cream blouse' 保持类别（罩衫）不变，只改变颜色。 | Ref: Replace the blue blouse with a white collar in the foreground with a denim jacket.<br>No-ref: Replace the selected blouse with a denim jacket.<br>或改为属性编辑：Change the color of the blue blouse ... to cream. | 目视 |

#### `v2-sa_3278974`（#534，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+point | Replace the blue shoebox with a plain kraft-cardboard shoebox. | U1 是一个蓝色 Adidas 鞋盒；将其替换为 'a plain kraft-cardboard shoebox' 保持了类别（鞋盒），仅改变了颜色/材质/印刷。 | Ref: Replace the blue shoebox with a woven wicker basket.<br>No-ref: Replace the selected box with a woven wicker basket.<br>或改写为属性：将蓝色鞋盒的颜色改为素色牛皮纸棕色 | 目视 |

#### `v2-sa_3283229`（#535，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 多单元同一物理对象/相互冲突 | noref+box | Remove the brown crossbody bag on the nearest woman on the left. | U1 是左侧最近那位女子的白色头巾(box [824,1105,876,1177])。U3 是同一女子斜挎的棕色包(box [808,1166,874,1305]);REF 对两者都说“on the nearest woman on the left”。 | 删除 U3,或将其改为其他物体(例如沿小路更远处穿棕色衣服行走的女子,或右侧的铜像) | 目视 |

#### `v2-sa_3317825`（#539，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+mask | Replace the cabbage nearest the vendor’s knee with a red cabbage. | U1 把一棵淡绿色卷心菜替换为 'a red cabbage' —— 蔬菜类别/形状相同，实质是颜色改变。 | Ref: Replace the cabbage nearest the vendor's knee with a pumpkin.<br>No-ref: Replace the selected cabbage with a pumpkin.<br>或改为属性：Change the color of the cabbage nearest the vendor's knee to purple. | 目视 |

#### `v2-sa_3354609`（#541，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the hanging metal weighing pan with a deeper stainless-steel weighing pan. | 被 mask 的物体本来就是浅口不锈钢秤盘;'Replace ... with a deeper stainless-steel weighing pan' 保持类别和材质,只改变深度,因此编辑几乎看不出,也不是类别/结构替换。 | Ref: Replace the hanging metal weighing pan with a woven wicker basket hanging from the scale chains.<br>No-ref: Replace the selected pan with a woven wicker basket. | 目视 |

#### `v2-sa_3358386`（#542，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+point | Replace the wooden bench at the front left with a new light-wood bench. | 被 mask 的物体是一张旧木长椅；payload 'a new light-wood bench' 类别和结构相同，只是木色/新旧不同——属于属性变化，而非 replace。 | Ref: Replace the wooden bench at the front left with a blue plastic chair.<br>No-ref: Replace the selected bench with a blue plastic chair. | 目视 |
| U2 | 轻微 | 方位/序数/实例指代错误 | ref+box | Tint the smaller window on the back wall pale green. | 被 mask 的窗户（box x1616-1778）是右侧墙上较窄的窗户（紧挨右边较大的窗户），不在后墙上——图像中央的后墙没有窗户。 | Ref: Tint the narrower window on the right wall pale green. | 目视 |

#### `v2-sa_3376573`（#544，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代歧义 | ref+box | Replace the NAPAPIJRI sign above the shop with a black sign reading CAFE in white. | 右侧下一个店面上方可见第二个较小的 NAPAPIJRI 招牌(源图约 x 1450);“the NAPAPIJRI sign above the shop”没有指明是哪一个,不过被 mask 的是更近、更大的那个。 | Ref: Replace the nearest NAPAPIJRI sign above the shop, next to the hanging arrow sign, with a black sign reading CAFE in white. | 目视 |
| U2 | 严重 | mask 质量 | noref+mask | Change the material of the metal frame of the nearest double wall sconce on the left to brass. | 范围是 'sconce frame'（REF：把金属框架的材质改为黄铜），但 mask（box [217,874,355,1063]）覆盖了整个双头壁灯，包括两个占 mask 大部分面积的大型磨砂玻璃灯罩。对该 mask 应用材质变更会把玻璃灯罩也变成黄铜。 | 将 mask 限制为仅深色金属臂/背板，或将范围改为整个壁灯，并把编辑改为 'Change the material of the metal arms of ... to brass'，配以仅含框架的 mask。 | 目视 |

#### `v2-sa_3390115`（#546，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+box | Replace the cyclist’s blue helmet with a white cycling helmet. | 被 mask 的物体已经是带通风孔的骑行头盔（深石板蓝）。替换为“a white cycling helmet”保持相同类别和结构，仅改变颜色。 | Ref: Replace the cyclist's blue helmet with a red full-face downhill helmet.<br>No-ref: Replace the selected helmet with a red full-face downhill helmet.<br>或转为 attribute：'Change the color of the cyclist's blue helmet to white.' | 目视 |

#### `v2-sa_3470503`（#552，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+none | Replace the Service sign on the building with a black sign reading SERVICE in white. | 被 mask 的物体是一块带泰文和 'Service' 的白色矩形建筑标牌。payload 'a black sign reading SERVICE in white' 类别和形状不变；该编辑是换色加文字改写，而不是类别/结构变化。 | Ref: Replace the Service sign on the building with a round wall clock.<br>No-ref: Replace the selected sign with a round wall clock.<br>或改为属性编辑：'Change the color of the Service sign on the building to black.' | 目视 |
| U3 | 轻微 | mask 质量 | noref+box | Add a yellow reflective strip on the visible truck door. | 门 mask [743,570,1046,1103] 的下边缘参差不齐、碎裂，溢入门下方深色驾驶室踏板/挡泥板区域（box 底部约 10%）。 | 将 mask 裁剪到门板轮廓，排除下方的踏板。 | 目视 |

#### `v2-sa_3514872`（#556，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+box | Replace the blue PERONI sign with a blue sign reading BAR in white. | 被 mask 的物体是蓝色长方形发光的 PERONI 标牌；替换为 'a blue sign reading BAR in white' 保持相同的类别、形状和颜色，只改变印刷文字，因此属于文本/内容编辑，而非类别/结构替换。 | Ref: Replace the blue PERONI sign with a round green neon clock.<br>No-ref: Replace the selected sign with a round green neon clock.<br>或改写为 replace 之外的文本编辑 | 目视 |

#### `v2-sa_3543848`（#560，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+mask | Replace the dark jacket on the standing man on the left with a beige casual jacket. | 被 mask 的衣物是男子的深海军蓝拉链夹克；替换为“a beige casual jacket”保持相同类别/形状，仅改变颜色。 | Ref: Replace the dark jacket on the standing man on the left with a gray hooded sweatshirt.<br>No-ref: Replace the selected jacket with a gray hooded sweatshirt.<br>或转为 attribute：'Change the color of the dark jacket on the standing man on the left to beige.' | 目视 |
| U4 | 轻微 | 指代歧义 | noref+point | Add a small cream seat cushion on the empty blue chair on the right. | 'the empty blue chair on the right' —— 美食广场右侧有好几把空的蓝色椅子(如圆桌后面)。被 mask 的是粉夹克女子前方最近的那把空蓝椅。 | Ref: Add a small cream seat cushion on the nearest empty blue chair on the right, in front of the woman in the pink jacket. | 目视 |

#### `v2-sa_3550286`（#561，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+box | Replace the large central orange parasol with a cream canvas parasol. | 把橙色遮阳伞替换为 'a cream canvas parasol' 保持类别不变，只改变颜色/材质。 | Ref: Replace the large central orange parasol with a tall patio heater.<br>No-ref: Replace the selected parasol with a tall patio heater.<br>或改为属性编辑：Change the color of the large central orange parasol to cream. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+mask | Add a strand of warm-white lights along its edge on the front awning marked CAFE DAGUERRE. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a strand of warm-white lights along the edge of the front awning marked CAFE DAGUERRE.<br>No-ref: Add a strand of warm-white lights along the edge of the selected awning. | 文本 |

#### `v2-sa_3562449`（#563，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+box | Replace the white Audi nearest the foreground with a red compact sedan. | U1 将白色奥迪轿车（box [1847,1254,2053,1389]）替换为 'a red compact sedan' ——同一类别；实质上是改色。 | Ref: Replace the white Audi nearest the foreground with a red pickup truck.<br>No-ref: Replace the selected car with a red pickup truck. | 目视 |
| U3 | 轻微 | 措辞/文法/描述细节 | ref+none | Remove the blue advertising board beside the river. | 蓝色广告牌(box [1558,938,1647,1003])立在隔着停放车辆的道路中央隔离带/人行道上,并不直接紧邻河流;由于蓝色广告牌唯一,目标仍可识别。 | Ref: Remove the blue advertising board on the pole beside the road. | 目视 |
| U4 | 严重 | 指代类别与 mask 不符 | ref+mask | Add a narrow planter of red flowers on the railing around the pointed-roof riverside turret. | U4 mask（box [1032,1086,1397,1187]）是河湾处方形石墩/石台顶部的装饰铁栏杆；那里看不到尖顶塔楼。REF 'railing around the pointed-roof riverside turret' 描述了一个不存在的结构，可能误导评判者。 | Ref: Add a narrow planter of red flowers on the iron railing atop the square stone bastion on the riverbank.<br>ZH: 在河岸方形石台上的铁栏杆加上一个种有红花的窄花槽。 | 目视 |

#### `v2-sa_3570130`（#564，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | ref+point | Replace the blue sedan parked near the right edge with a white compact sedan. | 被 mask 的轿车（box [1319,1174,1497,1308]）是银色/浅灰色汽车；它看起来发蓝只是因为整张黄昏图像有强烈的蓝色偏色（U1 银色 SUV 看起来也一样）。称其为“the blue sedan”描述有误，并且让 REF 在最右边缘那辆白车旁边变得不可靠。 | Ref: Replace the silver sedan parked near the right edge with a white compact sedan.<br>ZH: 银色轿车. | 目视 |

#### `v2-sa_3616046`（#567，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+none | Replace the tall text poster beside the display bicycle with a white poster reading WELCOME in red. | U1 本来就是带红/黑字的高白色海报('WE'RE HOME TO THOSE WHO WERE BORN HERE...');将其替换为 'a white poster reading WELCOME in red' 保持类别、形状和颜色,只改变印刷文字。 | Ref: Replace the tall text poster beside the display bicycle with a tall green potted plant.<br>No-ref: Replace the selected poster with a tall green potted plant.<br>or convert to an attribute edit of the poster's text | 目视 |
| U3 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a thin warm-white light ring around its face on the projecting black-and-gold wall clock. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a thin warm-white light ring around the face of the projecting black-and-gold wall clock.<br>No-ref: Add a thin warm-white light ring around the face of the selected clock. | 文本 |

#### `v2-sa_3633381`（#569，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+none | Replace the patterned backpack on the front-row woman in red with a plain navy backpack. | U1 将带图案的背包替换为 'a plain navy backpack' ——同一物体类别，仅图案/颜色改变。 | Ref: Replace the patterned backpack on the front-row woman in red with a black leather shoulder bag.<br>No-ref: Replace the selected backpack with a black leather shoulder bag.<br>或转为属性：Change the color of the patterned backpack ... to plain navy. | 目视 |
| U2 | 严重 | 指代歧义 | ref+mask | Change the color of the yellow T-shirt on the front-row participant to white. | 前排许多游行者穿黄色 T 恤(例如合成图约 x~515,y~360 附近的另一件黄衬衫);“the front-row participant”没有给出区分最左侧被 mask 者(cx=0.12)的位置信息。 | Ref: Change the color of the yellow T-shirt on the front-row participant at the far left to white. | 目视 |
| U4 | 轻微 | 指代歧义 | ref+point | Add a small hanging basket of white flowers on the curved streetlamp on the left. | 左侧出现两盏弯曲路灯：最左边一盏长拱臂灯（杆约 x=70，灯臂在 y~105 处向右弧出），以及被 mask 的、位于 x~200 的杆，其弯曲部分在顶部边缘被截断。 | Ref: Add a small hanging basket of white flowers on the tall curved streetlamp pole rising to the top edge on the left. | 目视 |

#### `v2-sa_3647055`（#571，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+mask | Replace the silver car behind the foreground bicycles with a dark blue compact car. | 被 mask 的物体是一辆银色两厢车;将其替换为 'a dark blue compact car' 保持相同类别和大致相同的形状,因此编辑主要是改色。 | Ref: Replace the silver car behind the foreground bicycles with a white delivery van.<br>No-ref: Replace the selected car with a white delivery van. | 目视 |
| U3 | 严重 | 指代歧义 | ref+mask | Remove the back-facing rectangular sign just left of the drawbridge. | REF 写的是 'back-facing rectangular sign'，但被 mask 的物体（box [275,954,331,1009]）是一叠三块绿白相间的方向指示牌，其文字和箭头朝向镜头；它是正面朝向的，并且是一组标牌，而不是单个背向的牌子。 | Ref: Remove the stacked green direction signs on the pole just left of the drawbridge.<br>No-ref: Remove the selected sign.<br>ZH: 背向镜头的矩形标牌 -> 叠放的绿色方向指示牌 | 目视 |
| U4 | 严重 | mask 质量 | noref+box | Add a narrow planter of red geraniums on the railing along the canal bridge. | “railing” mask 是沿整座桥的一条宽带（box [259,1122,2303,1237]），除了细细的栏杆外，还包含了许多靠着栏杆停放的自行车和桥上的行人。 | 将 mask 细化为仅栏杆条，或限制在没有自行车的一段栏杆上。 | 目视 |

#### `v2-sa_368308`（#576，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+point | Replace the silver SUV on the left with a dark green SUV. | U1 mask 的是左侧银色 SUV(box 286-644);'Replace ... with a dark green SUV' 保持相同类别,只改变颜色。 | Ref: Replace the silver SUV on the left with a white pickup truck.<br>No-ref: Replace the selected SUV with a white pickup truck.<br>or convert to attribute: 'Change the color of the silver SUV on the left to dark green.' | 目视 |

#### `v2-sa_3712023`（#579，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+mask | Replace the white polo shirt on the marcher beside the banner with a pale blue polo shirt. | U1 将横幅旁行进者的白色马球衫/T恤（box [1384,538,1506,683]）替换为 'a pale blue polo shirt' ——同一件衣服，仅颜色改变。 | Ref: Replace the white polo shirt on the marcher beside the banner with a red zip-up hoodie.<br>No-ref: Replace the selected shirt with a red zip-up hoodie.<br>或转为属性：change the color of the white polo shirt to pale blue. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a small blue bandana around its neck on the large brown dog on the right. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small blue bandana around the neck of the large brown dog on the right.<br>No-ref: Add a small blue bandana around the neck of the selected dog. | 文本 |

#### `v2-sa_3712240`（#580，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+box | Replace the black van nearest the camera with a white electric van. | 被 mask 的物体是一辆黑色紧凑型货运厢式车(Chevy City Express)。将其替换为“a white electric van”仍属同一类别和形状。唯一可见的差异是颜色,因为“electric”在视觉上并不明显。 | Ref: Replace the black van nearest the camera with a yellow taxi sedan.<br>No-ref: Replace the selected van with a yellow taxi sedan. | 目视 |

#### `v2-sa_3717579`（#581，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | ref+point | Tint the long diagonal window above the truck pale blue. | 斜向管状结构有一条连续的缝隙窗，被接缝分成多块，从左下延伸到右上（合成图中约 x 0-500）；mask 只覆盖其中一块（box x 66-302，位于最左上方 0.08W），而不是 'above the truck'（卡车驾驶室在约 0.2-0.4W，更靠下）。'the long diagonal window above the truck' 暗示的是整条窗带或更靠近卡车的一块。 | Ref: Tint the lowest-left pane of the long diagonal window strip on the white tubular structure at the upper left pale blue.<br>或将 mask 扩展到整条斜窗带 | 目视 |

#### `v2-sa_3733639`（#583，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+mask | Replace the dark cafe parasol at the lower right with a cream canvas parasol. | 被 mask 的物体是大型深灰色方形咖啡馆遮阳伞；payload“a cream canvas parasol”是相同的物体类型和形状，仅颜色/材质不同。 | Ref: Replace the dark cafe parasol at the lower right with a striped retractable awning.<br>No-ref: Replace the selected parasol with a striped retractable awning.<br>或转为 attribute：'Change the color of the dark cafe parasol at the lower right to cream.' | 目视 |

#### `v2-sa_3746390`（#587，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+mask | Replace the brown SUV on the left with a white compact SUV. | U1 将棕色 SUV(box [206,1100,645,1293])替换为 'a white compact SUV' —— 类别相同;实质上是改色。 | Ref: Replace the brown SUV on the left with a white delivery van.<br>No-ref: Replace the selected SUV with a white delivery van. | 目视 |
| U4 | 轻微 | 指代歧义 | noref+point | Add a small silver star pin on the lapel on the black leather jacket on the foreground pedestrian. | 前景中有两名行人一起行走（穿黑色皮夹克的女子，其身后是一名男子）；mask 在女子的夹克上。'the foreground pedestrian' 略有歧义，不过只有她穿皮夹克。 | Ref: Add a small silver star pin on the lapel of the black leather jacket of the ponytailed woman crossing the street. | 目视 |

#### `v2-sa_3758475`（#589，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 属性值问题（无变化/含糊） | noref+box | Change the color of the large spoked handwheel on the displayed cannon to dark bronze. | 被 mask 的带辐条手轮本来就是锈蚀的深棕色金属；'dark bronze' 与之色调几乎相同，因此该编辑近乎无效，难以判断。 | Ref: Change the color of the large spoked handwheel on the displayed cannon to bright red.<br>No-ref: Change the color of the selected handwheel to bright red. | 目视 |

#### `v2-sa_3783196`（#590，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | mask 质量 | ref+box | Change the color of the rusty rim of the truck’s front wheel to silver. | REF 针对“the rusty rim of the truck's front wheel”,但 U2 mask(box 1456-1904 x 1019-1457)勾勒了整个车轮,包括黑色轮胎;轮辋只是内部生锈的圆盘。 | 将 mask 限制在生锈的金属轮辋/轮毂圆盘上,或将目标改为“the front wheel”并配以合适的编辑。 | 目视 |
| U4 | 轻微 | mask 质量 | ref+none | Add a small white inventory label on the red-soda pack directly below the top green pack on the right. | U4 box 从 x=458 开始，而红色包装位于约 x 575-697；左侧相邻的紫/橙色包装上出现一个很小的零散 mask 碎片（约 x 460）。 | 去除零散碎片，使 mask/box 仅覆盖顶部绿色包装下方的红色包装。 | 目视 |

#### `v2-sa_378499`（#591，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+mask | Replace the green jacket on the passenger visible through the middle window with a navy jacket. | 被 mask 的物体是透过车窗可见的乘客的绿色（橄榄色）夹克；替换为“a navy jacket”只是同一类别内的颜色变化。 | Ref: Replace the green jacket on the passenger visible through the middle window with a gray hooded sweatshirt.<br>No-ref: Replace the selected jacket with a gray hooded sweatshirt.<br>或转为 attribute：'Change the color of the green jacket on the passenger visible through the middle window to navy blue.' | 目视 |
| U3 | 轻微 | mask 质量 | ref+point | Change the color of the yellow lettering on the opposite platform’s electronic board to white. | Scope 是 'lettering',但 mask 勾勒的是整块电子显示牌(box x 1097-1230),而不只是黄色文字行。 | either re-cut the mask to the text or change scope to 'display board' with 'Change the color of the lettering on the selected display board to white.' | 目视 |

#### `v2-sa_3792110`（#592，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the small green box beside the tall calligraphy plaque with a small dark wooden box. | 把小绿盒子替换为 'a small dark wooden box' 保持类别（盒子）不变，只改变颜色/材质。 | Ref: Replace the small green box beside the tall calligraphy plaque with a small ceramic vase.<br>No-ref: Replace the selected box with a small ceramic vase. | 目视 |
| U3 | 轻微 | mask 质量 | ref+none | Change the color of the lettering on the BLACK SANDALWOOD sign to gold. | 类别是 'lettering'，但 mask 覆盖了整块深色招牌板（汉字 壹認、粉色 黒壇 徽章和 'BLACK SANDALWOOD' 文字）；要重新着色哪部分文字未明确说明。 | Ref: Change the color of all lettering on the BLACK SANDALWOOD sign to gold.<br>No-ref: Change the color of the lettering on the selected sign to gold.<br>将 scope 设为 'sign'，target_part 设为 'lettering' | 目视 |

#### `v2-sa_3824138`（#598，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the navy blazer on the woman passing by with a beige linen blazer. | U2 将海军蓝西装外套（box [1036,830,1398,1500]）替换为“a beige linen blazer”——相同衣物类别和结构，只有颜色/材质变化。 | Ref: Replace the navy blazer on the woman passing by with a hooded rain parka.<br>No-ref: Replace the selected blazer with a hooded rain parka.<br>或转为 attribute：将西装外套的颜色改为米色 | 目视 |

#### `v2-sa_3868330`（#602，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | mask 质量 | ref+mask | Add a small yellow safety plaque on the orange railing just left of the noticeboard. | U3 栏杆 mask 是一整块实心区域（box 1180-1325 x 1165-1300），填满了细橙/红色栏杆条后方的整个区域，包括塔身灰色金属墙的大部分；栏杆本身只是几根细杆。 | 将 mask 精修为仅包含栏杆管（排除灰色墙面背景） | 目视 |

#### `v2-sa_38691`（#603，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 方位/序数/实例指代错误 | ref+point | Add a narrow planter of red flowers on the nearest balcony railing on the right bank. | 被 mask 的阳台（box 1750-1951 x 1004-1156）是右岸仓库远端（上游端）朝向桥的小型凸出阳台。同一建筑右下边缘的更大阳台和走廊离镜头更近，因此 "the nearest balcony railing on the right bank" 是错误的。 | Ref: Add a narrow planter of red flowers on the small projecting balcony railing at the far end of the right-bank building, facing the bridge. | 目视 |

#### `v2-sa_3872458`（#604，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 多单元同一物理对象/相互冲突 | noref+mask | Replace the black crossbody bag on the vendor’s back with a blue canvas sling bag. | U2(黑色斜挎包)斜挎在同一位摊贩的背后,其橙色 T 恤是 U3;U2 box [788,1025,909,1224] 位于 U3 box [737,1006,965,1283] 之内,且 T 恤 mask 围绕包带被挖空。两个单元在同一个人身上。 | 删除 U2 或 U3(例如保留 T 恤 attribute 并删除包),或选择另一个独立物体,如右侧推车上的金属锅 | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the black crossbody bag on the vendor’s back with a blue canvas sling bag. | 'Replace the black crossbody bag ... with a blue canvas sling bag'：sling bag 与 crossbody bag 属于同一类别；编辑只改变颜色/材质。 | Ref: Replace the black crossbody bag on the vendor's back with a small woven straw basket on a strap.<br>No-ref: Replace the selected bag with a small woven straw basket on a strap. | 目视 |

#### `v2-sa_3885316`（#607，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the lantern above the entrance gate with a brass lantern with clear glass. | U2 mask = 弯曲支架上带透明玻璃面板的黑色金属马车灯。Payload "a brass lantern with clear glass" 保持相同的类别/结构和玻璃,因此编辑只是灯架的材质/颜色变化。 | Ref: Replace the lantern above the entrance gate with a white frosted globe lamp.<br>No-ref: Replace the selected lantern with a white frosted globe lamp.<br>or convert to attribute: Change the material of the lantern above the entrance gate to brass. | 目视 |
| U3 | 严重 | 方位/序数/实例指代错误 | noref+point | Tint the lower window just left of the left gate pillar pale blue. | U3 mask = 位于图像边缘的最左侧可见推拉窗（源图 x~25-108）。它与 SOMERSET HOUSE 门柱之间（源图 x~135-210）还有第二扇推拉窗，那才是真正的 "just left of the left gate pillar"。因此 REF 指向的是邻近窗户，而不是被 mask 的窗户。 | Ref: Tint the leftmost window at the left edge of the image, behind the iron railing, pale blue.<br>ZH: 将画面最左边缘铁栏后的窗户的色调改为浅蓝色。 | 目视 |

#### `v2-sa_3893247`（#608，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | 多单元同一物理对象/相互冲突 | ref+mask | Add a small blue flower brooch on the white headscarf on the child holding the adult’s hand. | U3（姓名牌，box [759,896,874,1003]）挂在牵着成人手、正在挥手的孩子的小袋上；U4（白色头巾，box [623,485,786,686]）正是同一个孩子的头巾（脸就在头巾右侧，身体在正下方，带有 U3 的胸牌）。一个孩子身上有两个单元。 | 去掉 U4（或 U3），或将 U4 改为画面右边缘孩子的白色头巾 hijab（原图约 x 1600-1950, y 400-900）。 | 目视 |

#### `v2-sa_3921311`（#611，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+point | Replace the low stone bench to the left of the bridge with a dark wooden garden bench. | 桥的左侧有两个相似的低矮石凳:被 mask 的那个(box [250,1032,393,1079],紧靠 KEEP CAMBODIA CLEAN 标牌杆右侧)和更靠右(源图约 x 480-580,靠近桥端)的第二个低矮石凳。“the low stone bench to the left of the bridge”两者皆符合。 | Ref: Replace the leftmost low stone bench, just right of the KEEP CAMBODIA CLEAN sign post, with a dark wooden garden bench.<br>相应更新 ZH。 | 目视 |

#### `v2-sa_4017210`（#619，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | ref+box | Replace the orange basket in the middle of the boat with a brown wicker basket. | 被 mask 的物体是橙色小塑料开槽篮子；payload“a brown wicker basket”是相同类别（篮子）且形状相似，即颜色 + 材质的变化。 | Ref: Replace the orange basket in the middle of the boat with a small wooden crate.<br>No-ref: Replace the selected basket with a small wooden crate.<br>或转为 attribute（material: woven wicker）。 | 目视 |

#### `v2-sa_4018051`（#620，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+none | Replace the striped square cushion on the nearest bench with a plain sage-green cushion. | 最近的长椅(左下)上并排放着两个相似的蓝/灰条纹方靠垫;U1 mask(box [161,1162,432,1479])是右边/立着的那个,但 REF 'the striped square cushion on the nearest bench' 两个都符合。 | Ref: Replace the right striped square cushion on the nearest bench with a plain sage-green cushion.<br>ZH: 将最近长椅上右侧的条纹方靠垫替换为一个纯鼠尾草绿色靠垫。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a small black menu board on its tilted top on the empty metal menu stand at the edge of the seating area. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small black menu board on the tilted top of the empty metal menu stand at the edge of the seating area.<br>No-ref: Add a small black menu board on the tilted top of the selected stand. | 文本 |

#### `v2-sa_4023756`（#621，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | mask 质量 | noref+point | Remove the skull graphic on the rightmost striped shirt. | REF 移除最右侧条纹衬衫上的 'the skull graphic'，但 U1 mask（box x1564-1670, y508-694）只覆盖骷髅头；正下方的交叉骨（同一骷髅交叉骨印花的一部分）被遗漏，因此只移除 mask 区域会留下孤立的交叉骨。 | Ref: Remove the skull-and-crossbones graphic on the rightmost striped shirt.<br>扩展 mask 以包含交叉骨 | 目视 |
| U3 | 严重 | 指代歧义 | noref+mask | Change the color of the wire basket directly above the pirate costume packs to dark bronze. | 左上角有两篮装木剑的铁丝篮，都在包装好的海盗服上方（一个在原图 x~230-450，被 mask 的在 x445-982）；'the wire basket directly above the pirate costume packs' 不能明确地指向右边/前面的那个。 | Ref: Change the color of the front wire basket resting on the wooden rail, nearest the striped shirts, to dark bronze. | 目视 |

#### `v2-sa_4034728`（#624，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+none | Replace the camouflage cap on the leftmost fully visible person in the front row with a plain khaki patrol cap. | 被 mask 的帽子是沙漠迷彩的多用途/巡逻帽。将其替换为“a plain khaki patrol cap”仍是同一种帽型,仅去掉迷彩图案,因此属于图案/颜色变化。 | Ref: Replace the camouflage cap on the leftmost fully visible person in the front row with a black beret.<br>No-ref: Replace the selected cap with a black beret. | 目视 |
| U2 | 轻微 | 指代歧义 | ref+mask | Remove the dark SUV visible behind the center of the formation. | mask 是编队后方约 0.62W 处的深藏青色 SUV 车顶/车厢。一辆黑色皮卡正好在其前面，后排还停着其他深色车辆，因此 "the dark SUV visible behind the center" 略显宽松。 | Ref: Remove the dark blue SUV visible above the soldiers' caps just right of the center, beside the canopy pillar. | 目视 |

#### `v2-sa_4034922`（#625，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+box | Replace the red-and-green bus near the center with a blue-and-white bus of similar size. | 被 mask 的物体是红绿相间的鸡笼巴士（chicken bus）；替换为“a blue-and-white bus of similar size”保持类别和大小，仅改变涂装颜色，即实质上是改色。 | Ref: Replace the red-and-green bus near the center with a white box truck of similar size.<br>No-ref: Replace the selected bus with a white box truck of similar size.<br>或转为 attribute：Change the color of the red-and-green bus near the center to blue and white. | 目视 |

#### `v2-sa_4057910`（#627，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+mask | Replace the red flag above the museum with a plain white flag. | 被 mask 的物体是博物馆山花上方旗杆上的一面小红旗;'a plain white flag' 是同一物体类别/形状,只改变颜色。 | Ref: Replace the red flag above the museum with a long red-and-gold pennant banner.<br>No-ref: Replace the selected flag with a long red-and-gold pennant banner.<br>or convert to attribute: 'Change the color of the red flag above the museum to white.' | 目视 |
| U2 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a small pigeon perched on its head on the seated stone statue at the far right. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small pigeon perched on the head of the seated stone statue at the far right.<br>No-ref: Add a small pigeon perched on the head of the selected statue. | 文本 |

#### `v2-sa_4063118`（#628，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+point | Replace the silver car on the left with a blue compact car. | 被 mask 的汽车（box x75-275, y1732-2162）是白/银色两厢车；替换为 'a blue compact car' 本质上是同类车的换色。另外图中这辆车看起来是白色而非银色。 | Ref: Replace the white car parked on the left with a blue delivery van.<br>No-ref: Replace the selected car with a blue delivery van.<br>或改为属性编辑：Change the color of the white car on the left to blue. | 目视 |

#### `v2-sa_4154844`（#632，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | ref+point | Replace the round ceiling light with a small frosted-glass ceiling light. | 'the round ceiling light' ——至少还能看到另外两个圆形吸顶灯（一个约在 0.79W,0.06H，另一个在右上角）；U2 是顶部中央、风琴上方的球形灯。 | Ref: Replace the round ceiling light above the organ with a brass lantern-style pendant light.<br>No-ref: Replace the selected light with a brass lantern-style pendant light. | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the round ceiling light with a small frosted-glass ceiling light. | 现有的灯本来就是白色磨砂球形灯;“a small frosted-glass ceiling light”在视觉上几乎完全相同,因此该替换不属于明确的类别/结构变化。 | Ref: Replace the round ceiling light above the organ with a brass lantern-style pendant light.<br>No-ref: Replace the selected light with a brass lantern-style pendant light. | 目视 |

#### `v2-sa_4179283`（#634，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+box | Replace the high yellow flag on the right with a plain white flag. | U1 mask 的是右侧杆子高处的黄色三角旗（box [1523,583,1547,692]）。将其替换为 'a plain white flag' 保持旗帜类别和形状，只改变颜色。 | Ref: Change the color of the high yellow flag on the right to plain white.<br>No-ref: Change the color of the selected flag to plain white.<br>将 op 改为 attribute，或保持 replace 但换成不同物体，例如 'Replace the high yellow flag on the right with a red paper lantern.' | 目视 |

#### `v2-sa_4183336`（#635，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+box | Replace the purple polo shirt in the foreground with a plain navy polo shirt. | 目标是紫色菱形图案的 polo 衫；payload“a plain navy polo shirt”保持相同衣物类型/结构，仅改变颜色和图案——属于 attribute，而非 replace。 | Ref: Replace the purple polo shirt in the foreground with a white tank top.<br>No-ref: Replace the selected shirt with a white tank top.<br>或转为 attribute：Change the color of the purple polo shirt in the foreground to navy. | 目视 |

#### `v2-sa_4203157`（#637，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | ref+mask | Replace the red SPECIALIZED canopy valance on the left with a plain dark blue canopy valance. | 被 mask 的物体是印有红色 SPECIALIZED 字样的遮阳篷边饰;将其替换为 'a plain dark blue canopy valance' 保持相同物体和形状,只改变颜色并去掉印字(属性/图案编辑)。 | Ref: Replace the red SPECIALIZED canopy valance on the left with a hanging row of triangular bunting flags.<br>No-ref: Replace the selected valance with a hanging row of triangular bunting flags.<br>Or convert to attribute: color -> dark blue. | 目视 |

#### `v2-sa_4212793`（#638，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+point | Replace the dark car in the left foreground with a dark blue sedan. | 被 mask 的汽车（box x 58-552, y 1134-1451）本来就是深灰色轿车；替换为 'a dark blue sedan' 只改变颜色（类别和车身类型相同）。 | Ref: Replace the dark car in the left foreground with a white delivery van.<br>No-ref: Replace the selected car with a white delivery van.<br>或改为属性编辑：'Change the color of the dark car in the left foreground to dark blue.' | 目视 |

#### `v2-sa_4228887`（#640，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 指代类别与 mask 不符 | noref+point | Remove the wheeled bag beside the traveler at the far left. | 最左侧有一个软质黑色包放在黑色拉杆箱上。U3 mask(box 6-99 x 964-1073)只覆盖上方的软包以及拉杆箱的伸缩拉杆,而 REF 称其为“the wheeled bag”;轮子属于下方没有被 mask 的拉杆箱。 | Ref: Remove the black bag stacked on top of the suitcase beside the traveler at the far left.<br>从 mask 中排除拉杆箱的拉杆,或将目标改为整个拉杆箱+包的叠放组合 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+box | Add a small white information sticker in its lower corner on the large display showing 10 min and 30 min. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small white information sticker in the lower corner of the large display showing 10 min and 30 min.<br>No-ref: Add a small white information sticker in the lower corner of the selected display. | 文本 |

#### `v2-sa_4256768`（#641，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+mask | Replace the navy backpack near the center with a small brown leather backpack. | 被 mask 的物体是穿白色 T 恤男子背的深藏青/黑色日用背包；'Replace ... with a small brown leather backpack' 保持背包类别，只改变颜色/材质/大小。 | Ref: Replace the navy backpack near the center with a brown leather messenger bag.<br>No-ref: Replace the selected backpack with a brown leather messenger bag. | 目视 |
| U1 | 轻微 | 指代歧义 | noref+mask | Replace the navy backpack near the center with a small brown leather backpack. | “navy backpack near the center”（box 中心 x=0.58,y=0.89）：人群中心附近 x~0.40 处另有一位游客背着深色背包；被 mask 的是中心偏右、穿白 T 恤和蓝牛仔裤的男子身上的那个。 | Ref: Replace the navy backpack on the man in the white T-shirt just right of center with a brown leather messenger bag. | 目视 |

#### `v2-sa_4267734`（#642，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+box | Replace the clear glass lampshade in the foreground with a frosted white glass lampshade. | U1 将 'the clear glass lampshade' 替换为 'a frosted white glass lampshade' —— 同一物体类别和形状,只改变材质表面/颜色。 | Ref: Replace the clear glass lampshade in the foreground with a woven rattan dome lampshade.<br>No-ref: Replace the selected lampshade with a woven rattan dome lampshade.<br>or convert to attribute: 'Change the material of the clear glass lampshade to frosted white glass.' | 目视 |
| U3 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a small closed notebook on its empty right end on the wooden dresser beneath the pots. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small closed notebook on the empty right end of the wooden dresser beneath the pots.<br>No-ref: Add a small closed notebook on the empty right end of the selected dresser. | 文本 |

#### `v2-sa_4293407`（#645，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代歧义 | ref+box | Remove the red backpack on the blue-shirted visitor near the center. | 其他游客也背着红色背包（例如约 0.64W 处，以及约 0.76W 处穿蓝裙的女子）。被 mask 的穿蓝T恤、戴深色帽子的男子是最靠近中心的一位，因此 REF 大体但并非完全唯一。 | Ref: Remove the red backpack on the man in a blue T-shirt and dark cap near the center. | 目视 |
| U2 | 严重 | 指代歧义 | noref+mask | Change the color of the white polo shirt on the visitor beside the left-hand steps to light green. | 穿白色 polo 的“The visitor beside the left-hand steps”不能单独指出被 mask 的男子(位于中央台阶顶部,x~0.36W):台阶上或附近还有数名游客也穿白衬衫(例如约 0.47W 处背黑色背包的男子、约 0.15W 处左侧栏杆旁的男子)。区分线索是他的黑色斜挎带。 | Ref: Change the color of the white polo shirt of the man with a black crossbody strap at the top of the steps to light green. | 目视 |
| U3 | 严重 | replace 实为属性修改 | ref+none | Replace the pale canopy at the upper right with a plain dark green canopy. | 被 mask 的物体是右上角印有 'MOVENPICK' 字样的浅色露台遮阳伞。将其替换为 'a plain dark green canopy' 保持相同物体类型，只改变颜色并去掉印字。称其为 'canopy' 也不够准确；它是一把市集遮阳伞。 | Ref: Replace the pale patio umbrella at the upper right with a square straw beach parasol.<br>No-ref: Replace the selected umbrella with a square straw beach parasol.<br>或改为属性：'Change the color of the pale patio umbrella at the upper right to dark green.' | 目视 |
| U4 | 严重 | 编辑不合理/不可执行 | ref+mask | Add a small cream seat cushion on the empty wooden armchair at the upper-right cafe table. | 被 mask 的木扶手椅（box 2053-2142 x 127-240）已经有红色座垫（在 U4 放大图中清晰可见），因此“Add a small cream seat cushion on the empty wooden armchair”与原图冲突：椅子并非空的，而预期结果（第二个坐垫，还是替换红色的那个）未定义。 | Ref: Add a small cream throw pillow leaning against the backrest of the empty wooden armchair with a red seat cushion at the upper-right cafe table.<br>No-ref: Add a small cream throw pillow leaning against the backrest of the selected armchair. | 目视 |

#### `v2-sa_4329183`（#647，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+mask | Replace the checked shirt on the shopper near the center with a plain pale blue short-sleeved shirt. | 被 mask 的衬衫(box [1344,835,1495,1019])本来就是短袖浅蓝/白格子衬衫;替换为 'a plain pale blue short-sleeved shirt' 只是去掉格子图案 —— 同一服装和结构,属于图案/属性变化,几乎无变化。 | Ref: Replace the checked shirt on the shopper near the center with a dark green zip-up windbreaker.<br>No-ref: Replace the selected shirt with a dark green zip-up windbreaker. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a small white price tag on its lower edge on the hanging red-floral blanket just right of the blue-edged blanket. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small white price tag on the lower edge of the hanging red-floral blanket just right of the blue-edged blanket.<br>No-ref: Add a small white price tag on the lower edge of the selected blanket. | 文本 |

#### `v2-sa_4393371`（#650，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the black jacket on the approaching cyclist with a dark blue cycling jacket. | 被 mask 的物体是迎面骑来的骑行者的黑色拉链夹克；将其替换为 'a dark blue cycling jacket' 保持了相同的衣物类别和轮廓，实质上是黑色到深蓝色的改色，这也是难以判断的细微变化。 | Ref: Replace the black jacket on the approaching cyclist with a bright yellow hooded rain poncho.<br>No-ref: Replace the selected jacket with a bright yellow hooded rain poncho. | 目视 |

#### `v2-sa_4402790`（#652，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+point | Replace the horizontal purple liberty sign above the entrance with a navy sign reading BOUTIQUE in white. | U1 mask 是入口上方扁平矩形的紫色“liberty woman”门楣招牌(box [1064,561,1465,666]);将其替换为“a navy sign reading BOUTIQUE in white”仍是同样扁平的矩形招牌,仅改变颜色和文字,即属于 attribute(颜色+文字)编辑,而非类别/结构替换。 | Ref: Change the text on the horizontal purple liberty sign above the entrance to "BOUTIQUE".<br>No-ref: Change the text on the selected sign to "BOUTIQUE".<br>或转换为 attribute 操作;或者替换为结构不同的物体(例如由单个字母组成的发光霓虹招牌) | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small red SALE tag on its top bar on the clothing rack right of the shop entrance. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small red SALE tag on the top bar of the clothing rack right of the shop entrance.<br>No-ref: Add a small red SALE tag on the top bar of the selected rack. | 文本 |

#### `v2-sa_4421546`（#655，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the dark knit cap on the seated vendor in the foreground with a gray wool beanie. | 被 mask 的物体是坐着的摊主头上的深藏青色针织无檐帽；'a gray wool beanie' 是相同的头饰类型/形状，只有颜色（以及名义上的材质）改变。 | Ref: Replace the dark knit cap on the seated vendor in the foreground with a white crocheted kufi cap.<br>No-ref: Replace the selected cap with a white crocheted kufi cap.<br>或使用明显不同的结构，例如 'a brown flat cap with a short brim'，或改为属性 'Change the color of the dark knit cap ... to gray.' | 目视 |
| U3 | 轻微 | 措辞/文法/描述细节 | ref+mask | Add a small white cloth patch on its front edge on the domed red umbrella on the left. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small white cloth patch on the front edge of the domed red umbrella on the left.<br>No-ref: Add a small white cloth patch on the front edge of the selected umbrella. | 文本 |

#### `v2-sa_445897`（#660，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the sunglasses on the person at the right with black-framed wraparound sunglasses. | 右边的女子本来就戴着深色环绕式太阳镜（深红色镜框）；替换为 'black-framed wraparound sunglasses' 本质上是同一类别内的镜框换色。 | Ref: Replace the sunglasses on the person at the right with a pair of clear round reading glasses.<br>No-ref: Replace the selected sunglasses with a pair of clear round reading glasses.<br>或改为属性编辑：将镜框颜色改为黑色 | 目视 |

#### `v2-sa_447473`（#662，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the SPECIAL OFFER sign priced at 3 euros with a cream sign reading SPECIAL OFFER €4. | U2 mask 的是白色 SPECIAL OFFER '3.-' 价格牌（box [1285,1222,1348,1322]）。Payload 是 'a cream sign reading SPECIAL OFFER €4'，是同类物体，仅价格文字和颜色改变。没有发生类别或结构变化。 | Ref: Replace the SPECIAL OFFER sign priced at 3 euros with a small chalkboard easel.<br>No-ref: Replace the selected sign with a small chalkboard easel.<br>或转为属性/文字修改：'Change the price on the SPECIAL OFFER sign from 3 to 4 euros.' | 目视 |

#### `v2-sa_4477450`（#663，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+point | Replace the floral dress on the woman in the right foreground with a plain pale blue summer dress. | 目标是一条紫白相间的长碎花连衣裙;payload “a plain pale blue summer dress”仍是同一衣物类型,仅改变颜色/图案——属于 attribute 编辑。(mask 似乎还截去了她左侧所提红色包的一部分。) | Ref: Replace the floral dress on the woman in the right foreground with a white blouse and denim shorts.<br>No-ref: Replace the selected dress with a white blouse and denim shorts.<br>或转换为 attribute(图案 -> 纯淡蓝色);从 mask 中裁掉红色包。 | 目视 |

#### `v2-sa_4505880`（#666，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | noref+mask | Change the color of the lower shutter on the right-hand building to sage green. | 右侧建筑有三扇深色百叶窗：一扇在顶部（约 x 1130-1250, y 0-310），被 mask 的一扇（box x 1043-1124, y 585-796），另一扇被裁切，位于最右边缘较低处（约 x 1390-1500, y 700-1020）。被 mask 的百叶窗并非最低的一扇，因此 'the lower shutter on the right-hand building' 与之矛盾，或至少无法唯一识别它。 | Ref: Change the color of the narrow slanted shutter in the middle of the right-hand building wall, above the A-board sign, to sage green. | 目视 |

#### `v2-sa_4536573`（#668，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+box | Replace the handle on the left door with a brass lever handle. | 左门现有的把手已经是带底板的金属杠杆把手；替换为“a brass lever handle”只是材质/颜色变化。 | Ref: Replace the handle on the left door with a round brass doorknob.<br>No-ref: Replace the selected handle with a round brass doorknob. | 目视 |
| U3 | 严重 | mask 质量 | noref+mask | Add a small white name badge on its chest on the seamstress’s pink vest. | U3 'pink vest' mask 还覆盖了红/黄印花上衣:轮廓包住了画面右侧的印花短袖(~x=1070-1250, y=500-760)以及马甲片之间大部分印花前襟。 | restrict mask to the pink vest panels only, excluding the printed blouse sleeve and front | 目视 |
| U3 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small white name badge on its chest on the seamstress’s pink vest. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small white name badge on the chest of the seamstress’s pink vest.<br>No-ref: Add a small white name badge on the chest of the selected vest. | 文本 |

#### `v2-sa_4550787`（#669，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the red vest on the man at the left with a plain dark gray waistcoat. | 'Replace the red vest ... with a plain dark gray waistcoat'：被 mask 的物体是栗红色尼赫鲁式马甲；payload 是同一衣物类型，只改变颜色。 | Ref: Change the color of the red vest on the man at the left to dark gray.<br>No-ref: Change the color of the selected vest to dark gray.<br>改为属性编辑，或替换为不同的衣物类型（例如深灰色绗缝羽绒背心仍然是背心；优先用属性编辑） | 目视 |
| U2 | 轻微 | mask 质量 | ref+mask | Replace the red vest on the man at the left with a plain dark gray waistcoat. | U2 背心 mask 在右边缘外凸（合成图中约 x 465-560，y~600-705），包含了左侧男子与中间男子紧握的双手，这些不属于背心；该区域也与 U1 的夹克袖子区域相邻/重叠。 | 将 U2 mask 裁剪为背心衣片，排除双手 | 目视 |
| U3 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a small white name badge on its chest on the brown vest on the man at the right. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small white name badge on the chest of the brown vest on the man at the right.<br>No-ref: Add a small white name badge on the chest of the selected vest. | 文本 |

#### `v2-sa_4551219`（#670，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | ref+box | Replace the open black umbrella in front of the stage with a dark green umbrella. | U3 把“the open black umbrella”替换为“a dark green umbrella”——同一物体,仅颜色变化。 | Ref: Replace the open black umbrella in front of the stage with a large beach parasol.<br>No-ref: Replace the selected umbrella with a large beach parasol.<br>或转换为 attribute:“Change the color of the open black umbrella in front of the stage to dark green.” | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small round yellow badge on its chest on the black jacket on the person holding the umbrella. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small round yellow badge on the chest of the black jacket on the person holding the umbrella.<br>No-ref: Add a small round yellow badge on the chest of the selected jacket. | 文本 |

#### `v2-sa_4555867`（#672，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+point | Replace the light blue jacket on the left passenger with a navy denim jacket. | 左侧乘客的夹克（box 934-1039）本身已经是带补丁的浅蓝色牛仔夹克。将其替换为 'a navy denim jacket' 保持衣物类型和材质，只改变颜色。 | Ref: Replace the light blue denim jacket on the left passenger with a red quilted puffer vest.<br>No-ref: Replace the selected jacket with a red quilted puffer vest.<br>或改为属性：'Change the color of the left passenger's light blue jacket to navy.' | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small white number 7 decal on its bow on the empty gondola in the lower-right corner. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small white number 7 decal on the bow of the empty gondola in the lower-right corner.<br>No-ref: Add a small white number 7 decal on the bow of the selected gondola. | 文本 |

#### `v2-sa_4583482`（#676，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the pink apron on the seated person in white with a plain navy apron. | U2 mask 是背景中坐着的白衣女子的粉/洋红色围裙（带绿色带子）（box [1539,310,1678,523]）；'Replace ... with a plain navy apron' 保持相同的衣物类别，仅改变颜色/图案。 | Ref: Change the color of the pink apron on the seated person in white to navy blue.<br>No-ref: Change the color of the selected apron to navy blue.<br>将操作转为属性（color=navy blue） | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+box | Add a small yellow OPEN sticker at its top on the tall information board at the right edge. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small yellow OPEN sticker at the top of the tall information board at the right edge.<br>No-ref: Add a small yellow OPEN sticker at the top of the selected board. | 文本 |

#### `v2-sa_463680`（#678，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+mask | Replace the fish seller’s dark vest with a blue quilted vest. | 被 mask 的衣物是鱼贩的黑色工作背心;“a blue quilted vest”是同一衣物类型和轮廓,仅改变颜色和绗缝图案。 | Ref: Replace the fish seller's dark vest with a yellow waterproof bib apron.<br>No-ref: Replace the selected vest with a yellow waterproof bib apron.<br>或转换为 attribute:“Change the color of the fish seller's dark vest to blue.” | 目视 |
| U3 | 轻微 | 指代歧义 | ref+point | Change the color of the yellow crate at the back of the counter to green. | 柜台后方有两个黄色箱子（被 mask 的是上面一个，约视图 y~600-645，第二个在其右下方正下方，y~635-680）；'the yellow crate at the back of the counter' 无法单独指出上面那个。 | Ref: Change the color of the topmost yellow crate at the back of the counter to green. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a small white price label reading 5/kg on its front on the frontmost fish crate on the counter. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small white price label reading 5/kg on the front of the frontmost fish crate on the counter.<br>No-ref: Add a small white price label reading 5/kg on the front of the selected crate. | 文本 |

#### `v2-sa_4667828`（#680，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the gategourmet sign on the catering truck with a white sign reading CATERING in blue. | U2 mask 是餐饮车顶上白色的 'gategourmet' 招牌箱;payload 'a white sign reading CATERING in blue' 保持相同的白色招牌形态,只改变文字,即文字/内容编辑而非类别/结构替换。mask 左端还包含前方停放喷气机机翼/尾翼的一小条(次要问题)。 | Ref: Replace the gategourmet sign on the catering truck with a rooftop amber beacon light bar.<br>No-ref: Replace the selected sign with a rooftop amber beacon light bar.<br>or reclassify as a text edit; trim wing sliver from mask | 目视 |

#### `v2-sa_4688841`（#685，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | noref+mask | Replace the HAKATA STATION lettering near the roof with blue lettering reading CENTRAL STATION. | 被 mask 的 HAKATA STATION 屋顶字样本来就是蓝色；替换为 'blue lettering reading CENTRAL STATION' 只改变文字内容，不改变类别/结构，因此不是真正的 replace。 | Ref: Replace the HAKATA STATION lettering near the roof with a large round analog clock.<br>No-ref: Replace the selected sign with a large round analog clock.<br>或改为 replace 之外的文字编辑 | 目视 |

#### `v2-sa_4697965`（#686，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+none | Replace the wooden schoolhouse sign with a weathered wooden sign reading SCHOOLHOUSE MUSEUM. | U1 mask = 风化的木质招牌，写着 THE OLDEST WOOD SCHOOL HOUSE IN THE USA ST AUGUSTINE FLORIDA。Payload "a weathered wooden sign reading SCHOOLHOUSE MUSEUM" 保持了相同的类别、材质和风格；仅文字改变，因此这不是类别/结构替换。 | Ref: Replace the wooden schoolhouse sign with a black metal lantern-style wall sconce.<br>No-ref: Replace the selected sign with a black metal lantern-style wall sconce.<br>或保留为文字编辑：Change the text of the wooden schoolhouse sign to SCHOOLHOUSE MUSEUM (if text attribute is allowed). | 目视 |
| U2 | 轻微 | mask 质量 | ref+mask | Change the color of the wooden frame of the upper window to white. | U2 的 scope 是窗框,但 mask 覆盖了整个窗户,包括所有玻璃窗格和窗棂(box [522,324,786,675]);仅对窗框改为白色的重新着色也会在玻璃上被评估。 | 将 mask 限制在木制窗框/饰边上,或将 scope 改为整个窗户:Change the color of the frame of the upper gable window to white. | 目视 |

#### `v2-sa_4740557`（#687，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+point | Replace the Hello Kitty T-shirt on the girl at the left with a plain pale pink T-shirt. | U1 mask 的是左侧女孩的灰色 Hello Kitty T 恤（box [221,818,418,1049]）。载荷 'a plain pale pink T-shirt' 保持 T 恤类别和结构，只去掉印花并改变颜色。 | Ref: Replace the Hello Kitty T-shirt on the girl at the left with a yellow hooded raincoat.<br>No-ref: Replace the selected T-shirt with a yellow hooded raincoat.<br>或改为属性：'Change the color of the Hello Kitty T-shirt on the girl at the left to plain pale pink.' | 目视 |

#### `v2-sa_4789458`（#690，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | mask 质量 | noref+box | Add a small rectangular yellow reflector on its nearest section on the metal guardrail in the foreground. | U3 护栏 mask（comps=4）包含护栏外侧沥青路面上的许多噪点碎片（box 左/上部，合成图中约 x=0-850,y=690-900），而不仅仅是金属栏杆和立柱。 | 将 mask 清理为仅护栏横梁和立柱；去掉路面碎片 | 目视 |
| U3 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a small rectangular yellow reflector on its nearest section on the metal guardrail in the foreground. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small rectangular yellow reflector on the nearest section of the metal guardrail in the foreground.<br>No-ref: Add a small rectangular yellow reflector on the nearest section of the selected guardrail. | 文本 |

#### `v2-sa_4811077`（#693，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+box | Replace the beige jacket on the hiker with outstretched arms with a red insulated hiking jacket. | 被 mask 的物体是张开双臂的徒步者的米色休闲夹克；'Replace ... with a red insulated hiking jacket' 保持夹克类别；主要可见变化是颜色。 | Ref: Replace the beige jacket on the hiker with outstretched arms with a red hooded rain poncho.<br>No-ref: Replace the selected jacket with a red hooded rain poncho.<br>或改为属性编辑：将米色夹克的颜色改为红色 | 目视 |

#### `v2-sa_4863786`（#698，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+mask | Replace the dark backpack at the right edge with a beige canvas backpack. | 被 mask 的物体是右边缘的一个深色（黑色）尼龙背包。'A beige canvas backpack' 类别和形状相同，仅颜色/材质改变。 | Ref: Replace the dark backpack at the right edge with a brown leather messenger bag.<br>No-ref: Replace the selected backpack with a brown leather messenger bag.<br>或转为属性：'Change the color of the dark backpack at the right edge to beige.' | 目视 |

#### `v2-sa_4885403`（#700，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+box | Replace the navy shirt on the foreground runner with a white athletic T-shirt. | 前景跑者本身已经穿着藏青色短袖运动 T 恤；将其替换为 'a white athletic T-shirt' 只改变颜色（相同衣物类型）。 | Ref: Replace the navy shirt on the foreground runner with a white sleeveless running vest.<br>No-ref: Replace the selected shirt with a white sleeveless running vest.<br>或改为属性：'Change the color of the navy shirt on the foreground runner to white.' | 目视 |
| U2 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a small blue pennant near its top on the tall pole immediately left of the soccer goal. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small blue pennant near the top of the tall pole immediately left of the soccer goal.<br>No-ref: Add a small blue pennant near the top of the selected pole. | 文本 |

#### `v2-sa_4888519`（#701，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+box | Replace the left striped folding chair with a plain green folding chair. | 被 mask 的物体是多色条纹低矮沙滩折叠椅；payload“a plain green folding chair”保持相同类别/结构，仅改变颜色/图案。 | Ref: Replace the left striped folding chair with a small wooden stool.<br>No-ref: Replace the selected chair with a small wooden stool.<br>或转为 attribute：'Change the color of the left striped folding chair to plain green.' | 目视 |

#### `v2-sa_4933977`（#706，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | mask 质量 | ref+none | Change the color of the navy blazer on the man walking away in the center to brown. | 海军蓝西装外套的 mask 似乎包含了挂在男子左髋的深色单肩包(裁剪图显示轮廓在包周围鼓出)。 | exclude the shoulder bag and strap from the blazer mask | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the floral blouse on the left of the two foreground women with a pale blue linen blouse. | 被 mask 的衣物是短袖碎花罩衫；替换为 'a pale blue linen blouse' 衣物类型/形状相同，只改变图案/颜色/材质。 | Ref: Replace the floral blouse on the left of the two foreground women with a gray zip-up track jacket.<br>No-ref: Replace the selected blouse with a gray zip-up track jacket.<br>或改为属性编辑：'Change the pattern of the floral blouse ... to plain pale blue.' | 目视 |
| U3 | 严重 | 指代歧义 | noref+box | Add a small white SALE card at its front edge on the red tablecloth behind the striped-shirted person at the right. | REF 将桌布锚定到 'the striped-shirted person at the right'，但站在被 mask 红色桌子前的女子（原图 x~1950,y~1000-1290）穿的是灰色混纺粗花呢外套，而非条纹衬衫；右侧还有几张其他红色桌布（y~1100-1200 的长前桌）。该描述是错误的，锚点也很弱。 | Ref: Add a small white SALE card on the front edge of the curved red tablecloth with framed photos, behind the dark-haired woman in the gray jacket at the right.<br>No-ref: Add a small white SALE card on the front edge of the selected tablecloth.<br>ZH: 在右侧穿灰色外套的深发女子身后、摆着相框的弧形红色台布前缘加上一张小白色SALE卡片。 | 目视 |
| U3 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a small white SALE card at its front edge on the red tablecloth behind the striped-shirted person at the right. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small white SALE card at the front edge of the red tablecloth behind the striped-shirted person at the right.<br>No-ref: Add a small white SALE card at the front edge of the selected tablecloth. | 文本 |

#### `v2-sa_495948`（#708，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+none | Replace the white shirt on the man walking at the left with a pale blue linen shirt. | 将白衬衫替换为“a pale blue linen shirt”仍属同一衣物类别;仅颜色/材质变化。 | Ref: Replace the white shirt on the man walking at the left with a dark green polo shirt with a contrasting collar.<br>或转换为 attribute:Change the color of the white shirt on the man walking at the left to pale blue. | 目视 |

#### `v2-sa_49886`（#711，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the green umbrella beneath the left balcony with a cream patio umbrella. | 被 mask 的物体是一把打开的绿色品牌露台遮阳伞。将其替换为 "a cream patio umbrella" 保持相同物体类型，只改变颜色。 | Ref: Replace the green umbrella beneath the left balcony with a white canvas gazebo tent.<br>No-ref: Replace the selected umbrella with a white canvas gazebo tent.<br>或改为属性：Change the color of the green umbrella beneath the left balcony to cream. | 目视 |

#### `v2-sa_4999349`（#712，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | mask 质量 | noref+mask | Remove the black backpack in the foreground. | U1 背包 mask 在左下方（原图约 x~1400, y~1420-1495）有一小条多余的细条，位于背包主体之外的背带/腿部区域。 | 修剪多余的 mask 碎片 | 目视 |
| U3 | 严重 | replace 实为属性修改 | ref+mask | Replace the large neon-yellow flag at the left with a plain orange flag. | U3 是带绿色印花徽章的荧光黄三角旗;'a plain orange flag' 保持类别和形状,只改变颜色并去掉印花。 | Ref: Replace the large neon-yellow flag at the left with a large paper butterfly on a stick.<br>No-ref: Replace the selected flag with a large paper butterfly on a stick.<br>or recast as attribute: change the color of the flag to orange | 目视 |

#### `v2-sa_5005220`（#714，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | 指代歧义 | noref+box | Add a small white TAXI sign on its roof on the black sedan to the left of the red hatchback. | U4 mask 是位于源图 x~389-580 的黑色轿车；红色两厢车紧左侧是一辆深色厢式车/MPV（x~580-740），更靠左（x~190-330）还有另一辆黑色轿车。'the black sedan to the left of the red hatchback' 对两辆黑色轿车都适用，而最近的左侧车辆是那辆厢式车。 | Ref: Add a small white TAXI sign on the roof of the black sedan just left of the dark van, two cars left of the red hatchback.<br>相应更新 ZH | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a small white TAXI sign on its roof on the black sedan to the left of the red hatchback. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small white TAXI sign on the roof of the black sedan to the left of the red hatchback.<br>No-ref: Add a small white TAXI sign on the roof of the selected sedan. | 文本 |

#### `v2-sa_5008540`（#715，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 属性值问题（无变化/含糊） | ref+box | Change the color of the stone balustrade behind the lawn left of the obelisk to white. | 被 mask 的石栏杆（box 0-753 x 1030-1133）本来就是浅灰/米白色石材；将其颜色改为 'white' 近乎无效，评估者无法可靠验证。 | Ref: Change the color of the stone balustrade behind the lawn left of the obelisk to terracotta red.<br>No-ref: Change the color of the selected balustrade to terracotta red. | 目视 |
| U2 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a small bronze information plaque on its front on the pedestal of the central obelisk. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small bronze information plaque on the front of the pedestal of the central obelisk.<br>No-ref: Add a small bronze information plaque on the front of the selected pedestal. | 文本 |

#### `v2-sa_5020470`（#716，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | mask 质量 | noref+mask | Change the color of the gray seat of the white scooter to dark brown. | U1 座椅 mask 从座椅向上延伸,包含了白色踏板车右侧的车把握把和刹车杆(mask 顶部约在 box 顶 y~611);车把不属于座椅。 | 将 mask 裁剪为座垫及其前裙,排除车把握把/刹车杆 | 目视 |
| U3 | 严重 | replace 实为属性修改 | ref+mask | Replace the small SALE PREMIUM ACCESSORY sign with a white sign reading TEST RIDES AVAILABLE. | 'Replace the small SALE PREMIUM ACCESSORY sign with a white sign reading TEST RIDES AVAILABLE'：物体类别相同（小标牌），只有颜色和印刷文字改变。 | Ref: Replace the small SALE PREMIUM ACCESSORY sign with a small chalkboard easel.<br>No-ref: Replace the selected sign with a small chalkboard easel.<br>或改为属性（更改标牌的文字/颜色） | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a small white QR-code sticker in its upper-right corner on the large yellow-and-green display board. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small white QR-code sticker in the upper-right corner of the large yellow-and-green display board.<br>No-ref: Add a small white QR-code sticker in the upper-right corner of the selected board. | 文本 |

#### `v2-sa_5061008`（#720，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+none | Replace the terracotta bowl behind the painting with a white ceramic bowl. | 被 mask 的物体是一个带倒嘴的陶土搅拌碗。'A white ceramic bowl' 类别和形状相同，仅颜色/材质改变。 | Ref: Replace the terracotta bowl behind the painting with a small glass beaker.<br>No-ref: Replace the selected bowl with a small glass beaker.<br>或转为属性：'Change the material of the terracotta bowl behind the painting to white glazed ceramic.' | 目视 |

#### `v2-sa_5216619`（#730，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | replace 实为属性修改 | noref+point | Replace the large white-lettered kebab sign on the right with a white-lettered sign reading KEBAB HOUSE. | 被 mask 的物体是右侧立面上白字的 'DNISTOR kebap' 招牌;将其替换为 'a white-lettered sign reading KEBAB HOUSE' 保持同一物体(白字招牌),只改变文字 —— 属于文字属性编辑,而非类别/结构替换。 | Ref: Change the text of the large white-lettered kebab sign on the right to "KEBAB HOUSE".<br>No-ref: Change the text of the selected sign to "KEBAB HOUSE".<br>change op to attribute (property=text); or replace with a structurally different object, e.g. 'a hanging round wooden shop sign' | 目视 |

#### `v2-sa_5227150`（#732，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the black printed T-shirt on the right foreground runner with a pale blue athletic T-shirt. | 把黑色印花 T 恤替换为 'a pale blue athletic T-shirt' 保持类别（T 恤）不变；本质上是换色/去除印花。 | Ref: Replace the black printed T-shirt on the right foreground runner with a pale blue zip-up running jacket.<br>No-ref: Replace the selected T-shirt with a pale blue zip-up running jacket. | 目视 |
| U4 | 轻微 | mask 质量 | ref+box | Add a small white exhibit-number 12 plaque on its visible hull on the armored vehicle beneath the runners. | 车辆 mask 在左下角（原图约 x315-560, y1390-1500）、坐着的士兵后方有斑点状碎片，与主车体分离；很可能是车辆的前甲板，但噪点较多。 | 清理斑点状碎片，或确认它们属于该车辆 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+box | Add a small white exhibit-number 12 plaque on its visible hull on the armored vehicle beneath the runners. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small white exhibit-number 12 plaque on the visible hull of the armored vehicle beneath the runners.<br>No-ref: Add a small white exhibit-number 12 plaque on the visible hull of the selected vehicle. | 文本 |

#### `v2-sa_5322779`（#739，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+box | Replace the white T-shirt on the standing man near the center with a navy polo shirt. | U1 男子站在 cx=0.33(左三分之一处,紧靠三个坐着的男子右侧),并不 'near the center';他的衬衫看起来是浅蓝灰色而非白色。其他站着的人(如图像中心 x~740 附近的小人影、x~1190 处的黑衣女子)使 'the standing man near the center' 不可靠。 | Ref: Replace the light-blue T-shirt on the standing man just right of the three seated men with a navy polo shirt.<br>fix ZH accordingly | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+mask | Add a small white number 8 plaque on its pole on the streetlamp at the far right of the square. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small white number 8 plaque on the pole of the streetlamp at the far right of the square.<br>No-ref: Add a small white number 8 plaque on the pole of the selected streetlamp. | 文本 |

#### `v2-sa_5365574`（#743，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | noref+point | Change the color of the horizontal blue pipe across the foreground to white. | 前景中有几根蓝色管道交叉：被 mask 的那根（box [5,948,2250,1378]）是从左上斜向右的大型 DIAGONAL 管道；一根真正水平的蓝色管道沿底边延伸（约 y 1350-1500），左下还有一根倾斜的管道。'the horizontal blue pipe across the foreground' 更符合底部那根管道。 | Ref: Change the color of the large diagonal blue pipe crossing in front of the ferry's bow to white.<br>ZH: 将斜穿渡轮船头前方的大蓝色管道的颜色改为白色。 | 目视 |

#### `v2-sa_5447626`（#751，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+point | Replace the striped polo shirt on the flower seller with a pale blue cotton shirt. | 卖家穿着淡蓝/灰色横条纹短袖 polo;payload “a pale blue cotton shirt”颜色几乎相同且版型未指定,因此仅去掉条纹(图案变化)就能满足要求。 | Ref: Replace the striped polo shirt on the flower seller with a pale blue long-sleeved button-down shirt.<br>No-ref: Replace the selected shirt with a pale blue long-sleeved button-down shirt. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+none | Add a small price tag reading 50 on its rim on the large woven sack of white flowers in the foreground. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small price tag reading 50 on the rim of the large woven sack of white flowers in the foreground.<br>No-ref: Add a small price tag reading 50 on the rim of the selected sack. | 文本 |

#### `v2-sa_5462658`（#752，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the patterned scarf on the woman with a burgundy wool scarf. | 女子的黑白图案围巾（box [1389,664,1485,986]）被替换为 "a burgundy wool scarf" —— 物体类型相同，只有颜色/图案/材质改变。 | Ref: Replace the patterned scarf on the woman with a long beaded necklace.<br>No-ref: Replace the selected scarf with a long beaded necklace.<br>或改为属性：Change the color of the patterned scarf on the woman to solid burgundy. | 目视 |

#### `v2-sa_5490754`（#756，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | noref+point | Replace the middle of the three upper-floor white HERMES awnings with a dark green canvas awning. | U3 mask 的是上层中间那块白色 HERMES 遮阳篷(box 1496-1657 x);将其替换为 'a dark green canvas awning' 保持类别和形状,只改变颜色/材质。 | Ref: Replace the middle of the three upper-floor white HERMES awnings with a small wrought-iron balcony.<br>No-ref: Replace the selected awning with a small wrought-iron balcony.<br>Alternatively convert to attribute: 'Change the color of the middle of the three upper-floor white HERMES awnings to dark green.' | 目视 |

#### `v2-sa_5508914`（#758，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the patterned canopy on the cart in the foreground with a plain blue canvas canopy. | 被 mask 的物体是拖拉机拖车上平整的红/黄图案织物顶篷；'a plain blue canvas canopy' 保持相同的平整顶篷结构，仅改变图案/颜色/材质。 | Ref: Replace the patterned canopy on the cart in the foreground with a corrugated metal roof sheet.<br>No-ref: Replace the selected canopy with a corrugated metal roof sheet.<br>或转为属性：'Change the color of the patterned canopy on the cart in the foreground to plain blue.' | 目视 |

#### `v2-sa_5536770`（#759，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+point | Replace the wheelchair beside the window with a lightweight silver wheelchair. | 目标是一辆黑色/深蓝色轮椅;payload “a lightweight silver wheelchair”类别和结构相同,主要区别是颜色/表面处理——实质上是 attribute 编辑。 | Ref: Replace the wheelchair beside the window with a luggage trolley.<br>No-ref: Replace the selected wheelchair with a luggage trolley.<br>或转换为 attribute:Change the color of the wheelchair beside the window to silver. | 目视 |

#### `v2-sa_5550721`（#760，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the green cushion in the shop window with a navy velvet cushion. | 将绿色靠垫替换为 'a navy velvet cushion' 保持类别；只有颜色/材质改变。 | Ref: Replace the green cushion in the shop window with a small ceramic vase.<br>No-ref: Replace the selected cushion with a small ceramic vase.<br>或改为属性（颜色改为藏青色） | 目视 |
| U3 | 严重 | 指代歧义 | ref+none | Change the color of the white cushion with large black dots in the shop window to pale pink. | “the white cushion with large black dots in the shop window”——长凳上有两个黑白圆点靠垫：被 mask 的是绿色靠垫左侧的（x331-397），另一个在绿色靠垫右侧（原图约 x445-480）。 | Ref: Change the color of the white cushion with large black dots just left of the green cushion in the shop window to pale pink.<br>ZH: 将橱窗里绿色靠垫左侧带大黑圆点的白色靠垫... | 目视 |
| U4 | 轻微 | 指代歧义 | ref+mask | Add a narrow planter of red flowers on the upper-right balcony railing on the pink facade. | 'upper-right balcony railing on the pink facade' —— 被 mask 的阳台是立面中部的顶层阳台(1500 宽中 x324-722);它在左上阳台的右边,但不在立面右侧(圆形塔楼没有阳台)。 | Ref: Add a narrow planter of red flowers on the top-floor center balcony railing on the pink facade. | 目视 |

#### `v2-sa_5552382`（#761，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | ref+point | Replace the hanging direction sign marked 1 with a black sign reading INFORMATION. | REF 'the hanging direction sign marked 1' 至少适用于两块标牌：位于右中的被 mask 的那块（box [1420,1010,1543,1073]），以及同一高度最左侧另一块黑色悬挂的 '1' 方向牌（源图约 x 290-380, y ~1050）。一楼的 '0' 标牌也类似。 | Ref: Replace the hanging direction sign marked 1 on the right, near the FOSSIL store, with a black sign reading INFORMATION.<br>No-ref: Replace the selected sign with a black sign reading INFORMATION. | 目视 |

#### `v2-sa_5648905`（#772，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 多单元同一物理对象/相互冲突 | noref+box | Remove the black handbag carried by the front woman. | U1（黑色手提包）和 U3（奶油色和蓝色礼服）都属于前方同一位女士，且包直接挂在礼服前面（U1 box 位于 U3 box 内）。移除包会迫使对 U3 要改色的礼服区域做修补，因此两个编辑相互耦合。 | Ref: Remove the black handbag carried by the front woman.<br>将 U3 改为针对另一位女士的衣物（例如后方穿红衣女士的红裙子），或删除 U1 | 目视 |

#### `v2-sa_5716467`（#778，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | replace 实为属性修改 | ref+box | Replace the open notebook at the left edge of the table with an open white spiral notebook. | 桌子左边缘被 mask 的物体本来就是一本打开的白色横线(螺旋式)笔记本;替换为 'an open white spiral notebook' 实质上是无变化/同一类别。 | Ref: Replace the open notebook at the left edge of the table with a closed hardcover book.<br>No-ref: Replace the selected notebook with a closed hardcover book. | 目视 |
| U2 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a small sunflower sticker on its lid on the silver laptop facing the camera. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small sunflower sticker on the lid of the silver laptop facing the camera.<br>No-ref: Add a small sunflower sticker on the lid of the selected laptop. | 文本 |

#### `v2-sa_5735756`（#779，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 多单元同一物理对象/相互冲突 | ref+none | Change the color of the checked headscarf on the woman in red to navy blue. | U1（奶油色手提包）和 U2（格子头巾）都属于同一位穿红衣的女子：包挂在她肩上，正好在头巾上方，且两个 REF 都以 'the woman in red' 为锚点。同一个人身上有两个单元违反独立性规则（包带还穿过头巾 mask 区域）。 | 删除 U2（或 U1），改选另一个人的物品，例如左侧穿蓝衣女子的绿色头巾。 | 目视 |
| U3 | 严重 | replace 实为属性修改 | ref+mask | Replace the straw hat on the woman near the center with a beige cotton sunhat. | 被 mask 的帽子是编织草制渔夫帽/遮阳帽；payload 'a beige cotton sunhat' 是同类帽子且颜色相近，仅材质不同。 | Ref: Replace the straw hat on the woman near the center with a red baseball cap.<br>No-ref: Replace the selected hat with a red baseball cap. | 目视 |

#### `v2-sa_5755405`（#781，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | noref+box | Replace the silver door handle behind the woman with a brass doorknob. | 被 mask 的物体(box [402,1002,453,1070])本来就是一个圆形银色门把手;将其替换为“a brass doorknob”只是材质/颜色变化。 | Ref: Replace the silver doorknob behind the woman with a black lever-style door handle.<br>No-ref: Replace the selected door handle with a black lever-style door handle.<br>或转换为 attribute:材质 -> 黄铜 | 目视 |

#### `v2-sa_5788594`（#785，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | mask 质量 | noref+box | Change the color of the mobile stair truck at the right to yellow. | U2 mask（box [1792,654,2055,776]）仅覆盖卡车下部驾驶室/底盘；一直延伸到飞机舱门的大型有顶楼梯结构（'mobile stair truck' 的大部分）在 mask 之外，因此 'change the color of the mobile stair truck to yellow' 与 mask 区域冲突。 | Ref: Change the color of the cab of the mobile stair truck at the right to yellow.<br>No-ref: Change the color of the selected truck cab to yellow.<br>或将 mask 扩展到包含楼梯结构。 | 目视 |

#### `v2-sa_5803931`（#788，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | 指代歧义 | ref+none | Replace the child's pink coat with a yellow raincoat. | 有两个穿粉色夹克的小孩：被 mask 的是在小路上行走、戴灰色针织帽的那个（box x867-944），另一个是站在自行车正前方的粉衣幼童（视图 x~765-790,y~680-780）。“the child's pink coat”（以及 U3 的“left of the child”）不能唯一指出目标。 | Ref: Replace the pink coat of the child in the gray knit hat walking on the path with a yellow raincoat.<br>U3 REF -> 'Remove the red backpack on the walker left of the child in the gray hat.' | 目视 |

#### `v2-sa_5827205`（#789，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 指代歧义 | ref+point | Replace the magenta beanie below the cardboard sign with a black ribbed beanie. | REF/ZH 称被 mask 的无檐帽(box [618,1089,716,1198])为 'magenta'/'洋红色',但它其实是深栗/酒红色。其正右侧、同样在 Maestro 纸板牌下方(约 x=990, y=1140)有一顶亮洋红/粉色针织帽。因此颜色词会把仅看 ref 的读者引向错误的帽子。 | Ref: Replace the dark maroon beanie below the Maestro cardboard sign with a black ribbed beanie.<br>ZH: 将Maestro纸板牌下方的深酒红色针织帽替换为一顶黑色罗纹针织帽。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a small purple flower sticker in its upper-right corner on the MY BODY MY CHOICE sign. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small purple flower sticker in the upper-right corner of the MY BODY MY CHOICE sign.<br>No-ref: Add a small purple flower sticker in the upper-right corner of the selected sign. | 文本 |

#### `v2-sa_5831338`（#791，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | ref+mask | Change the color of the white GRIND T-shirt on the spectator near the center to light blue. | U2 mask 是戴绿色帽子的观众的白色 DC GRIND T恤（box [983,1196,1189,1485]，cx=0.48）。紧靠其左侧（约 x=0.40）另一位观众穿着几乎相同的白色 DC GRIND T恤，因此 'the spectator near the center' 不能唯一确定目标。 | Ref: Change the color of the white GRIND T-shirt on the spectator in the green cap near the center to light blue. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a small gold star emblem in its upper-left corner on the dark banner behind the rightmost spectator. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small gold star emblem in the upper-left corner of the dark banner behind the rightmost spectator.<br>No-ref: Add a small gold star emblem in the upper-left corner of the selected banner. | 文本 |

#### `v2-sa_5856108`（#793，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the silver-gray backpack at the right edge of the standing group with a brown leather backpack. | U2 把银灰色背包替换为 'a brown leather backpack' —— 类别相同；只有颜色/材质改变。 | Ref: Replace the silver-gray backpack at the right edge of the standing group with a brown leather messenger bag.<br>No-ref: Replace the selected backpack with a brown leather messenger bag. | 目视 |

#### `v2-sa_5865465`（#794，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | replace 实为属性修改 | ref+mask | Replace the black headscarf on the woman in the long foreground canoe with a beige cotton headscarf. | 被 mask 的物体是女士的黑色头巾（hijab）；替换为“a beige cotton headscarf”保持相同衣物类型和形状，仅改变颜色/材质。 | Ref: Replace the black headscarf on the woman in the long foreground canoe with a woven conical straw hat.<br>No-ref: Replace the selected headscarf with a woven conical straw hat.<br>或转为 attribute：颜色 -> 米色。 | 目视 |

#### `v2-sa_5969016`（#803，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 方位/序数/实例指代错误 | ref+mask | Replace the dark coat on the tall person standing near the center with a beige wool coat. | REF：'the tall person standing near the center'，但被 mask 的穿深色外套男子（box [450,862,573,1052]，中心 0.26W）站在左三分之一处，位于旋转木马左部前方；靠近中心的人是 U1（俯身看婴儿车，0.45W）。左侧还站着数名其他穿深色外套的人，因此该描述具有误导性。 | Ref: Replace the dark coat on the man standing with his back to the camera at the left of the carousel, next to the crouching person, with a beige wool coat. | 目视 |
| U4 | 严重 | mask 质量 | ref+point | Add a small red TICKETS sign on its front base on the carousel. | 旋转木马 mask（box [119,109,1672,1123]）向下延伸到前景人群中。它圈住了站在平台前的部分观众（如约 x~540 处蹲着的人和左侧约 x~150-320 的人群）以及模糊的乘客，因此“carousel”区域包含了邻近的人。 | 将 mask 限制在旋转木马结构（顶篷、立柱、平台），并排除其前方的观众。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a small red TICKETS sign on its front base on the carousel. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small red TICKETS sign on the front base of the carousel.<br>No-ref: Add a small red TICKETS sign on the front base of the selected carousel. | 文本 |

#### `v2-sa_5987768`（#805，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | noref+box | Replace the dark brown headscarf immediately right of the purple headscarf with a blue floral headscarf. | 将深棕色头巾替换为 'a blue floral headscarf' 保持相同的服装;只是颜色/图案变化。 | Ref: Change the color of the dark brown headscarf immediately right of the purple headscarf to blue with a floral pattern.<br>No-ref: Change the color of the selected headscarf to blue with a floral pattern.<br>Change op to attribute (color/pattern). | 目视 |

#### `v2-sa_6003979`（#806，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | noref+mask | Replace the blue AKW TRAVEL sign with a white sign reading ISLAND TOURS. | 被 mask 的物体是一块蓝色悬挂的 AKW TRAVEL 店铺招牌；替换为 'a white sign reading ISLAND TOURS' 物体类别和形状不变，只改变颜色和文字（属于属性/文字编辑，而非类别/结构的 replace）。 | Ref: Replace the blue AKW TRAVEL sign with a round wall-mounted clock.<br>No-ref: Replace the selected sign with a round wall-mounted clock. | 目视 |

#### `v2-sa_6010155`（#808，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 严重 | mask 质量 | ref+mask | Add a small white KEEP BACK sign on the crowd barrier on the right side of the car. | 已在原图上检查 U4.png：护栏 mask（box [1731,713,2065,1500]）填满了透明人群护栏后方的整个区域，包括观众的腿、短裤和鞋（例如原图约 1950-2030,1150-1290 处的鞋），而不仅仅是金属护栏杆。 | 将 U4 重新分割为仅金属人群护栏（栏杆和底脚），排除其后方的观众 | 目视 |

#### `v2-sa_6027797`（#812，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | ref+mask | Replace the right of the two lounge chairs between the large planters at the right with a white wooden sun lounger. | U3 把深色藤制躺椅（box [1894,813,2050,888]）替换为 'a white wooden sun lounger' —— 物体类别/形状相同；变化仅是颜色加材质。 | Ref: Replace the right of the two lounge chairs between the large planters at the right with a round patio table with two stools.<br>No-ref: Replace the selected lounge chair with a round patio table with two stools.<br>或改为属性（材质/颜色 -> 白色木质） | 目视 |

#### `v2-sa_6031468`（#813，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+point | Replace the purple-and-beige shirt on the man at the right with a plain white cotton T-shirt. | 被 mask 的衣物是右侧男子的紫色和米色短袖 T 恤（印有大“4”）；替换为“a plain white cotton T-shirt”保持相同衣物类型，仅改变颜色/印花。 | Ref: Replace the purple-and-beige shirt on the man at the right with a dark green rain poncho.<br>No-ref: Replace the selected shirt with a dark green rain poncho.<br>或转为 attribute：'Change the color of the purple-and-beige shirt on the man at the right to plain white.' | 目视 |

#### `v2-sa_6082506`（#818，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | ref+none | Replace the pale blue dress on the woman holding the white flowers with a pale lavender silk hanfu dress. | 被 mask 的衣物本来就是浅蓝色汉服风格连衣裙（高腰襦裙）。替换为 'a pale lavender silk hanfu dress' 类别和结构相同，只改变颜色和材质，因此实际上是属性编辑。 | Ref: Replace the pale blue dress on the woman holding the white flowers with a fitted pale lavender qipao.<br>No-ref: Replace the selected dress with a fitted pale lavender qipao.<br>或改为属性编辑：'Change the color of the pale blue dress on the woman holding the white flowers to pale lavender.' | 目视 |
| U4 | 严重 | 指代歧义 | ref+mask | Add a small gold butterfly brooch on its upper chest on the red-and-pink dress on the nearest woman. | REF 选的是 'the red-and-pink dress on the nearest woman'（被 mask 的女子在原图约 x=900-1350）。紧靠她左侧的女子（约 x=200-780）穿着几乎相同的红色上衣和粉色裙子的汉服。两人深度几乎相同，头部大小相近，脚都在底边，因此 'nearest' 无法可靠地唯一指向被 mask 的那位。 | Ref: Add a small gold butterfly brooch on the upper chest of the red-and-pink dress on the second woman from the left.<br>ZH: 在左起第二位女子的红粉色长裙上胸处加上一枚小金色蝴蝶胸针。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+mask | Add a small gold butterfly brooch on its upper chest on the red-and-pink dress on the nearest woman. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small gold butterfly brooch on the upper chest of the red-and-pink dress on the nearest woman.<br>No-ref: Add a small gold butterfly brooch on the upper chest of the selected dress. | 文本 |

#### `v2-sa_6091887`（#819，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 方位/序数/实例指代错误 | noref+box | Remove the red SUV parked near the center. | U1 红色 SUV 位于图像左下部 cx=0.29W 处,并不“near the center”;它仍是唯一的红色 SUV,因此颜色即可识别。 | Ref: Remove the red SUV parked on the left side of the street.<br>ZH:移除左侧街边停着的红色SUV。 | 目视 |

#### `v2-sa_6097564`（#820，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the gray coat in the left foreground with a beige wool coat. | U2 mask 的是左前景带毛边兜帽的浅灰色棉服（box [0,1050,830,1500]）。'A beige wool coat' 保持外套类别，只改变颜色和材质。 | Ref: Replace the gray coat in the left foreground with a red plaid poncho.<br>No-ref: Replace the selected coat with a red plaid poncho.<br>或改为属性：'Change the color of the gray coat in the left foreground to beige.' | 目视 |

#### `v2-sa_610993`（#822，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | mask 质量 | ref+none | Change the color of the female singer's jacket to burgundy. | U1 'jacket' mask 覆盖了铆钉黑色短夹克,但也填满了翻领之间的整个胸部,即下面的黑色短上衣(直到裸露的腹部)和项链区域。 | restrict mask to the jacket sleeves/lapels/back, excluding the black crop top and necklace | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the guitarist's T-shirt with a plain white T-shirt. | U2 是吉他手的黑色骷髅印花白字 T 恤；'replace with a plain white T-shirt' 衣物类型不变，只改变颜色/印花。 | Ref: Replace the guitarist's T-shirt with a red-and-black checked flannel shirt.<br>No-ref: Replace the selected T-shirt with a red-and-black checked flannel shirt. | 目视 |
| U3 | 严重 | 多单元同一物理对象/相互冲突 | noref+box | Remove the female singer's necklace. | U3 项链由 U1 夹克所属的同一位女歌手佩戴（两者的 physical parent 都是该歌手）；U3 的 mask/box 位于其胸前 U1 mask 区域内，因此这两个单元不是独立的物体。 | 去掉 U3（或去掉 U1），使只有一个单元以该歌手为目标 | 目视 |

#### `v2-sa_6123226`（#823，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 方位/序数/实例指代错误 | ref+point | Remove the black taxi with plate 38-78. | REF 以车牌“38-78”识别该出租车,但放大源图后,被 mask 的出租车车牌(box [443,741,879,1020])实为“38-28”。在约 20 辆相似的黑色出租车中车牌是唯一标识,因此错误的车牌会使 ref-only / 评估者的描述指向不存在的实例。 | Ref: Remove the black taxi with plate 38-28.<br>ZH:移除车牌为38-28的黑色出租车。 | 目视 |

#### `v2-sa_6129691`（#824，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代类别与 mask 不符 | ref+none | Replace the round white shop sign in the lower right with a round white sign with a red coffee cup. | U1 mask 是右下方杆子上的圆形白色交通管制标志（红色禁止左转箭头，文字 'EXCEPT MUNI & TAXIS'），不是 'shop sign'。 | Ref: Replace the round white no-left-turn traffic sign in the lower right with a round white sign with a red coffee cup.<br>ZH: 右下方的圆形白色禁止左转交通标志 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a small blue heart patch on its sleeve on the white hoodie worn with a sandwich board. | 被 mask 的人穿浅灰/白色连帽衫，手持标语牌，不是三明治广告牌。 | Ref: Add a small blue heart patch on the sleeve of the light-gray hoodie of the marcher holding a white placard at the lower left. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a small blue heart patch on its sleeve on the white hoodie worn with a sandwich board. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small blue heart patch on the sleeve of the white hoodie worn with a sandwich board.<br>No-ref: Add a small blue heart patch on the sleeve of the selected hoodie. | 文本 |

#### `v2-sa_6151826`（#825，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | noref+mask | Replace the two-headed streetlamp above the nearest donkey with a black two-headed lantern streetlamp. | 被 mask 的路灯本来就是深色/黑色的双头灯笼式灯杆;将其 '替换为 a black two-headed lantern streetlamp' 实质上无变化(类别、结构和颜色相同)。 | Ref: Replace the two-headed streetlamp above the nearest donkey with a single tall modern LED street light.<br>No-ref: Replace the selected streetlamp with a single tall modern LED street light. | 目视 |

#### `v2-sa_6262299`（#830，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | ref+point | Replace the red CHIPOTLE sign on the right with a red rectangular BISTRO sign. | 被 mask 的物体本来就是一块写着 CHIPOTLE 的红色矩形悬挂招牌。'A red rectangular BISTRO sign' 类别、颜色和形状均不变，只改变印刷文字，属于属性级（文字）编辑，而不是替换。 | Ref: Replace the red CHIPOTLE sign on the right with a round hanging wrought-iron lantern.<br>No-ref: Replace the selected sign with a round hanging wrought-iron lantern.<br>或改为属性编辑：'Change the text of the red CHIPOTLE sign on the right to BISTRO.' | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a small blue inspection sticker in its lower corner on the bus windshield. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small blue inspection sticker in the lower corner of the bus windshield.<br>No-ref: Add a small blue inspection sticker in the lower corner of the selected windshield. | 文本 |

#### `v2-sa_6274646`（#832，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+box | Replace the boy's blue-and-yellow checked shirt with a plain light green cotton shirt. | 男孩的蓝黄格纹翻领衬衫被替换为 'a plain light green cotton shirt'，保持相同的衣物类型；只有颜色/图案改变。 | Ref: Replace the boy's blue-and-yellow checked shirt with a light green hooded sweatshirt.<br>No-ref: Replace the selected shirt with a light green hooded sweatshirt. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+box | Add a small white FRESH APPLES price card on its front on the red fruit box in front of the boy. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small white FRESH APPLES price card on the front of the red fruit box in front of the boy.<br>No-ref: Add a small white FRESH APPLES price card on the front of the selected box. | 文本 |

#### `v2-sa_6274955`（#833，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 方位/序数/实例指代错误 | noref+mask | Remove the white car on the road below the large building. | 被 mask 的汽车（box 476-536 x 1564-1604）是带白色引擎盖的红色汽车（类似出租车），不是白色汽车，原图裁剪可见。颜色词与目标矛盾，可能把评判者引向另一辆白色车辆。 | Ref: Remove the red-and-white car on the road below the large building.<br>相应修正 ZH 颜色 | 目视 |

#### `v2-sa_6276448`（#834，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the large dark restaurant sign above the officers with a dark green sign reading NOODLE HOUSE. | 被 mask 的物体是带中文文字的大号深石板蓝矩形店招牌;payload 'a dark green sign reading NOODLE HOUSE' 是同一类型和形状的招牌,只改变颜色和文字。 | Ref: Replace the large dark restaurant sign above the officers with a row of red paper lanterns.<br>No-ref: Replace the selected sign with a row of red paper lanterns.<br>Or convert to attribute (color: dark green) / text edit. | 目视 |

#### `v2-sa_6282163`（#835，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+mask | Replace the rower's checked shirt with a plain light blue long-sleeved shirt. | U1 mask 是划船者的蓝/灰格子长袖纽扣衬衫（box [879,769,1123,1057]）；替换为 'a plain light blue long-sleeved shirt' 衣物类型和袖长不变，只改变图案/颜色。 | Ref: Replace the rower's checked shirt with a sleeveless orange life vest.<br>No-ref: Replace the selected shirt with a sleeveless orange life vest.<br>或改为属性编辑：'Change the pattern of the rower's checked shirt to plain light blue.' | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a small wooden FRESH FISH sign on its side wall on the blue-and-green waterside hut. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small wooden FRESH FISH sign on the side wall of the blue-and-green waterside hut.<br>No-ref: Add a small wooden FRESH FISH sign on the side wall of the selected hut. | 文本 |

#### `v2-sa_6315997`（#837，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 指代歧义 | ref+none | Remove the low pale shrub behind the car. | mask(box 1902-2089 x 98-203,右上角)覆盖的是汽车后方花坛里的深绿色多叶灌木。REF 称其为“the low pale shrub”,但它并不浅色;紧邻其左侧的浅粉色灌木和黄色菊花更符合“pale”,因此 REF 可能把人引向错误的植物。 | Ref: Remove the dark green shrub in the garden bed at the top right, just right of the yellow flowers. | 目视 |

#### `v2-sa_6329048`（#838，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+mask | Replace the seated woman's red shoulder bag with a small black leather shoulder bag. | 被 mask 的物体是女子的红色小斜挎/单肩包；将其替换为 'a small black leather shoulder bag' 保持相同物体类型和大小，只改变颜色/材质。 | Ref: Replace the seated woman's red shoulder bag with a small woven straw basket bag.<br>No-ref: Replace the selected bag with a small woven straw basket bag.<br>或改为属性：'Change the color of the seated woman's red shoulder bag to black.' | 目视 |
| U3 | 轻微 | mask 质量 | ref+point | Change the color of the pole of the rightmost globe streetlamp to bronze. | REF 针对“the pole of the rightmost globe streetlamp”，但 mask 同时包含了白色球形灯头和灯杆，因此改色也会给球形灯罩着色。 | 从 mask 中排除球形灯罩，或改写为 'Change the color of the rightmost globe streetlamp's pole and fitting to bronze.' | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a small blue wave decal on its lower panel on the visible front door of the silver car behind the seated woman. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small blue wave decal on the lower panel of the visible front door of the silver car behind the seated woman.<br>No-ref: Add a small blue wave decal on the lower panel of the selected car door. | 文本 |

#### `v2-sa_6400522`（#842，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| case | 严重 | 多单元同一物理对象/相互冲突 |  |  | 图中只有一位穿古装的女子：U1 是她长裙的花卉袖子，U2 是别在同一件长裙胸衣上的浮雕胸针；两个单元属于同一个人/同一件衣物。 | 只保留一个单元（例如 U2 胸针），或将其中一个替换为独立物体（例如右侧的石墙、针叶树枝） | 目视 |
| U1 | 轻微 | mask 质量 | ref+mask | Change the color of the floral sleeve at the left to dark blue. | U1 袖子 mask 在图像底边（原图 y~2150-2250）的手/背景上有参差的碎片。 | 清理底部碎片 | 目视 |

#### `v2-sa_6408945`（#843，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | ref+box | Replace the bright red diary cover left of the black diary with a tan leather cover. | U3 mask 的是鲜红色带纹理的日记本封面(box [727,461,1153,940])。“A tan leather cover”仍是日记本封面,仅改变颜色和材质。 | Ref: Change the color and material of the bright red diary cover left of the black diary to tan leather.<br>No-ref: Change the color and material of the selected cover to tan leather.<br>将操作改为 attribute | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add small gold initials AB near its top on the red diary cover in the back-right corner. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add small gold initials AB near the top of the red diary cover in the back-right corner.<br>No-ref: Add small gold initials AB near the top of the selected cover. | 文本 |

#### `v2-sa_6432289`（#846，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+mask | Replace the beige shoulder bag on the woman near the center with a brown leather shoulder bag. | U1 是一个米色/奶油色单肩包；'replace with a brown leather shoulder bag' 保持相同物体类型和形状，只改变颜色/材质。 | Ref: Replace the beige shoulder bag on the woman with long dark hair with a small black backpack.<br>No-ref: Replace the selected bag with a small black backpack.<br>或改为属性：将包的颜色改为棕色 | 目视 |
| U1 | 轻微 | 方位/序数/实例指代错误 | noref+mask | Replace the beige shoulder bag on the woman near the center with a brown leather shoulder bag. | 包的主人位于 x~0.23W，中心偏左；最靠近图像中心的是穿花纹外套和头巾的女士（x~0.35W）。包本身是唯一的，所以目标仍可恢复。 | Ref: Replace the beige shoulder bag on the long-haired woman in a white-sleeved top with a small black backpack. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a thin white stripe across its lower panel on the front door of the parked brown car. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a thin white stripe across the lower panel of the front door of the parked brown car.<br>No-ref: Add a thin white stripe across the lower panel of the selected car door. | 文本 |

#### `v2-sa_6472262`（#848，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the tall narrow menu board against the right column with a narrow black chalkboard reading COFFEE AND CAKE. | 被 mask 的物体本来就是靠在右侧立柱上的高窄深色黑板菜单；替换为 'a narrow black chalkboard reading COFFEE AND CAKE' 类别和形状不变，只改变书写的文字。 | Ref: Replace the tall narrow menu board against the right column with a small potted bay tree.<br>No-ref: Replace the selected board with a small potted bay tree.<br>或改为属性编辑（修改文字） | 目视 |
| U4 | 轻微 | mask 质量 | ref+point | Add a small OPEN sign on the left door on the central white double doors of the pavilion. | U4 门 mask 是碎裂的（2 个组件），其下半部分沿着立在门前的白色拱形玻璃屏风而不是门板；上方的亮窗区域也不完整。 | 将中央白色双开门重新分割为屏风后方的干净矩形 | 目视 |

#### `v2-sa_6516217`（#852，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+box | Replace the yellow-and-blue ball in the air with a white volleyball. | 空中的球本来就是黄蓝相间的排球(Mikasa 风格的拼片)。将其替换为“a white volleyball”类别和形状不变,仅改变颜色。 | Ref: Replace the yellow-and-blue ball in the air with an orange basketball.<br>No-ref: Replace the selected ball with an orange basketball.<br>或转换为 attribute:“Change the color of the yellow-and-blue ball in the air to white.” | 目视 |
| U3 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a small black number 7 on its chest on the gray T-shirt on the player raising both arms. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small black number 7 on the chest of the gray T-shirt on the player raising both arms.<br>No-ref: Add a small black number 7 on the chest of the selected T-shirt. | 文本 |

#### `v2-sa_654776`（#855，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| case | 严重 | 多单元同一物理对象/相互冲突 |  |  | U2(白色棒球帽)和 U3(带金色登山扣的黑色背包)属于同一个男子:U3 的裁剪图显示戴白帽者背着那个背包。 | Drop U2 or U3, or retarget U2 to the other light cap at x~0.44W (different person). | 目视 |
| U1 | 严重 | replace 实为属性修改 | ref+box | Replace the pink knitted hat at the far left with a plain purple knitted beanie. | 把粉色针织（猫耳）帽替换为 'a plain purple knitted beanie' 仍是针织帽；本质上是换色。 | Ref: Replace the pink knitted hat at the far left with a black wide-brimmed sun hat.<br>No-ref: Replace the selected hat with a black wide-brimmed sun hat. | 目视 |
| U2 | 严重 | 指代歧义 | noref+mask | Change the color of the white baseball cap near the center-left to dark blue. | 'the white baseball cap near the center-left' ——U2 的帽子在 x~0.24W（偏左），而另一顶白色/浅色棒球帽在 x~0.44W，更符合 'center-left'。 | Ref: Change the color of the white baseball cap on the man with the black backpack, just below the raised-fist placard, to dark blue.<br>但参见与 U3 的独立性问题。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+mask | Add a small gold star in its upper-left corner on the black placard with the red raised fist. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small gold star in the upper-left corner of the black placard with the red raised fist.<br>No-ref: Add a small gold star in the upper-left corner of the selected placard. | 文本 |

#### `v2-sa_6561145`（#857，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | mask 质量 | noref+mask | Remove the small white motorboat near the center-right. | 小型白色摩托艇 [1454,911,1611,977] 的 mask 还包含了坐着的驾驶员的上半身;用该 mask 移除“boat”也会移除这个人(scope 未说明)。 | Ref: Remove the small white motorboat near the center-right together with its driver.<br>No-ref: Remove the selected boat together with its driver. | 目视 |
| U2 | 严重 | mask 质量 | ref+none | Change the color of the cream hull of the motorboat in the foreground to dark blue. | REF 的目标是 'the cream hull'（范围为船体），但 mask [177,1199,973,1500] 覆盖整艘水上出租车：光亮的桃花心木舱顶、挡风玻璃、后部驾驶舱和座椅，以及奶油色下部船体。mask 的层级（整艘船）与所指部位不符。 | Ref: Change the color of the cream lower hull of the wooden water taxi in the foreground to dark blue.<br>将 mask 限制为桃花心木甲板/船舱以下的奶油色船体侧面，或把范围改为 'boat' 并重新措辞。 | 目视 |
| U3 | 严重 | replace 实为属性修改 | ref+mask | Replace the dark padded jacket on the man in the foreground boat with a tan canvas jacket. | 被 mask 的物体是深灰色绗缝羽绒服；“a tan canvas jacket”仍是同样结构的夹克，即颜色 + 材质变化。 | Ref: Replace the dark padded jacket on the man in the foreground boat with a knitted wool sweater.<br>No-ref: Replace the selected jacket with a knitted wool sweater. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a small gold coffee-cup emblem at its right end on the green cafe awning at the far left. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small gold coffee-cup emblem at the right end of the green cafe awning at the far left.<br>No-ref: Add a small gold coffee-cup emblem at the right end of the selected awning. | 文本 |

#### `v2-sa_6563331`（#858，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+point | Replace the black suit jacket on the leftmost man with a navy blue blazer. | U1 mask 是最左侧男子的黑色西装外套(box [55,410,278,703]);'navy blue blazer' 在结构上是同一件剪裁外套,因此编辑实质上是改色 黑->海军蓝。 | Ref: Replace the black suit jacket on the leftmost man with a tan trench coat.<br>No-ref: Replace the selected jacket with a tan trench coat.<br>or convert to attribute: change color of the black suit jacket to navy blue | 目视 |
| U3 | 轻微 | 措辞/文法/描述细节 | ref+box | Add a small embroidered white flower on its upper back on the black coat on the woman at the right of the group. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small embroidered white flower on the upper back of the black coat on the woman at the right of the group.<br>No-ref: Add a small embroidered white flower on the upper back of the selected coat. | 文本 |

#### `v2-sa_6616672`（#860，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | noref+mask | Replace the white shirt on the man beside the van in the rear right with a pale blue button-up shirt. | 被 mask 的衣物是警卫的白色短袖纽扣制服衬衫；'a pale blue button-up shirt' 是同一衣物类型/结构，只改变颜色。 | Ref: Replace the white shirt on the man beside the van in the rear right with a dark zip-up windbreaker jacket.<br>No-ref: Replace the selected shirt with a dark zip-up windbreaker jacket.<br>或改为属性编辑：'Change the color of the white shirt on the man beside the van in the rear right to pale blue.' | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+none | Add a small blue flower decal on its visible front body panel on the small white car behind the foreground car at the right. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small blue flower decal on the visible front body panel of the small white car behind the foreground car at the right.<br>No-ref: Add a small blue flower decal on the visible front body panel of the selected car. | 文本 |

#### `v2-sa_6670486`（#864，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the silver SUV behind the sedan with a white compact SUV. | U2 mask 的是一辆银色紧凑型跨界 SUV（类似 Ford EcoSport，box [1626,1082,1982,1287]）。载荷 'a white compact SUV' 属于相同类别和尺寸级别，因此实际变化只有颜色。 | Ref: Replace the silver SUV behind the sedan with a red pickup truck.<br>No-ref: Replace the selected SUV with a red pickup truck.<br>或改为属性：'Change the color of the silver SUV behind the sedan to white.' | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+mask | Add a small red ribbon around its neck on the stone lion left of the first red door. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small red ribbon around the neck of the stone lion left of the first red door.<br>No-ref: Add a small red ribbon around the neck of the selected statue. | 文本 |

#### `v2-sa_6678734`（#865，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | noref+point | Replace the blue sign along the upper-right edge with a blue rectangular FOOD AND DRINKS sign. | U3 已经是带白色文字的蓝色矩形标牌（'Tns. 089-...'）；替换为“a blue rectangular FOOD AND DRINKS sign”保持类别、形状和颜色，仅改变印刷文字。 | Ref: Replace the blue sign along the upper-right edge with a round red-and-white restaurant sign.<br>No-ref: Replace the selected sign with a round red-and-white restaurant sign. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+box | Add a folded white towel inside it in the blue basket at the far right. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | placement.site 单独存储，渲染为 "<relation> the <site> of <anchor>" | 文本 |

#### `v2-sa_6690415`（#866，扩充 #200–#868，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the white pedestrian-zone sign near the street corner with a white sign with a blue pedestrian symbol and PEDESTRIAN AREA text. | 被 mask 的标志本来就是带蓝色圆形行人符号的白色 'area pedonale' 标志;替换为 'a white sign with a blue pedestrian symbol and PEDESTRIAN AREA text' 只改变文字语言,即文字属性编辑,而非结构替换。 | Ref: Change the text on the white pedestrian-zone sign near the street corner to "PEDESTRIAN AREA".<br>No-ref: Change the text on the selected sign to "PEDESTRIAN AREA".<br>op replace->attribute (text); or replace with a different sign type, e.g. a red-and-white no-entry sign | 目视 |

#### `v2-sa_6724758`（#870，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the New York T-shirt on the man at the right with a plain white T-shirt. | 被 mask 的物体是一件印有 'New York' 的深灰色T恤；将其替换为 'a plain white T-shirt' 保持衣物类型，仅改变颜色/印花。 | Ref: Change the color of the New York T-shirt on the man at the right to plain white.<br>No-ref: Change the color of the selected T-shirt to plain white.<br>或替换为不同类型的衣物，例如白色纽扣衬衫 | 目视 |

#### `v2-sa_6737576`（#872，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+box | Remove the brown satchel on the background figure. | 'the background figure' 同时用于 U1（左上中部的挎包者，box x 426-634）和 U3（右上角的另一个人物）；背景中有多人，因此 REF 无法指出背挎包的人。 | Ref: Remove the brown satchel hanging at the hip of the background figure just left of the soldier's cap at the top. | 目视 |
| U3 | 严重 | replace 实为属性修改 | noref+point | Replace the black trousers on the background figure with dark wool trousers. | U3 将背景人物的黑色裤子替换为“dark wool trousers”——类别相同、深色调相同；仅是材质变化，应属于 attribute。 | Ref: Replace the black trousers on the background figure at the upper right with knee-length dark shorts.<br>No-ref: Replace the selected trousers with knee-length dark shorts.<br>或转为 attribute material=wool | 目视 |
| U3 | 严重 | 指代歧义 | noref+point | Replace the black trousers on the background figure with dark wool trousers. | 士兵身后有几个背景人物在行走(画面左上和右上),大多穿深色长裤;'the background figure' 无法指出右上角那位(box x 844-1137, y 0-385)。 | Ref: Replace the black trousers on the background figure at the top right, just behind the soldier's cap, with knee-length dark shorts. | 目视 |

#### `v2-sa_6754915`（#874，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 方位/序数/实例指代错误 | ref+none | Remove the blue backpack beside the man in the black hat. | 蓝色 Invicta 背包（box 896-983 x 1176-1275）位于一位穿藏青色连帽衫、戴米色帽子（不是黑帽子）的坐着的男子旁边。唯一明确戴黑帽的人是最右边（约 0.83W）坐着的男子，因此 REF 锚点指向了错误的人。 | Ref: Remove the blue backpack beside the seated man in the navy hoodie and beige cap.<br>相应修正 ZH | 目视 |
| U2 | 轻微 | 指代歧义 | ref+mask | Change the color of the purple coat on the seated woman at the left to navy blue. | "the seated woman at the left" 是相对于右侧三人组（紫外套、格子连帽衫、深色外套）而言的。在整幅图中，穿紫外套的女子位于约 0.59W，且有许多坐着的人更靠左。 | Ref: Change the color of the purple coat on the seated long-haired woman to navy blue. | 目视 |

#### `v2-sa_6776348`（#876，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the purple polo shirt on the man left of center with a plain white polo shirt. | U2 将紫色 polo 衫(box [522,231,738,525])替换为 'a plain white polo shirt' —— 同一服装类型,只改变颜色。 | Ref: Replace the purple polo shirt on the man left of center with a white tank top.<br>No-ref: Replace the selected polo shirt with a white tank top.<br>Or convert to attribute: change the color of the purple polo shirt to white. | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | ref+point | Remove the turquoise polo shirt on the man at center-right. | U3 移除的是一名年轻男子所穿的青绿色 polo 衫（box [757,178,911,452]）；移除所穿衣物会留下未定义的裸露躯干/内层衣物。 | Ref: Change the color of the turquoise polo shirt on the young man beside the man in purple to orange.<br>No-ref: Change the color of the selected polo shirt to orange.<br>将 op 改为 attribute（或替换为另一件衣物）。 | 目视 |
| U3 | 严重 | 方位/序数/实例指代错误 | ref+point | Remove the turquoise polo shirt on the man at center-right. | REF 说 'the man at center-right'，但穿青绿色Polo衫的男子位于 0.37W，偏左；穿白背心（约 0.65W）和米色衬衫（约 0.9W）的男子才是中偏右/右侧。 | Ref: ... the turquoise polo shirt on the young man just right of the man in purple, left of center ...<br>ZH: 中间偏左、紫衣男子右侧的青年男子 | 目视 |

#### `v2-sa_6814925`（#881，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 指代歧义 | ref+box | Remove the chair beside the planted path. | U3 mask = 最右边缘搭着绿色外套的黑色咖啡馆椅子（box 中心 0.96W,0.86H）。沿种植床有许多相同的黑色咖啡馆椅子（如约 0.70-0.85W, 0.55-0.70H），因此“the chair beside the planted path”不能唯一指出它。 | Ref: Remove the black chair with a green jacket draped over it at the far right edge, next to the seated woman.<br>ZH: 移除最右侧边缘搭着绿色外套的黑色椅子。 | 目视 |

#### `v2-sa_682765`（#883，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+point | Replace the white shirt on the foreground man at the left with a pale blue shirt. | 被 mask 的衣物是前景金发男子的白色T恤（左下角，被画面截断）；'a pale blue shirt' 是同一衣物类别，仅颜色改变。 | Ref: Replace the white T-shirt on the foreground man at the left with a red zip-up hoodie.<br>No-ref: Replace the selected T-shirt with a red zip-up hoodie.<br>或转为属性：'Change the color of the white T-shirt on the foreground man at the left to pale blue.' | 目视 |
| U2 | 严重 | 方位/序数/实例指代错误 | ref+box | Change the color of the white button-up shirt on the man near the center to light green. | “the man near the center”——被 mask 的男子(藏青帽、白色纽扣衬衫,box cx=0.68)明显偏中心右侧;真正中心附近有数名穿白衣的男子(例如紧靠其左侧背黑色背包的男子、穿条纹衬衫的男子)与之竞争。“button-up”线索有帮助,但空间短语具有误导性。 | Ref: Change the color of the white button-up shirt on the man in the navy cap, right of center, to light green.<br>ZH:将中间偏右戴藏蓝色帽子男子的白色纽扣衬衫的颜色改为浅绿色。 | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | noref+mask | Remove the yellow T-shirt on the man at the right. | 移除黄色 T 恤（男子唯一可见的上身衣物，背对镜头）会留下未定义的裸露躯干；不是合理的衣物移除。 | Ref: Replace the yellow T-shirt on the man at the right with a gray hooded sweatshirt.<br>No-ref: Replace the selected T-shirt with a gray hooded sweatshirt.<br>将 op 从 remove 改为 replace 或 attribute | 目视 |

#### `v2-sa_6834065`（#884，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | replace 实为属性修改 | ref+point | Replace the wooden park bench beneath the laptop with a dark green bench. | 将木质公园长椅替换为“a dark green bench”保持类别；只有颜色（以及隐含的材质）变化。 | Ref: Replace the wooden park bench beneath the laptop with a low stone wall.<br>No-ref: Replace the selected bench with a low stone wall.<br>或转为 attribute：Change the color of the wooden park bench beneath the laptop to dark green. | 目视 |

#### `v2-sa_6841406`（#885，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the small window on the right side of the facade with a warm amber window. | U2 将立面右侧的深色小窗(box [2105,1143,2174,1235])替换为 "a warm amber window" —— 同一扇窗,只是颜色/色调(亮着的琥珀色玻璃)变化;没有结构替换。 | Ref: Replace the small window on the right side of the facade with a round porthole window.<br>No-ref: Replace the selected window with a round porthole window.<br>or convert to attribute: Tint the small window on the right side of the facade warm amber. | 目视 |

#### `v2-sa_6859686`（#887，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | ref+none | Replace the blue shirt on the marcher near the center with a white polo shirt. | “the marcher near the center”——U2(cx=0.27W)位于左三分之一处;十几名游行者穿着同样的蓝衬衫,其中几位更靠近图像中心。 | Ref: Replace the blue shirt on the marcher carrying a black jacket and brown bag, second from the left, with a white polo shirt. | 目视 |
| U3 | 严重 | mask 质量 | ref+mask | Remove the stroller at the right foreground. | U3 的 'stroller' mask 是碎片化的（4 个连通块），包含大型橙色圆点气球和条纹毯子，而婴儿周围的婴儿车框架/座椅仅被部分且参差地覆盖。 | 仅对婴儿车框架/座椅重新分割，排除气球 | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | ref+mask | Remove the stroller at the right foreground. | 婴儿车里坐着一个幼童；移除整个婴儿车会让孩子悬空/需要凭空造一个新支撑，使该编辑不适定。 | Ref: Change the color of the stroller's black frame at the right foreground to silver.<br>No-ref: Change the color of the selected stroller's frame to silver.<br>将 op 从 remove 改为 attribute 或 add（例如在婴儿车把手上加一个杯架） | 目视 |

#### `v2-sa_6868139`（#888，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | mask 质量 | ref+point | Remove the front wheel on the nearest illuminated cart. | U1 mask(box [2090,1190,2189,1339])是右侧大型发光纸灯笼箱上剪出的马车插画的最右侧车轮。它是一幅图画,不是实体马车轮。马在画面左侧,所以马车朝左,被 mask 的最右轮是后轮,而不是 'front wheel'。 | Ref: Remove the rear wheel of the carriage picture on the large illuminated lantern box at the right.<br>better: retarget to a physical object, or drop the unit | 目视 |

#### `v2-sa_68727`（#889，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+none | Change the color of the dark blue jacket on the skater at the left to burgundy. | U1 mask 是位于冰场右侧 x~0.86W 处一名男子的深蓝色羽绒服；'the skater at the left' 仅相对于他旁边穿浅蓝色夹克的女子（U3）才成立。正式输入是 ref-only（ref+none），而在整幅图像中还有许多滑冰者更靠左（例如 x~0.26W 的穿黑衣女子），因此 REF 指向了错误的区域。 | Ref: Change the color of the dark blue jacket on the skater at the right side of the rink, standing just left of the woman in the light blue jacket, to burgundy.<br>相应更新 ZH | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | noref+box | Remove the light blue jacket on the skater at the right. | U3 移除的是右侧女子穿的浅蓝色连帽羽绒服；移除所穿外衣会使身体/内层衣物无定义。 | Ref: Remove the hood from the light blue jacket on the skater at the right.<br>No-ref: Remove the hood from the selected jacket.<br>或将 op 改为属性：把夹克颜色改为红色 | 目视 |

#### `v2-sa_692643`（#893，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 属性值问题（无变化/含糊） | noref+box | Change the color of the round plant on the yellow wall to deep green. | U2 mask（box [1383,376,1485,557]）是本来就已经是绿色的悬挂植物；'change the color ... to deep green' 近乎无操作，无法可靠评分。 | Ref: Change the color of the round plant on the yellow wall to autumn orange.<br>No-ref: Change the color of the selected plant to autumn orange. | 目视 |
| U3 | 严重 | replace 实为属性修改 | ref+point | Replace the metal utility box on the left wall with a blue utility box. | U3 将左墙上的深色金属配电箱替换为 'a blue utility box' ——同一物体，仅改色。 | Ref: Replace the metal utility box on the left wall with a wall-mounted wooden mailbox.<br>No-ref: Replace the selected utility box with a wall-mounted wooden mailbox.<br>或转为属性 color->blue | 目视 |

#### `v2-sa_6992576`（#898，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代类别与 mask 不符 | ref+mask | Replace the glass bottle beside the baskets with a blue ceramic vase. | 被 mask 的“glass bottle”（box [1056,1656,1154,1871]）是放在长凳上的水烟壶的玻璃水底座（黄铜杆和蓝色软管从中升起）；它是水烟壶的一部分，不是独立的瓶子，而且也并非真的“beside the baskets”（篮子挂在上方墙上）。把它替换成蓝色陶瓷花瓶会让水烟壶杆悬空。 | Ref: Replace the glass base of the hookah with the blue hose with a blue ceramic hookah base.<br>No-ref: Replace the selected hookah base with a blue ceramic hookah base.<br>将 scope 设为 'hookah base'。 | 目视 |
| U3 | 轻微 | 指代歧义 | noref+box | Remove the plastic bucket on the right. | 被 mask 的塑料桶(box [849,1624,962,1742])靠近图像中心(x~0.60),位于水烟壶之间,并不明显 'on the right'。 | Ref: Remove the white plastic tub between the hookahs. | 目视 |
| U4 | 严重 | 方位/序数/实例指代错误 | ref+point | Add a small blue label on the open cardboard box below the wall display. | 被 mask 的纸箱（box [1071,564,1341,807]）位于砖/墙台沿的上方，在墙挂篮子展示的 ABOVE，而不是 'below the wall display'；它看起来也不是开着的。 | Ref: Add a small blue label on the cardboard box on the top ledge above the wall baskets.<br>ZH: 墙面编篮上方台沿上的纸箱. | 目视 |

#### `v2-sa_7002146`（#899，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+point | Change the color of the road wheel on the tank at the left to dark gray. | 坦克一字排开有五个几乎相同的负重轮；'the road wheel on the tank at the left' 没有说是哪一个。被 mask 的轮子 [487,951,666,1198] 是从左数第四个（在可见的大轮中是从右数第二个）。 | Ref: Change the color of the fourth road wheel from the left on the tank to dark gray.<br>ZH: 将坦克从左数第四个负重轮的颜色改为深灰色。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+box | Replace the concrete post in the foreground with a dark stone post. | 被 mask 的物体是顶部带青色信息牌的灰色混凝土基座立柱;payload “a dark stone post”形状/类别相同,仅改变颜色/材质。 | Ref: Replace the concrete post in the foreground with a small black metal lamp post.<br>No-ref: Replace the selected post with a small black metal lamp post. | 目视 |
| U3 | 轻微 | 编辑不合理/不可执行 | noref+mask | Remove the grass strip behind the tank. | U3 移除的是地被 'grass strip'（小路另一侧阳光照射的草坪的 4 个碎片，[1537,911,2000,983]）；移除一块无定形的表面区域没有明确结果（裸土？路面？），使编辑难以评判。 | Ref: Change the grass strip behind the tank to bare brown soil.<br>或选择离散物体，例如左侧的灯柱。 | 目视 |

#### `v2-sa_701713`（#900，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 方位/序数/实例指代错误 | noref+box | Change the color of the terracotta roof just right of the ship to dark brown. | U2 mask（box [1280,569,1468,607]）是船后方、两根桅杆之间可见的拱窗建筑的赤陶四坡屋顶，完全位于船的水平范围内（船跨约 x~320-1783）；并不是“just right of the ship”。船的真正右侧还有许多其他赤陶屋顶。 | Ref: Change the color of the terracotta hip roof of the arched-window building behind the ship, between its two masts, to dark brown.<br>ZH: 将船两根桅杆之间后方拱窗建筑的红瓦屋顶的颜色改为深棕色。 | 目视 |
| U3 | 严重 | replace 实为属性修改 | ref+point | Replace the small window on the distant building with a warm yellow window. | U3 将一扇小窗(box [138,736,172,783])替换为 'a warm yellow window' —— 同一物体类别,只改变颜色/光照。另外 'the small window on the distant building' 符合左侧 Hotel Viana Sol 建筑上许多相同的窗户。 | Ref: Replace the second-floor window below the HOTEL VIANA SOL sign at the far left with a small balcony door.<br>No-ref: Replace the selected window with a small balcony door.<br>make REF unique (e.g. 'the window at the left end of the Hotel Viana Sol facade') and make the payload a structural change, or convert to attribute | 目视 |

#### `v2-sa_7168629`（#904，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | noref+box | Replace the white T-shirt on the child at the top with a yellow T-shirt. | 将孩子的白/浅灰 T 恤替换为“a yellow T-shirt”保持相同衣物类别，仅改变颜色。 | Ref: Replace the white T-shirt on the child at the top with a yellow hooded sweatshirt.<br>No-ref: Replace the selected T-shirt with a yellow hooded sweatshirt.<br>或转为 attribute：'Change the color of the white T-shirt on the child at the top to yellow.' | 目视 |
| U3 | 严重 | 指代歧义 | noref+point | Remove the blue paint cup near the center. | 被 mask 的杯子(box [1025,771,1161,895],0.73W)是装着深色液体的浅蓝色调塑料杯;它的颜料并不是蓝色。另一个装深色液体的塑料杯更靠近真正的中心(约 x=740, y=1050,0.5W),调色盘上也有青/蓝色颜料格。'the blue paint cup near the center' 至少同样符合另一只杯子。mask 似乎还把液体内部留成了空洞。 | Ref: Remove the light-blue plastic cup of dark water at the upper right of the palettes.<br>ZH: 移除调色盘右上方装有深色水的浅蓝色塑料杯。 Also fill the interior of the U3 mask so the cup's contents are included. | 目视 |

#### `v2-sa_717431`（#905，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the turquoise scarf on the central person with a white scarf. | U2 是青绿色针织围脖/围巾；替换为 'a white scarf' 纯粹是同一类别内的换色。 | Ref: Replace the turquoise scarf on the central person with a gray wool turtleneck collar.<br>No-ref: Replace the selected scarf with a gray wool turtleneck collar.<br>或改为属性编辑：将青绿色围巾的颜色改为白色 | 目视 |

#### `v2-sa_724183`（#912，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the tan jacket on the fishmonger with a navy jacket. | 被 mask 的衣物是一件棕褐色绗缝羽绒夹克。'A navy jacket' 是相同的衣物类型，只改变颜色。 | Ref: Replace the tan quilted jacket on the fishmonger with a white rubberized fishmonger's apron.<br>No-ref: Replace the selected jacket with a white rubberized fishmonger's apron.<br>或改为属性：'Change the color of the fishmonger's tan quilted jacket to navy blue.' | 目视 |
| U3 | 严重 | 指代歧义 | noref+point | Remove the whole fish on the cutting table. | 被 mask 的物体是一个被切下的大金枪鱼头（box 1023-1464 x 814-1156），不是整条鱼。第二个金枪鱼头，即正在被切的那个，就在同一张桌子上它的后面。“The whole fish on the cutting table”与事实不符，也无法区分两个鱼头。 | Ref: Remove the large tuna head lying in front on the right side of the cutting table.<br>No-ref: Remove the selected fish head.<br>将 spec scope 改为 'fish head'。 | 目视 |
| U4 | 严重 | 指代歧义 | ref+box | Add a small red label on the white foam box on the shelf. | 左侧柜台上有多个白色泡沫箱:被 mask 的那个(~0.12W)、紧靠其左侧标有 '5.1' 的相邻一个,以及左上角的其他几个。'The white foam box on the shelf' 无法指出目标,而且它放在木柜台上而不是架子上。 | Ref: Add a small red label on the white foam box on the left counter, just right of the box marked 5.1. | 目视 |

#### `v2-sa_7266192`（#915，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+none | Replace the green technical sign in the center with a blue information sign. | 目标是绿色的“CARACTERISTICAS TECNICAS”信息牌；payload“a blue information sign”是相同的物体类型，因此该编辑简化为改色（绿到蓝）。 | Ref: Replace the green technical sign in the center with a wooden notice board holding a paper map.<br>No-ref: Replace the selected sign with a wooden notice board holding a paper map.<br>或转为 attribute：Change the color of the green technical sign in the center to blue. | 目视 |
| U2 | 严重 | 指代类别与 mask 不符 | ref+mask | Remove the vertical railing at the right. | U2 mask(box x1292-1500, y1574-2048)覆盖发光阶梯平台的右侧部分 —— 金属框架内成排的绿色 LED 灯和台阶面板 —— 而不只是 'vertical railing'。将其作为栏杆移除定义不清。 | Ref: Remove the illuminated step panel at the right edge of the platform.<br>No-ref: Remove the selected panel.<br>Or re-mask to only the metal railing bars at the right. | 目视 |
| U3 | 严重 | 指代歧义 | noref+box | Change the finish of the metal beam crossing the upper scene to matte black. | 摩天轮上部满是交叉的金属梁；被 mask 的细深色斜梁（box x60-742,y126-465）无法被 'the metal beam crossing the upper scene' 单独指出，而且它在夜景中本来就接近黑色，使 'matte black' 近乎无操作。 | Ref: Change the color of the thin diagonal metal beam at the upper left, just right of the white LED strip, to bright red.<br>No-ref: Change the color of the selected beam to bright red. | 目视 |

#### `v2-sa_7307193`（#917，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | replace 实为属性修改 | noref+box | Replace the information sign by the gate with a blue visitor sign. | 被 mask 的白色矩形信息牌被替换为 'a blue visitor sign' —— 同一物体类型和形状,实质上是改色;payload 在结构上描述不足。 | Ref: Replace the information sign by the gate with a round blue visitor sign showing a white 'i' symbol.<br>No-ref: Replace the selected sign with a round blue visitor sign showing a white 'i' symbol. | 目视 |
| U3 | 严重 | 指代歧义 | ref+point | Remove the wooden fence in the foreground. | REF 'the wooden fence in the foreground' 适用于两处木栏杆：位于左边缘被 mask 的那处（box [0,1309,292,1574]），以及中右前景中更大、更显眼的木质坡道栏杆。更显眼的那个不是目标。 | Ref: Remove the wooden fence at the left edge of the foreground.<br>No-ref: Remove the selected fence.<br>ZH: 移除前景左侧边缘的木栅栏。 | 目视 |

#### `v2-sa_7316567`（#919，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 属性值问题（无变化/含糊） | noref+box | Change the color of the dark jacket on the station worker to navy blue. | 车站工作人员的制服夹克（box x 235-489, y 423-903）已经是深海军蓝；将其改为“navy blue”几乎是无操作，无法评分。 | Ref: Change the color of the dark navy jacket on the station worker to light gray.<br>No-ref: Change the color of the selected jacket to light gray. | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the yellow direction board above the platform with a blue direction board. | 将站台上方的黄色指示牌替换为 'a blue direction board' —— 同一物体类别和形状,只改变颜色。 | Ref: Change the color of the yellow direction board above the platform to blue.<br>No-ref: Change the color of the selected direction board to blue.<br>convert op to attribute, or replace with a different object e.g. 'a round analog station clock' | 目视 |
| U3 | 轻微 | 措辞/文法/描述细节 | noref+point | Remove the blue station information screen at the upper left. | 左上方的车站信息屏是灰色外壳，带黑色 LED 显示和站台号 '4'；它不是蓝色的。 | Ref: Remove the gray station information screen with the platform number 4 at the upper left.<br>ZH 蓝色 -> 灰色 | 目视 |

#### `v2-sa_7337463`（#920，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代歧义 | noref+mask | Tint the lamp at the right storefront warm amber. | U2 mask 是立在右翼前面的高大路灯杆（box 1456-1507 x, 675-1296 y）。右侧店面在其 LEGACY GALLERY 招牌上方也有一排绿色鹅颈灯，所以 'the lamp at the right storefront' 有歧义；'Tint ... warm amber' 也不清楚指的是灯光辉光还是灯杆颜色。 | Ref: Change the color of the street lamp post in front of the right storefront to warm amber.<br>No-ref: Change the color of the selected lamp to warm amber.<br>使用属性 'color' 代替 'tint'。 | 目视 |
| U4 | 轻微 | 编辑不合理/不可执行 | ref+mask | Add a brass handle on the wooden entrance door in the center. | 中央木制双开门中央本来就有两个深色圆形把手;再添加“a brass handle”是多余的,且放置位置不明确。 | Ref: Add a brass kick plate along the bottom of the wooden entrance door in the center.<br>No-ref: Add a brass kick plate along the bottom of the selected door. | 目视 |

#### `v2-sa_7374194`（#923，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | replace 实为属性修改 | ref+point | Replace the black T-shirt on the man with the stroller with a white T-shirt. | 推婴儿车男子的黑色 T 恤被替换为 'a white T-shirt'：类别相同，只有颜色改变。 | Ref: Replace the black T-shirt on the man with the stroller with a white short-sleeved button-up shirt.<br>No-ref: Replace the selected T-shirt with a white short-sleeved button-up shirt.<br>或改为属性：'Change the color of the black T-shirt on the man with the stroller to white.' | 目视 |
| U2 | 严重 | 指代歧义 | noref+point | Tint the departure screen on the left blue and white. | 左侧有三块相邻的航班信息屏（原图 x 约 0-500）。被 mask 的（box [269,423,423,517]）是三块中最右边的一块，标题为“Departures”；中间那块标题为“Salidas”（同样是出发）。“the departure screen on the left”不能唯一指出它。值“blue and white”也含糊，因为该屏幕本来就是蓝/白显示。 | Ref: Change the background color of the rightmost of the three flight-information screens on the left to green.<br>No-ref: Change the background color of the selected screen to green.<br>ZH: 将左侧三块航班信息屏中最右侧屏幕的底色改为绿色。 | 目视 |
| U3 | 严重 | 指代歧义 | ref+box | Remove the green departure sign above the hall. | REF 称被 mask 的标志(box [433,291,528,377])为 'green departure sign'。它实际上是灰色的值机标志,写着 'Gepäckaufgabe / Check-in / Facturación 13-17',只有一小块绿色数字牌。中央的大型头顶标志字面上写的是 'Abflug / Departures / Salidas',所以仅看 ref 的读者会选错标志。 | Ref: Remove the small gray check-in sign with the green '13-17' panel on the upper left wall.<br>ZH: 移除左上墙面上带绿色“13-17”数字块的灰色值机指示牌。 | 目视 |

#### `v2-sa_7374523`（#924，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | mask 质量 | ref+none | Change the color of the purple costume on the central performer to deep blue. | U1 'purple costume' mask 只覆盖紫色上衣（竹乐器周围 8 个碎片）；同一套服装配套的紫色裤子没有被 mask，因此对 'the costume' 换色与 mask 冲突。 | Ref: Change the color of the purple shirt of the central performer to deep blue.<br>No-ref: Change the color of the selected shirt to deep blue.<br>或扩展 mask 以包含紫色裤子 | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the black costume on the person behind the performer with a white costume. | U2 是一件黑色衬衫/服装上衣；'a white costume' 只是同一衣物类别的改色。 | Ref: Replace the black shirt on the person behind the performer with a white hooded raincoat.<br>No-ref: Replace the selected costume with a white hooded raincoat.<br>或改写为属性：把颜色改为白色 | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | noref+box | Remove the thatched roof in the upper right. | U3 移除了背景中一间小屋的茅草屋顶(mask 被一片棕榈叶分成两大块);移除建筑的屋顶属于大型结构移除,结果不确定(无屋顶的建筑或露出看不见的区域)。 | Ref: Change the color of the thatched roof in the upper right to dark gray.<br>No-ref: Change the color of the selected roof to dark gray.<br>将操作由 remove 改为 attribute | 目视 |
| U4 | 轻微 | 指代类别与 mask 不符 | ref+point | Add a blue ribbon on the straw broom beside the performer. | U4 物体是挑在杆子上的一捆扎好的稻草，不是扫帚。 | Ref: Add a blue ribbon on the bundle of rice straw beside the performer.<br>No-ref: Add a blue ribbon on the selected straw bundle. | 目视 |

#### `v2-sa_738866`（#926，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the white coat on the woman near the center with a yellow coat. | U2 是女子的白色连帽羽绒服;“replace with a yellow coat”仍属同一衣物类别,仅改变颜色。 | Ref: Replace the white coat on the woman near the center with a red plaid wool poncho.<br>No-ref: Replace the selected coat with a red plaid wool poncho.<br>或转换为 attribute:将外套颜色改为黄色 | 目视 |
| U3 | 严重 | 指代歧义 | ref+point | Change the color of the metal railing across the water to dark green. | U3 mask 只是右下角石柱右侧的一小段绿色栏杆（box [1841,1216,2250,1500]）；REF 'the metal railing across the water' 并不描述它（它在前景，而不是水对面），同样适用于石柱左侧人们站立处的长绿色栏杆段。 | Ref: Change the color of the green railing segment to the right of the stone pillar in the lower-right corner to dark green.<br>栏杆本身已经是绿色；考虑使用更明确的值，例如 'bright red' | 目视 |
| U3 | 严重 | 属性值问题（无变化/含糊） | ref+point | Change the color of the metal railing across the water to dark green. | 栏杆本来就是柔和的绿色；“dark green”几乎是无操作的变化，评判者无法可靠验证。 | Ref: Change the color of the green railing segment to the right of the stone pillar in the lower-right corner to bright red.<br>No-ref: Change the color of the selected railing to bright red. | 目视 |

#### `v2-sa_7429655`（#928，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 属性值问题（无变化/含糊） | ref+point | Change the color of the dark SUV behind the sedan to white. | REF/ZH 称轿车后面的 SUV 为 'dark'，但被 mask 的吉普式 SUV（box [1331,860,1608,1131]）是浅银/香槟色；把它改成白色几乎看不出来，且描述有误。 | Ref: Change the color of the silver SUV behind the sedan to dark red.<br>No-ref: Change the color of the selected SUV to dark red.<br>ZH: 将轿车后方的银色SUV的颜色改为深红色。 | 目视 |

#### `v2-sa_7532719`（#937，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the large bin at the right with a blue recycling bin. | U2 mask 是带蓝色盖子的深灰色轮式街道垃圾箱(box [1409,828,1728,1161]);“a blue recycling bin”是同一类别的物体,因此该编辑基本上是重新着色。 | Ref: Replace the large bin at the right with a stack of three cardboard boxes.<br>No-ref: Replace the selected bin with a stack of three cardboard boxes.<br>或转换为 attribute:将右侧大垃圾箱的颜色改为蓝色 | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | ref+point | Remove the building behind the truck. | U3 移除的是 'the building behind the truck' —— 一栋多层公寓楼（box [1172,280,1482,567]），其下部被卡车遮挡；按协议，移除整栋大楼是不合理的。 | Ref: Add a green awning above the top-floor balcony of the building behind the truck.<br>No-ref: Add a green awning above the top-floor balcony of the selected building.<br>更改 op，或针对可移除的部件（例如移除卫星天线/阳台栏杆） | 目视 |
| U4 | 严重 | 指代歧义 | noref+point | Add a small awning on the building at the right. | U4 mask 只是第二辆垃圾车上方可见的一栋建筑的顶部条带（box [1538,498,1783,645]）；更靠右处（x>1800）还有几栋其他建筑，所以“the building at the right”有歧义，并且由于只能看到屋顶线，遮阳篷的位置也不明确。 | Ref: Add a small awning above the top-floor window of the building visible above the second garbage truck.<br>No-ref: Add a small awning above the top-floor window of the selected building. | 目视 |

#### `v2-sa_754509`（#939，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+box | Change the color of the coat on the person left of center to olive green. | “the coat on the person left of center”适用于中心偏左的许多人(金发穿黑大衣的女子、书桌旁穿深色夹克的男子、围围巾的女子)。被 mask 的衣物是站在栅栏旁的黑发者的黑色皮夹克(box x 957-1058)。 | Ref: Change the color of the black leather jacket on the dark-haired person standing by the fence, left of center, to olive green.<br>No-ref: Change the color of the selected jacket to olive green. | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the backpack on the person right of center with a black backpack. | 被 mask 的物体是穿灰色连帽衫的步行者背的青绿色背包；'a black backpack' 是相同的物体类型，只改变颜色。REF 'the person right of center' 也较弱：背红色背包的人就紧靠左边。 | Ref: Replace the teal backpack on the person in the gray hoodie right of center with a brown leather messenger bag.<br>No-ref: Replace the selected backpack with a brown leather messenger bag.<br>或改为属性：'Change the color of the teal backpack ... to black.' | 目视 |
| U4 | 严重 | 指代歧义 | ref+box | Add a flower box on the window on the upper facade. | “the window on the upper facade”适用于十几个相同的上层窗户；mask 是中央立柱左侧的小矩形上层窗户（box x 1162-1227，cx=0.53）。 | Ref: Add a flower box on the small upper-floor window directly left of the third column from the left of the portico.<br>ZH: 在门廊从左数第三根柱子左侧的上层小窗户加上一个花箱。 | 目视 |

#### `v2-sa_7567802`（#941，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+point | Replace the lamp post on the right with a black post. | 'Replace the lamp post on the right with a black post'——被 mask 的物体本来就是深色路灯杆（灯头+杆身）；payload 'a black post' 只是一个颜色/近乎相同的物体，因此该编辑至多是换色且描述不足。 | Ref: Replace the lamp post on the right with a tall wooden flagpole.<br>No-ref: Replace the selected lamp post with a tall wooden flagpole. | 目视 |
| U3 | 严重 | 指代歧义 | ref+box | Remove the man near the center. | 'the man near the center' ——被 mask 的男子（box x659-697，cx=0.30W）站在中央雕像左侧，旁边还有另外两名男子（约 0.27-0.29W）；他并不靠近图像中心，也未被唯一确定。 | Ref: Remove the man with a white shirt and shoulder bag standing behind the benches left of the statue, rightmost of the three men there. | 目视 |
| U4 | 严重 | 指代歧义 | noref+mask | Add a roof sign on the car at the left. | “the car at the left”——左侧停着许多汽车(约 0.05-0.13W 处的一排);被 mask 的是树后 0.18W 处的一辆黄绿色小型掀背车。 | Ref: Add a roof sign on the small yellow car behind the trees at the left.<br>ZH:在左侧树后的小黄色轿车加上一个车顶标志。 | 目视 |

#### `v2-sa_7620275`（#943，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 属性值问题（无变化/含糊） | noref+point | Change the finish of the iron fence at the lower left to matte black. | 左下角的栅栏本来就是深灰/黑色金属网，所以 "matte black" 几乎没有可见变化。mask 还覆盖了整个面板区域，包括透过网眼看到的植物。 | Ref: Change the color of the iron fence at the lower left to dark green.<br>No-ref: Change the color of the selected fence to dark green. | 目视 |
| U2 | 严重 | 指代歧义 | ref+box | Replace the decorative item near the lower center with a ceramic planter. | "the decorative item near the lower center" 在摆满几十件装饰品的店面里非常含糊。mask 是店门右侧搁架上一只装白花的编织柳条篮（box 881-998 x 963-1048）。 | Ref: Replace the wicker basket of white flowers on the shelf just right of the shop door with a ceramic planter.<br>No-ref: Replace the selected basket with a ceramic planter.<br>scope=basket | 目视 |
| U3 | 严重 | 指代歧义 | noref+mask | Remove the potted plant near the center. | 中心周围出现许多盆栽植物(架子上的雏菊、沿街的花盆)。该 mask 是门廊屋顶右侧下方悬挂植物的红色花盆(box 1010-1096 x 625-734)。 | Ref: Remove the hanging red flower pot under the right side of the wooden porch roof. | 目视 |
| U4 | 严重 | 指代歧义 | ref+none | Add a blue plaque on the small sign on the facade. | "the small sign on the facade" 符合店面上的许多小标牌和牌匾。mask 是悬挂在店门右侧柱子上的一块白色手绘小标牌（box 1057-1106 x 950-999）。给标牌添加 "a blue plaque on" 的宿主/载荷搭配也很奇怪。 | Ref: Add a small blue sticker on the small white hand-painted sign hanging on the post right of the shop door.<br>No-ref: Add a small blue sticker on the selected sign. | 目视 |

#### `v2-sa_7628589`（#944，扩充 #869–#944，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 属性值问题（无变化/含糊） | ref+mask | Change the color of the costume on the foreground dancer to deep red. | 前景舞者的弗拉门戈服装已经是亮红色；“change ... to deep red”几乎察觉不到变化，使该编辑近乎无操作且难以评分。 | Ref: Change the color of the red flamenco dress of the foreground dancer to royal blue.<br>No-ref: Change the color of the selected costume to royal blue.<br>ZH: 改为宝蓝色 | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the green dress near the center with a blue dress. | U2 绿色连衣裙 -> 'a blue dress' 只是同一类别内的颜色变化。 | Ref: Replace the green dress near the center with a white blouse and a long navy skirt.<br>No-ref: Replace the selected dress with a white blouse and a long navy skirt.<br>or recast as attribute: change the color of the green dress to blue | 目视 |
| U3 | 严重 | 指代歧义 | ref+point | Remove the sign at the upper right. | 'the sign at the upper right'——U3 是位于 0.66W,0.14H 的一个很小的模糊圆形蓝/红交通标志；更靠右上（~0.93W,0.12H）还有一个更大的圆形黄色标志。 | Ref: Remove the small round blue-and-red no-parking sign behind the dancer's head. | 目视 |
| U4 | 严重 | 多单元同一物理对象/相互冲突 | noref+point | Add a gold buckle on the sandal near the bottom. | U4 凉鞋（cx=0.76W, cy=0.77H）在绿裙女子腿部正下方的脚上，也就是穿着 U2 裙子的同一个人身上。 | 去掉 U4，或选另一个人的凉鞋（例如左边穿花裙的女子） | 目视 |

#### `v2-sa_7639254`（#945，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 严重 | 指代歧义 | ref+none | Remove the firefighter in the foreground. | U3 mask 的是撞毁汽车旁手持杆子、穿黄色高可见度服装的站立救援人员(box [920,628,1166,998])。前景约有十名消防员和急救人员(深色和黄色制服)在作业,因此“the firefighter in the foreground”无法识别他。他穿的也是急救员式的黄色服装,而不是消防员的深色装备。 | Ref: Remove the standing rescuer in a yellow hi-vis suit holding a pole at the right side of the crashed car.<br>No-ref: Remove the selected rescuer. | 目视 |
| U4 | 严重 | 指代歧义 | ref+mask | Add a small bird on the tree at the upper right. | U4 mask 的是白色救护车上方山坡上的一棵茂密落叶树（box [1624,79,1896,373]），但整个上部区域是森林，右上方有许多树。 | Ref: Add a small bird on the bushy leafless-topped tree directly above the white ambulance at the upper right. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+mask | Add a small bird on the tree at the upper right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_7643197`（#946，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 属性值问题（无变化/含糊） | noref+box | Change the color of the figurine on the left to blue. | U1 站立的小人偶是多色的（黑发、白衬衫、深色裤子、肤色）；“change the color of the figurine to blue”没有说明哪个涂装部分变化。 | Ref: Change the color of the white shirt of the standing figurine on the left to blue.<br>或保持整个人偶的范围，但写明 'paint the whole figurine blue' | 目视 |
| U2 | 严重 | 指代歧义 | ref+point | Replace the figurine near the lower center with a wooden figure. | U2 mask 是穿橙色衬衫和绿色长裤的弯腰小人偶(从左数第二个,cx=0.35W)。所有弯腰人偶站得一样高;'the figurine near the lower center' 至少同样符合穿粉色或蓝色衬衫的人偶(更接近 x=0.5)。正式输入 ref+point 依赖 REF。 | Ref: Replace the bent-over figurine in the orange shirt and green trousers with a small stone lion statue.<br>No-ref: Replace the selected figurine with a small stone lion statue. | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the figurine near the lower center with a wooden figure. | 把一个弯腰男孩的彩绘小雕像替换为 'a wooden figure'（同一类别，姿势未指定）本质上是材质变化。 | Ref: Replace the bent-over figurine in the orange shirt and green trousers with a small stone lion statue.<br>No-ref: Replace the selected figurine with a small stone lion statue.<br>或改为属性编辑：将小雕像的材质改为雕刻木材 | 目视 |
| U3 | 严重 | mask 质量 | noref+point | Remove the figurine on the right. | U3 mask（最右边的小人偶：绿衬衫、蓝牛仔裤）有 3 个组件；除了该人偶外，还包含了原图 x~1420-1580, y~1190-1410 处米色裤腿和黑色鞋子的不规则碎片，它们属于相邻的蓝衬衫人偶。 | 去掉 U3 mask 左边的米色裤腿/鞋子碎片；只保留绿衬衫/蓝牛仔裤的人偶 | 目视 |

#### `v2-sa_7685764`（#950，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 属性值问题（无变化/含糊） | noref+point | Change the color of the lamp post at the right to black. | 右侧的 U1 灯杆本来就是深色(黑色/深绿色铸铁);'change the color to black' 几乎看不出变化。 | Ref: Change the color of the lamp post at the right to gold.<br>No-ref: Change the color of the selected lamp post to gold. | 目视 |
| U2 | 严重 | 指代歧义 | ref+box | Replace the cyclist near the lower left with a pedestrian. | 左下附近有两名骑行者驶离：一位穿深色衣服，约在 0.22W，被 mask 的那位穿蓝色夹克，在 0.28W（box [603,989,679,1175]）。'the cyclist near the lower left' 对两者都适用（深色那位甚至更靠左）。 | Ref: Replace the cyclist in a blue jacket riding toward the red museum building with a pedestrian. | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | noref+mask | Remove the building on the right. | U3 mask（box [1431,71,1744,944]，面积 4.3%）是整座克里姆林宫角楼（带绿色尖顶的巨大砖塔）；移除整座大型地标建筑是不适定的修复任务。另外 'the building on the right' 有歧义：更靠右的黄色军械库建筑也是右侧的建筑。 | Ref: Remove the red star-less green-roofed spire top of the round brick tower on the right.<br>宜改用属性：'Change the color of the green spire roof of the round red brick tower to gold.'；或删除该单元 | 目视 |

#### `v2-sa_7711079`（#952，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 属性值问题（无变化/含糊） | ref+box | Change the color of the building on the right to warm beige. | 该建筑本来就有大片米色石板区域（右侧街区和下部立面），紧邻深灰色板边。'Change the color of the building to warm beige' 只会产生部分可见变化，且不清楚哪些表面应当改变。 | Ref: Change the color of the dark gray floor slabs and facade of the building on the right to white. | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the bench at the lower left with a wooden bench. | 被 mask 的物体是一把石质/混凝土块长椅。将其替换为 'a wooden bench' 保持类别，仅改变材质。mask 还包含了躺在长椅旁的独立大石头（U2 放大图）。 | Ref: Replace the stone bench at the lower left with a round metal bistro table.<br>No-ref: Replace the selected bench with a round metal bistro table.<br>或转为属性：'Change the material of the stone bench at the lower left to wood.' 并从 mask 中去掉大石头。 | 目视 |
| U3 | 严重 | 指代歧义 | ref+none | Remove the chair near the lower center. | 被 mask 的椅子(x~0.28W,面积极小 0.0004)是绿篱旁小桌周围一组相同白色户外椅中的一把,且位于中心偏左而不是“near the lower center”。REF 无法将其单独指出。 | Ref: Remove the leftmost white outdoor chair in the group of chairs beside the hedge, left of the pool. | 目视 |

#### `v2-sa_7753369`（#956，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| case | 严重 | 多单元同一物理对象/相互冲突 |  |  | U2 扩音器（box [744,687,867,855]）被举到 U3 要求移除的那个人的脸前（box [667,622,908,1417]）；U3 mask 围绕扩音器裁切。两项编辑在物理上相互耦合：移除该男子会让（被替换的）扩音器悬空。 | 删除 U3（移除人物）或删除 U2；或选择不同的人物/物体，使各单元相互独立 | 目视 |
| U3 | 严重 | 指代歧义 | noref+box | Remove the person at the left. | “the person at the left”适用于多个人：最左侧举着 IMPEACH 标牌的男子、左边缘穿黑夹克的人，以及被 mask 的拿扩音器的男子（cx=0.35）。mask 是戴红帽、穿藏青色夹克拿着扩音器的男子。 | Ref: Remove the man in the red cap and navy jacket walking toward the camera.<br>ZH: 移除戴红帽、穿藏蓝夹克朝镜头走来的男子。 | 目视 |
| U4 | 严重 | 指代歧义 | ref+point | Add a white emblem on the flag near the center. | U4 mask 是背景白色建筑上的一面很小的美国国旗(box [1002,508,1031,564]);中心附近(扩音器男子后方)举着一面大得多的美国国旗,附近还有其他小旗,所以 'the flag near the center' 有歧义。另外,在已经有白色星星的美国国旗上加 'white emblem' 难以验证。 | Ref: Add a white emblem on the small flag flying from the white building in the background.<br>consider a more distinctive payload (e.g. 'a small yellow fringe along its edge') | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a white emblem on the flag near the center. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_7757919`（#957，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 属性值问题（无变化/含糊） | noref+point | Change the color of the airplane in the center to silver. | 这架无人机本来就是中灰色；改为 'silver' 是非常细微的变化，难以验证。 | Ref: Change the color of the airplane in the center to white.<br>No-ref: Change the color of the selected airplane to white. | 目视 |
| U2 | 轻微 | 指代歧义 | ref+box | Replace the traffic barrel at the left with a yellow cone. | 左侧并排放着两个相同的黄黑条纹桶/配重块（x~0.05-0.11W）；被 mask 的是这对中右边那个，但 REF 只说了 'the traffic barrel at the left'。 | Ref: Replace the right one of the two striped barrels at the left with a yellow cone. | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | noref+mask | Remove the display stand at the lower left. | U3 mask(box 592-823 x,1246-1407 y)是直接支撑灰色导弹模型前部的黑色三角形支架;移除它会使导弹头悬空无支撑。轮廓也紧贴导弹头的下侧。 | 改用 attribute,例如“Change the color of the display stand under the nearest missile at the lower left to red.”,或选择独立放置的物体。 | 目视 |

#### `v2-sa_7805976`（#961，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+mask | Change the color of the car at the lower left to red. | U1 mask = 白色掀背车（box [0,1457,391,1666]）。紧挨其正前方/下方的最左下边缘处部分可见一辆深灰色汽车，那才是字面意义上的左下；左侧还停着其他几辆汽车。“the car at the lower left”不唯一。 | Ref: Change the color of the white hatchback parked on the left side of the street to red. | 目视 |
| U2 | 严重 | 指代歧义 | ref+none | Replace the car at the right with a blue sedan. | U2 mask = 红色大众两厢车(box [1228,1455,1500,1698])。更靠右、更靠近镜头的右边缘停着一辆深色车,与其部分重叠,所以 "the car at the right" 至少同样符合那辆深色车。Payload "a blue sedan" 也接近对相似车辆的改色。 | Ref: Replace the red hatchback parked on the right side of the street with a blue pickup truck.<br>No-ref: Replace the selected car with a blue pickup truck. | 目视 |
| U3 | 严重 | 指代歧义 | ref+mask | Remove the balcony on the left. | U3 mask = 左侧公寓楼上的一个阳台（从上数第二个，box [7,279,184,509]），那里有一排几乎相同的阳台（上方和下方有好几个）。"the balcony on the left" 无法确定是哪一个。 | Ref: Remove the second balcony from the top on the building at the left edge.<br>ZH: 移除左侧边缘建筑从上往下第二个阳台。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a street sign on the utility pole near the center. | U4 mask 是一根路灯杆（顶部有弯臂），上面已经挂着蓝色 P 停车标志；称其为 "utility pole" 并要求添加 "a street sign" 略显宽泛。 | Ref: Add a green street-name sign on the street lamp post near the center.<br>No-ref: Add a green street-name sign on the selected pole. | 目视 |

#### `v2-sa_7833331`（#963，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 属性值问题（无变化/含糊） | ref+none | Change the color of the truck in the foreground to dark blue. | 前景卡车是白色箱体，带蓝色围栏，上面装着箱子和水桶。'Change the color of the truck to dark blue' 没有说明是哪一部分（白色车厢还是蓝色围栏），且 mask 包含了货物。 | Ref: Change the color of the white body panels of the delivery truck in the foreground to dark blue. | 目视 |
| U2 | 严重 | 编辑不合理/不可执行 | ref+mask | Remove the building behind the truck. | U2 'Remove the building behind the truck' 针对的是占据右上背景的整栋白色商业建筑（box [1110,0,2250,784]，占图像 15%）。mask 是碎裂的（3 个组件，电线杆和最右侧立面周围有斑点），并且留下了店面和行人。移除整栋建筑是不适定的。 | 删除 U2，或改为小物体，例如电线杆或店面上方的红色店招 'Rosario Hogar' | 目视 |

#### `v2-sa_7850865`（#965，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代歧义 | noref+mask | Change the color of the flag at the upper left to blue. | 左半边飘着几面相似的绿色 'Gernsbach' 旗(如 ~x=400, y=330 和 ~x=350, y=400);U1 是 cx=0.37 处最高的那面,所以 'the flag at the upper left' 只有松散的区分性。 | Ref: Change the color of the highest green flag, on the tall pole left of center, to blue. | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the metal planter at the lower right with a stone planter. | U2 将金属花盆箱替换为 'a stone planter'——同一物体类别，只改变材质。 | Ref: Change the material of the metal planter at the lower right to gray stone.<br>No-ref: Change the material of the selected metal planter to gray stone.<br>op replace->attribute，或替换为结构不同的物体（例如 'a wooden park bench'） | 目视 |
| U3 | 严重 | 编辑不合理/不可执行 | ref+mask | Remove the building at the left. | U3 移除 'the building at the left'，一栋占据背景的大型多层房屋（box 244-622 x 535-831）；移除整栋建筑会留下无定义的背景。mask（2 个组件）中间还有一道竖直缝隙（旗杆），并且跨越了两个相邻的立面。 | Ref: Change the color of the roof of the building at the left to dark gray.<br>或将 replace 操作改为在立面上的 add（例如在一层商铺上方添加条纹遮阳篷） | 目视 |

#### `v2-sa_7944519`（#968，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 属性值问题（无变化/含糊） | noref+point | Change the color of the blossom cluster at the lower left to pale pink. | 左下角的花簇（box [453,921,695,1157]）已经是鲜艳的粉色；将其改为“pale pink”几乎察觉不到变化，难以评判。 | Ref: Change the color of the blossom cluster at the lower left to white.<br>No-ref: Change the color of the selected blossom cluster to white.<br>ZH: 白色 | 目视 |
| U2 | 轻微 | 指代歧义 | ref+box | Remove the carving near the center. | "the carving near the center" 含糊;可见多块雕花木板(左上花朵后面,以及主梁下方钟周围)。被 mask 的是梁上方顶部中央的云纹雕花板。 | Ref: Remove the cloud-pattern wooden carving at the top center above the main beam.<br>none | 目视 |

#### `v2-sa_8060797`（#976，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+box | Replace the carving on the left with a painted ornament. | U2 将左侧柱子上的雕花面板（box [575,427,709,930]）替换为 'a painted ornament' ——这是同一装饰面板的表面/材质风格变化，且 payload 含糊。 | Ref: Replace the carving on the left with a small brass oil lamp mounted on the pillar.<br>No-ref: Replace the selected carving with a small brass oil lamp mounted on the pillar.<br>或改为属性：把左侧雕刻的颜色改为金色 | 目视 |

#### `v2-sa_8066140`（#978，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+box | Replace the sign at the left with a yellow sign. | 'Replace the sign at the left with a yellow sign' —— 被 mask 的物体是红白相间的禁止抛锚标志;payload 只指定了颜色(同一类别),所以是内容未定义的改色。 | Ref: Replace the red no-anchoring sign on the quay wall at the left with a round blue life-buoy holder.<br>No-ref: Replace the selected sign with a round blue life-buoy holder.<br>or attribute: Change the color of the red border of the no-anchoring sign at the left to yellow. | 目视 |
| U3 | 严重 | 指代歧义 | noref+mask | Remove the balcony near the upper center. | 'the balcony near the upper center'——立面上有许多阳台；被 mask 的是位于 ~0.68W 处奶油色建筑上层的一个长铁艺阳台，并不在中心，附近还有其他上层阳台（例如右侧建筑 ~0.9W 处）。 | Ref: Remove the long wrought-iron balcony on the upper floor of the cream building right of center, above the trees. | 目视 |
| U4 | 严重 | 指代歧义 | ref+none | Add a flower box on the dormer near the upper left. | 'the dormer near the upper left' ——左上的复折屋顶有一排约 6 个相同的老虎窗；被 mask 的是那排最右边的一个（约 0.25W）。 | Ref: Add a flower box on the rightmost dormer of the grey mansard roof at the upper left. | 目视 |

#### `v2-sa_8336561`（#988，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| case | 严重 | 多单元同一物理对象/相互冲突 |  |  | U1 赌桌 mask 覆盖整个毛毡台面，包括其上的扑克牌和筹码；U3 牌（box 432-634 x 1808-1872）位于 U1 mask 内部而没有孔洞，因此两个单元的 mask 重叠。 | 从 U1 桌子 mask 中抠除牌和筹码（至少是 U3 的牌），使 mask 不重叠。 | 目视 |
| U1 | 轻微 | 方位/序数/实例指代错误 | ref+none | Change the color of the casino table at the left to dark green. | 被 mask 的二十一点牌桌横跨图像整个底部（box 宽 0-1500）；它是前景牌桌，不是“at the left”的那张。唯一的另一张桌子（绿色，背景右侧）不会混淆，但空间词是错的。 | Ref: Change the color of the red felt of the blackjack table in the foreground to dark green. | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the bag at the right with a black handbag. | 在原图裁剪中,被 mask 的包(x 1366-1434,面积极小 0.0009)本来就是穿棕褐色上衣的背景女子背的黑色单肩包。将其替换为 'a black handbag' 基本看不出变化。 | Ref: Replace the black shoulder bag of the woman in the background at the right with a red straw tote bag.<br>No-ref: Replace the selected bag with a red straw tote bag. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a small badge on the shirt at the upper left. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_83477`（#990，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 属性值问题（无变化/含糊） | ref+mask | Change the color of the car in the center to blue. | Carabinieri 警车已经是深海军蓝；“change the color ... to blue”几乎是无操作。 | Ref: Change the color of the car in the center to red.<br>No-ref: Change the color of the selected car to red. | 目视 |
| U3 | 严重 | 方位/序数/实例指代错误 | ref+point | Remove the fence at the front. | 'the fence at the front' —— 奶油色尖桩篱笆在背景中,位于车后/左侧,而不在前面。 | Ref: Remove the cream picket fence behind the car at the left. | 目视 |

#### `v2-sa_8359156`（#992，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | mask 质量 | ref+mask | Replace the banana plant above the truck with a palm tree. | U2 mask(box [1145,69,1583,437])只覆盖了伸出 IBC 罐上方的香蕉植株最上面两片叶子;同一株香蕉的大下叶位于卡车驾驶室右侧(合成图约 x=1250-1550,y=230-560)且未被 mask,因此“Replace the banana plant ... with a palm tree”只针对该植株的一个片段。 | 将 mask 扩展到完整可见的香蕉植株(驾驶室右侧的叶子),或改写为“the banana leaves above the tank” | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a small bird on the tree at the upper right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8364504`（#994，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代类别与 mask 不符 | ref+mask | Change the color of the banner at the left to blue. | U1 mask 是左侧杆子上的韩国国旗（太极旗），但 REF 称其为 'the banner'；而且对多色旗帜（白底、红蓝圆、黑色卦象）'change the color ... to blue' 没有说明改变哪一部分。 | Ref: Change the color of the white field of the South Korean flag at the left to light blue.<br>No-ref: Change the color of the white field of the selected flag to light blue.<br>scope 用 'flag' 而不是 'banner'；ZH: 将左侧韩国国旗的白色底色改为浅蓝色。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the flag near the center with a white flag. | 被 mask 的物体是大门附近带黄色星形徽记的高大蓝旗；'a white flag' 只是在同一旗帜类别/形状内改变颜色。 | Ref: Replace the blue flag near the center with a red paper lantern hanging from the pole.<br>No-ref: Replace the selected flag with a red paper lantern hanging from the pole.<br>或转为属性：'Change the color of the blue flag near the center to white.' | 目视 |
| U3 | 严重 | 指代歧义 | ref+point | Remove the person at the right. | “the person at the right”——右边缘站着两个人:被 mask 的穿米色外套、戴渔夫帽的女子(box x 2113-2211),以及更靠右、被画面部分截断的穿蓝色夹克、戴白帽的人(真正最右侧的人)。 | Ref: Remove the woman in a beige jacket and bucket hat at the right.<br>ZH:移除右侧穿米色外套、戴渔夫帽的女子。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a blue logo on the information board at the lower left. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8364627`（#995，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+box | Change the color of the door near the center to dark green. | 'the door near the center' —— 被 mask 的窄白门在 0.63W；约 0.47W 的玻璃白门更靠近中心，因此 REF 可能绑定到错误的门。 | Ref: Change the color of the narrow white door under the small arched window, right of the dark shutter, to dark green. | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the door at the right with a red door. | “Replace the door at the right with a red door”保持类别；只有颜色变化。此外“at the right”有歧义：更靠右的大型拱形白色双开门（~0.78W）和另一扇窄门（~0.71W）都在附近。 | Ref: Replace the narrow white door left of the arched double door at the right with a red brick wall section.<br>No-ref: Replace the selected door with a red brick wall section.<br>或 attribute：Change the color of the narrow white door left of the arched double door to red. | 目视 |
| U3 | 轻微 | 指代歧义 | ref+none | Remove the sign above the street. | 'the sign above the street' 含糊;还有 LE COMPTOIR 遮阳篷和一块悬挂的小 ANTIQUITES 招牌。被 mask 的是大的 ANTIQUITES 招牌。 | Ref: Remove the large ANTIQUITES sign above the awning. | 目视 |
| U4 | 严重 | 指代歧义 | ref+mask | Add a small emblem on the manhole cover below. | 'the manhole cover below'——人行道上至少可见四个排水/检修井盖；被 mask 的是左下方 LE COMPTOIR 店面旁边的那个（x836-958）。 | Ref: Add a small emblem on the drain cover at the base of the wall next to the LE COMPTOIR shopfront. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+mask | Add a small emblem on the manhole cover below. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8382869`（#997，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | mask 质量 | noref+mask | Change the color of the sign at the left to blue. | 并排挂着两个相同的“CALL ROOM”标志;U1 mask 只覆盖左边那个,但存储的 box [951,527,1325,639] 横跨两个标志,因此 box 定位器与 mask 不一致。REF “the sign at the left”较弱,因为该标志位于 0.45W。 | Ref: Change the color of the left one of the two CALL ROOM signs to blue.<br>根据 mask 重新计算 box(约 [951,527,1090,639]) | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the door near the center with a red door. | U2 是白框玻璃门；'a red door' 只是颜色改变。 | Ref: Replace the glass door near the center with a solid red wooden door.<br>No-ref: Replace the selected door with a solid red wooden door. | 目视 |
| U3 | 严重 | 指代歧义 | ref+mask | Remove the chair near the lower center. | U3 是透过敞开门洞可见的众多深绿色塑料椅之一（0.55W,0.68H）；“the chair near the lower center”不能唯一指出它。 | Ref: Remove the dark green plastic chair just inside the open doorway, behind the front chair. | 目视 |
| U4 | 严重 | 方位/序数/实例指代错误 | noref+box | Add a cushion on the chair at the lower right. | U4 椅子在门口 0.58W,0.72H 处,不在图像右下方;里面还有几把其他椅子也可能符合。 | Ref: Add a cushion on the front dark green plastic chair in the open doorway. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a cushion on the chair at the lower right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8405850`（#1000，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 属性值问题（无变化/含糊） | noref+point | Change the color of the semi-truck in the center to blue. | 半挂卡车的驾驶室是银色，挂车本来就涂有蓝色板块/波浪图案；'change the color of the semi-truck to blue' 范围不清（只是驾驶室？包括装饰的整个挂车？）且部分是无操作。 | Ref: Change the color of the silver cab of the semi-truck in the center to blue.<br>或选择红色这类对比色应用于整个卡车车身。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+box | Replace the building at the left with a brick facade. | 目标是左侧被部分遮挡的白色商业建筑（box x0-689）。'Replace the building ... with a brick facade' 只改变墙面材质（属性），而且替换整栋建筑属于大型结构编辑；payload 'facade' 不是建筑级别的物体。 | Ref: Change the exterior material of the building at the left to red brick.<br>No-ref: Change the exterior material of the selected building to red brick.<br>operation replace -> attribute (property=material, value=red brick) | 目视 |

#### `v2-sa_8425235`（#1001，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代歧义 | ref+mask | Change the color of the lamp post at the left to black. | U1 是 cx=0.33 处非常高的桅杆灯;更靠左还有其他灯杆/标志杆,因此“the lamp post at the left”表述不够准确。 | Ref: Change the color of the tall mast lamp post rising above the buildings left of center to black. | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the coat near the center with a blue coat. | U2 把女子的黑色外套替换为 'a blue coat' —— 只是颜色改变。 | Ref: Change the color of the black coat of the dark-haired woman walking away near the center to blue.<br>No-ref: Change the color of the selected coat to blue.<br>op replace->attribute（或替换为不同衣物，例如 'a beige trench coat' 仍然是外套；建议用 'a red puffer vest'） | 目视 |
| U2 | 严重 | 指代歧义 | noref+box | Replace the coat near the center with a blue coat. | “the coat near the center”太泛：中心附近几个行人都穿大衣/夹克（x~520 处穿蓝夹克的男子、x~340 处穿深色夹克的男子）；被 mask 的是 cx=0.59 处背身走远的深发女士的黑色大衣。 | Ref: Replace the black coat of the dark-haired woman walking away from the camera, right of center, with a red puffer vest. | 目视 |
| U4 | 严重 | 指代歧义 | noref+point | Add a white arrow on the sign at the far left. | 最左侧一根杆子上有一摞白色方向标志('Kabataş Beşiktaş'、'Fatih Yenikapı'、'Sirkeci Unkapanı',以及蓝色标志)。U4 只 mask 了 'Fatih Yenikapı' 这块;'the sign at the far left' 符合其中任何一块。 | Ref: Add a white arrow on the 'Fatih Yenikapı' direction sign on the pole at the far left. | 目视 |

#### `v2-sa_8429220`（#1002，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | 指代类别与 mask 不符 | noref+mask | Replace the fabric at the lower left with a blue cloth. | REF 称目标为 'the fabric at the lower left'，但 mask（box [485,1181,636,1397]，被栅栏横杆分成 3 个分量）是坐在栅栏后一名男子所穿的条纹衬衫/衣物；它是人身上的衣服，不是散放的织物。 | Ref: Change the color of the striped shirt of the man sitting behind the fence at the lower left to blue.<br>No-ref: Change the color of the selected shirt to blue.<br>将 scope 重命名为 shirt 并转为 attribute | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the fabric at the lower left with a blue cloth. | 'Replace the fabric ... with a blue cloth' 保持同一类别（布）；仅改色。 | Ref: Change the color of the striped shirt of the man sitting behind the fence at the lower left to blue.<br>No-ref: Change the color of the selected shirt to blue. | 目视 |

#### `v2-sa_8543461`（#1008，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+mask | Change the color of the small car at the right to red. | 右侧堤岸边停着一排小汽车；“the small car at the right”适用于多辆。被 mask 的 [2034,568,2106,602] 是红色汽车之间的白色掀背车。 | Ref: Change the color of the small white car parked between the red cars at the right along the embankment to red. | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the large sign at the upper left with a blue sign. | 被 mask 的物体是工厂广告牌内红白相间的椭圆形标志牌;payload 'a blue sign' 只改变颜色。 | Ref: Replace the oval logo sign in the middle of the large rooftop billboard with a round analog clock.<br>No-ref: Replace the selected sign with a round analog clock.<br>Or convert to attribute color=blue. | 目视 |
| U2 | 严重 | 指代歧义 | noref+box | Replace the large sign at the upper left with a blue sign. | 'the large sign at the upper left' 更自然地指整块深红色屋顶广告牌（带 '1851' 和西里尔文字）；mask [747,252,1025,405] 只是其中央的椭圆形标志牌，位于 x~0.39（上方偏中左）。 | Ref: Replace the oval logo sign in the middle of the large rooftop billboard with a round analog clock. | 目视 |
| U3 | 严重 | 指代歧义 | ref+point | Remove the sign at the lower right. | 被 mask 的 'sign' [1752,839,1879,880] 是白色河游船上层甲板上的小蓝色横幅，位于中等高度（cy=0.57），不在右下；图像中还有很多其他招牌。'the sign at the lower right' 无法识别它。 | Ref: Remove the blue banner on the upper deck of the white river cruise boat.<br>No-ref: Remove the selected banner. | 目视 |

#### `v2-sa_8550648`（#1009，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+box | Change the color of the window at the upper left to blue. | U1 mask(box [222,249,386,391])是砖墙立面最上方可见一排中从左数第二扇窗;其左侧在图像边缘(合成图 x~0-110,同一排)的窗户更“upper-left”,且存在许多相同的窗户,因此“the window at the upper left”有歧义。“Change the color of the window”也不清楚是对窗框还是玻璃重新着色。 | Ref: Change the color of the window frame of the second window from the left in the top row of the brick building to blue.<br>No-ref: Change the color of the selected window frame to blue. | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the bicycle at the lower right with a red bicycle. | U2 mask 是车架最右端的黄色公路自行车；'Replace ... with a red bicycle' 保持类别，只改变颜色。 | Ref: Change the color of the yellow bicycle at the lower right to red.<br>No-ref: Change the color of the selected bicycle to red.<br>将 op 改为 attribute，或替换为不同物体（例如 'an electric scooter'） | 目视 |

#### `v2-sa_8607627`（#1011，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 属性值问题（无变化/含糊） | ref+box | Change the color of the wheel near the center to black. | 被 mask 的车轮由黑色 Bridgestone 轮胎和银色合金轮辋组成;“Change the color of the wheel ... to black”对轮胎而言近乎空操作,且没有说明要改的是轮辋。 | Ref: Change the color of the silver alloy rim of the wheel near the center to matte black.<br>No-ref: Change the color of the rim of the selected wheel to matte black. | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the bucket at the lower right with a blue bucket. | 被 mask 的物体是装满零件的白/奶油色 NIPPON PAINT 桶；'a blue bucket' 保持相同物体类型，只改变颜色。 | Ref: Replace the paint bucket at the lower right with a red metal toolbox.<br>No-ref: Replace the selected bucket with a red metal toolbox.<br>或改为属性：'Change the color of the paint bucket at the lower right to blue.' | 目视 |
| U3 | 严重 | mask 质量 | ref+none | Remove the shelf at the left. | “shelf at the left”mask（box y 536-555，高 19 像素）只是机油罐货架上一块搁板的细前沿条；搁板上摆满了 LIQUI MOLY 罐子，所以只移除它是不适定的（罐子会悬空），而且“shelf”也可能指整个货架单元。 | Ref: Remove the oil cans on the lowest visible shelf of the shelving unit at the left.<br>或删除该 unit；若保留，则 mask 整块搁板 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+mask | Add a small label on the plastic bag at the right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_862087`（#1013，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 措辞/文法/描述细节 | noref+mask | Change the color of the fabric at the lower left to blue. | 左下角被 mask 的物体是一件悬挂的带粉色印花的白色T恤（陈列的衣物），而不是泛泛的 'fabric'。 | Ref: Change the color of the hanging white T-shirt at the lower left to blue.<br>No-ref: Change the color of the selected T-shirt to blue.<br>设置 scope=T-shirt。 | 目视 |
| U2 | 严重 | 指代歧义 | ref+none | Replace the small window at the left with a round window. | 左侧建筑有许多相同的小窗。“the small window at the left”不能挑出被 mask 的那个(box [268,682,361,753]):最低可见楼层、摊位篷布正上方的一扇泛绿的窗。 | Ref: Replace the small green-tinted window just above the market canopy on the left building with a round window.<br>ZH:将左侧楼房市场帐篷正上方的小绿色玻璃窗替换为一扇圆窗。 | 目视 |
| U3 | 严重 | mask 质量 | ref+mask | Remove the canopy near the center. | U3 'canopy' mask（comps=3, box [183,799,1358,1429]）覆盖白色扇贝形摊位顶篷，但也包含前面展示桌上独立的白色桌布/桌裙（约 y=1250-1430）和顶篷下悬挂的纸质通知。移除该 mask 还会移除桌布。 | Ref: Remove the white scalloped canopy of the market stall near the center.<br>重新 mask 到仅顶篷屋顶，并去掉桌布连通块。 | 目视 |
| U4 | 轻微 | 指代歧义 | noref+box | Add a red logo on the small sign near the lower center. | REF 把小灰色标牌放在“near the lower center”，但它挂在布料摊位内部，约 0.31W, 0.70H，中心偏左。可以识别，但描述较松散。 | Ref: Add a red logo on the small gray sign hanging inside the fabric stall. | 目视 |

#### `v2-sa_8631298`（#1014，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 属性值问题（无变化/含糊） | ref+point | Change the color of the white sedan at the lower left to red. | U1 左下方的轿车是香槟/米金色,不是白色;REF/ZH 称其为 'white sedan',与图像矛盾(目标按位置仍唯一)。 | Ref: Change the color of the champagne sedan at the lower left to red.<br>ZH: 将左下方的香槟色轿车的颜色改为红色。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+point | Replace the white sedan at the upper right with a blue sedan. | U2 白色轿车 -> 'a blue sedan' 只是同一类别内的颜色变化。 | Ref: Replace the white sedan parked along the fence on the right with a blue pickup truck.<br>No-ref: Replace the selected car with a blue pickup truck. | 目视 |
| U2 | 轻微 | 指代歧义 | noref+point | Replace the white sedan at the upper right with a blue sedan. | U2 位于中右（0.80W,0.44H）、围栏旁；其他白色车辆（白色皮卡约 0.92W,0.32H；围栏后的白色轿车）都在更靠上的右上方。 | Ref: Replace the white sedan parked along the fence on the right with a blue pickup truck. | 目视 |
| U4 | 严重 | 指代歧义 | noref+mask | Add a flower box on the window near the upper center. | “the window near the upper center”——建筑立面有几十扇类似的小窗;U4 是 0.34W,0.17H 处、拱形窗旁的一扇带格栅的小窗。 | Ref: Add a flower box on the small square window just left of the arched window on the white building at upper left. | 目视 |

#### `v2-sa_8671723`（#1015，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 属性值问题（无变化/含糊） | ref+none | Change the color of the boat at the right to white. | U1 船（TALAIS，box [1627,608,2002,825]）有蓝色船体和白色上层建筑。'Change the color of the boat to white' 实际指的是船体，指令应当说明这一点。 | Ref: Change the color of the blue hull of the boat at the right to white. | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the streetlight at the left with a black streetlight. | U2 mask 的是左边缘弯曲的灰/白色路灯（box [29,293,160,799]）。“Replace ... with a black streetlight”保持类别，仅改变颜色。 | Ref: Change the color of the curved streetlight at the far left to black.<br>No-ref: Change the color of the selected streetlight to black.<br>将 op 改为 attribute | 目视 |
| U3 | 严重 | 指代歧义 | noref+box | Remove the flag near the top. | U3 mask 的是屋顶旗杆上的黄红相间的日内瓦旗(box [715,28,752,97])。其正右侧同一高度飘着一面红色瑞士国旗,更右边还可见另一面旗,所以 'the flag near the top' 有歧义。 | Ref: Remove the yellow-and-red Geneva flag on the rooftop pole near the top. | 目视 |
| U4 | 严重 | 指代歧义 | ref+point | Add a small flower pot on the railing at the lower left. | U4 mask 的是码头最左端的一小段滨河栏杆（box [0,692,128,729], cy=0.47）。那是图像的垂直中部，不是左下方，而且同一栏杆沿整个码头延续。 | Ref: Add a small flower pot on the short railing section at the far left end of the waterfront promenade. | 目视 |

#### `v2-sa_8698583`（#1017，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代类别与 mask 不符 | ref+mask | Change the color of the coat near the center to blue. | U1 mask 是基座上青铜雕像（丘吉尔雕像）的长外套，不是人的衣物；REF“the coat near the center”没有说明是雕像的雕塑外套，而下方许多人（警察等）也穿着大衣。 | Ref: Change the color of the bronze coat of the statue on the stone plinth to blue.<br>ZH: 将石基座上雕像的青铜外套的颜色改为蓝色。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the streetlight at the far right with a black streetlight. | 最右侧的路灯本来就是深色(黑/深蓝)灯杆;将其替换为 'a black streetlight' 至多是改色,几乎无变化。 | Ref: Replace the streetlight at the far right with an ornate double-headed Victorian lamp post.<br>No-ref: Replace the selected streetlight with an ornate double-headed Victorian lamp post. | 目视 |
| U3 | 严重 | 指代歧义 | ref+point | Remove the window at the right. | 右边的建筑有几十扇相似的窗户；'the window at the right' 无法确定被 mask 的窗户（右边缘路灯旁的一扇小窗，box 1442-1491 x 923-1004）。从立面上移除一扇窗户的定义也很弱。 | Ref: Remove the window on the right building just right of the far-right streetlight, at the image's right edge.<br>考虑改用 attribute（例如更改窗框颜色） | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a white stripe on the shoes at the lower right. | U4 mask 是金发牛仔裤女子的一只白色运动鞋；REF 说的是 'the shoes'（复数），而且在白鞋上加白色条纹几乎看不出来。 | Ref: Add a black stripe on the white sneaker of the blonde woman walking at the lower right.<br>No-ref: Add a black stripe on the selected shoe. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a white stripe on the shoes at the lower right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_873326`（#1019，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+box | Change the color of the cow near the center to brown. | 两头白牛并排走在中间；mask（box [680,596,1679,1304]）是靠近的那一头。'the cow near the center' 对两者都适用（它们其实是瘤牛/公牛，不是母牛）。 | Ref: Change the color of the nearer of the two white oxen pulling the plow to brown.<br>No-ref: Change the color of the selected ox to brown.<br>scope cow -> ox | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+point | Replace the straw hat at the upper left with a red hat. | U2 将锥形草帽替换为 'a red hat' ——payload 只指定了颜色，没有新的帽子类型/结构。 | Ref: Replace the conical straw hat at the upper left with a red baseball cap.<br>No-ref: Replace the selected hat with a red baseball cap. | 目视 |

#### `v2-sa_8739681`（#1020，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+mask | Change the color of the stone lion near the center to dark gray. | 约十几座几乎相同的石狮环绕中央喷泉;U1 是水池中心右侧紧邻的正面朝前的狮子(box 748-878)。“the stone lion near the center”适用于好几只狮子。 | Ref: Change the color of the stone lion facing the camera directly below the right part of the fountain basin to dark gray. | 目视 |
| U2 | 严重 | 指代歧义 | ref+none | Replace the arched window at the upper left with a round window. | U2 是塔楼三联拱窗的中间开口（cx=0.42）；其两侧拱窗同样 'at the upper left'，因此 REF 无法指出中间那个。 | Ref: Replace the middle arched window of the three-arch opening in the upper tower with a round window.<br>ZH: 将上方塔楼三联拱窗中间的拱窗替换为一扇圆窗。 | 目视 |
| U3 | 严重 | 指代类别与 mask 不符 | ref+mask | Remove the stone post at the lower left. | U3 mask 是带圆形底座的细黑色金属围栏支柱（stanchion），不是“stone post”。 | Ref: Remove the black metal barrier stanchion in the lower left foreground.<br>No-ref: Remove the selected stanchion.<br>scope -> stanchion | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a small flag on the roof at the upper right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8801740`（#1022，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the backpack near the center with a blue backpack. | U2 将黑色背包（藏青Polo衫男子背的）替换为 'a blue backpack' ——同一类别，仅改色。 | Ref: Replace the black backpack worn by the man holding the camera with a brown leather messenger bag.<br>No-ref: Replace the selected backpack with a brown leather messenger bag.<br>或转为属性：把背包颜色改为蓝色。 | 目视 |
| U2 | 严重 | mask 质量 | ref+mask | Replace the backpack near the center with a blue backpack. | 背包 mask(box [467,753,1257,1784],3 个分量)由男子躯干周围的两条肩带和侧面网兜组成;背包主体大部分藏在他身后,轮廓似乎也含了他的一部分手臂。可见的“backpack”是碎片化的,因此整个背包的替换定义不清。 | 改为针对相机(例如“Replace the black DSLR camera held by the man with a silver compact camera”)或他的藏青色 polo 衫。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a small badge on the shirt at the upper right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8813510`（#1025，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the pew at the lower right with a dark wooden pew. | U2 mask 是右下角一条中棕色木质教堂长椅;'Replace the pew ... with a dark wooden pew' 保持同一物体,只是颜色变深。 | Ref: Change the color of the pew at the lower right to dark walnut brown.<br>No-ref: Change the color of the selected pew to dark walnut brown.<br>convert op to attribute, or replace with a different object (e.g. 'a row of folding chairs') | 目视 |
| U4 | 轻微 | 指代歧义 | ref+mask | Add a small candle on the column at the left. | U4 mask 是后殿左侧带红金色柱头的奶油色独立立柱（box [486,547,576,970]）；左侧还有其他柱子/壁柱（例如紧靠其右、彩绘窗旁的柱子，以及最左边的墙壁壁柱），因此 'the column at the left' 只是大致识别。 | Ref: Add a small candle on the base of the free-standing column to the left of the apse arch. | 目视 |

#### `v2-sa_8855821`（#1027，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the car near the center with a red car. | 被 mask 的物体是正在被擦拭的黑色马自达轿车；'a red car' 只是同一物体类别的颜色变化。 | Ref: Replace the black sedan near the center with a white pickup truck.<br>No-ref: Replace the selected car with a white pickup truck.<br>或改为属性编辑：'Change the color of the black sedan near the center to red.' | 目视 |
| U3 | 严重 | 指代歧义 | ref+mask | Remove the spray bottle near the center. | 中心附近有两个瓶子：工人腿边前轮处的粉色喷雾瓶（视图 x~855），以及靠近花坛、在敞开车门旁放着的被 mask 的带标签白瓶（box x 1485-1548）。'the spray bottle near the center' 更符合粉色那个。 | Ref: Remove the white labeled bottle by the car's open door, next to the planter.<br>No-ref: Remove the selected bottle.<br>ZH: 移除车门旁、花坛边的白色贴标瓶子。 | 目视 |
| U4 | 轻微 | mask 质量 | noref+box | Add a white stripe on the shoes at the lower center. | REF 说“the shoes”(复数),但 mask 只覆盖了工人的一只黑鞋(box x 1237-1350)。 | Ref: Add a white stripe on the worker's black shoe at the lower center.<br>No-ref: Add a white stripe on the selected shoe.<br>或将 mask 扩展到两只鞋 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a white stripe on the shoes at the lower center. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8908572`（#1031，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+mask | Change the color of the car at the lower left to red. | U1 mask 的是中远景的银色轿车（box [602,915,761,991], cx=0.30, cy=0.64）。它在中等高度而不是左下，并且其他车辆（一辆银色小型货车、一辆白色汽车、公交车）更靠左。 | Ref: Change the color of the silver sedan driving just ahead of the silver minivan to red. | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the traffic sign at the left with a blue sign. | U2 mask 的是左侧的绿色头顶方向指示牌（box [207,710,364,788]）。'Replace ... with a blue sign' 只是改色，且没有说明牌上显示什么。 | Ref: Change the background color of the green direction sign at the left to blue.<br>No-ref: Change the background color of the selected traffic sign to blue.<br>将 op 改为 attribute | 目视 |
| U3 | 严重 | 指代歧义 | ref+point | Remove the traffic light near the top. | U3 mask 的是悬挂在顶部中央附近横臂上的横向交通信号灯(box [953,99,1160,185])。U4 的交通灯挂在同一横臂的左上方,更低处还有更多灯,因此“the traffic light near the top”至少适用于两个。 | Ref: Remove the traffic light hanging at the top center, at the end of the overhead arm. | 目视 |

#### `v2-sa_8962292`（#1035，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | ref+none | Replace the motorbike at the left with a blue motorbike. | U2 'Replace the motorbike at the left with a blue motorbike' 只改变了红色踏板车的颜色。 | Ref: Replace the red scooter at the left with a blue bicycle.<br>No-ref: Replace the selected motorbike with a blue bicycle.<br>or convert to attribute color->blue | 目视 |
| U4 | 轻微 | 多单元同一物理对象/相互冲突 | noref+box | Add a small logo on the plastic bag near the center. | U4 塑料袋挂在 U1 自行车的车把上，U3 帽子由该自行车的骑行者佩戴；这些单元聚集在同一个骑行者/自行车上，尽管它们是不同的物体。 | 可接受；可选择一个不附属于 U1 自行车的物体 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+box | Add a small logo on the plastic bag near the center. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_8998938`（#1037，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 属性值问题（无变化/含糊） | ref+none | Change the color of the boardwalk near the center to brown. | 被 mask 的物体是水上的之字形人行桥(桥面、深色栏杆和混凝土桥墩),不是 'boardwalk near the center'。其桥面和栏杆本来就偏棕/深色,所以 'to brown' 是一个弱且难以判断的变化。 | Ref: Change the color of the zigzag footbridge over the water to bright red.<br>No-ref: Change the color of the selected bridge to bright red.<br>Set scope to 'footbridge'. | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+mask | Replace the building at the upper right with a white building. | 被 mask 的物体是天际线上远处的灰色高层塔楼。'Replace the building with a white building' 保持类别不变，只改变颜色。'At the upper right' 也有歧义：天际线右侧部分有几座相似的塔楼（~0.62W、~0.75W），而被 mask 的那座在 0.69W，更靠近中心。 | Ref: Replace the tall gray tower on the skyline just right of center with a red-and-white lattice transmission tower.<br>No-ref: Replace the selected building with a red-and-white lattice transmission tower. | 目视 |

#### `v2-sa_9006288`（#1038，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| case | 轻微 | 多单元同一物理对象/相互冲突 |  |  | U2（红伞）握在男孩手里，U4 是同一男孩白衬衫的袖子；两个单元都与同一个孩子相关，尽管伞是一个独立的手持物体。 | 考虑把 U4 移到女孩身上（例如她的蓝色腰带），以使各单元归属不同的父对象。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | ref+box | Replace the umbrella at the upper center with a blue umbrella. | U2 把红色油纸伞(box [536,0,1489,651])替换为“a blue umbrella”——同一类别,仅颜色变化。 | Ref: Replace the red paper umbrella at the upper center with a large woven straw sun hat held on a stick.<br>或转换为 attribute:将红色纸伞的颜色改为蓝色。 | 目视 |
| U3 | 严重 | 指代类别与 mask 不符 | noref+mask | Remove the banner at the upper left. | REF 称 U3 为 'the banner at the upper left'，但 mask（box [312,4,561,343]）是一块带蓝色标志和营业时间的白色长方形小告示牌。一面真正的大横幅（绿/白色 'wing' 横幅）挂在更靠左处，因此 'banner' 指向了错误的物体。 | Ref: Remove the small white sign with opening hours at the upper left, behind the girl's head.<br>No-ref: Remove the selected sign.<br>范围 -> sign | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+none | Add a small badge on the sleeve near the center. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9006757`（#1039，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | mask 质量 | ref+mask | Change the color of the train at the left to red. | “the train at the left”——左侧灰/蓝/红条纹的火车横跨约 x~0-460 的多节车厢，但 mask 只覆盖最左侧一节车厢的碎片（box [0,737,119,860]）；红车头的蓝色火车也在左半边，使 REF 有歧义。 | Ref: Change the color of the gray train on the far-left track to red.<br>将 mask 扩展到整列可见的灰色火车，或改写为 'the leftmost gray carriage'。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the door near the center with a blue door. | 蓝色火车上被 mask 的乘客门本来就是蓝色;'Replace ... with a blue door' 是无变化/改色。'the door near the center' 在众多车门中也有歧义。 | Ref: Change the color of the first side door behind the red cab of the blue train to yellow.<br>No-ref: Change the color of the selected door to yellow.<br>op=attribute. | 目视 |

#### `v2-sa_9033895`（#1043，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+point | Change the color of the car at the lower left to red. | 'the car at the lower left' 符合沿左侧停放的许多车;被 mask 的是停在车列末端、靠近中心偏左(cx=0.28)、紧挨一辆黄色车的深蓝色小型面包车。 | Ref: Change the color of the dark blue minivan parked at the end of the row, next to the yellow car, to red.<br>ZH: 将停在车列末端、黄色汽车旁的深蓝色小型面包车的颜色改为红色。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+point | Replace the information sign at the right with a blue sign. | 被 mask 的物体是灯柱上的绿色 'Balaton / Veszprém' 方向牌；'a blue sign' 仍是同一物体，只改变颜色。'the information sign at the right' 也较宽松——右侧有几块标牌（停车/交通标志、多箭头行人指路牌）。 | Ref: Replace the green Balaton/Veszprém direction sign on the lamp post at the right with a round analog street clock.<br>No-ref: Replace the selected sign with a round analog street clock.<br>或改为属性编辑：'Change the color of the green Balaton/Veszprém direction sign to blue.' | 目视 |
| U3 | 严重 | 指代歧义 | ref+box | Remove the door at the right. | 'the door at the right' ——粉色转角建筑有几扇门（x~0.67W 处的灰色金属双开门、x~0.78W 处贴有告示的被 mask 木门，以及更靠右的店铺入口）。移除建筑的门还会留下无定义的敞开门洞。 | Ref: Remove the paper notices from the brown wooden door of the pink corner building, beside the signpost.<br>或改为属性：'Change the color of the brown wooden door of the pink corner building to dark green.' | 目视 |

#### `v2-sa_9068084`（#1046，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+box | Replace the backpack at the right with a red backpack. | U2 黑色束口背包 -> 'a red backpack' 只是改色。 | Ref: Replace the black drawstring backpack of the woman in the light blue hoodie on the right with a brown leather shoulder bag.<br>No-ref: Replace the selected backpack with a brown leather shoulder bag. | 目视 |
| U3 | 严重 | 指代类别与 mask 不符 | ref+point | Remove the banner at the right. | U3 mask 是像披风一样披在女子背上的白红白旗帜(0.91W);长条白色“banner”是紧挨着它横举的另一个物体。把披风旗称为“the banner at the right”具有误导性,而且移除被穿戴的旗帜披风接近于移除被穿戴的衣物。 | Ref: Change the color of the red stripe of the white-red-white flag draped over the woman's back on the right to blue.<br>No-ref: Change the color of the selected flag's red stripe to blue.<br>category -> flag;或保留 remove 但重新 mask 为长条白色横幅 | 目视 |

#### `v2-sa_9068591`（#1047，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the fence at the left with a black fence. | U2 mask 的是左侧半埋在雪中的一小段深绿色金属栏杆（box [78,434,198,531]）。'Replace the fence at the left with a black fence' 只改变颜色。 | Ref: Change the color of the green railing half-buried in snow at the left to black.<br>No-ref: Change the color of the selected fence to black.<br>将 op 改为 attribute | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+mask | Add a small label on the trash bin near the center. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9111693`（#1052，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | ref+point | Change the color of the car at the lower left to red. | U1 是沿路缘停放的银色掀背车(cx=0.41)。棕色出租车(U2)更靠近左下角,因此“the car at the lower left”至少同样符合出租车。 | Ref: Change the color of the silver hatchback parked at the curb in front of the pink building to red.<br>ZH:将粉色楼前路边停放的银色掀背车改为红色。 | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+point | Replace the car at the far left with a blue car. | U2（最左边的棕色 Yandex 出租轿车）'Replace ... with a blue car' 只在同一类别内改变颜色。 | Ref: Replace the brown taxi at the far left with a blue pickup truck.<br>No-ref: Replace the selected car with a blue pickup truck.<br>或改为属性：color -> blue | 目视 |
| U3 | 严重 | 指代歧义 | ref+box | Remove the window at the left. | 左侧粉色立面有一整片相同的窗户网格；U3 是左图像边缘被部分截断的三楼窗户。“the window at the left”适用于许多窗户。 | Ref: Remove the partially visible window at the left image edge on the second row from the bottom of the pink building. | 目视 |
| U4 | 严重 | 指代歧义 | noref+mask | Add a small badge on the jacket at the lower right. | U4 是站在远侧人行道上的金发女子的黑大衣(cx=0.72);她右边的男子穿米色夹克,所以 'the jacket at the lower right' 更自然地指他的。Mask 内部也有空洞。 | Ref: Add a small badge on the black coat of the blonde woman standing on the far sidewalk.<br>No-ref: Add a small badge on the selected coat. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small badge on the jacket at the lower right. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

#### `v2-sa_9172711`（#1060，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 指代歧义 | noref+point | Change the color of the basket at the left to brown. | “the basket at the left”——有几个编织篮:油桶顶上被 mask 的那个(0.35W)、更靠左地面上的另一个(约 0.16W,0.92H),以及中心的几对。此外该篮子本来就是棕褐色/棕色藤编,所以“to brown”是个很弱的变化。 | Ref: Change the color of the sulfur-filled wicker basket resting on the oil drums to dark red.<br>No-ref: Change the color of the selected basket to dark red. | 目视 |
| U2 | 严重 | 指代歧义 | ref+box | Replace the load near the center with a wooden crate. | 'the load near the center' —— 被 mask 的物体是底部地面上的一小堆黄色硫磺块（0.47W,0.94H），不在图像中心附近；还有若干类似的硫磺货物（0.35W 和 0.63W 的筐里、工人搬运的、0.82W 的地上堆）。 | Ref: Replace the small pile of yellow sulfur chunks on the ground right of the oil drums with a wooden crate.<br>No-ref: Replace the selected sulfur pile with a wooden crate.<br>范围 -> 'sulfur pile' | 目视 |
| U3 | 严重 | 指代歧义 | noref+mask | Remove the rock at the right. | “the rock at the right”——整张图是一片岩石坡；被 mask 的是右上边缘（0.98W,0.23H）的灰色小圆石，无法从该短语中识别。 | Ref: Remove the small grey boulder at the upper right edge of the slope. | 目视 |
| U4 | 严重 | 指代歧义 | ref+none | Add a warning label on the oil drum at the lower left. | 'the oil drum at the lower left' —— 两个油桶放在一起:更靠左的红白 'PE' 桶,以及其右侧被 mask 的黑盖 'IDEM' 桶(x476-615);REF 最自然地会选最左的(红色)桶。 | Ref: Add a warning label on the black-and-white IDEMITSU oil drum under the sulfur basket at the lower left. | 目视 |

#### `v2-sa_9216210`（#1069，扩充尾段 #945–#1083，最严重：严重）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 严重 | 属性值问题（无变化/含糊） | ref+box | Change the color of the railing at the left to dark. | 'Change the color of the railing to dark' 没有给出色相。被 mask 的栏杆是横跨整个图像宽度（box 0-1500）的圆形金/黄铜栏杆，所以 'at the left' 也是错的。 | Ref: Change the color of the gold circular railing around the floor medallion to matte black.<br>No-ref: Change the color of the selected railing to matte black. | 目视 |
| U2 | 严重 | replace 实为属性修改 | noref+mask | Replace the glass storefront near the center with a wooden storefront. | mask（box 954-1182 x 1595-1711，中心偏右）覆盖的是人群后方一家商店上部发光的玻璃门面。“Replace with a wooden storefront”是相同类别，仅材质变化。“Near the center”也较弱，因为回廊沿线有几个类似的店面。 | Ref: Replace the lit glass shop window right of center, behind the crowd, with a large red digital advertising screen.<br>No-ref: Replace the selected storefront with a large red digital advertising screen. | 目视 |
| U4 | 严重 | 指代歧义 | ref+mask | Add a small plaque on the animal sculpture near the center. | 天花板圆顶有一圈镀金生肖动物浮雕。被 mask 的是图像顶边的一个羊/公羊浮雕(0.62W, 0.08H),并不 'near the center'。圆顶中心是肋条交汇处,有几个动物雕塑更靠近它,所以 REF 无法识别目标。 | Ref: Add a small plaque on the gilded goat relief at the top edge of the ceiling dome, right of center. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+mask | Add a small plaque on the animal sculpture near the center. | add 物品过于笼统，未说明颜色/图案/文字 | 把 payload 具体化，如 "a small round white star logo" / "a small brass badge"，并写明安装部位 | 文本 |

### 4.3 仅含轻微问题的 case（138 个，目视确认）

#### `v2-sa_5460754`（#6，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代歧义 | noref+point | Replace the partly hidden reel at the bottom center with a wooden cable reel with broad circular flanges. | 底排有四个卷轴（最左两个、U2 第三个、U3 最右）。U2（box x 614-978）是第三个，位于右下角卷轴的左侧，并不明显处于“center”；“partly hidden”有一定区分作用，但第二个卷轴同样被部分遮挡。 | Ref: Replace the partly hidden reel directly left of the bottom-right reel with a wooden cable reel with broad circular flanges. | 目视 |

#### `v2-sa_4594747`（#10，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 中文翻译不一致 | ref+mask | Add one small red navigation light at the tip of the vertical tail of the front airplane. | ZH REF 写的是“垂直尾翼及根部过渡”（尾翼及根部过渡），而英文只说“the vertical tail of the front airplane”。 | ZH: 给前方飞机的垂直尾翼顶端加上一盏小红色航行灯。 | 目视 |

#### `v2-sa_1905152`（#11，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 中文翻译不一致 | noref+box | Remove the hood on the back of the person at the left. | ZH 写的是灰色帽兜(gray hood),但被 mask 的帽兜(box [88,461,282,567])在图中是深黑/炭色;English 未提颜色。 | ZH: 移除左后方背向镜头人物的帽兜。 | 目视 |

#### `v2-sa_3392242`（#15，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代歧义 | ref+mask | Add one yellow luggage tag attached to the side of the gray suitcase near the center. | U2 mask 是一个灰色拉杆行李袋，位于 cx=0.36W，由穿灰色夹克的男子拉着；一个灰色/橄榄色行李箱（cx~0.47W）更靠中间，因此 'near the center' 并不严谨，不过 'gray' 基本能起到区分作用。 | Ref: Add one yellow luggage tag attached to the side of the gray rolling bag pulled by the man in the gray jacket. | 目视 |

#### `v2-sa_4308138`（#20，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代歧义 | ref+mask | Add one round dark-green seat cushion on the pale bar stool beside the crowd on the left. | 几张其他浅色/白色吧台凳就在 U2 右侧（合成图中约 x~560-600，位于人群后方）；“the pale bar stool beside the crowd on the left”并不完全唯一，尽管 U2 是最显眼的一个。 | Ref: Add one round dark-green seat cushion on the white bar stool standing in the aisle just right of the man in jeans on the left. | 目视 |

#### `v2-sa_604524`（#37，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | 措辞/文法/描述细节 | ref+box | Replace the orange inner top of the woman at the lower left with a white blouse with a ruffled neckline. | REF 把被 mask 的内层上衣称为 'orange'，但像素显示是左下方棕色夹克下的芥末黄上衣（North Face logo）；目标仍然唯一。 | Ref: Replace the yellow inner top of the woman at the lower left with a white blouse with a ruffled neckline.<br>ZH 橙色 -> 黄色 | 目视 |

#### `v2-sa_1411984`（#45，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 中文翻译不一致 | noref+box | Remove the printed chest graphic from the seated man's pink T-shirt. | EN 写的是 pink T-shirt（图中为鲑鱼粉色T恤）；ZH 写的是 红色短袖（红色）。 | ZH: 移除摩托车上男子的粉色T恤的胸前印花。 | 目视 |
| U3 | 轻微 | 措辞/文法/描述细节 | ref+point | Change the color of the white T-shirt of the passerby behind the tree on the left to pale green. | 被 mask 的衣物是白色翻领短袖衬衫,而不是 T 恤;该男子走在树的左侧(仅轻微被遮挡),“behind the tree”表述不够准确。 | Ref: Change the color of the white short-sleeved shirt of the man walking on the far left to pale green.<br>No-ref: Change the color of the selected shirt to pale green.<br>scope=shirt | 目视 |

#### `v2-sa_4507759`（#47，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | mask 质量 | ref+point | Change the color of the jacket of the woman beside the man in blue to sage green. | U3 夹克 mask 在夹克上方、女子深色头发/头部区域（约合成图 x=140-175,y=445-485）有第二个小连通块，不属于夹克。 | 去掉 mask 上方的小连通块，只保留藏青色夹克躯干部分 | 目视 |

#### `v2-sa_10876982`（#52，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 方位/序数/实例指代错误 | ref+point | Remove the sleeves from the race shirt of the man behind the yellow-capped runner. | U1 mask 是黄帽跑者图像右侧紧邻的那名男子的衬衫（box x 1652-1800，对比她的 1524-1674），两人深度几乎相同；'behind' 较弱，但黄帽这一锚点仍能唯一确定他。 | Ref: Remove the sleeves from the race shirt of the man just right of the yellow-capped runner.<br>ZH: 黄帽跑者右侧男子 | 目视 |
| U5 | 轻微 | 指代歧义 | ref+none | Add one reflective band around the sleeve nearest the camera of the race shirt of the open-armed runner on the red carpet. | 张开双臂的跑者面向镜头，双臂对称展开；'the sleeve nearest the camera' 无法指向某一只特定的袖子。 | Ref: Add one reflective band around the image-left sleeve of the race shirt of the open-armed runner on the red carpet.<br>No-ref: Add one reflective band around the image-left sleeve of the selected shirt. | 目视 |

#### `v2-sa_3442588`（#54，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代歧义 | noref+point | Remove the short crank on the side of the middle machine. | 中间机器侧面有两个类似曲柄的配件:被 mask 的带旋钮的扁平拉杆(box [847,860,982,957])和其上方带旋钮的曲柄手柄(约 x=760-850,y=640-780 src)。“short crank on the side”可能指其中任何一个,不过被 mask 的那个是位置更低、更长的拉杆。 | Ref: Remove the flat lever-crank on the lower side of the middle machine. | 目视 |

#### `v2-sa_5157199`（#57，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 中文翻译不一致 | noref+point | Add one small white fabric badge on the visible back of the pink T-shirt at the top. | physical_parent_zh 写的是“上方蓝衣人物”（穿蓝衣的人），但被 mask 的顶部 T 恤（box x537-827,y0-289）是粉/褐红色，REF 和 ZH 也是这么写的。 | physical_parent_zh -> '上方粉衣人物' | 目视 |

#### `v2-sa_2875285`（#63，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 中文翻译不一致 | noref+mask | Remove the collar of the complete dog sculpture in the background. | NOREF ZH '移除选中的衣领' 使用了 衣领（衬衫领子），而目标是一只狗雕像的项圈（项圈），REF ZH 的表述是正确的。 | ZH noref: 移除选中的项圈。 | 目视 |

#### `v2-sa_10831959`（#65，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U5 | 轻微 | 中文翻译不一致 | ref+point | Change the color of the visible canopy of the multicolored umbrella on the right to white. | ZH REF '将其右侧彩色伞的可见伞面改为白色' 含有多余的 '其'（its），而英文 'the multicolored umbrella on the right' 中没有对应成分。 | ZH: 将右侧彩色伞的可见伞面改为白色。 | 目视 |

#### `v2-sa_6065460`（#74，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | mask 质量 | noref+box | Add one dark-red seat cushion on the chair partly hidden by an empty chair at the center right. | U2 mask(comps=3)包含右上角靠近邻桌处的一个分离碎片(合成图约 x=1015-1060,y=868-880),它在视觉上不属于 x~930-1000 处勾勒的椅子。 | 从 U2 mask 中移除该分离碎片 | 目视 |

#### `v2-sa_745831`（#78，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U5 | 轻微 | mask 质量 | ref+point | Remove the lower legs of the trousers of the person behind and left of the white-shirted child to make knee-length shorts. | U5 裤子 mask（box [382,868,521,1279]）的左上角突出部分延伸到后方那个人臀部高度的棕色包/手部区域，不仅仅是牛仔裤。 | 将 mask 修剪为仅蓝色牛仔裤 | 目视 |

#### `v2-sa_8660529`（#81，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | 中文翻译不一致 | ref+mask | Remove the blue chair back partly hidden between the two pale-shirted men at the left center. | EN 说椅背位于 'between the two pale-shirted men' 之间,但其右侧的男子(合成图中约 x~420-470)穿的是深灰色衬衫;只有左边的男子穿白衬衫。ZH 正确地写作 浅衣男子和灰衣男子。目标仍可识别。 | Ref: Remove the blue chair back partly hidden between the white-shirted man and the dark-gray-shirted man at the left center. | 目视 |

#### `v2-sa_8952950`（#84，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | 措辞/文法/描述细节 | ref+box | Change the color of the pale top partly hidden by the dark-jacketed person at the back right to pale green. | U4 的 mask 是一小条明显的黄色上衣（box [1549,366,1697,576]），部分被穿藏青夹克的人遮挡；REF 称其为 'pale top'（ZH 浅色上衣）。通过 'partly hidden by the dark-jacketed person' 仍可识别目标。 | Ref: Change the color of the yellow top partly hidden by the dark-jacketed person at the back right to pale green.<br>ZH: 将右后方被深色外套人物挡住的黄色上衣改为浅绿色。 | 目视 |

#### `v2-sa_9865645`（#87，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 措辞/文法/描述细节 | noref+point | Remove the white back lettering from the green T-shirt of the man directly behind him. | REF 'the man directly behind him' 依赖 U1 的指代对象（单独使用 REF 时 'him' 未定义）；目标是站在弯腰男子身后、穿绿色衬衫、印有白色 'THE DENIM BROS' 字样的男子。 | Ref: Remove the white lettering from the green T-shirt of the man standing behind the bending man. | 目视 |

#### `v2-sa_9181698`（#91，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 属性值问题（无变化/含糊） | ref+none | Change the color of the visible jeans of the person riding the cow to dark blue. | 骑行者的牛仔裤（U3，box [705,844,879,1155]）本来就是中等深浅的褪色蓝色丹宁；目标 'dark blue' 只是细微变化，难以验证，削弱了该属性编辑。 | Ref: Change the color of the visible jeans of the person riding the cow to bright red.<br>No-ref: Change the color of the selected trousers to bright red.<br>选一个明显不同的颜色 | 目视 |

#### `v2-sa_936576`（#92，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | mask 质量 | noref+box | Replace the trousers of the khaki-uniformed person in the middle with loose cargo trousers with large thigh pockets. | U1 卡其色长裤 mask（box 890-1169 x，1091-1500 y）沿男子手持的龙头道具的白色杆向左上延伸，包含了一小条道具。 | 将 mask 裁剪为仅卡其色长裤。 | 目视 |

#### `v2-sa_2361184`（#93，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 方位/序数/实例指代错误 | noref+box | Replace the pale headscarf of the woman in the middle with a fitted pleated headwrap. | 戴头巾的女子(box [1220,0,1471,317],中心 x=0.67W)是两位成年人中靠右的一位,而不是“in the middle”;她仍可凭浅色头巾被唯一识别。 | Ref: Replace the pale headscarf of the woman on the right with a fitted pleated headwrap.<br>ZH:将右侧女子的浅色头巾替换为贴合头部的褶裥包头巾。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Remove the white chest lettering from the sleeveless top of the child between the two adults. | REF 称该孩子的蓝色上衣为 'sleeveless'，但在裁剪图中看起来是带白色字样的蓝色短袖 T 恤。 | Ref: Remove the white chest lettering from the blue T-shirt of the child between the two adults. | 目视 |

#### `v2-sa_8894367`（#94，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 编辑不合理/不可执行 | ref+box | Remove the sleeves from the shirt visible on the man at the far left rear. | U1 mask 是最左后方男子蓝衬衫的肩部/上胸部（box x74-323），大部分被浅蓝上衣和灰发男子遮挡；至多能部分看到一只上臂袖子，但 REF 要求移除“the sleeves”（复数）。 | Ref: Remove the visible sleeve from the blue shirt of the man at the far left rear.<br>No-ref: Remove the visible sleeve from the selected shirt.<br>或将 op 改为 attribute（给蓝衬衫改色） | 目视 |

#### `v2-sa_1012535`（#96，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | mask 质量 | ref+none | Change the color of the striped T-shirt of the man on the right to orange. | 条纹 T 恤的 U4 mask 向杆子右侧延伸(视图中约 x~1290-1355),包住了男子手持的绿色文件夹/纸张,并触及灰衬衫女子的手臂;重新着色也会影响文件夹。 | 将 mask 裁剪为仅含条纹 T 恤面料,排除绿色文件夹和邻近的手臂 | 目视 |

#### `v2-sa_10207017`（#99，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代歧义 | ref+box | Replace the lower drum-strap segment at the left front-row drummer's waist with a braided cord strap segment. | U2 的背带属于约 0.15W 处的鼓手，但最左边缘（约 0.03W，带鼓）还能部分看到另一名前排鼓手，因此“the left front-row drummer”略显宽泛。 | Ref: Replace the lower drum-strap segment at the waist of the second front-row drummer from the left with a braided cord strap segment. | 目视 |

#### `v2-sa_10540618`（#101，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 措辞/文法/描述细节 | noref+mask | Change the color of the jeans of the dark-blue-jacketed child in the middle to maroon. | U3 的牛仔裤属于中间那位穿藏青色羽绒服、戴蓝绿色头巾的人；这个人看起来并不明显像孩子。 | Ref: Change the color of the jeans of the person in the navy puffer jacket and teal headscarf in the middle to maroon. | 目视 |

#### `v2-sa_1141051`（#108，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 中文翻译不一致 | noref+mask | Remove the collar from the white shirt beneath the right officer's protective vest. | ZH REF '移除右前警员防护背心下露出的白衬衫领口与两袖的衣领' 表述混乱（先提到 领口与两袖 又提到 衣领）；英文只移除衣领。 | ZH: 移除右侧警员防护背心下白衬衫的衣领。 | 目视 |

#### `v2-sa_1201946`（#110，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 中文翻译不一致 | ref+mask | Add one small chest pocket sewn onto the red top of the woman behind the child at the back right. | physical_parent_zh 为 '右后浅衣女子'(light-clothed woman),但被 mask 的上衣(box x1965-2094)如 REF 所述是深红/栗色。 | physical_parent_zh -> '右后红衣女子' | 目视 |

#### `v2-sa_1572241`（#112，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 措辞/文法/描述细节 | ref+none | Remove the lower legs of the jeans of the person with the red backpack in the middle to make knee-length shorts. | U1 人物的背包（box x 744-888）明显是亮粉/洋红色，而非红色；她仍是唯一背这种背包的人，因此目标可识别。 | Ref: Remove the lower legs of the jeans of the person with the pink backpack in the middle to make knee-length shorts.<br>ZH: 中间背粉色背包者 | 目视 |

#### `v2-sa_2119572`（#119，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 中文翻译不一致 | noref+point | Replace the foreground yellow shrimp tray with a shallow rectangular wicker basket. | EN 替换整个前景的黄色虾托盘；ZH 说仅替换托盘可见的边沿和侧壁（可见边沿和侧壁）。 | ZH: 将前景盛虾的黄色托盘替换为浅口长方形藤篮。 | 目视 |
| U4 | 轻微 | 指代歧义 | ref+box | Add a short blue work apron over the front of the sleeveless top of the vendor at the back right. | U4 摊贩(box 中心 x=0.63)位于柜台后方中间偏右;另有两名摊贩(0.72 处的 U5 和约 0.87 处的红上衣摊贩)更靠右,因此“at the back right”表述不够准确,不过“sleeveless top”(红/黑花纹)可起到区分作用。 | Ref: Add a short blue work apron over the front of the red-and-black sleeveless top of the vendor leaning over the fish counter at the center right. | 目视 |

#### `v2-sa_2367179`（#124，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 属性值问题（无变化/含糊） | ref+none | Change the color of the large white woven sack full of green fruit at the left rear to green. | U2 麻袋是白色编织布（box [124,561,422,978]），顶部可见装满绿橄榄；目标颜色“green”对麻袋来说确实是改变，但与内容物颜色一致，使结果难以评判（橄榄本来就是绿色）。 | Ref: Change the color of the large white woven sack full of green fruit at the left rear to red.<br>No-ref: Change the color of the selected sack to red.<br>选择与橄榄不同的颜色 | 目视 |

#### `v2-sa_2787726`（#129，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 措辞/文法/描述细节 | noref+point | Add one small embroidered flower patch on the outer thigh of the jeans of the brown-backpacked woman at the front left. | REF 称这位女子为 "brown-backpacked"，但她髋部的棕色皮质物品（box [78,1177,249,1500]）是单肩/斜挎包，不是背包。 | Ref: Add one small embroidered flower patch on the outer thigh of the jeans of the woman with the brown shoulder bag at the front left.<br>none | 目视 |
| U4 | 轻微 | 中文翻译不一致 | ref+none | Change the color of the yellow ceremonial umbrella above the middle of the elephant procession to deep red. | ZH REF 写的是“黄色仪仗伞及可见伞杆”（伞及其杆），而英文只说了伞；同时也漏掉了 "elephant procession"。 | ZH: 将象队中间上方的黄色仪仗伞改为深红色。 | 目视 |

#### `v2-sa_37740`（#137，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | 指代歧义 | ref+point | Tint the glass light bulb at the middle left pale blue. | 被 mask 的灯泡（box x 379-640）是从左数第二个灯泡；另有一个被部分截断的灯泡挂在最左边缘（x~0-170）同样高度处。'the glass light bulb at the middle left' 可以理解为任一个。 | Ref: Tint the second glass light bulb from the left, in front of the hanging ham, pale blue. | 目视 |

#### `v2-sa_3928896`（#138，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | mask 质量 | ref+box | Add one small elbow patch on the visible sleeve of the checked shirt of the back-facing man on the right. | 格子衬衫 mask（box [1615,703,1816,975]）还包含了斜挎在衬衫外的深色斜挎包及其背带。 | 优化 mask，排除斜挎包及其背带 | 目视 |

#### `v2-sa_443140`（#143，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 方位/序数/实例指代错误 | ref+mask | Replace the shirt of the side-facing uniformed man at the back left with a short-sleeved polo shirt. | 被 mask 的衬衫（box 中心 x=0.65）属于后排站立的三名制服男子中最左边的那位；按图像坐标他位于中心偏右，因此 'at the back left' 仅在相对于制服群体时成立。他仍可作为侧身面向的制服男子被唯一识别。 | Ref: Replace the shirt of the side-facing uniformed man standing by the cabin door, leftmost of the uniformed men at the back, with a short-sleeved polo shirt. | 目视 |
| U2 | 轻微 | 指代歧义 | noref+box | Change the color of the shirt of the hat-wearing man behind the foreground man to pale yellow. | 'the hat-wearing man behind the foreground man'：真正的前景男子是两位坐着的平民；意图指向的是被最右侧背对镜头的制服男子（同样戴帽）部分挡住的、戴藏青帽的制服男子。 | Ref: Change the color of the shirt of the uniformed man in the navy cap, partly hidden behind the back-turned officer at the far right, to pale yellow. | 目视 |

#### `v2-sa_5196006`（#154，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | 措辞/文法/描述细节 | noref+point | Remove the sleeves from the pale T-shirt of the man behind the bride's head. | U4 的 T 恤是带大幅印花的灰橄榄/卡其色衬衫,并不明显是 'pale';不过定位语 'man behind the bride's head' 仍能识别它。 | Ref: Remove the sleeves from the olive printed T-shirt of the man behind the bride's head. | 目视 |

#### `v2-sa_5735900`（#160，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 中文翻译不一致 | ref+none | Remove the left-side long sock of the leather-shorted boy on the right. | ZH 把被 mask 的袜子称为“绿色长袜”（green long sock），但这只袜子是灰色针织的，仅袜口有绿色条纹；英文 REF 没有给出颜色。 | ZH: 移除最右穿皮短裤男孩靠画面左侧的灰色长袜。 | 目视 |

#### `v2-sa_5953627`（#163，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U5 | 轻微 | 措辞/文法/描述细节 | ref+point | Remove the pale-green plastic bag on the rim of the rectangular basket at the right rear, including its contents. | U5 的包（box [1523,682,1741,847]）看起来是装着粉色物品的透明/发白塑料袋。“Pale-green”不太贴切，不过其余描述（在篮子边缘、右后方）仍然是唯一的。 | Ref: Remove the clear plastic bag of pink items on the rim of the rectangular basket at the right rear, including its contents. | 目视 |

#### `v2-sa_6233893`（#166，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | mask 质量 | ref+none | Add one small chest pocket sewn onto the pale shirt of the orange-scarfed man on the right. | U1 “pale shirt” 的 mask 轮廓除了白衬衫外，还圈入了披在肩/胸前的橙色围巾（放大裁剪图显示围巾位于红色轮廓内）。 | 将橙色围巾从衬衫 mask 中排除 | 目视 |

#### `v2-sa_6571872`（#170，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 措辞/文法/描述细节 | ref+mask | Remove the checked scarf around the blue-jacketed woman's neck in front. | REF/ZH 称被 mask 的围巾为 'checked'（格子），但它实际是蓝夹克卷发女子身上的一条长长的绿色与粉/紫色条纹针织围巾；目标仍然唯一。 | Ref: Remove the green-and-pink striped scarf around the neck of the curly-haired woman in the blue jacket in front.<br>ZH 格子围巾 -> 绿粉条纹围巾 | 目视 |

#### `v2-sa_7184680`（#173，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | 措辞/文法/描述细节 | noref+point | Remove the tall shaft, making it an ankle boot from the black boot on the middle male dancer's raised foot. | REF “Remove the tall shaft, making it an ankle boot from the black boot on ...”语序混乱;mask 正确覆盖了中间男舞者抬起的黑色靴子。 | Ref: Remove the tall shaft from the black boot on the middle male dancer's raised foot, making it an ankle boot.<br>No-ref: Remove the tall shaft from the selected boot, making it an ankle boot. | 目视 |

#### `v2-sa_7407780`（#177，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 方位/序数/实例指代错误 | noref+point | Replace the front-center folding chair facing the camera with a round wooden stool. | REF 称该椅子在 'front-center'，但其 box 中心为 0.33W（偏离图像中心靠左）；朝向侧面的 U2 椅子在 0.55W，实际上更居中。不过 'facing the camera' 加上位于 U5 与 U2 之间，仍可识别它。 | Ref: Replace the front-left-of-center folding chair facing the camera with a round wooden stool. | 目视 |

#### `v2-sa_7566194`（#181，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 措辞/文法/描述细节 | ref+point | Add one small silver buckle attached to the thin pink-bag strap across the left-front woman's chest. | 粉色包的背带（box [722,534,806,816]）从女士举起的手垂直垂到她臀部的包上；并没有斜跨她的胸前。 | Ref: Add one small silver buckle attached to the thin strap of the pink bag hanging from the left-front woman's raised hand.<br>ZH: 给左前女士手中提起的粉色包细长包带加上一个小银色带扣。 | 目视 |

#### `v2-sa_7794828`（#187，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | 指代类别与 mask 不符 | ref+box | Add one small blue star-shaped patch sewn onto the white short sleeve above the red jacket on the right. | REF/ZH 把袖子锚定为“above the red jacket”/红外套,但袖子下方的红色物品(box [1304,625,1549,948])是带扣带的红色斜挎包,而不是外套。目标仍可识别。 | Ref: Add one small blue star-shaped patch sewn onto the white short sleeve above the red bag on the right.<br>ZH:红外套 -> 红色挎包 | 目视 |

#### `v2-sa_8120561`（#188，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 措辞/文法/描述细节 | ref+none | Change the color of the elevated carriage driver's blue jacket to dark brown. | REF 称车夫的夹克为 'blue'；图中它是深色、近乎黑色的仿皮夹克，只是调色带来冷蓝色调。目标无歧义（只有一名车夫）。 | Ref: Change the color of the elevated carriage driver's dark jacket to dark brown.<br>ZH: 将高处车夫的深色外套改为深棕色。 | 目视 |

#### `v2-sa_8830719`（#196，原版 #0–#199，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 措辞/文法/描述细节 | ref+none | Remove the hood from the hooded jacket of the hat-wearing man on the left. | 最左侧的 U1 男子(box [105,152,370,630])戴着拉起的深海军蓝帽兜,看不到帽子,因此图像不支持 'hat-wearing'。'On the left' 仍能唯一识别他。 | Ref: Remove the hood from the dark navy hooded jacket of the man at the far left. | 目视 |
| U2 | 轻微 | 措辞/文法/描述细节 | ref+mask | Remove the hood from the hooded jacket of the side-facing person immediately to his right. | 'Immediately to his right' 依赖 U1 的文本，可能被理解为该男子自己的右边，即图像左侧。目标是 U1 图像右侧的那位戴棕色兜帽的人。 | Ref: Remove the hood from the brown hooded jacket of the side-facing person at the left, just image-right of the man in the dark navy jacket. | 目视 |

#### `v2-sa_10006079`（#200，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代类别与 mask 不符 | noref+mask | Remove the black backpack beside the woman. | 被 mask 的物体是躺在船底的黑色 Quechua 圆筒旅行包/手提包（带抽绳的横向桶形），不是背包；仍可唯一识别为女子旁边的黑色包。 | Ref: Remove the black duffel bag beside the woman.<br>No-ref: Remove the selected bag. | 目视 |

#### `v2-sa_10044652`（#203，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 方位/序数/实例指代错误 | noref+point | Replace the central man’s red-and-blue track jacket with a navy bomber jacket. | 红蓝夹克男子位于 x~0.29W（图像中偏左），并不居中；不过夹克本身是唯一的，所以目标仍可识别。 | Ref: Replace the red-and-blue track jacket of the man standing on the left sidewalk with a navy bomber jacket.<br>无 | 目视 |

#### `v2-sa_10235725`（#219，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | add 锚点不当 | ref+point | Add a small silver lapel pin to the black-and-white checked shirt. | Payload 是黑白格纹纽扣衬衫上的“lapel pin”,而该衬衫没有翻领;放置位置未指定。 | Ref: Add a small silver pin on the chest of the black-and-white checked shirt.<br>No-ref: Add a small silver pin on the chest of the selected shirt. | 目视 |

#### `v2-sa_10308802`（#225，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代歧义 | ref+point | Add a silver hubcap to the rightmost rear wheel of the black truck. | 'rightmost rear wheel of the black truck' —— 被 mask 的轮子是挂车后轴组的右轮（原图 x~601-664）；牵引车自身更靠右的后驱动轮（原图约 x 940-1120）也可能被理解为卡车的后轮。 | Ref: Add a silver hubcap to the rightmost trailer wheel of the black truck. | 目视 |

#### `v2-sa_10367798`（#231，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代歧义 | noref+box | Replace the left hanging bulb with a traditional brass pendant lantern. | 存在多个悬挂灯泡（视图中约 x~390 和 ~1150 处的两个较低灯泡，天窗附近的两个较小的上方灯泡）。被 mask 的是最左上方的灯泡；REF“the left hanging bulb”也可能对应左下方的灯泡。U2 用了“upper-right”，但 U1 缺少对应的限定词。 | Ref: Replace the upper-left hanging bulb with a traditional brass pendant lantern. | 目视 |

#### `v2-sa_10375302`（#233，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | mask 质量 | ref+none | Change the color of the nearest fisherman’s pale shirt to light blue. | 渔夫衬衫的第二个 mask 分量(鱼竿下方,约 [1340,720,1460,790])还圈入了他腰带处的金色渔线轮/腰包区域,而不仅是衬衫布料。 | Trim the lower mask component to exclude the reel/waist pouch. | 目视 |

#### `v2-sa_10398187`（#236，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代类别与 mask 不符 | ref+point | Remove the leftmost orange traffic cone. | U1（box [141,750,181,815]）是带反光带的橙色管状隔离柱，不是锥形交通锥。 | Ref: Remove the leftmost orange delineator post.<br>No-ref: Remove the selected delineator post. | 目视 |
| U2 | 轻微 | 指代歧义 | noref+point | Replace the right orange traffic cone with a terracotta planter with a small boxwood shrub. | 'the right orange traffic cone' 指两个橙色标志物中靠右的那个，但两者都位于图像最左侧（x=0.14W）；“right”是相对的，可能造成误导。 | Ref: Replace the orange traffic cone to the right of the delineator post at the left with a terracotta planter with a small boxwood shrub. | 目视 |

#### `v2-sa_10444816`（#242，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代歧义 | ref+box | Change the color of the orange T-shirt facing away in the background to bright blue. | 有数名穿橙色 T 恤、戴粉色帽子的男子（最左 x~0.0-0.05W，U1 后方约 0.12W）。U2（box [648,686,774,840]，中心 0.36W）是背景中央行走的那位，但 'the orange T-shirt facing away in the background' 也可能指左侧横幅后穿橙色衣服的男子。 | Ref: Change the color of the orange T-shirt of the man in the pink cap walking in the center background to bright blue. | 目视 |

#### `v2-sa_10450817`（#243，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代歧义 | ref+mask | Remove the white sponsor sticker on the car door. | U2 mask = 车门上号码 15 旁边的大白色拉力赛牌（49 Rajd Swidnicki / KRAUSE）。同一车门上紧挨其下方还有其他几个小白色赞助贴纸（如一个 KRAUSE 贴纸），因此“the white sponsor sticker on the car door”并不严格唯一，尽管该牌最显眼。 | Ref: Remove the large white rally plate sticker next to the number 15 on the car door. | 目视 |

#### `v2-sa_10624309`（#251，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | mask 质量 | ref+none | Remove the bottle immediately left of the central red disc. | U3 box [0,714,915,1055] 延伸到图像左边缘，而瓶子 mask 约从 x~365 开始；因此该 box 也覆盖了最左边相邻的带标签瓶子，使 box 定位比必要的更宽松（正式输入为 ref+none，影响较小）。 | 根据瓶子 mask 重新计算紧致的 box（约 x 365-915），并去掉左边缘多余的像素。 | 目视 |

#### `v2-sa_10790861`（#272，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | 指代歧义 | noref+box | Remove the flag above the street. | 'the flag above the street'：背景较低处、建筑物后方（x~0.45W, y~0.35H）还能看到第二面较小的绿色旗帜；被 mask 的是顶部中央杆子高处的那面高旗（box [968,309,1011,505]）。 | Ref: Remove the flag at the top of the tall flagpole in the upper center. | 目视 |

#### `v2-sa_10813555`（#279，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 方位/序数/实例指代错误 | ref+mask | Remove the silver car below the cement mixer. | 被 mask 的银色轿车(box [189,278,410,350])位于水泥搅拌车(搅拌车 box [316,71,696,345])旁边/左侧,处于同一路面高度,而不是在其“below”;由于它是搅拌车旁唯一的汽车,仍可识别。 | Ref: Remove the silver car to the left of the cement mixer truck.<br>ZH:移除水泥搅拌车左侧的银色小汽车。 | 目视 |

#### `v2-sa_10974884`（#294，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 措辞/文法/描述细节 | noref+point | Replace the “MENDEPARTEMENTET” shop sign with a wooden “MARINA” sign. | 被 mask 的横幅标牌写的是 'MINDEPARTEMENTET'（带 I），但 REF/ZH 拼成了 'MENDEPARTEMENTET'。同一个词也画在上方建筑立面上；mask 正确覆盖了雨篷下方的深色横幅标牌。 | Ref: Replace the dark blue “MINDEPARTEMENTET” banner sign under the canopy with a wooden “MARINA” sign.<br>ZH 中的拼写也要修正。 | 目视 |

#### `v2-sa_11150954`（#308，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | Ref/No-ref 不等价 | noref+point | Replace the entrance wall lantern’s light head with an opal globe light. | REF 指向 "the entrance wall lantern's light head"(mask 仅为灯头,不含支架),ZH NOREF 写的是 选中的灯头,但 EN NOREF 写的是 "Replace the selected lantern",可能被理解为包括支架在内的整盏灯。 | No-ref: Replace the selected lantern head with an opal globe light. | 目视 |

#### `v2-sa_11170556`（#309，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | 指代歧义 | ref+point | Add a small red tassel on the bottom of the paper lantern on the left. | 左侧还能部分看到其他纸灯笼（一个在最左边缘约 x=30,y=330，一个在墙边约 x=240,y=340）；'the paper lantern on the left' 依赖于 U4 是最显眼的那一个。 | Ref: Add a small red tassel on the bottom of the large white paper lantern hanging on the left building wall. | 目视 |

#### `v2-sa_11182855`（#311，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | mask 质量 | ref+none | Remove the fishing boat behind the foreground boat. | 后方渔船 mask(box [11,515,1350,997],3 comps)参差破碎、孔洞很多,并且似乎包含了码头边缘的黑色轮胎护舷(最左侧约 x=10-130);渔船可识别,但轮廓有噪点。 | 清理 mask(填补后方船体/船舱的内部孔洞);对基于 ref 的评分而言按现状可接受。 | 目视 |

#### `v2-sa_1131468`（#313，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 方位/序数/实例指代错误 | ref+box | Add a narrow black ribbon band around the crown of the large straw hat in the center. | 'the large straw hat in the center'：被 mask 的圆锥形草帽位于中心偏右（box 中心 x=0.71W, y=0.34H）；左上方还有其他草帽。'large' 仍然起到区分作用。 | Ref: Add a narrow black ribbon band around the crown of the large conical straw hat right of center. | 目视 |

#### `v2-sa_1207849`（#324，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代类别与 mask 不符 | noref+point | Add a compact headlamp on the front of the helmet behind the foreground worker. | U1 mask(box [928,236,1157,404])是后面那个人戴的软檐帽(像棒球帽),而不是 REF/ZH(安全帽)所说的硬质安全帽。 | Ref: Add a compact headlamp on the front of the cap of the person behind the foreground worker.<br>No-ref: Add a compact headlamp on the front of the selected cap.<br>scope -> cap | 目视 |

#### `v2-sa_1212104`（#325，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 属性值问题（无变化/含糊） | noref+box | Change the color of the leftmost blue upstairs shutters to sage green. | REF 称被 mask 的最左侧楼上百叶窗为 'blue'，但图中它们是深青绿色/瓶绿色（与相邻百叶窗相同）。目标仍可被唯一识别为最左侧楼上的百叶窗。 | Ref: Change the color of the leftmost dark green upstairs shutters to sage green.<br>注：深绿色 -> 鼠尾草绿 是细微变化；建议改用对比更强的值，例如浅蓝色 | 目视 |

#### `v2-sa_1247398`（#331，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 属性值问题（无变化/含糊） | ref+mask | Change the color of the trampoline on the right to blue. | 蹦床由绿色软垫框架罩、黑色网面和灰色金属腿组成；'change the color of the trampoline to blue' 没有说明哪个部分（实际上是绿色软垫）应变成蓝色，让评判者去猜网面/腿是否也要改。 | Ref: Change the color of the green frame pads of the trampoline on the right to blue.<br>No-ref: Change the color of the green frame pads of the selected trampoline to blue. | 目视 |

#### `v2-sa_1415852`（#349，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 措辞/文法/描述细节 | noref+point | Add a small action camera on the top of the rider’s blue helmet. | 头盔（box [846,589,974,719]）在图中看起来是亮黑色/很深的藏青色；REF 称其为 'blue helmet'。场景中只有一顶头盔，因此目标无歧义。 | Ref: Add a small action camera on the top of the rider's dark helmet. | 目视 |

#### `v2-sa_1467894`（#353，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 多单元同一物理对象/相互冲突 | noref+point | Add a blue silk bow on the handle of the white geometric handbag. | 几何图案手提包（U3，box [1119,1148,1212,1278]）由同一位女士手提，她的白色外套是 U1（box [1073,984,1194,1245]）；包与外套区域重叠，因此两处编辑在同一个人身上相互影响（外套替换必须围绕手提的包重新渲染）。 | 作为独立物体可以接受，但可考虑为 U1 或 U3 选择不同人物身上的目标。 | 目视 |

#### `v2-sa_1471745`（#354，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | mask 质量 | ref+none | Replace the black car behind the fence on the left with a silver hatchback. | 左侧围栏后的黑色 SUV 超出了 mask 右边缘:其车尾角/尾灯(在被 mask 的后轮右侧,原图约 x~300-320)未被覆盖。 | extend mask to include the rear of the black SUV | 目视 |

#### `v2-sa_1630927`（#376，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a small handwritten price tag on the hanging white basket behind the person on the right. | REF 说 'the hanging white basket behind the person on the right'，但被 mask 的白色塑料篮（box [1460,747,1830,911]）放在唯一（坐着的）人物右侧的货架上；'hanging' 和 'the person on the right' 不准确，不过目标仍可识别。 | Ref: Add a small handwritten price tag on the white plastic basket on the shelf to the right of the seated person. | 目视 |

#### `v2-sa_1642015`（#377，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代歧义 | ref+box | Replace the wicker basket on the stall’s lower-left shelf with a white ceramic bowl. | 左下方的架子上有两个柳条篮:被 mask 的较大的那个(box x 609-787)和紧挨其右侧的一个较小的;“the wicker basket”没有说明是哪一个。 | Ref: Replace the larger wicker basket on the stall's lower-left shelf with a white ceramic bowl. | 目视 |
| U4 | 轻微 | 指代歧义 | ref+none | Change the color of the pale green bowl on top of the glass display case to blue. | 玻璃展示柜顶部放着两个淡绿色陶瓷碗/罐；被 mask 的是右边那个（box x 1088-1192），另一个紧靠其左侧。 | Ref: Change the color of the right pale green bowl on top of the glass display case to blue. | 目视 |

#### `v2-sa_1649043`（#379，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | replace 实为属性修改 | ref+box | Replace the round Heineken sign on the left with a round coffee-shop sign. | U1 将圆形 Heineken 灯箱招牌替换为 'a round coffee-shop sign' —— 同一物体类型和形状,只是印刷的品牌/图案变了;作为类别/结构替换偏弱。 | Ref: Replace the round Heineken sign on the left with a wrought-iron hanging lantern.<br>No-ref: Replace the selected sign with a wrought-iron hanging lantern. | 目视 |

#### `v2-sa_168719`（#384，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | mask 质量 | noref+box | Replace the central flower arrangement behind the couple with an arrangement of white roses and greenery. | 中央花艺 mask 向下延伸，绕过新娘举起的、手绘指甲花的手（该手拿着叉子和蛋糕）（合成图中约 x 650-740，y 310-420），并包含部分粉色帷幔；替换整个 mask 可能会改动这只手。 | 细化 mask，排除新娘举起的手/叉子和粉色帷幔 | 目视 |

#### `v2-sa_1725557`（#386，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 属性值问题（无变化/含糊） | noref+box | Change the color of the standing person’s white shirt on the left to navy blue. | U1 站立者(左上角,在图像顶部被裁切)的衬衫看起来是浅灰色而非白色。 | Ref: Change the color of the light gray shirt of the standing person on the left to navy blue. | 目视 |

#### `v2-sa_1850053`（#397，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | mask 质量 | noref+box | Remove the freestanding “NOW LEASING” sign. | REF 移除的是独立的 'NOW LEASING' 标牌，但 mask（box [669,1293,1369,1858]）只覆盖标牌板，不包括下面的金属丝支架腿；移除 mask 区域会留下支架。 | 扩展 mask 以包含金属丝支架腿，或表述为 'Remove the NOW LEASING sign together with its wire stand.' | 目视 |

#### `v2-sa_1939144`（#406，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 指代类别与 mask 不符 | noref+mask | Change the color of the blue shorts just left of the monument to beige. | mask(很小,box 813-876 x 1095-1148)覆盖的是花坛后面一名站立男子裤子的蓝色牛仔布臀部;腿部被花遮挡,且该衣物看起来像牛仔裤而不是短裤。 | Ref: Change the color of the blue jeans of the man standing just left of the monument to beige.<br>No-ref: Change the color of the selected jeans to beige. | 目视 |

#### `v2-sa_2176556`（#425，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | mask 质量 | noref+point | Add a small blue information plaque on the balcony railing at the upper left. | U2 阳台栏杆 mask（box [38,72,337,155]）是覆盖在开放栏杆上的填充多边形，包含了栏杆后面的三名游客（一人穿亮橙/黄色夹克，一人穿粉色），而不仅仅是栏杆。 | 将 mask 优化为仅栏杆条/顶部横栏，或将游客视为受保护内容 | 目视 |

#### `v2-sa_222823`（#429，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代歧义 | noref+box | Change the color of the black table covering in front of the food trailer to white. | U1 mask = 拖车正前方的长条黑布覆盖的矩形桌（box [941,848,1780,1136]）。左前景还有第二张黑色弹力布覆盖的鸡尾酒桌，同样在拖车前面；"the black table covering in front of the food trailer" 没有明确排除它。 | Ref: Change the color of the black covering on the long rectangular table in front of the food trailer to white. | 目视 |

#### `v2-sa_2313448`（#434，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 属性值问题（无变化/含糊） | ref+none | Change the color of the white rose in the bucket to pink. | 被 mask 的玫瑰（box [1732,595,2027,769]）是奶油色，中心已带有粉/桃色晕染，因此“white rose ... to pink”是一个较弱、部分已满足的改变。 | Ref: Change the color of the cream rose in the bucket to deep red.<br>No-ref: Change the color of the selected rose to deep red. | 目视 |

#### `v2-sa_2373849`（#440，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | replace 实为属性修改 | ref+box | Replace the black shirt behind the ladder with a blue work shirt. | U2 将左侧工人的黑色 T 恤替换为 'a blue work shirt' —— 主要是同一服装类别(衬衫)内的颜色变化;结构变化只是隐含的。 | Ref: Replace the black T-shirt behind the ladder with a blue hooded sweatshirt.<br>No-ref: Replace the selected shirt with a blue hooded sweatshirt. | 目视 |

#### `v2-sa_2497784`（#451，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代歧义 | ref+box | Change the color of the long roof of the covered bridge to slate gray. | 廊桥屋顶在砖塔左侧(雕像后方,显示图 x~0-760)和右侧均可见;mask 只覆盖右侧一段(box x 1143-1711)。“the long roof of the covered bridge”可能被理解为整个屋顶。 | Ref: Change the color of the long roof section to the right of the covered bridge's tower to slate gray. | 目视 |

#### `v2-sa_2599387`（#464，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 指代歧义 | ref+mask | Change the color of the upper clock face on the tower to cream. | U3 mask 是绿色圆顶上正面朝前的钟面(box 749-822,580-657);圆顶左侧同一高度的上层还有第二个朝向侧面的钟面(约 0.29W,0.40H),因此“upper clock face”略有歧义。 | Ref: Change the color of the front-facing upper clock face on the tower dome to cream. | 目视 |

#### `v2-sa_2602254`（#465，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代歧义 | noref+point | Replace the rightmost blue chair under the tent with a white folding chair. | 被 mask 的椅子正后方/右侧（显示图约 x 1140-1160）还有另一把部分可见的蓝色椅子，因此 "rightmost" 略显宽松。被 mask 的椅子是这一排右端最靠前的一把。 | Ref: Replace the front blue chair at the right end of the row under the tent with a white folding chair. | 目视 |

#### `v2-sa_2800852`（#484，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | mask 质量 | noref+box | Tint the arched window above the shop pale gray. | 拱形窗 mask 漏掉了拱的左上角(扇形窗左上角被切出一个缺口)。 | 将 mask 扩展到完整的拱形轮廓。 | 目视 |

#### `v2-sa_280789`（#485，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代歧义 | noref+point | Replace the yellow plastic jug at the right-hand stall with a silver metal canister. | 被 mask 的壶 [1560,1284,1607,1367] 是站在右侧摊位前、人们脚边地面上的半透明米色/棕褐色壶，既不明显是黄色，也不在摊位上；'yellow plastic jug at the right-hand stall' 描述较宽松（足够唯一，但颜色/位置措辞可能误导）。 | Ref: Replace the beige plastic jug on the ground in front of the right-hand stalls with a silver metal canister. | 目视 |

#### `v2-sa_2969849`（#506，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代类别与 mask 不符 | noref+mask | Replace the cream shirt on the crouching person with a blue checked shirt. | U2 mask（box [1369,528,1683,814]）是蹲着的男子身上的奶油色拉链夹克/风衣，REF 称其为 'cream shirt'。把夹克替换为蓝色格子衬衫是合理的衣物更换，但措辞应写 jacket。 | Ref: Replace the cream jacket on the crouching man with a blue checked shirt.<br>No-ref: Replace the selected jacket with a blue checked shirt.<br>scope -> jacket | 目视 |

#### `v2-sa_2980326`（#507，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代歧义 | noref+box | Remove the horizontal white-blue-red flag behind the helicopter. | 直升机机头右侧可见第二面白蓝红俄罗斯三色旗的一部分(源图 x~1970,大部分被遮挡);被 mask 的那面(box x2082-2144)是唯一完整可见的,位于一面白红蓝海军风格旗和一面黄蓝空军旗之间。REF “behind the helicopter”不能严格地将其单独指出。 | Ref: Remove the white-blue-red tricolor flag between the white ensign-style flag and the yellow-and-blue sunburst flag at the right. | 目视 |

#### `v2-sa_2988008`（#509，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 指代歧义 | ref+mask | Remove the second hanging snack bag from the left. | 在第一个炸面球大袋（x~1000-1250 src）和 U3（1263-1492）之间挂着一个较小的白色/透明塑料袋；若计入，U3 就是第三个悬挂的袋子。“second ... snack bag”依赖于只把大的炸面球袋算作零食袋。 | Ref: Remove the second large hanging bag of puris from the left.<br>ZH: 移除从左数第二个悬挂的大袋炸面球。 | 目视 |

#### `v2-sa_2989808`（#510，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | 多单元同一物理对象/相互冲突 | noref+mask | Remove the medal worn by the athlete raising the trophy. | U1(奖杯)和 U4(奖牌)都属于同一位穿海军蓝衬衫的中间运动员:她拿着奖杯并佩戴奖牌。它们是不同的物体,所以只是弱耦合。 | Ref: Remove the medal worn by the athlete in the orange jacket on the far right.<br>retarget U4 to the far-right athlete's medal, or keep as is | 目视 |

#### `v2-sa_3081992`（#517，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | mask 质量 | noref+box | Change the color of the STRAWBERRY 2 for £5 price board to dark green. | 黑板 mask box [449,501,845,1144] 远远延伸到 STRAWBERRY 2 for £5 黑板下方；mask 包含悬挂的绳圈以及下方草莓盒圆形贴纸上的一块碎片。 | 将 mask 裁剪为仅含黑板（box 约 y 501-1000）。 | 目视 |

#### `v2-sa_3110521`（#519，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代类别与 mask 不符 | noref+box | Replace the purple hat on the left with a white bucket hat. | 被 mask 的物品(box [677,207,1046,425])是系在头发上的紫色布质头巾/方巾,不是帽子;另外佩戴者在画面中偏左,而不是在画面左侧。 | Ref: Replace the purple bandana on the long-haired woman's head with a white bucket hat.<br>No-ref: Replace the selected bandana with a white bucket hat.<br>Set scope to 'bandana'. | 目视 |

#### `v2-sa_3124476`（#520，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | replace 实为属性修改 | noref+mask | Replace the white shirt behind the front-right placard with a pale-blue cotton blouse. | 把白色有领衬衫替换为 'a pale-blue cotton blouse'——几乎等价的上装，所以变化主要是颜色；属于边缘性的 replace。 | Ref: Replace the white shirt behind the front-right placard with a gray hooded sweatshirt.<br>No-ref: Replace the selected shirt with a gray hooded sweatshirt. | 目视 |
| U2 | 轻微 | 措辞/文法/描述细节 | ref+none | Change the color of the gray flat cap in the middle-right crowd to burgundy. | 被 mask 的帽子（box x1512-1651）是带弧形帽檐的灰色棒球帽，而不是 'flat cap'；其正下方还有第二顶石板蓝色棒球帽，因此措辞应当精确。 | Ref: Change the color of the gray baseball cap in the middle-right crowd to burgundy. | 目视 |

#### `v2-sa_3176315`（#527，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | replace 实为属性修改 | ref+box | Replace the tall gray advertising board in the middle with a cream poster reading Welcome to Dresden in navy. | U1 mask 是一块独立站立的灰色广告牌，印有“WERKZEUG UM 1600”；payload“a cream poster reading Welcome to Dresden in navy”实际上只是更换同一块板上印刷的图案（海报无法独立站立），所以读起来是内容/图形变化，而非结构性替换。 | Ref: Replace the tall gray advertising board in the middle with a wooden information kiosk.<br>No-ref: Replace the selected board with a wooden information kiosk.<br>或改写为更改展板的海报图案 | 目视 |

#### `v2-sa_3317928`（#540，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | mask 质量 | noref+point | Change the color of the vendor’s blue headscarf to burgundy. | U2 头巾 mask（box [717,321,1110,978]）同时覆盖了素色蓝灰色头巾（hijab）和系在颈部、垂到胸前的另一条浅蓝花卉围巾；REF 只提到单一的“blue headscarf”。 | 要么将 mask 限制为素色 hijab，要么改写为 'the vendor's blue headscarf and floral neck scarf'。 | 目视 |

#### `v2-sa_3460138`（#551，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 多单元同一物理对象/相互冲突 | ref+box | Remove the white plastic bag held by the visitor in purple. | U3 的白色塑料袋由同一位参观者拿在手里,他的紫色夹克是 U2(REF 甚至称他为 'the visitor in purple');两个 mask 不重叠,但两个单元落在同一个人身上。 | acceptable as a held detachable object; otherwise swap U3 for an unrelated object (e.g. the tan shoulder bag of the man at far left) | 目视 |

#### `v2-sa_3474930`（#554，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | mask 质量 | noref+point | Change the color of the walls of the blue-roofed building at the far left to cream. | scope 是“walls”,但 mask(box 0-189 x 549-702)覆盖了最左侧的整栋建筑,包括其蓝色屋顶。墙壁本来就是白色/米白色,改成奶油色几乎看不出变化。 | Ref: Change the color of the walls of the blue-roofed building at the far left to terracotta.<br>No-ref: Change the color of the selected walls to terracotta.<br>将 mask 限制在墙面区域(排除屋顶)或将 scope 改为 building | 目视 |

#### `v2-sa_3628858`（#568，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a coiled rope inside in the green boat floating near the upper middle. | REF/NOREF 'Add a coiled rope inside in the green boat' 出现了重复介词（payload 存为 'a coiled rope inside'）。目标（漂浮的绿色小船，上部中间）正确。 | Ref: Add a coiled rope inside the green boat floating near the upper middle.<br>No-ref: Add a coiled rope inside the selected boat.<br>payload -> 'a coiled rope' | 目视 |

#### `v2-sa_3633416`（#570，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 属性值问题（无变化/含糊） | noref+point | Tint the tall wooden-framed window to the right of the central doorway pale blue. | “Tint the tall wooden-framed window ... pale blue”：mask 覆盖整个窗户（棕色木框 + 玻璃）；不清楚应该是窗框还是玻璃变成浅蓝色。 | Ref: Change the color of the wooden frame of the tall window to the right of the central doorway to pale blue.<br>No-ref: Change the color of the frame of the selected window to pale blue. | 目视 |

#### `v2-sa_3650367`（#572，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | replace 实为属性修改 | ref+point | Replace the blue banner on the left wall with a blue banner reading STADIUM ENTRANCE in white. | U1 将左墙上的蓝色 CBF/BRASIL 横幅替换为同类型的另一条蓝色横幅,只是把印刷文字改为“STADIUM ENTRANCE”。类别/结构不变;这是内容/文字编辑。 | Ref: Replace the blue banner on the left wall with a large round stadium clock.<br>No-ref: Replace the selected banner with a large round stadium clock.<br>或保留为 attribute/文字编辑:“Change the text on the blue banner on the left wall to STADIUM ENTRANCE in white.” | 目视 |

#### `v2-sa_3689823`（#577，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | mask 质量 | noref+box | Remove the round sign on the red building at the right. | 圆形标牌的 mask（box 2138-2272）有参差的碎片溢出到蓝色路名牌上，遮住了其左上部分（在 U3 放大图中可见）。圆形标牌本身被完整覆盖，因此目标仍然清楚。 | 裁掉覆盖在圆形标牌前方蓝色路名牌（Maipu/C103）上的 mask 碎片。 | 目视 |

#### `v2-sa_3792618`（#593，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | mask 质量 | noref+point | Add a strand of warm-white fairy lights on the balcony railing above the doorway. | U4 栏杆 mask(box [1544,0,1982,363])是覆盖整个阳台开口的填充区域:栏杆条加上其后的落地窗、窗帘和墙壁。只有花被挖除。栏杆本身是细竖条。作为 add 编辑的锚点定位器尚可接受,但对背景覆盖过多。 | 可选:将 mask 细化为仅含栏杆条和顶部横栏。 | 目视 |

#### `v2-sa_3817024`（#596，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 措辞/文法/描述细节 | noref+mask | Replace the striped shirt on the passing man with a pale blue linen shirt. | 路过男子的衬衫（box x 1274-1385）是白/灰色小格纹（gingham）图案，不是条纹；他是唯一的路人，因此目标仍可识别。 | Ref: Replace the checked shirt on the passing man with a pale blue linen shirt.<br>ZH 条纹 -> 格纹 | 目视 |

#### `v2-sa_3825192`（#599，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 指代歧义 | noref+point | Remove the tall blue sign near the center foreground. | U3 mask 是立柱上一块小的浅蓝色雪道图/信息牌(box x883-923, y926-986);其正下方是一面高的蓝色羽毛旗/横幅,更符合 'tall blue sign',所以 REF 可能把人误导到横幅上。 | Ref: Remove the small blue-and-white map board on a post near the center, above the blue banner. | 目视 |

#### `v2-sa_388235`（#606，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | mask 质量 | ref+none | Change the color of the black hat at the lower right to burgundy. | U2 mask（右侧黑帽，x 983-1228）在 x 517-519 处有一条 3 像素宽的多余碎片，与 U1 的帽子 mask 重叠约 10 像素，使 U2 的 box 膨胀为 [517,1682,1229,1836]，从而包含了 U1 的帽子。针对 U2 的 box 定位器会覆盖两顶帽子。 | 删除多余碎片；U2 的 box 应约为 [983,1682,1229,1836] | 目视 |

#### `v2-sa_4003889`（#617，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 措辞/文法/描述细节 | ref+box | Change the color of the navy T-shirt on the crouching person in blue jeans at the front to gray. | REF/ZH 称蹲着的男子的 T 恤为 'navy'，但图中（box [886,725,1143,923]）看起来是黑色；目标仍然唯一（前景穿蓝色牛仔裤的蹲姿男子）。 | Ref: Change the color of the black T-shirt on the crouching person in blue jeans at the front to gray.<br>ZH: 黑色T恤 | 目视 |

#### `v2-sa_4216048`（#639，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | mask 质量 | ref+mask | Remove the low horizontal power line behind the airplane. | 电线 mask（box [2242,268,2743,330]）只覆盖了右侧铁塔附近一根细线的一小段；这根线几乎看不见，很可能延伸到 mask 之外，导致移除难以验证。 | 沿电线整个可见范围延伸 mask，或删除该单元 | 目视 |

#### `v2-sa_4276122`（#643，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small blue star patch on the front on the yellow baseball cap. | 'Add a small blue star patch on the front on the yellow baseball cap' 里 'on' 重复了；位置 'front' 被并入了 payload 字符串（spec payload='a small blue star patch on the front', site=''）。 | Ref: Add a small blue star patch on the front of the yellow baseball cap.<br>No-ref: Add a small blue star patch on the front of the selected cap.<br>spec: payload='a small blue star patch', site='front' | 目视 |

#### `v2-sa_4371531`（#649，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | mask 质量 | noref+mask | Replace the tall H&M billboard on the left with a blue travel poster showing a snowy mountain. | U1 mask 只覆盖 H&M 广告牌的正面。相邻的、展示同一广告活动的侧面被排除在外，右边缘沿线还有一些零散的小 mask 碎片（box 因此延伸到 y=806）。 | 清理零散碎片；可选地写明 'the front face of the tall H&M billboard' | 目视 |

#### `v2-sa_4561526`（#674，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 属性值问题（无变化/含糊） | ref+box | Change the color of the rightmost orange-topped lifeboat to white. | 救生艇船体本来就是白色；只有橙色顶篷/顶部不同，因此“Change the color of the ... lifeboat to white”不清楚是哪个部分改变，可能被判定为无操作。 | Ref: Change the color of the orange canopy of the rightmost orange-topped lifeboat to white.<br>No-ref: Change the color of the orange canopy of the selected lifeboat to white. | 目视 |
| U3 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small black number 4 on its hull on the lifeboat immediately left of the rightmost one. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small black number 4 on the hull of the lifeboat immediately left of the rightmost one.<br>No-ref: Add a small black number 4 on the hull of the selected lifeboat. | 文本 |

#### `v2-sa_4644538`（#679，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | mask 质量 | noref+mask | Replace the yellow TOUR & LAUNDRY sign with a yellow sign reading TOURIST INFO. | 黄色标牌的 U2 mask 在左下方有一处突出（约 x424-450,y740-790 src），覆盖了标牌旁边部分悬挂装饰物/邻近物体。 | 将 mask 修剪为仅黄色标牌板 | 目视 |
| U3 | 轻微 | 措辞/文法/描述细节 | ref+none | Add a small white number 5 decal on its front panel on the scooter facing the camera. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small white number 5 decal on the front panel of the scooter facing the camera.<br>No-ref: Add a small white number 5 decal on the front panel of the selected scooter. | 文本 |

#### `v2-sa_4791630`（#691，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 措辞/文法/描述细节 | noref+point | Change the color of the metal chair behind the round table to pale blue. | 被 mask 的银色金属椅(box [944,1704,1246,2250])位于圆形大理石桌的左/前侧,更靠近镜头,而不是在桌子后面;右下角还有另一把部分可见的灰色椅子。目标仍可恢复,但 'behind' 不准确。 | Ref: Change the color of the silver metal chair at the left of the round table to pale blue. | 目视 |

#### `v2-sa_4880528`（#699，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | 方位/序数/实例指代错误 | ref+mask | Remove the yellow-flowered shrub in the pot behind the orange flowers. | 黄花灌木盆(box [1317,1183,1412,1288])位于橙花盆(U1,x~1686-1778)的左侧,仅比它略远;“behind the orange flowers”表述不够准确,但该实例是唯一的(只有一个黄花盆)。 | Ref: Remove the yellow-flowered shrub in the pot left of the orange-flowered shrub. | 目视 |

#### `v2-sa_5044363`（#717，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代歧义 | noref+point | Replace the pale pink dress on the woman at the lower right with a navy sleeveless dress. | 右下方有两位穿浅粉色的女士：U2（无袖浅粉连衣裙，box 中心 0.81W）以及更靠右（~0.92W）穿白上衣粉裙子的另一位。“the woman at the lower right”区分度较弱；“dress”有帮助，但 REF 可以更严谨。 | Ref: Replace the pale pink sleeveless dress on the woman next to the floral-dress woman at the lower right with a navy sleeveless dress. | 目视 |
| U3 | 轻微 | 属性值问题（无变化/含糊） | ref+box | Remove the gray handbag carried by the woman in a light gray dress. | U3 的包(box [1446,711,1508,787])是米色/卡其色帆布手提袋,却被描述为 'gray handbag'。 | Ref: Remove the beige tote bag carried by the woman in a light gray dress.<br>ZH: 移除浅灰色连衣裙女子提着的米色手提袋。 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small white CAFE sign along its front edge on the striped awning at the upper right. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small white CAFE sign along the front edge of the striped awning at the upper right.<br>No-ref: Add a small white CAFE sign along the front edge of the selected awning. | 文本 |

#### `v2-sa_5048336`（#718，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 方位/序数/实例指代错误 | noref+box | Remove the red shopping bag behind the towel-wrapped man. | 红白相间的包（x~0.46W）挂在裹毛巾男子的右边、穿迷彩服男子的左边，靠近栏杆柱；它不在裹毛巾男子身后。它是唯一的红色包，因此目标仍可识别。 | Ref: Remove the red shopping bag beside the man in camouflage, above the railing post. | 目视 |

#### `v2-sa_5232925`（#733，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| case | 轻微 | 多单元同一物理对象/相互冲突 |  |  | 四个单元中的三个(U1 黑色大衣、U2 白色购物袋、U3 黑青绿相间的包)属于同一位最近的女子;两个包都挂在她手上且相互重叠(U3 box [403,1209,478,1308] 与 U2 box [364,1245,438,1377] 重叠),因此编辑会相互影响。 | 考虑删除 U2 或 U3,并在广场其他位置选择一个物体(例如左侧的婴儿车)。 | 目视 |

#### `v2-sa_5252263`（#735，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代歧义 | ref+mask | Replace the tall young tree left of the bridge tower with a young cherry tree. | 塔楼左侧更远处（cx~0.08W）还有另一棵带支撑的幼树；U2 是最靠近塔楼的那棵（cx=0.28W）。'tall' 起到部分区分作用。 | Ref: Replace the tall young tree just left of the bridge tower with a young cherry tree. | 目视 |
| U3 | 轻微 | 属性值问题（无变化/含糊） | noref+box | Change the color of the wooden railing in the lower-left foreground to white. | 左下前景的 U3 栏杆是带开口的深绿色；看起来并不明显是木质的。 | Ref: Change the color of the dark green railing in the lower-left foreground to white. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a small bronze information plaque on its visible lower face on the concrete bridge tower. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small bronze information plaque on the visible lower face of the concrete bridge tower.<br>No-ref: Add a small bronze information plaque on the visible lower face of the selected tower. | 文本 |

#### `v2-sa_5390926`（#747，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | 指代类别与 mask 不符 | ref+box | Replace the blue SUV behind the parking meter with a white compact van. | 停车计时器后方被 mask 的蓝色汽车（x~0.49W）是一辆小型蓝色掀背车（Skoda 风格），不是 SUV；目标仍可识别为那辆蓝色汽车。 | Ref: Replace the blue hatchback behind the parking meter with a white compact van.<br>No-ref: Replace the selected car with a white compact van. | 目视 |

#### `v2-sa_5394116`（#748，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | 指代类别与 mask 不符 | noref+box | Add a small white star patch on the maroon hood on the leftmost foreground boy. | mask（box 397-803 x 1301-1439）只覆盖了最左侧男孩藏青色兜帽的栗色内衬；外层兜帽是藏青色。“The maroon hood”对该部位的称呼略有偏差，不过目标仍可识别。 | Ref: Add a small white star patch on the maroon hood lining of the leftmost foreground boy's navy hoodie.<br>No-ref: Add a small white star patch on the selected hood lining. | 目视 |

#### `v2-sa_5399663`（#749，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | mask 质量 | noref+point | Replace the phone-repair sign with the yellow lettering at the left with a black sign reading PHONE REPAIR. | U2 box [103,742,229,860] 跨越黄色手机/工具图标以及箭头形的 REMONT TELEFONOV 牌子,但 mask 只勾勒了箭头牌;图标牌(同一手机维修招牌的一部分)被排除,因此替换 "the phone-repair sign" 会把图标留下。 | Ref: Replace the arrow-shaped phone-repair sign with yellow lettering at the left with a black sign reading PHONE REPAIR.<br>or extend mask to include the phone icon plate above the arrow | 目视 |

#### `v2-sa_5478678`（#753，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | replace 实为属性修改 | ref+none | Replace the cream sign on the wooden donation box with a brass plaque reading DONATIONS. | 被 mask 的物体是木柜上写有泰文的浅奶油色纸牌；替换为“a brass plaque reading DONATIONS”仍是同一位置的扁平标牌，主要区别在材质和文字（属边界 attribute）。 | Ref: Replace the cream sign on the wooden donation box with a small framed photograph of a lotus flower.<br>No-ref: Replace the selected sign with a small framed photograph of a lotus flower. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+mask | Add a small red flower sticker on its front edge on the front display table. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small red flower sticker on the front edge of the front display table.<br>No-ref: Add a small red flower sticker on the front edge of the selected table. | 文本 |

#### `v2-sa_5505559`（#757，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代歧义 | noref+mask | Remove the largest pale rock in the cluster below the right tower. | 被 mask 的岩石（box [1564,1357,1644,1409]）位于右塔下方一小簇大小相近的浅色岩石中（两侧邻居大小相当，例如紧靠右边的那块）；'largest' 在视觉上并不明确。 | Ref: Remove the pale rock just left of center in the small cluster below the right tower. | 目视 |

#### `v2-sa_5589230`（#765，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代歧义 | ref+point | Remove the round turquoise GINO sign at the left. | 左侧建筑上有两块圆形青绿色 GINO 招牌。被 mask 的那块（box [369,1351,437,1417]）是更大更近的，另一块较小的挂在其右侧约 150px、高度相近处。'At the left' 只有理解为 'leftmost' 才成立。 | Ref: Remove the larger, leftmost round turquoise GINO sign. | 目视 |

#### `v2-sa_5614303`（#767，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 措辞/文法/描述细节 | noref+point | Change the color of the gray yoga mat under the nearest man to teal. | 站在被 mask 的灰色垫子上的是一名穿蓝色球衣的小男孩,而不是成年男子(ZH 也写作 男子)。垫子本身 mask 正确,仍可识别为最近的灰色垫子。 | Ref: Change the color of the gray yoga mat under the boy in the blue jersey in the foreground to teal.<br>ZH:将前景蓝色球衣男孩脚下的灰色瑜伽垫的颜色改为蓝绿色。 | 目视 |

#### `v2-sa_564503`（#771，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U4 | 轻微 | mask 质量 | ref+mask | Replace the small framed picture left of the stringed instrument with a framed floral still-life painting. | U4 相框画 mask 在画出的椭圆内部有若干分散的孔洞（在人物脸部/手附近），因此 mask 未完全覆盖画面。 | 填补 U4 mask 内部的孔洞 | 目视 |

#### `v2-sa_5830026`（#790，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | mask 质量 | noref+mask | Add a white lace curtain in the ground-floor white-framed window beside the hanging basket. | U2 窗户 mask 向右延伸，包裹了悬挂的花篮和窗框旁的一条墙面，因此包含了相邻物体（花篮）。 | 将 mask 收紧到白色窗框和玻璃，排除悬挂的花篮 | 目视 |

#### `v2-sa_5851358`（#792，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 方位/序数/实例指代错误 | ref+box | Change the color of the taller streetlamp behind the truck to dark blue. | U2 高路灯(src x~1531-1609)立在卡车驾驶室右侧的混凝土墙之外(卡车止于 x~1390),并不在卡车后面;“taller”确实可将其与 U1 区分,因此目标仍可还原。 | Ref: Change the color of the taller streetlamp beyond the concrete wall, above the fence post right of the truck, to dark blue. | 目视 |

#### `v2-sa_590072`（#797，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | mask 质量 | noref+point | Change the color of the globe streetlamp in the left foreground to bronze. | U2 mask 有 2 个分量:除了左前景的球形路灯外,还包含背景多球灯的灯臂的一小片碎片,紧挨其灯杆(视图中约 y~515,box 右边缘)。 | remove the stray background lamp fragment from the mask | 目视 |

#### `v2-sa_5919801`（#799，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代歧义 | noref+box | Add a small white RACING decal on the raised right door of the black sports car. | 正面朝向的黑色汽车的两扇剪刀门都已抬起；U2 是图像右侧那扇，即车自身的左门。'raised right door' 按图像坐标是正确的，但可能被理解为车的右门（图像左侧）。 | Ref: Add a small white RACING decal on the image-right raised door of the black sports car. | 目视 |

#### `v2-sa_5933347`（#800，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | mask 质量 | ref+none | Change the color of the purple roof of the separate yellow building at the upper right to dark gray. | 右上角的黄色建筑有两层紫色屋顶；U3 mask（box x2073-2351, y273-366）覆盖上方主屋顶，但漏掉了其正下方的紫色屋顶裙边/檐，因此整体屋顶改色会留下一部分紫色。 | 扩展 mask 以包含下方紫色屋顶部分 | 目视 |

#### `v2-sa_5967529`（#802，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 指代歧义 | ref+box | Replace the tan hooded coat on the person near the center with a burgundy wool coat. | 被 mask 的棕褐色连帽羽绒服穿在 x~0.33W、偏中心左侧的一个人身上。U1 女子也穿着棕褐色连帽外套,且许多人站得更靠近中心。“Near the center”加“tan hooded”仍基本能识别目标。 | Ref: Replace the tan hooded puffer jacket on the person walking toward the camera, left of center, with a burgundy wool coat. | 目视 |

#### `v2-sa_6014866`（#810，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | mask 质量 | ref+mask | Replace the black shirt on the boy in the foreground with a gray polo shirt. | U3 黑衬衫 mask(box 281-554 x,1718-2157 y)延伸到底部男孩手持黑色相机处;相机似乎被包含在衬衫轮廓内。 | 从衬衫 mask 中排除手持相机。 | 目视 |

#### `v2-sa_604786`（#815，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 指代歧义 | ref+box | Change the color of the small rectangular shutter on the tower front to dark green. | 塔楼正面有若干小的矩形窗/百叶窗(左翼、上层、小通风口);被 mask 的那个(box x1329-1397)是正面山墙正下方宽的灰色双扇百叶窗。'small rectangular shutter on the tower front' 并不具有区分性。 | Ref: Change the color of the gray double shutter under the front gable of the tower to dark green. | 目视 |

#### `v2-sa_6105776`（#821，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 措辞/文法/描述细节 | ref+box | Change the color of the magenta headscarf near the center to navy blue. | 被 mask 的头巾（box x 1009-1093, y 791-928）是暗红/栗色，不是洋红色；它是中心附近唯一这样的长围巾，所以目标仍可识别。 | Ref: Change the color of the maroon headscarf near the center to navy blue.<br>ZH 洋红色 -> 酒红色 | 目视 |

#### `v2-sa_6347272`（#840，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 指代歧义 | noref+box | Remove the colorful cold-drink poster behind the customer in black. | 'the colorful cold-drink poster behind the customer in black' —— 海报(x1232-1378, y841-1003)挂在黑衣顾客(x1099-1219)的右上方,而不是正后方;但作为唯一的冻茶海报仍然唯一。 | Ref: Remove the colorful frozen-tea poster hanging above the counter to the right of the menu boards. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+point | Add a small red NEW sticker in its upper corner on the pancake poster near the right end of the menu row. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small red NEW sticker in the upper corner of the pancake poster near the right end of the menu row.<br>No-ref: Add a small red NEW sticker in the upper corner of the selected poster. | 文本 |

#### `v2-sa_6455103`（#847，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | 指代歧义 | ref+box | Remove the round potted shrub beside the black speaker stack. | 黑色音箱堆旁有两盆相似的黑盆圆形灌木(U3 在 x~590-660,另一盆紧挨其右,约 x=670-700);'the round potted shrub beside the black speaker stack' 无法指出左边那盆。 | Ref: Remove the left one of the two round potted shrubs beside the black speaker stack. | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | noref+mask | Add a small white sun emblem on its upper back on the orange T-shirt in the lower-right foreground. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small white sun emblem on the upper back of the orange T-shirt in the lower-right foreground.<br>No-ref: Add a small white sun emblem on the upper back of the selected T-shirt. | 文本 |

#### `v2-sa_6720037`（#868，扩充 #200–#868，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U1 | 轻微 | 指代歧义 | ref+none | Remove the white panel van in the center. | 四辆白/银色厢式车排成一排停放；U1（box [1537,1084,1860,1297], x=0.64W）是左起第三辆，并不明显 'in the center'。它只能凭无窗厢式货车这一点来区分，而 REF 确实提到了这一点。 | Ref: Remove the windowless white panel van, third from the left among the parked vans. | 目视 |

#### `v2-sa_6725724`（#871，扩充 #869–#944，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U3 | 轻微 | mask 质量 | ref+none | Replace the jersey on the fan at the left with a plain white polo shirt. | 左侧球迷的 U3 球衣 mask(box [190,544,745,1431])在图像右侧延伸到了从他肩上披下的深绿色墨西哥国旗/披风上(源图约 x 650-745),而不仅是球衣。 | 将 mask 裁剪为球衣;排除披挂的旗帜 | 目视 |
| U4 | 轻微 | 措辞/文法/描述细节 | ref+mask | Add a small blue information sign on its pole on the streetlamp in the left background. | add 指令含悬空 its/their（协议要求 payload 不含悬空 its） | Ref: Add a small blue information sign on the pole of the streetlamp in the left background.<br>No-ref: Add a small blue information sign on the pole of the selected streetlamp. | 文本 |

#### `v2-sa_7650355`（#948，扩充尾段 #945–#1083，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 方位/序数/实例指代错误 | noref+point | Replace the box near the lower left with a wooden crate. | 被 mask 的黄色盒子是安装在左墙中等高度（0.06W,0.58H）、踏板车上方的一个小盒子，并不 'near the lower left'；它是唯一这样的盒子，因此目标仍可识别。 | Ref: Replace the small yellow box mounted on the left wall above the scooter with a wooden crate. | 目视 |
| U4 | 轻微 | mask 质量 | noref+mask | Add a striped awning on the building on the right. | 建筑 mask（box 1672-2250，整个高度）参差不齐：顶部和边缘有许多斑点碎片，现有灰色雨篷和墙挂式电表周围有孔洞，雨篷处切得很粗糙。建筑顶部本来就有一个雨篷，因此 'add a striped awning on the building' 没有给出放置位置。 | Ref: Add a striped awning above the doorway of the building on the right.<br>No-ref: Add a striped awning above the doorway of the selected building.<br>清理 mask（填补孔洞，去掉斑点） | 目视 |

#### `v2-sa_7773451`（#959，扩充尾段 #945–#1083，最严重：轻微）

| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |
|---|---|---|---|---|---|---|---|
| U2 | 轻微 | 指代歧义 | noref+mask | Replace the trash can at the lower left with a blue recycling bin. | 'the trash can at the lower left' —— 除了被 mask 的大型黑色带轮垃圾桶(x254-426),紧挨它还有第二个较小的黑色垃圾桶(原图约 x440-520)。 | Ref: Replace the large black wheeled trash can at the lower left with a blue recycling bin. | 目视 |
| U3 | 轻微 | Ref/No-ref 不等价 | ref+none | Remove the person at the far left. | REF 写 'the person at the far left'，而 NOREF 写 'the selected man'（scope 'man'）；ZH 用的是 人物。 | Ref: Remove the man sitting at the far left.<br>No-ref: Remove the selected man. | 目视 |

### 4.4 仅有自动文本规则发现的轻微问题的 case（40 个）

以下 case 目视复核未记录问题，只有 add 指令悬空 its 或笼统 payload 的文本问题（未单独目视判定，但属于协议明确禁止的写法）。

| case | U | 当前指令 (Ref) | 问题 | 建议 |
|---|---|---|---|---|
| `v2-sa_2084860` | U1 | Add a string of warm-white lights winding along the stem and leaves of the leaf-shaped decoration and its long support on the right. | 悬空 its/their | placement.site 单独存储，渲染为 "<relation> the <site> of <anchor>" |
| `v2-sa_3804406` | U2 | Add a small opening-hours sticker in its lower corner on the tall window below the right-hand McDonald’s logo. | 悬空 its/their | Ref: Add a small opening-hours sticker in the lower corner of the tall window below the right-hand McDonald’s logo.<br>No-ref: Add a small opening-hours sticker in the lower corner of the selected window. |
| `v2-sa_396678` | U4 | Add a white gull perched on its canopy on the large straw parasol above the foreground loungers. | 悬空 its/their | Ref: Add a white gull perched on the canopy of the large straw parasol above the foreground loungers.<br>No-ref: Add a white gull perched on the canopy of the selected parasol. |
| `v2-sa_4106294` | U3 | Add a small red number 7 decal on its bow on the jet ski on the right. | 悬空 its/their | Ref: Add a small red number 7 decal on the bow of the jet ski on the right.<br>No-ref: Add a small red number 7 decal on the bow of the selected jet ski. |
| `v2-sa_4399039` | U4 | Add a small yellow star sticker in its lower corner on the white EVIDENCE BASED POLICY placard. | 悬空 its/their | Ref: Add a small yellow star sticker in the lower corner of the white EVIDENCE BASED POLICY placard.<br>No-ref: Add a small yellow star sticker in the lower corner of the selected placard. |
| `v2-sa_4417376` | U4 | Add a small price label on its outer side on the white pot near the center-left. | 悬空 its/their | Ref: Add a small price label on the outer side of the white pot near the center-left.<br>No-ref: Add a small price label on the outer side of the selected pot. |
| `v2-sa_4435260` | U3 | Add a small yellow number 12 tag on its handle on the shopping cart in front of the woman in pink. | 悬空 its/their | Ref: Add a small yellow number 12 tag on the handle of the shopping cart in front of the woman in pink.<br>No-ref: Add a small yellow number 12 tag on the handle of the selected cart. |
| `v2-sa_4557102` | U4 | Add a small white fabric patch on its upper back on the beige shirt on the man behind the table. | 悬空 its/their | Ref: Add a small white fabric patch on the upper back of the beige shirt on the man behind the table.<br>No-ref: Add a small white fabric patch on the upper back of the selected shirt. |
| `v2-sa_4686433` | U4 | Add a small white number 5 decal on its front panel on the red motorcycle on the right. | 悬空 its/their | Ref: Add a small white number 5 decal on the front panel of the red motorcycle on the right.<br>No-ref: Add a small white number 5 decal on the front panel of the selected motorcycle. |
| `v2-sa_4812017` | U4 | Add a small red OPEN sticker at its bottom on the tall white sign with red Chinese characters behind the taxi. | 悬空 its/their | Ref: Add a small red OPEN sticker at the bottom of the tall white sign with red Chinese characters behind the taxi.<br>No-ref: Add a small red OPEN sticker at the bottom of the selected sign. |
| `v2-sa_4841012` | U3 | Add a small white opening-hours sticker near its bottom on the glass of the left entrance door. | 悬空 its/their | Ref: Add a small white opening-hours sticker near the bottom of the glass of the left entrance door.<br>No-ref: Add a small white opening-hours sticker near the bottom of the selected glass. |
| `v2-sa_4908624` | U3 | Add a small white star patch on its chest on the brown T-shirt on the boy at the right. | 悬空 its/their | Ref: Add a small white star patch on the chest of the brown T-shirt on the boy at the right.<br>No-ref: Add a small white star patch on the chest of the selected T-shirt. |
| `v2-sa_4911053` | U4 | Add a small embroidered flower on its upper back on the brown jacket on the woman at the left. | 悬空 its/their | Ref: Add a small embroidered flower on the upper back of the brown jacket on the woman at the left.<br>No-ref: Add a small embroidered flower on the upper back of the selected jacket. |
| `v2-sa_4966808` | U1 | Add a small bee at its center on the large orange flower in the foreground. | 悬空 its/their | Ref: Add a small bee at the center of the large orange flower in the foreground.<br>No-ref: Add a small bee at the center of the selected flower. |
| `v2-sa_5052360` | U2 | Add a small white CLASSIC CARS banner along its front edge on the blue canopy at the right. | 悬空 its/their | Ref: Add a small white CLASSIC CARS banner along the front edge of the blue canopy at the right.<br>No-ref: Add a small white CLASSIC CARS banner along the front edge of the selected canopy. |
| `v2-sa_5097246` | U4 | Add a small white patch on its upper back on the light blue jacket on the right platform. | 悬空 its/their | Ref: Add a small white patch on the upper back of the light blue jacket on the right platform.<br>No-ref: Add a small white patch on the upper back of the selected jacket. |
| `v2-sa_5099188` | U4 | Add a small white TAXI sign on its roof on the silver sedan behind the dark green car. | 悬空 its/their | Ref: Add a small white TAXI sign on the roof of the silver sedan behind the dark green car.<br>No-ref: Add a small white TAXI sign on the roof of the selected sedan. |
| `v2-sa_5129234` | U3 | Add a small white OPEN decal in its lower corner on the large window at the far right of the brick building. | 悬空 its/their | Ref: Add a small white OPEN decal in the lower corner of the large window at the far right of the brick building.<br>No-ref: Add a small white OPEN decal in the lower corner of the selected window. |
| `v2-sa_5192457` | U4 | Add a small white ICE CREAM banner along its edge on the beige umbrella behind the foreground minivan. | 悬空 its/their | Ref: Add a small white ICE CREAM banner along the edge of the beige umbrella behind the foreground minivan.<br>No-ref: Add a small white ICE CREAM banner along the edge of the selected umbrella. |
| `v2-sa_5258379` | U2 | Add a small white fleet-number 12 decal near its bottom on the sliding side door of the yellow DHL van. | 悬空 its/their | Ref: Add a small white fleet-number 12 decal near the bottom of the sliding side door of the yellow DHL van.<br>No-ref: Add a small white fleet-number 12 decal near the bottom of the selected door. |
| `v2-sa_5385604` | U4 | Add a small black cycling computer at its center on the drop handlebar at the right edge. | 悬空 its/their | Ref: Add a small black cycling computer at the center of the drop handlebar at the right edge.<br>No-ref: Add a small black cycling computer at the center of the selected handlebar. |
| `v2-sa_5561778` | U4 | Add a red ribbon around its neck on the left-hand guardian-beast statue beside the central red door. | 悬空 its/their | Ref: Add a red ribbon around the neck of the left-hand guardian-beast statue beside the central red door.<br>No-ref: Add a red ribbon around the neck of the selected statue. |
| `v2-sa_5563395` | U2 | Add a small white plate at its front-right corner on the wooden table beneath the grill. | 悬空 its/their | Ref: Add a small white plate at the front-right corner of the wooden table beneath the grill.<br>No-ref: Add a small white plate at the front-right corner of the selected table. |
| `v2-sa_5636423` | U3 | Add a small white star decal in its lower corner on the upper-right window above the bookshop. | 悬空 its/their | Ref: Add a small white star decal in the lower corner of the upper-right window above the bookshop.<br>No-ref: Add a small white star decal in the lower corner of the selected window. |
| `v2-sa_56735` | U3 | Add a small embroidered gold star on its upper back on the cream cloak on the rightmost person. | 悬空 its/their | Ref: Add a small embroidered gold star on the upper back of the cream cloak on the rightmost person.<br>No-ref: Add a small embroidered gold star on the upper back of the selected cloak. |
| `v2-sa_5686312` | U2 | Add a small white number 4 plaque on its pole on the globe streetlamp beside the middle of the stairs. | 悬空 its/their | Ref: Add a small white number 4 plaque on the pole of the globe streetlamp beside the middle of the stairs.<br>No-ref: Add a small white number 4 plaque on the pole of the selected streetlamp. |
| `v2-sa_5694648` | U4 | Add a small black TOURS sign along its rear edge on the carriage canopy. | 悬空 its/their | Ref: Add a small black TOURS sign along the rear edge of the carriage canopy.<br>No-ref: Add a small black TOURS sign along the rear edge of the selected canopy. |
| `v2-sa_5761646` | U1 | Add a small white inspection decal in its lower corner on the upper trapezoidal window on the left side of the glazed nose. | 悬空 its/their | Ref: Add a small white inspection decal in the lower corner of the upper trapezoidal window on the left side of the glazed nose.<br>No-ref: Add a small white inspection decal in the lower corner of the selected window. |
| `v2-sa_5794853` | U1 | Add a small white CITY SHUTTLE decal on its side panel on the turquoise minibus in the left foreground. | 悬空 its/their | Ref: Add a small white CITY SHUTTLE decal on the side panel of the turquoise minibus in the left foreground.<br>No-ref: Add a small white CITY SHUTTLE decal on the side panel of the selected minibus. |
| `v2-sa_5799580` | U4 | Add a row of small amber reflectors along its top on the narrow median between the bus and the car. | 悬空 its/their | Ref: Add a row of small amber reflectors along the top of the narrow median between the bus and the car.<br>No-ref: Add a row of small amber reflectors along the top of the selected median. |
| `v2-sa_5884999` | U4 | Add a small blue FISHING PERMITTED sign on its pole on the tall streetlamp at the right. | 悬空 its/their | Ref: Add a small blue FISHING PERMITTED sign on the pole of the tall streetlamp at the right.<br>No-ref: Add a small blue FISHING PERMITTED sign on the pole of the selected streetlamp. |
| `v2-sa_6004886` | U4 | Add a small gold OPEN sticker in its lower-right corner on the square Body Line sign. | 悬空 its/their | Ref: Add a small gold OPEN sticker in the lower-right corner of the square Body Line sign.<br>No-ref: Add a small gold OPEN sticker in the lower-right corner of the selected sign. |
| `v2-sa_6010367` | U3 | Add a small silver reflective patch on its side pocket on the large backpack on the front-left hiker. | 悬空 its/their | Ref: Add a small silver reflective patch on the side pocket of the large backpack on the front-left hiker.<br>No-ref: Add a small silver reflective patch on the side pocket of the selected backpack. |
| `v2-sa_607590` | U3 | Add a folded red cloth on its seat on the stone bench in the lower-left foreground. | 悬空 its/their | Ref: Add a folded red cloth on the seat of the stone bench in the lower-left foreground.<br>No-ref: Add a folded red cloth on the seat of the selected bench. |
| `v2-sa_6204662` | U3 | Add a small hanging flower box at its center on the long balcony railing on the left-hand market building. | 悬空 its/their | Ref: Add a small hanging flower box at the center of the long balcony railing on the left-hand market building.<br>No-ref: Add a small hanging flower box at the center of the selected railing. |
| `v2-sa_6208318` | U4 | Add a small yellow safety sticker near its right end on the long foreground escalator handrail. | 悬空 its/their | Ref: Add a small yellow safety sticker near the right end of the long foreground escalator handrail.<br>No-ref: Add a small yellow safety sticker near the right end of the selected handrail. |
| `v2-sa_6391751` | U4 | Add a small hanging flower box at its center on the balcony railing on the red building. | 悬空 its/their | Ref: Add a small hanging flower box at the center of the balcony railing on the red building.<br>No-ref: Add a small hanging flower box at the center of the selected railing. |
| `v2-sa_6487910` | U4 | Add a small white reflective strip across its back on the black jacket on the pedestrian beneath the Citibank sign. | 悬空 its/their | Ref: Add a small white reflective strip across the back of the black jacket on the pedestrian beneath the Citibank sign.<br>No-ref: Add a small white reflective strip across the back of the selected jacket. |
| `v2-sa_6624578` | U4 | Add a small blue tourist-information sign on its pole on the streetlamp at the far right. | 悬空 its/their | Ref: Add a small blue tourist-information sign on the pole of the streetlamp at the far right.<br>No-ref: Add a small blue tourist-information sign on the pole of the selected streetlamp. |
| `v2-sa_6641776` | U1 | Add a small silver bell on its handlebar on the bicycle leaning against the wall. | 悬空 its/their | Ref: Add a small silver bell on the handlebar of the bicycle leaning against the wall.<br>No-ref: Add a small silver bell on the handlebar of the selected bicycle. |

## 5. 系统性改进建议

### 5.1 应在构建管线中新增的校验器

1. **方位/序数校验**：解析 ref 中目标头名词自身的方位词（排除 “left of X” 等关系短语），与 box 中心比较；更关键的是利用 dense annotation 中同类别其他实例，验证 “leftmost/second from left/nearest/upper” 在同类候选中成立；不成立直接拒绝。本次 115 条自动命中中 78 条被确认。
2. **人物层级校验**：scope/category ∈ 人物词时禁止 attribute/replace（除非 target_part 指明服装）；replace payload 为服装而 target 为人时拒绝；add 锚点为整个人时必须给出服装/身体部位并改用对应 mask。同时校验 `category=person` 的 mask 是否真的是整人（用 dense 标注类别或人体/服装分割模型），本批多例 “person” 实为衣服。
3. **replace 类别变化校验**：payload 头名词与原 scope 同义/同类且修饰词仅为颜色/材质/图案/文字时，强制转为 attribute 或要求换成不同品类/结构；payload 无名词（“with blue”）直接拒绝。
4. **无变化（no-op）校验**：在 mask 内测量主色（Lab 均值/主导色），与 attribute 目标色或 replace payload 颜色比较，ΔE 过小即拒绝（本次发现白车改白、黑灯改黑、红敞篷换红敞篷、已有头盔再加头盔等）。
5. **ref 名词—mask 一致性校验**：用 VLM/开放词汇检测在 mask 裁剪上验证 ref 头名词与颜色词（“officer”→衬衫、“bottle”→水母、“sign”→灯笼等均可被拦截）；与 dense 标注的 source_category 交叉检查。
6. **歧义校验**：统计 dense 标注中与目标同类别、且满足 ref 修饰语的实例数；>1 时要求加区分信息，尤其对 `ref+none`（纯文本定位）单元强制要求唯一性复核。
7. **独立性校验**：利用 associations_json 及 mask 空间关系（服装/配件 mask 是否落在某人物 mask 或其外扩范围内）判断两个单元是否属于同一人/同一车；同一人身上的衬衫+袖子、帽子+包都应拒绝；检查单元间编辑依赖（删除的人手持另一单元目标）。
8. **不可执行编辑规则**：禁止 remove 穿着中的上衣/外套/裙子（除非人台）、整栋建筑/桥/屋顶等大结构、载人的婴儿车/轮椅；add payload 必须是实物，禁止 glow/light effect；add 到已占用座椅、已有同类物（已有坐垫/头盔/花盆）时拒绝。
9. **模板检测**：对 “the <noun> at/near the <方位>” 型 ref、generic payload（a small logo/badge/sign）、generic evidence（“是四个不同对象”）设阈值报警；一个 case 内多数单元为模板时整 case 退回人工撰写。
10. **文本规范**：add 渲染器把 site 写成 “<relation> the <site> of <anchor>”，禁止悬空 its；中文由同一 spec 渲染并做颜色/方位/数量/操作一致性检查。

### 5.2 流程建议

- 审核记录要与实际一致：尾段 2.5.0-draft 记录的 evidence/protection 为泛化模板，却与其他 case 同样标为 `ai_direct_visual` 并计入“全部经视觉审核”。建议区分“模板草稿”与“已逐图复核”，未复核者不得进入正式集合。
- 每次修订后重新生成审图（原图 + 各 U 轮廓 + 局部放大）并逐 U 复核“ref 是否只指向该 mask”；对纯 ref 单元要求复核者在不看 mask 的情况下先按 ref 圈出目标，再与 mask 比对（盲测一致性）。
- 引入独立人工抽检（至少每 20 case 抽 1 个，尾段全检），并在 `known_issues.json` 中登记本报告的阻断项。
- replace 与 attribute 的边界、颜色词标准、方位词（图像坐标 vs 身体左右）写入撰写检查表。

### 5.3 正式评测前建议排除/返工的 case

- **必须排除（直至修复并复核）**：所有含阻断问题的 case（158 个，见 4.1 节）。
- **建议整体退回重写**：尾段 #945–#1083 全部 139 个 case（模板化、137/139 有严重及以上问题）；#869–#944 的 76 个 case 建议逐条复核重写（73/76 有严重及以上问题）。
- 两者并集共 **204** 个 case 建议暂不进入正式评测；在此之外，含“严重”问题的 case 应在修订后再评测，或在报告中单独标注。
- 若需立即评测，可用的“相对干净”子集为：无任何阻断/严重问题且不在尾段的 case，共 572 个（仍可能含轻微措辞问题）。

含阻断问题的 case（158 个）：

`v2-sa_7103552`, `v2-sa_1580699`, `v2-sa_719433`, `v2-sa_1539716`, `v2-sa_1980337`, `v2-sa_2194487`, `v2-sa_7725244`, `v2-sa_10602261`, `v2-sa_10631376`, `v2-sa_1112483`, `v2-sa_2734741`, `v2-sa_2981106`, `v2-sa_3662681`, `v2-sa_4441086`, `v2-sa_4582303`, `v2-sa_5072835`, `v2-sa_5074342`, `v2-sa_538938`, `v2-sa_5405364`, `v2-sa_626400`, `v2-sa_6283149`, `v2-sa_6534458`, `v2-sa_6665557`, `v2-sa_6769026`, `v2-sa_6776835`, `v2-sa_6779549`, `v2-sa_6791309`, `v2-sa_679629`, `v2-sa_6823812`, `v2-sa_6850445`, `v2-sa_6888719`, `v2-sa_6895502`, `v2-sa_6896269`, `v2-sa_6935352`, `v2-sa_6937647`, `v2-sa_6943290`, `v2-sa_6977563`, `v2-sa_7052077`, `v2-sa_7116219`, `v2-sa_7125342`, `v2-sa_7191982`, `v2-sa_7205265`, `v2-sa_720948`, `v2-sa_7229007`, `v2-sa_7231402`, `v2-sa_7237977`, `v2-sa_7247537`, `v2-sa_725238`, `v2-sa_7279175`, `v2-sa_7311948`, `v2-sa_7362739`, `v2-sa_7365220`, `v2-sa_7381987`, `v2-sa_7420848`, `v2-sa_7448541`, `v2-sa_7452479`, `v2-sa_7464946`, `v2-sa_7470032`, `v2-sa_7493523`, `v2-sa_7494564`, `v2-sa_7506005`, `v2-sa_7522810`, `v2-sa_7542458`, `v2-sa_7563964`, `v2-sa_7567943`, `v2-sa_7650202`, `v2-sa_7677069`, `v2-sa_7698269`, `v2-sa_7716977`, `v2-sa_77343`, `v2-sa_7735833`, `v2-sa_777091`, `v2-sa_7797481`, `v2-sa_7810159`, `v2-sa_7835850`, `v2-sa_7854521`, `v2-sa_7892712`, `v2-sa_7945941`, `v2-sa_7985091`, `v2-sa_7991555`, `v2-sa_8012456`, `v2-sa_8018927`, `v2-sa_8043384`, `v2-sa_805201`, `v2-sa_8064958`, `v2-sa_807381`, `v2-sa_8092195`, `v2-sa_8099809`, `v2-sa_8188123`, `v2-sa_8219544`, `v2-sa_8243132`, `v2-sa_8290161`, `v2-sa_8319146`, `v2-sa_8321304`, `v2-sa_834249`, `v2-sa_8356934`, `v2-sa_8364417`, `v2-sa_8364723`, `v2-sa_838336`, `v2-sa_8403002`, `v2-sa_8430103`, `v2-sa_8430740`, `v2-sa_8448822`, `v2-sa_8489034`, `v2-sa_8532764`, `v2-sa_8586145`, `v2-sa_8608311`, `v2-sa_8680793`, `v2-sa_8731521`, `v2-sa_876819`, `v2-sa_8802184`, `v2-sa_8809691`, `v2-sa_8830987`, `v2-sa_886183`, `v2-sa_8871336`, `v2-sa_8874867`, `v2-sa_8910733`, `v2-sa_8915261`, `v2-sa_8945299`, `v2-sa_8963199`, `v2-sa_9013170`, `v2-sa_9015358`, `v2-sa_9033026`, `v2-sa_9042900`, `v2-sa_9066871`, `v2-sa_9071097`, `v2-sa_9086959`, `v2-sa_9089846`, `v2-sa_9105975`, `v2-sa_911936`, `v2-sa_9123338`, `v2-sa_9131105`, `v2-sa_9136349`, `v2-sa_9142280`, `v2-sa_9161358`, `v2-sa_9169801`, `v2-sa_9173282`, `v2-sa_9180481`, `v2-sa_9187878`, `v2-sa_9202366`, `v2-sa_9206930`, `v2-sa_9212792`, `v2-sa_921334`, `v2-sa_9214653`, `v2-sa_922772`, `v2-sa_9229006`, `v2-sa_9237516`, `v2-sa_9241496`, `v2-sa_9247733`, `v2-sa_9249460`, `v2-sa_926201`, `v2-sa_927124`, `v2-sa_9289265`, `v2-sa_9298533`, `v2-sa_9327453`, `v2-sa_9337303`, `v2-sa_9345888`, `v2-sa_9357354`

known_issues.json 仅登记了 `v2-sa_9357354` 的 U1/U2；本次确认其 U1 的 “at the left” 实为画面右侧舞者（box x=1460–1907 / 2250），并新增大量同类问题（如 `v2-sa_9345888` U1/U2 的 “officer” 实为平民白衬衫、U3 “hat at the left” 实在右侧）。建议将本报告阻断项全部登记到 known_issues。

建议排除 case 列表（阻断 ∪ 尾段 #945–#1083）：

`v2-sa_7103552`, `v2-sa_1580699`, `v2-sa_719433`, `v2-sa_1539716`, `v2-sa_1980337`, `v2-sa_2194487`, `v2-sa_7725244`, `v2-sa_10602261`, `v2-sa_10631376`, `v2-sa_1112483`, `v2-sa_2734741`, `v2-sa_2981106`, `v2-sa_3662681`, `v2-sa_4441086`, `v2-sa_4582303`, `v2-sa_5072835`, `v2-sa_5074342`, `v2-sa_538938`, `v2-sa_5405364`, `v2-sa_626400`, `v2-sa_6283149`, `v2-sa_6534458`, `v2-sa_6665557`, `v2-sa_6769026`, `v2-sa_6776835`, `v2-sa_6779549`, `v2-sa_6791309`, `v2-sa_679629`, `v2-sa_6823812`, `v2-sa_6850445`, `v2-sa_6888719`, `v2-sa_6895502`, `v2-sa_6896269`, `v2-sa_6935352`, `v2-sa_6937647`, `v2-sa_6943290`, `v2-sa_6977563`, `v2-sa_7052077`, `v2-sa_7116219`, `v2-sa_7125342`, `v2-sa_7191982`, `v2-sa_7205265`, `v2-sa_720948`, `v2-sa_7229007`, `v2-sa_7231402`, `v2-sa_7237977`, `v2-sa_7247537`, `v2-sa_725238`, `v2-sa_7279175`, `v2-sa_7311948`, `v2-sa_7362739`, `v2-sa_7365220`, `v2-sa_7381987`, `v2-sa_7420848`, `v2-sa_7448541`, `v2-sa_7452479`, `v2-sa_7464946`, `v2-sa_7470032`, `v2-sa_7493523`, `v2-sa_7494564`, `v2-sa_7506005`, `v2-sa_7522810`, `v2-sa_7542458`, `v2-sa_7563964`, `v2-sa_7567943`, `v2-sa_7639254`, `v2-sa_7643197`, `v2-sa_7650202`, `v2-sa_7650355`, `v2-sa_7677069`, `v2-sa_7685764`, `v2-sa_7698269`, `v2-sa_7711079`, `v2-sa_7716977`, `v2-sa_77343`, `v2-sa_7735833`, `v2-sa_7753369`, `v2-sa_7757919`, `v2-sa_777091`, `v2-sa_7773451`, `v2-sa_7797481`, `v2-sa_7805976`, `v2-sa_7810159`, `v2-sa_7833331`, `v2-sa_7835850`, `v2-sa_7850865`, `v2-sa_7854521`, `v2-sa_7892712`, `v2-sa_7944519`, `v2-sa_7945941`, `v2-sa_7985091`, `v2-sa_7991555`, `v2-sa_8012456`, `v2-sa_8018927`, `v2-sa_8043384`, `v2-sa_805201`, `v2-sa_8060797`, `v2-sa_8064958`, `v2-sa_8066140`, `v2-sa_807381`, `v2-sa_8092195`, `v2-sa_8099809`, `v2-sa_8188123`, `v2-sa_8219544`, `v2-sa_8243132`, `v2-sa_8290161`, `v2-sa_8319146`, `v2-sa_8321304`, `v2-sa_8336561`, `v2-sa_834249`, `v2-sa_83477`, `v2-sa_8356934`, `v2-sa_8359156`, `v2-sa_8364417`, `v2-sa_8364504`, `v2-sa_8364627`, `v2-sa_8364723`, `v2-sa_8382869`, `v2-sa_838336`, `v2-sa_8403002`, `v2-sa_8405850`, `v2-sa_8425235`, `v2-sa_8429220`, `v2-sa_8430103`, `v2-sa_8430740`, `v2-sa_8448822`, `v2-sa_8489034`, `v2-sa_8532764`, `v2-sa_8543461`, `v2-sa_8550648`, `v2-sa_8586145`, `v2-sa_8607627`, `v2-sa_8608311`, `v2-sa_862087`, `v2-sa_8631298`, `v2-sa_8671723`, `v2-sa_8680793`, `v2-sa_8698583`, `v2-sa_8731521`, `v2-sa_873326`, `v2-sa_8739681`, `v2-sa_876819`, `v2-sa_8801740`, `v2-sa_8802184`, `v2-sa_8809691`, `v2-sa_8813510`, `v2-sa_8830987`, `v2-sa_8855821`, `v2-sa_886183`, `v2-sa_8871336`, `v2-sa_8874867`, `v2-sa_8908572`, `v2-sa_8910733`, `v2-sa_8915261`, `v2-sa_8945299`, `v2-sa_8962292`, `v2-sa_8963199`, `v2-sa_8998938`, `v2-sa_9006288`, `v2-sa_9006757`, `v2-sa_9013170`, `v2-sa_9015358`, `v2-sa_9033026`, `v2-sa_9033895`, `v2-sa_9042900`, `v2-sa_9066871`, `v2-sa_9068084`, `v2-sa_9068591`, `v2-sa_9071097`, `v2-sa_9086959`, `v2-sa_9089846`, `v2-sa_9105975`, `v2-sa_9111693`, `v2-sa_911936`, `v2-sa_9123338`, `v2-sa_9131105`, `v2-sa_9136349`, `v2-sa_9142280`, `v2-sa_9161358`, `v2-sa_9169801`, `v2-sa_9172711`, `v2-sa_9173282`, `v2-sa_9180481`, `v2-sa_9187878`, `v2-sa_9202366`, `v2-sa_9206930`, `v2-sa_9212792`, `v2-sa_921334`, `v2-sa_9214653`, `v2-sa_9216210`, `v2-sa_922772`, `v2-sa_9229006`, `v2-sa_9237516`, `v2-sa_9241496`, `v2-sa_9247733`, `v2-sa_9249460`, `v2-sa_926201`, `v2-sa_927124`, `v2-sa_9289265`, `v2-sa_9298533`, `v2-sa_9327453`, `v2-sa_9337303`, `v2-sa_9345888`, `v2-sa_9357354`

## 6. 产物与可复现性

| 文件 | 内容 |
|---|---|
| `/tmp/samtok_audit/phaseA.py` / `auto_checks.json` | 阶段 A 规则脚本与全部命中、每单元 mask 统计 |
| `/tmp/samtok_audit/render.py` / `views/` | 审图渲染脚本与 1,084 张合成审图 |
| `/tmp/samtok_audit/batches/` / `agent_prompt.md` | 28 个目视审查批次的输入与审查规程 |
| `/tmp/samtok_audit/agent_out/` | 每批目视结果（findings / reviewed，含被否定的自动 flag 及理由） |
| `/tmp/samtok_audit/findings.jsonl` | 合并后的全部问题（每行一条：case_id、unit_id、severity、category、evidence、suggested_fix、verified_visually 等） |
| `/tmp/samtok_audit/reviewed.txt` / `reviewed_meta.json` | 已目视的 case 列表（1,084）及每 case 审查摘要 |
| `/tmp/samtok_audit/lead_spotcheck.jsonl` | 主审抽查记录 |
