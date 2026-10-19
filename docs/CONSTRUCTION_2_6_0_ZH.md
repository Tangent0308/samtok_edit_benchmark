# SAMTok Edit Benchmark 2.6.0：构造与校验过程

本文记录当前版本如何从源数据得到可发布的 1,084-case benchmark。它描述数据构造，不记录尚未完成的模型评测结果。

## 1. 源数据和冻结边界

数据来自 SA-1B 图像及本地配套 dense annotation。当前版本不再混入早期 PACO-LVIS/ADE20K 的 212 条样本。原版 200 张经过筛选后保留；扩充阶段从排除原版和训练 reservoir 的候选中继续筛选，最终新增 884 张，累计 1,084 张唯一源图。

源图、source mask、object id、来源哈希和审核记录保存在数据根：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2/
├── assets/<case>/                 # source.jpg、原始 U#.png、新 U#_v2.png 及 manifest 指定资产
├── benchmark/                     # 当前正式元数据镜像
├── benchmark_history/2.5.0/      # 旧 release 备份
└── release_2_6_work/<case>/       # 分割候选、final.jpg、配方和审图过程，不是评测输入
```

仓库的正式数据只从 [data/v2_2.6.0/cases.jsonl](../data/v2_2.6.0/cases.jsonl) 读取；`data/v2_1084/` 是 2.5.0 冻结基线，`data/v2/` 是原版 200 张，`data/v2_1k/` 是早期草稿，均不作为当前入口。

## 2. case 选择

每张源图必须满足：

1. 2–5 个可区分的编辑单元；
2. 至少两个交互形式，覆盖 ref/no-ref 和 point/box/mask 的组合；
3. 目标来自至少两个可区分的物理父对象，不能把同一人的不同部位、同一车辆的不同零件冒充独立对象；独立携带物可以单独计数；
4. 源图中目标可被看清、mask 有真实边界，并能写出无歧义的短指令；
5. 目标允许 add、replace、remove 或 attribute 中的一种自然编辑，且不会制造不合理的断肢、悬浮物或整图重绘任务。

候选阶段只生成建议，不自动接受。构造者必须看清洁原图、二值 mask 局部和全图定位图，核对类别、左右、前后、序数、同类实例、遮挡和父对象归属。低对比、透明、镂空、模糊和小目标可以保留为困难样本，但必须能说明其边界和指代；无法稳定解释的候选换目标或弃用。

截至冻结：新增候选 964 条视觉审核记录，其中 884 张接受、75 张保留、5 张不采用；加原版 200 张形成 1,084 张正式 case。扩充审核是 assistant 直接视觉检查，不是独立人工终审。

## 3. 编辑单元和 operation 设计

每个 U 由结构化 `instruction_spec` 生成英文 ref、blind no-ref、中文、completion requirement、edit contract 和 preserve 说明。U 只绑定一个源实例/部件/区段/附着部位和一种操作。

| 操作 | 设计规则 | 源 mask |
|---|---|---|
| add | 优先直接承载、附着、穿戴、容纳或印制；当前 release 的 add 都使用直接锚点 | 现有承载物或明确 site，不画新增物轮廓 |
| replace | 必须有结构或类别变化；无法自然替换的纯颜色/材质变化改为 attribute | 被替换的原物体/部件 |
| remove | 明确 whole、part、contents 或区段的范围和终点 | 实际被删除对象、部件或区段；含内容物时按契约合并 |
| attribute | 只改变 color/material/finish/pattern/texture/text 等属性，保留身份和结构 | 属性实际发生变化的物体、表面或部件 |

replace 不把整个人改成衣服，也不把单纯换色包装成结构替换。add 的 relation/site 分开存储；不会靠扫描 `near/below/above` 自动猜测锚点语义。颜色、左右和类别都从无标注原图核实，不能从彩色定位图读取。

## 4. 协议 2.0 和 no-ref

2.6.0 固定：

- `instruction_protocol_version=2.0`；
- `mask_semantics.version=2.0`；
- `instruction_style=benchmark-concise-3-blind-1`；
- no-ref 统一盲指代 `the selected region`；
- source mask 等于实际编辑区域，ref/no-ref 共用同一 mask，box/point 从该 mask 确定性计算。

构造步骤先写 ref 的“对哪里做”和“做什么”，再由 canonical `instruction_protocol.py` 从同一 spec 渲染 no-ref：只把源目标、部件、宿主、方位、序数和 add site 整体替换成 `the selected region`，操作、payload、属性值、附着关系和必要结果要求保留。禁止手写 no-ref，也禁止在 no-ref 中泄露源类别、位置或宿主。

中文和英文同步更新；不把通用保留句堆进每条指令，公共 preserve/edit contract 在评测私有字段中保存。历史 1.0 只在兼容层和归档文档中保留，用于核查旧 release，不参与 2.6.0 生成。

## 5. mask 精修

2.0 mask 语义要求“源 mask = 实际编辑区域”：

- 整体编辑保留实际物体可见像素、孔洞和遮挡边界；
- part/target_part 只画部件；剪短只画被剪掉的区段；
- add 只画附着部位；新物体的边缘、阴影和超出部分不预先画进输入 mask；
- remove contents 根据 `contents` 或 `contents_only` 明确是否包含容器；
- 保留 `mask_v1`、`box_v1`、`point_v1` 以便追溯，发布文件是 `U#_v2.png`。

