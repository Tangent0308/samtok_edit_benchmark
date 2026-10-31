# 阶段 2 历次执行与确认记录

> 本页为按时间追加的历史记录，早期“当前状态”仅指当时节点。当前有效方式见 [详细评测文档](CURRENT_EVALUATION_ZH.md)和[20 图 dev 协议](PROTOCOL.fairness-v2.dev20.md)；实时进度见[启动指南](DEV20_RUN_ZH.md)。历史 PID 与计数不能用于判断当前作业。

阶段1五项推荐、共享输入均已获用户确认。用户确认paste-back按GT selector诊断报告、不称上界；取消逐模型冒烟暂停，要求全部主表方法测试后统一汇报。所有非正式产物在`/tmp/ifbench/`；experiments2只接收最终冻结后的正式评测产物。

## 冒烟节点状态（历史）

7个主表方法冒烟完成。固定3个dev case × 10 settings：204个主路径输出、12个备选输出，MaskFlow S1/S5共6个N/A；生成失败0。实际扩散API调用264次，原生planner调用17次（RePlan 4，MIRAGE 13）。这些是完整性/资源计数，不是质量评分。截至该冒烟汇总节点尚未执行Judge、dev选型、test或冻结；后续启动授权见本页末尾。

[统一图片报告](/tmp/ifbench/tiered_v1/smoke/SUMMARY_REPORT.html) · [Markdown](/tmp/ifbench/tiered_v1/smoke/SUMMARY_REPORT.md) · [机器汇总](/tmp/ifbench/tiered_v1/smoke/SUMMARY.json) · [无重复采样检查](/tmp/ifbench/tiered_v1/smoke/duplicate_check.json)。详细报告逐模型展示10个setting的全部固定样例、实际最终prompt、原生参数、mask和输出；HTML图片内嵌。报告中的原生区域彩框为示意图，不是模型收到的额外图像。

共享公共输入仍是适配器唯一数据来源。[共享输入审核包](/tmp/ifbench/tiered_v1/shared_inputs_20261027/index.html)已获批准。当前只冻结split/区域分配；模型输入方案尚未冻结。正式结果目录保持空。

## 阶段门

|节点|状态与交付|继续条件|
|---|---|---|
|1 共享输入|全部10个setting，各3个实际输入样例；已获确认|已满足|
|2 全模型冒烟|7个主表方法完成，统一问题和推荐报告已生成|用户取消逐模型审批；定性建议不代替dev选型|
|3 dev选型、冻结前|尚未开始；须报告每模型所有候选JointPass、完整性、推荐选择及S2丢区域选择|仍须停下等待用户确认，之后才冻结并进入test|

每模型≤4个完整配置，PE/PUP和其他适配开关共同占预算。S2丢区域候选属于best-adapted补充结果，主配对保留区域；S3/S4-noref不得丢区域，S5不得丢单元。可选两方法未进本轮主表冒烟，附录仍在主表正式评测完成后执行。

## MIRAGE公开ref字段修正（已确认）

用户明确选择“从公开指令确定性提取目标短语（推荐）”。有ref且给定区域时，refer_object只能是当前公共instruction的连续原文片段；不读取私有spec.ref，提取不明确的请求待核。S1/S5缺区域保持原生planner。确认记录：[/tmp/ifbench/tiered_v1/smoke/mirage_ref_policy.json](/tmp/ifbench/tiered_v1/smoke/mirage_ref_policy.json)。9个固定样例单元已逐一验证原文span，完整dev语法覆盖尚未验证。旧15个零推理blocked记录已归档，之后补齐，没有重跑成功输出或测试selected-region替代方案。

## 运行边界

RePlan原生planner使用SDPA替代本机缺少的FlashAttention2；当前Torch/Transformers版本与部分上游依赖不同，已在报告披露，不宣称数值完全等价。MICE完整S5所有单元已路由并生成，但质量仍待评。MaskFlow的S1/S5保留N/A，不以骨干回退补图。所有输出恢复源图尺寸；MaskFlow保留逐步原生输出、有效mask与反裁剪记录。

## 原协议§10.1消融追踪

