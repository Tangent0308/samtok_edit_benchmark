# Historical IF-Bench session notes

Archived on 2026-10-30. These are chronological evidence, not current authorization.
Current rules: [repository instructions](../../../../../../AGENTS.md) and [approved dev20 protocol](../PROTOCOL.fairness-v2.dev20.md).

# IF-Bench output placement

User instruction, 2026-10-27: experiments2 is reserved for final, frozen formal evaluation artifacts. Put audit evidence, source snapshots, temporary downloads, smoke tests, dev candidate outputs, debugging logs, and non-formal previews under `/tmp/ifbench/`. Current review: `/tmp/ifbench/protocol_review_20261027/`.

Keep development code and protocol documentation in this repository. Generated audit/check JSON belongs in the temporary directory. Only final frozen configuration/protocol, formal run inputs/outputs/logs, judge records, and final reports may enter `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/IF-Bench/`. The user has confirmed all five protocol recommendations and authorized phase 2. The shared-input gate is approved. The user revoked per-model smoke approval: complete all model smoke tests, then consolidate problems and recommendations. The remaining mandatory stop gate is after dev scores and proposed selections, before freezing/test. Do not delete or relocate unrelated historical experiments.

This instruction supersedes the parent AGENTS.md visualization path for non-formal IF-Bench artifacts. Historical immutable logs can retain old paths; preserve their bytes and use the relocation receipt to resolve paths.

Current status: all 7 main-table smoke tests completed on the same 3 fixed dev cases across 10 settings. Actual records: 216 outputs (204 main-path, 12 alternative), 6 N/A (MaskFlow S1/S5), no generation failures; 264 diffusion API calls and 17 native planner API calls. Report: `/tmp/ifbench/tiered_v1/smoke/SUMMARY_REPORT.html` (inline images), with Markdown and machine records alongside. Shared package: `/tmp/ifbench/tiered_v1/shared_inputs_20261027/`. Those counts describe the completed smoke stage, not quality scores. The subsequent dev-selection authorization is recorded below. No test has started. Formal IF-Bench results directory remains empty.

MIRAGE public-ref extraction was explicitly approved: use an exact contiguous span of the current public instruction, never private spec.ref; ambiguous extraction remains pending. Approval: `/tmp/ifbench/tiered_v1/smoke/mirage_ref_policy.json`. Do not treat smoke recommendations as frozen or scored selections. Historical instruction superseded: see the 2026-10-29 user authorization below.

Latest user approval: “我确认，开始。” authorizes the registered full dev selection. Plan: `/tmp/ifbench/tiered_v1/dev_selection/plan.json`; live report: `PROGRESS.html` in that directory. Work proceeds through generation, canonical blind Judge and proposed selection, then MUST stop before freeze/test. The orchestrator writes `REVIEW_REQUIRED.json` at that boundary and never creates freeze.json. All artifacts remain temporary. MIRAGE grammar coverage has been extended using public text only and checked on all 386 dev units; exact spans and rule hash are recorded in `ref_span_inventory.json`. No private target reference or model output was used for that extraction.


2026-10-28 用户最新指令：暂不评测未验证一次性多目标编辑的 MaskFlow。当前执行范围为其余六个主表方法；MaskFlow 的串行适配运行已停止，已有产物只留在临时目录，不进入当前 Judge、候选选择、分母或失败/N/A计数。原候选登记不修改，使用 plan-digest 绑定的 `/tmp/ifbench/tiered_v1/dev_selection/scope.json` 保存用户范围变更。后续可选/附录的仅串行适配方法亦不得未经重新确认启动。


2026-10-28：用户已要求后台定期监控。独立只读监控 PID 4164429，每60秒检查、每600秒保存常规快照，异常/状态变更即时留档；输出 `/tmp/ifbench/tiered_v1/dev_selection/monitor/REPORT.html`、`latest.json`、`history.jsonl`、`events.jsonl`，源码 `samtok_benchmark/ifbench/dev_monitor.py`。监控不改评测、不重采样；生成ETA使用实测耗时与动态GPU调度模拟，Judge正式batch>=16至少32条记录后才给评分ETA；冻结前审核到达后自动结束监控并保留最终报告。


2026-10-29恢复：Qwen2.1 PE异常请求保留失败、不重试；290条未开始请求已核验后由新controller PID 200038恢复，8卡并行。旧PAUSED已归档 `engineering/recovery_20261029/`。监控是本地文件只读监控，没有接聊天推送，不能声称会自动在聊天通知用户。监控曾及时发现异常，但此前未主动送达；详情见EXECUTION_STATUS_ZH.md。

