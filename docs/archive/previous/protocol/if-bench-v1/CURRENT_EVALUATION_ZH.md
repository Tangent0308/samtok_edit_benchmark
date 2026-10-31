# IF-Bench 当前详细评测方式：fairness v2.1 / dev20

本文件说明 **2026-10-30 用户已确认修复后的方案**，与[v2.1执行修订](PROTOCOL.fairness-v2.1.dev20.md)配套。它是方法说明，不是分数报告。范围是七模型×十setting×同一二十张dev图，共1400个逻辑请求；只改变Qwen2.1的2K配置及MICE短前导/完整性检查，没有新候选搜索，未授权正式冻结或test。

旧 108 图候选实验、前置两图验证、当前 20 图 dev 是三个不同阶段，不能混算结果。前置验证的 140/140 表示都生成了可读取且绑定正确的图片，**不表示编辑任务通过**。2026-10-31 的原生 offload 修复已补齐 Qwen2.1 的 177 条解码 OOM，全部成功输出的 Judge 已完成；最新计数、历史成本及带图报告见[修复运行记录](DEV20_RECOVERY_RUN_ZH.md)，原启动方式见[启动指南](DEV20_RUN_ZH.md)。

## 1. 公平性、样本与适用范围

同一 setting、同一 case 的模型获得相同公开文本和区域信息。适配器只能机械地组织 prompt、图像、标记与原生区域参数；不能查看未公开的目标名、mask/bbox 或合法效果契约。RePlan/MIRAGE 自身的规划与定位属于被评测完整方法，并逐项记成本；不把它们的分数称为裸 Qwen 骨干分数。

不接外部 SAM、grounder、语义补全、caption 改写器；Qwen PE 和 FLUX PUP 关闭。即使组件是官方提供的可选增强器，也不自动进入本轮方法边界。不因低分改 prompt、手修计划、扩大区域或换 seed。每个 case 的多个目标在**一次原生联合编辑流程**中完成，不人为串行编辑 K 次。

| 项目 | 固定规则 |
|---|---|
| 数据 | release 2.6.0，1,084 张图；manifest SHA256 `818ce524a1d1f363dc8ea5caa7a887b2dd0355c17a5600d1cbd696cffcf263fb` |
| 原 split | 108 dev / 976 test，按源图隔离；沿用原 split 与 S4/S5 分配 |
| 本轮 dev | 从原 108 dev 按 K 比例分层；各 K 至少一图、最大余数分配名额，层内按 SHA256(`20261027:{source_id}`) 排序取样 |
| 样本数 | K=2/3/4/5 分别 3/4/11/2 图，共 20 图、72 个编辑单元；所有模型相同 |
| 剩余开发图 | 88 图仍属于 dev，不转入 test；抽样不读取输出或分数 |
| 采样 | 生成 seed=42，每个请求一份输出；原生内部分支和调用另计 |
| 方案 | 每模型一个预先确定的公平性方案；Qwen dual 是呈现规则，不冒称旧 JointPass 搜索胜者 |
| 范围外 | MaskFlow 暂缓，因为未验证一次联合多目标编辑；不计入本轮失败或 N/A 分母。其他可选/附录方法另行安排 |
| 执行门 | 完成 dev 与 Judge 后写 `REVIEW_REQUIRED.json`；等待用户确认正式冻结/test |

S2 的丢弃区域只作为 **S1 精确复用的补充行**，不替换主行，也不按分数重新选型。S3、S4-noref 和 S5 的 no-ref 单元不得丢弃区域。当前七模型十 setting 都有已批准的输入路径；低分、误定位或生成失败不改称 N/A。

## 2. 十个 setting 提供什么

`I` 是清洁源图；`A` 是该 setting 的统一标注副本；`T_ref` 是数据中原始 ref 指令；`T_noref` 是数据中原始 no-ref 指令，不能把省略的目标描述补回去。表中的“区域”选择源对象、部件或新增内容的依附锚点，**不是编辑后差分 GT，也不总是硬编辑边界**。

| Setting | 每单元指令 | 每单元公开区域 | 关键限制 |
|---|---|---|---|
| S1 | `T_ref` | none | 不给标记图、坐标或隐藏区域 |
| S2-point | `T_ref` | point | 保留点，不猜一个物体框 |
| S2-box | `T_ref` | box | 源选择框，不捏造输出对象框 |
| S2-mask | `T_ref` | mask | 公开二值 mask，可机械编码为完整轮廓 |
| S3-point | `T_noref` | point | 不能补对象名或丢点 |
| S3-box | `T_noref` | box | 不能补对象名或丢框 |
| S3-mask | `T_noref` | mask | 不能补对象名或丢 mask |
| S4-ref | `T_ref` | 固定逐单元 point/box/mask 混合 | 所有模型共用同一分配 |
| S4-noref | `T_noref` | 与 S4-ref 完全相同 | 只改变语言指代，区域分配不变 |
| S5 | manifest 冻结的逐单元 ref/no-ref | manifest 冻结的 none/point/box/mask | none 必须保留 ref；不为 none 单元补一个区域 |

### 2.1 坐标与统一标记