|项目|执行口径/当前状态|
|---|---|
|双图 vs 单图|共享构造已提供；模型适用性与真实效果留dev/补充实验|
|可视化 vs 坐标|共享构造已提供；mask→坐标框会丢形状，显式记录，不冒称完全等价|
|轮廓 vs 外扩圆圈；固定 vs 随机颜色|保留为后续baseline消融；不用于未注册的额外配置搜索|
|FLUX PUP / Qwen rewriter / Step1X reflection|保留官方推荐对照，记录真实额外调用；主表rewriter关闭，内置流程按已审定配置|
|RePlan/MIRAGE原生规划 vs 给定区域|保留补充对照；原生预测不叫确定性转换|
|point小框 vs SAM†|小框共享构造已实现；SAM仅补充，尚未运行|
|K次推理随机unit顺序|后续固定seed诊断；不能挑最佳顺序作为主结果|
|标记残留与paste-back|残留率与GT selector paste-back诊断；用户已明确不用“上界”名称|


本文件不填任何未运行分数。后续按dev候选选择、冻结前审核、正式test和统一Judge顺序推进。

## Dev选型启动授权

用户以“我确认，开始。”明确授权继续dev选型。候选清单已预登记：[/tmp/ifbench/tiered_v1/dev_selection/plan.json](/tmp/ifbench/tiered_v1/dev_selection/plan.json)；[动态进度及实际图片](/tmp/ifbench/tiered_v1/dev_selection/PROGRESS.html)。所有108张dev图、10个setting使用同一公共输入包，候选选择/冻结规则不变。

MIRAGE的公开短语预检查发现48条未被最小样例语法覆盖的指令。已扩展确定性文本规则处理finish、Tint、源对象with修饰及add的既有支撑点；386个dev单元均返回可逐字验证的连续原文片段，不读私有ref、不观察编辑结果。规则hash与全部span保存在`ref_span_inventory.json`，该规则版本在dev生成前固定。

新Judge独立构造canonical视图，不沿用旧runner泄漏actual_instruction、editor_interaction、variant的prompt。运行环境、验证日志和完整后台状态见临时目录。此处记录启动授权，不表示dev评分完成；下一次必须停下的节点仍是全部候选分数汇报后、冻结之前。


### dev 后台队列已启动（2026-10-27）

统一 canonical Judge 三例验证均成功解析为 scored；实际环境和证据绑定记录见 `/tmp/ifbench/tiered_v1/dev_selection/judge/current.json`。后台 controller PID 3807393，启动状态 generation-running，任务记录见 `dev_selection/orchestration/jobs.json`，自动图片报告见 `dev_selection/PROGRESS.html`。完整 dev 生成及评分完成后停止在冻结前；尚未启动 test，正式实验目录为空。


### 动态 GPU 接力已启用（2026-10-28）

用户要求加速后，新增 `dev_balancer.py`：未来启动的 dev_runner 作为调度进程，根据实际耗时估计的剩余工作量和活跃副本数分配空闲 GPU，独立子进程保留对应模型原环境。正在运行的 8 个生成进程未被中断、重启或发送信号。候选、输入、参数、seed、任务锁与失败处理不变。分配记录与代码快照位于 `/tmp/ifbench/tiered_v1/dev_selection/engineering/balanced_queue/`；旧 controller 的 jobs.json 标签仅代表初始调用，动态子任务以 worker/assignment 记录为准。3 项调度测试通过。当前时长模型预测剩余生成从约 32.1 小时降至约 28.4 小时；这是规划估算，尚不是实测加速比。Judge 的三例试跑不能代表正式 batch=16 吞吐，首次正式评分后更新耗时预测。


### MaskFlow 单 mask 与串行适配的区分（2026-10-28）

复核官方 commit 3125f1ecd72f5a4e068c5a1954e9d6a8df38d443：一个样例输入一张源图、一张空间 mask 和一个 prompt；此路径未要求 mask 只有一个连通区域，也未提供多个 mask 与多个指令的原生逐项绑定接口。因此“必须逐目标串行”不能作为官方接口结论。U1…UK 串行是已确认协议的适配选择。并集 mask + 复合指令可构造成单次调用，但并集本身丢失区域到指令的分组绑定，尤其影响 no-ref；质量尚未验证。新增联合候选需作为协议/候选变更处理，当前继续原已批准运行，不替换或重采样。证据记录：`dev_selection/engineering/maskflow_joint_interface_clarification.json`。


### MaskFlow 暂缓，三张卡已转给 Qwen-2511

已停止 MaskFlow PID 3807476、3807483、3846766，其他五个在途生成进程保留。新 supervisor PID 4032862 接管它们；GPU 4、5、7 由动态调度新增三个 Qwen-2511 副本。当前六模型登记物理请求 12528，MaskFlow 全部 1080 个物理任务及对应别名从执行/评分视图排除，原 plan.json 保持不变。历史控制器记录保存于 `orchestration/before_maskflow_deferral/`。因用户停止产生的半成品不计运行失败。修改通过 7 项范围/调度/协议测试。


