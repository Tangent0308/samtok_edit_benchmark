# 八个外部 benchmark：约二十条扩展对比

本轮固定 164 条请求 / 方法，SITEdit 与 Qwen-Image-2.1 共 328 个预定输出。原 70 条 / 方法的结果只读复用，新增 94 条 / 方法；没有重新生成旧样本，没有重新判分旧答案。

SITEdit 固定 aa5a414、Pass1 step2000、S2 adapter16000、raw SAMTok TE、40 步、token guidance 2；底座为 Qwen-Image-2.1、40 步、CFG 1。生成 seed 42，抽样 seed 20261107。所有新样本在生成前固定，各方法输入与评分口径保持不变。

## 代表性指标速查

此表便于定位各项目的主要观察；完整指标在下文，不把不同 benchmark 的分数合成总分。↑ 越高越好，↓ 越低越好。

| Benchmark | 请求数 | 指标 | SITEdit | Qwen-Image-2.1 |
|---|---:|---|---:|---:|
| GIE-Bench | 18 | 编辑正确率 ↑ | 0.6667 | 0.7778 |
| CompBench | 20 | 局部 CLIP-T ↑ | 21.0700 | 20.0940 |
| ComplexBench-Edit | 20 | 指令得分 ↑ | 0.3958 | 0.5700 |
| Inter-Edit | 20 | 区域内 AlphaCLIP ↑ | 0.9730 | 0.9680 |
| Complex-Edit | 24 | Overall ↑ | 7.6674 | 8.4472 |
| GEdit-Bench | 22 | Overall ↑ | 6.7348 | 7.7097 |
| Omni IIE Bench | 20 | LPIPS ↓ | 0.3138 | 0.3730 |
| GIDE-Bench | 20 | 指令遵循 ↑ | 3.7250 | 3.7250 |

请求数按原有分层保持平衡：GIE 为 9 类 × 2；GEdit 为 11 类 × 2；Complex-Edit 为 6 张源图 × K=1/2/4/8，共 24 条；Omni IIE 为 10 张源图的 high/low 配对，共 20 条。其余各 20 条。配对或不同复杂度请求不算独立源图。

本轮为分层小样本比较，不代表全量测试集排名或统计显著性。CompBench 本轮仍为六类单轮客观指标，速查表为固定子集的逐请求均值，各任务分项保存在 JSON 的 groups 中；与按任务汇总的正式全量运行分别报告。

Inter-Edit 仍为公开 mask 与四项客观指标；Omni IIE 仍为 high/low 配对的八项客观指标，QA/Overall 为 N/A。涉及 VLM 的 benchmark 统一使用用户指定 GPT-5.4，保留官方提示、证据、测量次数和聚合，不能直接与不同 Judge 的论文数字混排。

## 两方法的比较观察

- **GIE-Bench**：SITEdit 较高/较优的指标为 区域外 CLIP ↑、区域外 SSIM ↑、官方 MSE ↓、官方 PSNR ↑；底座较高/较优的指标为 编辑正确率 ↑。
- **CompBench**：SITEdit 较高/较优的指标为 局部 CLIP-T ↑、局部 CLIP-I ↑、背景 PSNR ↑、背景 SSIM ↑、背景 LPIPS ↓。
- **ComplexBench-Edit**：SITEdit 较高/较优的指标为 区域外 L1 ↓、区域外 L2 ↓；底座较高/较优的指标为 指令得分 ↑。
- **Inter-Edit**：SITEdit 较高/较优的指标为 全图 LPIPS ↓、区域内 AlphaCLIP ↑、区域外 AlphaCLIP ↑、BSS ↓。
- **Complex-Edit**：底座较高/较优的指标为 IF ↑、IP ↑、PQ ↑、Overall ↑。
- **GEdit-Bench**：底座较高/较优的指标为 语义一致 SC ↑、感知质量 PQ ↑、Overall ↑。
- **Omni IIE Bench**：SITEdit 较高/较优的指标为 LPIPS ↓、PSNR ↑、SSIM ↑、BG LPIPS ↓；底座较高/较优的指标为 CLIP-I ↑、FG LPIPS ↓、FG CLIP-I ↑、BG CLIP-I ↑。
- **GIDE-Bench**：SITEdit 较高/较优的指标为 视觉自然度 ↑；均值相同的指标为 指令遵循 ↑。

