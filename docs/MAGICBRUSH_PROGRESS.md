# MagicBrush 进度记录

时间均为 UTC；协议见 [MAGICBRUSH_EVALUATION.md](MAGICBRUSH_EVALUATION.md)。

## 2026-11-05

- 16:24 开始只读核对。系统时间早于 GPU 许可时段；GPU 4–7 约占用 46–50 GB，未启动任何 GPU 进程。
- 已 fetch `v2branch`、`eval-refedit`、`eval-mira`，主 worktree checkout 未改；从 `origin/v2branch` 读取配置／用法。
- 已阅读 RefEdit/MIRA 的 AGENTS、评测与进度文档、公开数据与八方法 adapter、worker、ARNOLD 模板；核对 SITEdit aa5a414 原始主行配置。
- 官方调研确认：test 已公开，535 会话／1,053 轮；HF gated=false；固定 GitHub d2d7f84 与 HF 6c25456；CC BY 4.0。未使用第三方镜像或付费接口。
- 创建独立 worktree `/opt/tiger/tanyue/if-bench-magicbrush` 和 `eval-magicbrush`，基于 `origin/eval-refedit` c9f9447；解除继承的远程分支追踪，防止误推 RefEdit。
- 在实现前写定方案：八方法，两种 mask 输入轨道，独立全轮／连续最终轮；mask-provided 论文区域指标与现行 scorer 整图指标的差异显式披露。
- 17:22 数据下载与解码完成：535 会话／1,053 轮；一／二／三轮会话数 216／120／199。六个 parquet 均通过官方 SHA256；指令与官方 metadata 一致，连续轮次的 GT/source RGB 像素一致。`SOURCE.json` SHA256：`7290246236a8b5cbae16093f65c7ce6f5e618e5db25174144f09109529ee4dd9`。
- 所有 1,053 个 mask 均为 RGBA、含透明和不透明区域；统一 alpha<128 为编辑区。首轮 533 张 500px、2 张 1024px；固定公开 1024px 网格与 IF-Bench canvas，避免连续编辑被恢复到 500px。三条官方空 local description 原样保留并披露。
- 官方 CLIP ViT-B/32 与 DINO ViT-S/16 权重已下载校验；CPU 相同图像自检得到 L1=L2=0、CLIP-I=DINO=1。使用安全权重加载和已安装 Transformers FP32 实现，与旧 CUDA/FP16 的精度差异列入方案。
- 新模块已具备公开输入、两轨道八方法适配、多轮依赖、独立生成／评分记录、分会话 bootstrap、报告、拼图、原生环境 staging。18 项 CPU 契约测试通过；包含禁止 GPU 0–3、19:00 时间门禁、占用门禁、无 GT 回退、mask 信息边界、完整请求数和冻结模块不变。
- 正在构造共享输入并执行训练指纹审计。尚未开始 GPU 冒烟或正式实验。
- 重合审计已比较 1,588 个去重后的源／GT 图像，对照 646,908 个训练图像指纹与 8,337 条 gRES 指纹。COCO id 命中 31 会话，其中 17 会话可追溯到实际 S2／Pass1 微调。逐一查看 31 对图像，确认同一 COCO 照片的裁剪关系；保守排除 31 会话，所有方法共用 504 会话／981 独立轮次子集。
- 额外感知近邻覆盖 20 会话，已查看全部候选缩略图，未确认新增重合；两条旧路径不可访问，改从既有 gRES parquet 读取 SHA 完全相同的图像字节核查。保存 `overlap/VISUAL_REVIEW.json` 与对比图。上述目检为 Codex 辅助核查，不冒充独立人工审计；任意裁剪、基础预训练和未记录数据来源不在穷尽性保证内。

- 18:14 共享包构造完成：2,106 份公开请求，bundle digest `545b6b9af9c7ccbe0980d62cc1fd8daaa7d4297e46a9652d0a11ecb947530faa`。固定冒烟为 `323789-1` 无 mask、`508582-1` 有 mask、`323789-2` 连续无 mask。
- 18:31 评分器补齐原始 DINO 的 LayerNorm epsilon=1e-6；198 个参数张量与原始官方 checkpoint 完全相同，两张真实图的独立 CPU 前向特征逐位一致，证据 `METRIC_PARITY.json`。未执行远程模型代码。
- CPU 集成测试覆盖三个请求的实际 worker 调度、连续输入依赖及完成结果复用；模型替身仅在测试中使用，不进入数据、冒烟或正式输出。

- 18:33 全量包 10,531 个公开／评分资产通过 NAS 路径与 SHA 核验，见 `PREPARE_VERIFICATION.json`。
- 为连续轮次在新机器上重绘标记，固定 DejaVuSans 字体字节并附许可，放入共享包 assets；三个实际标记图重新绘制后与已有输入逐字节一致。

