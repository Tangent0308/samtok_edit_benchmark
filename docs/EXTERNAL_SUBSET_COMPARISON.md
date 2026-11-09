# 固定子集：多方法对比

2026-11-09，用户授权在刚完成的三个固定子集上补充代表性方法。本轮名单在新增方法推理前固定；SITEdit/Base 结果已知，新增方法不根据得分增删。

| Benchmark | 相同请求数 | 全部比较方法 | 新增生成数 |
|---|---:|---|---:|
| CompBench | 240 | FLUX.2 Klein-9B、MICE、RePlan、Qwen-Image-2.1、SITEdit | 720 |
| Inter-Edit | 200 | FLUX.2 Klein-9B、MICE、Qwen-Image-2.1、SITEdit | 400 |
| Omni IIE | 200（100 对 low/high） | FLUX.2 Klein-9B、MICE、Qwen-Image-2.1、SITEdit | 400 |

## 方法选择与输入

- Qwen-Image-2.1 与 SITEdit：逐条核验复用原 validation_20261109 的生成和评分，不重采样、不覆盖。
- FLUX.2 Klein-9B：其他模型家族的通用编辑器；官方 distilled 4 步、guidance 1、seed 42。CompBench/Omni 输入原图和原指令；Inter-Edit 输入原图、公开二值 mask 附加图和固定解释提示。
- MICE：基于 Klein-4B 的区域控制方法，原生 4 步、guidance 1。Inter-Edit 使用其原生区域 mask 绑定；CompBench/Omni 没有公开区域，采用原生全局提示路径，不加入外部定位器。后两项只检验其无区域输入行为，并不等于测试区域注意力模块的完整收益。
- RePlan：只加入 CompBench，比较原生规划流程在复杂和连续编辑中的表现。原图和原指令 → 官方 RePlan-Qwen2.5-VL-7B planner → Qwen2511 区域编辑；40 步、true CFG 4、seed 42，不手工改计划。

保持既有约 1MP 画布、回源几何、权重、方法源码、所有参数、官方客观评分及失败口径。CompBench 第二轮消费同方法第一轮实际输出。Inter-Edit 不给任何方法私有参考/目标图；Omni low/high 成对保留。仅使用既有本地评分，无 API 调用。

## 证据、复用与统计

原始 SELECTION.json/配置保持只读，新计划记录其 SHA256、原计划 digest 和相同 case_ids/源图簇。新的 comparison_20261109/run、scores 仅对旧两个方法建立指向原记录的链接；新增方法写入新目录。原生成、评分和报告均不改动。

报告保留所有原生指标、官方子任务/面积加权聚合和覆盖率。失败仍占应评数量，不虚构最差分或删除 case；如覆盖率不同，额外提供所有方法共同有效请求的敏感性表。使用原固定源图簇的共享 bootstrap 生成均值区间；新增比较为本次扩展分析，不将原两方法的 53 项 Holm 校正当成新增比较的显著性结果。

## 执行状态

2026-11-09 08:03 UTC 启动本机新增方法生成；33 项相关 CPU 测试通过。全部共享输入/评分资产预检通过。原两方法 131 个分组指标的均值和 95% 区间复算与原报告完全一致。沿用本机八卡：每卡只启动一个自身 worker，保留无关约 1.6 GiB 占用；原生 CPU 评分和下一方法生成重叠。

- 控制目录：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_comparison_20261109/`。
- 原清单：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_validation_20261109/<benchmark>/SELECTION.json`。
- 新结果：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_<benchmark>/comparison_20261109/`。
- 可视化：`/opt/tiger/tanyue/visualization_tmp/ExternalComparison_20261109/`。

统计结论以最终逐条记录为准，此处不预填成绩。

冻结生成源码：`169be537f0f69a73701a273cea84df89dc60ad7f`；新计划 digest：`ecc7a5247d13c5798e830dc4fbba909cc03ab28cb1ad386eeb1d86ce1c00c3d9`。`scripts/external_compare.py` 管理新增方法的原生 worker，`scripts/finalize_external_compare.py` 只监控与生成 CPU 报告，不改推理进程。
