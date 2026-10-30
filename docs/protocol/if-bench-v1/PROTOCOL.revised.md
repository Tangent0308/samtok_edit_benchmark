# IF-Bench 分级评测协议 — ifbench-tiered-v1-rc1

**状态：本修订提案的五项推荐已获用户确认；执行ID为 ifbench-tiered-v1。原审计提案版本名保留以便对照。** 2026-10-27。数据release 2.6.0；协议ID与数据版本分开。原文、证据、差异见同目录 `PROTOCOL.original.md`、`METHOD_AUDIT_ZH.md`、`APPENDIX_AUDIT_ZH.md`、`CHANGELOG_ZH.md`。尚未执行候选选择或正式评测。

## 1. 数据、区域语义与隔离

使用远程 `v2branch@6521c8a1daef8a87555c93dea1b156bbab7cbc4b` 的 `data/current.json` 所指 manifest：1084张独立源图、3872单元；K=2/3/4/5分别147/255/597/85图；add980、replace969、remove921、attribute1002。SHA256：`818ce524a1d1f363dc8ea5caa7a887b2dd0355c17a5600d1cbd696cffcf263fb`。

mask是源图选择器：add选择依附点/支撑锚点，其余操作选择源对象/部件。**不是输出差分GT，也不是自动禁止其外一切变化的硬约束。** 合法局部接触、遮挡、揭露背景、边界、光影按私有编辑契约评判。point/box使用release中的冻结几何（半开像素xyxy；point在mask内），经统一几何校验后保留，不为某个模型重新选“更好点”。如重算，必须全体使用同一确定性算法并另存版本。

构建两个独立视图：公共编辑输入只含源图、unit ID、该setting的指令和可见区域；私有Judge输入含canonical ref、源selector mask及合法效果契约。适配器不得读取隐藏的target类别/ref/mask/bbox、completion_requirement、preserve或review来完善prompt、放置标签、选crop或决定编辑范围。数据先统一过滤/审查；不得按某模型输出排除case。冻结后任何标注变更均产生新hash和协议版本。

## 2. Settings与分配

|Setting|每单元文本|公开区域|
|---|---|---|
|S1|全部ref|none|
|S2-point / box / mask|全部ref|所有单元统一point / box / mask|
|S3-point / box / mask|全部no-ref|所有单元统一point / box / mask|
|S4-ref|全部ref|逐单元混合point/box/mask|
|S4-noref|全部no-ref|与S4-ref完全相同的混合分配|
|S5|沿用manifest interaction.has_ref|沿用manifest interaction.locator；none必须ref|

S4用seed=20261027和稳定SHA256(case_id,unit_id,协议ID)生成分配；三模态等概率的确定性映射，若一图全同模态，则按unit ID把最后一个单元循环换下一模态。分配表先生成一次、所有模型共用，保存原始hash/最终分配。K=2只要求≥2种，不要求三种齐备。此S4采样约束会改变边际分布，报告实际计数。

S5不重新随机分配，因为2.6.0已有冻结、近等量的七种合法交互组合（每种553或554单元）。如需新随机S5，必须另命名S5-random，不能称复现原release。

主文至少报S1、S3-mask、S3-point、S5；全部10列均保存并报告。正式主表按相同完整test分母。不能把缺区域的单元移除后称完整S5；已知不支持的setting记N/A，支持但推理失败按失败计入分母。模型/基础环境错误先处理，不以无限次换seed重试寻找好图。

## 3. 指标、统计与解释

每单元E=4、P≥3、Q≥3才UnitPass；UP为所有单元微平均。每图全部单元通过，且global_P/global_Q均≥3，才JointPass；JP按图平均。报告E/P/Q各分数和通过率、global P/Q、操作类型与K分桶、完整性coverage。

`Δ_lang^m = UP(S2-m) − UP(S3-m)`；`G_region^m = UP(S2-m) − UP(S1)`；`R_mod=min_m UP(S3-m)/max_m UP(S3-m)`；`C_mix=mean_m UP(S3-m)−UP(S4-noref)`。JP同样计算。分母max为0时R_mod=N/A；任一setting缺完整同一分母，相关差值N/A，不补0、不换子集。

