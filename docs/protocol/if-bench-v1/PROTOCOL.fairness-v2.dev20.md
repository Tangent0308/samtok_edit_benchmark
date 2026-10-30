# IF-Bench 公平性协议 v2：已确认的20图dev执行版

用户在完成两图验证后确认本方案，并明确将本轮dev数量从108改为20；授权包含固定方案的dev生成与统一Judge，仍不包含正式冻结或test。

本文件落实用户2026-10-30明确的目标：同一setting提供相同公开区域信息，不使用被评测方法之外的组件转换输入或加强能力，尽可能保留方法自身推理。用户已批准本轮“每模型先固定一套方案、相同2张dev图×10settings、一次采样、不按分数继续搜索”的修订验证，并要求加入FLUX.2 Klein-9B蒸馏版。两图验证现已完成。后续仅执行本文件新增的20图dev范围，正式冻结/test仍需dev汇报后确认。

前置两图验证、实际输入/输出和汇总在 `/tmp/ifbench/fairness_v2_20261030/`。本次20图dev启动包及授权位于 `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v2-dev20-20261030/`，其 `AUTHORIZATION.json`、`selection.json`、`plan.json` 分别登记本次授权、名单和固定请求；真实运行状态见 `results/`。运行期间的pending不能称为通过。旧 `PROTOCOL.revised.md`、dev候选、分数、失败和计算记录保留，不能用新方案重新解释成旧方案的成绩。

## 1. 目标与方法边界

评测对象是完整命名模型/方法在该公开输入下完成任务的表现。Qwen/FLUX使用权重包自带的编码器、扩散模型、VAE和scheduler；RePlan包含其官方TainU规划器；MIRAGE包含其官方解析/定位VLM及区域编辑算法；MICE保留其官方多实例attention。组件清单和实际调用成本必须随结果公布，不能把完整方法的成绩称为裸编辑骨干成绩。

不启用外接SAM、额外grounder、额外语义解释器、独立caption改写器、Qwen PE或FLUX PUP。不按输出人工补指代、改框、改prompt、重采样或选优。官方仓库可选提供某个增强器，不自动使它成为本轮评测核心的必要组件。原生规划中产生的对象理解属于方法自身推理，不能让另一个临时引入的模型代做。

固定模板、公开编号/颜色绑定、坐标换算、公开区域可视化及原生API要求的栅格化属于机械输入适配。不得读取该setting未公开的mask/bbox、对象ref、合法效果契约等来完善编辑输入。确定性不等于语义等价：点不自动表示一个5%硬编辑框，源选择器不自动表示输出对象的目标框。

## 2. 数据、setting与固定呈现

数据仍为既有2.6.0 release；108 dev / 976 test、源图隔离、split seed、S4分配、S5 manifest交互分配全部沿用已确认版本。不得在test上改变输入或参数。前置两个验证case是旧smoke中预先选定的 `v2-sa_10063996`（K2）和 `v2-sa_7414116`（K5且S5含none），不是按模型输出选例。

| Setting | 每单元文本 | 区域信息 |
|---|---|---|
| S1 | 原始ref指令 | none |
| S2-point / box / mask | 原始ref指令 | 相应公开point / box / mask |
| S3-point / box / mask | 原始no-ref指令 | 相应公开point / box / mask |
| S4-ref | 原始ref指令 | 固定的逐单元混合模态 |
| S4-noref | 原始no-ref指令 | 与S4-ref相同的混合分配 |
| S5 | manifest中冻结的ref/no-ref | manifest中冻结的none/point/box/mask；none必须有ref |

区域仍是源对象、部件或新增内容的依附锚点，不是编辑后差分GT或统一的硬编辑边界。所有模型使用同一份公开几何与原文任务；表达形式按实际原生接口决定，不能声称输入像素、内部token数或计算量完全相同。

复用已审查的统一标注：固定五色、U编号、点/框/完整mask轮廓；保留mask洞和断开组件。标注图与清图同尺寸同坐标，当前transform为identity。源图像素被标注覆盖、视觉缩放、原生预处理及标记残留均需披露，不用隐藏mask作清理。

