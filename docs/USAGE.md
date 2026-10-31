# IF-Bench 使用说明

IF-Bench 评测同一真实场景中 2–5 个目标的联合编辑。当前固定方案为 **`fairness-v2.2-1mp`**，范围为 **Qwen-Image-Edit-2511、Qwen-Image-2.1、FLUX.3 Klein distilled、RePlan（Qwen-2511）、MIRAGE（Qwen-2511）、MICE（Klein-4B）、FLUX.2 Klein-9B distilled**。以下表格定义全部七模型×十种 setting，不按输出或分数另选输入。

配置见 [fairness_v2_2_1mp.json](../configs/evaluation/fairness_v2_2_1mp.json)，运行见 [FULL_RUN.md](FULL_RUN.md)，实际验证状态见 [RESULTS.md](RESULTS.md)，数据科学信息见 [CONSTRUCTION.md](CONSTRUCTION.md)。模型接收共同的约 1MP 图像；Judge 仍依据原始源图、原始 GT 和 canonical 指令评分。

## 1. 数据与文件

release 2.6.0 有 **1,084 张源图、3,872 个编辑单元**。K=2/3/4/5 的图数分别为147/255/597/85；add/remove/replace/attribute 的单元数分别为980/921/969/1,002。当前入口由 [data/current.json](../data/current.json) 指定，统计见 [statistics.json](../data/v2_2.6.0/statistics.json)。

| 内容 | 位置或约束 |
|---|---|
| 当前 manifest | [data/v2_2.6.0/cases.jsonl](../data/v2_2.6.0/cases.jsonl) |
| manifest SHA256 | `818ce524a1d1f363dc8ea5caa7a887b2dd0355c17a5600d1cbd696cffcf263fb` |
| 原始数据资产根 | `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2` |
| 权重根 | `/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models` |
| 当前实验配置 | [fairness_v2_2_1mp.json](../configs/evaluation/fairness_v2_2_1mp.json) |
| 公共输入、几何、运行代码快照 | 已发布运行包；具体路径与 SHA 由 `plan.json` 和 `READY.json` 冻结 |
| 小样本、审查、预览和日志 | `/tmp/ifbench/` 或共享 `.ifbench-tmp/` 下的独立运行目录 |
| 已冻结正式输出 | `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/IF-Bench/` 下的独立正式目录 |

全量评测使用全部1,084张图，只报告一份总结果。数据包含开发过程中已接触的样本，因此不将总结果称为独立未见测试集估计。当前 release 的 `independent_human_verified=false`、`semantic_signoff=false` 如实保留；自动校验或 AI 看图不等于独立人工验收。

## 2. 约 1MP 公共画布

### 2.1 两套坐标各司其职

- **canonical source**：manifest 中的原始源图、尺寸与 GT。仅用于数据身份、逆映射和 Judge。
- **I**：按统一确定性规则生成的约 1MP 清图，包含固定灰色留边；所有编辑模型及其原生 planner/locator 只接收这份画布对应的图像。
- **A**：在 I 上重新画当前 setting 的公开区域、颜色和 U 标签；与 I 同尺寸、同坐标。不是参考答案图。

设原图尺寸为 `(W,H)`，目标面积 `A₀=1024²`。从 `s=sqrt(A₀/(W×H))` 开始，内容尺寸为 `(round(Ws),round(Hs))`，两轴分别向上对齐到32得到画布；若画布面积超过 A₀，令 `s←0.995s` 后重算。round 使用 ties-to-even。内容用 LANCZOS 等比缩放，居中放到 RGB `(128,128,128)` 底色；奇数留边多出的像素在右/下侧。保存最终内容尺寸、画布尺寸、内容框、两轴实际比例与偏移。

画布面积以1024²为上限，不把每张图拉伸成1024×1024，也不裁掉源图内容。全部 setting 对同一 case 使用同一 I；所有模型共享相同 I 和 A 字节。网格与整数内容尺寸会有微小宽高比取整误差，实际比例以几何记录为准。

### 2.2 区域与标记

只先投影当前 setting 已公开的信息，再进行几何转换。模型侧公开请求不含原始高分辨率图或未公开的框/mask，也不能让 planner 根据 canonical 路径重新读取原图。