每个候选 mask 在干净原图上检查颜色、类别、左右、边界、遮挡和独立目标关系；提交前看对应 `final.jpg`。构造校验再检查尺寸、二值非空、point 是否在 mask 内、box 是否为紧致半开框、目标交叠和源图哈希。需要时按“改指令 → 修 mask → 同图换独立目标 → 删除单元”的顺序处理；当前版本没有删除 case 或单元。

2.6.0 共发布 708 张新版 mask，其中 299 个是协议要求的部件/site mask；1,552 条 ref 改写、3,872 条 no-ref 重渲染，691 张新版 mask 的像素发生变化。修订记录在 `construction/release_2_6/revisions/`，构建应用记录在 `data/v2_2.6.0/revisions_applied.jsonl`。

## 6. 审查、修订和发布

发布前按以下顺序执行：

1. `remaining_work.jsonl` 收集每个 case 的审查问题和 `part_masks_needed`；
2. 按 `todo / partial / done_unlogged / done` 处理，逐 case 修改 revision JSON；
3. 用 `round2` reviewer 写 `construction/release_2_6/logs/round2.jsonl`，记录真实动作、证据和不采纳的审查意见；
4. `status.py` 重新计算状态，确保 open findings 和待换部件 mask 为 0；
5. `build.py` / `publish.py` 生成 release manifest、mask patch、comparison、统计和 current pointer；
6. 安装补丁到数据根并运行完整资产/几何/协议校验。

最终磁盘状态：804 个修复任务完成，另 280 个 case 无专项修复任务而统一迁移协议；最后一轮 758 个单元动作是 keep 450、revise 299、retarget 9、drop 0。全库没有删除 case 或 unit；状态清单没有未解决 case。

构建级检查通过并不等于独立语义终审：`independent_human_verified=false`、`semantic_signoff=false`。早期审查卡和 PDF 属于过程证据，不能替代当前 manifest，也不能当成模型输出质量结果。

## 7. 可复现入口

在仓库根目录运行：

```bash
PYTHONPATH=. /opt/tiger/envs/gen/bin/python construction/release_2_6/materialize_masks.py \
  --dataset-root /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2

PYTHONPATH=. /opt/tiger/envs/gen/bin/python construction/release_2_6/status.py

PYTHONPATH=. /opt/tiger/envs/gen/bin/python -m samtok_benchmark.v2.cli validate \
  --manifest data/v2_2.6.0/cases.jsonl \
  --dataset-root /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2 \
  --minimum-cases 1000 --output data/v2_2.6.0/validation.json
```

构造工具的入口按职责分在 `construction/` 和 `construction/release_2_6/`；模型生成、输入编码和 judge 在 `evaluation/` 与 `samtok_benchmark/v2/`。不要直接改写 `data/v2_1084/`、`data/v2/` 或数据根旧备份。