2026-10-29 Judge工程优化：用户授权预取、连续补位及16/32并发性能验证。912条旧Judge记录在完整批次边界保留，交接目录 `engineering/judge_stream_20261029/`。新runner模块dev_judge_stream、PID255776；原dev_judge.py及v2/judge.py不得为此改动，旧config仅描述初始引擎，实际参数和额外校准调用见executions/*/receipt.json。新记录逐条落盘且不覆盖旧记录；SIGUSR1排空停止；admitted未返回的请求禁止自动重试。监控现PID254672，持续调度ETA从新完成速率计算。校准回答不参与dev评分；当前尚在加载/验证，实测结论待calibration/summary.json。


Judge连续调度首次校准出现已定位的vLLM0.31接口适配错误：enqueue返回内部随机化ID，step输出外部ID，原映射触发KeyError。错误发生于隔离校准，原912条评测记录hash重新核验无变化，production submitted=0。已改为通过output_processor.request_states读取显式external_req_id映射，新增回归测试，11项测试通过。旧执行记录保留：32次完成的baseline调用和16次中止/未持久化的stream校准调用共48次；其中15条由engine shutdown明确记为aborted，首条因ID映射错误未保存。新的PID266912继续校准，复用已完成baseline，不覆盖评测记录；余下两种调度各32次额外调用独立记录，最终总数以各execution receipt与submissions为准。新日志orchestration/031-canonical-judge-stream.log。


### Judge调度实测结论与恢复（2026-10-29）

同一组32份dev输出：batch16=211.373秒（545.007项/小时）；continuous16=381.815秒（301.717项/小时）；continuous32运行427.536秒时仍0/32完整返回，已中止隔离性能试验，不把该时间冒称完整耗时。旧GPU批处理策略更快，故最终采用8卡TP/EP、引擎上限16、每批16请求、4线程预取最多两批图像。所有校准均不进候选分数；共112次额外Judge请求，其中64份完整回答、48份中止或未持久化，按execution记录归档。性能试验的引擎容量上限为32，batch16基线实际提交16；恢复评分引擎容量回到原16。

中止校准后遗留的EngineCore267750与8个worker仍占显存，导致一次恢复启动失败（未提交评分）。已根据记录的PID、父子关系和启动时间定向清理，证据 `engineering/judge_stream_20261029/orphan_cleanup.json`；无关GPU进程未动。原912份评分hash再次确认未变，未重跑已评分请求。当前恢复进程PID278315，日志 `orchestration/033-canonical-judge-prefetch.log`，额外校准不再重复。13项协议、调度、输入映射和监控测试通过。

当前只读监控PID275781。预取批处理ETA使用完整墙钟耗时，避免一批16条同时写入导致早期速度被夸大。实测报告（内嵌3组既有dev图像）：`/tmp/ifbench/tiered_v1/dev_selection/engineering/judge_stream_20261029/REPORT.html`。恢复评分与实际批间等待仍待新记录验证，不能宣称已取得全流程加速倍数。


2026-10-29 05:44 UTC恢复验证通过：PID278315的8卡TP/EP、引擎上限16、每批16+4线程预取已新增32条成功评分，总计925 scored/19 judge-failed，原912条hash全部不变。两次批间准备等待2.87/5.97毫秒；旧56次非推理间隔中位数9.18秒。新首32条完整墙钟169.42秒，约679.96项/小时；样本不同，不宣称严格加速倍数。切换、隔离校准及重载造成约48.5分钟无新dev评分落盘，一次性成本如实记录。证据engineering/judge_stream_20261029/production_verification.json，图文REPORT.html已更新。继续未完成dev Judge；19条原格式失败不补分、不重试，冻结/test门槛不变。

2026-10-29 latest explicit user authorization: use subagents in parallel as each model completes evaluation, to inspect, analyze, summarize and create thumbnail visualizations. This supersedes the earlier no-subagents restriction for this task. Keep scoring/inference GPU processes untouched; subagents use CPU only with bounded I/O, write preliminary materials exclusively under /tmp/ifbench/, never modify Judge scores or choose from incomplete scores. A model with all Judge attempts terminal but failures is reviewable with clearly incomplete scores; failures block final selection. At most 3 analysis agents concurrently; test/freeze approval gate unchanged.


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


### 2026-10-29：输入适当性复核（冻结前新增证据）

用户要求根据完整实验判断输入能否体现模型能力。只读CPU复核已完成六模型×10settings，报告/tmp/ifbench/tiered_v1/dev_selection/input_suitability_review/INPUT_SUITABILITY_ANALYSIS.md，各模型md/JSON、global_evidence及VALIDATION同目录；未改分数/输入/候选、未新增推理、未freeze/test。旧冻结提案只证明已登记候选内的dev选择，不代表已充分验证原生最优用法。用户尚未批准修改协议、扩候选或重跑。

关键：FLUX全部3417有区域输入src=tgt，包括remove，存在与官方训练格式remove tgt=null/new target行语义不一致；框仅序列化入文本，不能夸大成硬注意力禁止删除。annotation还改变单图至4MP与多图约1MP预处理，其平均JP增益CI跨0。RePlan非S1的972请求将局部任务重复进global，偏离官方严格分离模板，合并/单元未丢；108个S1原生response原样保留。建议先澄清这两项再沿用旧提案冻结。

MIRAGE box/mask各S2/S3 108/108输入输出一致；point→小框影响融合支持域；给定区域的局部指令未像官方parser去除全图方位词。S1失败是原生grounding JSON解析，S5失败是2对/1unit绑定guard拒绝，不笼统归为两次原生崩溃。MICE box2/386、mask3/386在原生nearest latent量化变空，跨settings14unit；point没有空域。S5 global+regions存在注意力传播边界。RePlan1050条新生成日志与MICE4497文本段均未实际截断。

Qwen2511/single有候选对照但coordinates部分S3更高；Qwen21/single合理受控，PE实际dual，1080对图片/参数/seed相同；PE元数据rewriter=0等静态字段不可靠，实际按component记录计。Qwen21当前output_resolution=1024为固定pipeline默认，与README推荐2048级不同；独立mask/single+PE未测，不宣称最佳完整能力。所有因果影响未隔离，不能估算新配置分数。LATEST_REVIEW/REVIEW_REQUIRED附加本报告，原分数/原提案保持历史可追溯，等待用户决定如何处理新发现。

### 2026-10-30：用户明确公平性优先，禁止外加增强

用户澄清目标不是提高所有模型分数，而是尽可能确保公平：不用被评测模型/方法以外的组件转换输入或加强能力，尽可能保留自身推理，通过 prompt、额外图或图上标注提供同 setting 的公开信息。机械格式转换允许，但不得补对象语义/隐藏几何；确定性不自动保证语义正确（尤其 point→硬区域、selector→输出框）。Qwen PE/FLUX PUP 主配置继续关闭，不能因其更高分或官方推荐而纳入；既有增强结果仅保留历史。不要继续安排外接 SAM、grounder、caption 改写等增强实验。完整 RePlan/MIRAGE 方法原有的规划组件须明确列出，限公共输入并记录调用，不能将额外组件改称原生，也不能把方法成绩冒称裸骨干成绩。

用户这次澄清不取消原 dev 候选上限/同等预算/冻结前确认，也不授权新推理或输入修订。后续先以公平性和原生接口语义审查候选，低分本身不是换输入、扩区域或新增组件的理由。记录位于 /tmp/ifbench/tiered_v1/dev_selection/input_suitability_review/FAIRNESS_CLARIFICATION.md；旧分数、提案和分析报告保留可追溯。本轮只写说明及状态，不改实验记录、未freeze/test。

### 2026-10-30：用户另行批准公平性修订验证，并加入 FLUX.2 Klein-9B

用户随后明确要求基于官方代码重新分析、测试、得到最终方式，并新增 FLUX.2 Klein（按此前清单为9B蒸馏版）。就旧FLUX3已用满4候选的冲突，已向用户提出具体方案，用户选择“采用上述协议修订验证（推荐）”：每模型先按公平性固定一套新方案，仅同一2张dev图×10settings做一次验证，不按分数继续搜索，旧候选及耗时完整保留。授权记录 `/tmp/ifbench/fairness_v2_20261030/AUTHORIZATION.json`；此授权取代上一段“尚未授权新输入/推理”的当前状态，但不授权Judge搜索、冻结或test。

固定图为旧smoke的 v2-sa_10063996（K2）、v2-sa_7414116（K5，S5含none），选择不读取输出。Qwen两版本复用已核验dual；FLUX3 dual/boxes=None/PUP-off；RePlan标注图原生planner→同坐标清图原生editor，response原样、CLI推荐expand0/switch.5；MIRAGE原生逐unit批解析保留全部pairs，原生定位消息追加公开标记说明，清图联合编辑；MICE单图，point/none入global，box/mask原生binding，不改attention；FLUX2 9B dual、4步CFG1。输入、runner和验证plan在GPU前固定，执行中不因输出差改prompt或选方案。原生误识别标记属于应报告的表现，不能手改计划救分。

用户另明确授权将FLUX2权重下载到 `/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models`，并完成官方门控；固定revision 92196c8e11f7b6cf2b7493e037d8c5345c559216 的24个Diffusers文件已下载且LFS SHA/文件大小核验，receipt `flux2_download.json`。凭据只用于认证，不写代码、报告或登录缓存。

临时根 `/tmp/ifbench/fairness_v2_20261030/`；RUN_STATUS.json记录任务；各model最终方式和图片报告在其子目录。MICE与FLUX2已各20/20出图；其余进度以实际record为准，不把CPU spy契约当神经网络验证。并行GPU仅本机已分配任务，不动无关PID154280；read-only权重顺序预读仅工程加速。正式experiments2未写入，旧结果不得覆盖。


### 2026-10-30：七模型固定方案验证完成，最终方式待确认

公平性修订本轮140/140逻辑请求均获得图像并通过输入/输出SHA、公开请求digest和回源尺寸核验，0运行失败、0绑定错误。44个精确旧输出复用（两Qwen各20、FLUX3/RePlan各2个S1），96次新编辑；RePlan新增18次原生规划、MIRAGE61次（188个batch项，不混称API数）。无Judge调用、无新UP/JP分数、未按输出修改固定方案或重采样。自己的GPU worker均已退出，不动无关进程。

最新总报告 `/tmp/ifbench/fairness_v2_20261030/FINAL_EVALUATION_METHODS.md`，全部setting图册 `ALL_MODELS_ALL_SETTINGS_GALLERY.md`；组报告保留实际prompt、原生计划/预测框和逐例输入/输出。发现原生错定位、漏/错编辑和标记残留，均如实保留；出图成功不是任务通过。两个case是固定K2/K5验证，不是总体质量或正式随机10例人工抽检。

待确认规范 `docs/protocol/if-bench-v1/PROTOCOL.fairness-v2.proposed.md` 与逐条修订记录已明确原生组件、输入映射和参数。RePlan expand0/switch.5准确来源为官方CLI的qwen/qwen2511分支默认，不冒称作者明确推荐。所有未冲突的旧最终交付保留，原8项消融逐项列历史/待计划/新边界不执行；失败分母、Judge缺分、禁止自动回退和通用补评规则继续适用。

下一阶段建议是用户确认固定方式后完成同一108-dev与统一Judge，不重新选候选；完整dev汇报后仍须按用户原要求停在freeze/test前确认门。本轮两图验证授权不自动包含新全dev、冻结或test。旧分数/候选提案/分析文件hash仍一致；LATEST_REVIEW和REVIEW_REQUIRED仅追加本轮指针，正式experiments2/IF-Bench仍为空。


### 2026-10-30：用户确认公平方案并改为20张dev，要求8卡自启动入口

用户明确“我确认，但我希望减少dev数量到20张图，加快速度。给我8卡入口指令，进行dev集评测。”现已授权七模型固定方案的20图dev及统一Judge，不再搜索；正式freeze/test门不变。按原108-dev池K分层比例、固定seed20261027及SHA256(seed:source_id)排序抽20，K2/3/4/5=3/4/11/2，共72units；剩余88仍留dev，976test未动。抽样只读取ID和公开K，先落selection再读取输出/分数。

自启动共享包 `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v2-dev20-20261030/`。入口前台start.sh，逐模型8卡分片生成，全部生成结束后原8卡TP/EP batch16 Judge按模型评分。1400逻辑请求中440个旧输出精确缓存、960个待新生成；旧Judge池按canonical/output SHA精确匹配，不按candidate身份搬分。两运行环境分离，保持原Python/torch/transformers；不覆盖不同的既有/tmp目录，不碰无关GPU进程。未知已提交请求不自动重试。

开发模块fairness_dev_plan/worker/run/judge/report；用户指南docs/protocol/if-bench-v1/DEV20_RUN_ZH.md、已确认20图dev协议PROTOCOL.fairness-v2.dev20.md。全部dev缓存、日志、输出及报告在共享临时包，正式experiments2不写入。入口交付/CPU验证不等于实际新推理已完成；是否启动以results/executions与真实records为准。