这些是相同固定请求上的分数观察。背景保持、参考图相似度与指令完成度衡量的内容不同，不能仅凭一项指标较优就判定方法全面更好；本轮不进行跨 benchmark 混合排名。

## 完整分数与逐例图

### GIE-Bench（18 条）

| 指标 | SITEdit | Qwen-Image-2.1 | 有效数（SITEdit / Base） |
|---|---:|---:|---|
| 编辑正确率 ↑ | 0.6667 | **0.7778** | 18/18；18/18 |
| 区域外 CLIP ↑ | **0.9830** | 0.9802 | 18/18；18/18 |
| 区域外 SSIM ↑ | **0.9688** | 0.9214 | 18/18；18/18 |
| 官方 MSE ↓ | **952.6646** | 1346.8982 | 18/18；18/18 |
| 官方 PSNR ↑ | **20.7558** | 18.9299 | 18/18；18/18 |

- Published MSE/PSNR threshold selects all pixels on released 0/1 masks; these are not corrected background scores.

- [原始报告与逐例绑定](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_gie/pilot20_20261108/report/REPORT.json)。
- [全部输入输出对照](/opt/tiger/tanyue/visualization_tmp/ExternalPilot20_20261108/gie/REPORT.md)。



### CompBench（20 条）

| 指标 | SITEdit | Qwen-Image-2.1 | 有效数（SITEdit / Base） |
|---|---:|---:|---|
| 局部 CLIP-T ↑ | **21.0700** | 20.0940 | 20/20；20/20 |
| 局部 CLIP-I ↑ | **0.8749** | 0.8589 | 20/20；20/20 |
| 背景 PSNR ↑ | **28.3745** | 27.1399 | 20/20；20/20 |
| 背景 SSIM ↑ | **0.9501** | 0.8771 | 20/20；20/20 |
| 背景 LPIPS ↓ | **0.0445** | 0.0584 | 20/20；20/20 |

- 使用官方 eval_all.py：512×512、CLIP ViT-L/14、LPIPS squeeze；原始 mask/目标图只进入评分。
- 多目标指令作为完整公开指令输入，一次 Pass1 和一次联合编辑，不按目标串行编辑。
- 背景误差保留官方将编辑区置零后在全图求值的定义。

- [原始报告与逐例绑定](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/pilot20_20261108/report/REPORT.json)。
- [全部输入输出对照](/opt/tiger/tanyue/visualization_tmp/ExternalPilot20_20261108/compbench/REPORT.md)。



### ComplexBench-Edit（20 条）

| 指标 | SITEdit | Qwen-Image-2.1 | 有效数（SITEdit / Base） |
|---|---:|---:|---|
| 指令得分 ↑ | 0.3958 | **0.5700** | 20/20；20/20 |
| 区域外 L1 ↓ | **0.0466** | 0.0733 | 20/20；20/20 |
| 区域外 L2 ↓ | **0.0202** | 0.0222 | 20/20；20/20 |

- 指令评分使用官方 rubric 与依赖聚合规则；GPT-5.4 替代 Gemini。
- L1/L2 的源图目标框由官方 GroundingDINO 评分流程产生，仅用于评分。

- [原始报告与逐例绑定](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_complexbench_edit/pilot20_20261108/report/REPORT.json)。
- [全部输入输出对照](/opt/tiger/tanyue/visualization_tmp/ExternalPilot20_20261108/complexbench_edit/REPORT.md)。



### Inter-Edit（20 条）

