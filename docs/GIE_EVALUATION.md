# GIE-Bench 小子集评测

状态：用户已于 2026-11-07 批准实施。此文档先于评测代码及生成创建。

## 范围与来源

- 官方仓库：https://github.com/apple-aiml-research/ml-gie-bench
- 冻结 commit：`06953ba0faa2be70ac814b26a7ba0a0ae13c497e`。
- 数据：官方 `gie_bench_json.zip` 与 `images2000urls/` 原始来源链接。
- 许可：仓库 `LICENSE`；数据 `LICENSE_DATA`（CC BY-NC-ND）。只从官方列出的来源获取，不绕过访问限制。
- 选取 9 类编辑各 1 条，抽样 seed 20261107，生成之前冻结。样本不足或来源不可访问时明确记录，不依据输出换样本。
- 这是子集可运行性及能力验证，不作为全量 benchmark 分数。

## 模型与公开输入

两个模型接收同一源图及原始 `edit_instruction`。`object_mask`、问答和正确答案仅供评分，不能进入任何编辑器或 Pass1。

SITEdit 使用 aa5a414 冻结源码、Pass1 LoRA step 2000、S2 adapter 16000、raw SAMTok TE、40 步、token guidance 2、seed 42。文字任务使用原生 Pass1 → S2，复用已经核验的外部评测指令插入规则。Qwen-Image-2.1 使用原始模型、40 步、CFG 1、seed 42。两者沿用约 1MP 公共画布和几何还原；不使用模型之外的定位、指令改写或结果挑选。

## 评分

1. 功能正确性：逐字保留官方 `GPT-4o_VQA_evaluation.py` 的系统提示、题目、选项和源图/输出图顺序，模型改为用户指定的 `gpt-5.4-2026-03-05`，精确匹配官方 expected_answer。记录所有请求、答案、用量和输入绑定。
2. 区域 CLIP 与 SSIM：官方 `masked_clip_ssim_evaluation.py`；OpenAI CLIP ViT-B/32 空间 token 池化；224×224 LANCZOS；SSIM 使用官方灰度与 mask 定义。
3. MSE/PSNR：官方 `masked_mse_evaluation.py`、`masked_psnr_evaluation.py`，保留 SIFT 配准、阈值和原始像素量纲。实现与数据不一致时披露，不静默修正。
4. Judge 仅切换传输和模型，其他科学定义保留。分数只与本次同口径重跑的底座比较，不与原 GPT-4o 论文数字混排。
5. 每个请求只生成一次。缺失/失败逐条保留；官方未定义的惩罚不自行补零。逐指标报告有效分母。

## 发布数据与实现核对

- JSON 有 10 个原始 edit_type 标签。依论文 §3.1，将 `Scene Change`（74）与 `Background Change`（46）合为 `Scene/Background Change`（120），与其余 8 类各 120 条对应。抽样规则与映射已经写入 `SUBSET.json`，不是看输出后合并。
- mask 实际取值为 0/1。官方 MSE/PSNR 使用 `<128` 的阈值，因此这两个发布脚本实际对全图配准后计算。本轮原样保留，并使用“官方发布脚本 MSE/PSNR”标注，不能将其解释为正确排除了编辑区域的背景指标。CLIP/SSIM 正常使用 0/1 mask。
- 问答评分只调用官方选定函数，替换模型与传输；不运行上游占位客户端和命令行入口。

## 文件组织

- 数据：`/mnt/bn/strategy-mllm-train/user/tanyue/datasets/GIE-Bench/`，包含 `SOURCE.json`、原始文件、固定子集与图像。
- 正式批准的小子集产物：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_gie/pilot_20261107/`。
- 临时诊断：`/tmp/ifbench/external_pilots_20261107/`。
- 对比图：`/opt/tiger/tanyue/visualization_tmp/GIE-Bench_20261107/`。
- 分支：`eval-gie`，基于已验证的 `eval-magicbrush` commit `06ebe0f7c4387a9c8a93ee667f7390dcafc9220f`，复用冻结的生成适配器。其他 worktree 保持不变。

## 执行顺序

核对来源和评分 → 固定子集 → 构建公开/私有输入 → CPU 合约检查 → 2 条端到端冒烟 → 余下 7 条 → 分数、逐例对比、耗时与失败清单。配置不变且绑定一致的冒烟结果直接复用。