公开坐标原点在左上角，x 向右、y 向下。point 为源图像素 `(x,y)`；box 为半开区间 `(x1,y1,x2,y2)`，`0 ≤ x1 < x2 ≤ W`、`0 ≤ y1 < y2 ≤ H`；mask 与源图同尺寸，白色选中、黑色未选中。模型所需的 normalized xyxy 用 `(W,H,W,H)` 分别相除。

标注固定为 U1…UK；颜色依次为 red `(255,0,0)`、blue `(0,80,255)`、green `(0,170,0)`、yellow `(255,210,0)`、magenta `(230,0,230)`。点半径 `max(1,round(.01*min(W,H)))`，白环宽 `.002` 比例；框/轮廓宽 `.004` 比例。字号 `max(12,round(.02*min(W,H)))`，固定 DejaVuSans 字体及 hash，使用 Python ties-to-even round。

mask 画所有内部边界，包括洞、分离组件与贴边部分；不填色覆盖目标。U 标签与引线仅依赖当前公开几何放置。`A` 与 `I` 同尺寸、同坐标，变换为 identity；适配器之后的模型原生缩放另记。标记会覆盖少量源像素，也可能在原生缩放后难以辨认，这些限制不能靠私有 GT 清理。

实现：[public.py](../../../../../src/samtok_benchmark/ifbench/public.py)、[render.py](../../../../../src/samtok_benchmark/ifbench/render.py)。旧 `geometry.py` 中的小框、mask→bbox 函数为历史流程保留，**不是当前 point 输入规则**。

### 2.2 共享最终 prompt

Qwen 两版、FLUX2 的 S1 使用下面的完整模板；`{instruction_i}` 逐字取对应公开指令：

```text
Apply all of the following edits to the image. Keep everything else unchanged.
U1. {instruction_1}
U2. {instruction_2}
...
```

它们的有区域 setting，以及 FLUX3 的有区域 setting，使用：

```text
Image 1 is the clean source image to edit. Image 2 is the same image with colored marks and U labels. Use the marks only to identify the selected regions in Image 1. Return only the edited Image 1. Do not reproduce any marks, labels, or leader lines.
Each supplied region selects a source object, part, or anchor. For an addition, it selects the attachment or support location, not the outline of the new object.
Apply all of the following edits to the image. Keep everything else unchanged.
U1. [{color_1} {shape_1}, label U1] {instruction_1}
U2. [{color_2} {shape_2}, label U2] {instruction_2}
...
```

`shape` 只能是 `point`、`box`、`mask contour`；none 单元省略整个中括号，不造标记。请求完全没有区域时只用第一种模板和 `I`。`...` 只是本文表示后续单元的占位符，实际 prompt 没有省略号。实际全文保存于每请求的 `request.json` / `call.json`；不是自然语言改写器生成。

实现：[inputs.py](../../../../../src/samtok_benchmark/ifbench/inputs.py)。RePlan、MIRAGE 和 MICE 的原生接口所需差异在下面单独说明。

## 3. Qwen-Image-Edit-2511

原生 `QwenImageEditPlusPipeline` 接收图像列表和 prompt，没有单独 bbox/point/instance-mask 参数。区域通过 `A` 提供，不声称具有硬 mask 编辑约束。保留权重自带 Qwen2.5-VL 编码器、DiT、VAE 和 scheduler，没有外接规划器。

| Setting | 实际编辑器图像参数 | 指令与区域呈现 |
|---|---|---|
| S1 | `[I]` | `T_ref`，共享 S1 模板 |
| S2-point | `[I,A]` | `T_ref` + 点/U 绑定 |
| S2-box | `[I,A]` | `T_ref` + 框/U 绑定 |
| S2-mask | `[I,A]` | `T_ref` + 完整 mask 轮廓/U 绑定 |
| S3-point | `[I,A]` | `T_noref` + 点/U 绑定 |
| S3-box | `[I,A]` | `T_noref` + 框/U 绑定 |
| S3-mask | `[I,A]` | `T_noref` + 完整轮廓/U 绑定 |
| S4-ref | `[I,A]` | `T_ref` + 固定混合标记 |
| S4-noref | `[I,A]` | `T_noref` + 同一混合标记 |
| S5 | `[I,A]`，若全 none 则 `[I]` | 冻结的混合指令；仅标注已有区域 |

固定 `num_inference_steps=40`、`true_cfg_scale=4`、`guidance_scale=1`、`negative_prompt=" "`、`max_sequence_length=512`、`num_images_per_prompt=1`。40 步来自权重 card 的示例，不把 pipeline 函数的 50 步默认混称同一值。

原生视觉语言条件约 384² 面积，VAE 条件约 1024² 面积；不是所有图像条件都只有 384 像素。图像顺序通过 prompt 定义，pipeline 不提供“绝不复制第二图”的硬保证；标记残留保留在实际输出。

