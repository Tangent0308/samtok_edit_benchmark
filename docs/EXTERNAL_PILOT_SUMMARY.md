# 八个外部 benchmark：SITEdit 与 Qwen-Image-2.1 小子集验证

带全部对比图的总报告：`/opt/tiger/tanyue/visualization_tmp/ExternalBenchPilots_20261107/REPORT.md`。图片保存在指定可视化目录，不提交到 Git。

固定 70 条请求、两方法各生成一次，共 140 个预定输出。抽样 seed 为 20261107，生成 seed 为 42。每个 benchmark 独立分支、固定输入后再生成和评分；不按结果换样、调参或挑选重采样。

SITEdit 为 aa5a414 冻结主行：Pass1 step2000、S2 adapter16000、raw SAMTok TE、40 步、token guidance 2；base 为 Qwen-Image-2.1 原生 40 步、CFG 1。两方法获得相同公开信息，约 1MP 画布，输出回源后再采用各 benchmark 的原生评分预处理。

涉及付费 Judge 的项目统一采用用户指定 GPT-5.4；保留各官方提示、证据与聚合定义。因此这是同协议重评的两模型对比，不能直接和使用其他 Judge 的论文数字混排。所有数值均来自实际输出和评分记录，没有估计填分。

这些是分层小子集观察，不是完整测试集排名或显著性结论。不同 benchmark 的指标不能相加为一个总分。

## 完成情况与分支

| 顺序 | Benchmark | 请求数 | SITEdit 出图 | Base 出图 | 主要验证内容 |
|---:|---|---:|---:|---:|---|
| 1 | [GIE-Bench](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-gie/docs/GIE_RESULTS.md) | 9 | 9/9 | 9/9 | 文字指令编辑的正确性与非编辑区域保持 |
| 2 | [CompBench](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-compbench/docs/COMPBENCH_RESULTS.md) | 8 | 8/8 | 8/8 | 多对象、隐含意图与组合编辑 |
| 3 | [ComplexBench-Edit](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-complexbench-edit/docs/COMPLEXBENCH_EDIT_RESULTS.md) | 10 | 10/10 | 10/10 | 并行多指令与链式指令 |
| 4 | [Inter-Edit](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-interedit/docs/INTEREDIT_RESULTS.md) | 8 | 8/8 | 8/8 | 公开 mask 引导的区域编辑 |
| 5 | [Complex-Edit](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-complex-edit/docs/COMPLEX_EDIT_RESULTS.md) | 8 | 8/8 | 8/8 | 同图不同复杂度的复合指令 |
| 6 | [GEdit-Bench](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-gedit/docs/GEDIT_RESULTS.md) | 11 | 11/11 | 11/11 | 十一类通用图像编辑 |
| 7 | [Omni IIE Bench](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-omni-iie/docs/OMNI_IIE_RESULTS.md) | 8 | 8/8 | 8/8 | 同图 low/high 配对的隐含意图编辑 |
| 8 | [GIDE-Bench](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-gide/docs/GIDE_RESULTS.md) | 8 | 8/8 | 8/8 | 文字、框、多边形指引的双目标编辑 |

独立核对：68 个汇总数值均由逐例评分复算一致；266 次实际 API 请求、778 个答案全部正常结束。[核对记录](/opt/tiger/tanyue/visualization_tmp/ExternalBenchPilots_20261107/AUDIT.json)。

## 这轮验证说明什么

- **CompBench 是本轮最明确的正向信号**：SITEdit 的局部文本/图像一致性与三项背景保持指标均优于 base。可以优先考虑扩大预先固定的样本规模来验证这一观察。
- **GIE 与 Inter-Edit 体现分项取舍**：SITEdit 的部分区域外保持指标更好，但编辑正确性或区域内目标相似度并未同时领先，不能用保持分数替代任务成功。
- **Omni IIE 的结果也是混合的**：SITEdit 的 LPIPS、SSIM、BG LPIPS 更好；base 的全图/前景 CLIP 相似度等指标更好。缺少 QA 的本轮结果不足以直接衡量隐含意图是否全部完成。
- **ComplexBench-Edit、Complex-Edit、GEdit-Bench 与 GIDE 的主要指令/综合评分为 base 较高**。保留全部固定样例，没有隐藏较低分项目。这一观察只适用于当前冻结输入适配与小子集。
- 本轮不选择新 checkpoint、不改 token guidance、不尝试多个 prompt 后择优。后续若扩大评测，应先确定完整协议和样本，不能把本轮子集当作完整 benchmark 报分。

## 已确认的协议边界

