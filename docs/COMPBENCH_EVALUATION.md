# CompBench 小子集评测方案

用户于 2026-11-07 确认；先记录协议，再实现评测。

- 范围：8 条固定请求，SITEdit 与 Qwen-Image-2.1。不是全量 benchmark 结论。
- 官方评分仓库：https://github.com/comp-bench/CompBench.git，当前核验 commit `ca0ec0dea6ce2ced7d42e26afdedd712034e6b56`。
- 抽样 seed 20261107，按已确认计划分层，生成前保存固定清单。
- 源码基础：新分支 `eval-compbench` 从已验证的两模型 pilot 通用代码 f0b954e 创建；不改变其他 worktree、IF-Bench 冻结包或现有结果。
- 方法固定：SITEdit aa5a414、Pass1 step2000、S2 adapter16000、raw TE、40步、γ2、seed42；Qwen-Image-2.1 原生40步、CFG1、seed42。
- 输入边界：两模型获得同一公开信息。评分 mask/GT/问题答案不能进入生成。只允许确定性几何转换，模型自己的原生定位流程保持不变。
- 评分：冻结官方函数、预处理、模型权重及聚合；涉及 API 时换为用户指定 GPT-5.4，原提示与评分定义保留，明确披露，不与其他 Judge 的论文数字直接混排。
- 异常：原始记录保留、失败不隐去，不自行把缺失分数补成零。
- 临时产物：`/tmp/ifbench/external_pilots_20261107/`。
- 已确认的小子集结果：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/pilot_20261107/`。
- 可视化：`/opt/tiger/tanyue/visualization_tmp/CompBench_20261107/`。

下载版本、输入边界、官方评分代码与执行命令见下文；本小子集已完成。当前的全量方案另见 [COMPBENCH_FULL_RUN.md](COMPBENCH_FULL_RUN.md)。

## 已确认的发布接口处理

用户确认：8 条来自六个原生可评分子任务：add/remove/replace/implicit_reasoning 各 1；multi_object_add/remove 各 2。action/location/view 缺 mask 且官方脚本不覆盖，不进入本轮子集。

## 冻结的数据与评分实现

数据：`BohanJia/CompBench` revision `a4c5a4d1854056d24aad43a494772dc90588d426`，CC BY 4.0。只读复用已有官方 Parquet，核对完整 SHA256 后将八条样例解码到独立 `datasets/CompBench-Pilot-20261107`；SUBSET.json 与 SOURCE.json 保存来源和选择。

编辑只获得源图和完整原始 instruction；SITEdit 对公开复合指令一次 Pass1 后一次编辑。评分的目标图、mask、caption 不进入模型。两方法使用原生固定配置，公共约 1MP 输入、输出回源；官方评分再按其规则缩放到 512×512。

五项指标直接调用官方 `eval_all.py`：LC-T、LC-I 使用 CLIP ViT-L/14（官方 OpenAI 权重 revision `32bd64288804d66eefd0ccbe215aa642df71cc41`）；多目标 caption 各算 LC-T 后取均值；背景 PSNR/SSIM/LPIPS 用 mask 将编辑区置零，LPIPS 为 squeeze。评分环境 transformers 4.57.1、torchmetrics 1.8.2、CPU FP32；没有付费 API。

工程兼容：CLIPScore 用路径内的 `openai` 识别本地模型，因此通过只读符号链接访问相同权重。未修改官方指标或模型文件。

```bash
python -I scripts/compbench_prepare.py --existing /path/to/CompBench --dataset /path/to/CompBench-Pilot-20261107 --output /path/to/pilot/bundle
python scripts/run_external_pilot.py --config configs/external/compbench.json --bundle /path/to/pilot/bundle --output /path/to/pilot/run --gpus 6 7 --attempt pilot01
python -m samtok_benchmark.external_compbench.score --bundle /path/to/pilot/bundle --run /path/to/pilot/run --output /path/to/pilot/scores --upstream /path/to/compbench-ca0ec0d --clip-path /path/to/openai/clip-vit-large-patch14
python -m samtok_benchmark.external_compbench.report --root /path/to/pilot --previews /path/to/visualization --doc docs/COMPBENCH_RESULTS.md
```

评分设置 `CUDA_VISIBLE_DEVICES=''`，包路径加入 PYTHONPATH。`--case-ids` 可限定冒烟两条；之后全清单运行会校验并复用已完成请求，不重采样。
