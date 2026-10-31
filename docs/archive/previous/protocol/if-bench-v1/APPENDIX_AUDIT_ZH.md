# 附录方法：阶段1静态核对

按用户顺序要求，附录模型的推理排在主表完成之后。本轮对其源码、文档与可行性做静态审计，**没有执行附录大模型**。下列“接受”只表示参数路径，不保证标记理解。每个方法×10个setting的判定与证据见SETTING_MATRIX_ZH.md；原生模型/代码SHA见SOURCE_INDEX.md。通用G01–G22规则同样适用。

## A1. Step1X-Edit v1.2

单图编辑，原始I做S1、A做S2/S3可接入，坐标只是文本候选，无原生point/mask参数。v1p2必须用官方指向的Peyton-Chen/diffusers分支；不应复用本地旧Step1X i1258权重冒充v1p2。源码默认28步、CFG6、size_level1024、thinking=False、reflection=True/max_try_cnt=3；**官方v1p2示例是50步且thinking/reflection都True**。原协议所述是函数默认而非推荐组合。

备选：(A，推荐) 官方示例50步、两开关开启，单图A；(B) 两开关关闭作为计算受控消融；(C) 显式坐标候选（只有公共坐标）。S4/S5沿冻结映射，但S5无标记单元仍保留ref指令。reflection可能多次生成并选择，不可称每case只有一次网络推理；说明内部反馈不使用benchmark Judge。主机80GB符合官方建议，但v1p2权重尚未本机验证；fork及Transformers依赖需独立环境。代码/权重Apache-2.0。