| 类型 | 当前公共画布中的定义 |
|---|---|
| point | 公开像素点经 `(x×sx+ox, y×sy+oy)` 连续仿射变换；仅绘图时栅格化 |
| box | 半开 `(x1,y1,x2,y2)` 的每条边按相同仿射变换；normalized xyxy 再除以公共画布 `(Wc,Hc,Wc,Hc)` |
| mask | 公开二值 mask 用 NEAREST 缩放到内容尺寸，留边补0；白色选中、黑色未选中 |
| none | 无几何，不从 GT 或其他 setting 补区域 |

不调用 SAM、外部定位器、caption 改写器或区域修复器；不将点变成额外目标框，不把 mask 简化成 bbox。若公共 mask 缩放后为空，输入构造明确报错；原生接口拒绝输入则记录失败，不膨胀区域、删任务或删分母。模型内部量化仍保留其原生行为。

标记在公共画布上重新绘制。固定颜色为 U1 red `(255,0,0)`、U2 blue `(0,80,255)`、U3 green `(0,170,0)`、U4 yellow `(255,210,0)`、U5 magenta `(230,0,230)`。令 `d=min(Wc,Hc)`，点半径为 `max(1,round(.01d))`，白环宽 `max(1,round(.002d))`，轮廓宽 `max(1,round(.004d))`，字号 `max(12,round(.02d))`；使用固定 DejaVuSans 字体和 SHA。mask 画完整边界，包括洞、分离组件和贴边部分，不填色遮盖目标。标签与引线只依赖公开几何。

### 2.3 原生网格与输出恢复

公共输入像素预算不等于所有方法的内部视觉 token、局部裁剪或计算预算相同。检查点自身的视觉编码器、VAE、KV cache 和原生区域处理保留。

Qwen2511、Qwen2.1、FLUX3、FLUX2 Klein-9B 的输出宽高按公共画布传入；MICE 的 `model_size` 使用公共画布。**RePlan 和 MIRAGE 保留各自约1MP原生输出网格。RePlan 的该原生区域流程不以传入 width/height 控制最终尺寸，不将这两个参数写成有效约束；MIRAGE 的原生接口也不增加此约束。** 两者均只读 I/A，其内部缩放和局部分支属于方法自身。每次调用记录实际 raw 尺寸与面积。

输出同时保存完整 `raw.png` 和供 Judge 使用的 `output.png`。将几何记录中的内容框按 `raw尺寸/公共画布尺寸` 换算为浮点 crop box，再用一次 LANCZOS resize 去除留边并恢复原始 `(W,H)`。这只是所有模型共同的几何逆映射，不使用 GT 擦除标记、修改背景或修图。

实现：[公共画布与逆映射](../src/samtok_benchmark/ifbench/canvas.py) · [公开信息边界](../src/samtok_benchmark/ifbench/public.py) · [确定性标注](../src/samtok_benchmark/ifbench/render.py)。

## 3. 十种 setting 与 prompt

**ref** 是包含目标身份或位置描述的公开指令。**no-ref** 保留操作与结果要求，用 `the selected region` 替换目标指称，不能从私有标注补回对象名。U1…UK 同时绑定指令、颜色、区域和原生 local 输入。selector 选择现有对象、部件或 attachment/support anchor；添加任务的 selector 不是新增物的输出轮廓，也不是任意编辑的硬差分边界。

| Setting | 每单元文字 | 每单元区域 |
|---|---|---|
| S1 | ref | none |
| S2-point | ref | point |
| S2-box | ref | box |
| S2-mask | ref | mask |
| S3-point | no-ref | point |
| S3-box | no-ref | box |
| S3-mask | no-ref | mask |
| S4-ref | ref | 固定混合 point/box/mask |
| S4-noref | no-ref | 与 S4-ref 相同的混合分配 |
| S5 | 固定逐单元 ref/no-ref | 固定逐单元 none/point/box/mask；none 必须是 ref |

S4/S5 分配只生成一次，七模型共用。每个请求的 K 个目标进入一次原生联合编辑流程，不把目标人工分成 K 次连续改图。S3、S4-noref 和 S5 的 no-ref 单元不丢弃区域。S2 discard-region 仅以同一 case 的 S1 输出精确复用为补充，不替代主行、不参与重新择优。

共享 global 模板为：

```text
Apply all of the following edits to the image. Keep everything else unchanged.
U1. {公开指令1}
U2. {公开指令2}
```

双图模板固定前导为：

