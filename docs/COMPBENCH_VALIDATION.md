# 扩大样本的独立配对验证

2026-11-09 用户确认：本机八卡比较固定 SITEdit aa5a414 主行与 Qwen-Image-2.1，仅使用官方客观指标，不调用付费 API。模型参数、输入映射、生成 seed 42、约 1MP 画布及原生评分均保持四机发布版不变。

## 事前固定方案

- CompBench：add/remove/replace/implicit/multi-object add/multi-object remove 各 30 条；multi-turn add/remove 各 15 个完整两轮链，共 240 条。第二轮输入同方法第一轮输出；action/location/view 不属于本轮范围。
- Inter-Edit：五类任务 × 中英文，每层 20 条，共 200 条。若抽到已确认的官方空 mask，原样保留并对两个方法一致记 data_input_invalid/N/A。
- Omni IIE：按数据来源比例固定抽取 100 个完整 low/high 配对，共 200 条；当前观察只代表这一配对子集，不代表所有公开单轮记录。
- 抽样 seed 20261109；从公开任务/语言/来源等元数据抽样。排除此前已分析 pilot 和冒烟中的源图（按已发布资产指纹），不读取模型输出或分数选择样本。清单、父子链和源图聚类在生成前冻结。
- 本轮新样本独立报告；旧 20 条结果保留为探索性材料，不混成新的独立验证结果。样本量固定，不根据结果扩样、重采样或提前停止。

## 分析口径

所有官方指标均报告原始点估计、覆盖率、SITEdit 相对 Base 的配对差值及 95% 区间；不构造自定义总分。CompBench 保留官方五组等权子任务汇总；Inter-Edit 报告整体和类别/语言；Omni 报告整体与 low/high，保留原生区域权重。

按源图进行 paired cluster bootstrap（10,000 次，seed 20261109）：两个方法共用抽样索引；同一源图的两轮/多个请求或 low/high 一起重采样，每次重算官方聚合。差值统一朝改善方向表示，并保留原指标方向。同步给出源图配对置换检验及 Holm 多重比较校正；正式主比较族事前固定为 CompBench 五组×五指标、Inter-Edit 整体四指标、Omni 整体/low/high×八指标。类别细分仅作诊断。失败和缺分保持完整应评分母，差值只用可配对有效分数并明确覆盖率，不填零。

可视化提供全部样本的输入/输出对照；用于正文分析的例子注明选取规则，不把个例或已知 pilot 当作泛化结论。

## 执行与文件

代码与文档放当前 eval 分支；临时配置/冻结清单证据/监控在 `.ifbench-tmp/external_validation_20261109/`。本轮固定样本正式结果写入 `experiments2/SAMTokEdit/external_<benchmark>/validation_20261109/`；图像预览位于 `/opt/tiger/tanyue/visualization_tmp/ExternalValidation_20261109/`。不修改四机 READY 包、其公开输入或既有正式结果。

本机 0–7 卡仅在每卡现有占用约 1.6 GiB、可用显存至少 70,000 MiB 时使用；不结束已有进程。采用独立本机入口复用冻结 worker，只有调度代码负责本次八卡授权。CPU 评分与下一模型生成重叠。

## 完成状态与结果

已于 2026-11-09 06:39 UTC 完成生成、原生评分和配对统计；全部 240 条请求 × 两方法有效，生成/评分失败为 0，付费 API 调用为 0。本轮 GPU 任务已全部退出。

本 benchmark 的 25 项预设主比较中，SITEdit 有 24 项点估计更好；12 项同时满足改善量 95% 区间下界 > 0 和跨三个 benchmark 共 53 项比较的 Holm 校正 p < 0.05。计数仅用于完整陈述结果，不是新的综合分。

