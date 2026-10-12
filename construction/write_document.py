"""Render the single maintained benchmark document from the frozen release metadata."""

import argparse
import copy
import json
import shutil
from pathlib import Path
from PIL import Image
from samtok_benchmark.io import read_jsonl
from samtok_benchmark.v2.inputs import render_locators

REPO = Path(__file__).resolve().parents[1]


def table(headers, rows):
    return "\n".join(
        ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
        + ["| " + " | ".join(map(str, r)) + " |" for r in rows]
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    a = parser.parse_args()
    root = a.dataset_root
    cases = read_jsonl(REPO / "data/v2/cases.jsonl")
    s = json.loads((REPO / "data/v2/statistics.json").read_text())
    release = json.loads((REPO / "data/v2/release.json").read_text())
    figures = REPO / "docs/assets"
    figures.mkdir(parents=True, exist_ok=True)
    examples = []
    for number in [1, 8, 33, 138, 168, 198, 200]:
        case = cases[number - 1]
        dest = figures / f"case_{number:03d}.jpg"
        if not dest.exists():
            units = copy.deepcopy(case["units"])
            for u in units:
                u["interaction"]["locator"] = "mask"
            render_locators(case, units, root, dest)
            with Image.open(dest) as im:
                im.thumbnail((1200, 1000))
                im.save(dest, quality=90)
        rows = []
        for u in case["units"]:
            mode = "ref" if u["interaction"]["has_ref"] else "noref"
            rows.append(
                [
                    u["id"],
                    u["operation"],
                    mode + "+" + u["interaction"]["locator"],
                    u["instruction_" + mode],
                    u["instruction_" + mode + "_zh"],
                ]
            )
        examples.append(
            f"### Case {number:03d}：{case['difficulty']['scene_zh']}\n\n`{case['id']}`。{case['difficulty']['evidence_zh']}\n\n![源图与所选区域](docs/assets/case_{number:03d}.jpg)\n\n"
            + table(["目标", "任务", "正式输入", "English", "中文"], rows)
        )
    text = (
        f"""# SAMTok Benchmark v2：SA-1B 多对象细粒度交互编辑

当前唯一版本为 **v2 / release {release["release_version"]}：200 张 SA-1B 源图、785 个独立目标，每图 2–5 个目标**。全部源图与所选 mask 及任务在 2.2.0 阶段已由 assistant 逐图查看。本次 2.3.0 为协议迁移：保留审图证据、区域和编辑语义，统一双版本渲染并修正添加位置语序，未冒充新的独立人工审图。当前冻结的是源图、任务和交互标注，尚无模型编辑结果或独立人工验收。

此文档是仓库唯一维护的说明，审核包和数据目录中的同名内容是它的发布副本。旧 212 条和旧说明已退出当前清单，历史保存在 Git 与数据归档目录；不与这 200 条混合统计。

## 1. 评测目标与判定方式

研究问题是：同一复杂场景中，用户分别指定多个物体或部件，以不同形式输入，模型能否同时准确、完整地执行全部编辑，保护其余内容，并保证每个编辑的自然质量。评测重点包括实例选择、部件指代、遮挡后的多块可见区域覆盖、细长区域和孔洞边界、相邻内容保护，以及不同对象指令之间的干扰。

| 维度 | 判断内容 | 失败示例 |
| --- | --- | --- |
| E：目标与执行完整性 | 每条指令选中正确实例和部件；实际完成要求的操作、数量、位置和全部相关可见部分 | 改错同款箱子的提手；只改被遮挡部件的一段；只新增替代物却留下原物 |
| P：非目标保持 | 保留该对象未指定部分、邻近物、遮挡者和背景；同图其他指令明确允许的变化除外 | 修改提手时改变箱体；改衣袖时改变躯干或旁人 |
| Q：编辑质量 | 每个目标的形状、材质、边缘、接触、遮挡、光照与阴影合理 | 新配件悬空；断裂边缘；部件融合；不合理的局部结构 |

每个 U 独立判断 E/P/Q，同时判断整图 global_P/global_Q。**JointPass = 所有 U 的 E∧P∧Q ∧ global_P ∧ global_Q**。任一目标漏改、错改、越界或质量失败，整条 case 失败；大目标的成功不能补偿小目标的失败。报告同时分解 E/P/Q、目标数、编辑类型、交互形式、困难标签；主指标是整图联合成功率。

评估查看原图/结果全图及逐目标固定坐标的配对局部裁剪。允许操作必需的局部显露背景、连接、光影调整。**源 mask 是语义定位标注，不是输出差分金标准**，不能用差分与 mask 的 IoU 代替 E/P/Q。尤其 add、replace 和移除子部件，允许变化范围由具体指令决定。全量源标注和验收规则属于 evaluator 私有信息。

## 2. 源数据与可追溯路径

本版图片全部来自前期分析的 **SA-1B 图片库及配套 dense annotation**，不含 PACO-LVIS 或 ADE20K 的旧 212 条。SA-1B 是为通用图像分割建立的大规模自然图像与区域资源；本地 handoff 给出的图片/标注索引口径为 **11,185,362 条**，这里沿用 handoff 的统计，没有重新扫描全库。场景包含人群、街市、店铺、衣物配件、车辆、器物、建筑设施等。

配套 dense TFRecord 中有 `key`、图片 caption、tags、`objects_json` 和 `associations_json`。对象记录包含 object_id、类别/描述与 COCO RLE 可见区域。它们是本地配套的 dense 标注；本文不把这些语义对象与官方 SA-1B 自动 mask 集逐项等同。类别和描述可有误，实际入选及指令以图像、mask 和实物归属核查为准。

- Handoff：`/mnt/hdfs/byte_ttlive_strategy_llm/user/haobo.yuan/datasets/SA1B_HANDOFF.md`。
- 图片 TFRecord：`/mnt/hdfs/byte_ttlive_strategy_llm/user/haobo.yuan/datasets/sa1b_tfd_1k/`。
- 图片索引：上述目录的 `sa_000000_unified_tot1000.index`。
- Dense TFRecord：`/mnt/hdfs/byte_ttlive_strategy_llm/user/haobo.yuan/datasets/sa1b_dense_label/annotation/`。
- Dense 索引：上述目录的 `all1000.index`。
- 当前源素材及筛选过程：`{root}/sa1b_source_selection/`。
- 正式来源追溯：仓库 `data/v2/provenance.jsonl`，记录 SA ID、所选原 object_id、原始/解析后的 TFRecord 文件、offset、length、原素材清单 SHA256 和训练目录匹配。

索引中的旧 `/mnt/hdfs/sg_byte_ttlive_strategy_llm/` 前缀解析为本机 `/mnt/hdfs/byte_ttlive_strategy_llm/`。按已给出的偏移读取记录，不重建图片全量索引。原始 RLE 和所选区域清单保存在 `sa1b_source_selection/selected_sources.jsonl`；正式 PNG 记录逐文件 SHA256。

## 3. 如何挑选和筛选

先按固定 seed 抽样读取标注并安排候选查看顺序，再实际查看图片决定入选。初始 seed 20261011 抽 800 条，取回优先候选 320 张，另外补充器物等方向 74 张；扩充 seed 20261012 再抽不重叠的 2,000 条，取回 850 张。累计数字如下，阶段不是相加关系。

{table(["阶段", "数量"], [["解析 dense 标注", 2800], ["取回候选图片", 1244], ["实际查看原图场景", 622], ["进一步检查原图、叠加图和局部并记录决定", 252], ["细查后保留", 200], ["细查后备用", 41], ["细查后淘汰", 11]])}

候选召回先排除 sky/ground/wall 等背景类别，并把面积约 0.08%–30%、重复类别、部件关键词、较小区域较多的图片排前。初始排序分数为 `2×min(重复量,12)+min(部件量,15)+min(小区域量,12)+min(候选量,12)`，仅用于安排查看顺序。类别重复、面积小、mask 多都不能单独构成入选证据。

**逐图入选标准：**

1. 每图实际选出 2–5 个不同实物的目标。不能把一个物体的碎块、同一个人的两只衣袖、同一辆车的多个零件冒充多个物体。每个 U 记录 `physical_parent_zh`；独立背包等配件可以与使用者分别作为目标。
2. 难点落实到所选区域：同类近似实例、被人/物遮挡、细杆/窄带/孔洞、小部件、相邻接触边界、不同粒度并存等，记录具体证据；背景热闹而目标只是孤立大块不够。
3. 对照较大原图、mask 叠加和目标局部，检查实物归属、全部可见部分、遮挡关系、孔洞、边缘及需要保护的邻居。同一对象分离的可见块保留为一个 U。
4. 目标足够清晰且指代可写；纯 ref 使用方位、所属人物/物体及部件关系区分实例。point/box 可以含更强的干扰，但真实目标必须可识别。
5. 舍弃 mask 把背景孔洞填满、整个人误标为衣物、错误覆盖邻居、目标明显失焦、镜面/印刷物冒充实物、同一实物重复计数等问题；可只剔除某张图的不合格 mask。
6. 未看过、未记录 accept、备用及淘汰项均不进入正式 200 条。所有入选图本轮又查看并写任务；审查归属如实记录为 `ai_direct_visual`，不冒充人工验收。

场景初筛 `review/scene_review.tsv`、细查决定 `review/decisions.jsonl`、候选图片 `candidates/`、检索/审图脚本 `scripts/` 均在源素材过程目录。仓库 `data/v2/selection/` 保存关键筛选日志、统计及原 RLE 验证结果。指令审查记录在 `data/v2/instruction_reviews.jsonl`，对应 50 张四图审查页的路径和 SHA256；大图回看保留在各源图的 `review.jpg`。

这是困难场景定向精选，并非 SA-1B 全库无偏样本。衣物、包带、提手等仍较多，领域没有做均衡配额；“高难”来自视觉结构审查，尚无模型成功率标定。

## 4. 区域标注与交互协议

mask 使用 dense annotation 中该目标原始可见区域，转为与原图同尺寸的 0/255 PNG；逐像素与原 RLE 核对，不扩张、补画或合并不同实物。box 为 mask 紧致轴对齐框，整数 xyxy，右下不含。point 取 mask 内距边界最远的像素，保证落在目标内；这是确定性构造点，不代表真实用户点击分布。

英文 ref 由本轮逐图编写，中文给出对应实例/部件；无 ref 的指令仅用 `the selected <part type>` 表明粒度，不泄露完整位置描述。mask 是所选对象/部件的定位范围：196 个 add 定位承载物或安装部位，77 个 remove 进一步明确其中子部件，余下 512 个直接针对所选可见对象或部件。衣领、logo、衣袖等子部件任务不能被误评为“必须改完整件衣服”。

**Add 的区域语义（benchmark DCO contract）：** add 的公开 mask、box 或 point 标记的是源图中已经存在的承载物/安装面，即新增物体的锚点（host/attachment anchor），不标记新增物体在结果图中的预计轮廓，也不是输出差分金标准。新增物体在 source 中不存在；因此 instruction 使用 `Add <new item> to/on/onto <target>.`，其中 `<target>` 与该锚点绑定，原承载物必须保留，新增物体必须以指令要求的数量、位置和接触关系附着到该锚点。add 的 `edit_contract.locator_semantics` 为 `addition_support`；其允许的结果变化可以因连接、遮挡、边缘、光照或阴影而超出锚点，但不能借此改动无关对象。评测时应检查新增物体是否出现、是否附着在指定锚点、原承载物及邻近内容是否保持，以及整体编辑质量。

每个对象独立取一种正式模式，无 ref 必须有 point/box/mask；有 ref 可以无区域。冻结时按 manifest 顺序循环七种模式，保证每图至少两种形式；未按模型效果挑模式。

{table(["正式模式", "目标数"], s["interactions"].items())}

`ref+none` 是纯 ref。公开输入不会附送其 point/box/mask；no-ref 不附送私有 full ref。中文翻译默认仅供审核。审核页“全部 ref”会把私有目标标签画到原图，用于复核；**不等同于模型的正式输入**。

支持两个协议：`native_regions_v2` 直接提供对应坐标或 mask，且只暴露实际指定的形式；`visual_locator_v2` 提供干净源图和仅画指定定位形式的第二张提示图。审核包内 JPEG 提示图用于浏览；正式运行生成 PNG，保持原分辨率。支持 `mixed` 主评测、`all_ref`、`all_mask_noref` 和 `single` 消融。不同协议/消融需分别报告。

## 5. Instruction 如何撰写

本节以冻结的 **benchmark v2 / release 2.3.0，200 张源图、785 个编辑目标，instruction 协议 1.0**为准，规范的是模型收到的公开任务指令。`construction/instructions/design.tsv` 逐对象记录语义设计，`construction/instruction_adapter.py` 将旧 recipe 转成统一语义槽位，`src/samtok_benchmark/v2/instruction_protocol.py` 负责英文双版本拼句与校验；完整验收条件另存于 `completion_requirement`、`preserve` 和 `edit_contract`。训练数据生成器附加的长 prompt 不属于这里的公开 instruction。第 5.1–5.6 节记录冻结版本现状；当前两边共用的完整协议见第 5.7 节。

本版任务来自逐图查看场景和选区后的设计与冻结。后续按类型扩样应先分配编辑类型，再寻找适合该类型的目标与自然修改；不合适就拒绝或补选，不应为了凑数改成其他类型。本次已将 785 条任务迁移至协议 1.0；119 条添加指令调整位置关系的语序，任务语义、区域与类别保持不变。旧版已归档。

### 5.1 公共写法与 ref/no-ref

每个独立目标 U 只写一条简短、明确、可视觉判定的编辑请求，交代“执行什么操作、作用于什么对象/部件、改成什么或添加什么”。同图多个目标分别通过 U 编号绑定指令与定位信息，不挤进一个含糊长句，也不要求先执行另一个 U 才能理解本 U。

- **ref 版本**：`<target>` 是依据源图编写的完整指代表达，可以包含类别、源颜色、方位、所属人物/物体及部件关系。描述必须与该 U 的区域指向同一实例；不确定的颜色不要猜，不能用编辑后的属性描述源目标。
- **no-ref 版本**：仅把同一 `<target>` 替换成 `the selected <scope>`，例如 `the selected jacket`。`scope` 保留对象/部件类型与粒度，删除用来定位宿主实例的左右位置、人物身份等信息。新增物、数量、颜色、材质、删除子部件和必要安装位置必须保留。**no-ref 不是无语义指令**，不能把“移除衣服上的徽标”缩成“移除选中的衣服”。
- 两版本的编辑内容必须等价；差异只在源实例如何定位。no-ref 中允许 `upper back` 等定义新增物安装位置的词，也允许 `white chest emblem` 等明确待删除子部件的词，它们是编辑语义，不是泄露完整宿主 ref。
- `has_ref=true` 时发送 `instruction_ref`，可以配 `none/point/box/mask`；`has_ref=false` 时发送 `instruction_noref`，必须配 `point/box/mask`。转换定位形式不改变操作和编辑内容。每个 U 只向模型发送实际指定的一种版本，不同时附送私有 full ref。
- 公开英文句子使用祈使句和句号，写操作必需信息，不反复添加“保留其他内容”，不混入设计理由、审核结论、模型名、生成步骤或重试要求。保持要求是全局默认行为，具体保护关系在私有验收标注中展开。
- 中文审核翻译须保留相同操作、数量、目标粒度和结果要求；默认正式输入使用英文，中文用于审核。

当前冻结数据的英文 ref 实际长度为 **4–26 词，中位 17**，no-ref 为 **4–16 词，中位 10**，按空白分词。新写作沿用这一简洁预算。两边均已移除最少词数和机械上限，超预算记录 `instruction_length_advice` 供审查，不能为压缩长度丢弃必要语义。长度合格不代表语义正确。

### 5.2 四类及其子类的固定句式

下表中的 `<target>` 在 ref 中取完整指代，在 no-ref 中统一取 `the selected <scope>`。当前构建器兼容 add 的 `to` 句式，并把可明确拆出的安装位置放入 placement，渲染为 `Add <item> <relation> <site of target>.`。

| 类型 / recipe | 英文句式 | 中文含义与语义边界 | 当前数量 |
| --- | --- | --- | ---: |
| add / A | `Add <new item> to <target>.` | 给指定承载物添加源图中不存在的物品；必要时写数量、大小和安装位置，原承载物保留 | 196 |
| replace / R | `Replace <target> with <new object/part>.` | 用结构、形态或品类不同的新物体/部件替代旧目标；只换色不算 replace | 196 |
| remove / D | `Remove <target>.` | 完整移除指定目标，合理补全显露背景 | 109 |
| remove / D:contents | `Remove <target>, including its contents.` | 连同容器中的物品一起移除，不能把内容物悬留 | 11 |
| remove / D:part | `Remove <part> from <target>.` | 只移除所选对象上的明确子部件，宿主其余部分保留 | 56 |
| remove / D:lowerlegs | `Remove the lower legs of <target> to make knee-length shorts.` | 剪去下段裤腿，改为及膝短裤，保留上部裤装 | 18 |
| remove / D:hem | `Remove the lower section of <target> to make it knee-length.` | 剪去裙装下段，改为及膝长度 | 3 |
| attribute / C | `Change the color of <target> to <value>.` | 改颜色，保留对象身份、几何与相关纹理 | 179 |
| attribute / C:material | `Change the material of <target> to <material>.` | 改为明确材质，保留对象身份和几何；例如 polished gold，不能仅用 matte black 冒充材质 | 13 |
| attribute / C:tint | `Tint <target> <color>.` | 给透明物体染色，保持合理透光性质；`attribute_kind` 仍为 color | 4 |

### 5.3 各类型必须明确的编辑范围

**add：区域是源锚点。** mask/box/point 指向源图中的承载物或安装面，不是新增物体的预计轮廓。指令中必须能判断新增什么、加到哪个锚点，以及必要数量和附着位置。新增物要与场景用途、体量、支撑/连接关系自洽，不能借添加替换掉宿主。当前 196 个 add 全是局部增添/附着，不包含自由空间新增大型物体。连接、遮挡和必要阴影可以超出源 mask，不能据此任意改变邻近物。

**replace：明确旧目标和新身份。** 替代物应能占据原来的合理位置，尺度、用途和支撑关系可成立；旧身份应消失，不能只是旁边多放一个新物体。若目标是衣袖、提手等部件，只替换该部件，不能把整个人或整件宿主一起改掉。

**remove：先分清删整物还是删子部件。** 普通 D 删除整个指令目标；D:contents 还删除内容物；D:part、D:lowerlegs 和 D:hem 只删除所选宿主中的指定部分。后面三类共 **77 个**，`edit_contract.scope_relation=subregion_of_selected_object`。源 mask 可以定位整件宿主，具体删除范围由文本进一步限定；不能把这些 case 评成“mask 覆盖的全部内容都应消失”。其中删除已有徽标、印花或文字的 7 个任务也是 remove，不应改归 replace。

**attribute：明确属性和值。** 当前只包含颜色/染色和材质，不包含任意属性变化。目标对象及其几何身份应保持，不能趁换色改变款式、形状或文字。颜色要与源图有可判定区别，材质值要是真正的材料；透明物的染色不能直接变成不透明实心块。当前颜色/染色合计 183 个、材质 13 个。

源 mask 在所有类型中都是语义定位依据，不是结果图的逐像素差分真值。实际允许改动由文本目标、操作类型及必要局部物理效应共同决定。

### 5.4 冻结 benchmark 中的真实例子

下面是清单原句，未为解释而改写；中文解释用于说明含义。

| case / U | ref 指令 | no-ref 指令 | 中文含义 |
| --- | --- | --- | --- |
| `v2-sa_10146830/U3` · add | Add one small round enamel pin on the upper back of the central girl's leather jacket. | Add one small round enamel pin on the upper back of the selected jacket. | 给皮衣后背上部加一枚小圆形珐琅徽章；no-ref 仍须保留数量与安装位置 |
| `v2-sa_10063996/U1` · replace | Replace the outer sleeve of the woman on the left with a flared bell sleeve. | Replace the selected sleeve with a flared bell sleeve. | 将指定衣袖替换为喇叭袖 |
| `v2-sa_10146830/U1` · remove | Remove the hood hanging down the red-clad person's back. | Remove the selected hood. | 移除指定帽兜 |
| `v2-sa_2566092/U1` · remove 子部件 | Remove the white chest emblem from the foreground drummer's pink T-shirt. | Remove the white chest emblem from the selected T-shirt. | 只删除 T 恤胸前白色徽标，保留 T 恤 |
| `v2-sa_10063996/U2` · attribute 颜色 | Change the color of the red coat of the woman on the right to navy blue. | Change the color of the selected coat to navy blue. | 将指定外套改为藏蓝色 |
| `v2-sa_5033895/U1` · attribute 材质 | Change the material of the crown of the front-right elephant-headed statue to polished gold. | Change the material of the selected crown to polished gold. | 将指定冠饰材质改为抛光黄金 |
| `v2-sa_1580699/U4` · attribute 染色 | Tint the narrow transparent package immediately left of the blue shopping bag amber. | Tint the selected package amber. | 将指定透明包装染成琥珀色，保留透明性质 |

这些例子说明写法与评测语义，不代表已经取得合格目标图。当前 benchmark 冻结的是任务和输入，独立人工验收与模型编辑评测仍待完成。

### 5.5 多目标与训练管线的区别

正式 benchmark 每张源图有 2–5 个不同实物的目标，每个 U 独立绑定自己的指令和交互形式，主评测要求在同一结果图中全部完成。当前冻结分布是：2–4 目标图的操作类型不重复，5 目标图覆盖四类且仅一类重复；全局四类按目标计最多相差 1 个。它们是本版 case 设置，不是单条英文句子的语法规则。

当前训练构造管线已实现统一语义记录、四类及删除子类、Tint 和外观属性扩展，由同一 renderer 生成 ref/no-ref。子部件和内容物范围必须有预处理提供的执行区域；缺失则拒绝，不把“删除宿主上的徽标”降级为整物删除。训练实验中“每源两个目标、同一类、分别生图”也不等同于 benchmark 的混合类型多目标联合任务。对齐 benchmark 需要保留这些范围语义，不能只比较四个 operation 标签。

### 5.6 写完后的核对要求

1. 从干净源图确认 ref、区域、类别和所属实例一致；同类多个目标的方位不能互相矛盾。
2. 仅比较 ref/no-ref 的目标短语替换后，操作、数量、目标属性、安装位置和删除范围应全部一致。
3. 确认类别语义成立：添加没有变成替换，替换不是仅换色，删除子部件没有变成删宿主，属性修改没有改几何。
4. 确认请求符合画面可见内容和常见修图需求，有合理尺度、支撑和遮挡关系；不靠想象的故事解释怪异变化。
5. 检查句子长度、中英文等价性，以及同图各 U 的独立性、保护关系和联合可执行性。

修改冻结指令需更新设计记录、重新审图并重新冻结版本。本文补充规范不会改写当前任务清单、改变 operation 分类或代替视觉质量验收。

### 5.7 统一 instruction 协议 v1.0（已接入 benchmark 与训练管线）

本协议统一 benchmark 和训练数据的语义设计与英文渲染，已接入 release 2.3.0 及训练管线。沿用四类操作、ref/no-ref 和源区域定位原则。协议版本独立于数据集 release；支持某种句式不等于该子类已经出现在冻结样本中，也不等于已验证生成质量。

#### A. 一条指令表达什么

统一结构为：**操作 + 实际编辑对象 + 新内容/目标值 + 必要的局部关系或范围**。每个 U 对应一个源实例或其部件，以及一种编辑操作。优先一句话；仅在省略信息会产生不同合理结果时，增加短限定语。输入 point/box/mask 负责定位源实例，文字负责明确编辑内容和局部范围。

区分两个概念：`S` 是区域或 ref 选中的源实例；`T` 是实际操作对象，可以直接等于 S，也可以是 S 内文字明确指定的部件。例如区域选中夹克时，T 可以是“该夹克的领口”；区域已精确选中领口时，T 就是“选中的领口”，不能再写“领口的领口”。add 则以 S 或其可见部位为新增物的锚点。

同一种类型使用稳定的主句，不要求所有细节塞进一个不自然的固定短语。不额外写“请”“高质量”“真实自然”“只修改这里”“保持其他不变”等重复套话。数量、接触关系、保留某一易混淆部件、结果长度等若决定任务含义，应保留在公开指令中，不能仅写在 evaluator 私有字段里。

#### B. 分类型句式和边界

| 类型 | 推荐主句 | 可按需补充的内容 | 类型边界 |
| --- | --- | --- | --- |
| add | `Add <item> <relation> <anchor>.` | 新物的类别、必要数量/外观，锚点上的部位、放置或连接关系 | 新增实体或实体配件；原锚点保留。输入区域指向源锚点，不指向新增物轮廓 |
| replace | `Replace <T> with <replacement>.` | 新实体/部件的设计、数量、关键外观；必要连接关系 | 旧对象/部件被替代，不能留下旧物又在旁边增加新物；仅改颜色、图案或材质归 attribute |
| remove | `Remove <T>.`；宿主定位时用 `Remove <part> from <S>.` | 明确连带移除内容物、移除数量、裁去范围和预期终点 | 删除整物或指定局部，保留未请求的宿主部分；不是把 mask 内全部像素都清空 |
| attribute | `Change the <property> of <T> to <value>.` | 目标属性值，以及确实必要的属性组合或局部范围 | 保留实体身份及未请求的几何、部件和外观；改变已有对象/表面属性，不添加或替换实体 |

**add 的关系不要一律用模糊的 `to`。** 承载关系可写 `on the seat of`、`inside`，连接可写 `attached to the handle of`；已有 to 句式在位置明确时继续有效。缺省优先依附/承载型添加。为覆盖自然请求，允许以可见源实例为参照的 `under`、`beside` 等位置关系，但必须有可见可用空间及合理落地/支撑条件，必要时写清参照侧。例如 `Add a small wastebasket on the floor beside the left leg of the selected desk.`。这种参照型添加是新协议的表达能力，当前冻结 benchmark 的 add 仍全是局部依附型；训练入口仅在已有明确执行区域时接受参照型任务。

数量可由 `a/an` 表示一个；要求恰好几个时写 `one/two/...`。同一锚点上添加两个相同物品可以是一个 U，不因新增数量变成两个源编辑目标。默认一个 U 只涉及一个新增物类别；“加靠垫并删除包”是两种操作，不能塞进同一 U。

**remove 保留现有灵活子类：**

- 整体与内容物：`Remove <T>, including its contents.`。容器及物品是否一起移除应明确；若只清空容器，写 `Remove the contents from <S>.`，保留容器。
- 已有标记/局部部件：`Remove the logo from <S>.`、`Remove the hood from <S>.`。保留载体，合理补全被移除处。
- 裁短：沿用 `Remove the lower section of <T> to make it knee-length.` 等“范围 + 终点”形式，不另增一套操作类型。裁短是 remove 的明确例外，允许因切除产生轮廓变化；不能扩大为任意形状变换。
- 附件或物品是否连带删除若有多种合理解释，必须在公开句子中消歧；普通背景补全、必要阴影处理属于全局执行要求，无需每条重复。

**attribute 从颜色/材质扩为有限、可核验的外观属性集合：**

| property | 推荐表达 / 示例 | 保持要求 |
| --- | --- | --- |
| color | `Change the color of <T> to navy blue.` | 保留相关纹理、结构与光照关系 |
| material | `Change the material of <T> to brushed steel.` | 材料必须真实明确；只改变现有表面的材质表现，尺寸和构型不随意变化 |
| finish | `Change the finish of <T> to matte.` | 区分表面光泽与材料；matte black 是颜色/表面效果，不是材料名 |
| pattern | `Change the pattern of <T> to thin blue stripes.` | 只改变指定表面图案，保持裁剪、褶皱和遮挡；支持原本纯色表面 |
| texture | `Change the surface texture of <T> to a fine pebbled texture.` | 目标纹理应具体且适配源对象；不借此改轮廓或结构 |
| text | `Change the text on <T> to "OPEN".` | 引号内是精确内容；需要特定行/标签时在 T 中明确，保留载体和未指定文字 |
| tint / opacity | `Tint <T> amber.`；`Make <T> translucent.` | tint 默认保留原透明性质；透明度变化只有明确请求时才允许，不借材质修改隐式改变 |

保留 `Tint` 作为颜色的自然短式；`Make ... translucent/opaque` 是透明度的受限短式。可自然写 `Recolor <T> navy blue.` 的任务仍优先统一为 `Change the color ...`，不为同一语义增加大量随机同义模板。

同一 T 上确有必要且兼容的多个外观要求可以合并为一个 attribute，例如 `Change the color of <T> to navy blue and its finish to matte.`；内部仍分别记录属性和值。不要默认把每条扩成多属性任务，也不混入移除、添加或实体替换。

**分类边界固定：**加实体布贴/徽章是 add；让衣服表面出现条纹是 attribute.pattern；把已有标牌文字改成另一串文字是 attribute.text；删除已有 logo/文字是 remove；把整块标牌换成另一种结构是 replace。翻转、搬移、重新摆姿势等不属于这四类协议，不强行重标。新增属性及参照型添加应分别记录子类，评测时分项统计，不能把新能力混进旧版本结果直接比较。

#### C. ref/no-ref 从同一份语义记录生成

只更换 S 的实例定位表达，其他编辑内容保持一致：

| 内容 | ref | no-ref |
| --- | --- | --- |
| 源实例 S | 源图中可准确定位的简短名词短语 | `the selected <scope>` |
| 源实例内部的操作部位 | 保留 | 保留 |
| 新物、数量、结果值 | 保留 | 保留 |
| 放置/附着关系、删除范围 | 保留 | 保留 |
| 为定位源实例写的左右位置、所属人物等 | 按需保留 | 删除，由定位信息承担 |

`scope` 必须由当前图像和区域确认，不能直接用可能错误的原始类别或其第一个别名。独立确定 scope 与 ref 的一致语义，再渲染两版本；不能让模型分别自由写两条指令后只检查字符串不同。无 ref 必须有 point/box/mask；ref 可单独使用或配区域。同一 U 切换定位形式不应改变上述语义。

以下是**协议示例，不是新增冻结 benchmark 样本**：

| 类型 | ref 示例 | no-ref 示例 |
| --- | --- | --- |
| add | Add a beige cushion on the seat of the black chair on the left. | Add a beige cushion on the seat of the selected chair. |
| replace | Replace the handle of the red suitcase with a rigid black handle. | Replace the handle of the selected suitcase with a rigid black handle. |
| remove | Remove the logo from the runner's white T-shirt. | Remove the logo from the selected T-shirt. |
| attribute | Change the color of the collar of the front man's jacket to navy blue. | Change the color of the collar of the selected jacket to navy blue. |

后面三例的区域均假设定位宿主（箱子、T 恤、夹克）。若区域本来就定位提手/徽标/领口，no-ref 应分别改为 `the selected handle/logo/collar`，不能混用宿主粒度。子部件必须在源图上可定位；出现多个同名部件时，保留区分该部件必需的局部方位，例如 `the left pocket of the selected jacket`。

#### D. 简洁性、自然性和多目标规则

- 写足能够区分不同编辑结果的信息，然后停止；不要求每条凑满数量、颜色、材质、大小、位置这几项。对结果没有作用的修饰词删除。
- 默认一句话；ref 26 词、no-ref 16 词继续作为常规写作目标，不设最低词数，也不为达标删掉必要限定。超过目标先检查冗余，超过 40 词建议重新审查或拆解；长而必要的指代可保留。该协议的长度要求是写作指导；现有训练器已迁移为非空检查、语义校验与长度审查提示。
- 属性或替代物应与源对象、场景用途、尺度和光照自洽。选择普通人可能提出的修图请求，不能单为明显变化设计奇怪物件/极端颜色。
- 无 ref 不等于允许随意歧义：指令结合公开定位信息后必须明确。没有足够清晰的源实例、部件或可行支撑关系时，拒绝该任务并按同类补样。
- 每个 U 可独立理解，所有 U 又须能在同一张结果图联合执行；避免一条删除另一条的宿主、对同一表面要求互斥颜色等冲突。不引用“上一个编辑”“第一步结果”。
- 全局默认保留未请求内容，并完成必要的背景、边缘、遮挡、连接和光影修复。这些默认项不重复写进每条指令；超出默认含义的要求必须公开，不能由私有验收偷偷增加。

#### E. 实现约定与迁移边界

内部最小语义记录应包含：`operation`、`selection`（源实例 ID、经核对的 ref/scope 和定位信息）、`target_part`（若有）、`change`（新物/替代物/删除范围/属性和值），以及按需的 `placement`（关系与部位）、`qualifiers`（必要数量或保留要求）。这些是作者侧结构化槽位，不要求模型输入暴露 JSON，也不能把内部全量定位信息泄露给 ref-only 任务。放置几何、执行 mask、审核证据独立保存，不塞入公开短句。

模板根据操作和槽位渲染 ref/no-ref，逐项核验语义等价，并记录 `instruction_protocol_version`。旧 release 2.2.0 的语义与四类基础模板继续兼容，无需仅为句式重写历史任务；改变实际编辑语义必须重新审查和冻结版本。

已同步修改规划输出、双版本渲染、schema、生成 prompt、区域范围检查、审核规则与 SAMTok 指令绑定。两个仓库使用逐字一致的无依赖 `instruction_protocol.py`，包括语义槽位校验、ref/no-ref 渲染和漂移拒绝。宿主 mask + 子部件语义必须提供可靠执行区域；若未提供或仍覆盖整个宿主，拒绝执行。参照型 add 也须显式执行区；普通依附型 add 保留现有生成兼容路径。LaMa 仅做删除，重着色后端仅做单一颜色属性，其他属性交给文字条件编辑器。**已完成代码接入和协议验证，未据此宣称新增子类生成质量合格。**

### 5.8 本次迁移验证（2.3.0）

全部 785 个目标写入协议版本和语义记录，119 组 add 指令将原有位置短语显式绑定到源锚点。例如 `Add one small round enamel pin on the upper back to ...` 改为 `Add one small round enamel pin on the upper back of ...`。迁移没有添加新的物品、位置或属性要求；中英文请求的原编辑内容保持一致。

已逐字段核对源图、原始 target/mask/box/point、交互形式、操作类别、中文指令和保护标注均未变。785 组 ref/no-ref 全部从语义记录重渲染校验；200 条正式 native mixed 输入只暴露所选指令和定位形式，不泄露完整 spec 或私有 full ref。1,185 个资产通过哈希及几何核验。差异清单与共享模块摘要见 `data/v2/protocol_migration.json`。

benchmark 测试 95 通过、ruff 全部通过；训练管线全量测试 438 通过、1 跳过。可用 `PYTHONPATH=src python construction/verify_instruction_protocol.py --training-repo ../sa1b-samtok-edit-data` 复核两份协议模块逐字相同与全部双版本一致性。测试覆盖类型/属性拒绝、双版本语义漂移、精确文字、数量与位置、部件执行区域、SAMTok 绑定和元数据往返。2.3.0 审核包已重新完成全部 200 case 的浏览器加载与 mask/box/ref 叠加检查，页面错误和失败请求均为 0；完整 PDF 逐页嵌入全部 200 case 图像。此 benchmark 发布未运行编辑模型。旧 2.2.0 元数据归档于数据根目录的 `archive/release_2.2.0_before_protocol_1.0/`。

## 6. 当前构建结果

{table(["编辑类型", "目标数", "占比", "包含该类型的 case"], [[op, s["operations"][op], f"{s['operations'][op] / 785:.2%}", s["case_operation_presence"][op]] for op in ["add", "replace", "remove", "attribute"]])}

{table(["每图独立目标数", "case 数", "占比"], [[k, v, f"{v / 200:.1%}"] for k, v in s["targets_per_case"].items()])}

平均每图 **3.925** 个目标。4–5 目标图共 **126 条（63%）**。5 目标图的重复类型分别为 add 19、replace 18、remove 19、attribute 29 条；完整组合分布见 `statistics.json` 的 `case_operation_combinations`。

{table(["难点标签（可重叠）", "case 数"], sorted(s["source_selection"]["difficulty_case_counts"].items(), key=lambda x: -x[1]))}

mask 面积占整图中位数 **0.5725%**，最小 **0.0814%**、最大 **13.1828%**；小于 1% 的有 **535/785** 个目标。**203 个目标 / 115 张图**含多个显著连通块，但仍按 785 个实物目标计数。连通块采用 4 邻接，忽略小于 max(9 像素, mask 面积 0.1%) 的分量；与“分离可见区域”人工场景标签的 14 条不是同一统计。

{table(["操作子类", "目标数"], s["recipes"].items())}

其中 A/R/D/C 分别对应 add/replace/remove/attribute，D:part 指删选中对象的指定子部件，D:contents 包含内容物，D:lowerlegs/D:hem 为裁去服装下段，C:material/C:tint 为材质/透明染色。全部 132 种英文部件类型及数量、操作×交互交叉表均保存在 `statistics.json`，不把近义英文名称当成严格语义 taxonomy。

### 训练目录交集与评测状态

`/mnt/bn/strategy-mllm-train/user/tanyue/datasets/SAMTok_Training_Data/sam_info.json` 中匹配到本版 **200/200** 张 SA ID；抽样 2800 条中匹配 2799 条。目录成员关系不等于某个 checkpoint 实际训练过，但本版不能被描述为已经审计过的独立 holdout。正式研究比较前需结合实际训练清单与近重复检查界定模型暴露情况。

当前 95 项测试、全 200 case 浏览器加载与叠加检查通过；生成并校验了 200 个 native mixed 输入 job，未调用模型。源资产/标注校验通过，200 个源图 SHA256 唯一，1185 个资产逐文件核对；无模型运行、无模型得分、独立人工复核为 0。此处统计描述构建完成的任务集，不代表编辑模型已通过它。

## 7. 代码、数据与审核包路径

| 内容 | 路径 |
| --- | --- |
| 唯一 v2 repo | `/opt/tiger/samtok_edit_benchmark_v2branch`，分支 `v2branch` |
| 唯一维护文档 | repo `README.md`；`/opt/tiger/SAMTok Benchmark v2.md` 指向它 |
| 正式版本元数据 | repo `data/v2/`，同步到 `{root}/benchmark/` |
| 数据总根目录 | `{root}` |
| 正式源图 | `assets/v2-sa_<id>/source.jpg` |
| 正式单目标 mask | `assets/v2-sa_<id>/U1.png` … `U5.png` |
| 选区复核图 | `assets/v2-sa_<id>/selection_review.jpg`，原标注 ID 见元数据 |
| 源素材筛选过程 | `sa1b_source_selection/`，候选/备用/原 RLE/检索日志 |
| 指令过程 | `construction/instructions/`，design.tsv、审图 sheets、进度记录 |
| 正式模型运行与输出 | `evaluation/`，与任务源资产分开；本版尚无运行 |
| 历史归档 | `archive/pre_sa1b_212_v2_2.1.0/`、`archive/previous_review_packages/`，不属当前评测 |
| 本机审核包目录 | `/opt/tiger/samtok_edit_benchmark_v2_review` |
| 当前本机审核目录 | `evaluation/review_protocol1_release2.3.0/`（相对数据根目录） |
| 当前正式输入 | `evaluation/inputs_protocol1_native/jobs.jsonl` |
| 当前审核压缩包 | `/opt/tiger/samtok_edit_benchmark_v2_review_release2.3.0_20261012.zip` |
| 完整离线 PDF | 审核包内 `benchmark_all_200_cases.pdf`，200 页，每页一个 case |

相对资产路径都以数据总根目录或便携包根目录为基准。仓库只保留当前任务元数据、代码、唯一说明及少量说明插图，不提交正式大图、过程图片、审核 zip、模型结果。历史 v1 单对象 API 的基础兼容代码/合成测试保留；当前数据仅 `data/v2/`，不携带旧评测清单。

正式元数据：`cases.jsonl` 为完整任务；`asset_manifest.jsonl` 为 1185 项资产清单；`provenance.jsonl` 为来源；`instruction_design.jsonl` 和 `instruction_reviews.jsonl` 为逐对象设计/逐图审查；`statistics.json`、`release.json`、`validation.json` 为统计、版本和验证；`selection/` 为选择依据。`release.json` 的 manifest SHA256 绑定当前任务，编辑输入、模型输出与评分均有摘要绑定。

[下载完整 2.3.0 审核包](https://huggingface.co/datasets/TTangenty/samtok_edit/resolve/main/samtok_edit_benchmark_v2_review_20261010.zip?download=true)；[直接查看全部 200 case 的 PDF](https://huggingface.co/datasets/TTangenty/samtok_edit/resolve/main/samtok_edit_benchmark_v2_all_200_cases.pdf?download=true)。此次发布目标为 release 2.3.0 / instruction protocol 1.0，沿用旧下载名与兼容下载名；文件名中的日期不代表内部版本。远端是否已完成替换，以发布回执的 `status` 和 `remote_updated` 为准。发布脚本在单次 HF commit 中替换两个 zip、校验文件、PDF 和说明，并核验远端 SHA256。发布回执见 `data/v2/review_package.json`；包内仅记录归档前内容验证，远端回执存于仓库与 HF 同名 JSON。

解压整个压缩包后，在包内运行：

```bash
python run_review.py
# 不自动打开浏览器时：
python run_review.py --no-browser --port 8766
```

打开 `http://127.0.0.1:8766/`。只需 Python 3.10+ 标准库与现代浏览器，不依赖编辑器的 html.showPreview 扩展。左侧选 case 后再加载图片。支持按目标数（含 5）、任务、来源、状态搜索；默认原图；一键全部 point/mask/box/ref，也可点击“全部 mask + box + ref”同时开启三层，各层可叠加，第二次点击关闭该层；逐对象也可切换。英文和中文指令同时展示，正式混合输入可恢复冻结交互形式。

审核决定、每对象问题和指令建议写入包内 `reviews/review_results.json`，刷新保留，可导出 JSON。正式任务清单不会被审核建议直接改写。发布包初始没有虚构的用户复核记录。

## 8. 构建、验证与运行

```bash
cd /opt/tiger/samtok_edit_benchmark_v2branch
python -m pip install -e '.[dev,review]'

python construction/build_sa1b_v2.py \\
  --dataset-root {root}
python construction/write_document.py \\
  --dataset-root {root}

samtok-benchmark-v2 validate --manifest data/v2/cases.jsonl \\
  --dataset-root {root} \\
  --minimum-cases 200 --output data/v2/validation.json

# 从冻结标注生成英文模型输入；不能直接把整个审核包喂给编辑模型。
samtok-benchmark-v2 prepare --manifest data/v2/cases.jsonl \\
  --dataset-root {root} \\
  --protocol native_regions_v2 --variants mixed \\
  --output {root}/evaluation/native_mixed

# output 必须是空目录；已有审核结果不会被覆盖。
samtok-benchmark-v2 review --manifest data/v2/cases.jsonl \\
  --dataset-root {root} \\
  --output /opt/tiger/samtok_edit_benchmark_v2_review

python -m pytest -q
python -m ruff check .
```

重新冻结需要现有 `sa1b_source_selection/gallery_data.json`、selected 资产和指令审查 sheets；不会重新随机抽图。若改写指令，需回看相应 case、更新设计记录、重新冻结并重建审核包，不能仅改网页文案。浏览器验证还需先运行 `python -m playwright install chromium`。`construction/check_review_browser.py` 检查真实浏览器中的全部 case、图像和叠加交互；`construction/publish_review.py` 归档并校验 HF 远程 SHA256。Git 提交遵循 `feat: ...` 等标准类型信息。

## 9. 可视化样例与实际双语指令

下图展示源图及全部已选 mask，颜色按 U1 红、U2 蓝、U3 金、U4 紫、U5 绿。这里完整展示选区以便审核，正式输入只给每个 U 冻结的形式。**这些是源图标注可视化，不是模型编辑结果。** 表中是正式模式实际发送的英文指令及审核用中文翻译；no-ref 的实例通过图上区域选择。

"""
        + "\n\n".join(examples)
        + "\n"
    )
    count = len(s["scope_types"])
    text = text.replace("全部 132 种英文部件类型", f"全部 {count} 种英文部件类型")
    (REPO / "README.md").write_text(text, encoding="utf-8")
    shutil.copyfile(REPO / "README.md", root / "BENCHMARK_V2_ZH.md")
    shutil.copytree(figures, root / "docs/assets", dirs_exist_ok=True)
    link = Path("/opt/tiger/SAMTok Benchmark v2.md")
    if link.is_symlink():
        link.unlink()
    if not link.exists():
        link.symlink_to(REPO / "README.md")
    print("Wrote canonical README and data copy; figures:", len(examples))


if __name__ == "__main__":
    main()