- 19:00:12 确认 GPU 4–7 均为 1,605 MiB，只有既有 1,596 MiB 进程；19:00 后启动四卡 `smoke_001`，未使用 GPU 0–3，未结束其他进程。生成源码为 `6bd2263`，冻结 19 个生成相关源码文件。
- 冒烟记录：`.ifbench-tmp/magicbrush_20261105/smoke_001/`；launcher 日志 `/tmp/claude_magicbrush_20261105/smoke_001.log`。SITEdit 首轮纯文字定位与直接 mask 编码已完成；尚未进行正式实验。

- 八方法 24/24 张图与五指标评分全部完成：33 条阶段记录均为 completed，17 个 worker 正常退出，无缺失 admission。实际输入／输出拼图已放到 `visualization_tmp/MagicBrush_20261105/`，中文报告与逐请求分数在共享包 `smoke_001/report/`。
- 正式生成实测外推为 342.77 GPU·h，四卡理想时间 85.69 h、八卡 42.85 h，另加加载／I/O／评分。依据用户 8 h 上限，未在本机启动正式实验。
- Qwen2.1 连续第二轮噪声较重；19:23 独立进程对同一输入／seed 复核，raw 与 output 均与原记录 SHA 完全一致。记录在 `diagnostics/qwen21_same_input_fresh_process/`，未改原图或模型参数，未并入正式结果或吞吐估计。
- 逐方法状态、耗时、显存、样例观察及正式剩余工作见 [MAGICBRUSH_RESULTS.md](MAGICBRUSH_RESULTS.md)。当前发布身份与命令见下方四机部署记录。

## 2026-11-06：当前四机 32 卡部署

- 用户最新要求为一个 ARNOLD 作业、4 workers × 8 H100 80GB；已替换此前的启动文件和部署文档。生成、评分和统计实现及配置不变，继续使用 SITEdit aa5a414 的冻结主行。
- 535 个完整会话分配为 133／133／135／134，各节点每方法分别 786／786／786／784 请求。四台各八卡生成，全部生成完成后执行 32 个标准指标分片，node 0 统一统计和 bootstrap。
- 跨机协调使用 NAS 原子目录租约、逐节点心跳与四节点屏障。只有全部旧节点释放后才允许新 attempt 进入；平台强制停止须明确确认全部旧 worker 退出后放行协调锁。未知 admission 仍不自动重采样。
- 29 项 CPU 测试通过，包含四节点完整阶段无重漏、续跑不再调用模型、32 个评分分片、并发心跳、同伴失败、最后一个节点仍运行时阻止新 attempt、显式恢复和只停止自己的进程。实际 NAS 四进程测试的最终结果记录在新包外交接文档中，不将其描述为四台物理机器的 GPU 实验。
- 首次四机发布路径 `.ifbench-tmp/magicbrush_4node32_20261106/`，交接记录为同级 `magicbrush_4node32_20261106-handoff.md`。新包封存 `BASELINE.json` 后解除对旧 READY 和启动文件的依赖；共同公开输入、GT、字体、指标权重、重合审计与冒烟证据保留。
- 冒烟外推生成总量仍为 342.77 GPU·h，32 卡理想生成时间 10.71 h，当前任务队列模拟约 11.36 h，加载、I/O、评分与报告另计。没有启动正式实验或 GPU 任务。

## 2026-11-06：修复源码下载阻塞

- run001 于 03:08 UTC 启动；node 0 的 GitHub clone 未完成，目录只有 `.git`，HEAD 不存在。用户已停止四个远端 worker。结果根仍为空，没有生成、评分或未知 admission。
- 两处在线 clone 改为从 NAS 发布包恢复 Git bundle：benchmark 固定发布提交，SITEdit 固定 aa5a414。入口先校验 bundle SHA256，仅允许 Git 本地文件协议；增加启动阶段和失败记录。评测输入、19 个生成源文件、配置、权重、评分及统计不变。
- 30 项 CPU 测试通过，新增覆盖无网络时命名分支与 detached HEAD 的恢复及错误 commit 拒绝；shell 语法和 Ruff 检查通过。
- 新入口 `.ifbench-tmp/magicbrush_4node32_nas_20261106/start.sh`，恢复使用 `run002`。保留旧四机包与 run001 证据。离线 CPU 验证和发布身份写入包外 `magicbrush_4node32_nas_20261106-handoff.md`。

## 2026-11-06：run002 持续监控