2026-10-28：用户已要求后台定期监控。独立只读监控 PID 4164429，每60秒检查、每600秒保存常规快照，异常/状态变更即时留档；输出 `/tmp/ifbench/tiered_v1/dev_selection/monitor/REPORT.html`、`latest.json`、`history.jsonl`、`events.jsonl`，源码 `samtok_benchmark/ifbench/dev_monitor.py`。监控不改评测、不重采样；生成ETA使用实测耗时与动态GPU调度模拟，Judge正式batch>=16至少32条记录后才给评分ETA；冻结前审核到达后自动结束监控并保留最终报告。


### 2026-10-29：PE 补充请求失败后的恢复

2026-10-28 12:22:31 UTC，Qwen-2.1 official-pe/S5/v2-sa_6720037（此前已记录 PE 截断及官方解析回退）在 CUDA vectorized_gather 处报告索引越界并触发模型暂停。具体异步故障算子尚未确认，不能将超长文本直接写成已证明根因。其他方法继续完成，21:11 UTC 调度器因剩余290条请求未运行而退出。监控12:22:38即记录暂停，但仅写本地文件，没有聊天推送；用户询问后才人工检查恢复。

已核对剩余290条均未开始、均为正常解析的PE缓存。保留原失败及全部已生成结果，归档 PAUSED 并启动新进程，仅继续未执行请求；不改prompt/参数/seed，不重跑失败。恢复调度器PID 200038，8卡并行Qwen-2.1，首批已实际出图。证据与旧控制器记录在 `/tmp/ifbench/tiered_v1/dev_selection/engineering/recovery_20261029/`。生成完成后仍自动进入统一Judge，再停在冻结前。


### 2026-10-29：Judge 连续调度优化（用户已授权）

新增 `dev_judge_stream.py`，复用未修改的 canonical Judge 输入、原始 prompt/chat template、解码参数和严格评分解析。4 个 CPU 线程预取最多64份证据；引擎维持8卡 TP/EP，最大并发容量32，请求完成立即持久化并补入后续请求。16/32并发使用固定32份已评dev输出做性能校准，校准原始回答仅存在临时 execution/calibration 目录，不覆盖或参与dev候选分数。按耗时选并发，不按评分选；额外96次Judge调用独立计入执行记录。批处理差异可能影响FP8数值与回答，比较记录会如实披露，不声称逐token等价。

原调度在912份评分全部落盘后停止，其中893条成功、19条Judge格式失败。完整旧记录hash及进程交接证据：`/tmp/ifbench/tiered_v1/dev_selection/engineering/judge_stream_20261029/`。旧子进程退出超过最初20秒等待，随后自然退出，未强杀在途请求。新进程PID255776，目前处于验证/加载/校准阶段；完成校准后只继续未评分的请求。异常格式处理规则未修改，Judge失败不当作编辑失败，仍阻塞冻结。

基础 `judge/<run_id>/config.json` 保留原批处理配置；新的实际调度参数、源码快照、校准调用和每条新结果通过 `executions/*/receipt.json` 及 `execution_receipt` 字段关联，不冒称新调度仍是原batch16配置。启动时核对原canonical指纹及所有输出绑定；已有记录不覆盖。新增 admitted 日志使重启时遇到已提交但无回答的请求停止核查，不自动再次采样。SIGUSR1只停止提交新请求并排空在途请求。结束后仍停在冻结前审核。

监控进程已重启为PID254672：连续调度积累至少33条新结果后才重新按完成速率估计ETA，计入预处理与落盘开销，不继续使用旧batch时间推算。图文报告位置不变，仍仅本地文件监控，没有会话推送。


Judge连续调度首次校准出现已定位的vLLM0.31接口适配错误：enqueue返回内部随机化ID，step输出外部ID，原映射触发KeyError。错误发生于隔离校准，原912条评测记录hash重新核验无变化，production submitted=0。已改为通过output_processor.request_states读取显式external_req_id映射，新增回归测试，11项测试通过。旧执行记录保留：32次完成的baseline调用和16次中止/未持久化的stream校准调用共48次；其中15条由engine shutdown明确记为aborted，首条因ID映射错误未保存。新的PID266912继续校准，复用已完成baseline，不覆盖评测记录；余下两种调度各32次额外调用独立记录，最终总数以各execution receipt与submissions为准。新日志orchestration/031-canonical-judge-stream.log。