| 指标 | SITEdit | Qwen-Image-2.1 | 有效数（SITEdit / Base） |
|---|---:|---:|---|
| 全图 LPIPS ↓ | **0.2316** | 0.2580 | 20/20；20/20 |
| 区域内 AlphaCLIP ↑ | **0.9730** | 0.9680 | 20/20；20/20 |
| 区域外 AlphaCLIP ↑ | **0.9791** | 0.9680 | 20/20；20/20 |
| BSS ↓ | **2.9655** | 21.3317 | 20/20；20/20 |

- 原始公开 mask 同时提供给两方法，SITEdit 直接用原生 codec 编码，不调用 Pass1 定位。
- 四项均为官方客观指标，AlphaCLIP ViT-L/14 grit1m 8xe，LPIPS-alex。
- S_ref_AlphaCLIP / VLM 为 N/A：官方数据缺少 reference_image，用户已确认该口径。

- [原始报告与逐例绑定](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_interedit/pilot20_20261108/report/REPORT.json)。
- [全部输入输出对照](/opt/tiger/tanyue/visualization_tmp/ExternalPilot20_20261108/interedit/REPORT.md)。



### Complex-Edit（24 条）

| 指标 | SITEdit | Qwen-Image-2.1 | 有效数（SITEdit / Base） |
|---|---:|---:|---|
| IF ↑ | 8.8771 | **9.8083** | 24/24；24/24 |
| IP ↑ | 6.3750 | **6.9958** | 24/24；24/24 |
| PQ ↑ | 7.7500 | **8.5375** | 24/24；24/24 |
| Overall ↑ | 7.6674 | **8.4472** | 24/24；24/24 |

- real 3 张、syn 3 张原图，在 K=1/2/4/8 的原始复合指令上评测；共 24 条请求、6 张独立源图。
- 两模型只获得公开 compound_instruction，不用私有 sequence/reasoning 或外部指令拆分。
- 官方提示与结构化评分，GPT-5.4；每项每输出重复 20 次后平均，全部保留。
- IF/IP/PQ 范围 0–10，Overall 为三项平均。

- [原始报告与逐例绑定](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_complex_edit/pilot20_20261108/report/REPORT.json)。
- [全部输入输出对照](/opt/tiger/tanyue/visualization_tmp/ExternalPilot20_20261108/complex_edit/REPORT.md)。



### GEdit-Bench（22 条）

| 指标 | SITEdit | Qwen-Image-2.1 | 有效数（SITEdit / Base） |
|---|---:|---:|---|
| 语义一致 SC ↑ | 7.1364 | **8.2727** | 22/22；22/22 |
| 感知质量 PQ ↑ | 6.6364 | **7.3636** | 22/22；22/22 |
| Overall ↑ | 6.7348 | **7.7097** | 22/22；22/22 |

- 英文 11 类各 2 条，使用 input_image_raw 与原始公开指令。
- 使用官方 VIEScore 提示、图像预处理和 min/几何平均聚合，GPT-5.4 替代官方 GPT-4.1。
- 范围 0–10；SC/PQ 各取子分最小值，Overall=√(SC×PQ)。解析失败不猜随机分。

- [原始报告与逐例绑定](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_gedit/pilot20_20261108/report/REPORT.json)。
- [全部输入输出对照](/opt/tiger/tanyue/visualization_tmp/ExternalPilot20_20261108/gedit/REPORT.md)。



### Omni IIE Bench（20 条）

| 指标 | SITEdit | Qwen-Image-2.1 | 有效数（SITEdit / Base） |
|---|---:|---:|---|
| LPIPS ↓ | **0.3138** | 0.3730 | 20/20；20/20 |
| PSNR ↑ | **17.8748** | 17.7359 | 20/20；20/20 |
| SSIM ↑ | **0.5997** | 0.5706 | 20/20；20/20 |
| CLIP-I ↑ | 0.9179 | **0.9278** | 20/20；20/20 |
| FG LPIPS ↓ | 0.2013 | **0.1801** | 20/20；20/20 |
| FG CLIP-I ↑ | 0.8997 | **0.9186** | 20/20；20/20 |
| BG LPIPS ↓ | **0.2468** | 0.3055 | 20/20；20/20 |
| BG CLIP-I ↑ | 0.9189 | **0.9271** | 20/20；20/20 |

