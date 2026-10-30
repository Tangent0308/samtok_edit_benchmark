# IF-Bench 阶段 1：协议核对报告

审计日期：2026-10-27。状态：**供用户确认的修订建议；未授权阶段 2**。没有运行 dev 候选选择、test 生成或 Judge。代码/README/model card/官方示例与 issue 分开核对；接口可传入不等于模型理解了输入，也不等于推荐用法。

本地旧工作区已从 `9e63e4f` 快进到远程 `v2branch` 的 `6521c8a1daef8a87555c93dea1b156bbab7cbc4b`。审计开发工作区为 `/opt/tiger/tanyue/if-bench`，分支 `if-bench-protocol-audit`。不改写历史 release 或旧实验结果。

- [逐方法 × 10 settings 核对矩阵](SETTING_MATRIX_ZH.md)（CSV 同名）。所有单元格均有证据，修正与备选方案见本文对应方法。
- [全局问题清单](GLOBAL_ISSUES_ZH.md)。其中 add 锚点语义、分母一致性、数据隔离与候选冻结是执行前必修项。
- [修订后的完整协议](PROTOCOL.revised.md)与[逐条修订记录](CHANGELOG_ZH.md)。原协议原样留存为 `PROTOCOL.original.md`。
- [来源与版本](SOURCE_INDEX.md)、[运行可行性与最小验证](RUNTIME_ZH.md)。原始源码快照、model card、HTTP 状态、日志在实验根 `sources/`、`checks/`、`smoke/`。

判定：✅协议接口与证据一致；⚠️可实现但须修正接口/默认值/解释/适配；❌原方案不能直接按所述方式运行或不能作为该 setting 的完整结果；❓现有证据不能确认。✅不代表编辑质量通过。运行状态另列，不以缺少本地依赖推断模型不支持。

协议指定的 6 个 commit 均解析成功；截至本次取证，Qwen2.1、FLUX.3、RePlan、MIRAGE、MICE、MaskFlow 的最新 HEAD 与指定 commit 相同，未发现“新版本已经修复、旧 commit 未修复”的差异。其余方法和 Diffusers 已补齐 immutable SHA。issue 检查是每仓库最近更新的至多 100 条（含 PR），不声称穷尽；issue 用户报告不自动视为已证实的缺陷。

## 1. Qwen-Image-Edit-2511

**支持性。** `QwenImageEditPlusPipeline` 接受多参考图；编码器给图像加 `Picture n:`，因此 `[I,A]` 的图像顺序可实现。没有独立 point/box/mask 参数，也没有坐标解析器；把坐标写入普通文本仅是待验证候选。代码未显式限制参考图数量，不应解读为无限图片的官方质量保证；IF-Bench 固定最多两张。S1 编号指令、S2/S3 双图点/框适配无接口冲突；S2/S3-mask 要修复洞和多个连通域的绘制；S4/S5 要冻结选择规则和保留无区域单元。

**默认/推荐。** 函数默认 50 步，2511 model card 示例 40 步、`true_cfg_scale=4`、`guidance_scale=1`、`negative_prompt=" "`；推荐按 model card 明确填写，不能省略负面提示后以为 CFG 一定生效。VLM 条件图约 384²，VAE 参考图约 1024²，因此源图上很小的点和细轮廓经缩放后可能消失。不是输入图像分辨率越大，VLM 看到的区域就越清楚。

**修正选择。** (A，推荐) `[I,A]`，保留 A 单图与显式画布坐标为候选；(B) 单图 A，可能损坏原始颜色且要求模型去标记；(C) 坐标文本，须选定一种约定，不称“原生接口”。S2 丢弃区域单独报 `S2-best-adapted`，不进入区域增益的主配对计算。具体候选效果留到阶段 2 的 dev。

