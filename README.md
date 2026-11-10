# IF-Bench

本分支 **`eval-mira`** 保存 SITEdit 的 MIRA-Bench 评测实现、协议与结果。**最新 R2@1000 已完成全部 200 张图的生成和 GPT-5.4 评分**，并与 Qwen-Image-2.1、Qwen-Image-Edit-2511、RePlan、MIRAGE 及 SITEdit v4 对比。R2 的 PF / Cons / PQ / Overall 为 **7.881 / 7.830 / 6.748 / 7.269**（0–10 分）。

- **[当前完整结果与 R2 配置](docs/MIRA_R2.md)**：六行对比、置信区间、正确权重核验、全部结果路径及 CPU 复算入口。
- [公共评测协议](docs/MIRA_EVALUATION.md)：200 张图、每图五项联合编辑，各模型推理方式、官方指标及 GPT-5.4 Judge。
- [运行手册](docs/MIRA.md)：环境、数据、生成、评分、断点恢复和检查命令。
- [实际执行审计](docs/MIRA_FULL_RUN.md)：运行记录与原生调用证据；[文档索引](docs/README.md)列出独立诊断材料。

R2 正式结果位于 `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira/r2_20261110/`。五行既有对照记录保持原样；RePlan 的一例生成失败保留，按 199/200 覆盖率报告。原始图像、权重、评分记录与密钥不存入 Git。

IF-Bench 评测真实场景中的细粒度、多目标图像编辑：在同一张图上联合完成 2–5 个编辑，并保持未授权内容。任务覆盖添加、删除、替换和属性修改，比较不同目标语言与区域提示下的编辑完成度、内容保持和视觉质量。

当前数据 release **2.6.0** 包含 **1,084 张源图、3,872 个编辑单元**。当前评测采用 **`fairness-v2.2-1mp`**：七个基线及我方 **SAMTokEdit**、十种 setting，共享约 1MP 的清图与公开区域；模型自身的原生流程保留。全量结果合并报告，不分别列 dev/test 成绩。SAMTokEdit 由[独立仓库](https://github.com/Tangent0308/samtok_edit/tree/qwen-image-2.1-v4)运行，与七基线使用相同的公开请求、canonical Judge 和配对统计。

- [数据构建](docs/CONSTRUCTION.md)：来源、选择、任务与区域标注、审核、发布和复现。
- [评测用法](docs/USAGE.md)：公共画布、十种 setting、八方法实际输入、参数和指标。
- [四机运行](docs/FULL_RUN.md)：4×8 H100 前台入口、固定分片、统一 Judge 与汇总。
- [验证与结果](docs/RESULTS.md)：当前小样本验证证据及全量评测状态。

本分支保留外部评测所依赖的 IF-Bench 冻结实现；IF-Bench 主评测的最新论文结果以 [v2branch](https://github.com/Tangent0308/samtok_edit_benchmark/tree/v2branch) 为准。七基线配置见 [fairness_v2_2_1mp.json](configs/evaluation/fairness_v2_2_1mp.json)，开发规范见 [CONTRIBUTING.md](CONTRIBUTING.md)。