| 任务组 | 指标 | SITEdit | Base | 改善量（95% CI） | Holm p |
|---|---|---:|---:|---:|---:|
| Local Editing | LC-T ↑ | 21.4605 | 20.7794 | +0.6811 [+0.1151, +1.2374] | 0.3480 |
| Local Editing | LC-I ↑ | 0.8497 | 0.8175 | +0.0322 [+0.0177, +0.0468] | 0.0078 |
| Local Editing | PSNR ↑ | 29.8751 | 26.1089 | +3.7662 [+2.2566, +5.2390] | 0.0053 |
| Local Editing | SSIM ↑ | 0.9552 | 0.8748 | +0.0804 [+0.0524, +0.1099] | 0.0053 |
| Local Editing | LPIPS ↓ | 0.0448 | 0.0583 | +0.0134 [-0.0023, +0.0264] | 0.9099 |
| Multi-object Editing | LC-T ↑ | 20.8663 | 20.2354 | +0.6309 [+0.0844, +1.1905] | 0.4266 |
| Multi-object Editing | LC-I ↑ | 0.8699 | 0.8537 | +0.0162 [-0.0043, +0.0365] | 1.0000 |
| Multi-object Editing | PSNR ↑ | 27.1897 | 27.1803 | +0.0094 [-1.4886, +1.4843] | 1.0000 |
| Multi-object Editing | SSIM ↑ | 0.9375 | 0.8784 | +0.0591 [+0.0191, +0.1043] | 0.1122 |
| Multi-object Editing | LPIPS ↓ | 0.0636 | 0.0566 | -0.0069 [-0.0252, +0.0100] | 1.0000 |
| Implicit Reasoning | LC-T ↑ | 20.0527 | 19.0943 | +0.9584 [-0.2096, +2.2177] | 1.0000 |
| Implicit Reasoning | LC-I ↑ | 0.8905 | 0.8365 | +0.0540 [+0.0245, +0.0832] | 0.0350 |
| Implicit Reasoning | PSNR ↑ | 32.2221 | 27.3069 | +4.9152 [+2.3902, +7.4674] | 0.0053 |
| Implicit Reasoning | SSIM ↑ | 0.9780 | 0.8788 | +0.0992 [+0.0616, +0.1451] | 0.0053 |
| Implicit Reasoning | LPIPS ↓ | 0.0181 | 0.0634 | +0.0453 [+0.0311, +0.0604] | 0.0053 |
| Multi-turn (Turn 1) | LC-T ↑ | 21.2605 | 21.0073 | +0.2532 [-0.5570, +1.0412] | 1.0000 |
| Multi-turn (Turn 1) | LC-I ↑ | 0.8493 | 0.8266 | +0.0227 [+0.0022, +0.0468] | 0.8215 |
| Multi-turn (Turn 1) | PSNR ↑ | 29.8615 | 27.8633 | +1.9982 [-0.7660, +4.5481] | 1.0000 |
| Multi-turn (Turn 1) | SSIM ↑ | 0.9687 | 0.8882 | +0.0805 [+0.0293, +0.1390] | 0.0114 |
| Multi-turn (Turn 1) | LPIPS ↓ | 0.0304 | 0.0433 | +0.0129 [+0.0010, +0.0234] | 0.4060 |
| Multi-turn (Turn 2) | LC-T ↑ | 21.7498 | 19.9060 | +1.8438 [+0.6030, +3.0830] | 0.1122 |
| Multi-turn (Turn 2) | LC-I ↑ | 0.8557 | 0.7787 | +0.0771 [+0.0494, +0.1028] | 0.0053 |
| Multi-turn (Turn 2) | PSNR ↑ | 24.9302 | 18.4308 | +6.4995 [+4.9631, +7.9520] | 0.0053 |
| Multi-turn (Turn 2) | SSIM ↑ | 0.9125 | 0.5086 | +0.4039 [+0.3480, +0.4627] | 0.0053 |
| Multi-turn (Turn 2) | LPIPS ↓ | 0.0745 | 0.2714 | +0.1968 [+0.1569, +0.2441] | 0.0053 |

改善量的正值统一表示 SITEdit 更好；低优指标采用 Base − SITEdit，高优指标采用 SITEdit − Base。区间为逐项 95% 区间，统计显著性采用预设 53 项主比较的单侧配对源图置换检验及 Holm 校正。分组内样本量与方法均值区间见完整报告。

### 结果分析

- 稳定提升集中在单目标局部编辑、隐式指令以及连续编辑第 2 轮。第 2 轮的 LC-I、PSNR、SSIM、LPIPS 均通过统一校正，说明在使用自身第一轮输出继续编辑的条件下，优势仍然保留。
- 多目标组的各项结果应分别阅读：4/5 项点估计朝 SITEdit 改善，LPIPS 的点估计由 Base 更好；该组各项均未通过本轮统一校正。
- 正式结论对应这 240 条固定新请求；action/location/view 未纳入，本轮结果不代表 3,481 条全量成绩。

### 报告、可视化与复现

- [完整逐项报告](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/validation_20261109/report/REPORT.md)
- [配对统计 JSON](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/validation_20261109/report/PAIRED_REPORT.json)；SHA256：`5f31ac3b27114d799bdc653ea2acbb875cfce420b6915011ce7a204f2fef6b9c`。
- [所有固定样本的真实输入输出对照](/opt/tiger/tanyue/visualization_tmp/ExternalValidation_20261109/compbench/INDEX.md)（按 case id 排序，无结果筛选）。
- [完整图册 HTML](/opt/tiger/tanyue/visualization_tmp/ExternalValidation_20261109/compbench/index.html)
- 清单：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_validation_20261109/compbench/SELECTION.json`；原生评分与生成：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/validation_20261109`。
- 生成源码提交：`1a9074dff51fc55a8db9bc106df13d8e8242b161`；计划 digest：`2366505216a28de87226e330cb8f097fc59b6f4e36e1ccc1866952497a71e075`。
- [像素级源图核验](/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_validation_20261109/audit/SOURCE_PIXELS.json)：分组与事前清单一致。

![CompBench 全部主比较的配对效应图](/opt/tiger/tanyue/visualization_tmp/ExternalValidation_20261109/compbench/PAIRED_EFFECTS.png)

图像文件保留在实验可视化目录，不提交模型输出或数据到 Git。`scripts/external_pair_report.py` 复算统计，`scripts/plot_external_pair.py` 渲染图表；两者不调用推理或 API。