证据：[官方接口与默认参数](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L527)、[原生预处理](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L648)、[40 步模型 card](https://huggingface.co/Qwen/Qwen-Image-Edit-2511/blob/6f3ccc0b56e431dc6a0c2b2039706d7d26f22cb9/README.md#L39)。本地调用由 [fairness_dev_worker.py](../../../../../src/samtok_benchmark/ifbench/fairness_dev_worker.py) 复用 [dev_runner.py](../../../../../src/samtok_benchmark/ifbench/dev_runner.py) 的 `Qwen2511` adapter。

## 4. Qwen-Image-2.1

使用原生 `QwenImage21Pipeline`；权重自带 Qwen3-VL 编码器、DiT、VAE、scheduler 和 KV cache 保留。独立 PE 检查点及其改写调用关闭。模型内部视觉编码器不等同于外接增强组件。

| Setting | 实际编辑器图像参数 | 指令与区域呈现 |
|---|---|---|
| S1 | `[I]` | `T_ref`，共享 S1 模板 |
| S2-point | `[I,A]` | `T_ref` + 点/U 绑定 |
| S2-box | `[I,A]` | `T_ref` + 框/U 绑定 |
| S2-mask | `[I,A]` | `T_ref` + 完整轮廓/U 绑定 |
| S3-point | `[I,A]` | `T_noref` + 点/U 绑定 |
| S3-box | `[I,A]` | `T_noref` + 框/U 绑定 |
| S3-mask | `[I,A]` | `T_noref` + 完整轮廓/U 绑定 |
| S4-ref | `[I,A]` | `T_ref` + 固定混合标记 |
| S4-noref | `[I,A]` | `T_noref` + 同一混合标记 |
| S5 | `[I,A]`，若全 none 则 `[I]` | 冻结的混合指令；none 单元只给文字 |

固定40步、true CFG=1、`output_resolution=2048`、`use_kv_cache=True`、PE=False。v2.1按作者README的2K推荐执行；旧v2的1024是pipeline默认，只保留为历史配置，不复用其输出、不在两种分数间择优。视觉与VAE条件沿用原生缩放和宽高比；mask仍为轮廓图。请求、环境账本及实际参数一致；显存不足不自动降回1K。

2026-10-31 的工程修复增加显式 `execution.memory_policy="model_cpu_offload"` 选项，使用原生 CPU offload 调度组件，不改上述输入或计算参数。已用固定 S1/S2-point 两例验证，其中 S1 与原成功输出逐像素一致；S2-point 能完成但有标记残留。原发布 v2.1 包仍保留常驻 GPU 配置及其失败，诊断结果不混入 dev 分数。详见[修复验证与恢复边界](ENGINEERING_REPAIR_20261030_ZH.md)。

随后用户明确授权在本机完成修复后的 dev20 与全部缺失 Judge。新包 `fairness-v21-qwen-repaired-dev20-20261031` 仅重跑原177个已终止的Qwen2.1解码OOM请求；23个原成功输出经相同公开请求、权重版本和采样参数校验后复用，并披露resident来源。其余六模型原终态保留，单独恢复完成的Judge记录经完整provenance校验后复用。原失败及已经完成40步去噪的成本、两例独立诊断均保留；诊断输出不能代替本轮输出。实现入口为 `evaluation.protocol_audit.prepare_fairness_dev20_recovery`；这不是新的输入方案搜索，完成后仍停在dev审核门。

证据：[接口与默认值](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/qwenimage21/pipeline_qwenimage21.py#L511)、[预处理](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/qwenimage21/pipeline_qwenimage21.py#L608)、[官方分辨率示例](https://github.com/QwenLM/Qwen-Image-2.1/blob/ab96caa944157ca28a4f36b695c3047549f48f98/README.md#L230)、[独立 PE](https://github.com/QwenLM/Qwen-Image-2.1/blob/ab96caa944157ca28a4f36b695c3047549f48f98/prompt_rewrite/README.md#L1)。本地入口：`smoke_adapters.Qwen21`，由当前 worker 调用。

## 5. FLUX.3 Klein distilled

使用官方 `generate` / `Pipeline`，固定 `boxes=None`、PUP=False。图像列表提供公开标记，不构造 `src_bbox=tgt_bbox` 表格，也不捏造 remove/add 的输出对象框。保留原生 DiT、文本编码器、autoencoder。两张参考图在官方最多十图接口范围内。

| Setting | 实际图像参数 | prompt / 几何参数 |
|---|---|---|
| S1 | `[I]` | 下述原生 S1 文本；`boxes=None` |
| S2-point | `[I,A]` | 共享 dual 模板 + `T_ref`/点；`boxes=None` |
| S2-box | `[I,A]` | dual + `T_ref`/框；`boxes=None` |
| S2-mask | `[I,A]` | dual + `T_ref`/完整轮廓；`boxes=None` |
| S3-point | `[I,A]` | dual + `T_noref`/点；`boxes=None` |
| S3-box | `[I,A]` | dual + `T_noref`/框；`boxes=None` |
| S3-mask | `[I,A]` | dual + `T_noref`/完整轮廓；`boxes=None` |
| S4-ref | `[I,A]` | dual + `T_ref`/固定混合；`boxes=None` |
| S4-noref | `[I,A]` | dual + `T_noref`/同一混合；`boxes=None` |
| S5 | `[I,A]`，若全 none 则 `[I]` | 冻结混合文字/已有标记；`boxes=None` |

S1 精确保留已验证的原生文本，不追加 U/区域表：

```text
Edit <ref_image_0>. {instruction_1} {instruction_2} ... Keep everything else unchanged.
```

这里原始指令用单个空格连接，省略号仅为文档占位符。固定 distilled、16 步、`guidance=None`、seed=42；`safety=False` 是官方默认，不加载未启用的可选分类器。PUP 关闭偏离官方增强器推荐，符合本轮已确认组件边界；不能把结果说成含 PUP 系统成绩。

单图原生处理最多约 4 MP，双图每图约 1 MP；保留原生 pad/crop 和 16 像素网格策略。S1→区域 setting 的差值因此包含预处理变化，不能解释成纯区域信息因果效应。

证据：[可省略 boxes 的入口](https://github.com/black-forest-labs/flux-3-image-klein/blob/bfc8889a4497f846416f253a3972a1941ac698b9/src/flux3/generate.py#L30-L75)、[原生多图接口](https://github.com/black-forest-labs/flux-3-image-klein/blob/bfc8889a4497f846416f253a3972a1941ac698b9/src/flux3/pipeline.py#L62-L94)、[原生预处理](https://github.com/black-forest-labs/flux-3-image-klein/blob/bfc8889a4497f846416f253a3972a1941ac698b9/src/flux3/pipeline.py#L133-L176)。本地： [fairness_flux3_replan.py](../../../../../src/evaluation/protocol_audit/fairness_flux3_replan.py) 的 `request` / `Flux3FairnessRunner`。

## 6. RePlan（Qwen-2511 骨干）

**每个 setting 都保留官方 TainU/RePlan-Qwen2.5-VL-7B planner，再执行一次 Qwen-2511 区域联合编辑。** 不是只在缺区域时使用 planner，也不是 benchmark 替它手写局部计划。

| Setting | planner 实际图像和公开指令 | editor 实际输入 |
|---|---|---|
| S1 | `I` + 共享 `T_ref` 文本 | `I` + 原生 response |
| S2-point | `A` + `T_ref`/点/U 绑定 | `I` + 原生 response |
| S2-box | `A` + `T_ref`/框/U 绑定 | `I` + 原生 response |
| S2-mask | `A` + `T_ref`/完整轮廓/U 绑定 | `I` + 原生 response |
| S3-point | `A` + `T_noref`/点/U 绑定 | `I` + 原生 response |
| S3-box | `A` + `T_noref`/框/U 绑定 | `I` + 原生 response |
| S3-mask | `A` + `T_noref`/完整轮廓/U 绑定 | `I` + 原生 response |
| S4-ref | `A` + `T_ref`/固定混合 | `I` + 原生 response |
| S4-noref | `A` + `T_noref`/同一混合 | `I` + 原生 response |
| S5 | `A`（全 none 时 `I`）+ 冻结混合指令 | `I` + 原生 response；none 由自身理解 |

有区域时，把共享 single 模板的首句换成下面固定前导，随后原样保留 selector 说明、BASE 与 U/颜色/任务行：

```text
This is an annotated copy of the source image. Use the colored marks and U labels only to identify the selected source regions. The marks, labels, and leader lines are not scene objects or editing targets. Plan the requested edits for the clean source image with the same dimensions and coordinates.
```

上述文本仍交给官方 `build_messages` 拼接 `replan.txt`，`get_vlm_response` 使用原生生成参数和 `max_new_tokens=2048`，保留原始 response。再用 `region_edit_with_attention(I, response, ...)` 编辑清图，不手改 bbox/hint、global/local 分工或目标数，也不重复把 local 任务追加到 global。

这是**官方分阶段 API 的明确编排**；不是原样调用 `edit_single` 单图 wrapper。planner 看 `A`、editor 看同坐标 `I`，坐标变换为 identity，原生 response 的像素框及后续框处理不人工纠正。标签被误当目标、漏项或错误框属于方法表现。

固定 40 步、true CFG=4、guidance=1、negative=`" "`、`expand_value=0`、`attention_switch_step=.5`。0/.5 来自官方 CLI 的 qwen/qwen2511 分支默认；Python 方法默认 .15/0，eval YAML 还有其他值，不能称为唯一默认或作者明确推荐。planner 以 SDPA 替代环境缺少的 FlashAttention2，记录 backend 差异，不承诺逐位等价。

证据：[官方完整方法](https://github.com/JIA-Lab-research/RePlan/blob/6c9b12f0c619cc8ca6f50b536b24aff377525f8c/README.md#L105-L124)、[消息入口](https://github.com/JIA-Lab-research/RePlan/blob/6c9b12f0c619cc8ca6f50b536b24aff377525f8c/replan/pipelines/replan.py#L401-L416)、[原生生成与返回图像](https://github.com/JIA-Lab-research/RePlan/blob/6c9b12f0c619cc8ca6f50b536b24aff377525f8c/replan/pipelines/replan.py#L465-L512)、[wrapper 调用关系](https://github.com/JIA-Lab-research/RePlan/blob/6c9b12f0c619cc8ca6f50b536b24aff377525f8c/replan/pipelines/replan.py#L1058-L1086)、[CLI 默认](https://github.com/JIA-Lab-research/RePlan/blob/6c9b12f0c619cc8ca6f50b536b24aff377525f8c/replan/inference/run_replan.py#L183-L192)。本地：`fairness_flux3_replan.ReplanPlannerOnlyRunner` / `ReplanEditorOnlyRunner`。

## 7. MIRAGE（Qwen-2511 骨干）

保留官方 Qwen3.5-9B parser/locator 与 MIRAGE 局部/全局联合去噪。每条公开 unit 指令独立作为原生 parser 的一个 batch item，保留其返回的**全部** `(refer_object,new_instruction)` 对。原生拆分数可以不同于 benchmark 的 K，不增加“必须恰好 K 对”的人工拒绝规则。

| Setting | parser / locator 获得的信息 | 最终联合编辑器 |
|---|---|---|
| S1 | parser 读 `T_ref`；locator 看 `I` | `I` + 原始全局指令 + 原生局部指令/预测框 |
| S2-point | parser 读 `T_ref`；locator 看 `A` + 当前 unit 点/U 提示 | 同上 |
| S2-box | parser 读 `T_ref`；locator 看 `A` + 当前 unit 框/U 提示 | 同上 |
| S2-mask | parser 读 `T_ref`；locator 看 `A` + 当前 unit 轮廓/U 提示 | 同上 |
| S3-point | parser 读 `T_noref`；locator 看 `A` + 当前 unit 点/U 提示 | 同上；不补私有对象名 |
| S3-box | parser 读 `T_noref`；locator 看 `A` + 当前 unit 框/U 提示 | 同上 |
| S3-mask | parser 读 `T_noref`；locator 看 `A` + 当前 unit 轮廓/U 提示 | 同上 |
| S4-ref | parser 读 `T_ref`；locator 看同一混合 `A` + 各 unit 提示 | 同上 |
| S4-noref | parser 读 `T_noref`；locator 看同一混合 `A` + 各 unit 提示 | 同上 |
| S5 | parser 读冻结混合指令；locator 看 `A`，none 无额外空间提示 | 同上；none 仍走自身定位 |

空间提示追加到原生 grounding 消息，**不塞进 refer_object**，以免改变 `_split_part`。固定文本为：

```text
Spatial input for this edit: the {color} {shape} labeled {unit_id} indicates the selected source object, part, or anchor. The marks and labels are input annotations, not the target object. For an addition, the selection identifies the existing attachment or support location, not the outline of the new object.
```

原生 direct、parent、part 定位与裁剪分支保留，裁剪图也保留公开提示。定位结果是 normalized xyxy，经官方 `to_pixels(...,padding=10)` 变成源图像素框。用原生 `qwen_prompt` 构造局部编辑文本；最终全局文本是共享 `global_prompt(public)`，清图只编辑一次。原生分支中的 parent 回退属于方法内部流程，与 benchmark 擅自换成 S1/裸骨干不同。

固定 40 步、true CFG=4、negative=`" "`、patch ratio=.4；parser/locator `thinking=False`、`do_sample=False`，parser 最多 512 新 token、grounding 最多 128。环境缺少 FLA 时使用模型原有 PyTorch reference kernel，披露实现差异。记录每次 chat API、batch item、原生拆分对数、分支与实际 diffusion forward；不能把一个 batch item 当一次独立 API。

证据：[原生 parser](https://github.com/ZiqianLiu666/MIRAGE/blob/234a31968df307879a55675873a54258d6c0eae4/mirage/vlm.py#L409-L472)、[原生定位/parent/part](https://github.com/ZiqianLiu666/MIRAGE/blob/234a31968df307879a55675873a54258d6c0eae4/mirage/vlm.py#L237-L272)、[Qwen3.5 grounding](https://github.com/ZiqianLiu666/MIRAGE/blob/234a31968df307879a55675873a54258d6c0eae4/mirage/vlm.py#L300-L317)、[局部 prompt 和联合编辑](https://github.com/ZiqianLiu666/MIRAGE/blob/234a31968df307879a55675873a54258d6c0eae4/inference.py#L62-L91)。本地：[请求构造](../../../../../src/evaluation/protocol_audit/fairness_mirage_mice_probe.py) 的 `payload` / `spatial_hint`、[实际 worker](../../../../../src/samtok_benchmark/ifbench/fairness_dev_worker.py) 的 `_mirage_plan` / `_trace_mirage`。

## 8. MICE（FLUX.2 Klein-4B 骨干）

保留 MICE 原生多实例 attention 和 Klein-4B distilled。当前 attention 的双参考图路径在原生函数重放中发生 token 索引越界，因此**只传一张图**，不改写 attention 补多图能力。没有原生点定位器，也不接外部组件。

| Setting | 实际单图 | global / local / 区域绑定 |
|---|---|---|
| S1 | `I` | 所有 `T_ref` 进入 global；零实例绑定 |
| S2-point | `A` | 所有 `T_ref` + 点/U 进入 global；不造框或 mask |
| S2-box | `I` | 每条 `T_ref` 进入 local；原生 normalized xyxy box API |
| S2-mask | `I` | 每条 `T_ref` 进入 local；公开 mask 的原生 binding |
| S3-point | `A` | 所有 `T_noref` + 点/U 进入 global；不造框或 mask |
| S3-box | `I` | 每条 `T_noref` 进入 local；原生 box API |
| S3-mask | `I` | 每条 `T_noref` 进入 local；原生 mask binding |
| S4-ref | 有 point 则 `A`，否则 `I` | point→global；box/mask→对应 local；都用 `T_ref` |
| S4-noref | 与 S4-ref 同一选择 | 同一逐模态映射，改为 `T_noref` |
| S5 | 有 point 则 `A`，否则 `I` | none/point→global；box/mask→local；使用冻结混合文字 |

有 point 时直接复用完整共享 `A`，不会悄悄擦掉其中其他 unit 的框/轮廓；这些 unit 也按原生 API 获得相同区域，未添加信息。无 point 时用清图。S1/纯 point 属于原生 global-only 路径；point 确实通过标记提供了，但不是原生硬点绑定，也不是 discard。原生 global/local 相互作用与单图去标记负担如实保留。

prompt 是 `[global_text, local_1, ...]` 用官方分隔符 `$BREAKFLAG$` 拼接。global 只列 none/point 的原文任务，local 只列对应 box/mask 的原文任务，保持 unit 顺序。含 point 的 global 前导为：

```text
U marks select source objects, parts, or attachment points. Remove all marks; keep everything else unchanged.
```

随后直接接global unit行，任务原文与U/颜色标签不变；不再叠加旧长selector说明和BASE。没有point时仍只用BASE加global unit行；没有global任务时保留BASE，不把local任务复制到global。

官方`outer_local_prompts`实际只保留每段前200个文本条件token，不能只检查512上限。构建包及生成前按真实chat模板核对完整长度≤200，并检查原生前200有效token IDs与完整序列一致。失败在提交生成前落终态，保留原因及0次调用，不创建started、不删词、不改官方200默认。旧S2-point的4/20文本缺失记录保留；新版对全部84个含point请求统一修订。

区域具体调用：仅含 box 的 regional 列表传 `instance_bboxes_xyxy_normalized`；包含 mask 时传 `instance_masks_yx`，box 用官方 floor/ceil 函数生成绑定网格，mask 用官方 nearest resize 到同一网格。mask 不先变 bbox；point 不进入 regional 列表。实际网格和非零 token 数保存为 `binding-U*.png` 与 `call.json`，小 mask 原生量化为空时不手工扩张。

画布按官方 loader：`W'=round(sqrt(1024²*W/H))//16*16`、`H'=round(sqrt(1024²*H/W))//16*16`；图像用 LANCZOS resize，mask 采用原生 nearest。绑定网格为 `(H'/16,W'/16)`。固定 4 步、CFG=1、`outer_local_prompts`、`apitasmkernelnonlap`、`strict=False`、kernel=11、temperature=3、sigma=.6，binding 覆盖全部四步。

证据：[官方 CLI/API](https://github.com/Blowing-Up-Groundhogs/mice/blob/43b289de84dfd184c0ee1b551b0e1bea02f6e92d/infer_flux2_mice.py#L30-L79)、[区域分支](https://github.com/Blowing-Up-Groundhogs/mice/blob/43b289de84dfd184c0ee1b551b0e1bea02f6e92d/flux2/pipeline_flux2_klein.py#L903-L912)、[原生 box 量化](https://github.com/Blowing-Up-Groundhogs/mice/blob/43b289de84dfd184c0ee1b551b0e1bea02f6e92d/flux2/pipeline_utils.py#L56-L75)、[单参考图 attention 假设](https://github.com/Blowing-Up-Groundhogs/mice/blob/43b289de84dfd184c0ee1b551b0e1bea02f6e92d/flux2/attention/attention_processor_APITASM_kernel_nonlap.py#L380-L403)、[strict=False factory](https://github.com/Blowing-Up-Groundhogs/mice/blob/43b289de84dfd184c0ee1b551b0e1bea02f6e92d/flux2/attention/__init__.py#L13-L19)。本地：`fairness_mirage_mice_probe.payload` 和 `fairness_dev_worker._mice_edit`。

## 9. FLUX.2 Klein-9B distilled

本行是 **9B 蒸馏版**，不是 MICE 的 4B 骨干，也不是 base/KV 版本。使用 `Flux2KleinPipeline` 原生图像列表接口、Qwen3-8B 文本编码器、DiT、VAE、scheduler；文本编码器是检查点组成部分，不是额外图像解释器。

| Setting | 实际图像参数 | 公开输入 |
|---|---|---|
| S1 | `[I]` | `T_ref`，共享 S1 模板 |
| S2-point | `[I,A]` | `T_ref` + 点/U 绑定 |
| S2-box | `[I,A]` | `T_ref` + 框/U 绑定 |
| S2-mask | `[I,A]` | `T_ref` + 完整轮廓/U 绑定 |
| S3-point | `[I,A]` | `T_noref` + 点/U 绑定 |
| S3-box | `[I,A]` | `T_noref` + 框/U 绑定 |
| S3-mask | `[I,A]` | `T_noref` + 完整轮廓/U 绑定 |
| S4-ref | `[I,A]` | `T_ref` + 固定混合标记 |
| S4-noref | `[I,A]` | `T_noref` + 同一混合标记 |
| S5 | `[I,A]`，若全 none 则 `[I]` | 冻结混合文字，none 无额外标记 |

固定 4 步、`guidance_scale=1`、`max_sequence_length=512`，按蒸馏模型推荐而非通用 pipeline 的 50/4 默认。图像走 VAE 条件；每图超过 1024² 时按原生处理缩小，再对齐 VAE 网格。超过 512 token 的完整请求记录失败，不删指令或补做另一份采样。9B 权重已获授权并下载，启动不要求在脚本中填写 token。

证据：[原生多图入口](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/flux2/pipeline_flux2_klein.py#L616)、[原生预处理](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/flux2/pipeline_flux2_klein.py#L762)、[蒸馏 9B 的 4/1 默认](https://github.com/black-forest-labs/flux2/blob/50fe5162777813d869182b139e83b10743caef15/src/flux2/util.py#L28)。本地：`fairness_dev_worker.NativeBackend` 的 `flux2_klein9b` 分支。

## 10. 固定版本、调用与工程差异

下表源码/权重SHA沿用已核验版本，不在运行时重新解析`main`/`latest`。新版参数见[MODEL_CONFIGS.dev21.json](MODEL_CONFIGS.dev21.json)，旧[dev20快照](MODEL_CONFIGS.dev20.json)保留历史1K配置。Qwen两版及FLUX2使用的Diffusers固定为`06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a`。

| 模型 | 官方方法 commit | 编辑权重 revision | 原生额外组件 revision |
|---|---|---|---|
| Qwen2511 | `06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a`（Diffusers） | `6f3ccc0b56e431dc6a0c2b2039706d7d26f22cb9` | 检查点内编码器，无独立 planner |
| Qwen2.1 | `ab96caa944157ca28a4f36b695c3047549f48f98` | `b3179ad355be050328e483a9dfdd9e60cd62adfa` | 检查点内编码器；等价权重 metadata revision `d26bb61231c349cf6b7896fa83353113880e1ba3` |
| FLUX3 | `bfc8889a4497f846416f253a3972a1941ac698b9` | `337337621b8526e120f2275d250242f4a6bedd75` | 无 PUP |
| RePlan | `6c9b12f0c619cc8ca6f50b536b24aff377525f8c` | Qwen2511 同上 | TainU planner `518f82339520058d043c4fbc270481876d8463e4` |
| MIRAGE | `234a31968df307879a55675873a54258d6c0eae4` | Qwen2511 同上 | Qwen3.5-9B `c202236235762e1c871ad0ccb60c8ee5ba337b9a` |
| MICE | `43b289de84dfd184c0ee1b551b0e1bea02f6e92d` | Klein-4B `e7b7dc27f91deacad38e78976d1f2b499d76a294` | 原生 instance attention，无 planner |
| FLUX2 Klein-9B | `50fe5162777813d869182b139e83b10743caef15` | `92196c8e11f7b6cf2b7493e037d8c5345c559216` | 检查点内 Qwen3-8B encoder |

每次联合编辑记录一次 editor API，不把“40 步”直接当真实 transformer forward 数：CFG、MIRAGE 分支等可能增加 forward。RePlan 通常一次 planner API；MIRAGE 按实际 parser/direct/parent/part 调用统计，单列 batch items。复用记录的本轮新增调用为 0，原始成本另存，不重复加总。

生成环境为 Python 3.11.2 / torch 2.8.0+cu128 / transformers 5.19.0 / Diffusers 0.42.0.dev0；Judge 为 Python 3.12.13 / torch 2.13.0+cu129 / vLLM 0.31.0+cu129 / transformers 5.17.0。启动包绑定依赖清单、源码和权重；这些是该次环境快照，不是安装时无限制升级的要求。SDPA、reference kernel、原生分辨率差异与图像路由均须随结果披露。

## 11. 统一 Judge 与两个百分数

所有原生输出先用 LANCZOS 回到源图分辨率，保留 `raw.png` 和 `output.png`。Judge 只看清洁源图、回源输出、canonical ref 指令、GT selector 与既有合法效果契约；不传模型名、setting、实际 no-ref/标记 prompt 或输入形式。所有 setting 使用同一 canonical 任务，不因 no-ref 改宽评分标准。

Judge 是固定 `Qwen3.8-Flash-Next-FP8@236dfdf285828023ca3bcd3f37366c58a3469b13`。8 GPU tensor/expert parallel，batch=16，最多序列长 49152，GPU memory utilization=.85；4 线程预取图像，按模型依次评分。temperature=0、seed=0、max_tokens=12288、reasoning_effort=low。全图最多 1024² 像素、局部视图最多 512²，裁剪 padding 为 selector-box 长边的 .25、最少 12 像素；源/输出 crop 上使用同一 GT 轮廓。

| 指标 | 什么叫通过 | 百分数分母 |
|---|---|---|
| **UnitPass / UP** | 一个编辑目标的 E=4、P≥3、Q≥3 同时成立 | 所有编辑单元的微平均，本轮每行 72 个 |
| **JointPass / JP** | 同一图所有 unit 通过，且 global_P≥3、global_Q≥3 | 源图平均，本轮每行 20 张 |

E 是目标编辑完成度，P 是应保留内容的保持，Q 是视觉质量，均为 0–4 分。这两个百分数是通过率，不是两个模型的分数，也不是 E/P/Q 平均分。单个目标失败就会使该图 JP 失败，即使其他目标通过。

95% CI 使用 **源图为 cluster 的 paired bootstrap**：所有模型/setting 共用重采样索引，10,000 次、seed=20261027，取 2.5% / 97.5% 分位数。每次重新计算 UP 的单元分母，不能把 72 个相关单元当独立图抽样。K 桶在各桶内按图抽样；K=5 仅两图，区间只描述这个小 dev 样本。

设 `M` 分别取 UP、JP，`m∈{point,box,mask}`：

| 派生指标 | 定义 |
|---|---|
| 语言依赖度 `Δ_lang(m)` | `M(S2-m) − M(S3-m)` |
| 区域增益 `G_region(m)` | `M(S2-m) − M(S1)` |
| 形式鲁棒性 `R_mod` | `min_m M(S3-m) / max_m M(S3-m)`；最大值为 0 时 N/A |
| 混合代价 `C_mix` | `mean_m M(S3-m) − M(S4-noref)` |

每种口径都给 paired CI、实际分母与有效 bootstrap 次数。比较缺任一完整行时不换子集。差值是系统表现描述，可能同时包含原生缩放、规划、global/local attention 等差异，不能一概解释成单因素因果结论。

实现：[fairness_dev_judge.py](../../../../../src/samtok_benchmark/ifbench/fairness_dev_judge.py)、[fairness_dev_report.py](../../../../../src/samtok_benchmark/ifbench/fairness_dev_report.py)；沿用历史 canonical Judge 源码和 rubric，不改评分阈值。

## 12. 缓存、失败和进度如何解释

| 状态 | 处理与报告 |
|---|---|
| 精确生成缓存 | 完整请求、权重、原生参数、seed、资产SHA及父运行证据一致才复用；v2.1计划复用1116条终态（含1条原生失败），其余284条新生成 |
| 精确 Judge 缓存 | canonical 指令/GT、输出 SHA 和 Judge 配置全相同时复用；不是按模型或候选名称直接搬分 |
| 原生规划/生成失败 | 保存原异常与调用记录，留在完整分母并记编辑失败；不重采样、不改 N/A、不退回 S1/裸骨干 |
| Judge 格式或运行失败 | 保存原回答/异常，记缺分；不能补 0、不能当编辑失败，相关完整行及派生量保持不可用 |
| 无歧义解析恢复 | 只恢复已有原回答的确定结构/分数字段，不使用思考段猜数，不新增模型调用 |
| started/admitted 无终态 | 可能已经采样，不自动重试；保留现场供核对 |
| 协议 N/A | 如实显示并单列；不能事后按质量决定 N/A，也不能部分删样本改变分母 |

旧 13 键一次性补评授权不适用于新 dev20 键。已完成的旧结果、失败、候选与耗时全部保留；主表 70 行之外的 21 条 S2 discard 补充行只是对应 S1 结果别名，不新增出图或 Judge 调用。

逐模型 8 卡分片生成；RePlan/MIRAGE 的 planner 阶段完成后才加载 editor，避免同时驻留。所有生成退出后，8 卡统一 Judge 按模型完成一组再进入下一组。只有真实写入终态结果才算完成；加载/缓存核验、生成进度和 Judge 进度分开报告。资源 ETA 只能来自实测吞吐。

## 13. 可复现入口、图例与尚未完成的交付

前台启动命令：

```bash
bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v21-dev20-20261030/start.sh
```

包根的`selection.json`、`plan.json`、`requests/`保存同一名单、新配置与最终请求；`READY.json`绑定提交和文件SHA。旧父计划`2c80d958eaa663f96ef89eb89fd430f0eefa021347a39634cb2048dfabb8e3a8`及结果保持不变。新包通过`parent_run`、逐请求cache receipt和原始调用/trace追溯精确复用；不能把旧digest称为新版。运行包固定源码，后续Git更新不会热更新该包。

`results/` 中保留逐请求最终 prompt、原生 response/框、真实输入图及 MICE 绑定网格、原尺寸输出、回源输出、SHA、调用次数、时间与显存。完成后的 `results/report/REPORT.md` 直接插入实际输入/输出图片，列出每模型每 setting 的 UP/JP、CI、失败/缺分及证据。仓库不复制实验图片；在有共享挂载的机器上打开该 Markdown 及相邻图片即可查看。前置两图完整图册位于 `/tmp/ifbench/fairness_v2_20261030/ALL_MODELS_ALL_SETTINGS_GALLERY.md`，不可把它称为本轮新结果。

标记残留的独立人工抽检、双人 Cohen κ、GT selector paste-back 诊断，以及正式每模型 × setting 随机十例抽检仍需按后续计划完成。paste-back 可能擦掉合法新增内容，所以**只称诊断，不称上界**，也不替换主结果。此前固定两例目视观察不是总体残留率。

原消融逐项状态见[执行协议第 7 节](PROTOCOL.fairness-v2.dev20.md#7-后续交付与原消融清单的状态)。当前不额外启动 †SAM / ‡外部定位 / §caption 增强行；已有 PE/PUP 只保留历史系统结果。所有开发材料继续放临时目录，最终确认并冻结的正式结果才进入 `experiments2/IF-Bench/`。
