# 统一 instruction 与源区域协议

### 一条指令与一个源区域

Benchmark 与训练数据共用以下规范：英文语义记录/渲染格式为 `instruction_protocol_version=2.0`，mask 含义契约为 `mask_semantics.version=2.0`，写作风格为 `benchmark-concise-3-blind-1`（自 release 2.6.0 起；定稿依据见 [07 号文档](07_SAMTokEdit_Qwen21_指令协议2.0_noref改为盲指代.md)）。三者分别描述可序列化字段、区域的意义和语言写法，不是三套不同任务协议。共享代码沿用上游 v2branch 的 2.0 实现，当前发布入口见 [2.6.0 发布说明](RELEASE_2_6_0_ZH.md)。2.0 的 no-ref 与 1.0 不兼容；≤2.5.0 的结果不能与 2.6.0 的 no-ref 单元直接比较。1.0 的历史正文保留于 [INSTRUCTION_PROTOCOL_1.0_ZH.md](INSTRUCTION_PROTOCOL_1.0_ZH.md)，代码按 spec 自带的 version 保留 1.0 渲染以校验冻结的旧 release。

每个编辑目标 U 绑定一个源实例或部件 S、一种操作及其指令。Point、box、mask 和文字 ref 是 S 的不同定位形式，互相转换不产生新目标。原始 mask 保留可见像素、遮挡和孔洞；不把 bbox 内未选中的醒目物体误当成 S。Mask 不因编辑改成结果轮廓，也不是允许任意修改其内部全部内容的授权。

**2.0 统一规则：源 mask = 实际被编辑的区域 T。** 编辑整个物体或部件时 S = T，mask 不变；attribute/replace 带 `target_part`、remove `part` 时 mask 为该部件本身；remove `lowerlegs`/`hem` 为被剪掉的那一段；remove `contents` 为容器 ∪ 内容物，`contents_only` 为内容物；add 的 mask 是新物体附着的部位（锚点）：不带 site 时为直接承载物，带 site 时为 site 本身（例如提手、外套后背上部），仍然不是新物体轮廓。Ref 与 no-ref 共用同一 mask，box/point 由它生成（紧致框；点取离边界最远的像素）。替换下来的 1.0 宿主 mask 保留为 `target.mask_v1` 及 `box_v1`、`point_v1`，原文件不覆盖。

### 四类指令与 mask 的含义

| 类型 | 标准句式 | 源 mask 的含义 | 必须保持的边界 |
|---|---|---|---|
| add | `Add <item> <relation> <anchor>.` | 新物体实际附着的现有部位（直接承载物，或 site 本身）；少数符合条件的紧邻参照物 | 宿主保留；新增数量、接触、尺度及位置自然；不是新增物最终轮廓 |
| replace | `Replace <target> with <replacement>.` | 被替换的现有物体/部件本身 | 新旧对应同一对象层级，有真实结构/品类变化；单纯换色归 attribute |
| remove | `Remove <target>.` 或 `Remove <part> from <host>.` | 实际被删除的物体、部件或区段（含内容物时为容器 ∪ 内容物） | 只删除指明范围；不把整个宿主清空；不设计不自然的断肢任务 |
| attribute | `Change the <property> of <target> to <value>.` | 属性变化实际所在的物体、表面或部件本身 | 保留身份、结构及未指定内容；不得把“给人改色”含糊代指衣服 |

Attribute 支持 color/material/finish/pattern/texture/text；透明物染色用 `Tint <target> <color>.`，透明度用 `Make <target> transparent/translucent/opaque.`。文字内容逐字保留并加引号；仅必要时在一句话内列多个属性。加实体徽章/布贴属于 add，改变原表面图案属于 attribute，删除已有标志属于 remove。

删除内容物、连同内容物删除、剪短衣物等须写明范围和终点。一个 U 不混入不同操作；同一锚点添加多个同类物品可为一个 U，但必须说明数量。多目标 case 的每个 U 独立绑定指令，其他 U 授权的变化不算该 U 的越界。

### Add：直接锚点优先，安装部位与关系分开

1. 优先在所选对象上直接承载、容纳、穿戴、附着或印制。先根据宿主功能、材质、尺寸和可见空间选择自然的新物，而不是先想好物品再寻找远处参照。
2. `placement.relation` 写新增物与宿主/安装部位的关系，如 `on/in/attached to/mounted on/sewn onto/clipped to/hanging from`；`placement.site` 只写必要的宿主内部位置。`ref` 负责区分哪个宿主，不重复承担 site 的内容。
3. “在袖口下方的衣袖上缝补丁”是直接附着：`relation=sewn onto`、`site=area below the cuff`、`anchor_mode=support`。Site 里出现 below/near 不会把它变成参照添加。“椅子旁的包”用于识别包，给包提手加牌子仍是直接锚点。
4. 新物边缘、必要接触阴影和遮挡可超出源 mask，不能要求全部新增像素都落在原 mask 内。但必须与该宿主保持真实接触/支撑，且不妨碍原有功能、不改动无关实例。
5. 只有直接添加不自然时，才允许 `anchor_mode=reference`：位置真正紧邻、可见支撑面明确、侧别/安装位置唯一。远距离地标、悬浮新物、可落在多个位置的“附近”均不接受。训练构造必须有可信执行区域；缺少时换类型或拒绝该指令，不判原 mask 无效。
6. 2.0 中带 site 的 add，mask 精确到 site 本身；site 是区段而非可命名部件（如 `the lower portion`）时，取宿主 mask 上新物体实际落下的那一块（benchmark 人工框定，训练数据由目标图差异求出）。
7. 本版 benchmark 的全部 add 均使用直接锚点。协议允许紧邻例外，不等于当前样本含此例外。Benchmark 用户只提供源定位，不需要预先画出新物轮廓；训练内部执行 mask 不能冒充 benchmark 输入。