Δ_lang仅在相同适配/超参/附加组件下解释语言去除差值；G_region在S1规划/S2注入的模型上是完整系统差值，不是纯区域因果增益。C_mix是描述性差值，不证明混用导致损失；另外可报告按S4逐单元模态选择S3结果的matched-unit基线，但不得把单元边际乘积当JP的真基线。caption丢掉ref的模型不声称低Δ_lang代表语言鲁棒。

以**源图为cluster**做paired bootstrap，所有settings/模型共用索引，10000次、seed=20261027、95% percentile CI；每次重新计算UP、JP和派生式。K分桶在桶内按图抽样。记录实际分母、有效bootstrap次数及0分母次数。

## 4. 输入编码与确定性转换

按unit ID序列化，语义统一，允许原生格式不同。普通文本模板为“Apply all of the following edits to the image. Keep everything else unchanged.”加编号原始指令。no-ref使用manifest已有文本，仅允许已声明、无新增对象语义的固定词法替换。

双图模板明确第1图是原图、第2图是标记副本，只编辑第1图并不保留标记；单图模板要求按标记编辑并移除标记。单位颜色固定红/蓝/绿/黄/品红，颜色+编号在prompt中绑定。点半径 `max(1,round(.01*min(W,H)))`，白外环；box线宽与mask线宽 `max(1,round(.004*min(W,H)))`；mask绘制所有外边界、内洞、断开组件，不填色覆盖目标。颜色RGB值、字体文件hash、字号、round实现、边缘裁剪和标签冲突算法在builder规范中固定；不能依赖系统随机字体。标签只根据该setting公开几何放置，不使用隐藏bbox找“区域外”。所有边界/标签必要时置于固定外侧页边并记录图像坐标变换。

|转换|规则|信息/标记|
|---|---|---|
|mask→box|非零像素紧外接框，max坐标+1|确定性但有损，记录lossy=true|
|box→mask|半开矩形栅格化|不能恢复物体精细轮廓|
|point→小框/矩形mask|边长短边5%，由点坐标确定、边界clip；不能读隐藏mask定尺度|确定性，记录转换；不称推断出完整对象|
|point→SAM|统一且冻结具体SAM2-L仓库、revision、配置；单个正点，按预测分最高取mask，固定tie-break|†，只补充；本轮未安装/选择SAM配置|
|none→额外grounder/输出范围规划|统一冻结外部模型与模板，只看公共图文|‡；串联外部分割可†‡|
|指令→caption|只从公共操作/负载与允许图像输入生成；冻结规则或同一改写模型/缓存|§；无ref不能从私有描述补语义|

原生规划器属于完整方法，可不标外部‡，但必须标 `planner-active`、保存预测区域；不是确定性转换。源图本身对所有模型公开，方法从图像推断不是额外oracle，但带来模型先验与计算差异。轮廓图与原mask不宣称信息完全等价。

坐标文本只是明确标注坐标系的普通文本候选。已知原生接口按源码约定换算；未知接口禁止把dev选出来的格式称“编码器原生约定”。xyxy与yxyx、[0,1]/[0,1000]/像素不可混用；拒绝NaN、逆序、越界，保存源画布到模型画布变换。

## 5. Dev、候选预算、冻结与执行门

108张dev、976张test，按源图/family隔离，固定seed=20261027。阶段1查看/试跑的case必须进入dev（`checks/data_audit.json`列出的两图），再对剩余source ID按SHA256排序补足108；实际名单已在获批共享输入中冻结，split digest为`d9062861e8d719988ed360b305ae158f7566109800349b707ef6ec4685a31594`。披露旧协议已经全量评过，不能宣称这些图从未用于研究观察。

