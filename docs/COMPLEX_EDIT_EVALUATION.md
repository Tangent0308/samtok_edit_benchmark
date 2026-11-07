# Complex-Edit 小子集评测方案

用户于 2026-11-07 确认；先记录协议，再实现评测。

- 范围：8 条固定请求，SITEdit 与 Qwen-Image-2.1。不是全量 benchmark 结论。
- 官方评分仓库：https://github.com/UCSC-VLAA/Complex-Edit.git，当前核验 commit `3502eaa9e81bc99623bd995106df48c0f921af31`。
- 抽样 seed 20261107，按已确认计划分层，生成前保存固定清单。
- 源码基础：新分支 `eval-complex-edit` 从已验证的两模型 pilot 通用代码 f0b954e 创建；不改变其他 worktree、IF-Bench 冻结包或现有结果。
- 方法固定：SITEdit aa5a414、Pass1 step2000、S2 adapter16000、raw TE、40步、γ2、seed42；Qwen-Image-2.1 原生40步、CFG1、seed42。
- 输入边界：两模型获得同一公开信息。评分 mask/GT/问题答案不能进入生成。只允许确定性几何转换，模型自己的原生定位流程保持不变。
- 评分：冻结官方函数、预处理、模型权重及聚合；涉及 API 时换为用户指定 GPT-5.4，原提示与评分定义保留，明确披露，不与其他 Judge 的论文数字直接混排。
- 异常：原始记录保留、失败不隐去，不自行把缺失分数补成零。
- 临时产物：`/tmp/ifbench/external_pilots_20261107/`。
- 已确认的小子集结果：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_complex_edit/pilot_20261107/`。
- 可视化：`/opt/tiger/tanyue/visualization_tmp/Complex-Edit_20261107/`。

以下固定版本、公开字段映射和原生评分口径已在生成前完成核查；样例与生成配置不再按评分结果调整。

## 已固定的输入和评分

官方数据 revision `b0b8a81d740ae413d52572281a23dc975c4b4b91`，CC BY-NC 4.0。real/syn 各固定一张源图，各取 K=1/2/4/8 的原始 compound_instruction，共 8 条；同图不同复杂度没有换样。两模型只得到复合指令和公开源图，不读取私有 sequence/reasoning，也不用额外模型拆分指令。SITEdit 沿用纯文字复合请求的冻结 RefEdit 适配，一次 Pass1 后一次联合编辑；Qwen2.1 原指令一次生成。共享约 1MP 输入并将输出回源。

评分原样使用官方 alignment（rubric=True、CoT=True）和 quality（rubric=True、CoT=False、instruction=False）的提示与结构化格式；按用户要求替换 GPT-4o 为 GPT-5.4。每输出、每方面仍采用官方默认 n=20 次测量，每次 API 请求 m=5 个答案，temperature=1；共 16 输出×2方面×20=640 个评分答案、128 个正常 API 请求，不挑最好答案。IF/IP/PQ 各平均后，Overall 为三项均值。输入输出图原生编码，不另行加入 GT。

记录说明：使用逐 case 绑定聚合，避免官方多进程无序列表 zip 导致错配；官方脚本将 final_quality 误写到 overall 汇总文件，本实现从逐例三项均值汇总真正的 Overall。每条评分保留原文和 20 次测量，解析失败不猜分、不无限重试。为 GPT-5.4 预留 8192 tokens；这一 API 模型/预算变更单独披露。

## 下载和本机复现

数据下载入口仅调用官方 Hugging Face 固定 revision，不执行数据包中的代码。已下载的原文件先验证后复用。

```bash
python -I scripts/download_external_pilot.py --config configs/external/complex_edit_data.json --dataset /mnt/bn/strategy-mllm-train/user/tanyue/datasets/Complex-Edit
python -I scripts/complex_edit_prepare.py --dataset /mnt/bn/strategy-mllm-train/user/tanyue/datasets/Complex-Edit --output /path/to/pilot/bundle
python scripts/run_external_pilot.py --config configs/external/complex_edit.json --bundle /path/to/pilot/bundle --output /path/to/pilot/run --gpus 6 7 --attempt pilot01
```

门控仓库使用 `--token-file /protected/path` 读取已授权凭据；不能把凭据写入 Git。数据解析始终使用 `-I`。先加 `--case-ids` 跑所选两条冒烟，再用同一 bundle/config 跑完整固定子集，完成项不会重采样。完整评分命令通过 `python -m samtok_benchmark.external_complex_edit.score --help` 查看；所有源码 SHA、评分原文、实际时长保留在实验根。

本机评分环境：`/tmp/ifbench/external_pilots_20261107/env_metrics`，torch 2.8.0、torchvision 0.23.0、transformers 4.57.1、numpy 2.4.6、Pillow 13.0.0、scikit-image 0.25.2、torchmetrics 1.8.2、lpips 0.1.4、openai 3.28.0。生成使用配置中的独立冻结环境；没有修改生成环境。CPU 评分设置 `CUDA_VISIBLE_DEVICES=''`，`PYTHONPATH` 指向本分支 src。