- CompBench 仅选官方可评分的六类；action/location/view 未被这轮 8 条请求覆盖。
- Inter-Edit 保留四项不依赖 reference_image 的客观指标；缺参考图的指标及 VLM 为 N/A。
- Omni IIE 保留八项官方可运行指标；QA 和 Overall 为 N/A，不生成额外问题。其 BG_CLIP-I 实现会丢弃遮罩 alpha，含义需按下文说明解读。
- GIE 原始 MSE/PSNR 的阈值行为照官方代码保留，不误称为背景分数。
- Qwen2.1 的部分区域提示输出原生带透明背景；所有输出按已固定的 RGB 回源/评分口径处理，不回贴源图、不补背景。原始 RGBA 与独立诊断保留。
- 所有数据采用官方发布源和固定版本。未借用训练标注或私有评测信息增强生成；门控数据仅在用户授权后下载。

## 各项实际分数

↑ 越高越好，↓ 越低越好；加粗仅表示当前小子集的较优数值，不表示统计显著。

### GIE-Bench（9 条）

| 指标 | SITEdit | Qwen-Image-2.1 | 有效评分数（各方法） |
|---|---:|---:|---:|
| 编辑正确率 ↑ | 0.4444 | **0.5556** | 9/9；9/9 |
| 区域外 CLIP ↑ | **0.9868** | 0.9835 | 9/9；9/9 |
| 区域外 SSIM ↑ | **0.9817** | 0.9404 | 9/9；9/9 |
| 官方 MSE ↓ | **774.7253** | 1155.0131 | 9/9；9/9 |
| 官方 PSNR ↑ | **20.3889** | 18.8291 | 9/9；9/9 |

- GIE 官方 MSE/PSNR 代码对 0/1 mask 使用 <128 阈值，实际覆盖全图；不把这两项称作背景指标。

- 结果文件：[GIE-Bench REPORT.json](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_gie/pilot_20261107/report/REPORT.json)。
- 评测代码与输入说明：[eval-gie](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-gie/docs/GIE_EVALUATION.md)。
- [全部请求的图文对比](/opt/tiger/tanyue/visualization_tmp/GIE-Bench_20261107/REPORT.md)。

### CompBench（8 条）

| 指标 | SITEdit | Qwen-Image-2.1 | 有效评分数（各方法） |
|---|---:|---:|---:|
| 局部 CLIP-T ↑ | **20.6279** | 19.2590 | 8/8；8/8 |
| 局部 CLIP-I ↑ | **0.8604** | 0.8533 | 8/8；8/8 |
| 背景 PSNR ↑ | **28.4617** | 28.3005 | 8/8；8/8 |
| 背景 SSIM ↑ | **0.9377** | 0.9247 | 8/8；8/8 |
| 背景 LPIPS ↓ | **0.0418** | 0.0505 | 8/8；8/8 |

- 使用官方 eval_all.py：512×512、CLIP ViT-L/14、LPIPS squeeze；原始 mask/目标图只进入评分。
- 用户确认六个可评分类别共 8 条；action/location/view 缺少官方 mask/评分实现，不在本轮范围。
- 多目标指令作为完整公开指令输入，一次 Pass1 和一次联合编辑，不按目标串行编辑。
- 背景误差保留官方将编辑区置零后在全图求值的定义。

- 结果文件：[CompBench REPORT.json](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/pilot_20261107/report/REPORT.json)。
- 评测代码与输入说明：[eval-compbench](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-compbench/docs/COMPBENCH_EVALUATION.md)。
- [全部请求的图文对比](/opt/tiger/tanyue/visualization_tmp/CompBench_20261107/REPORT.md)。

### ComplexBench-Edit（10 条）

| 指标 | SITEdit | Qwen-Image-2.1 | 有效评分数（各方法） |
|---|---:|---:|---:|
| 指令得分 ↑ | 0.4004 | **0.6692** | 10/10；10/10 |
| 区域外 L1 ↓ | **0.0564** | 0.0737 | 10/10；10/10 |
| 区域外 L2 ↓ | 0.0278 | **0.0265** | 10/10；10/10 |

- 五组各 2 条，公开的原始多行指令作为三个联合目标；一次定位和一次联合编辑。
- 指令评分使用官方 rubric 与依赖聚合规则；GPT-5.4 替代 Gemini。
- L1/L2 的源图目标框由官方 GroundingDINO 评分流程产生，仅用于评分。

- 结果文件：[ComplexBench-Edit REPORT.json](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_complexbench_edit/pilot_20261107/report/REPORT.json)。
- 评测代码与输入说明：[eval-complexbench-edit](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-complexbench-edit/docs/COMPLEXBENCH_EDIT_EVALUATION.md)。
- [全部请求的图文对比](/opt/tiger/tanyue/visualization_tmp/ComplexBench-Edit_20261107/REPORT.md)。

### Inter-Edit（8 条）