### Judge调度实测结论与恢复（2026-10-29）

同一组32份dev输出：batch16=211.373秒（545.007项/小时）；continuous16=381.815秒（301.717项/小时）；continuous32运行427.536秒时仍0/32完整返回，已中止隔离性能试验，不把该时间冒称完整耗时。旧GPU批处理策略更快，故最终采用8卡TP/EP、引擎上限16、每批16请求、4线程预取最多两批图像。所有校准均不进候选分数；共112次额外Judge请求，其中64份完整回答、48份中止或未持久化，按execution记录归档。性能试验的引擎容量上限为32，batch16基线实际提交16；恢复评分引擎容量回到原16。

中止校准后遗留的EngineCore267750与8个worker仍占显存，导致一次恢复启动失败（未提交评分）。已根据记录的PID、父子关系和启动时间定向清理，证据 `engineering/judge_stream_20261029/orphan_cleanup.json`；无关GPU进程未动。原912份评分hash再次确认未变，未重跑已评分请求。当前恢复进程PID278315，日志 `orchestration/033-canonical-judge-prefetch.log`，额外校准不再重复。13项协议、调度、输入映射和监控测试通过。

当前只读监控PID275781。预取批处理ETA使用完整墙钟耗时，避免一批16条同时写入导致早期速度被夸大。实测报告（内嵌3组既有dev图像）：`/tmp/ifbench/tiered_v1/dev_selection/engineering/judge_stream_20261029/REPORT.html`。恢复评分与实际批间等待仍待新记录验证，不能宣称已取得全流程加速倍数。


2026-10-29 05:44 UTC恢复验证通过：PID278315的8卡TP/EP、引擎上限16、每批16+4线程预取已新增32条成功评分，总计925 scored/19 judge-failed，原912条hash全部不变。两次批间准备等待2.87/5.97毫秒；旧56次非推理间隔中位数9.18秒。新首32条完整墙钟169.42秒，约679.96项/小时；样本不同，不宣称严格加速倍数。切换、隔离校准及重载造成约48.5分钟无新dev评分落盘，一次性成本如实记录。证据engineering/judge_stream_20261029/production_verification.json，图文REPORT.html已更新。继续未完成dev Judge；19条原格式失败不补分、不重试，冻结/test门槛不变。


### 2026-10-29：用户授权逐模型Judge与并行subagent报告

用户要求先完成一个模型的Judge再进入下一个。已核对去重请求顺序为qwen2511(2756)→qwen21(3131)→flux3(2596)→replan(812)→mirage(808)→mice(1076)，并新增batch group_key约束，尾部不足16也不与下一模型混批。CPU可提前读取后续图片，但GPU请求必须逐模型完成。新测试覆盖模型边界和短尾批；8项Judge调度测试通过。通过SIGUSR1排空旧进程、核验全部已提交请求有结果并确认原worker全退出/8卡显存释放后交接，保留1616份评分。当前Judge PID319362，日志orchestration/034-canonical-judge-model-serial.log；已实际提交新16条且全部qwen2511。未重复校准，未改评分、prompt、模型参数或seed。交接证据engineering/model_serial_20261029。

三个subagent已分组准备六模型图文核查报告，全部图片base64内嵌，目录/tmp/ifbench/tiered_v1/dev_selection/model_reviews/{model}/，入口INDEX.html；不得将未齐Judge分数称为最终分析。完成触发服务dev_review_queue PID324381每60秒读取真实Judge记录，写STATUS.json；某模型pending=0才写trigger.json。judge_attempts_complete与score_complete分开，Judge失败不能补0或算编辑失败。每模型CPU watcher每120秒核验trigger及实际终态，自动生成统计/诊断报告；真正的新定性目视审查须另记agent观察，不能冒称后台脚本完成AI目视审查。所有watcher与queue均nice19、idle I/O、单线程。ASSIGNMENTS.json记录agent和PID（qwen2511=321314、mice=321316、qwen21/mirage=320713、flux3=322550、replan=322551）。这些是本地报告触发，未配置会话推送。

预备审阅新增发现RePlan5个S1规划文本漏项/合并/额外目标的证据，详见model_reviews/replan/observations.json与evidence.json；保留批准的原生planner默认，不修prompt、不重试、不擅自改评分。正式freeze/test审批门槛不变，experiments2仍仅存最终确定结果。


### 2026-10-29：第二台8卡Judge入口

