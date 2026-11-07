# Inter-Edit 小子集评测方案

用户于 2026-11-07 确认；先记录协议，再实现评测。

- 范围：8 条固定请求，SITEdit 与 Qwen-Image-2.1。不是全量 benchmark 结论。
- 官方评分仓库：https://github.com/Delong-liu-bupt/Inter-Edit.git，当前核验 commit `220c1dc26d8401cae160a6b25e48198f85bdd115`。
- 抽样 seed 20261107，按已确认计划分层，生成前保存固定清单。
- 源码基础：新分支 `eval-interedit` 从已验证的两模型 pilot 通用代码 f0b954e 创建；不改变其他 worktree、IF-Bench 冻结包或现有结果。
- 方法固定：SITEdit aa5a414、Pass1 step2000、S2 adapter16000、raw TE、40步、γ2、seed42；Qwen-Image-2.1 原生40步、CFG1、seed42。
- 输入边界：两模型获得同一公开信息。评分 mask/GT/问题答案不能进入生成。只允许确定性几何转换，模型自己的原生定位流程保持不变。
- 评分：冻结官方函数、预处理、模型权重及聚合；涉及 API 时换为用户指定 GPT-5.4，原提示与评分定义保留，明确披露，不与其他 Judge 的论文数字直接混排。
- 异常：原始记录保留、失败不隐去，不自行把缺失分数补成零。
- 临时产物：`/tmp/ifbench/external_pilots_20261107/`。
- 已确认的小子集结果：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_interedit/pilot_20261107/`。
- 可视化：`/opt/tiger/tanyue/visualization_tmp/Inter-Edit_20261107/`。

以下固定版本、公开字段映射和原生评分口径已在生成前完成核查；样例与生成配置不再按评分结果调整。

## 已确认的发布接口处理

用户确认：四项不依赖 reference_image 的官方客观指标保留；S_ref_AlphaCLIP 和依赖额外参考图的 VLM 评分记 N/A。绝不把 GT 当作编辑器参考图。

## 当前冻结的输入与指标

八条按任务和语言固定分层：Add、Local、Remove 各中英文 1 条，Text Editing 英文 1 条、Texture 中文 1 条。公开源图、mask 和原指令同时提供给两方法；不翻译指令。发布 mask 的像素网格小于源图，依官方代码先 NEAREST 对齐源图，再按同一 1MP 几何映射到画布。mask>128 为选中区域。

- SITEdit：公开 mask 直接由其原生 SAMTok codec 编码，不调用 Pass1 定位；将区域 token 插入原指令，S2 40 步、γ2、raw TE 一次编辑。
- Qwen2.1：干净画布和二值 mask 作为两张参考图，固定提示说明白色为选中区域；原指令不改写，40 步、CFG1。
- 输出都去除公共画布 padding 后回源尺寸，无粘贴或修图。
- 四项指标直接沿用官方数学定义：LPIPS-alex（对目标图）、区域内 AlphaCLIP（对目标图）、区域外 AlphaCLIP（对源图）、BSS_Laplacian（代码实际为 Sobel 边缘梯度内外环差，保留官方名称）。AlphaCLIP 是 ViT-L/14、官方 grit1m full-tune 8xe 权重。
- 数据缺少 reference_image，用户确认 S_ref_AlphaCLIP 和 VLM 评分为 N/A。mask 和 GT 只在各自被协议公开的边界内使用，GT 绝不作为模型参考输入。
- 官方数据卡未声明数据许可；代码仓库 MIT。不重新分发数据，只保留来源和校验和。

## 下载和本机复现

数据下载入口仅调用官方 Hugging Face 固定 revision，不执行数据包中的代码。已下载的原文件先验证后复用。

```bash
python -I scripts/download_external_pilot.py --config configs/external/interedit_data.json --dataset /mnt/bn/strategy-mllm-train/user/tanyue/datasets/Inter-Edit-Test
python -I scripts/interedit_prepare.py --dataset /mnt/bn/strategy-mllm-train/user/tanyue/datasets/Inter-Edit-Test --output /path/to/pilot/bundle
python scripts/run_external_pilot.py --config configs/external/interedit.json --bundle /path/to/pilot/bundle --output /path/to/pilot/run --gpus 6 7 --attempt pilot01
```

门控仓库使用 `--token-file /protected/path` 读取已授权凭据；不能把凭据写入 Git。数据解析始终使用 `-I`。先加 `--case-ids` 跑所选两条冒烟，再用同一 bundle/config 跑完整固定子集，完成项不会重采样。完整评分命令通过 `python -m samtok_benchmark.external_interedit.score --help` 查看；所有源码 SHA、评分原文、实际时长保留在实验根。

本机评分环境：`/tmp/ifbench/external_pilots_20261107/env_metrics`，torch 2.8.0、torchvision 0.23.0、transformers 4.57.1、numpy 2.4.6、Pillow 13.0.0、scikit-image 0.25.2、torchmetrics 1.8.2、lpips 0.1.4、openai 3.28.0。生成使用配置中的独立冻结环境；没有修改生成环境。CPU 评分设置 `CUDA_VISIBLE_DEVICES=''`，`PYTHONPATH` 指向本分支 src。

## 原生透明输出的记录口径

原始 `raw.png` 保留模型返回的 RGBA；冻结画布回源函数和这些官方 RGB 指标使用 `convert("RGB")`，不会把透明区域贴回源图，也不补背景。冒烟中 Qwen2.1 部分输出预测了大面积透明 alpha，RGB 图中显为紫色；这是原始输出的透明区域在 RGB 口径下的表现，不能误写成文件损坏或预处理生成了紫色背景。后续报告保留该限制，不按得分修改输出转换或重新生成。
