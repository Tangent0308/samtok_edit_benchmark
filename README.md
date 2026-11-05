# IF-Bench

本分支 **`eval-magicbrush`** 增加 SITEdit 与七个基线的 MagicBrush 外部评测：535 个会话、1,053 个编辑轮次，无 mask／有 mask 两种输入，独立单轮／连续多轮两种评测，使用免费标准指标。SITEdit 固定 `aa5a414` 主行，完整推理配置、训练数据重合、执行状态均明确披露。

- [评测方案](docs/MAGICBRUSH_EVALUATION.md)：官方协议、八方法输入、指标、数据重合与偏差。
- [运行手册](docs/MAGICBRUSH.md)：下载、安全解码、冒烟、单机 8 卡与断点续跑。
- [冒烟结果与正式交付](docs/MAGICBRUSH_RESULTS.md)：24/24 流程验证、逐方法实测耗时／显存、重合审计与全量入口。
- [实际进度](docs/MAGICBRUSH_PROGRESS.md)：已完成检查、真实结果和剩余工作；冒烟不作为正式基准成绩。

本分支基于 `eval-refedit` 的八方法后端，独立实现 MagicBrush 数据与评测模块。IF-Bench 的最新正式论文结果见主分支 [PAPER_RESULTS.md](https://github.com/Tangent0308/samtok_edit_benchmark/blob/v2branch/docs/PAPER_RESULTS.md)。下面为 IF-Bench 项目背景。

IF-Bench 评测真实场景中的细粒度、多目标图像编辑：在同一张图上联合完成 2–5 个编辑，并保持未授权内容。任务覆盖添加、删除、替换和属性修改，比较不同目标语言与区域提示下的编辑完成度、内容保持和视觉质量。

当前数据 release **2.6.0** 包含 **1,084 张源图、3,872 个编辑单元**。当前评测采用 **`fairness-v2.2-1mp`**：七个基线及我方 **SAMTokEdit**、十种 setting，共享约 1MP 的清图与公开区域；模型自身的原生流程保留。全量结果合并报告，不分别列 dev/test 成绩。SAMTokEdit 由[独立仓库](https://github.com/Tangent0308/samtok_edit/tree/qwen-image-2.1-v4)运行，与七基线使用相同的公开请求、canonical Judge 和配对统计。

- [数据构建](docs/CONSTRUCTION.md)：来源、选择、任务与区域标注、审核、发布和复现。
- [评测用法](docs/USAGE.md)：公共画布、十种 setting、八方法实际输入、参数和指标。
- [四机运行](docs/FULL_RUN.md)：4×8 H100 前台入口、固定分片、统一 Judge 与汇总。
- [验证与结果](docs/RESULTS.md)：当前小样本验证证据及全量评测状态。

七基线冻结配置见 [fairness_v2_2_1mp.json](configs/evaluation/fairness_v2_2_1mp.json)，SAMTokEdit 配置与调用见[方法说明](docs/USAGE.md#44-samtokedit我方方法)，开发规范见 [CONTRIBUTING.md](CONTRIBUTING.md)。本分支保留模板分支的 IF-Bench 开发记录；正式成绩以以上 `v2branch` 结果页为准。