- 官方固定 768×768 评分，LPIPS-vgg、CLIP ViT-B/32。BG LPIPS/CLIP 和 FG LPIPS 按原生区域面积权重聚合，其余逐例平均。
- 官方 BG_CLIP_I 仅把背景 mask 写入 alpha，CLIPProcessor 转 RGB 后忽略 alpha；逐例与全图 CLIP-I 相同，汇总使用背景面积权重。保留原实现，不将它解释为独立的纯背景指标。
- QA 和 Overall 均 N/A：发布数据及官方可执行入口缺少 QA，用户已确认；不自行造题。

- [原始报告与逐例绑定](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_omni_iie/pilot20_20261108/report/REPORT.json)。
- [全部输入输出对照](/opt/tiger/tanyue/visualization_tmp/ExternalPilot20_20261108/omni_iie/REPORT.md)。



### GIDE-Bench（20 条）

| 指标 | SITEdit | Qwen-Image-2.1 | 有效数（SITEdit / Base） |
|---|---:|---:|---|
| 指令遵循 ↑ | 3.7250 | 3.7250 | 20/20；20/20 |
| 视觉自然度 ↑ | **3.5500** | 3.1500 | 20/20；20/20 |

- SITEdit 通过原生 codec/box locator/文字定位处理公开区域；一次联合 Pass1、一次联合 S2。
- Judge 保留官方 evaluation 指令和两编辑评分规则，GPT-5.4 替代 GPT-5.1；两项范围均为 1–5。
- 原始 RGBA 另行保留；RGB 评分中的部分紫色背景来自原生预测的透明区域，没有回贴源图或补背景。该现象需与指令遵循得分一起分析。

- [原始报告与逐例绑定](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_gide/pilot20_20261108/report/REPORT.json)。
- [全部输入输出对照](/opt/tiger/tanyue/visualization_tmp/ExternalPilot20_20261108/gide/REPORT.md)。



## 覆盖率与实际开销

| Benchmark | SITEdit 出图 | Base 出图 | 新增 API 响应 |
|---|---:|---:|---:|
| GIE-Bench | 18/18 | 18/18 | 18 |
| CompBench | 20/20 | 20/20 | 0 |
| ComplexBench-Edit | 20/20 | 20/20 | 60 |
| Inter-Edit | 20/20 | 20/20 | 0 |
| Complex-Edit | 24/24 | 24/24 | 256 |
| GEdit-Bench | 22/22 | 22/22 | 44 |
| Omni IIE Bench | 20/20 | 20/20 | 0 |
| GIDE-Bench | 20/20 | 20/20 | 24 |

实际新增 API 响应 402 次、1426 个答案；旧新合计 668 次、2204 个答案。异常文件 0，受理未作答 0。具体异常及覆盖率按各报告记录，不填零或过滤。

独立从原始逐例分数重算 68 个汇总值，均与报告一致。Omni 区域指标按原生面积权重重新累计；其他指标逐例计算，不平均两个阶段的均值。

[完整核对记录](/opt/tiger/tanyue/visualization_tmp/ExternalPilot20_20261108/AUDIT.json)。方法源码、配置、public、bundle、受理、输出和评分绑定已在各报告生成时核验。

## 工程问题与处理

CompBench 首次 CPU 评分因 TorchMetrics 对 CLIP 路径名称的检查而退出；改用已有 openai/clip-vit-large-patch14 别名后完成。已核对权重和预处理文件字节相同，只重新启动尚未完成的 CPU 评分，没有重新生成。原失败日志保留。

Complex-Edit、GEdit 的派生报告曾沿用上轮样本数量的文字说明；已根据本轮固定清单修正，旧派生报告存入独立诊断目录。修正前后除 notes 外所有 JSON 字段完全一致，生成与原始评分记录均未改动。