每模型最多4个**完整配置**；输入编码、坐标格式、strength、扩张策略及PE/PUP/planner开关的组合均计入这4个，不做额外笛卡尔积。受控行与另报的官方推荐流程共用此预算；固定官方推荐配置也占一个，单列结果不产生额外免费搜索名额。不要求人为凑满4个；报告实际候选数、有效运行数、GPU秒。每个候选/setting/case只生成一个最终输出、固定基础seed=42；串行unit seed用固定SHA256(42,case_id,unit_id)派生，跨paired settings保持一致。reflection内部多尝试保留原生语义并单独计数，不按“1输出”隐去计算成本。

一个候选是从模态到输入形式的完整映射，S2/S3共享同一映射，S4/S5组合规则也包含在配置中。以预先约定的适用settings上dev平均JP选择一次；适用集合对该模型所有候选相同；平分按预注册优先级（原生官方格式、较少调用、候选ID）决定。选择前保存候选清单，选择后保存freeze.json，包括所有代码/权重/数据/分配/模板/seed/预处理/Judge版本。test不再改选。

S2主配对行必须保留区域。允许另报S2-best-adapted：dev在同一预算内比较保留区域与S1输入；如果选S1，明确discard-region=true。这个优化行不参与Δ_lang/G_region主解释。S3/S4-noref不得丢弃区域；S5也不得丢弃no-ref的唯一定位信息。S4-ref如另做fallback，同样单独命名。

执行顺序：用户确认本协议→补齐环境及必要的1–2例接口验证→构建公共/私有输入隔离与几何检查→冻结split/分配/候选→dev选择→冻结全部配置→主表完整test生成→同一Judge→严格完整性报告→可选和附录。没有确认不得进入dev或test。

## 6. 主表与可选模型配置

|方法|默认候选/协议修正|官方配置依据与本协议决策|
|---|---|---|
|Qwen-2511|S1 I；区域默认[I,A]，候选A、显式坐标；mask不能只画最大外轮廓|2511权重，40步、true CFG4、guidance1、negative=" "；记录50步函数默认与40步card推荐的区别|
|Qwen2.1|默认[I,A]；A为候选；M_vis仅在确切编码/绑定验证后纳入|基础2.1权重，40步、CFG1、output_resolution1024；主受控行无PE，官方PE-I2I推荐流程另报；Turbo另行|
|FLUX.3 Klein|`obj_i`/`ref_image_0`，正文引用id，bbox输入归一化yxyx；add编码源锚点，不造输出框；第二张A保留点/形状为候选|distilled16步、guidance=None；主受控行PUP关闭（偏离推荐），PUP开启完整流程另报；10图上限；记录单/多图预处理差异|
|RePlan Qwen2511|S1原生planner；box/mask注入真实尖括号response；point受控行小框；native-planner点定位作为独立候选/补充；S5公共文本规划无区域单元后严格合并|40步、trueCFG4、guidance1、negative=" "；直接调用显式expand0/switch.5；planner用TainU专用权重|
|MIRAGE Qwen2511|写全局与区域两份JSONL；有ref且给定区域的refer_object从当前公开指令确定性提取，必须是原文连续片段，歧义待核，禁止读取私有spec.ref；无ref为the selected region；point受控小框；S1及S5缺区域部分调用原生VLM|40步、trueCFG4、patch .4；给定与预测框均显式10px padding（预测框不重复padding），再走官方最小crop/context逻辑；记录VLM实际调用数|
|MICE 4B|精确`$BREAKFLAG$`；mask和normalized xyxy恰选一个；S4全部转mask；S1 global-only退化；S5 global+regions扩展已在完整任务冒烟跑通，质量仍待dev，不截断任务|4步、CFG1、outer_local_prompts、kernel11/temp3、block0:5/0:20、全步binding；不调用会重写所有操作为replace的原dataset builder|
|MaskFlow|单mask、K次；no-ref保留selected region或固定masked region；selector-as-edit-mask限制显式披露；S1/S5缺区域无直接CLI路径|Qwen2511+latest.safetensors固定HF revision，50步/textCFG4/maskCFG1，原生25膨胀/25模糊与Poisson/pixel blend；不二次GT回贴|
|可选FLUX.2-klein-9B|默认双图，候选单图|蒸馏4步/CFG1，不用函数默认50/4；base-9B另行|
|可选QwenImageEditInpaint|原生单mask、K次；明确旧Qwen-Image-Edit权重|strength .6、50步、trueCFG4；若选.8/1计入4候选预算；latent blend保留|

