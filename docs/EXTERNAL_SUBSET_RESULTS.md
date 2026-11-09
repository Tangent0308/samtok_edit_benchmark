# 固定子集：新增方法对比结果

使用此前固定的同一批 CompBench 240 条、Inter-Edit 200 条和 Omni IIE 100 对 low/high（200 条）请求。SITEdit 与 Qwen-Image-2.1 原始结果逐条校验复用；新增方法不改变样本、输入或原生评分。表中粗体为相应指标最优点估计；↑ 越大越好，↓ 越小越好。

按用户最新要求，剩余请求以最多四张空闲 GPU 续跑，保留此前已完成记录；评分使用 CPU，没有付费 API 调用。完整均值区间、分组、来源和运行开销见各 benchmark 的报告。

## CompBench

LC-T/LC-I 衡量局部指令/目标一致性；PSNR、SSIM、LPIPS 衡量非编辑区域保持。每组按官方规则对所含子任务等权聚合。连续第二轮使用该方法第一轮的实际输出。

| 组别 | 方法 | 有效/应评 | LC-T ↑ | LC-I ↑ | PSNR ↑ | SSIM ↑ | LPIPS ↓ |
|---|---|---:|---:|---:|---:|---:|---:|
| 局部编辑 | FLUX.2 Klein-9B | 90/90 | 21.64 | **0.8513** | 26.76 | 0.9475 | 0.0484 |
| 局部编辑 | MICE | 90/90 | **21.70** | 0.8420 | 23.32 | 0.9355 | 0.0579 |
| 局部编辑 | RePlan | 90/90 | 20.72 | 0.8334 | 29.45 | 0.9418 | 0.0490 |
| 局部编辑 | Qwen-Image-2.1 | 90/90 | 20.78 | 0.8175 | 26.11 | 0.8748 | 0.0583 |
| 局部编辑 | **SITEdit** | 90/90 | 21.46 | 0.8497 | **29.88** | **0.9552** | **0.0448** |
| 多目标编辑 | FLUX.2 Klein-9B | 60/60 | **20.92** | 0.8888 | 24.75 | 0.9339 | 0.0603 |
| 多目标编辑 | MICE | 60/60 | 20.83 | 0.8762 | 21.99 | 0.9293 | 0.0642 |
| 多目标编辑 | RePlan | 60/60 | 20.04 | **0.8921** | **30.38** | **0.9549** | **0.0358** |
| 多目标编辑 | Qwen-Image-2.1 | 60/60 | 20.24 | 0.8537 | 27.18 | 0.8784 | 0.0566 |
| 多目标编辑 | **SITEdit** | 60/60 | 20.87 | 0.8699 | 27.19 | 0.9375 | 0.0636 |
| 隐式指令 | FLUX.2 Klein-9B | 30/30 | 19.85 | 0.8862 | 23.86 | 0.9235 | 0.0731 |
| 隐式指令 | MICE | 30/30 | **20.33** | 0.8918 | 23.28 | 0.9388 | 0.0596 |
| 隐式指令 | RePlan | 30/30 | 19.61 | **0.8957** | 29.32 | 0.9445 | 0.0505 |
| 隐式指令 | Qwen-Image-2.1 | 30/30 | 19.09 | 0.8365 | 27.31 | 0.8788 | 0.0634 |
| 隐式指令 | **SITEdit** | 30/30 | 20.05 | 0.8905 | **32.22** | **0.9780** | **0.0181** |
| 连续第 1 轮 | FLUX.2 Klein-9B | 30/30 | 21.16 | **0.8506** | 28.91 | **0.9698** | **0.0299** |
| 连续第 1 轮 | MICE | 30/30 | **21.67** | 0.8453 | 25.32 | 0.9643 | 0.0328 |
| 连续第 1 轮 | RePlan | 30/30 | 20.04 | 0.8425 | **30.52** | 0.9581 | 0.0325 |
| 连续第 1 轮 | Qwen-Image-2.1 | 30/30 | 21.01 | 0.8266 | 27.86 | 0.8882 | 0.0433 |
| 连续第 1 轮 | **SITEdit** | 30/30 | 21.26 | 0.8493 | 29.86 | 0.9687 | 0.0304 |
| 连续第 2 轮 | FLUX.2 Klein-9B | 30/30 | 21.53 | 0.8505 | 23.06 | 0.8905 | 0.0900 |
| 连续第 2 轮 | MICE | 30/30 | 21.38 | 0.8446 | 19.73 | 0.8755 | 0.1027 |
| 连续第 2 轮 | RePlan | 30/30 | 20.51 | 0.8337 | 24.49 | 0.8812 | 0.0927 |
| 连续第 2 轮 | Qwen-Image-2.1 | 30/30 | 19.91 | 0.7787 | 18.43 | 0.5086 | 0.2714 |
| 连续第 2 轮 | **SITEdit** | 30/30 | **21.75** | **0.8557** | **24.93** | **0.9125** | **0.0745** |

完整结果：[REPORT.md](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/comparison_20261109/report/REPORT.md)；机器可读表：[TABLES.csv](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/comparison_20261109/report/TABLES.csv)。

## Inter-Edit

所有方法拿到同一公开 mask：SITEdit 原生编码，MICE 原生区域绑定，Qwen-Image-2.1 与 FLUX.2 通过附加图获得。区域内 AlphaCLIP 对比目标图，区域外 AlphaCLIP 对比源图。

