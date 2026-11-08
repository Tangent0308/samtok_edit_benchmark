# Complex-Edit · SITEdit / Qwen-Image-2.1 pilot

分支 `eval-complex-edit` 已完成固定 24 条请求的两方法对比，采用冻结 SITEdit aa5a414 主行与 Qwen-Image-2.1。两方法全部正常出图并完成本轮可运行评分；这是分层小样本结果。

- [当前结果与完整指标](docs/COMPLEX_EDIT_PILOT20_RESULTS.md)
- [当前抽样、路径与复现方式](docs/COMPLEX_EDIT_PILOT20.md)
- [方法输入与原生评测协议](docs/COMPLEX_EDIT_EVALUATION.md)
- [进度与处理记录](docs/COMPLEX_EDIT_PROGRESS.md)
- [八个 benchmark 的扩展对比汇总](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-gie/docs/EXTERNAL_PILOT20_SUMMARY.md)

全部实际输入输出对照：`/opt/tiger/tanyue/visualization_tmp/ExternalPilot20_20261108/complex_edit/REPORT.md`。原小子集结果保存在 [初始 pilot 报告](docs/COMPLEX_EDIT_RESULTS.md)，原始记录未改动。

数据、权重、密钥和完整图像输出不入 Git。IF-Bench 正式结果见 [v2branch/PAPER_RESULTS.md](https://github.com/Tangent0308/samtok_edit_benchmark/blob/v2branch/docs/PAPER_RESULTS.md)。