所有具体源码与权重SHA见SOURCE_INDEX.md。本表配置已在7个主表方法上完成冒烟，但不等于通过质量验证。MICE S1/global-only与S5/global+regions均保留完整任务并已跑通；MaskFlow S1/S5仍N/A，不用较小分母或backbone fallback补一个可比的数字。所有退化/扩展路径须明确命名。

受控主行与官方推荐流程都重要：Qwen PE、FLUX PUP关闭帮助检查输入适配，但不能据此声称评出了官方最佳性能；如要作SOTA方法优劣结论，必须同时给推荐原生流程。它们只访问公共输入，并记录生成文本和计算量。

## 7. 多单元、融合与几何

单输出方法一次联合请求；多分支实际网络调用单独统计。单区域方法按固定U1…UK串行，下一步输入为上一步输出；在统一画布坐标链上使用冻结源选择器，不偷偷用模型/GT跟踪已经移动的对象。附录随机顺序诊断的seed和次数预先固定，不能用其中最好的输出作主结果。

保留各方法原生融合：MaskFlow pixel/Poisson、Qwen Edit Inpaint latent blend、Flux2KleinInpaint latent blend、PowerPaint所选分支的真实返回流程（普通分支raw、controlnet分支paste）。BrushNet示例blended=False；若启用则属于显式适配选项。取消“没有融合就必须额外回贴”的统一规则；外加回贴只按当前公开区域的确定性范围操作并单列配置，禁止point/box行取隐藏mask回贴。

选择器范围限制新增/扩张时须按操作报告，不把小框低分简单称为不能读点。候选可包含固定比例扩张，但不可通过GT输出或test逐例调大小。每个单元保存实际输入/有效编辑mask/几何变换，最后先反pad/crop再resize到源图；mask缩放用最近邻，连续图像用冻结插值方法。

## 8. 附录模型（主表完成后执行）

Step1X v1.2使用官方fork与v1p2权重，50步示例、guidance6、size1024；thinking+reflection开启为推荐行，关闭作为消融，报告最多3次尝试。LongCat Edit 50步/guidance4.5。BAGEL单图及官方interleave多图为候选，固定think，50步，text/image CFG按调用层明确填写。OmniGen2代码默认28步/4/1与README推荐50步、编辑image guidance1.2–2.0不同，建议冻结50/4/1.5并披露。Hunyuan完整Instruct用50步、think_recaption、最多3图；Distil8步另行，不能缩短reasoning预算后冒充推荐配置。

HiDream full允许多参考图，默认50步/guidance5/约4MP；dev单参考分支有专门scheduler，不把这一条件写成所有编辑只能1图；单图A、双图[I,A]候选须在同一checkpoint/scheduler策略下冻结。GoT必须生成完整got_input token语法及0–1000框，不能只注入JSON；padding作为适配记录。TAL只纳入S1单元顺序编辑；不给task_type时的默认行为和手工操作映射须明确记录，不额外提供私有语义。

FLUX.1 Fill、BrushNet、PowerPaint、InstantX、BrushEdit主要需目标状态caption§，不是直接指令替代。InstantX官方推荐全图描述会增加prompt改写需求；只能从公共输入产生，所有caption适配记录是否丢失ref。BrushEdit整体具有VLM/定位流程，S1若用它必须命名完整方法，不可与跳过VLM的BrushNet内核混为一谈。GoT/TAL不适用“所有第8节方法都是K次单mask”的总括。

各方法具体修正、依赖与待核项见APPENDIX_AUDIT_ZH.md；附录本轮只静态核对，没有运行大模型。

## 9. Judge与残留诊断

固定Qwen3.8-Flash-Next-FP8的权重revision、推理环境、温度0、seed0、rubric与图像证据构建版本。Judge只看源图、输出、canonical ref、源mask和私有合法效果契约；无模型/setting/候选名。复用旧judge必须证明输入/输出/rubric所有digest一致，本协议默认重新构建，不混用旧visual_locator_v2的分数。