```text
Image 1 is the clean source image to edit. Image 2 is the same image with colored marks and U labels. Use the marks only to identify the selected regions in Image 1. Return only the edited Image 1. Do not reproduce any marks, labels, or leader lines.
Each supplied region selects a source object, part, or anchor. For an addition, it selects the attachment or support location, not the outline of the new object.
Apply all of the following edits to the image. Keep everything else unchanged.
```

随后逐行追加 `U编号. [颜色 point/box/mask contour, label U编号] 公开原指令`。none 单元省略整个方括号；全 none 请求直接使用 I+global，不生成空标注图。花括号仅表示文档变量；实际请求必须保存完整最终 prompt。实现见 [inputs.py](../src/samtok_benchmark/ifbench/inputs.py)。

## 4. 七模型 × 十种 setting

方法边界为完整命名方法。PE/PUP 关闭，不接外部语义转换或能力增强组件。检查点自带编码器保留；RePlan/MIRAGE 自带 planner/parser/locator 保留，并单独记录调用与成本。†/‡/§ 分别表示另行使用 SAM、外部定位或 caption 改写的补充配置，均不进入当前主结果。

### 4.1 Qwen2511、Qwen2.1、FLUX3、FLUX2 Klein-9B

下表逐项适用于四个模型中的每一个。文字路由均由 setting 决定；FLUX3 的 S1 使用下述原生引用模板，其余使用共享 global/dual。

| Setting | 图像列表 | 文本 | 区域呈现 |
|---|---|---|---|
| S1 | `[I]` | ref/global；FLUX3用S1模板 | 无区域 |
| S2-point | `[I,A]` | ref/dual | 彩点与U绑定 |
| S2-box | `[I,A]` | ref/dual | 彩框与U绑定 |
| S2-mask | `[I,A]` | ref/dual | 完整mask轮廓与U绑定 |
| S3-point | `[I,A]` | no-ref/dual | 同一彩点 |
| S3-box | `[I,A]` | no-ref/dual | 同一彩框 |
| S3-mask | `[I,A]` | no-ref/dual | 同一完整轮廓 |
| S4-ref | `[I,A]` | ref/dual | 固定混合标记 |
| S4-noref | `[I,A]` | no-ref/dual | 与S4-ref相同的标记 |
| S5 | 有区域为`[I,A]`；全none为`[I]` | 冻结混合文字 | 仅标记已公开区域 |

双图原生 API 不提供“第二图只定位、绝不复制标记”的硬约束，图像角色由固定 prompt 表达。视觉 mask 轮廓不是二值 inpainting mask，文本编码器也不因此变成额外定位模型。真实标记残留与编辑错误保留评分，不据输出修改路由。

| 模型 | 当前原生调用与参数 |
|---|---|
| Qwen-Image-Edit-2511 | `QwenImageEditPlusPipeline(image=images, prompt=prompt, width=Wc, height=Hc, ...)`；40步、true CFG4、guidance1、negative=`" "`、max_sequence_length512、单输出；保留原生VLM/VAE条件处理。 |
| Qwen-Image-2.1 | `QwenImage21Pipeline(image=images, prompt=prompt, width=Wc, height=Hc, ...)`；40步、true CFG1、`output_resolution=1024`、`use_kv_cache=True`、PE关闭。原生 `enable_model_cpu_offload` 放置组件，保留BF16与原生KV流程，不额外启用VAE tiling/slicing。 |
| FLUX.3 Klein distilled | `generate(..., images=images, boxes=None, width=Wc, height=Hc, model="distilled", steps=16, guidance=None, pup=False, safety=False)`；全部setting固定boxes=None，不补src/tgt目标框；输入公共画布，保留原生预处理。 |
| FLUX.2 Klein-9B distilled | `Flux2KleinPipeline(image=images, prompt=prompt, width=Wc, height=Hc, ...)`；4步、guidance1、max_sequence_length512。内置Qwen3-8B是文本编码器，不额外承担视觉指代。完整chat token超限则记录失败，不截掉后续任务。 |

FLUX3 的 S1 固定形式为 `Edit <ref_image_0>. {全部ref指令，单空格连接} Keep everything else unchanged.`。当前各 setting 共用同一 I；区域增益仍是完整方法在两种输入条件下的表现差，不能自动解释成单因素因果效应。

