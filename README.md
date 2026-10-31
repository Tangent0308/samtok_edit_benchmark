# IF-Bench

IF-Bench 评测真实场景中的细粒度、多目标图像编辑：在同一张图上联合完成 2–5 个编辑，并保持未授权内容。任务覆盖添加、删除、替换和属性修改，比较不同目标语言与区域提示下的编辑完成度、内容保持和视觉质量。

当前数据 release **2.6.0** 包含 **1,084 张源图、3,872 个编辑单元**。当前评测采用 **`fairness-v2.2-1mp`**：七个固定模型/方法、十种 setting，共享约 1MP 的清图与公开区域；模型自身的原生流程保留。全量结果合并报告，不分别列 dev/test 成绩。

- [数据构建](docs/CONSTRUCTION.md)：来源、选择、任务与区域标注、审核、发布和复现。
- [评测用法](docs/USAGE.md)：公共画布、十种 setting、七模型实际输入、参数和指标。
- [四机运行](docs/FULL_RUN.md)：4×8 H100 前台入口、固定分片、统一 Judge 与汇总。
- [验证与结果](docs/RESULTS.md)：当前小样本验证证据及全量评测状态。

**全量评测待运行。** 小样本能否正确调用、出图和恢复坐标，与编辑任务是否通过分别报告；不把接口验证当成全量成绩。完整配置见 [fairness_v2_2_1mp.json](configs/evaluation/fairness_v2_2_1mp.json)，开发规范见 [CONTRIBUTING.md](CONTRIBUTING.md)。
