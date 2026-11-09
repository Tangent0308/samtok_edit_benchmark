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

已于 2026-11-09 06:39 UTC 完成生成、原生评分和配对统计；全部 200 条请求 × 两方法有效，生成/评分失败为 0，付费 API 调用为 0。本轮 GPU 任务已全部退出。

本 benchmark 的 24 项预设主比较中，SITEdit 有 9 项点估计更好；5 项同时满足改善量 95% 区间下界 > 0 和跨三个 benchmark 共 53 项比较的 Holm 校正 p < 0.05。计数仅用于完整陈述结果，不是新的综合分。

| 任务组 | 指标 | SITEdit | Base | 改善量（95% CI） | Holm p |
|---|---|---:|---:|---:|---:|
| all | LPIPS ↓ | 0.3492 | 0.3581 | +0.0088 [+0.0020, +0.0154] | 0.1829 |
| all | PSNR ↑ | 15.8597 | 16.1507 | -0.2910 [-0.5452, -0.0426] | 1.0000 |
| all | SSIM ↑ | 0.5279 | 0.5117 | +0.0162 [+0.0058, +0.0270] | 0.0374 |
| all | CLIP_I ↑ | 0.9050 | 0.9222 | -0.0171 [-0.0239, -0.0106] | 1.0000 |
| all | FG_LPIPS ↓ | 0.2217 | 0.2160 | -0.0056 [-0.0151, +0.0021] | 1.0000 |
| all | FG_CLIP_I ↑ | 0.8902 | 0.9086 | -0.0185 [-0.0262, -0.0113] | 1.0000 |
| all | BG_LPIPS ↓ | 0.2201 | 0.2379 | +0.0178 [+0.0130, +0.0224] | 0.0053 |
| all | BG_CLIP_I ↑ | 0.9097 | 0.9251 | -0.0155 [-0.0215, -0.0096] | 1.0000 |
| task/low | LPIPS ↓ | 0.3093 | 0.3245 | +0.0152 [+0.0068, +0.0233] | 0.0114 |
| task/low | PSNR ↑ | 16.9718 | 17.0544 | -0.0825 [-0.4344, +0.2744] | 1.0000 |
| task/low | SSIM ↑ | 0.5474 | 0.5279 | +0.0196 [+0.0082, +0.0320] | 0.0144 |
| task/low | CLIP_I ↑ | 0.9399 | 0.9426 | -0.0027 [-0.0085, +0.0030] | 1.0000 |
| task/low | FG_LPIPS ↓ | 0.2079 | 0.2024 | -0.0055 [-0.0229, +0.0085] | 1.0000 |
| task/low | FG_CLIP_I ↑ | 0.9307 | 0.9386 | -0.0079 [-0.0157, -0.0003] | 1.0000 |
| task/low | BG_LPIPS ↓ | 0.1998 | 0.2254 | +0.0255 [+0.0203, +0.0309] | 0.0053 |
| task/low | BG_CLIP_I ↑ | 0.9424 | 0.9448 | -0.0024 [-0.0081, +0.0035] | 1.0000 |
| task/high | LPIPS ↓ | 0.3891 | 0.3916 | +0.0025 [-0.0076, +0.0125] | 1.0000 |
| task/high | PSNR ↑ | 14.7475 | 15.2470 | -0.4995 [-0.7759, -0.2261] | 1.0000 |
| task/high | SSIM ↑ | 0.5083 | 0.4955 | +0.0128 [-0.0009, +0.0268] | 0.9099 |
| task/high | CLIP_I ↑ | 0.8701 | 0.9017 | -0.0316 [-0.0438, -0.0201] | 1.0000 |
| task/high | FG_LPIPS ↓ | 0.2365 | 0.2306 | -0.0059 [-0.0136, +0.0019] | 1.0000 |
| task/high | FG_CLIP_I ↑ | 0.8496 | 0.8787 | -0.0291 [-0.0423, -0.0168] | 1.0000 |
| task/high | BG_LPIPS ↓ | 0.2398 | 0.2500 | +0.0102 [+0.0023, +0.0180] | 0.2490 |
| task/high | BG_CLIP_I ↑ | 0.8779 | 0.9061 | -0.0282 [-0.0388, -0.0182] | 1.0000 |

改善量的正值统一表示 SITEdit 更好；低优指标采用 Base − SITEdit，高优指标采用 SITEdit − Base。区间为逐项 95% 区间，统计显著性采用预设 53 项主比较的单侧配对源图置换检验及 Holm 校正。分组内样本量与方法均值区间见完整报告。

### 结果分析

- 整体 SSIM 与背景 LPIPS 通过统一校正；low 指令组的全图 LPIPS、SSIM、背景 LPIPS 也通过校正。优势更集中于低复杂度指令下的感知/结构保真和背景保留。
- PSNR、CLIP-I 与前景 CLIP-I 的整体点估计由 Base 更高，high 组也呈现这种差异。因此本轮支持逐指标的能力取舍，而不是 Omni 所有指标上的整体领先。
- 该结果覆盖 100 个完整 low/high 源图配对；保持官方面积权重。官方 BG CLIP-I 的 RGB 处理使单例特征与全图 CLIP-I 相同，仅聚合权重不同，不能解释为另一项独立的背景语义证据。

### 报告、可视化与复现

- [完整逐项报告](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_omni_iie/validation_20261109/report/REPORT.md)
- [配对统计 JSON](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_omni_iie/validation_20261109/report/PAIRED_REPORT.json)；SHA256：`8fe0de89a377bdc5ca4922b6f450c6f5a444e9be0fbc74304fbc13adcee8f860`。
- [所有固定样本的真实输入输出对照](/opt/tiger/tanyue/visualization_tmp/ExternalValidation_20261109/omni_iie/INDEX.md)（按 case id 排序，无结果筛选）。
- [完整图册 HTML](/opt/tiger/tanyue/visualization_tmp/ExternalValidation_20261109/omni_iie/index.html)
- 清单：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_validation_20261109/omni_iie/SELECTION.json`；原生评分与生成：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_omni_iie/validation_20261109`。
- 生成源码提交：`1a9074dff51fc55a8db9bc106df13d8e8242b161`；计划 digest：`2366505216a28de87226e330cb8f097fc59b6f4e36e1ccc1866952497a71e075`。
- [像素级源图核验](/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_validation_20261109/audit/SOURCE_PIXELS.json)：分组与事前清单一致。

![Omni IIE 全部主比较的配对效应图](/opt/tiger/tanyue/visualization_tmp/ExternalValidation_20261109/omni_iie/PAIRED_EFFECTS.png)

图像文件保留在实验可视化目录，不提交模型输出或数据到 Git。`scripts/external_pair_report.py` 复算统计，`scripts/plot_external_pair.py` 渲染图表；两者不调用推理或 API。