## 3. 每个模型的固定流程

符号：I为清洁源图，A为该setting的统一标注副本，T为该setting的公开原文指令。S1无标注副本，使用I。

| 模型 | S1 | 有区域的S2/S3/S4/S5 | 必须保留的边界 |
|---|---|---|---|
| Qwen-Image-Edit-2511 | I＋T | `[I,A]`＋固定双图说明＋T | 无原生独立bbox/mask参数；区域通过图示提供；不加定位器 |
| Qwen-Image-2.1 | I＋T | `[I,A]`＋同一固定双图说明＋T | PE关闭；mask是轮廓图，不冒称独立inpainting mask |
| FLUX.2 Klein-9B distilled | I＋T | `[I,A]`＋同一固定双图说明＋T | 9B蒸馏版；4步；无外接改写 |
| FLUX.3 Klein distilled | I＋T | `[I,A]`＋固定双图说明＋T，`boxes=None` | PUP关闭；不生成/复制虚构的tgt_bbox；单/多图的官方预处理差异保留 |
| RePlan（Qwen2511） | 原生planner看I和T，再原生编辑I | 原生planner看A和绑定说明；原样response经官方区域编辑接口作用于I | 不手写或修补局部计划；不重复注入global/local任务；这是官方分阶段API编排，不冒称原样单图wrapper |
| MIRAGE（Qwen2511） | 原生逐unit解析、定位I，再联合编辑I | 原生解析原文；定位器看A及该unit公开标记说明；按原生预测框和局部指令联合编辑I | 不外接定位器，不强制原生pair数等于K，不人工补对象语义或修框 |
| MICE（FLUX.2 Klein-4B） | 同一MICE pipeline的global-only路径 | 依模态使用下表规则；原生attention保持默认 | 实际多实例attention不支持双参考图；无原生点定位器，不加外部组件补齐 |

MICE逐模态规则如下，S2和S3共享同一映射，S4/S5按单元组合：

| 单元模态 | 输入与绑定 |
|---|---|
| none | 原始指令进入global文本槽，不造区域 |
| point | 保留真实点标注和U绑定，将原始指令放global文本槽；不生成小框或硬mask |
| box | 原始指令进入对应local槽；使用官方normalized xyxy box API及原生floor/ceil量化 |
| mask | 原始指令进入对应local槽；使用公开二值mask及官方nearest量化 |
| box与mask混合 | 用官方函数将两种公开区域变成同一原生绑定网格，保持逐unit顺序，不引入隐藏轮廓 |

MICE在一张图存在point时使用单张A，其他单元的box/mask信息仍由原生绑定提供；没有point时使用I。点仍被提供，不是discard-region。S1和纯point不会启用实例区域绑定；S4/S5的global与local相互作用受原生attention限制。这些是必须标注的退化/适配路径，不应据低分改成N/A，也不声称它们等于原生点接口。单图标注的像素遮挡和去标记负担须如实报告。

RePlan的planner前导只说明标记的用途与清图编辑关系，不请求额外擦标记任务；原任务、U编号和颜色绑定保留。planner和editor使用同坐标不同图像，原生response、内部框处理和全局/局部分工原样传递。MIRAGE保留官方解析器的原生局部指令生成；新增的只是将当前公开标记说明追加到原生定位消息，包含parent/part裁剪分支，不修改其算法。

## 4. 默认配置与可复现要求

| 模型 | 固定主要参数 |
|---|---|
| Qwen2511 | 40步、true CFG4、guidance1、negative=" "、max sequence512 |
| Qwen2.1 | 40步、true CFG1、output_resolution1024、KV cache开、PE关 |
| FLUX2 Klein-9B | 蒸馏4步、CFG1、max sequence512 |
| FLUX3 Klein | distilled16步、guidance=None、PUP关；safety=False（官方默认），不加载未启用的可选分类器 |
| RePlan | Qwen2511 40步/true CFG4/guidance1、negative=" "；expand0、switch.5；官方planner模板及2048-token生成上限 |
| MIRAGE | Qwen2511 40步/true CFG4、patch ratio .4、官方10px padding；Qwen3.5-9B原生parser/locator及其默认生成设置 |
| MICE | 4步/CFG1、outer_local_prompts、kernel11、temperature3、默认nonlap且strict=False、官方全步binding；画布按官方loader的round规则 |