- 03:53 四个远端 worker 均从 NAS 恢复固定源码，03:55 左右完成资产校验；04:10 前后完成环境恢复与预检，四台配置和 bundle 指纹相同，各启动八个单卡任务。
- 截至 04:28:47 的只读监控快照：RePlan 成功规划 524 条；MIRAGE 成功规划 207 条、失败 27 条。编辑阶段尚无成功图，1 条 MIRAGE 编辑记录因上游规划失败而失败。上述是运行中计数，不能当作最终指标或失败率。
- 核查首批四条 MIRAGE 失败：三条是冻结 `mirage/vlm.py` 解析器收到的目标列表与局部指令列表长度不一致，一条定位回答为空；对应原生回答和 traceback 已保留，未发现 CUDA/OOM 证据。不重试、不改原始记录，不为方法失败停止全局队列。
- Qwen-2511 首次加载较慢：04:29 抽查四台日志均在模型组件加载完成后约 18 分钟无新输出，尚未观察到首个请求受理。不能仅因心跳正常就认定出图正常；已请求远端只读 GPU/进程 I/O 诊断，原因待确认。
- 持续监控目录为 `.ifbench-tmp/magicbrush_monitor_20261106/`，60 秒更新 `STATUS.json`、`STATUS.md`，保留 `ALERTS.jsonl`、逐条阶段索引及输出解码/SHA/尺寸抽查。诊断见 `MIRAGE_INITIAL_FAILURE_REVIEW.json`、`LOADING_DELAY.json`；只写监控目录，不修改实验。
- ETA 必须等四台各至少完成 20 张图、各自首图后积累至少 10 分钟观测再外推。规划耗时和冷加载阶段不能直接当成编辑吞吐；此前冒烟外推 11.36 h 仅指生成排队成本，不含准备、加载、评分和汇总。

- 04:36 出现首批完成图，04:38:49 四台均已成功出图：Qwen-2511 73、RePlan 15、MIRAGE 9，共 97；11 次输出解码、SHA、尺寸抽查通过，另目检三个真实输出。node 0 首个 Qwen-2511 后端加载实测 1517.55 s，随后推理 38.66 s；确认延迟位于加载阶段，但没有远端 I/O 证据，不能进一步断言具体原因。未重启任务、未调整配置；不把运行抽检当作最终分数。
- 05:39:48 快照：25,136 条生成请求已有 2,527 条终态（10.1%），其中成功出图 2,478 张（Qwen-2511 1,579、RePlan 628、MIRAGE 271），MIRAGE 编辑失败 49 条，含原生规划失败的连续轮次依赖传播。四台各八个任务，未发现基础设施故障；其余方法仍在冻结队列中，尚未评分。基于当前吞吐的剩余生成估计约 4.5 h，尚未覆盖后续模型冷加载、评分和汇总，不能当成最终完成时间。
- 已核对 MIRAGE `mask-free/iterative/149-2` 和 RePlan `mask-free/iterative/127517-2`：第二轮公开输入与上一轮实际输出逐字节一致，依赖记录 SHA 也一致，没有 GT 替换。目检 RePlan `mask-provided/independent/478407-2`，请求的姜色卷发已出现，右下边缘另有小块彩色瑕疵；这是单例观察，原因未确定，原图保留供冻结评分。证据均在监控目录 `REPLAN_OUTPUT_RECURRENT_REVIEW.json`；未修改正式输入、输出或记录。
- 06:07 FLUX.3 开始正式出图。node 0 首图加载 367.81 s、推理 6.21 s，实际 seed 42、16 步、PUP 关闭与冻结配置一致；解码、尺寸和 SHA 核验通过。目检首图场景完整，部分窗帘下移但仍露出下方窗户；这是单例观察，不替代正式指标。证据 `FLUX3_FIRST_OUTPUT_REVIEW.json`。四台的四种已启动方法首图均已通过校验，共 16 次。
- 用户执行了 node 0 只读运行诊断：06:20:13 和 06:20:23 两次采样各有七张卡利用率 99–100%，短暂空闲的卡不同，八个任务进程的 CPU 计数均增长，十秒内无新增主缺页，近期 I/O 压力平均值为零。该时段未见停滞迹象；不能用正常出图阶段的采样解释此前冷加载缓慢的具体原因。原始采样 `runtime-node-0-1793946023-15072.json`，分析 `RUNTIME_NODE0_REVIEW_0620.json`，均在独立监控目录。
- 06:29:48 快照：5,084 / 25,136 条请求终态（20.2%），成功出图 5,008 张（Qwen-2511 2,595、RePlan 1,151、MIRAGE 466、FLUX.3 796），MIRAGE 编辑失败 76 条。四台各八个任务，没有基础设施故障；其他四种方法仍排队，评分尚未开始。MIRAGE 新见的 JSON 错误位置已核对为相同的原生定位回答不完整问题，证据 `MIRAGE_300994_2_REVIEW.json`。剩余生成暂估约 3.9 h，后续模型加载、评分及汇总仍不在保证范围内。

## 当前待办

1. `run002` 四台已出图；持续检查逐模型输出、失败原因和稳定吞吐，之后监督评分及最终汇总。
2. 完成后汇总全量／统一去重合子集、五指标和会话 bootstrap，保留失败与恢复记录。