入口：[原生 adapter](../src/samtok_benchmark/ifbench/dev_runner.py) · [模型 worker](../src/samtok_benchmark/ifbench/fairness_dev_worker.py) · [FLUX3 helper](../src/evaluation/protocol_audit/fairness_flux3_replan.py) · [Qwen2.1原生内存放置](../src/samtok_benchmark/ifbench/qwen21_memory.py)。

### 4.2 RePlan 与 MIRAGE

两者的最终 editor 都编辑清图 I。全部视觉输入仅来自公共 I/A，不让 planner 读取 canonical 高分辨率原图；原生规划中的局部裁剪仍按方法自身执行。

| Setting | RePlan：原生planner→editor | MIRAGE：原生parser/locator→editor |
|---|---|---|
| S1 | `I+ref`→`I+原样response` | parser读ref；locator看I→I联合编辑 |
| S2-point | `A+ref/点/U`→`I+response` | parser读ref；locator看A+点/U提示→I |
| S2-box | `A+ref/框/U`→`I+response` | parser读ref；locator看A+框/U提示→I |
| S2-mask | `A+ref/轮廓/U`→`I+response` | parser读ref；locator看A+轮廓/U提示→I |
| S3-point | `A+no-ref/点/U`→`I+response` | parser读no-ref；locator看A+点/U提示→I |
| S3-box | `A+no-ref/框/U`→`I+response` | parser读no-ref；locator看A+框/U提示→I |
| S3-mask | `A+no-ref/轮廓/U`→`I+response` | parser读no-ref；locator看A+轮廓/U提示→I |
| S4-ref | `A+ref/固定混合`→`I+response` | parser读ref；locator看混合A+各U提示→I |
| S4-noref | `A+no-ref/同一混合`→`I+response` | parser读no-ref；locator看相同A+各U提示→I |
| S5 | `A+混合文字`→I；全none时planner看I | parser读混合文字；locator看A/I，none无额外几何提示→I |

**RePlan。** 所有 setting 调用方法自带 TainU/RePlan-Qwen2.5-VL-7B planner。区域请求用固定说明：

```text
This is an annotated copy of the source image. Use the colored marks and U labels only to identify the selected source regions. The marks, labels, and leader lines are not scene objects or editing targets. Plan the requested edits for the clean source image with the same dimensions and coordinates.
```

随后拼接 selector 说明、BASE与各U原指令。官方 `build_messages` 加入 `replan.txt`，`max_new_tokens=2048`。显式调用 `get_vlm_response(final_prompt, planner_image)`，再将 response 原样交给 `region_edit_with_attention(clean_source, final_prompt, response, ...)`。这是官方分阶段 API 编排；不手改框、hint、global/local归属或目标数。误把U标签当对象、遗漏任务或无效计划都保留原生表现。

editor为40步、true CFG4、guidance1、negative=`" "`、`expand_value=0`、`attention_switch_step=.5`。后两项采用官方Qwen CLI分支默认，不能混称Python API的全部默认。保留SDPA实现记录和原生近1MP网格，**不声称显式width/height生效**。

**MIRAGE。** 每个公开U指令作为原生parser的一个batch item；保留全部 `(refer_object,new_instruction)` 对，不强制拆分数等于K。Qwen3.5-9B原生direct/parent/part定位分支保留，none单元由方法自身从ref和I定位。公开区域只向对应grounding message追加：

```text
Spatial input for this edit: the {color} {shape} labeled {unit_id} indicates the selected source object, part, or anchor. The marks and labels are input annotations, not the target object. For an addition, the selection identifies the existing attachment or support location, not the outline of the new object.
```

不将提示塞进 `refer_object`，不人工修正原生框。normalized xyxy由官方 `to_pixels(..., padding=10)` 转为公共图坐标；局部文本用官方 `qwen_prompt`。清图I、公开原指令global、原生sub-prompts/bboxes进入 `run_qwen_image_edit`，保留40步、true CFG4、`patch_ratio=.4`、negative=`" "` 和原生全局/局部联合去噪、近1MP输出网格。parser/locator固定 `thinking=False`、`do_sample=False`，parse/grounding最多512/128新token；PyTorch reference kernel等实现身份如实记录。

两个方法都分别记录API调用、batch items、原生拆分数与diffusion forward，不把batch items当API次数。原生生成框是命名方法自身推理结果，不能用GT替换。入口：[RePlan helper](../src/evaluation/protocol_audit/fairness_flux3_replan.py) · [MIRAGE请求与空间提示](../src/evaluation/protocol_audit/fairness_mirage_mice_probe.py) · [worker](../src/samtok_benchmark/ifbench/fairness_dev_worker.py)。