证据：[step1x:README.md:125](https://github.com/stepfun-ai/Step1X-Edit/blob/4cca05dfcd6c32dc810d0b4db84c2bf0682a5aeb/README.md#L125-L171)；[step1x_fork:src/diffusers/pipelines/step1x_edit/pipeline_step1x_edit_v1p2.py:946](https://github.com/Peyton-Chen/diffusers/blob/f5f1c98fa00cb4d0479af1b1b1c17d724345963a/src/diffusers/pipelines/step1x_edit/pipeline_step1x_edit_v1p2.py#L946-L979)；[v1p2 model card](https://huggingface.co/stepfun-ai/Step1X-Edit-v1p2)。

## A2. LongCat-Image-Edit

单图`LongCatImageEditPipeline`；无原生point/box/mask。官方编辑示例50步、guidance4.5、CPU offload约18GB；Turbo8步/CFG1是独立权重，不能换名。S1 I、区域A的接口成立，坐标文本无解析保证。S2可额外报丢区域优化行，S3不允许。S4/S5共享映射并保持无区域文本。推荐(A)单图标记；(B)显式坐标候选，不能因为VLM就称原生坐标接口。本机旧/tmp下载未视作现有可靠权重，正式重下载前核对revision；Apache-2.0。

证据：[longcat:README.md:173](https://github.com/meituan-longcat/LongCat-Image/blob/f0e4c43c5ef74b011ff71570fbfc2bdffbc9ab06/README.md#L173-L196)；[官方配置问题 #37](https://github.com/meituan-longcat/LongCat-Image/issues/37)。

## A3. BAGEL

`__call__`便利入口是一张图，但`interleave_inference(input_lists=[I,A,text])`循环接受多张PIL图。维护者在官方issue #83给过实际多图列表示例，原协议“无官方多图示例”不成立。该例不是标记图编辑质量验证，维护者还说明训练中此类多对象数据比例较低。交错入口默认think=False、50步、cfg_text3、cfg_img1.5、cfg_interval[.4,1]、shift3，底层gen_image默认text CFG4，README建议4–8；务必记录所用入口与值，不能混称默认。

推荐(A)单图A与双图[I,A]作为dev候选；(B)明确坐标候选；think固定或另列消融。S1 I，S2/S3绑定编号，S4/S5保留全请求。代码无显式图片数上限，不保证任意多图质量；本协议≤2图、K≤5。本机无BAGEL权重验证，官方提供offload/量化路线，单80GB资源上可能可行，仍❓。Apache-2.0。

证据：[bagel:inferencer.py:208](https://github.com/ByteDance-Seed/Bagel/blob/a2fa77dd8caeefc41e6607ae0ec17408d3f4ee9f/inferencer.py#L208-L280)；[维护者多图答复与示例](https://github.com/ByteDance-Seed/Bagel/issues/83)。

## A4. OmniGen2

`input_images`为多图列表，S1单图、S2/S3双图以及S4/S5组合均可传。函数默认28步/text CFG4/image CFG1；README推荐编辑image CFG1.2–2.0并以50步为默认说明。因此原协议只引用代码4/1会遗漏推荐配置。推理使用参考图VAE通道不能因论文叫MLLM就推断代码会把图像送入语言编码器；官方issue #13提出这一点，未见维护者答复，坐标候选不得称原生。

推荐(A)50步/4/1.5与双图标记，声明1.5是推荐范围中预注册值；(B)单图A；(C)严格代码默认28/4/1另报。输出默认1024²，单输入align_res和多输入路径有差异，应显式保持源图比例。README约17GB、CPU offload可用；本机尚未权重验证。代码及权重条款各自核对，不能从依赖FLUX VAE自动推出整模型同一许可。

证据：[omnigen2:omnigen2/pipelines/omnigen2/pipeline_omnigen2.py:467](https://github.com/VectorSpaceLab/OmniGen2/blob/18e6f9d5271b517fcb32e999f10df943ae9b8f20/omnigen2/pipelines/omnigen2/pipeline_omnigen2.py#L467-L550)；[omnigen2:README.md:178](https://github.com/VectorSpaceLab/OmniGen2/blob/18e6f9d5271b517fcb32e999f10df943ae9b8f20/README.md#L178-L198)；[issue #13](https://github.com/VectorSpaceLab/OmniGen2/issues/13)。

## A5. HunyuanImage-3.0-Instruct

支持≤3参考图，双图标记接口可接入。完整Instruct与Distil不可混行；前者50步，后者8步，`bot_task=think_recaption`、en_unified、max_new_tokens2048、image_size=auto、infer_align_image_size=True、SDPA；README推荐≥8×80GB，不是已证明的最低硬件下限。guidance需要从选中checkpoint的generation config记录，README表没有统一可替代的CFG常数，不猜数值。

推荐(A)完整官方默认推理，记录thinking/recaption输出；(B)Distil8另列；(C)关闭内置思考作为消融，不能用64 token调试预算冒充推荐。S4/S5如双图且有多目标必须保留顺序和全部指令。现机资源数量匹配但8卡可能有其他任务且未下载完整权重，不能称已跑通。官方issue #98报告步数参数路径问题，应在运行前检查实际NFE而非只读CLI。Hunyuan许可证排除EU/UK/韩国，另有大用户规模条款。

证据：[hunyuan:README.md:158](https://github.com/Tencent-Hunyuan/HunyuanImage-3.0/blob/6e9113a692a27a0751d82aba3b2015a876646c03/README.md#L158-L264)；[hunyuan:README.md:425](https://github.com/Tencent-Hunyuan/HunyuanImage-3.0/blob/6e9113a692a27a0751d82aba3b2015a876646c03/README.md#L425-L429)；[步数问题 #98](https://github.com/Tencent-Hunyuan/HunyuanImage-3.0/issues/98)。

## A6. HiDream-O1-Image

原协议“编辑模式恰好一张图”过强：CLI `--ref_images`是任意列表，pipeline确实循环多图。`len(ref_images)==1`控制**dev**权重的特定editing scheduler，以及可选keep_original_aspect；full模式不据此拒绝双图。默认full：50步、CFG5、shift3、2048²；dev：28步、CFG0、shift1，单图默认flow_match；需要明确使用哪份checkpoint。`layout_bboxes`为xxyy相对坐标、会合成布局参考图，不是已有对象的通用编辑mask。

推荐(A)原始full权重下把A与[I,A]都纳入候选，保持官方约4MP分辨率；(B)dev专用单图编辑作为独立行；(C)layout只在语义匹配的补充实验中验证，不强塞主表。S1/S2/S3/S4/S5均不能根据“单图强制”错误限制候选。历史已有高分辨率结果不能直接算新setting验证；本机有名为HiDream的权重，但需核对full/dev匹配，附录暂不推理。MIT；某些可选agent涉及额外Gemma权重许可，应记录所选路径。

证据：[hidream:inference.py:26](https://github.com/HiDream-ai/HiDream-O1-Image/blob/2c2d29ff729e48f33e41f49edfdbd81d5ac103b4/inference.py#L26-L97)；[hidream:models/pipeline.py:184](https://github.com/HiDream-ai/HiDream-O1-Image/blob/2c2d29ff729e48f33e41f49edfdbd81d5ac103b4/models/pipeline.py#L184-L230)；[hidream:README.md:310](https://github.com/HiDream-ai/HiDream-O1-Image/blob/2c2d29ff729e48f33e41f49edfdbd81d5ac103b4/README.md#L310-L321)。

## A7. FLUX.1 Fill

单图+白编辑mask，不提供一个请求内K组独立prompt/mask绑定，故按unit顺序K次。主入口没有S1无mask方案，S5不能只做有mask部分。caption式prompt§、官方50步/guidance30；模型权重`FLUX.1-Fill-dev`。hard edit extent与源selector，尤其add锚点/point小框的冲突必须披露。

推荐(A)按公共selector转换、caption§及固定原生设置；(B)固定扩张mask为候选；(C)额外grounder‡仅补充。若额外像素回贴，范围只由当前公开区域导出，不能回贴隐藏GT；GT回贴不是上界。HF门控，本次匿名读取配置401，不能称可下载已验证。非商用权重条款；显存需按大FLUX完整载入/offload实测，当前未做。

证据：[diffusers:src/diffusers/pipelines/flux/pipeline_flux_fill.py:1](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/flux/pipeline_flux_fill.py#L1-L90)；[FLUX.1 Fill model card](https://huggingface.co/black-forest-labs/FLUX.1-Fill-dev)。

## A8. Flux2KleinInpaintPipeline

单mask与可选image_reference都存在；默认strength .8、50步、guidance8仅为函数默认，实际需要结合蒸馏/非蒸馏权重约束。**L1213–1224每步latent blend真实存在**，原文归类“没有融合”错误。不能因为latent blend就宣称像素严格不变。

推荐(A)明确base或distilled checkpoint后按官方示例参数，保留latent blend；(B)额外像素融合独立候选，避免重复默认回贴；(C)不要把整个source当第二次reference默认为必需。S1/S5无mask同单mask限制，point/box转换及caption/指令具体按选中权重验证。官方issue #15131涉及padding_mask_crop输出几何，本协议先不使用该选项，必须记录当前revision。9B门控状态与显存同可选FLUX.2，附录未推理。

证据：[diffusers:src/diffusers/pipelines/flux2/pipeline_flux2_klein_inpaint.py:1213](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/flux2/pipeline_flux2_klein_inpaint.py#L1213-L1224)；[diffusers:src/diffusers/pipelines/flux2/pipeline_flux2_klein_inpaint.py:828](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/flux2/pipeline_flux2_klein_inpaint.py#L828-L850)；[padding_mask_crop issue #15131](https://github.com/huggingface/diffusers/issues/15131)。

## A9. BrushNet

原生单mask，用caption§，按K次串行；box→矩形mask用random-mask权重合理，分割形状mask可用segmentation-mask权重；S4混合用何权重是方法配置，不能每case凭结果切换。README同时有SD1.5/SDXL版本，须显式选定。示例50步、brushnet conditioning1、**blended=False**；`blended=True`是脚本变量，不是pipeline天然总会融合的保证。

推荐(A)明确SD1.5+固定random-mask权重、示例原样；(B)blended=True单独候选；(C)segmentation权重作为另一个完整配置而不是额外免费候选。S1/S5缺区域不能直接执行。依赖fork Diffusers，不能安装到主模型共用环境。权重与基础SD许可分别记录；未推理，不能给精确峰值显存。mask正反约定须测试，issue #7/#51不能替代代码检查。

证据：[brushnet:examples/brushnet/test_brushnet.py:12](https://github.com/TencentARC/BrushNet/blob/0f9d9e54ca85c40a11a8f0504b4b5b2e7e8fd14d/examples/brushnet/test_brushnet.py#L12-L65)；[brushnet:README.md:128](https://github.com/TencentARC/BrushNet/blob/0f9d9e54ca85c40a11a8f0504b4b5b2e7e8fd14d/README.md#L128-L156)；[mask讨论 #51](https://github.com/TencentARC/BrushNet/issues/51)。

## A10. PowerPaint

有`PowerPaintController`可调用，不必启动Gradio才推理；仍需封装批处理。text-guided用P_obj、remove用P_ctxt并可无caption；UI默认45步/CFG7.5，remove官方建议≥10。不同task分支resize短边512/640，对齐mask须一致。代码中确有soft paste计算，但**普通predict分支将result_paste/dict_out赋值注释掉，返回原始result**；controlnet分支却返回result_paste。不能仅搜索到blend公式就称默认输出已融合。

推荐(A)固定v2 checkpoint和普通任务入口，按其真实返回图，remove CFG10，其他7.5；(B)显式启用软件融合的适配候选，披露变更；(C)如选controlnet路线另列，不能混作同一默认。S2/S3 caption丢ref导致Δ_lang结构性接近0；S1/S5无mask仍需补充定位或N/A。基础SD版本与PowerPaint权重/许可证分别核对；issue #155反映入口兼容问题，阶段2附录需实际验证。此处不声称有原生一致的多区域输入。

证据：[powerpaint:app.py:250](https://github.com/open-mmlab/PowerPaint/blob/5b4c3d52291709fcec2a1870d987da693fd3549c/app.py#L250-L386)；[powerpaint:app.py:377](https://github.com/open-mmlab/PowerPaint/blob/5b4c3d52291709fcec2a1870d987da693fd3549c/app.py#L377-L386)；[powerpaint:app.py:674](https://github.com/open-mmlab/PowerPaint/blob/5b4c3d52291709fcec2a1870d987da693fd3549c/app.py#L674-L684)；[入口问题 #155](https://github.com/open-mmlab/PowerPaint/issues/155)。

## A11. InstantX Qwen-Image-ControlNet-Inpainting

model card使用`QwenImageControlNetInpaintPipeline`，实际传`control_image`与`control_mask`，不是泛化的`mask_image`调用。示例30步、trueCFG4、negative=" "、ControlNet conditioning（示例1）；基础为Qwen-Image生成模型而非2511编辑器。官方推荐描述整个图像及inpaint区域的caption，不推荐指令式prompt。

推荐(A)冻结从公共信息生成全图caption§的统一改写流程；(B)仅局部目标caption§作为消融，但可能低估官方推荐能力；(C)原始指令仅作为待测候选，不能称官方推荐。不同setting必须避免共享含私有ref的caption缓存。S1不能无mask，S5不能跳过任务；单maskK次，额外回贴可另列。HF非门控/Apache声明已取证，完整Qwen base和ControlNet尚未在本机验证，显存/offload待实测。

证据：[InstantX/Qwen-Image-ControlNet-Inpainting/README.md](https://huggingface.co/InstantX/Qwen-Image-ControlNet-Inpainting/blob/5387c47add7b3a9b1d6341b75a251d235408c670/README.md)；[diffusers:src/diffusers/pipelines/qwenimage/pipeline_qwenimage_controlnet_inpaint.py:1](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_controlnet_inpaint.py#L1-L100)。

## A12. BrushEdit

官方整体有VLM编辑类型、对象识别、定位mask与caption流程，**S1不应因为底层BrushNet需要mask就把整个BrushEdit判为不支持**。原协议的“传用户mask+target_prompt跳过VLM”基本可实现：分支仍需明确task/category，完整入口与BrushNet内核两行应分开。`BrushEdit_Pipeline`内部会缩放到VAE倍数、模糊21，返回图可能已经融合；逐路径追踪返回值。

推荐(A)S1完整官方工作流，区域setting注入已有用户mask/公共caption§，记录绕过了哪些组件；(B)BrushEdit-BrushNet-core作为单独受控行，S1 N/A；(C)若统一外部grounder，标‡，不可混成“原生”。S5可原生规划无区域单元，但合并完整K任务仍须适配验证。fork依赖、VLM/SAM/BrushNet多模型和可能的API入口需明确选择本地方案；本轮未运行。许可证明确排除EU，不与Hunyuan的范围混同。

证据：[brushedit:app/src/brushedit_all_in_one_pipeline.py:9](https://github.com/TencentARC/BrushEdit/blob/0f415c52aa306b5d53f5cb54045fba4fe521fed5/app/src/brushedit_all_in_one_pipeline.py#L9-L71)；[brushedit:app/src/brushedit_app.py:689](https://github.com/TencentARC/BrushEdit/blob/0f415c52aa306b5d53f5cb54045fba4fe521fed5/app/src/brushedit_app.py#L689-L752)。

## A13. GoT

`got_input`为自定义CoT字符串，不是bbox JSON参数。解析器要求`<|box_start|>(x1,y1),(x2,y2)<|box_end|> (color)`，整数0–1000，逗号空格等格式严格。生成还依赖完整GoT token序列，不能只插一个孤立框就声称区域注入已验证。模型默认50步、guidance7.5、image guidance1、cond image guidance4、1024²，输入图会拉伸；pad→裁回是benchmark适配，不是官方原样行为。

推荐(A)S1官方完整生成；(B)S2/S3/S4/S5完整模板内注入公共框，point固定小框、mask外接框，标为待验证扩展；(C)单图标记作fallback候选，但须有容量和语义验证。保留相同源selector约束，no-ref不可填隐藏对象名。S5无区域部分原生生成GoT后合并可能丢/重复单元，须验证。主机H100理论可运行但项目多组件权重及依赖未完整下载，❓；许可证见源码，不以arXiv文档替代。

证据：[got:got/models/got_model.py:72](https://github.com/rongyaofang/GoT/blob/091220916124ce9d479dc2574981816afbb32a1f/got/models/got_model.py#L72-L109)；[got:got/models/utils.py:27](https://github.com/rongyaofang/GoT/blob/091220916124ce9d479dc2574981816afbb32a1f/got/models/utils.py#L27-L51)；[got:got/models/got_model.py:260](https://github.com/rongyaofang/GoT/blob/091220916124ce9d479dc2574981816afbb32a1f/got/models/got_model.py#L260-L280)。

## A14. TAL

官方`infer_qwen.py`是原始Qwen-Image-Edit的DiffSynth路径，不能默认为2511。无用户区域参数，按任务类型利用source/target注意力生成内部mask；单元顺序处理S1符合接口。默认28步；CLI cfg_scale、task_type映射与语义步骤需要明确记录，不能把其他模型的CFG默认复制过来。缺task_type时会使用两个stream定位，与显式add/remove不同。模型内部任务感知定位属于TAL，不是外部‡。

推荐(A)原生S1，公共操作类型通过指令固定映射，逐单元K次；(B)不提供task_type的官方默认作消融。S2–S5按原协议范围N/A（不接受用户区域），可以另研究标记图但那是新增用法不能算已验证TAL接口。官方Python3.10/Torch2.6/CUDA12.4/Transformers4.57.6，需隔离DiffSynth依赖；不是使用所有新模型环境的一行插件。tree检查未找到LICENSE；基础权重许可不覆盖TAL代码。未运行附录模型。

证据：[tal:infer_qwen.py:124](https://github.com/Jessie459/TAL/blob/3143b0561b5573f64196fef156d93d075c7b0037/infer_qwen.py#L124-L184)；[tal:infer_qwen.py:262](https://github.com/Jessie459/TAL/blob/3143b0561b5573f64196fef156d93d075c7b0037/infer_qwen.py#L262-L315)；[tal:README.md:7](https://github.com/Jessie459/TAL/blob/3143b0561b5573f64196fef156d93d075c7b0037/README.md#L7-L30)。

所有附录模型的“推荐候选”是本审计建议，不能冒称原作者已做过IF-Bench。原第8节的概括只适用于真正的单mask内核，不能覆盖GoT/TAL或完整BrushEdit。缺失参数/许可证/硬件峰值本轮明确留❓，不凭相似模型补数字。
