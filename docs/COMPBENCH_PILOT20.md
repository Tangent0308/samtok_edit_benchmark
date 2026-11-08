# CompBench 约二十条扩展评测

2026-11-08 用户授权扩展先前八个 benchmark，比较冻结 SITEdit aa5a414 与 Qwen-Image-2.1。

## 事前固定的范围

沿用六类单轮客观评分范围：add/remove/replace/implicit 各三条，multi-object add/remove 各四条，共 20 条；不改全量运行包。 保留上轮全部样本，抽样 seed 仍为 20261107；在各层排除已有 ID 后无放回抽取新增样本，抽样不读取输出或分数。`SELECTION.json` 在新增推理前冻结。

方法、提示和评分沿用 [COMPBENCH_EVALUATION.md](COMPBENCH_EVALUATION.md)。40 步、seed 42；SITEdit raw TE / token guidance 2 / Pass1 step2000 / S2 adapter16000。涉及 API 时仍为 GPT-5.4，不修改原生测量次数、提示、图像证据或聚合。缺失指标不填零；失败不重采样。

## 文件组织与复用

- 本轮根：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/pilot20_20261108`。
- `SELECTION.json`：原样本、新样本、分组和来源。
- `additional/`：仅新增请求的输入、生成与评分；原始 pilot_20261107 只读。
- `report/`：从原样本和新增样本逐条核验后合并统计；不能将两轮均值简单平均。
- 新资产：`datasets/ExternalPilot20_20261108/compbench/`，不改已有数据。
- 对照图：`/opt/tiger/tanyue/visualization_tmp/ExternalPilot20_20261108/compbench/`。

## 当前进度

已完成 20 条 / 方法的生成、评分与逐例合并。两方法共 40/40 张输出，所有本轮可运行指标均覆盖全部请求；无生成失败、API 错误或受理未作答。使用的 GPU 已释放。

结果见 [COMPBENCH_PILOT20_RESULTS.md](COMPBENCH_PILOT20_RESULTS.md)，[八项目汇总](https://github.com/Tangent0308/samtok_edit_benchmark/blob/eval-gie/docs/EXTERNAL_PILOT20_SUMMARY.md)；全部输入输出图见 `/opt/tiger/tanyue/visualization_tmp/ExternalPilot20_20261108/compbench/REPORT.md`。

## 复现入口

```bash
python -I scripts/extend_external_pilot.py --benchmark compbench --config configs/external/compbench.json --root /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/pilot20_20261108 --dataset-output /mnt/bn/strategy-mllm-train/user/tanyue/datasets/ExternalPilot20_20261108/compbench
```

生成与评分由 `scripts/run_pilot20_queue.py` 管理，两张授权 GPU 上各运行一种方法；原生评分脚本由隔离入口 `scripts/score_external_pilot.py` 调用。`scripts/report_external_pilot20.py` 核验原样本与新增样本的 public、bundle、源码、配置、输出、受理及评分绑定，再合并逐条数值；Omni 区域权重按官方规则重新累计。

共享实验范围为 164 条请求 / 方法，保留原 70 条，仅新增 94 条 / 方法。按各官方测量次数，本轮新增 GPT-5.4 调用最多 402 次：GIE 18、ComplexBench-Edit 60、Complex-Edit 256、GEdit 44、GIDE 24；其余三个仅客观评分。已受理未作答不自动重发。

核验：原 140 个输出与 68 个旧汇总值逐条复核通过，审计结果与 2026-11-07 保存的 AUDIT.json 完全一致；全部 210 条原阶段收据中的科学源码哈希与当前生成实现一致。只新增抽样/调度/汇总代码，生成和原生评分代码未修改。

## 本轮工程修复

客观评分首次启动被 TorchMetrics 的路径名称检查拒绝，尚未产生分数；既有 `ExternalBenchMetrics/openai/clip-vit-large-patch14` 是同一权重目录的标准名称软链接。改为该路径后，24 个新增输出均完成五项客观评分。六个权重/预处理文件的 SHA256 已核验一致；没有改模型、公式或图像，没有重新推理。证据：`.ifbench-tmp/external_pilot20_20261108/COMPBENCH_SCORER_PATH_REPAIR.json`。失败启动日志原样保留。

## 本轮处理记录

首次 CPU 评分因 TorchMetrics 检查 CLIP 路径名称退出；改用现有 `openai/clip-vit-large-patch14` 别名后完成。六个权重/预处理文件 SHA256 均相同，未重跑生成。原失败日志与路径修复后的完成日志均保留。

本轮扩展抽样、逐例合并与原生区域权重的 5 项 CPU 合约测试通过；核验和诊断记录在 `.ifbench-tmp/external_pilot20_20261108/`。