### 4.3 MICE

MICE使用Klein-4B distilled与原生多实例attention。当前实现使用单张图，point通过A/global传达，box/mask用原生区域参数。没有额外点定位，也不把point造为框。

| Setting | 实际单图 | global文本 | local文本/区域 |
|---|---|---|---|
| S1 | I | 所有ref任务 | 无local/实例区域 |
| S2-point | A | 所有ref+点/U | 无local/实例区域 |
| S2-box | I | BASE | 各ref+原生normalized box |
| S2-mask | I | BASE | 各ref+原生mask binding |
| S3-point | A | 所有no-ref+点/U | 无local/实例区域 |
| S3-box | I | BASE | 各no-ref+原生box |
| S3-mask | I | BASE | 各no-ref+原生mask |
| S4-ref | 有point为A，否则I | point的ref任务 | box/mask的ref+原生区域 |
| S4-noref | 与S4-ref相同 | point的no-ref任务 | box/mask的no-ref+原生区域 |
| S5 | 有point为A，否则I | none/point的固定指令 | box/mask的固定指令+原生区域 |

存在point时使用完整共享A，其他公开框/轮廓仍保留；相同区域同时进入原生参数不增加信息。没有point则只给I。native prompt按 `[global,local_1,...]` 用 `$BREAKFLAG$` 连接；global只列none/point任务，local只列对应box/mask，不把local任务重复并入global。存在point时global固定短前导：

```text
U marks select source objects, parts, or attachment points. Remove all marks; keep everything else unchanged.
```

随后追加原样U/颜色/指令行。无point时用BASE，没有global任务时只保留BASE。

box-only regional列表传 `instance_bboxes_xyxy_normalized`；包含mask则传 `instance_masks_yx`，其中box用官方floor/ceil函数量化，mask用官方nearest得到同一绑定网格。**model_size为公共画布 `(Wc,Hc)`，绑定网格为 `(Hc/16,Wc/16)`**。不先把mask变bbox，不人工扩大空区域。

全量 CPU 几何核验发现：3,872 个公开 mask 在约1MP画布上均非空；其中39个单元在 MICE 原生16倍降采样后变为空绑定，影响104条请求（S2-mask/S3-mask各39、S4-ref/S4-noref各9、S5为8）。这属于模型自身区域编码的限制，保留原生处理，不用膨胀或框替换加强模型；后续报告单独标记此类请求。核验记录见 [GEOMETRY_AUDIT.json](assets/current/GEOMETRY_AUDIT.json)。

固定4步、CFG1、`outer_local_prompts`、`apitasmkernelnonlap`、`strict=False`、kernel11、temperature3、sigma.6，binding覆盖全部四步。每个global/local段使用真实checkpoint tokenizer与相同chat模板，确认完整有效序列≤200，且原生512补齐后前200有效IDs与完整序列一致。超限则保留完整输入、记录采样前失败与零新增调用，不截断、改写或扩大原生200预算。

入口：[完整性检查](../src/samtok_benchmark/ifbench/fairness_dev_revision.py) · [原生绑定worker](../src/samtok_benchmark/ifbench/fairness_dev_worker.py)。

## 5. 固定配置与证据

所有生成请求seed=42，每请求只采样一次。源码commit、编辑与planner权重revision、精度、原生参数和组件在 [配置文件](../configs/evaluation/fairness_v2_2_1mp.json) 中固定；实际执行同时保存commit、逐文件SHA、实际调用和 `plan.json`。不在运行中解析为main/latest，不用短测表现改变prompt、步数或模型版本。

当前最小GPU验证固定为K=2/K=5的两张图、S1/S3-point/S5、七模型，共42条请求；CPU输入验证另加入K=4第三图，覆盖210个模型×setting×case组合。固定名单只根据公开K和ID顺序选择；实际完成与图册见[RESULTS.md](RESULTS.md)，不因少量样本成功而声称完整70组合均已GPU验证。

每条逻辑请求保留：公开prompt与资产SHA、公共画布及几何SHA、模型最终调用、实际输入/输出尺寸、raw/output SHA、planner trace、采样seed、真实API/forward计数、终态和实测耗时。小样本图册只从这些实际文件生成；未生成前不放占位图片或宣称通过。