用户授权将部分模型分配到新机器，并确认共享 `/mnt/bn/strategy-mllm-train/user/tanyue/` 挂载。远端临时包：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/judge-node2-20261029/`；不在experiments2。入口为 `bash <包目录>/start.sh`，后台启动并打印日志位置。要求8张空闲H100 80GB、x86_64 Linux及足够的本地/tmp空间；固定13.5GB运行环境直接解包，不重新安装漂移版本。远端为Qwen2.1(3131)、MIRAGE(808)、MICE(1076)，共5015个唯一Judge请求；本机为Qwen2511、FLUX3、RePlan，各机内部仍按模型顺序运行。

旧Judge PID319362通过SIGUSR1完整排空，保留2000份记录逐一hash核验；原所有admitted都有响应，旧worker全部退出后本机PID373184以不可变reservation排除远端三个模型。交接证据：`/tmp/ifbench/tiered_v1/dev_selection/engineering/node2_20261029/`。READY发布时再次确认5015远端key与本机admitted/records无交集。已有Judge失败不覆盖、不重试；未知结果的admitted任务禁止自动重采样。

远端使用原canonical evidence、prompt、Backend、parse、权重revision、decode和8卡TP/EP配置，batch16与4线程预取；CPU验证已核对5015输出和源图/mask、迁移环境及原fingerprint，没有增加Judge调用。17项调度、分片和监控测试通过，真正新机器GPU加载/推理由用户启动后验证。共享ACTIVE claim防止两个远端实例重复执行，实际模块hash/分片keys/原bindings/原始回答均校验。自动汇入PID374888每60秒将校验通过的远端记录导入本机原Judge记录目录，遇冲突立即停止，不改已有评分。监控PID373889按双机分片展示进度，不沿用单机全队列ETA。模型完成后仍触发既有图文报告；冻结前审批与不碰test规则不变。


2026-10-29 Merlin入口修正：用户实际通过Merlin批作业启动node2；原start.sh后台nohup后返回0，平台遂在10:39 UTC结束作业并清理所有子进程。共享日志仅到runtime校验/解包开始，admitted=0、records=0、ACTIVE不存在，未发生Judge调用。已把共享start.sh和仓库源脚本改为默认前台exec，并通过tee同时保留控制台与共享日志；相同启动命令无需nohup或&。新增生命周期回归测试验证入口在worker运行时不退出且原样传播失败码。上述历史文档中的“后台启动”已失效，以此前台规则为准。只修改入口生命周期，canonical代码、数据、配置、权重及分片不变；证据engineering/node2_20261029/merlin_foreground_fix/receipt.json。用户可重新提交同一命令，不需清理评分缓存。


2026-10-29 15:59 UTC首轮双机Judge齐全：11179唯一请求，10983 scored、196 judge-failed、0 pending。远端14:11:59 UTC完成5015，本机14:56:55 UTC完成最后4164（另2000早先保留）。自动merge曾因共享receipt一次FileNotFoundError退出，84条MICE未汇入；已用原canonical merge重新校验并导入84条既有评分（均scored），无重推理/覆盖。证据engineering/node2_20261029/final_import_audit.json。正常completed退出不再误报进程崩溃。196评分失败仍阻塞候选冻结，未补0、未重试、未进入test。三个subagent正在并行复核剩余模型的终态报告。


### 2026-10-29：用户批准确定性Judge修复与完整dev分析

用户指令“直接进行修复，修复后进行完整的分析总结。”授权恢复原始回答的无歧义结构、按已有score派生pass；不增加模型调用。独立修复器samtok_benchmark/ifbench/judge_repair.py，产物/tmp/ifbench/tiered_v1/dev_selection/judge_repair_v1/。196原失败中183已恢复、13保留缺失，11166有效/11179总请求；原11179记录逐文件SHA核验不变。数值与证据仅来自最终回答，未借思考段或其他unit/global字段补分；多个匿名P/Q块、真缺Q、条件表达式均拒绝。重复同数值字段保留全部原证据，不取其一覆盖。新增Judge/生成调用均0。10项边界测试通过；10983原有效回答在新解析器中数值/pass全一致。

全模型分析180候选-setting行，162完整、18缺分，全部共享10000次源图paired bootstrap。独立复算180分母、162行UP/JP/CI、5组共享key缺失差界、12525生成-Judge绑定均通过。MIRAGE native完整；Qwen2511 single、Qwen21 single、FLUX3 native-annotation在缺失取值数学界下均严格领先其他主候选，但不冒称候选评分已齐或自动冻结。S2同分规则对齐预登记（保留区域→注册顺序→ID）；唯一完整平分FLUX3/S2-box的推荐未变化。

最新入口judge_repair_v1/REPORT.html，包含24组实际输入/输出/prompt、52幅内嵌图；全量统计analysis/REPORT.html、逐条恢复账本REPAIR_AUDIT.html和范围审计DELIVERABLE_AUDIT.html。原model_reviews/STATUS与monitor原始计数仍为首轮raw状态，修复后的有效状态以本独立报告为准。13条补评仅列在PROPOSED_REJUDGE_13.json作为待批准提案，未执行。正式experiments2未写入，freeze/test未启动。


### 2026-10-29：13条一次性canonical补评已获批准

用户对明确提案“对这13条使用原canonical输入各补评一次，最多新增13次Judge调用，保留首轮记录、不重新出图”回复“同意。”。授权文件在/tmp/ifbench/tiered_v1/dev_selection/judge_rejudge13_v1/authorization.json，SHA绑定此前PROPOSED_REJUDGE_13.json；runner为samtok_benchmark/ifbench/dev_rejudge13.py。只允许该13键、每键一次额外回答、保留原11179记录及196确定性修复记录；已admitted无返回禁止自动重试，失败的新回答亦终态。canonical/evidence/prompt/权重/seed/阈值不变，实际batch按模型分组（4/2/2/4/1），引擎上限16，8卡TP/EP。不进行额外校准或编辑生成。新回答仅可由原canonical解析或同一已批准recover规则读取；不选择多次有效回答。记录raw与effective两个不可覆盖层。15项修复/补评边界测试通过。

启动PID515279，日志judge_rejudge13_v1/run.log；新分析写judge_rejudge13_v1/analysis，旧repair报告保留历史。后续若分数齐全，仅提出冻结候选并在冻结/test前等待用户确认，不因补评授权自动冻结或进入test。


### 2026-10-29：13条补评完成，完整dev选型待冻结确认

获准的13个key已各补评一次：12条canonical直接有效，1条按同一确定性规则恢复；共13次新增Judge调用，编辑生成和校准均0。当前11179/11179有效，180/180候选×setting完整。原11179首轮记录与196修复层记录hash全部不变；独立复算180行UP/JP及18候选均JP/10000次paired-bootstrap CI一致（浮点差<=1.12e-16）。旧3条生成/planner失败仍保留在分母，未重试或删掉。

最新图文入口/tmp/ifbench/tiered_v1/dev_selection/judge_rejudge13_v1/REPORT.html（52幅内嵌图），全部统计analysis/REPORT.html，补评逐条证据REJUDGE_AUDIT.html，建议配置analysis/PROPOSED_SELECTION.json。主配置建议：Qwen2511 single、Qwen21 single、FLUX3 native-annotation、RePlan/MIRAGE/MICE native。S2 best-adapted补充选择discard：Qwen2511 point/box、Qwen21 point、MIRAGE point、MICE point；Qwen2511 mask同分保留区域。非S2 discard候选行只是首个主候选原请求复用，S3/S4-noref没有丢弃区域。PE/PUP仍单列补充。

LATEST_REVIEW.json和REVIEW_REQUIRED.json发布有效状态与待审批提案；旧监控/逐模型入口已指向新报告，原始状态归档judge_rejudge13_v1/historical_status。仅停止本任务已完成的CPU observer，未动无关GPU进程。尚未freeze、未启动test、正式experiments2未写入。用户此次“同意”只授权13次补评，不能据此跳过预先约定的dev选型冻结前确认。人工残留率/κ、GT selector paste-back诊断、未执行消融、正式抽检和完整GPU占用统计仍属后续交付，不声称全部benchmark已完成。


### 2026-10-29：逐setting Word/HTML图文文档

用户要求逐setting写清六模型分数、实际输入方式，并直接插入输入/输出图。CPU生成器evaluation/protocol_audit/build_setting_document.py读取既有完整分析与CASE_EVIDENCE，输出/tmp/ifbench/tiered_v1/dev_selection/setting_document/IF-Bench_dev_setting_report.docx及同名.html。主文60模型×setting统计（UP/JP及95% CI）、固定首个dev源图60组示例；S5另加首个K5源图6组以展示none区域，合计66组、98幅内嵌图。附录保留全部180候选行和S2最佳适配。

Word图像直接嵌入，无外链；HTML亦用data URI。原生框示意明确未送入模型；MICE展示真实actual_source.png与逐目标bitmap masks；RePlan用actual_global_prompt/actual_region_guidance，FLUX用generation_metadata.prompt，MIRAGE含sub_prompts。DOCUMENT_MANIFEST.json保存逐例路径、统计及SHA；VALIDATION.json保存覆盖与容器检查。所有产物仍在临时目录，未新增模型调用、未冻结、未启动test；本次写文档请求不构成冻结批准。


2026-10-29 用户指定Markdown格式：已将同版内容导出setting_document/IF-Bench_dev_setting_report.md，图片使用标准Markdown内联图片语法引用同目录figures；IF-Bench_dev_setting_markdown.zip包含md及所需图片。Markdown解析器渲染后核对52张表及133个原文prompt/参数块与HTML一致，98幅图片引用全部有效。未改统计、未新增调用、未冻结/test。


### 2026-10-29：输入适当性复核（冻结前新增证据）

用户要求根据完整实验判断输入能否体现模型能力。只读CPU复核已完成六模型×10settings，报告/tmp/ifbench/tiered_v1/dev_selection/input_suitability_review/INPUT_SUITABILITY_ANALYSIS.md，各模型md/JSON、global_evidence及VALIDATION同目录；未改分数/输入/候选、未新增推理、未freeze/test。旧冻结提案只证明已登记候选内的dev选择，不代表已充分验证原生最优用法。用户尚未批准修改协议、扩候选或重跑。

关键：FLUX全部3417有区域输入src=tgt，包括remove，存在与官方训练格式remove tgt=null/new target行语义不一致；框仅序列化入文本，不能夸大成硬注意力禁止删除。annotation还改变单图至4MP与多图约1MP预处理，其平均JP增益CI跨0。RePlan非S1的972请求将局部任务重复进global，偏离官方严格分离模板，合并/单元未丢；108个S1原生response原样保留。建议先澄清这两项再沿用旧提案冻结。

MIRAGE box/mask各S2/S3 108/108输入输出一致；point→小框影响融合支持域；给定区域的局部指令未像官方parser去除全图方位词。S1失败是原生grounding JSON解析，S5失败是2对/1unit绑定guard拒绝，不笼统归为两次原生崩溃。MICE box2/386、mask3/386在原生nearest latent量化变空，跨settings14unit；point没有空域。S5 global+regions存在注意力传播边界。RePlan1050条新生成日志与MICE4497文本段均未实际截断。

Qwen2511/single有候选对照但coordinates部分S3更高；Qwen21/single合理受控，PE实际dual，1080对图片/参数/seed相同；PE元数据rewriter=0等静态字段不可靠，实际按component记录计。Qwen21当前output_resolution=1024为固定pipeline默认，与README推荐2048级不同；独立mask/single+PE未测，不宣称最佳完整能力。所有因果影响未隔离，不能估算新配置分数。LATEST_REVIEW/REVIEW_REQUIRED附加本报告，原分数/原提案保持历史可追溯，等待用户决定如何处理新发现。

### 2026-10-30：公平性优先的用户澄清

用户明确不以提高各模型分数为目的，要求不引入被评测模型/方法以外的组件做输入转换或能力增强，尽可能保持原生推理，信息通过 prompt、额外图或标注图提供。已把执行边界记录为临时 Markdown：`/tmp/ifbench/tiered_v1/dev_selection/input_suitability_review/FAIRNESS_CLARIFICATION.md`。必要的机械编码不补语义；原生完整方法的组件明确登记；PE/PUP 主配置保持关闭，已有增强结果独立保留，不再以最高性能为由扩展外部增强实验。

此前适用性报告的实测事实保留，但“未测更强配置”不再作为追加实验的推荐理由。FLUX 源/目标语义、RePlan 全局/局部提示、点到硬区域等仍按是否忠实传递输入审查，不能仅以低分为理由修订。既有 dev 选择预算和冻结前确认规则不变。只更新说明及 review 元数据；未修改正式协议正文、输入、分数或候选，没有新增模型调用，未freeze/test。

### 2026-10-30：公平性修订验证获批并执行

用户明确要求重新分析和测试，并新增FLUX.2 Klein-9B蒸馏版。针对原FLUX3四候选已满，用户另行批准将本轮作为显式协议修订：每模型预先固定一套公平输入，只用相同两张dev图×十setting验证，不按分数搜索，保留历史候选与计算记录。授权及固定范围见 `/tmp/ifbench/fairness_v2_20261030/AUTHORIZATION.json`。旧选择规则的历史结果保留；本轮选择依据是输入信息和原生流程，不冒称新方案是原dev按JP选出的方案。正式冻结/test仍需后续确认。

固定两个case是旧smoke的K2 v2-sa_10063996和K5 v2-sa_7414116。Qwen两版各20条既有dual输入/输出通过绑定和SHA复核；其余固定方案分卡验证。MICE、FLUX2现已各20条真实出图，其他进度看RUN_STATUS及逐条record。固定FLUX2权重24文件约34.7GB已获门控访问并校验，按用户明确要求放共享models/pretrained_models/FLUX.2-klein-9B，凭据不写报告或代码。

已纠正两处旧MICE解释：小box变空发生在旧source-raster→nearest适配，原生floor/ceil box接口386/386非空；23个box缩减是strict模式的离线模拟，实际strict=False，不应归为实际运行事实。MICE官方round画布与旧int画布在108dev中2图不同，固定两样例相同。RePlan expand0/switch.5来自官方Qwen CLI推荐，不是Python函数默认。新验证只处理公开输入，不添加外部增强、不修改历史评分、不调用Judge。


### 2026-10-30：七模型固定方案验证完成，最终方式待确认

公平性修订本轮140/140逻辑请求均获得图像并通过输入/输出SHA、公开请求digest和回源尺寸核验，0运行失败、0绑定错误。44个精确旧输出复用（两Qwen各20、FLUX3/RePlan各2个S1），96次新编辑；RePlan新增18次原生规划、MIRAGE61次（188个batch项，不混称API数）。无Judge调用、无新UP/JP分数、未按输出修改固定方案或重采样。自己的GPU worker均已退出，不动无关进程。

最新总报告 `/tmp/ifbench/fairness_v2_20261030/FINAL_EVALUATION_METHODS.md`，全部setting图册 `ALL_MODELS_ALL_SETTINGS_GALLERY.md`；组报告保留实际prompt、原生计划/预测框和逐例输入/输出。发现原生错定位、漏/错编辑和标记残留，均如实保留；出图成功不是任务通过。两个case是固定K2/K5验证，不是总体质量或正式随机10例人工抽检。

待确认规范 `docs/protocol/if-bench-v1/PROTOCOL.fairness-v2.proposed.md` 与逐条修订记录已明确原生组件、输入映射和参数。RePlan expand0/switch.5准确来源为官方CLI的qwen/qwen2511分支默认，不冒称作者明确推荐。所有未冲突的旧最终交付保留，原8项消融逐项列历史/待计划/新边界不执行；失败分母、Judge缺分、禁止自动回退和通用补评规则继续适用。

下一阶段建议是用户确认固定方式后完成同一108-dev与统一Judge，不重新选候选；完整dev汇报后仍须按用户原要求停在freeze/test前确认门。本轮两图验证授权不自动包含新全dev、冻结或test。旧分数/候选提案/分析文件hash仍一致；LATEST_REVIEW和REVIEW_REQUIRED仅追加本轮指针，正式experiments2/IF-Bench仍为空。


### 2026-10-30：用户确认公平方案并改为20张dev，要求8卡自启动入口

用户明确“我确认，但我希望减少dev数量到20张图，加快速度。给我8卡入口指令，进行dev集评测。”现已授权七模型固定方案的20图dev及统一Judge，不再搜索；正式freeze/test门不变。按原108-dev池K分层比例、固定seed20261027及SHA256(seed:source_id)排序抽20，K2/3/4/5=3/4/11/2，共72units；剩余88仍留dev，976test未动。抽样只读取ID和公开K，先落selection再读取输出/分数。

自启动共享包 `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v2-dev20-20261030/`。入口前台start.sh，逐模型8卡分片生成，全部生成结束后原8卡TP/EP batch16 Judge按模型评分。1400逻辑请求中440个旧输出精确缓存、960个待新生成；旧Judge池按canonical/output SHA精确匹配，不按candidate身份搬分。两运行环境分离，保持原Python/torch/transformers；不覆盖不同的既有/tmp目录，不碰无关GPU进程。未知已提交请求不自动重试。

开发模块fairness_dev_plan/worker/run/judge/report；用户指南docs/protocol/if-bench-v1/DEV20_RUN_ZH.md、已确认20图dev协议PROTOCOL.fairness-v2.dev20.md。全部dev缓存、日志、输出及报告在共享临时包，正式experiments2不写入。入口交付/CPU验证不等于实际新推理已完成；是否启动以results/executions与真实records为准。
