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

2026-11-09 08:03 UTC 启动本机新增方法生成；33 项相关 CPU 测试通过。全部共享输入/评分资产预检通过。原两方法 131 个分组指标的均值和 95% 区间复算与原报告完全一致。当前按用户最新要求最多四卡并行，每个未完成阶段从本机已授权 0–7 中选择空闲卡，实际卡号写入 worker 回执；首选 0、1、3、4。保留无关进程，原生 CPU 评分和下一方法生成重叠。

- 控制目录：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_comparison_20261109/`。
- 原清单：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_validation_20261109/<benchmark>/SELECTION.json`。
- 新结果：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_<benchmark>/comparison_20261109/`。
- 可视化：`/opt/tiger/tanyue/visualization_tmp/ExternalComparison_20261109/`。

统计结论以最终逐条记录为准，此处不预填成绩。

冻结生成源码：`169be537f0f69a73701a273cea84df89dc60ad7f`；新计划 digest：`ecc7a5247d13c5798e830dc4fbba909cc03ab28cb1ad386eeb1d86ce1c00c3d9`。`scripts/external_compare.py` 管理新增方法的原生 worker，`scripts/finalize_external_compare.py` 只监控与生成 CPU 报告，不改推理进程。

## 四卡续跑记录

run001 完成 717 张新增图像后，GPU 6 在 RePlan 第二轮编辑模型加载期间出现新的外部显存占用，触发 OOM。失败发生在请求 admission 之前，余下 3 条没有采样；没有模型失败或未知 admission。保留全部原始日志、load_failure 和成功记录。用户随后要求改用四卡。

续跑保持原 PLAN.json、清单、方法配置、原生生成/评分源码和结果根不变；只发布 `executions/four-gpu.json` 调度记录，绑定原计划 SHA、当前调度源码和 GPU 0–3。已完成记录核验复用，其余 803 条首次推理。并发 worker 的致命错误改为即时检查，随后在当前请求完成后协调退出。没有结束或改动其他任务。

run002-four 在任何新增请求受理前，被 GPU 2 的新增外部占用触发空闲检查而退出。run003-four-idle 改为最多四卡的空闲设备池：每个未缓存阶段重新检查空闲显存并记录实际卡号，已完成阶段仅做 CPU 核验，不占 GPU；不结束其他进程。两个模型的 CPU 评分可以并行，每个模型仍是原先四个分片、每进程四线程，评分公式/参数不变。新调度记录位于 `executions/four-gpu-idle.json`，此前两个 attempt 和执行记录全部保留。