### 精简、准确、无歧义

默认一句祈使句：动作＋最短无歧义目标短语＋必要结果。目标唯一时停止添加限定；有竞争实例时才增加一个经图像核实的所属、方位、颜色或序数。序数必须说明可见计数组和方向；身体左右易混淆时用 image-left/image-right。颜色从无标注原图读取，不从彩色 mask 叠加读取。

不要另起 `which is/located/the one...` 分句解释位置，不堆叠宿主、颜色、方向，不列排除项。不要附加“其他都不变”“保留材质/光照”等通用保留列表：这些由公共契约和内部生成提示承担。`qualifier` 默认空，仅当省略会改变请求语义时保留短限定。必要的计数、精确文字、安装位置和删除范围不可为缩句而删除。

常规目标是 Ref 不超过26个英文空格词；No-ref 由盲指代模板生成，长度只取决于 payload；不是硬截断阈值，不填充到目标长度。Replace 的新形态写在一个完整替换物短语中，内部 form_change 证据不再追加到句尾。模型在同一次请求内检查并删冗，不默认增加润色调用。

### Ref / No-ref（2.0：no-ref 为盲指代）和结构化记录

两种指令从同一 `instruction_spec` 渲染。**一句话规则：把指令拆成“对哪里做”和“做什么”；“对哪里做”整体换成 `the selected region`，源 mask 选中的就是这个“哪里”；“做什么”原样保留。**

| 属于“对哪里做”，并入 `the selected region` | 属于“做什么”，原样保留 |
|---|---|
| 物体类别：sleeve、chair、man | 动作：change、replace、remove、add、tint、make |
| 部件和宿主：the handle of …、the lower legs of … | payload：替换物、新增物 |
| add 的安装部位（site） | 属性名和新值：the color … to navy blue |
| 位置、方位、序数：left、third from the front | add 的附着关系：on、attached to、clipped to … |
| 源物体的现状特征：the red coat | 结果说明：to make knee-length shorts、including its contents |

No-ref 句式（`<R>` = `the selected region`）：`Change the <property> of <R> to <value>.`、`Change the text on <R> to "<text>".`、`Tint <R> <value>.`、`Make <R> <value>.`、`Replace <R> with <payload>.`、`Remove <R>.`（whole/part/contents_only）、`Remove <R>, including its contents.`、`Remove <R> to make knee-length shorts.`、`Remove <R> to make it knee-length.`、`Add <payload> <relation> <R>.`。只描述编辑要求的 qualifier 原样保留，提到图中其他物体的 qualifier 在 no-ref 中整句去掉。Payload 不得指回源物体（去掉 `its/it/a matching one`），新物体用具体名词写出；payload 和属性值中出现类别或方位词不算泄露。中文 no-ref 一律写“选中区域”，如 `将选中区域的颜色改为海军蓝。`、`给选中区域加上一枚小圆形珐琅徽章。`。

例如 Ref `Add a red tag clipped to the handle of the left suitcase.` 的 no-ref 为 `Add a red tag clipped to the selected region.`，mask 是那只箱子的提手；Ref `Remove the white chest emblem from the foreground drummer's pink T-shirt.` 的 no-ref 为 `Remove the selected region.`，mask 是胸前徽标。

`render(spec, has_ref=False)` 输出盲指代；canonical `validate_noref` 按结构化槽位和标准渲染结果做确定性检查，并验证 qualifier 是否属于允许保留的结果要求或应删除的源图说明。Payload/属性值中的类别与方位词不按源指代泄露处理。修复工具的 `check_blind_noref` API 由 `instruction_compat.py` 包装该检查；历史 1.0 使用 `_legacy_instruction_protocol_v1.py`。`instruction_spec` 字段不变，`ref/scope/target_part/placement.site` 仍用于 ref 渲染。`mask_semantics.source_role` 只取 `anchor`（add）和 `target`（其余，指实际被编辑的区域）。

作者记录包含 operation、核实后的 ref/scope、payload、target_part/remove_mode、attributes、placement 与必要 qualifier。连接关系和 site 单独存储；构造器不得靠扫描 near/below/above 猜测锚点语义。英文、中文、completion requirement、edit contract 和摘要必须随同一条作者记录一起更新；`completion_requirement`、`edit_contract`、`preserve` 是评测者私有说明，可继续用完整 ref 描述，但范围必须与新 mask 一致。

### 训练执行与质量检查

2.0 起 benchmark 的源 mask 即实际编辑区域；训练数据中源定位 mask、执行区域 execution/support mask、邻近保护区域仍是不同概念，紧邻参照任务必须有可信执行区域；检查区域与语义层级相符，不能仅把 ref 改成部件名称而仍开放整个宿主。区域外像素不变只能证明合成边界，不能证明区域内改对、自然或没有误伤。

检查依次覆盖：原图/mask 绑定及几何；逐条 Ref/No-ref 等价与规范；图像中的实例归属和最接近竞争目标；操作自然性与类别边界；add 接触关系和局部位置；生成后完成度、非目标保护和自然质量。自动校验、模型视觉审核、assistant 目视复核和独立人工验收分别记录，不能互相冒充。