证据：[diffusers:src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py:530](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L530-L551)；[diffusers:src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py:231](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L231-L280)；[Qwen/Qwen-Image-Edit-2511/README.md](https://huggingface.co/Qwen/Qwen-Image-Edit-2511/blob/6f3ccc0b56e431dc6a0c2b2039706d7d26f22cb9/README.md)。

## 2. Qwen-Image-2.1

**支持性。** README 明确宣称至多 10 张参考图及圈画/涂抹/独立 mask；Diffusers 实际接口仍是普通 `image` 列表，没有命名 `mask_image` 通道。`[I,A]` 可以传入；“黑底多色多实例 M_vis”没有被官方材料规定为独立 mask 的确切编码，不能从该宣称推出其多单元绑定已验证。仓库 issue #21 正是在询问局部编辑示例，本次读取未见维护者答案。

**默认/推荐。** 基础权重 `Qwen/Qwen-Image-2.1`：40 步、CFG 1、默认输出面积由 `output_resolution=1024` 控制、保持长宽比。README 展示了更高分辨率，且推荐独立的 PE-I2I 改写器；关改写器是受控 benchmark 选择，不是官方最推荐流程。Turbo（8 步及权重保存的 schedule）与基础权重不是同一行，不能悄悄替换。prompt rewriter 不在 `__call__` 中自动开启，不存在凭空可用的 `rewrite=False` 参数。

**修正选择。** (A，推荐) 双图标记与单图圈画竞争；(B) 在 dev 上验证单个/多实例独立 mask 的模板后，才允许 M_vis 成为候选；(C) 单独报告官方 PE-I2I 开启流程，但它只可看到该 setting 的公共输入，S3 不能读取隐藏 ref 来改写。M_vis-point 必须画点，不能根据隐藏 GT mask 填整块物体。补充许可证为 Qwen Research License。

证据：[qwen21:README.md:141](https://github.com/QwenLM/Qwen-Image-2.1/blob/ab96caa944157ca28a4f36b695c3047549f48f98/README.md#L141-L178)；[diffusers:src/diffusers/pipelines/qwenimage21/pipeline_qwenimage21.py:512](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/qwenimage21/pipeline_qwenimage21.py#L512-L535)；[qwen21:README.md:239](https://github.com/QwenLM/Qwen-Image-2.1/blob/ab96caa944157ca28a4f36b695c3047549f48f98/README.md#L239-L264)；[官方 issue #21](https://github.com/QwenLM/Qwen-Image-2.1/issues/21)。

## 3. FLUX.3 Klein

**明确错误。** 原示例 `id:1, from:0` 经官方 `to_canvas` 得到 `id:"1", from:""`；`id` 不满足后续字母起始约定，`from` 也不是官方来源 token。不是“代码会为你校正”的格式。用 `id:"obj_1"`、`from:"ref_image_0"`，在正文显式引用 `<obj_1>` 和 `<ref_image_0>`。`src_bbox`/`tgt_bbox` 输入为 yxyx、[0,1]；`to_canvas` 才变成 0–1000。该函数会 clip，适配器应先拒绝越界/逆序坐标，不能靠静默 clip 修复。

**add 的结论。** 官方新增物体行是 `from:"target", src_bbox:null, tgt_bbox:输出框`。IF-Bench add 给的是源图锚点，**并没有新增物体输出框**。推荐给锚点本身建 `ref_image_0` 行，正文描述在该锚点上执行原始 add 指令；不要臆造新增物体的 GT 输出框。`desc` 按官方语义是静态外观，动作放正文。S3 可用“selected source anchor/region”这种无语义描述；不可从私有 ref 补对象类别或外观。replace 也不能一律解释成同一物体、同一大小不变，需说明源框/目标框相等是适配限制。

**默认/推荐。** distilled 是 16 步、无 CFG；base 是 50 步、CFG 4。主行明确为 distilled 权重。PUP 默认开启，原协议关闭属于消融；官方 bbox 是经过训练的文本布局格式，不是硬区域 mask 或专门 attention tensor。参考图上限 10。单图路径最高约 4 MP，双图每图约 1 MP，候选比较可能同时改变源图细节；要记录实际参考尺寸及固定输出画布，单独报告这一混杂。

**修正选择。** (A，推荐) 正确的来源/id/正文引用 + add 锚点行；mask/point 可增第二张 A 作为保真候选；(B) 只用双图 A，不强行把锚点当新物体框；(C) 开启 PUP，让官方模块从公共输入规划输出框，另列推荐原生流程。不能用 test Judge 选每例框。S5 不带区域的单元保留全文，不加虚构 bbox。

证据：[flux3:src/flux3/bbox.py:10](https://github.com/black-forest-labs/flux-3-image-klein/blob/bfc8889a4497f846416f253a3972a1941ac698b9/src/flux3/bbox.py#L10-L48)；[flux3:src/flux3/bbox.py:99](https://github.com/black-forest-labs/flux-3-image-klein/blob/bfc8889a4497f846416f253a3972a1941ac698b9/src/flux3/bbox.py#L99-L116)；[flux3:src/flux3/pup_prompts.json:5](https://github.com/black-forest-labs/flux-3-image-klein/blob/bfc8889a4497f846416f253a3972a1941ac698b9/src/flux3/pup_prompts.json#L5-L5)；[flux3:src/flux3/generate.py:30](https://github.com/black-forest-labs/flux-3-image-klein/blob/bfc8889a4497f846416f253a3972a1941ac698b9/src/flux3/generate.py#L30-L81)；[flux3:src/flux3/pipeline.py:19](https://github.com/black-forest-labs/flux-3-image-klein/blob/bfc8889a4497f846416f253a3972a1941ac698b9/src/flux3/pipeline.py#L19-L28)。CPU 检查已真实复现 `from=0` 丢失和数字 ID 识别失败。

## 4. RePlan / Qwen-2511

**支持性。** `init_vlm=False` + 注入 `response` 是代码支持的路径；只消费 `bbox_2d` 与 `hint`，不读 `point_2d`。bbox 为当前输入图像的绝对像素 xyxy。`<gen_image>`/`<region>` 必须为真实尖括号，原示例中的 HTML 实体 `&lt;...&gt;` 被官方 regex 拒绝。方法返回 `(edited_image, edit_folder, results)` 三元组，不能按单一dict取值（[返回语句](https://github.com/JIA-Lab-research/RePlan/blob/6c9b12f0c619cc8ca6f50b536b24aff377525f8c/replan/pipelines/replan.py#L988-L1013)）。区域数量未显式硬编码上限，但 K≤5、prompt 长度及显存仍须验证。

**默认/推荐。** Qwen2511 CLI 自动设 `expand_value=0`、`attention_switch_step=.5`；直接调用方法却默认 `.15` 和 `0`，原代码示例没有传这两个参数，因此与文字规定不一致。必须显式传入。40 步、true CFG 4、guidance 1、负面提示一个空格。内置规划器是 `TainU/RePlan-Qwen2.5-VL-7B`，不是本地同名大小的普通 Qwen2.5-VL。官方 `pyproject.toml` 固定 Transformers 4.52.4，与新模型共用一个环境不稳妥。

**point 与 S5。** “在文本写 the object at point(x,y)”是自定义 prompting，不是官方 point 参数。函数可以接收该字符串，但不能据此保证定位器会正确解释缩放前坐标。S5 按单元分别规划再合并也需要适配代码；原完整流程会改写全局 prompt，因此不得让已知区域单元被重复计划或让隐藏 ref 回流到 no-ref。只有全局公共指令和对应可见区域可用于规划。

**修正选择。** (A，推荐作为可直接复现的受控行) 所有显式 point 用固定小框，与 box/mask 一样注入；(B) 另列 `native-planner` 候选，point 给规划器同样公共输入，并以样例确认引用和坐标，保留推断框与调用日志；(C) SAM† 仅附录。内置规划器不加外部 ‡，但必须标 `planner-active`，不能把这种推断叫确定性转换。S1 原生规划与 S2 oracle 注入之间的 G_region 是系统差值，含“绕过规划器”的影响。

证据：[replan:replan/pipelines/replan.py:640](https://github.com/JIA-Lab-research/RePlan/blob/6c9b12f0c619cc8ca6f50b536b24aff377525f8c/replan/pipelines/replan.py#L640-L660)；[replan:replan/pipelines/replan.py:418](https://github.com/JIA-Lab-research/RePlan/blob/6c9b12f0c619cc8ca6f50b536b24aff377525f8c/replan/pipelines/replan.py#L418-L448)；[replan:replan/pipelines/replan.py:870](https://github.com/JIA-Lab-research/RePlan/blob/6c9b12f0c619cc8ca6f50b536b24aff377525f8c/replan/pipelines/replan.py#L870-L938)；[replan:replan/inference/run_replan.py:183](https://github.com/JIA-Lab-research/RePlan/blob/6c9b12f0c619cc8ca6f50b536b24aff377525f8c/replan/inference/run_replan.py#L183-L192)；[replan:pyproject.toml:10](https://github.com/JIA-Lab-research/RePlan/blob/6c9b12f0c619cc8ca6f50b536b24aff377525f8c/pyproject.toml#L10-L26)。

## 5. MIRAGE / Qwen-2511

**支持性。** 需要两份 JSONL：`--instruction-jsonl` 为 `{"image":...,"editing_instruction":...}`；`--crop-instruction-jsonl` 才是 `original_image/image/bbox/refer_object/new_instruction`。原协议只描述后一种却命名为前者，会报错或取不到全局指令。编辑阶段按 `original_image` 分组，再按区域记录的 `image` 名排序；使用 `crop_01...05` 保持 unit 顺序。区域 image 名是索引标识，实际 crop 在推理时从原图按框重算；不能把它误当第二张外部参考图。

**默认/推荐。** Qwen 40 步、true CFG 4、patch ratio .4、seed 42。`padding=10` 属于前处理 `crop_image.py`；直接写区域 JSONL 会绕过它，必须决定且记录是否对 oracle 框执行同样 padding。Qwen 分支还存在最小 crop、latent 向外取整、context padding/upscale/blend，不能简单称“只读紧框”。框为原图像素 xyxy 字典。VLM 默认 Qwen3.5-9B，存在 parse 与 locate 两阶段，部件可能另做父对象定位，不是固定一次 VLM 调用。

**修正选择。** (A，推荐) 写齐两文件，使用现成 `instruction_spec.ref` 作 S2 的 `refer_object`（3872 个单元均有该字段）；S3 用 `the selected region`，绝不补私有 ref；统一显式 10px padding；point 受控行用小框；(B) 官方 VLM 对公共 point/无区域单元定位作为 `native-planner` 流程，日志记录其不确定性；(C) SAM†。S5 合并是自定义适配，不能未经验证声称是原生完整入口。多分支 denoising 是一个输出轨迹但包含多次子分支网络求值，应报告实际 NFE/耗时。

证据：[mirage:inference.py:23](https://github.com/ZiqianLiu666/MIRAGE/blob/234a31968df307879a55675873a54258d6c0eae4/inference.py#L23-L95)；[mirage:crop_image.py:13](https://github.com/ZiqianLiu666/MIRAGE/blob/234a31968df307879a55675873a54258d6c0eae4/crop_image.py#L13-L69)；[mirage:mirage/vlm.py:44](https://github.com/ZiqianLiu666/MIRAGE/blob/234a31968df307879a55675873a54258d6c0eae4/mirage/vlm.py#L44-L55)；[mirage:mirage/geometry.py:9](https://github.com/ZiqianLiu666/MIRAGE/blob/234a31968df307879a55675873a54258d6c0eae4/mirage/geometry.py#L9-L51)；[mirage:mirage/qwen_image_edit.py:75](https://github.com/ZiqianLiu666/MIRAGE/blob/234a31968df307879a55675873a54258d6c0eae4/mirage/qwen_image_edit.py#L75-L205)。

## 6. MICE / FLUX.2-klein-4B

**支持性。** 准确分隔符是字面量 `$BREAKFLAG$`，不是未定义的 `BREAKFLAG` 常量。`instance_masks_yx` 为二维 float tensor（白/1 编辑），`instance_bboxes_xyxy_normalized` 为 [0,1] xyxy；两个参数必须恰有一个非 None。多单元 mask 数与局部 prompt 数必须相符；batch=1。S4 全部转 mask 是合理适配。数据示例只演示 replace，不能把它当作 add/remove/attribute 已验证。既有 dataset builder 会重写成 `Replace the ... with ...`，必须绕过该重写，保留本任务指令。

**默认/推荐。** 4 步、guidance 1、1024² 面积保持比例并对齐 16；`outer_local_prompts`、`apitasmkernelnonlap`、kernel 11、temperature 3、double blocks [0,5)、single [0,20)、所有 denoising 步应用 binding。源码分别截取 global/local 的前 200 token；不是无限 prompt。global 示例为一个空格，协议改成 Keep... 属于自定义模板，需记录。

**S1/S5 不应过度断言。** None/None 会断言失败，但源码还有 global prompt 通道，空列表与 None 不等价；global-to-image attention 明确存在。故“不支持任何无 mask 输入、只能外部 grounder”过强。本次已实测 `instance_masks_yx=[]`、global中放全部ref、4步成功生成一张双目标case的输出，确认S1退化路径能运行（不代表质量通过）。S5把无区域指令放global、其余保留局部绑定仍需单独验证；不能因S1跑通就认定混合绑定成功。若采用，必须完整K任务评分，不能只报有区域单元的高分。

**修正选择。** (A，推荐当前区域主行) 保持原生多实例输入，S1明确标global-only退化且已做连通性验证，S5混合路径仍待核，不截断任务；(B) 验证 global+区域混合适配，若采纳明确这是扩展用法并冻结；(C) 共用外部 grounder‡ 可补全，但只在附录。未发现仓库 LICENSE（以取证 tree 为界），基础 FLUX.2-4B 的 Apache-2.0 不自动覆盖 MICE 代码。

证据：[mice:flux2/pipeline_flux2_klein.py:779](https://github.com/Blowing-Up-Groundhogs/mice/blob/43b289de84dfd184c0ee1b551b0e1bea02f6e92d/flux2/pipeline_flux2_klein.py#L779-L818)；[mice:flux2/pipeline_flux2_klein.py:210](https://github.com/Blowing-Up-Groundhogs/mice/blob/43b289de84dfd184c0ee1b551b0e1bea02f6e92d/flux2/pipeline_flux2_klein.py#L210-L310)；[mice:mice_dataset.py:12](https://github.com/Blowing-Up-Groundhogs/mice/blob/43b289de84dfd184c0ee1b551b0e1bea02f6e92d/mice_dataset.py#L12-L95)；[mice:flux2/attention/attention_processor_APITASM_kernel_nonlap.py:31](https://github.com/Blowing-Up-Groundhogs/mice/blob/43b289de84dfd184c0ee1b551b0e1bea02f6e92d/flux2/attention/attention_processor_APITASM_kernel_nonlap.py#L31-L93)；[mice:infer_flux2_mice.py:30](https://github.com/Blowing-Up-Groundhogs/mice/blob/43b289de84dfd184c0ee1b551b0e1bea02f6e92d/infer_flux2_mice.py#L30-L80)。

## 7. MaskFlow / Qwen-2511 + latest

**明确错误。** 官方明确要求从数据集 prompt 去掉 `[MASK_AREA]`，换自然指代；原协议却把 `the selected region` 换成该占位符。推荐保留 benchmark no-ref 的 `the selected region`，或用统一、无新增语义的 `the masked region`，绝不能恢复 canonical ref。

**接口/默认。** CLI 的 `input.source/input.mask/input.prompt` 正确，一张空间对齐的白编辑黑保留 mask、每单元一次。README 推荐 `latest.safetensors`，默认 YAML 却仍是 `maskflow-S.safetensors`；要显式指定 latest 并 pin HF revision，不能把 latest 名称当不可变版本。50 步、text CFG 4、mask CFG 1，约 1 MP、32 对齐，膨胀25、blur25/sigma25、pixel blend 与 Poisson 默认流程需完整记录。不是简单“有 mask 就只是裁剪输入”；它还把 mask 放进 VLM/VAE 条件并限制编辑场。

**公平性与备选。** point 小框和 add 锚点作为硬编辑范围可能严重限制新增物体和完整属性修改。源码可接受，任务语义不等价。 (A，推荐受控主行) 显式命名 `selector-as-edit-mask`，使用原生默认膨胀/融合，报告按操作拆分与有效编辑面积；(B) 固定尺度确定性扩张作为预注册候选，不读取隐藏 GT 范围；(C) point→SAM†/输出区域规划‡作为补充。不要在融合后再额外 GT 回贴。

**无区域。** CLI 强制 mask，S1/S5 无区域单元不能直接执行。底层类有 no-mask 回退到 QwenImageEditPlus 的代码，但 CLI 不暴露，且回退后的 LoRA 及输出语义未验证；不能把这当作完整 MaskFlow 的已验证 S1。可另行验证标注 backbone fallback，或使用 grounder‡；任何方案必须完成整个请求。

证据：[maskflow:README.md:101](https://github.com/ReyChiaro/MaskFlow/blob/3125f1ecd72f5a4e068c5a1954e9d6a8df38d443/README.md#L101-L140)；[maskflow:configs/inference.yaml:6](https://github.com/ReyChiaro/MaskFlow/blob/3125f1ecd72f5a4e068c5a1954e9d6a8df38d443/configs/inference.yaml#L6-L33)；[maskflow:pipelines/qwenimage/qwenimage_maskflow.py:644](https://github.com/ReyChiaro/MaskFlow/blob/3125f1ecd72f5a4e068c5a1954e9d6a8df38d443/pipelines/qwenimage/qwenimage_maskflow.py#L644-L724)；[maskflow:pipelines/qwenimage/qwenimage_maskflow.py:132](https://github.com/ReyChiaro/MaskFlow/blob/3125f1ecd72f5a4e068c5a1954e9d6a8df38d443/pipelines/qwenimage/qwenimage_maskflow.py#L132-L162)；[maskflow:inference.py:22](https://github.com/ReyChiaro/MaskFlow/blob/3125f1ecd72f5a4e068c5a1954e9d6a8df38d443/inference.py#L22-L60)。

## 8. 可选：FLUX.2 klein-9B

蒸馏 `FLUX.2-klein-9B` 与 `FLUX.2-klein-base-9B` 不同。`Flux2KleinPipeline.__call__` 的默认 50/4 不能当作蒸馏权重推荐值；distilled 配置下 guidance>1 会警告并忽略，实际不启用 CFG。推荐 4 步、guidance 1。多图输入在代码中存在，参考图各自缩放到约 1 MP；官方没有标记图质量保证。文本编码器是 Qwen3ForCausalLM，无图像视觉编码，但“纯文本编码器绝对不能处理坐标”不是逻辑结论，只能说本协议缺乏推荐依据，优先双图/单图标记。S2 fallback 和 S4/S5 冻结同 Qwen。

备选 (A，推荐) distilled 4/1 与双图 A；(B) 单图 A；(C) base-9B 50/4 必须另起模型行，不能在 dev 里悄悄替换。HF 9B 受门控，本机有 4B 不代表有 9B 或已授权下载。

证据：[diffusers:src/diffusers/pipelines/flux2/pipeline_flux2_klein.py:580](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/flux2/pipeline_flux2_klein.py#L580-L596)；[diffusers:src/diffusers/pipelines/flux2/pipeline_flux2_klein.py:616](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/flux2/pipeline_flux2_klein.py#L616-L636)；[black-forest-labs/FLUX.2-klein-9B/README.md](https://huggingface.co/black-forest-labs/FLUX.2-klein-9B/blob/92196c8e11f7b6cf2b7493e037d8c5345c559216/README.md)。

## 9. 可选：QwenImageEditInpaintPipeline

这不是 2511 Plus 的同名 mask 重载。官方示例权重是 `Qwen/Qwen-Image-Edit`；应明确 checkpoint，不能默认把 2511 装进旧 pipeline 并声称等价。单 mask、指令 prompt、默认 strength .6、50 步、true CFG4，denoising 每步已有 latent blend。strength .6 实际执行的步数由 scheduler 截取，报告请求步数和实际 NFE。

备选 (A，推荐) 使用官方旧 Edit 权重作为单独可选对照，strength .6 固定；(B) .6/.8/1.0 选择应计入最多 4 个完整候选配置，不能额外给三倍预算；(C) 2511 支持须独立代码/权重兼容验证后命名新行。S1 无 mask 与 S5 部分无 mask不能直接用 inpaint 入口，整请求 N/A 或 grounder‡。与 MaskFlow 同样披露 selector≠输出 edit mask，不额外回贴。

证据：[diffusers:src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py:641](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py#L641-L660)；[diffusers:src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py:46](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py#L46-L66)；[diffusers:src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py:1019](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py#L1019-L1031)。

## 10. 原协议第 11 节逐项结论

|原待核项|结论|建议|
|---|---|---|
|Qwen2.1 圈画/单独 mask|README 宣称和 image-list 接口已确认；确切多实例 mask 编码仍❓；issue #21 无已读维护者解答|保留候选，不能预先宣告为原生 `mask_image` 通道|
|FLUX.3 add 的 src_bbox|✅新增内容行 src=null/from=target；⚠️benchmark 给的是源锚点，不是新增目标框|主候选编码锚点行；预测输出框放原生 PUP 补充流程|
|MaskFlow `[MASK_AREA]`|❌原替换方向与 README 相反|用原始 no-ref 或固定 masked-region 词法替换|
|BAGEL 多图没有官方示例|⚠️维护者在 issue #83 给了 `interleave_inference` 示例，并提醒训练占比较小|列为官方支持的多图调用候选，标记编辑效果仍待 dev|

许可证也需修订：MICE/TAL 的代码授权不能由基础权重继承；FLUX.3 当前为含条件商业授权的 Kommunity，而非概括为“全部非商用”；Qwen2.1 Research License 原协议遗漏；Hunyuan 与 BrushEdit 地域范围不同。详见运行报告与固定版本 LICENSE 链接。学术用途不自动免除许可条件；本次没有代表用户接受任何门控条款。