| 方法 | 有效/应评 | 全图 LPIPS ↓ | 区域内 AlphaCLIP ↑ | 区域外 AlphaCLIP ↑ | BSS ↓ |
|---|---:|---:|---:|---:|---:|
| FLUX.2 Klein-9B | 200/200 | 0.2372 | 0.9711 | 0.9740 | 9.0091 |
| MICE | 200/200 | 0.2280 | 0.9691 | **0.9828** | 4.8905 |
| Qwen-Image-2.1 | 200/200 | 0.2983 | 0.9692 | 0.9691 | 8.2957 |
| **SITEdit** | 200/200 | **0.2130** | **0.9716** | 0.9796 | **4.2268** |

完整结果：[REPORT.md](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_interedit/comparison_20261109/report/REPORT.md)；机器可读表：[TABLES.csv](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_interedit/comparison_20261109/report/TABLES.csv)。

## Omni IIE

下表合并 low/high 两组，保留官方面积权重；分组表见完整报告。QA/Overall 因官方发布版缺少 QA 材料仍为 N/A，本轮不引入替代评判器。

| 方法 | 有效/应评 | LPIPS ↓ | PSNR ↑ | SSIM ↑ | CLIP-I ↑ | FG LPIPS ↓ | FG CLIP-I ↑ | BG LPIPS ↓ | BG CLIP-I ↑ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FLUX.2 Klein-9B | 200/200 | 0.3575 | 15.57 | 0.5118 | 0.9151 | 0.2291 | 0.9025 | 0.2292 | 0.9174 |
| MICE | 200/200 | 0.3644 | 15.20 | 0.5173 | 0.9042 | 0.2308 | 0.8918 | 0.2409 | 0.9086 |
| Qwen-Image-2.1 | 200/200 | 0.3581 | **16.15** | 0.5117 | **0.9222** | **0.2160** | **0.9086** | 0.2379 | **0.9251** |
| **SITEdit** | 200/200 | **0.3492** | 15.86 | **0.5279** | 0.9050 | 0.2217 | 0.8902 | **0.2201** | 0.9097 |

完整结果：[REPORT.md](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_omni_iie/comparison_20261109/report/REPORT.md)；机器可读表：[TABLES.csv](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_omni_iie/comparison_20261109/report/TABLES.csv)。

## 结果分析

- **CompBench**：SITEdit 在连续第二轮的五项指标上均取得本次五方法比较中的最佳点估计；在局部编辑、隐式指令两组中，PSNR、SSIM、LPIPS 三项非编辑区域保持指标也均最好。新增对照同时显示各方法的侧重：RePlan 在多目标组的 LC-I 和三项保持指标上最好，MICE 在局部、隐式和连续第一轮的 LC-T 上最好。
- **Inter-Edit**：SITEdit 的全图 LPIPS（0.2130）、区域内 AlphaCLIP（0.9716）和 BSS（4.2268）均最好；MICE 的区域外 AlphaCLIP 最高。SITEdit 的优势同时体现在与目标图的感知接近程度、区域内语义一致性以及边界指标。
- **Omni IIE**：SITEdit 的全图 LPIPS（0.3492）、SSIM（0.5279）和背景 LPIPS（0.2201）均最好；Qwen-Image-2.1 在其余五项整体指标上最好。这个子集支持围绕感知距离、结构相似性和背景保持陈述优势，各项指标分别报告，不合成自定义总分。

以上描述均为本次固定子集的点估计比较；完整区间保留在正式 REPORT.md 及 COMPARISON.json 中。对新增方法不沿用原 SITEdit/Base 的多重检验显著性标签。

## 核验与范围

所有方法均使用冻结推理配置；模型名单在新增推理前固定。三个子集不等同于完整测试集排行榜，也不根据本轮分数重选样本。各方法的逐项 95% 区间采用同源图簇共同重采样 10,000 次；本表不将点估计排序当作新增方法间的显著性检验。

CompBench 和 Omni 的 MICE 使用原生无区域全局提示路径，不额外调用定位器。RePlan 在 CompBench 保留其原生规划阶段。原 SITEdit/Base 的全部 131 个分组指标均值和区间与此前报告完全一致。

Omni 官方实现中的 BG CLIP-I 单例图像特征与全图相同，仅聚合权重不同，本轮保留该公式。

- compbench：240 请求/方法，191 源图簇；记录的生成或评分失败 0 条。
- interedit：200 请求/方法，200 源图簇；记录的生成或评分失败 0 条。
- omni_iie：200 请求/方法，100 源图簇；记录的生成或评分失败 0 条。

原计划 digest：`ecc7a5247d13c5798e830dc4fbba909cc03ab28cb1ad386eeb1d86ce1c00c3d9`。执行记录与全部 attempt 日志：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_comparison_20261109`。

## 完成与恢复记录

2026-11-09 10:13 UTC 完成。新增 1,520 张输出，复用原 1,280 张，共 2,800 张；所有方法覆盖率 100%，生成/评分请求失败均为 0，付费 API 调用为 0。3,680 条生成/规划记录通过来源和字节校验。全部本轮 GPU/评分进程已退出。

run001 和 run002-four 的基础设施中断及原始日志保留。中断只影响未受理请求或模型加载，未把已受理请求重新采样。用户要求四卡后，run003-four-idle 使用最多四张空闲 GPU 完成剩余 803 条首次生成；原始计划和科学配置不变。当前执行与核验记录位于控制目录的 `executions/four-gpu-idle.json`、`FINAL_VERIFICATION.json` 和 `COMPLETED.json`。

具体方法输入、原生参数及选择依据见 [评测方案](EXTERNAL_SUBSET_COMPARISON.md)。正式分数和原始结果未被本页改写。
