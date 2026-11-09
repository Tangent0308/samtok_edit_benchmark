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

## 当前状态

样本清单已经冻结：240 条请求，191 个独立源图簇，未抽到已知空 mask。本机调度复用冻结生成/评分模块；CPU 抽样、链依赖、GPU 授权及原有输入合同测试已通过。已于 2026-11-09 04:11 UTC 启动 `local001`；三个数据集的只读预检均通过，8 卡已进入 CompBench 的 SITEdit 生成。原生分数和最终配对统计尚未完成。

固定清单：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_validation_20261109/compbench/SELECTION.json`；digest：`ab8e28826dc9617f6af78b296bf6dc84ebcd1a04e139f22f61ded4dd2277340e`。

入口：`scripts/external_pair.py prepare / freeze / run`。统一计划为 `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_validation_20261109/PLAN.json`，运行状态为 `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_validation_20261109/STATUS.json`。`run` 必须用新的 attempt；复用已完成终态，不自动放行已受理未完成记录。


统计和可视化只读取生成后的原生记录，源码位于 `external_pair/{statistics,report,preview}.py`。已测试官方权重、多轮同源绑定、固定 53 项比较族与校正、配对 bootstrap 的确定性。当前运行从已提交的独立快照执行，后续分析工具的增加不会改变生成源码。

## 2026-11-09 05:57 UTC 运行检查

CompBench 两方法各 240/240 出图和评分完成；Inter-Edit 两方法各 200/200 出图和评分完成；均无失败。Omni IIE 正在八卡生成 SITEdit，随后生成 Base。对已完成的两个 benchmark 先行复算了原生聚合与配对区间；53 项主比较的统一 Holm 校正等待 Omni 完成。所有新清单的源图像素核验通过，分组与冻结计划一致。

最终 `report/PAIRED_REPORT.json` 与 `report/REPORT.md` 自动写入各自 `validation_20261109` 根；`scripts/plot_external_pair.py` 读取最终报告绘制全部主比较的效应/区间图，保留指标原单位。全部真实样本对照图在 `visualization_tmp/ExternalValidation_20261109/<benchmark>/INDEX.md`；图中不使用结果筛选。
