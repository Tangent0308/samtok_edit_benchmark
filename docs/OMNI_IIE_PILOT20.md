# Omni IIE Bench 约二十条扩展评测

2026-11-08 用户授权扩展先前八个 benchmark，比较冻结 SITEdit aa5a414 与 Qwen-Image-2.1。

## 事前固定的范围

十组完整 low/high 配对，共 20 条；八项官方客观指标，QA/Overall 仍 N/A。 保留上轮全部样本，抽样 seed 仍为 20261107；在各层排除已有 ID 后无放回抽取新增样本，抽样不读取输出或分数。`SELECTION.json` 在新增推理前冻结。

方法、提示和评分沿用 [OMNI_IIE_EVALUATION.md](OMNI_IIE_EVALUATION.md)。40 步、seed 42；SITEdit raw TE / token guidance 2 / Pass1 step2000 / S2 adapter16000。涉及 API 时仍为 GPT-5.4，不修改原生测量次数、提示、图像证据或聚合。缺失指标不填零；失败不重采样。

## 文件组织与复用

- 本轮根：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_omni_iie/pilot20_20261108`。
- `SELECTION.json`：原样本、新样本、分组和来源。
- `additional/`：仅新增请求的输入、生成与评分；原始 pilot_20261107 只读。
- `report/`：从原样本和新增样本逐条核验后合并统计；不能将两轮均值简单平均。
- 新资产：`datasets/ExternalPilot20_20261108/omni_iie/`，不改已有数据。
- 对照图：`/opt/tiger/tanyue/visualization_tmp/ExternalPilot20_20261108/omni_iie/`。

## 当前进度

扩展清单和全部新增输入已固定并通过校验；新增生成于 2026-11-08 开始，在 GPU 4–7 的两个队列中执行。评分与后续生成交错运行。旧记录只读复用。

## 复现入口

```bash
python -I scripts/extend_external_pilot.py --benchmark omni_iie --config configs/external/omni_iie.json --root /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_omni_iie/pilot20_20261108 --dataset-output /mnt/bn/strategy-mllm-train/user/tanyue/datasets/ExternalPilot20_20261108/omni_iie
```

生成与评分由 `scripts/run_pilot20_queue.py` 管理，两张授权 GPU 上各运行一种方法；原生评分脚本由隔离入口 `scripts/score_external_pilot.py` 调用。`scripts/report_external_pilot20.py` 核验原样本与新增样本的 public、bundle、源码、配置、输出、受理及评分绑定，再合并逐条数值；Omni 区域权重按官方规则重新累计。

共享实验范围为 164 条请求 / 方法，保留原 70 条，仅新增 94 条 / 方法。按各官方测量次数，本轮新增 GPT-5.4 调用最多 402 次：GIE 18、ComplexBench-Edit 60、Complex-Edit 256、GEdit 44、GIDE 24；其余三个仅客观评分。已受理未作答不自动重发。
