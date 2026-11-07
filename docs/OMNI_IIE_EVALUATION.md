# OmniIIEBench 小子集评测方案

用户于 2026-11-07 确认；先记录协议，再实现评测。

- 范围：8 条固定请求，SITEdit 与 Qwen-Image-2.1。不是全量 benchmark 结论。
- 官方评分仓库：https://github.com/Young-2000/OmniIIEBench.git，当前核验 commit `d957aea591d98b7840db6d12a788d624e8b35bc4`。
- 抽样 seed 20261107，按已确认计划分层，生成前保存固定清单。
- 源码基础：新分支 `eval-omni-iie` 从已验证的两模型 pilot 通用代码 f0b954e 创建；不改变其他 worktree、IF-Bench 冻结包或现有结果。
- 方法固定：SITEdit aa5a414、Pass1 step2000、S2 adapter16000、raw TE、40步、γ2、seed42；Qwen-Image-2.1 原生40步、CFG1、seed42。
- 输入边界：两模型获得同一公开信息。评分 mask/GT/问题答案不能进入生成。只允许确定性几何转换，模型自己的原生定位流程保持不变。
- 评分：冻结官方函数、预处理、模型权重及聚合；涉及 API 时换为用户指定 GPT-5.4，原提示与评分定义保留，明确披露，不与其他 Judge 的论文数字直接混排。
- 异常：原始记录保留、失败不隐去，不自行把缺失分数补成零。
- 临时产物：`/tmp/ifbench/external_pilots_20261107/`。
- 已确认的小子集结果：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_omni_iie/pilot_20261107/`。
- 可视化：`/opt/tiger/tanyue/visualization_tmp/OmniIIEBench_20261107/`。

以下固定版本、公开字段映射和原生评分口径已在生成前完成核查；样例与生成配置不再按评分结果调整。

## 已确认的可执行协议

从 `YamJoy/OmniIIEBench` revision `334b76a6e3768ba90e98134d6730bc9cb22b18aa` 的 single_turn 中，按 seed 20261107 固定四个完整 low/high 语义尺度配对，共 8 条。两方法只得到原图与 modification_text，mask/目标图仅用于评分。共享约 1MP 输入、输出回源；SITEdit 纯文字复合请求一次 Pass1+S2，Qwen2.1 原指令一次生成。

用户确认只保留已发布入口实际可运行的 8 项：LPIPS、PSNR、SSIM、CLIP-I、FG/BG LPIPS、FG/BG CLIP-I。QA 未发布，官方入口将 qa_data 写为 None 且不调用 QA 评分，故 QA/Overall 均 N/A，不生成新题目代替。

固定官方代码 d957aea，评分统一 768×768，图像 LANCZOS、mask NEAREST，LPIPS-vgg、CLIP ViT-B/32。FG/BG 使用目标 mask，仅用于评分；BG LPIPS、BG CLIP-I、FG LPIPS 按官方面积权重汇总，FG CLIP-I 与全图指标为逐例均值。全部保留原生预处理，包括官方 region LPIPS 的 normalize=True 调用。不需付费 API。

## 下载和本机复现

数据下载入口仅调用官方 Hugging Face 固定 revision，不执行数据包中的代码。已下载的原文件先验证后复用。

```bash
python -I scripts/download_external_pilot.py --config configs/external/omni_iie_data.json --dataset /mnt/bn/strategy-mllm-train/user/tanyue/datasets/OmniIIEBench
python -I scripts/omni_iie_prepare.py --dataset /mnt/bn/strategy-mllm-train/user/tanyue/datasets/OmniIIEBench --output /path/to/pilot/bundle
python scripts/run_external_pilot.py --config configs/external/omni_iie.json --bundle /path/to/pilot/bundle --output /path/to/pilot/run --gpus 6 7 --attempt pilot01
```

门控仓库使用 `--token-file /protected/path` 读取已授权凭据；不能把凭据写入 Git。数据解析始终使用 `-I`。先加 `--case-ids` 跑所选两条冒烟，再用同一 bundle/config 跑完整固定子集，完成项不会重采样。完整评分命令通过 `python -m samtok_benchmark.external_omni_iie.score --help` 查看；所有源码 SHA、评分原文、实际时长保留在实验根。

本机评分环境：`/tmp/ifbench/external_pilots_20261107/env_metrics`，torch 2.8.0、torchvision 0.23.0、transformers 4.57.1、numpy 2.4.6、Pillow 13.0.0、scikit-image 0.25.2、torchmetrics 1.8.2、lpips 0.1.4、openai 3.28.0。生成使用配置中的独立冻结环境；没有修改生成环境。CPU 评分设置 `CUDA_VISIBLE_DEVICES=''`，`PYTHONPATH` 指向本分支 src。

## 官方 BG_CLIP_I 的实际含义

[`metrics_utils.py` L271–283](https://github.com/Young-2000/OmniIIEBench/blob/d957aea591d98b7840db6d12a788d624e8b35bc4/evaluation/metrics_utils.py#L271) 将背景 mask 写入 RGBA 的 alpha，RGB 本身未遮盖；所用 CLIPProcessor 会转 RGB 并丢弃 alpha。本机核查预处理张量逐字节相同，冒烟中的逐例 BG_CLIP_I 也与全图 CLIP_I 相同。官方后续按背景面积加权，因此其汇总值可能与全图均值不同。保留官方实现和名称，避免把该项当成独立的纯背景保持证据。其他区域指标仍按各自原函数计算。