| 指标 | SITEdit | Qwen-Image-2.1 | 有效评分数（各方法） |
|---|---:|---:|---:|
| 全图 LPIPS ↓ | 0.2342 | **0.2207** | 8/8；8/8 |
| 区域内 AlphaCLIP ↑ | 0.9642 | **0.9784** | 8/8；8/8 |
| 区域外 AlphaCLIP ↑ | **0.9756** | 0.9725 | 8/8；8/8 |
| BSS ↓ | **3.0413** | 13.5732 | 8/8；8/8 |

- 原始公开 mask 同时提供给两方法，SITEdit 直接用原生 codec 编码，不调用 Pass1 定位。
- 四项均为官方客观指标，AlphaCLIP ViT-L/14 grit1m 8xe，LPIPS-alex。
- S_ref_AlphaCLIP / VLM 为 N/A：官方数据缺少 reference_image，用户已确认该口径。

- 结果文件：[Inter-Edit REPORT.json](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_interedit/pilot_20261107/report/REPORT.json)。
- 评测代码与输入说明：[eval-interedit](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-interedit/docs/INTEREDIT_EVALUATION.md)。
- [全部请求的图文对比](/opt/tiger/tanyue/visualization_tmp/Inter-Edit_20261107/REPORT.md)。

### Complex-Edit（8 条）

| 指标 | SITEdit | Qwen-Image-2.1 | 有效评分数（各方法） |
|---|---:|---:|---:|
| IF ↑ | 8.4625 | **9.6687** | 8/8；8/8 |
| IP ↑ | 6.9875 | **7.4688** | 8/8；8/8 |
| PQ ↑ | 7.5375 | **8.3562** | 8/8；8/8 |
| Overall ↑ | 7.6625 | **8.4979** | 8/8；8/8 |

- real/syn 各 1 张原图，在 K=1/2/4/8 的原始复合指令上评测；不是 8 张独立源图。
- 两模型只获得公开 compound_instruction，不用私有 sequence/reasoning 或外部指令拆分。
- 官方提示与结构化评分，GPT-5.4；每项每输出重复 20 次后平均，全部保留。
- IF/IP/PQ 范围 0–10，Overall 为三项平均。

- 结果文件：[Complex-Edit REPORT.json](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_complex_edit/pilot_20261107/report/REPORT.json)。
- 评测代码与输入说明：[eval-complex-edit](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-complex-edit/docs/COMPLEX_EDIT_EVALUATION.md)。
- [全部请求的图文对比](/opt/tiger/tanyue/visualization_tmp/Complex-Edit_20261107/REPORT.md)。

### GEdit-Bench（11 条）

| 指标 | SITEdit | Qwen-Image-2.1 | 有效评分数（各方法） |
|---|---:|---:|---:|
| 语义一致 SC ↑ | 6.6364 | **7.9091** | 11/11；11/11 |
| 感知质量 PQ ↑ | 6.7273 | **7.7273** | 11/11；11/11 |
| Overall ↑ | 6.6295 | **7.7214** | 11/11；11/11 |

- 英文 11 类各 1 条，使用 input_image_raw 与原始公开指令。
- 使用官方 VIEScore 提示、图像预处理和 min/几何平均聚合，GPT-5.4 替代官方 GPT-4.1。
- 范围 0–10；SC/PQ 各取子分最小值，Overall=√(SC×PQ)。解析失败不猜随机分。

- 结果文件：[GEdit-Bench REPORT.json](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_gedit/pilot_20261107/report/REPORT.json)。
- 评测代码与输入说明：[eval-gedit](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-gedit/docs/GEDIT_EVALUATION.md)。
- [全部请求的图文对比](/opt/tiger/tanyue/visualization_tmp/GEdit-Bench_20261107/REPORT.md)。

### Omni IIE Bench（8 条）

| 指标 | SITEdit | Qwen-Image-2.1 | 有效评分数（各方法） |
|---|---:|---:|---:|
| LPIPS ↓ | **0.3236** | 0.3637 | 8/8；8/8 |
| PSNR ↑ | 17.7153 | **17.8766** | 8/8；8/8 |
| SSIM ↑ | **0.5446** | 0.5246 | 8/8；8/8 |
| CLIP-I ↑ | 0.9092 | **0.9366** | 8/8；8/8 |
| FG LPIPS ↓ | 0.0962 | **0.0908** | 8/8；8/8 |
| FG CLIP-I ↑ | 0.9046 | **0.9294** | 8/8；8/8 |
| BG LPIPS ↓ | **0.2495** | 0.2890 | 8/8；8/8 |
| BG CLIP-I ↑ | 0.9061 | **0.9358** | 8/8；8/8 |