RePlan的expand0/switch.5来自官方CLI的qwen/qwen2511分支默认。Python方法默认是.15/0，eval YAML还包含其他值，不能混称“唯一官方默认”或作者明确推荐。本轮不比较这些参数。Qwen2.1的1024是固定pipeline默认；README推荐的2K属于不同配置，未因可能提分而追加。

每个完整请求seed42，一次最终输出；多目标由方法原生联合流程处理，不加K次顺序编辑。记录实际扩散forward、规划API调用、batch item数量、原生分支数、墙钟/GPU占用及失败。额外生成预算不能隐藏在预备元数据中，真实调用以运行结果和trace为准。

所有checkpoint与source commit绑定到运行记录。FLUX2固定权重revision `92196c8e11f7b6cf2b7493e037d8c5345c559216`；已下载24个Diffusers文件并核验LFS SHA和大小。其余固定版本、原生组件、逐 setting 输入和官方源码证据见仓库内的[详细评测方式](CURRENT_EVALUATION_ZH.md)及[参数快照](MODEL_CONFIGS.dev20.json)；临时总报告另保留实际图像。为工程运行使用的SDPA替换、原生参考kernel回退、分卡、缓存和预读均须披露，不据此声称数值完全等同另一backend。

## 5. 验证、选择与正式执行门

前置两图验证是用户明确批准的协议修订验证，不是旧dev搜索的隐形第5候选。本次20图dev沿用其已确认的唯一固定方案。历史所有候选、原始失败、分数和GPU成本保留。此次在看到新输出前固定一套方案；两图验证用于检查输入、运行和真实失效模式，不以分数挑prompt，不从两图估计总体质量或改成更容易的任务。

Qwen选择dual的依据是保留清洁源图并采用一致呈现，不能声称它是旧dev按平均JointPass选出的single。single仍可构成另一项合规实验，不因得分高低改变其身份；本轮不再扩展对照搜索。

输入相同且代码、权重、seed、参数和内容绑定均能核验时，复用原输出，新增调用记0并保留原调用来源。新输入不得套用旧分数。原生误定位标签、错对象、漏编辑、标记残留或图像破坏按实际行为保留，不人工改计划或重采样救分。

S2主结果保留区域；discard-region只可作为清楚标注的S1输入复用补充，不用于改选主行。S3/S4-noref及S5无ref单元不得丢弃区域。未支持的路径是否N/A须依据接口和协议定义，不能依据低分决定。MaskFlow仍按用户此前指令暂不纳入本轮。

用户已确认七模型固定方式，并将本轮dev改为20张。原108张dev仍为开发池；按K分层比例、固定seed20261027和SHA256(seed:source_id)排序抽取20张，不查看分数或输出选择。K2/K3/K4/K5分别3/4/11/2图，共72单元。20图所有模型共用；剩余88张仍留在dev，不转入test；原976张test不变。名单、抽样算法、父split digest在共享启动包selection.json登记。

本轮执行7模型×10settings×20图，只有一套固定配置、不再搜索。完全相同的旧生成和Judge输入可在逐条核验后复用，费用和来源分开记录；新输出不得套用旧分数。已有440个完全相同生成结果可复用，另960个请求计划新生成；失败如实保留，不重新采样。

完成20图dev和统一Judge后，汇报完整分数、失败、实际输入与调用账本，再按用户原先要求停在freeze/test前等待确认。20图的CI、K桶和派生指标仅描述这个小样本，不冒称108图或正式test结果。正式freeze尚未生成；验证plan不是正式freeze。

