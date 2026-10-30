# IF\-Bench 分级评测协议与待评测模型输入方案（代码核对版）

**本文内容：**（1）IF\-Bench 的分级评测怎么做：S1–S5 五个 setting、指标、公平性协议；（2）每个待评测模型在每个 setting 下怎么输入最合适。

**核对说明：**所有接口细节均已对照官方 repo 与 diffusers 源码逐个核对（核对日期 2026\-10\-26），每个模型小节下方附有对应的代码链接和 commit 号。

**三条原则：**

- **原生优先：**模型有原生区域接口时用原生接口（FLUX\.3 的 bbox，RePlan、MIRAGE 的框，MICE、MaskFlow 的 mask）；没有原生接口时，才用可视化标记适配。

- **信息等量：**同一个 setting 下，所有模型拿到相同的区域信息。只允许确定性转换（mask → 外接框，box → 矩形 mask，point → 小框）。引入外部分割器的结果标 †，引入外部规划器或定位器的结果标 ‡，这类结果只作为补充行。

- **适配冻结：**每个模型的候选输入方式在 dev split 上只选一次，选定后冻结并用于 test，所选方案在论文中公开。

Benchmark 原始方案：[IF\-Bench 方案（V2\.6\.0）](https://<company-lark-sg-domain-a9ab3d9b>/docx/RvBqdZlBSovoT7xmKbMltVcSg7g)

---

# 1\. Benchmark 基本信息

- **数据规模：**1,084 张 SA\-1B 图像、3,872 个编辑单元，每张图 2–5 个单元。

- **操作类型：**add / replace / remove / attribute。

- **指令：**每个单元同时有 ref 版本（带指代表达，如 "the leftmost cup"）和 no\-ref 版本（指代替换为 "the selected region"）。

- **区域：**none / point / box / mask，其中 point 和 box 由 GT mask 确定性导出。

- **Judge：**Qwen3\.8\-Flash\-Next\-FP8；指标为 E / P / Q、UnitPass、JointPass。

---

# 2\. 分级评测设计（S1–S5）

## 2\.1 两条轴与五个 setting

评测沿两条轴拆分：**指代轴**（ref / no\-ref）和**区域轴**（none / point / box / mask）。所有 setting 共享同一批编辑目标、同一份 GT mask 和同一个 Judge，只改变"模型看到的输入形式"，因此 setting 之间可以做配对比较（paired bootstrap）。

|Setting|指令|区域|测什么|
|---|---|---|---|
|**S1 Text**|全部 ref|none|纯语言指代与多目标编辑能力，所有模型都能原生运行|
|**S2 Region\+Text**|全部 ref|所有单元统一用一种 m ∈ \{point, box, mask\}|语言和区域同时提供（信息冗余）时，区域带来的增益|
|**S3 Region\-only**|全部 no\-ref|所有单元统一用一种 m|只能靠区域定位，测模型是否真正读取了区域|
|**S4 Mixed\-Region**|分两个子档：全部 ref / 全部 no\-ref|每个单元随机取 point / box / mask|同一请求中混用多种区域形式时的鲁棒性|
|**S5 Full\-Mix**|逐单元 ref / no\-ref 混合|none / point / box / mask 混合；无区域的单元一定带 ref|V2\.6\.0 的完整交互场景|

**报告建议：**主表报 **S1、S3\-mask、S3\-point、S5**；S2 的三种形式、S3\-box 和 S4 放附录。S4 / S5 的随机分配用固定 seed 生成一次，所有模型共用同一份分配表。

## 2\.2 指标

基本口径沿用 V2\.6\.0：E（4/4）、P / Q（≥3/4）、global\_P / Q、UnitPass（UP）和 JointPass（JP）。在此基础上增加四个派生指标，m 表示区域形式：

|指标|定义|含义|
|---|---|---|
|语言依赖度|$\Delta_{lang}^{m}=UP_{S2\text{-}m}-UP_{S3\text{-}m}$|去掉语言指代后的掉点；越小，说明模型越能只靠区域完成定位|
|区域增益|$G_{region}^{m}=UP_{S2\text{-}m}-UP_{S1}$|在语言之外再给区域带来的提升|
|形式鲁棒性|$R_{mod}=\min_m UP_{S3\text{-}m}/\max_m UP_{S3\text{-}m}$|point / box / mask 三种形式之间的一致性|
|混合代价|$C_{mix}=\overline{UP}_{S3}-UP_{S4\text{-}noref}$|同一请求混用多种区域形式带来的额外损失|

四个派生指标同样按 JointPass 口径各算一份。另按目标数 K=2…5 分桶报告 JP 曲线，观察目标数增加后的性能变化。

## 2\.3 评测流程

---

# 3\. 公平性协议

**数据层**

- 所有 setting 共享同一批目标和 GT mask，用 paired bootstrap 给出置信区间

- ref 指令做唯一性检查，排除仍有歧义的指代

**输入层**

- 同一 setting 下所有模型拿到相同的区域信息

- 确定性转换（mask ↔ box、point → 小框）不加标记

- † 表示借助了外部分割器（point → SAM mask）

- ‡ 表示借助了外部规划器或定位器（如 S1 下用 grounding 模型给 MICE / MaskFlow 产生区域）

- § 表示指令被改写成描述式 caption（inpainting 类需要）

**适配层**

- 每个模型的输入方式在 dev split 上选定，选定后在 test 上冻结

- 所有模型的候选数和调参预算相同；每个 case 只采样一次，seed 固定

- 超参数取官方默认值或 model card 推荐值，偏离默认值时写明

**评测层**

- 所有 setting 使用同一个 Judge，始终输入 canonical ref 指令和 GT mask，Judge 不感知模型的输入形式

- 使用可视化标记的模型，报告标记残留率和 paste\-back 上界（非目标区域回贴原图后重新打分）

- 抽样做人工一致性检验（κ）

---

# 4\. 通用输入规范

## 4\.1 多目标指令的序列化

- **单次推理的模型：**K 条子指令按编号写进同一个 prompt，所有模型使用同一套英文模板。

- **只支持单区域、需要多次推理的模型：**每次推理只处理一个单元，按 unit ID 顺序执行，第 k 次的输入是第 k−1 次的输出。附录报告随机顺序带来的方差。

- ref 子指令直接使用 benchmark 的 canonical ref 指令；no\-ref 子指令使用 benchmark 自带的 "the selected region" 版本，不另行改写。

```plaintext
Apply all of the following edits to the image. Keep everything else unchanged.
1. Change the leftmost cup to blue.
2. Remove the dog lying on the sofa.
3. Add a red umbrella next to the bench.
```

## 4\.2 可视化标记规范（用于没有原生区域接口的模型）

|区域形式|绘制方式|理由|
|---|---|---|
|mask|沿 mask 外轮廓描边（线宽约为短边的 0\.4%），**不填充**|填充会改变目标的视觉颜色，干扰 attribute 类编辑；描边保留了形状信息，与 mask 的信息量一致|
|box|矩形描边|与 box 的信息量一致|
|point|实心圆点（半径约为短边的 1%）加白色外环|只给位置、不给范围，与 point 的信息量一致；不扩展成 mask|
|多目标绑定|每个单元一种颜色，按红、蓝、绿、黄、品红的固定顺序分配，并加数字标签；标签放在区域外侧，避免遮挡目标|prompt 用"颜色 \+ 编号"引用对应区域|
|文字说明|**不画在图上**，子指令只写在 prompt 中|多目标时画在图上的文字容易拥挤、遮挡目标；所有 baseline 都有文本通道，用 prompt 更自然|

```plaintext
# 双图前缀（多图模型）
Image 1 is the photo to edit. Image 2 is a copy of Image 1 with numbered colored marks
that indicate the target regions. Edit Image 1 only. The output must not contain any marks.

# 单图前缀（单图模型，输入为画了标记的原图 A）
The image contains numbered colored marks that indicate the target regions.
Apply the edits below and remove all marks in the output.

# S2（ref）
1. [red mark #1] Change the leftmost cup to blue.
# S3（no-ref）
1. [red mark #1] Change the selected region to blue.
```

## 4\.3 区域文本化（坐标，作为候选）

- 只用于编码器是 VLM 的模型，例如 Qwen\-Image\-Edit\-2511、Qwen\-Image\-2\.1、LongCat、Step1X、OmniGen2、BAGEL。FLUX\.2 klein 的编码器是纯文本 Qwen3，不使用这种方式。

- box 写成 \[x1, y1, x2, y2\]，坐标采用该模型编码器的原生约定（绝对像素或 0–1000 归一化，由 dev split 决定）；point 写成 \(x, y\)；mask 只能写外接框，会丢失形状信息。

- 只作为 dev split 上的候选，不作为默认方式。

## 4\.4 区域形式转换与标记

|转换|使用范围|标记|
|---|---|---|
|mask → 外接框|只接受框的接口|无|
|box → 矩形 mask|只接受 mask 的接口|无|
|point → 以点为中心的小框（边长为短边的 5%），需要时再栅格化成 mask|只接受框或 mask 的接口；不引入任何外部信息|无|
|point → SAM mask（统一使用 SAM2\-L、单个正样本点、取最高分 mask）|只作补充行|†|
|无区域单元 → 外部 grounder 给出框或 mask（统一使用同一个开放词表检测 \+ 分割模型）|只用于自身没有规划器的方法|‡|
|指令 → 描述式 caption（inpainting 类需要）|优先用规则模板；如用 LLM 改写，只改写一次、缓存后所有模型共用|§|

## 4\.5 候选方式的选择与冻结

- **dev split：**按图像从 IF\-Bench 中随机抽取约 10%（约 100 张），与 test 不重叠，以 JointPass 作为选择指标。

- **候选数量：**每个模型最多 4 种候选（见第 6–8 节各模型表格），所有模型的调参预算相同。

- **S2 的回退：**可视化标记对没有针对标记训练过的模型可能是干扰，若不允许回退，baseline 可能被低估。因此 S2 的候选里包含"丢弃区域"，即直接使用 S1 的输入；如果某个模型选中了这一项，在结果表中注明。S3 和 S4\-noref 不允许丢弃区域。

- **超参数：**采用官方默认值或 model card 推荐值；每个 case 只采样一次，seed 固定；输出统一 resize 回源图分辨率后再送入 Judge。

- **附加组件：**prompt 改写器（Qwen\-Image\-2\.1 的 rewriter、FLUX\.3 的 PUP）在主表中关闭，附录报告开启后的结果。Step1X 的 reflection、HunyuanImage 的 think\_recaption 属于模型内置流程，保持默认，并记录额外的推理调用次数。

## 4\.6 多次推理时的回贴规则

**自带融合，不额外回贴**

- MaskFlow（膨胀 \+ 模糊 \+ Poisson 融合）

- QwenImageEditInpaintPipeline（latent blend）

- BrushNet（blended=True）

**没有融合，每次推理后都要回贴**

- FLUX\.1 Fill、Flux2KleinInpaintPipeline、InstantX Qwen\-Image\-ControlNet\-Inpainting、PowerPaint

- 做法：把（膨胀后的）mask 以外的像素回贴为本次推理的输入，避免误差在多次推理中累积

---

# 5\. 模型分类与区域通道

|类别|模型|区域通道|每个请求的推理次数|
|---|---|---|---|
|纯文本编辑，多图|Qwen\-Image\-Edit\-2511、Qwen\-Image\-2\.1、FLUX\.2 klein\-9B、OmniGen2、HunyuanImage\-3\.0\-Instruct|原图 \+ 标记图|1|
|纯文本编辑，单图|Step1X\-Edit v1\.2、LongCat\-Image\-Edit、BAGEL、HiDream\-O1\-Image|标记画在原图上|1|
|原生框|FLUX\.3 Klein|bbox JSON|1|
|框 \+ 区域注意力 / 多分支|RePlan、MIRAGE、GoT|oracle 框|1|
|多实例 mask|MICE|K 个 mask 或 K 个框|1|
|单 mask 编辑 / inpainting|MaskFlow、QwenImageEditInpaint、Flux2KleinInpaint、FLUX\.1 Fill、BrushNet、PowerPaint、InstantX ControlNet\-Inpainting、BrushEdit|单个 mask|K|
|隐式定位|TAL|无|K（只跑 S1）|

---

# 6\. 逐模型输入方案：纯文本编辑模型

记号：I 为原图；A 为画了标记的原图；"默认"指 dev split 选择之前的首选方式；"候选"指参与 dev split 选择的其他方式。

## 6\.1 Qwen\-Image\-Edit\-2511

**代码核对：**[HF](https://huggingface.co/Qwen/Qwen-Image-Edit-2511) ｜ [pipeline\_qwenimage\_edit\_plus\.py](https://github.com/huggingface/diffusers/blob/main/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py)

**接口：**`QwenImageEditPlusPipeline(image=[...], prompt, true_cfg_scale=4.0, num_inference_steps=40)`，多图时自动拼接 "Picture \{\}:" 模板；代码中没有图片数量上限。

|Setting|默认输入|候选 / 说明|
|---|---|---|
|S1|image=\[I\]，prompt 为 4\.1 节的编号模板|—|
|S2|image=\[I, A\]（Picture 1 为原图，Picture 2 为标记图）\+ 双图前缀 \+ ref 子指令|候选：单图 A；I \+ 坐标文本；丢弃区域|
|S3|同 S2，子指令换成 no\-ref|候选：单图 A；I \+ 坐标文本|
|S4|点、框、轮廓按各单元的形式画在同一张 A 上，绑定方式同 S2 / S3|沿用 S2 / S3 选出的方式|
|S5|无区域的单元不画标记，在 prompt 中只写 ref；有区域的单元按其形式画标记|同上|

## 6\.2 Qwen\-Image\-2\.1

**代码核对：**commit `ab96caa` ｜ [GitHub](https://github.com/QwenLM/Qwen-Image-2.1) ｜ [HF](https://huggingface.co/Qwen/Qwen-Image-2.1) ｜ [diffusers pipeline\_qwenimage21\.py](https://github.com/huggingface/diffusers/blob/main/src/diffusers/pipelines/qwenimage21/pipeline_qwenimage21.py) ｜ [DiffSynth qwen\_image\_21\.py](https://github.com/modelscope/DiffSynth-Studio/blob/main/diffsynth/pipelines/qwen_image_21.py)

**接口：**`__call__(prompt, image, true_cfg_scale=1.0, num_inference_steps=40, output_resolution=1024)`。README 称支持圈画、涂画等标注，以及单独的 mask，但仓库中没有官方示例。

|Setting|默认输入|候选 / 说明|
|---|---|---|
|S1|image=\[I\]，关闭 prompt rewrite|附录报告开启 rewrite 的结果|
|S2|image=\[I, A\] \+ ref 子指令|候选：单图 A（对应 README 中"在图上圈画"的用法）；\[I, M\_vis\]（黑底彩色区域图，对应 README 中"单独 mask"的用法）；丢弃区域|
|S3|image=\[I, A\] \+ no\-ref 子指令|候选：单图 A；\[I, M\_vis\]|
|S4 / S5|同 6\.1 的处理方式|M\_vis 用相同的颜色编号|

## 6\.3 FLUX\.2 klein\-9B

**代码核对：**[GitHub](https://github.com/black-forest-labs/flux2) ｜ [text\_encoder\.py](https://github.com/black-forest-labs/flux2/blob/main/src/flux2/text_encoder.py) ｜ [pipeline\_flux2\_klein\.py](https://github.com/huggingface/diffusers/blob/main/src/diffusers/pipelines/flux2/pipeline_flux2_klein.py) ｜ [pipeline\_flux2\_klein\_inpaint\.py](https://github.com/huggingface/diffusers/blob/main/src/diffusers/pipelines/flux2/pipeline_flux2_klein_inpaint.py)

**接口：**`Flux2KleinPipeline(image=[...], prompt, guidance_scale=4.0)`。编码器是纯文本的 Qwen3，模型只能通过参考图"看到"标记。

|Setting|默认输入|候选 / 说明|
|---|---|---|
|S1|image=\[I\]|—|
|S2 / S3|image=\[I, A\] \+ 双图前缀 \+ ref / no\-ref 子指令|候选：单图 A；S2 可丢弃区域。不用坐标文本（编码器没有视觉能力）|
|S4 / S5|同 6\.1|diffusers 中还有 `Flux2KleinInpaintPipeline`，可作为附录中的单 mask K 次推理 baseline|

## 6\.4 OmniGen2 / HunyuanImage\-3\.0\-Instruct（多图，附录）

**代码核对：**[OmniGen2 GitHub](https://github.com/VectorSpaceLab/OmniGen2) ｜ [pipeline\_omnigen2\.py](https://github.com/VectorSpaceLab/OmniGen2/blob/main/omnigen2/pipelines/omnigen2/pipeline_omnigen2.py) ｜ [OmniGen2 HF](https://huggingface.co/OmniGen2/OmniGen2) ｜ [HunyuanImage\-3\.0 GitHub](https://github.com/Tencent-Hunyuan/HunyuanImage-3.0) ｜ [run\_image\_gen\.py](https://github.com/Tencent-Hunyuan/HunyuanImage-3.0/blob/main/run_image_gen.py) ｜ [HF Instruct](https://huggingface.co/tencent/HunyuanImage-3.0-Instruct)

|模型|S2–S5 默认输入|说明|
|---|---|---|
|OmniGen2|`input_images=[I, A]`，prompt 中用 "the first image / the second image" 指代两张图|代码默认 text\_guidance 4\.0、image\_guidance 1\.0；S1 时 input\_images=\[I\]|
|HunyuanImage\-3\.0\-Instruct|\[I, A\]（README 称最多 3 张图）|`bot_task="think_recaption"` 是模型内置推理，保持默认；需要至少 8×80GB 显存|

## 6\.5 单图模型：Step1X\-Edit v1\.2 / LongCat\-Image\-Edit / BAGEL / HiDream\-O1\-Image

**代码核对：**[Step1X GitHub](https://github.com/stepfun-ai/Step1X-Edit) ｜ [Step1X v1\.2 HF](https://huggingface.co/stepfun-ai/Step1X-Edit-v1p2) ｜ [pipeline\_step1x\_edit\_v1p2\.py](https://github.com/Peyton-Chen/diffusers/blob/step1xedit_v1p2/src/diffusers/pipelines/step1x_edit/pipeline_step1x_edit_v1p2.py) ｜ [LongCat GitHub](https://github.com/meituan-longcat/LongCat-Image) ｜ [LongCat diffusers pipeline](https://github.com/huggingface/diffusers/blob/main/src/diffusers/pipelines/longcat_image/pipeline_longcat_image_edit.py) ｜ [BAGEL GitHub](https://github.com/ByteDance-Seed/Bagel) ｜ [BAGEL inferencer\.py](https://github.com/ByteDance-Seed/Bagel/blob/main/inferencer.py) ｜ [HiDream\-O1 GitHub](https://github.com/HiDream-ai/HiDream-O1-Image) ｜ [HiDream inference\.py](https://github.com/HiDream-ai/HiDream-O1-Image/blob/main/inference.py) ｜ [HiDream pipeline\.py](https://github.com/HiDream-ai/HiDream-O1-Image/blob/main/models/pipeline.py)

|模型|S1|S2–S5 默认输入|候选 / 说明|
|---|---|---|---|
|Step1X\-Edit v1\.2|I \+ 编号模板|A \+ 单图前缀|候选：I \+ 坐标文本；S2 可丢弃区域。reflection 默认开启（max\_try\_cnt=3），保持默认并记录额外调用次数；thinking 关闭|
|LongCat\-Image\-Edit|I|A \+ 单图前缀|候选同上；50 步，guidance 4\.5|
|BAGEL|I|A \+ 单图前缀|候选：通过 `interleave_inference` 输入 \[I, A\]（官方没有多图编辑示例）。think 开关在所有 setting 下保持一致|
|HiDream\-O1\-Image|I|A（编辑模式要求恰好 1 张参考图）|`--layout_bboxes` 不是官方编辑用途，不用于主结果|

---

# 7\. 逐模型输入方案：原生区域方法

## 7\.1 FLUX\.3 Klein（原生 bbox）

**代码核对：**commit `bfc8889` ｜ [GitHub](https://github.com/black-forest-labs/flux-3-image-klein) ｜ [bbox\.py](https://github.com/black-forest-labs/flux-3-image-klein/blob/main/src/flux3/bbox.py) ｜ [generate\.py](https://github.com/black-forest-labs/flux-3-image-klein/blob/main/src/flux3/generate.py) ｜ [pup\_prompts\.json](https://github.com/black-forest-labs/flux-3-image-klein/blob/main/src/flux3/pup_prompts.json) ｜ [HF](https://huggingface.co/black-forest-labs/flux-3-image-klein) ｜ [diffusers 文档](https://github.com/huggingface/diffusers/blob/main/docs/source/en/api/pipelines/flux3.md)

**接口：**`generate.py` 把 `json.dumps(bbox.to_canvas(boxes))` 拼接到 prompt 后面。每一行的格式为 `{"id","from","src_bbox","tgt_bbox","desc"}`；用户框坐标为 **\[y\_min, x\_min, y\_max, x\_max\]，归一化到 0–1，y 在前**；tgt\_bbox=null 表示删除；MAX\_REFERENCES=10。主表关闭 PUP（`--no-pup`）。

|Setting|默认输入|候选 / 说明|
|---|---|---|
|S1|不写 bbox 行，prompt 为编号模板|—|
|S2|每个单元写一行：src\_bbox = tgt\_bbox = 区域框，desc = ref 子指令。remove 时 tgt\_bbox=null；add 时 src\_bbox 的填法需在 dev 上对照 pup\_prompts\.json 中 i2i\_bbox 的示例确认。mask 转外接框，point 转小框|候选：额外输入 A 作为第二张参考图（point / mask 时可补回点或形状信息）；丢弃区域|
|S3|同 S2，desc 换成 no\-ref 子指令|候选：额外输入 A|
|S4|所有单元都转成框后写成 bbox 行|—|
|S5|无区域的单元不写行，只写在 prompt 文本中；其余单元同 S2 / S3|—|

```python
rows = [
  {"id": 1, "from": 0, "src_bbox": [0.41, 0.08, 0.63, 0.22], "tgt_bbox": [0.41, 0.08, 0.63, 0.22],
   "desc": "Change the leftmost cup to blue."},
  {"id": 2, "from": 0, "src_bbox": [0.55, 0.50, 0.90, 0.85], "tgt_bbox": None,   # remove
   "desc": "Remove the dog lying on the sofa."},
]
```

## 7\.2 RePlan（骨干 Qwen\-Image\-Edit\-2511）

**代码核对：**commit `6c9b12f` ｜ [arXiv](https://arxiv.org/abs/2512.16864) ｜ [GitHub](https://github.com/JIA-Lab-research/RePlan) ｜ [replan\.py](https://github.com/JIA-Lab-research/RePlan/blob/main/replan/pipelines/replan.py) ｜ [run\_replan\.py](https://github.com/JIA-Lab-research/RePlan/blob/main/replan/inference/run_replan.py) ｜ [app\.py](https://github.com/JIA-Lab-research/RePlan/blob/main/replan/inference/app.py) ｜ [规划器 HF](https://huggingface.co/TainU/RePlan-Qwen2.5-VL-7B)

**接口：**规划器 TainU/RePlan\-Qwen2\.5\-VL\-7B 输出 region JSON；编辑器**只读 bbox\_2d 和 hint**，不使用 point\_2d。设置 `init_vlm=False` 后，可以直接注入 response（像素坐标）。Qwen 骨干下 expand\_value=0\.0、attention\_switch\_step=0\.5，全表保持一致。

|Setting|默认输入|说明|
|---|---|---|
|S1|完整流程：规划器 → 编辑器|规划器是方法自身的组件，不标 ‡|
|S2|box / mask：跳过规划器，注入 oracle 框（mask 用外接框），hint = ref 子指令。point：把点坐标写进给规划器的指令（"the object at point \(x, y\)"），由规划器产出框|point 走的是方法自带的规划器，不标记；补充行：SAM 点 → mask → 框，标 †|
|S3|同 S2，hint = no\-ref 子指令|—|
|S4|全部转成框；point 单元的处理同 S2|—|
|S5|只对无区域的单元运行规划器，输出的框与其余单元的 oracle 框合并成一个 response，单次完成编辑|全局描述 G = 所有子指令拼接|

```python
pipe = RePlanPipeline(..., init_vlm=False)
resp = ('&lt;gen_image&gt;' + G + '&lt;/gen_image&gt;&lt;region&gt;'
        '[{"bbox_2d":[x1,y1,x2,y2],"hint":"Change the leftmost cup to blue."}, ...]'
        '&lt;/region&gt;')
out = pipe.region_edit_with_attention(image, "", response=resp)
```

## 7\.3 MIRAGE（骨干 Qwen\-Image\-Edit\-2511；附录补 FLUX\.2\-klein\-base\-9B）

**代码核对：**commit `234a319` ｜ [arXiv](https://arxiv.org/abs/2604.05180) ｜ [GitHub](https://github.com/ZiqianLiu666/MIRAGE) ｜ [crop\_image\.py](https://github.com/ZiqianLiu666/MIRAGE/blob/main/crop_image.py) ｜ [inference\.py](https://github.com/ZiqianLiu666/MIRAGE/blob/main/inference.py) ｜ [mirage/flux2\.py](https://github.com/ZiqianLiu666/MIRAGE/blob/main/mirage/flux2.py)

**接口：**`crop_image.py` 默认用 Qwen3\.5\-9B 生成 jsonl，再由 `inference.py --instruction-jsonl` 执行多分支并行去噪。参数：`--padding 10`，`--patch-ratio 0.4`（多指令场景的默认值）。

|Setting|默认输入|说明|
|---|---|---|
|S1|完整流程：crop\_image\.py（VLM）→ inference|VLM 是方法自身的组件|
|S2|直接写 jsonl：bbox = 区域外接框（像素坐标），refer\_object = ref 中的指代表达（若单元没有单独的指代字段，就用整条 ref 子指令），new\_instruction = ref 子指令。point：交给 crop\_image\.py 的 VLM，在指令中附上点坐标|补充行：SAM 点 → mask → 框，标 †|
|S3|refer\_object = "the selected region"，new\_instruction = no\-ref 子指令|Qwen 骨干会把 refer\_object 写进 prompt 的 "Target: \.\.\."；裁剪本身已经完成定位|
|S4 / S5|全部转成框；无区域的单元交给 VLM 定位|重叠区域按编辑强度处理（方法自带逻辑）|

```json
{"original_image":"sa_xxx.jpg","image":"crop_01.png","bbox":{"x1":120,"y1":80,"x2":260,"y2":210},"refer_object":"the leftmost cup","new_instruction":"Change the leftmost cup to blue."}
```

## 7\.4 MICE（FLUX\.2\-klein\-4B，仓库中唯一的骨干）

**代码核对：**commit `43b289d` ｜ [arXiv](https://arxiv.org/abs/2606.31278) ｜ [GitHub](https://github.com/Blowing-Up-Groundhogs/mice) ｜ [infer\_flux2\_mice\.py](https://github.com/Blowing-Up-Groundhogs/mice/blob/main/infer_flux2_mice.py) ｜ [mice\_dataset\.py](https://github.com/Blowing-Up-Groundhogs/mice/blob/main/mice_dataset.py) ｜ [attention processor](https://github.com/Blowing-Up-Groundhogs/mice/blob/main/flux2/attention/attention_processor_APITASM_kernel_nonlap.py)

**接口：**prompt = `BREAKFLAG.join([global, inst_1, ..., inst_K])`；区域通过 `instance_masks_yx` 或 `instance_bboxes_xyxy_normalized` 输入，**两者只能选一个，不能混用**；默认 4 步。仓库没有 LICENSE。

|Setting|默认输入|说明|
|---|---|---|
|S1|N/A（方法本身没有定位能力）|补充行：外部 grounder 生成 mask，标 ‡|
|S2|mask → instance\_masks\_yx；box → instance\_bboxes；point → 小框；inst\_i = ref 子指令，global = "Keep everything else unchanged\."|补充行：point 经 SAM 转 mask，标 †|
|S3|同 S2，inst\_i 换成 no\-ref 子指令|—|
|S4|**统一转成 mask**：box 栅格化成矩形，point 用小框栅格化|因为两种区域输入不能混用|
|S5|有区域的单元同 S4；无区域的单元标 N/A，或用外部 grounder（‡）|主表只报不带 ‡ 的部分时，在表中注明|

## 7\.5 MaskFlow（Qwen\-Image\-Edit\-2511 \+ latest 权重）

**代码核对：**commit `3125f1e` ｜ [arXiv](https://arxiv.org/abs/2608.06929) ｜ [GitHub](https://github.com/ReyChiaro/MaskFlow) ｜ [inference\.py](https://github.com/ReyChiaro/MaskFlow/blob/main/inference.py) ｜ [configs/inference\.yaml](https://github.com/ReyChiaro/MaskFlow/blob/main/configs/inference.yaml) ｜ [HF](https://huggingface.co/ReyChiaro/MaskFlow)

**接口：**Hydra 参数 `input.source= input.mask= input.prompt=`，每次只处理一个 mask，自带膨胀、模糊（kernel 25）和 Poisson 融合。配置文件默认是 maskflow\-S，README 推荐 latest，主表使用 latest 并在文中注明。

|Setting|默认输入|说明|
|---|---|---|
|S1|N/A|补充行：外部 grounder \+ SAM，标 ‡|
|S2|推理 K 次；mask 直接输入，box 转矩形 mask，point 转小框 mask；prompt = ref 子指令|补充行：point 经 SAM 转 mask，标 †|
|S3|推理 K 次；把 no\-ref 子指令中的 "the selected region" 替换成 MaskFlow 训练时使用的 "\[MASK\_AREA\]" 写法（以 repo 示例为准）|这一替换属于固定规则，所有单元统一执行|
|S4 / S5|推理 K 次；无区域的单元标 N/A，或用外部 grounder（‡）|不需要额外回贴|

---

# 8\. 逐模型输入方案：单 mask inpainting 类及其他（附录）

这类模型每次只处理一个单元，共推理 K 次。S1 一律标 N/A（如用外部定位则标 ‡）。区域转换规则同 4\.4 节：box 栅格化成矩形 mask，point 用小框栅格化，SAM 结果作为补充行（†）。

|模型|prompt 与关键参数|融合 / 回贴|说明|
|---|---|---|---|
|QwenImageEditInpaintPipeline|指令式 prompt（ref / no\-ref 都可以）\+ mask\_image；strength 在 dev 上从 \{0\.6, 0\.8, 1\.0\} 中选|自带 latent blend|可作为主表的可选项，是"指令 \+ mask"最直接的对照|
|Flux2KleinInpaintPipeline|指令 \+ mask\_image，可选 image\_reference；默认 strength 0\.8、guidance 8\.0|每次推理后回贴|—|
|FLUX\.1 Fill|描述式 caption（§），50 步，guidance 30|每次推理后回贴|非商用许可|
|BrushNet|描述式 caption（§）；box 类 mask 使用 random\_mask 权重|blended=True|依赖 fork 版 diffusers|
|PowerPaint|add / replace / attribute 用 P\_obj \+ caption（§）；remove 用 P\_ctxt，不需要 caption|每次推理后回贴|只有 Gradio 入口，需要从 app\.py 中抽出批处理逻辑|
|InstantX Qwen\-Image\-ControlNet\-Inpainting|描述式 prompt（§），true\_cfg 4|每次推理后回贴|—|
|BrushEdit|传入用户 mask 和 target\_prompt 时跳过 VLM，直接用 BrushNet（SD1\.5）|自带|没有批处理脚本，需封装 BrushEdit\_Pipeline|
|GoT|S1 走原生流程；S2 / S3 通过 got\_input 注入框（0–1000 坐标），mask 用外接框，point 用小框|—|输入会被强制成 1024² 方形，需先 pad 再裁回原尺寸|
|TAL|只跑 S1；每条指令单独运行一次，共 K 次|—|不接受用户给的区域，S2–S5 标 N/A|

**代码核对：**

- QwenImageEditInpaintPipeline：[pipeline\_qwenimage\_edit\_inpaint\.py](https://github.com/huggingface/diffusers/blob/main/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py)

- Flux2KleinInpaintPipeline：[pipeline\_flux2\_klein\_inpaint\.py](https://github.com/huggingface/diffusers/blob/main/src/diffusers/pipelines/flux2/pipeline_flux2_klein_inpaint.py)

- FLUX\.1 Fill：[HF](https://huggingface.co/black-forest-labs/FLUX.1-Fill-dev) ｜ [pipeline\_flux\_fill\.py](https://github.com/huggingface/diffusers/blob/main/src/diffusers/pipelines/flux/pipeline_flux_fill.py)

- BrushNet：[GitHub](https://github.com/TencentARC/BrushNet)

- PowerPaint：[GitHub](https://github.com/open-mmlab/PowerPaint) ｜ [app\.py](https://github.com/open-mmlab/PowerPaint/blob/main/app.py) ｜ [HF v2\-1](https://huggingface.co/JunhaoZhuang/PowerPaint-v2-1)

- InstantX Qwen\-Image\-ControlNet\-Inpainting：[HF](https://huggingface.co/InstantX/Qwen-Image-ControlNet-Inpainting) ｜ [pipeline\_qwenimage\_controlnet\_inpaint\.py](https://github.com/huggingface/diffusers/blob/main/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_controlnet_inpaint.py)

- BrushEdit：[GitHub](https://github.com/TencentARC/BrushEdit) ｜ [brushedit\_app\.py](https://github.com/TencentARC/BrushEdit/blob/main/app/src/brushedit_app.py) ｜ [vlm\_pipeline\.py](https://github.com/TencentARC/BrushEdit/blob/main/app/src/vlm_pipeline.py)

- GoT：[arXiv](https://arxiv.org/abs/2503.10639) ｜ [GitHub](https://github.com/rongyaofang/GoT) ｜ [got/models/utils\.py](https://github.com/rongyaofang/GoT/blob/main/got/models/utils.py) ｜ [got\_model\.py](https://github.com/rongyaofang/GoT/blob/main/got/models/got_model.py)

- TAL：[arXiv](https://arxiv.org/abs/2604.20258) ｜ [GitHub](https://github.com/Jessie459/TAL) ｜ [infer\_qwen\.py](https://github.com/Jessie459/TAL/blob/main/infer_qwen.py)

**注意：**caption 式 inpainter 的 prompt 只描述编辑后的状态，指代信息根本不进入输入，所以它们在 S2 和 S3 下的输入完全相同，语言依赖度 Δ\_lang 按构造就约等于 0。论文中需要说明这一点，避免读者误以为这类模型对语言指代"鲁棒"。

---

# 9\. 总览矩阵

|模型|S1|S2|S3|S4|S5|
|---|---|---|---|---|---|
|Qwen\-Image\-Edit\-2511|原生|双图标记 \+ ref|双图标记 \+ no\-ref|混合标记|混合标记 \+ ref 文本|
|Qwen\-Image\-2\.1|原生|双图标记 / M\_vis|同左|混合标记|同左|
|FLUX\.2 klein\-9B|原生|双图标记|双图标记|混合标记|同左|
|Step1X / LongCat / BAGEL / HiDream|原生|单图标记|单图标记|单图混合标记|同左|
|FLUX\.3 Klein|原生|bbox 行|bbox 行|全部转框|bbox 行 \+ 文本|
|RePlan|自带规划|oracle 框；point 交给规划器|同左|全部转框|oracle 框 \+ 规划器补全|
|MIRAGE|自带 VLM|oracle jsonl；point 交给 VLM|同左|全部转框|oracle \+ VLM 补全|
|MICE|N/A（‡）|mask / 框 / 小框|同左|全部转 mask|部分 N/A（‡）|
|MaskFlow / inpainting|N/A（‡）|K × mask|K × mask|K × mask|部分 N/A（‡）|

† 表示补充行使用了 SAM 把点转成 mask；‡ 表示使用了外部 grounder；§ 表示指令被改写成 caption。不带标记的结果才进入主表的直接比较。

---

# 10\. 主表与附录划分

**主表**

- Qwen\-Image\-Edit\-2511

- Qwen\-Image\-2\.1

- FLUX\.3 Klein

- RePlan（Qwen\-2511 骨干）

- MIRAGE（Qwen\-2511 骨干）

- MICE

- MaskFlow

- 可选：FLUX\.2 klein\-9B、QwenImageEditInpaintPipeline

**附录**

- Step1X\-Edit v1\.2、LongCat、BAGEL、OmniGen2、HunyuanImage\-3\.0、HiDream\-O1

- FLUX\.1 Fill、Flux2KleinInpaint、BrushNet、PowerPaint、InstantX ControlNet\-Inpainting、BrushEdit

- GoT、TAL

- 所有 †、‡ 补充行

## 10\.1 输入相关的消融（只针对 baseline）

* [ ] 双图标记 vs 单图标记（Qwen\-2511、Qwen\-Image\-2\.1、FLUX\.2 klein）

* [ ] 可视化标记 vs 坐标文本（编码器为 VLM 的模型）

* [ ] 标记样式：贴合轮廓描边 vs 外扩圆圈；固定颜色 vs 随机颜色

* [ ] 附加组件开关：FLUX\.3 PUP、Qwen\-Image\-2\.1 rewriter、Step1X reflection

* [ ] RePlan / MIRAGE：自带规划器给出的框 vs oracle 框，分离规划误差与编辑误差

* [ ] point：小框 vs SAM mask（†），用于 MICE、MaskFlow、FLUX\.3

* [ ] K 次推理模型：unit 顺序随机化带来的方差

* [ ] 标记残留率与 paste\-back 上界

---

---

# 11\. 许可证与未验证项

**许可证：**

- MICE 和 TAL 的仓库没有 LICENSE。

- FLUX\.1 Fill、FLUX\.2 klein\-9B 和 FLUX\.3 Klein 的权重为非商用许可（FLUX\.3 的代码是 Apache\-2\.0）。

- HunyuanImage\-3\.0 与 BrushEdit 的许可证存在地域限制。

- 以上模型仅用于学术评测，论文中注明许可证即可。

**未验证项（需在 dev split 上确认）：**

- Qwen\-Image\-2\.1 的圈画 / mask 用法只来自 README，仓库中没有官方示例。

- FLUX\.3 Klein 中 add 操作的 src\_bbox 填法，需对照 pup\_prompts\.json 中 i2i\_bbox 的示例确认。

- MaskFlow 的 "\[MASK\_AREA\]" prompt 写法以 repo 示例为准。

- BAGEL 的多图编辑（interleave\_inference）没有官方示例。

---

# 12\. 暂时无法运行、仅在相关工作中引用的方法

|方法|状态|依据|
|---|---|---|
|AdaptEdit（[arXiv](https://arxiv.org/abs/2604.23763)）|未放出权重|原文写明 "We do not release the trained adapter checkpoints"|
|FineEdit（[arXiv](https://arxiv.org/abs/2604.10954)）|没有代码|HF 上的 FineEdit\_Model 是一个无关的 LLM|
|GVCoT（[arXiv](https://arxiv.org/abs/2603.01893)）|只有权重|HF 上的 zjYinnnn/Bagel\_GVCoT 没有推理代码|
|FireEdit / FOCUS / LOCI / FoI / ThinkDrag|没有代码，或代码仍是 TODO|—|

*代码核对日期：2026\-10\-26。commit 号见各模型小节的"代码核对"行，上游仓库更新后需要重新核对。*