标记残留率：预先抽样并人工判断输出是否出现颜色轮廓、数字标签、框/点；把自然红蓝物体与标记区别，不用简单颜色阈值代替真值。标记诊断与主评分独立；若输出可见标记，元数据盲测仍不能保证Judge无法猜测模式。随机分层样本按K、操作、模型报告，两名独立人工审查者计算二分类Cohen κ；如只完成AI检查，标明人工κ未完成。

GT mask回贴仅作`oracle_selector_pasteback`诊断，既可能提高P又可能伤害合法add/replace，不叫上界、不参与排名。主结果使用未经额外GT处理的真实输出。

## 10. 实验产物与开发组织

仓库展示名IF-Bench，旧 `samtok_benchmark` 模块路径暂保留以兼容旧代码；协议实现完成后增加新入口，不覆盖历史release的旧CLI语义。文档在 `docs/protocol/if-bench-v1/`，审计工具在 `evaluation/protocol_audit/`。

正式结果根：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/IF-Bench/`。只有用户确认协议且最终配置冻结后，正式评测才写入 `tiered_v1_<冻结日期>/`，包含冻结协议/配置、正式输入输出、Judge记录、正式运行日志和报告。每个配置和setting独立路径，配置digest不匹配时拒绝续跑；记录正式任务失败、拒绝、超时，不静默跳过。

审计、源码快照、临时下载、连通性样例、试错、dev候选搜索、调试日志与非正式可视化全部输出到 `/tmp/ifbench/`。当前阶段1目录为 `/tmp/ifbench/protocol_review_20261027/`，预览在其 `previews/`。dev候选输出不进入experiments2；只将最终选定配置及必要的选择摘要纳入正式freeze记录。配置冻结后的正式任务日志属于正式评测产物。

本条遵循用户2026-10-27的新目录要求，取代本任务此前将审计材料放experiments2以及预览放visualization_tmp的安排。仓库保留协议文档和开发代码，运行产生的检查JSON放临时目录。旧协议原文和历史日志保留原字节，历史绝对路径通过迁移记录追溯。

## 11. 许可证与原未验证项

代码与权重许可分开冻结；门控访问成功不代表许可审查完成。MICE/TAL仓库许可证缺失的结论须以指定tree为界，缺失不自动视作Apache。Qwen2.1 Research、FLUX.2-9B/FLUX.1-Fill非商用条款、FLUX.3 Kommunity的条件商业条款、Hunyuan（EU/UK/韩国）与BrushEdit（EU）地域限制分别记录。删去“学术评测注明即可”的自动授权句；不发布未经确认许可的模型权重。

原四个未验证项：Qwen2.1多实例独立mask仍待确切模板验证；FLUX.3新增内容src=null已确认但须遵守源锚点语义；MaskFlow占位符方向修正；BAGEL维护者多图示例已找到，但标记编辑效果尚待dev。运行状态详见RUNTIME_ZH.md，任何尚未跑通的方法不得写“已验证可复现”。

## 12. 阶段边界与仍需用户确认的决策

本提案建议：保持现有数据与S5分配；主表以完整分母评分；采用受控输入行并补充官方推荐流程；将selector与硬编辑范围区别写入表注；S2丢区域另列；禁止GT回贴上界；按源图冻结108/976；四个完整候选上限。

用户确认后才实现/冻结最终评测runner并进行dev/test。确认可以指定上述推荐的替代方案；在确认之前不以任何“默认同意”启动阶段2。未知接口与权限有真实阻塞时按方法标注，不能伪造完成。

用户确认后的执行补充：共享输入完成节点已获确认；用户随后取消逐模型暂停，要求连续完成全部主表方法冒烟并统一汇总问题和推荐输入；dev选择完成且冻结之前仍须停下汇报、等待确认。S2候选必须包含丢弃区域，但它只进入best-adapted补充结果；主配对结果保留区域。原协议§10.1的全部消融保留，paste-back按再次确认的“诊断”命名。详细追踪见EXECUTION_STATUS_ZH.md。


### 2026-10-28 用户确认的执行范围更新

用户要求暂不评测未验证一次性多目标编辑的方法。当前 MaskFlow 串行适配退出本轮，其既有临时结果不作为主表/补充成绩，也不记失败或 N/A；保留历史审计及输出以便追溯。当前主表运行六个其余方法，保持原 split、候选、seed 和 Judge 口径。单 mask 接口不等于不能联合编辑，MaskFlow 联合输入仍未验证；本次暂停不是对其联合能力的否定结论。范围覆盖记录见 `dev_selection/scope.json`。


## 执行补充：经批准的Judge格式恢复（2026-10-29）

用户已批准对dev首轮失败进行确定性恢复并完整分析。此补充不改变编辑输入、Judge视图、canonical指令、权重、阈值、采样seed或模型调用次数。原始记录保持只读，新增版本化overlay并逐条绑定原记录SHA256。只读取最终回答中完整的score/evidence原子；有明确标签与唯一unit归属可恢复结构；单个无标签原子且恰缺一个维度可补该字段名；同字段重复且数值一致时保留每段原证据。pass严格由E=4、P/Q/global≥3派生。拒绝任何冲突数值、缺失score/evidence、多维度无标签歧义、条件表达式或借其他unit/global/思考段补分。全部原文span和恢复规则留档。

无法恢复的Judge保留缺分，不计编辑失败、不补0、不替换评测子集。数学取值界仅用于敏感性分析，明确不是实测分数或置信区间；完整分数与候选冻结审批要求不变。新增Judge补评不包含在本次确定性修复授权中，需另行确认并保留所有首轮结果。实现与产物见EXECUTION_STATUS_ZH.md及judge_repair_v1/policy.json。


### 经批准的13条一次性补评

用户已另行批准对最终13条无法确定性恢复的dev Judge键使用原canonical输入各新增一次评分（最多13次）。清单由PROPOSED_REJUDGE_13.json固定并由授权SHA绑定；图像输出、canonical指令、GT视图、模型权重、解码参数和seed保持不变。保留全部首轮及修复记录，只使用本次唯一有效回答；不得在多个有效回答间择优。若本次仍无效，继续保留缺失，不自动增加调用。仍须完成候选汇报并在freeze/test前等待审批。


### 2026-10-29：13条补评完成，完整dev选型待冻结确认

获准的13个key已各补评一次：12条canonical直接有效，1条按同一确定性规则恢复；共13次新增Judge调用，编辑生成和校准均0。当前11179/11179有效，180/180候选×setting完整。原11179首轮记录与196修复层记录hash全部不变；独立复算180行UP/JP及18候选均JP/10000次paired-bootstrap CI一致（浮点差<=1.12e-16）。旧3条生成/planner失败仍保留在分母，未重试或删掉。

最新图文入口/tmp/ifbench/tiered_v1/dev_selection/judge_rejudge13_v1/REPORT.html（52幅内嵌图），全部统计analysis/REPORT.html，补评逐条证据REJUDGE_AUDIT.html，建议配置analysis/PROPOSED_SELECTION.json。主配置建议：Qwen2511 single、Qwen21 single、FLUX3 native-annotation、RePlan/MIRAGE/MICE native。S2 best-adapted补充选择discard：Qwen2511 point/box、Qwen21 point、MIRAGE point、MICE point；Qwen2511 mask同分保留区域。非S2 discard候选行只是首个主候选原请求复用，S3/S4-noref没有丢弃区域。PE/PUP仍单列补充。

LATEST_REVIEW.json和REVIEW_REQUIRED.json发布有效状态与待审批提案；旧监控/逐模型入口已指向新报告，原始状态归档judge_rejudge13_v1/historical_status。仅停止本任务已完成的CPU observer，未动无关GPU进程。尚未freeze、未启动test、正式experiments2未写入。用户此次“同意”只授权13次补评，不能据此跳过预先约定的dev选型冻结前确认。人工残留率/κ、GT selector paste-back诊断、未执行消融、正式抽检和完整GPU占用统计仍属后续交付，不声称全部benchmark已完成。
