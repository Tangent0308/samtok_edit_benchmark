# GEdit-Bench 小子集评测方案

用户于 2026-11-07 确认；先记录协议，再实现评测。

- 范围：11 条固定请求，SITEdit 与 Qwen-Image-2.1。不是全量 benchmark 结论。
- 官方评分仓库：https://github.com/stepfun-ai/Step1X-Edit.git，当前核验 commit `4cca05dfcd6c32dc810d0b4db84c2bf0682a5aeb`。
- 抽样 seed 20261107，按已确认计划分层，生成前保存固定清单。
- 源码基础：新分支 `eval-gedit` 从已验证的两模型 pilot 通用代码 f0b954e 创建；不改变其他 worktree、IF-Bench 冻结包或现有结果。
- 方法固定：SITEdit aa5a414、Pass1 step2000、S2 adapter16000、raw TE、40步、γ2、seed42；Qwen-Image-2.1 原生40步、CFG1、seed42。
- 输入边界：两模型获得同一公开信息。评分 mask/GT/问题答案不能进入生成。只允许确定性几何转换，模型自己的原生定位流程保持不变。
- 评分：冻结官方函数、预处理、模型权重及聚合；涉及 API 时换为用户指定 GPT-5.4，原提示与评分定义保留，明确披露，不与其他 Judge 的论文数字直接混排。
- 异常：原始记录保留、失败不隐去，不自行把缺失分数补成零。
- 临时产物：`/tmp/ifbench/external_pilots_20261107/`。
- 已确认的小子集结果：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_gedit/pilot_20261107/`。
- 可视化：`/opt/tiger/tanyue/visualization_tmp/GEdit-Bench_20261107/`。

以下固定版本、公开字段映射和原生评分口径已在生成前完成核查；样例与生成配置不再按评分结果调整。

## 已固定的输入和评分

使用官方 `stepfun-ai/GEdit-Bench` revision `50766778e2a737474c7e9bdf84cdce82c3ea3f4f`，只在英文 11 类中各抽 1 条（seed 20261107）。输入为 `input_image_raw` 与原始 instruction，目标图/评分信息不进入生成。SITEdit 沿用冻结 RefEdit 的纯文字单复合请求适配：一次 Pass1、一次 S2，不使用外部拆指令；底座原指令一次生成。共享约 1MP 画布，输出回源。

评分固定 Step1X-Edit commit `4cca05dfcd6c32dc810d0b4db84c2bf0682a5aeb` 的 VIEScore：原图/输出按各自宽高比缩放到约 512² 面积并原样 JPEG 编码；SC 看到原图、输出和原指令，PQ 只看输出。SC、PQ 各取对应 rubric 子分的最小值，Overall=√(SC×PQ)，均为 0–10。按用户要求将官方 GPT-4.1（代码中 backbone 名仍为 gpt4o）替换为 GPT-5.4。

官方解析失败路径会生成随机分数，本实现明确禁用这一随机兜底：仅使用原生合法解析结果，否则记缺分，保留 raw response。不将随机数充当观测。一次受理未收到答案不自动补发。

## 下载和本机复现

数据下载入口仅调用官方 Hugging Face 固定 revision，不执行数据包中的代码。已下载的原文件先验证后复用。

```bash
python -I scripts/download_external_pilot.py --config configs/external/gedit_data.json --dataset /mnt/bn/strategy-mllm-train/user/tanyue/datasets/GEdit-Bench
python -I scripts/gedit_prepare.py --dataset /mnt/bn/strategy-mllm-train/user/tanyue/datasets/GEdit-Bench --output /path/to/pilot/bundle
python scripts/run_external_pilot.py --config configs/external/gedit.json --bundle /path/to/pilot/bundle --output /path/to/pilot/run --gpus 6 7 --attempt pilot01
```

门控仓库使用 `--token-file /protected/path` 读取已授权凭据；不能把凭据写入 Git。数据解析始终使用 `-I`。先加 `--case-ids` 跑所选两条冒烟，再用同一 bundle/config 跑完整固定子集，完成项不会重采样。完整评分命令通过 `python -m samtok_benchmark.external_gedit.score --help` 查看；所有源码 SHA、评分原文、实际时长保留在实验根。

本机评分环境：`/tmp/ifbench/external_pilots_20261107/env_metrics`，torch 2.8.0、torchvision 0.23.0、transformers 4.57.1、numpy 2.4.6、Pillow 13.0.0、scikit-image 0.25.2、torchmetrics 1.8.2、lpips 0.1.4、openai 3.28.0。生成使用配置中的独立冻结环境；没有修改生成环境。CPU 评分设置 `CUDA_VISIBLE_DEVICES=''`，`PYTHONPATH` 指向本分支 src。