- 四个完整 high/low 配对，共 8 请求；区域 mask 与目标图均仅用于评分。
- 官方固定 768×768 评分，LPIPS-vgg、CLIP ViT-B/32。BG LPIPS/CLIP 和 FG LPIPS 按原生区域面积权重聚合，其余逐例平均。
- 官方 BG_CLIP_I 仅把背景 mask 写入 alpha，CLIPProcessor 转 RGB 后忽略 alpha；逐例与全图 CLIP-I 相同，汇总使用背景面积权重。保留原实现，不将它解释为独立的纯背景指标。
- QA 和 Overall 均 N/A：发布数据及官方可执行入口缺少 QA，用户已确认；不自行造题。

- 结果文件：[Omni IIE Bench REPORT.json](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_omni_iie/pilot_20261107/report/REPORT.json)。
- 评测代码与输入说明：[eval-omni-iie](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-omni-iie/docs/OMNI_IIE_EVALUATION.md)。
- [全部请求的图文对比](/opt/tiger/tanyue/visualization_tmp/OmniIIEBench_20261107/REPORT.md)。

### GIDE-Bench（8 条）

| 指标 | SITEdit | Qwen-Image-2.1 | 有效评分数（各方法） |
|---|---:|---:|---:|
| 指令遵循 ↑ | 3.5000 | **4.0000** | 8/8；8/8 |
| 视觉自然度 ↑ | 3.1875 | **3.2500** | 8/8；8/8 |

- 公开 polygon 2、xywh box 2、text 4，共 8 条，覆盖六种编辑组合。
- SITEdit 通过原生 codec/box locator/文字定位处理公开区域；一次联合 Pass1、一次联合 S2。
- Judge 保留官方 evaluation 指令和两编辑评分规则，GPT-5.4 替代 GPT-5.1；两项范围均为 1–5。
- 原始 RGBA 另行保留；RGB 评分中的部分紫色背景来自原生预测的透明区域，没有回贴源图或补背景。该现象需与指令遵循得分一起分析。

- 结果文件：[GIDE-Bench REPORT.json](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_gide/pilot_20261107/report/REPORT.json)。
- 评测代码与输入说明：[eval-gide](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-gide/docs/GIDE_EVALUATION.md)。
- [全部请求的图文对比](/opt/tiger/tanyue/visualization_tmp/GIDE-Bench_20261107/REPORT.md)。

## 运行开销

| Benchmark | SITEdit 平均编辑秒数 | Base 平均编辑秒数 | SITEdit / Base 峰值 allocated GiB |
|---|---:|---:|---:|
| GIE-Bench | 48.73 | 41.01 | 38.23 / 19.14 |
| CompBench | 48.93 | 40.73 | 38.31 / 19.10 |
| ComplexBench-Edit | 49.40 | 39.51 | 38.34 / 19.10 |
| Inter-Edit | 48.54 | 42.59 | 38.30 / 19.78 |
| Complex-Edit | 49.06 | 41.95 | 38.37 / 19.10 |
| GEdit-Bench | 48.12 | 40.70 | 38.27 / 19.12 |
| Omni IIE Bench | 48.68 | 41.57 | 38.23 / 19.13 |
| GIDE-Bench | 48.35 | 41.30 | 38.39 / 19.13 |

以上仅为实测编辑调用，不含权重加载；SITEdit 的额外 Pass1 或 codec 阶段另存逐阶段收据。峰值是 PyTorch allocated，不含同卡其他任务。GPU 只使用用户允许且空闲的 4–7；评分使用 CPU 或授权 API。

## 可追溯证据

汇总读取各分支独立保存的 REPORT.json。完整输入、逐例输出、评分原文、失败和配置身份均在各结果根；SOURCE.json 和 SUBSET.json 位于对应 NAS 数据目录。

| Benchmark | REPORT.json SHA256 |
|---|---|
| GIE-Bench | `a6f67d365dcee8646a5e283b70efe12162a490c3f1944547dcf2fa9f30210361` |
| CompBench | `53c4f880d8900b7a7021476b2a873ed366e2e1eb49873b775dcbf431d10cbc90` |
| ComplexBench-Edit | `edc034159420f321131fffe68f973372d4a865e32a9a59f2ead9c8006fefa5cf` |
| Inter-Edit | `181e40e0b6bc6d1923769053ba889aa97651c386c9185bff5923b978bf039e9d` |
| Complex-Edit | `8a7b2d68561bd5b0c96e50ed3c54c3ebdb89849b5c59f360b75d4835da673b68` |
| GEdit-Bench | `d9662c22b4191c97a739b70be2ac4002a87a154b74d29b5b5e97ff3832116cce` |
| Omni IIE Bench | `cafc68ad8613241c4401d51c6e6bd45bdb71bc2547dfafe5b93c812dbc576fa8` |
| GIDE-Bench | `48dca58eb55993be58eb60edbfde59f9622ba587c45e0616e92303cdcd50d03b` |