## 6. 统一 Judge 与统计

Judge只看原始清洁源图、去padding后回到原始尺寸的输出、canonical ref、原始GT selector与合法效果契约。它不知道模型名、setting、模型实际no-ref/标记prompt或区域输入形式。同一case的规范目标对所有setting相同。

固定Judge为 `Qwen3.8-Flash-Next-FP8@236dfdf285828023ca3bcd3f37366c58a3469b13`：temperature0、seed0、max_tokens12288、reasoning_effort=low；原始全图证据最多1024²像素，GT局部证据最多512²。TP8/EP、batch16，按模型顺序完成评分。Judge证据缩放属于评分流程，不能把编辑模型的1MP输入当作原始Judge源图。

| 指标 | 定义 | 全量每模型×setting分母 |
|---|---|---|
| E/P/Q | 每项0–4，分别为完成度/保持/质量 | 原子评分；不是通过率 |
| UnitPass（UP） | 每个U满足E=4且P≥3且Q≥3 | 3,872个单元，微平均 |
| JointPass（JP） | 一张图的所有U通过，且global_P≥3、global_Q≥3 | 1,084张源图 |

UP与JP是两个不同层次的通过率，不是两个Judge的分数。95% CI以源图为cluster作10,000次paired bootstrap，seed=20261027；七模型与全部setting共用全局抽样索引。每轮重算抽到图像的单元总数；不能把同图U当独立样本，也不能平均四机百分数或CI。K=2…5桶在各自的全局桶内按图抽样。

对 `M=UP` 和 `M=JP` 分别计算：

| 派生指标 | 定义 |
|---|---|
| 语言依赖度 | `M(S2-m)−M(S3-m)`，m为point/box/mask |
| 区域增益 | `M(S2-m)−M(S1)` |
| 形式鲁棒性 | `min_m M(S3-m)/max_m M(S3-m)`；最大值0时N/A |
| 混合代价 | `mean_m M(S3-m)−M(S4-noref)` |

这些描述当前固定完整方法的表现差异，不自动支持因果结论或模型排名显著性。主表同时报告实际完整分母、已评分数、原生失败和缺分。实现：[canonical Judge接入](../src/samtok_benchmark/ifbench/fairness_dev_judge.py) · [统计定义](../src/samtok_benchmark/ifbench/fairness_dev_report.py) · [全量合并](../src/samtok_benchmark/ifbench/full_report.py)。

## 7. 失败、缓存与真实性

| 情况 | 处理 |
|---|---|
| 原生规划/生成/输入限制失败 | 留完整图与单元分母，计编辑失败；保留异常、实际调用和成本 |
| Judge缺分/失败 | 保留raw/effective及异常，标缺分；不补0、不只报可评分子集 |
| 确定性格式恢复 | 只恢复原回答完整且唯一归属的score/evidence原子；另存overlay，不新增模型调用 |
| started/admitted后无终态 | 可能已采样；禁止自动重试或删除现场 |
| 精确生成缓存 | 输入像素、完整prompt、公共几何、参数、权重、原生配置、实现身份和seed全部匹配才可复用；新增调用记0 |
| 精确Judge缓存 | 原始canonical任务/GT、输出SHA与Judge配置全部匹配才可复用，不能按模型名搬分 |
| N/A | 只在协议不适用时使用；当前七模型十setting都有路径，低分/运行失败不能改称N/A |

不做输出驱动的prompt/坐标修复，不因低分重复采样，不用私有GT擦标记。GT selector paste-back只能另报“诊断”，不称上界；人工标记残留率和κ需要实际独立人工标注。固定抽检材料、额外消融和未完成项在结果页分别标明。

## 8. 安装与运行

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
if-bench --help
```

数据CPU校验：

```bash
if-bench validate-data \
  --manifest data/v2_2.6.0/cases.jsonl \
  --dataset-root /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2 \
  --output /tmp/ifbench/current-data-validation.json
```

安装代码不会下载权重或准备固定GPU环境。1MP公开画布、模型请求与执行必须由当前冻结运行包统一提供；不把通用数据/输入导出命令当作已构建模型执行包。四机共同入口、READY校验、硬件与故障规则见 [FULL_RUN.md](FULL_RUN.md)。

## 当前实际输入图册

[查看十种 setting、每种三个真实输入及最终 prompt](INPUT_EXAMPLES.md)。
