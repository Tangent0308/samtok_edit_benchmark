# IF-Bench

IF-Bench 是一个细粒度、多目标图像编辑 benchmark：在同一张真实场景图中联合完成 2–5 个编辑，比较不同语言指称和区域提示下的编辑执行、内容保持与视觉质量。

当前数据 release **2.6.0** 包含 **1,084 张图、3,872 个编辑单元**；七个已确认开源模型/方法的固定 **20 图 dev 验证已完成**，全量正式评测使用固定方案，四机入口已实现，结果待运行。

- [Benchmark 构建](docs/CONSTRUCTION.md)：来源、数据协议、筛选、标注、核验修复与发布重放。
- [Benchmark 用法](docs/USAGE.md)：十种 setting、数据路径、七模型的详细推理方式与真实输入示例。
- [四机全量运行](docs/FULL_RUN.md)：四台 8×H100 的启动命令、分工、恢复规则和统一汇总。
- [评测结果和分析](docs/RESULTS.md)：最新 dev20 分数、置信区间、逐 setting 模型对比和可视化。

开发与目录规范见 [CONTRIBUTING.md](CONTRIBUTING.md)。