## 6. Judge、统计与结果放置

Judge继续只看源图、实际输出、canonical ref、GT selector及已确认合法效果契约，不接收模型名、setting或输入编码。输出按原规则回到源图分辨率。UnitPass、JointPass阈值、同源图paired bootstrap、95% CI、K分桶及派生指标沿用原已确认定义；前置两图验证没有调用Judge；本次20图dev按同一口径运行Judge并报告真实分数与缺失。

沿用[旧修订协议](PROTOCOL.revised.md)§2、§9及经批准的Judge恢复附录：已声明支持而实际生成/规划失败的请求保留在原分母并记失败，不静默删掉或改为N/A；Judge本身失败保留缺分，不补0、不当作编辑失败、不换一个较容易的子集。没有自动S1、discard-region或裸骨干回退，也没有通用重新采样/补评授权。已有无歧义解析恢复规则可只读应用，但之前13个指定键的一次性Judge补评授权不适用于新请求；新的不完整记录须单独报告原因与处理提案。

模型自身定位器把公开点/标注推理成框，属于完整方法内部推理，须标planner-active和成本。外接†/‡/§增强不在当前公平主表范围；既有PE/PUP等结果只保留为独立历史系统结果。本轮不自动继续外部增强实验。

标记残留需要后续独立抽检；当前样例观察不能充当总体残留率。GT selector paste-back仍仅称诊断，不称上界、不进入主结果。FLUX单/多图分辨率变化、MICEglobal/区域绑定差异等使部分setting差值包含原生流程差异，不能当纯因果效应。

审计、下载临时日志、验证输入输出和报告保留在 `/tmp/ifbench/`；本次跨机器dev启动包与产物使用上述共享 `.ifbench-tmp/` 临时目录；权重按用户明确指定放共享models目录。只有最终确认并冻结后的正式评测产物进入 `experiments2/IF-Bench/`。

## 7. 后续交付与原消融清单的状态

未与用户最新边界冲突的原交付继续保留：完整模型×setting的UP/JP及95% CI、两种口径的派生指标、K=2…5分桶、版本/配置/实际调用与GPU耗时、偏差账本，以及每模型×setting预先随机抽10个case的输入/输出人工抽检材料。标记残留抽检及双人Cohen κ沿用旧§9；没有两名独立人工审查时须明确κ未完成，不能用本轮AI目视代替。前置固定两图图册和本次20图dev示例都不是正式test随机10例抽检。

原§10.1逐项保留状态如下；待另行计划的项不包含在此次20图固定配置dev中，也不能借消融名义修改已固定主配置。

| 原消融 | 当前状态 |
|---|---|
| 双图标记 vs 单图标记 | 旧Qwen候选已有记录，只代表旧配置；新FLUX2及新方案的完整对照尚未执行，须另行登记计划 |
| 可视化标记 vs 坐标文本 | 旧候选已有部分记录；新方案对照仍待另行计划，不按已有或未来test分数改主配置 |
| 轮廓/外扩圈、固定/随机颜色 | 尚未执行；保留为待计划诊断，不扩大此次单方案dev预算 |
| FLUX3 PUP、Qwen2.1 PE、Step1X reflection开关 | 既有PE/PUP结果仅保留历史，不再新增违背用户组件边界的增强行；Step1X尚未进入本轮，须随其完整方法边界另行核对 |
| RePlan/MIRAGE原生框 vs oracle框 | 尚未执行；仅可另列oracle诊断且明确使用额外GT信息，不替换主结果或用于选择主输入 |
| point小框 vs SAM mask | 最新边界下不新增：不以猜测小框代替点，不接外部SAM |
| K次推理模型的顺序随机化 | 用户已暂停未验证联合编辑的方法，本轮不执行串行顺序实验 |
| 标记残留与GT selector paste-back | 继续保留后续独立抽检/诊断；paste-back不称上界、不参与主结果排名 |

附录仍排在主表之后。此前审计结论不自动授权启动与当前组件/联合编辑边界冲突的附录路径。
