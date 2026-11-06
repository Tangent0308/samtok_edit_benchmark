# MagicBrush 评测：冒烟结果与正式实验交付

2026-11-06 更新。**八方法均通过三个固定请求的生成与免费评分（24/24），正式全量尚未启动。** 实测外推超过用户设定的本机 8 小时上限，按用户最新要求交付四机 32 卡 ARNOLD 入口，详见 [四机运行说明](MAGICBRUSH_CLUSTER_RUN.md)。冒烟的“通过”表示流程完成，不表示每个编辑目标均成功，也不构成总体性能结论。

## 1. 数据、评测方式与协议差异

MagicBrush 是基于 COCO 图像、人工指令与编辑 mask 构建的图像编辑数据集；测试集含 **535 个会话、1,053 轮**，一／二／三轮会话分别为 216／120／199。官方 test 已公开，本次仅从官方仓库与 Hugging Face 下载固定版本，保留 SOURCE、许可和校验和，未执行数据包代码。详细来源、已发表基线与参数见 [评测方案](MAGICBRUSH_EVALUATION.md)，执行命令见 [运行手册](MAGICBRUSH.md)。

两种输入轨道分别评独立单轮与连续多轮：独立设置评价全部 1,053 轮；连续设置每轮使用本方法上轮输出，评价 535 个最终图。第一轮精确复用，每方法共生成 3,142 个请求，八方法共 **25,136** 个。免费指标为 L1、L2/MSE、CLIP-I、DINO、CLIP-T；CLIP-T 使用官方 local description，禁止把该 caption 送给编辑模型。

| 方法 | 无 mask | 提供官方 mask |
|---|---|---|
| SITEdit | 原始指令 → 原生 Pass1 区域码 → S2 | mask → 原生 SAMTok codec 区域码 → S2 |
| Qwen-Image-2.1、Qwen2511、FLUX.3、FLUX.2 Klein-9B | 清图 + 原始指令 | 清图 + 同一 mask 的轮廓标记图 + 固定角色说明 + 原始指令 |
| RePlan | 原生 planner → Qwen2511 编辑 | planner 看标记图与指令，editor 编辑清图 |
| MIRAGE | 原生 parser / locator → 联合编辑 | locator 看标记图；editor 编辑清图；原生 patch ratio 0.4 |
| MICE | 原文作原生全局指令 | 公开 mask 与原文作原生区域绑定 |

SITEdit 严格使用 aa5a414、Pass1 step 2000、S2 adapter_16000、raw SAMTok text encoder、γ=2、同句去 token 的负分支、40 步、seed 42。本轮三个请求均有合法区域码，无纯文本回退；mask 请求的 grounder 调用数为 0，codec encode 为 1。没有 LoRA 强度调整或其他变体。

主要协议差异均已在实现前写入方案：

- 生成端统一公开 1024px 网格与 IF-Bench 约 1MP 画布；保存 raw，再逆映射回 1024px。连续输入不借用 GT、不按模型输出重新定位 mask。
- 提供 mask 的轨道采用公开 scorer 的整图五指标；论文 Table 3 使用区域指标，因此与该表不直接合并排名。论文 Table 2 历史数字也单独列为参考。
- 使用官方 CLIP ViT-B/32、原版 DINO ViT-S/16 的发布者转换权重与 FP32/eager 实现。DINO 恢复原始 LayerNorm epsilon=1e-6，并通过原权重与独立前向核验；不宣称与历史 CUDA/FP16 栈逐位相同。
- 官方三条空 local description 原样编码并保留在分母，不人工补写。mask 以 alpha<128 确定性转为编辑区域；不读取 GT 差异或调用外部定位器。

## 2. 训练图像重合：必须同时披露两套正式结果

**535 个会话中，有 31 个与已知 SAMTok/gRES 语料共享 COCO 源图，其中 17 个可追溯到实际 Pass1/S2 微调。** 源图重合不要求 PNG 字节相同；此次 COCO id 证据与 31 对图像的裁剪关系核查一致。对所有方法统一排除并集 31 个会话，得到 **504 个会话、981 个独立轮次**。正式报告同时列全量与这一共同子集。

审计复用已有训练指纹与实际使用清单，比较 1,588 张去重后的源／GT 图像。额外感知近邻核查未确认新增重合。冻结 SAMTok 底座是否实际使用本地 gRES 混合语料的每一条记录尚未核实；基础模型预训练和未记录来源不在审计范围。因此子集的含义是“在已审计清单中未发现重合”，不能写成“保证未训练”。图像核查为代理辅助目检，不声称独立人工标注。

证据位于共享包 `overlap/{OVERLAP.json,VISUAL_REVIEW.json}`；数据来源和全部原始哈希位于 `datasets/MagicBrush/SOURCE.json`。

## 3. 冒烟状态、耗时与显存

固定请求：`323789-1` 无 mask，`508582-1` 有 mask，以及 `323789-2` 连续无 mask。第三个请求是真实使用各方法上一轮输出的第二轮，不是该三轮会话的最终轮。选样与模型输出／得分无关。

| 方法 | 生成／评分 | 无 mask 秒/请求 | 有 mask 秒/请求 | 峰值 allocated / reserved（GiB） | 全量生成估计 GPU·h |
|---|---|---:|---:|---:|---:|
| SITEdit | 3/3；3/3 | 54.57 | 49.66 | 38.30 / 43.79 | 45.49 |
| Qwen-Image-2.1 | 3/3；3/3 | 44.07 | 44.47 | 19.71 / 22.21 | 38.64 |
| Qwen-Image-Edit-2511 | 3/3；3/3 | 75.12 | 130.85 | 57.98 / 58.73 | 89.88 |
| RePlan（Qwen2511） | 3/3；3/3 | 96.38 | 84.78 | 57.92 / 58.58 | 79.06 |
| MIRAGE（Qwen2511） | 3/3；3/3 | 80.16 | 80.94 | 57.98 / 58.94 | 70.30 |
| FLUX.3 Klein | 3/3；3/3 | 9.09 | 13.48 | 23.28 / 27.64 | 9.85 |
| MICE | 3/3；3/3 | 5.61 | 5.83 | 17.35 / 18.71 | 5.00 |
| FLUX.2 Klein-9B | 3/3；3/3 | 4.15 | 6.30 | 34.76 / 36.10 | 4.56 |

无 mask 耗时取两个固定请求的均值，有 mask 取一个请求；都包含该方法所需的规划／定位及编辑阶段，排除冷加载和文件 I/O。峰值是本进程 PyTorch allocated/reserved，未把既有共享进程约 1.6 GB 算进去。逐请求数值、加载时间、调用次数、实际参数和输出 SHA 均有原始记录；测量仅使用 GPU 4–7，且全部发生在 19:00 UTC 之后。

按每轨道每方法 1,571 个生成请求外推，合计 **342.77 GPU·小时**；32 卡理想时间 **10.71 小时**（当前四机队列约 **11.36 小时**），还需冷加载、I/O、免费评分和调度时间。这是三请求小样本外推，不是正式实测，也不是完成时间保证。

33 条阶段 admission 都有完成终态，24 张输出全部成功计分；17 个 worker 进程均正常退出。所有输出为可读的 1024×1024 图像。Qwen2.1 连续第二轮图像噪声较重，额外做了一次独立进程、相同输入和 seed 的诊断，raw 与恢复后图像均逐字节一致；未发现该例由跨请求状态引起。诊断独立保存，未覆盖冒烟结果，也未进入上述吞吐估计。

## 4. 样例观察与结论边界

- **观察：** `323789-1` 的“让人物大笑”指令下，多种基线形成明显笑容，SITEdit 的表情变化较弱；RePlan 也未达到与 GT 一样的明显笑容。
- **观察：** `508582-1` 中，SITEdit 改变了右侧公开 mask 内的披萨，但形态更像红色酱料；Qwen2.1、RePlan、MIRAGE 产生可辨识的圆形香肠片。Qwen2511 改动了左侧披萨；部分 Klein 输出的目标变化较弱。这些均按真实输出保留。
- **观察：** 连续编辑中，SITEdit、Qwen2511、MIRAGE、MICE 等输出了墙上地图；不同方法对上一轮效果的保留不同。拼图逐方法显示其真实前序输入，不以 GT 上一轮图替换。
- **统计结论：** 当前只能确认八方法、两种输入轨道及连续输入依赖均可执行，标准评分可用。三个请求不支持总体方法排名，正式全量与去重合结果仍待运行。
- **解释边界：** 整图相似度较高不等于每个局部编辑都正确；这些指标衡量的是像素／表征与参考的接近程度。当前样例不足以把现象归因于某个训练组件。本轮保留冻结方案，不做按分数或视觉效果的候选搜索。

实际插图与逐请求五指标在 NAS 的 `smoke_001/report/CHINESE_REPORT.md`、`REPORT.md` 中。图像不提交 Git；本机预览入口为 `/opt/tiger/tanyue/visualization_tmp/MagicBrush_20261105/README.md`。

## 5. 正式实验状态、路径与用户事项

**正式实验未启动，正式得分尚无。** 原因是实测外推超过本机 8 小时上限；剩余为八方法 25,136 个正式生成请求、免费评分、全量／去重合统计及报告。无付费 API；四机作业由用户提交。

| 内容 | 路径 |
|---|---|
| 分支 / worktree | `eval-magicbrush` / `/opt/tiger/tanyue/if-bench-magicbrush` |
| 数据 | `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/MagicBrush/` |
| 原始输入、重合审计、冒烟 | `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/magicbrush_20261105/` |
| 冒烟分数与插图报告 | 上述包内 `smoke_001/report/{CHINESE_REPORT.md,REPORT.md,REPORT.json}` |
| 时间外推 | 上述包内 `ESTIMATE.json` |
| 独立进程复核 | 上述包内 `diagnostics/qwen21_same_input_fresh_process/` |
| 正式结果（待用户启动后创建） | `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_magicbrush/run_001/` |
| 发布哈希、精确 commit、启动说明 | `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/magicbrush_4node32_nas_20261106-handoff.md` |

发布后，用户只需提交 **四机、每机 8×H100 80GB、同 NAS** 作业，前台执行 handoff 中的入口。恢复时只更换 attempt，不改结果根；已完成且身份一致的记录跳过，未知 admission 保留待核，不自动重采样。不需要访问授权、付费评分批准或模型参数决定。
