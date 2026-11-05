# MagicBrush：SITEdit 外部评测方案

本方案于 2026-11-05 在实现及生成之前写定。执行证据见 [MAGICBRUSH_PROGRESS.md](MAGICBRUSH_PROGRESS.md)。只使用 SITEdit `aa5a414` 主行，不做 checkpoint、LoRA 强度、quality-anchor、v5 或提示词择优。任何未运行的项目明确标注待执行，冒烟分数不作为基准结果。

## 1. 官方资料与冻结版本

- [论文](https://arxiv.org/html/2306.10012v3)：MagicBrush: A Manually Annotated Dataset for Instruction-Guided Image Editing，NeurIPS 2023 Datasets and Benchmarks。
- [官方仓库](https://github.com/OSU-NLP-Group/MagicBrush/tree/d2d7f84d71ff23154e3f16f0c8f19392782bd201)：固定 `d2d7f84d71ff23154e3f16f0c8f19392782bd201`。阅读 `README.md`、`LICENSE`、`evaluation/{README.md,image_eval.py,export_test_set.py}`，不执行下载包中的程序。
- [官方 HF 数据](https://huggingface.co/datasets/osunlp/MagicBrush/tree/6c254560879df7851233ea0fd2ae2a62764d0ef2)：固定 revision `6c254560879df7851233ea0fd2ae2a62764d0ef2`，`gated=false`。2026 年 10 月起 test 已公开，旧文档中的申请流程已过时。
- 数据和官方评测代码采用 **CC BY 4.0**；原始 COCO 图像保留其来源权利。官方 IP2P 模型另受 CreativeML Open RAIL-M 约束，本次不下载该 checkpoint。
- 完整数据含 5,313 个会话、10,388 个编辑轮次；本次只下载 test 的 **535 个会话、1,053 个轮次**（六个 parquet，约 3.07 GB）及四个官方 metadata JSON。不下载 train/dev。
- 源图来自 COCO；人工指令、自由形状 mask 及 DALL-E 2 编辑结果组成每轮样本；一个会话最多三轮。mask 是编辑区域，并不保证等同于实例分割。

## 2. 四个评测条件

| 输入轨道 | 独立单轮（single-turn / all-turn） | 连续多轮（multi-turn / final-turn） |
|---|---|---|
| mask-free | 每轮用对应官方 source（第 2/3 轮为 GT 上一轮输出）与原始 instruction；评全部 1,053 轮 | 从会话原图开始，每轮使用本方法上一轮输出与当前原始 instruction；评 535 个会话最终图，包含仅一轮的会话 |
| mask-provided | 同上，额外提供该轮官方 mask | 使用前一轮本方法输出，提供当前轮官方 mask；不根据输出重新定位或修 mask |

每轨道每方法生成 `1053 + (1053 - 535) = 1571` 张不同请求输出；第一轮在独立／连续设置下相同，精确复用。八方法两轨道共 **25,136** 个生成请求，单次采样、seed 42。不把第二轮 GT 输入混入连续编辑，也不只评第一轮来冒充官方 single-turn。前一轮失败则后续连续请求记为依赖失败，不换用 GT 补跑。

### 2.1 共享图像与信息边界

官方第一轮源图有 533 张为 500×500、2 张为 1024×1024；后续源图、所有 mask 和 GT 均为 1024×1024。**固定公开坐标网格为 1024×1024**：源图先转 RGB 并按 LANCZOS 确定性缩放到这个常量网格，再沿用主评测约 1MP 画布及输出逆映射（不改 `ifbench/canvas.py`）。这样第一轮不会因恢复到 500px 而令全部后续编辑持续降采样。该常量不按 GT、caption 或 mask 内容选择，两条输入轨道完全一致。所有方法使用相同 clean canvas、原文 instruction；只有 mask-provided 可读公开 mask。连续编辑每轮将上一轮恢复到 1024px 的本方法输出重新映射到公共画布。记录原图／画布尺寸、mask 转换、实际输出尺寸以及调用文本。保存 raw 与恢复后的 output；不贴回、不修背景。

实际 PNG 的 mask 是 RGBA，透明处为可编辑区域。固定取 **alpha < 128** 为二值可编辑区（255），其余为 0，再按 NEAREST 映射到画布；不从 RGB 内容或 GT 差异推导区域。保留原始 mask 字节和派生二值 mask。未知格式、空编辑区、非预期尺寸一律显式报错；颜色轮廓标记只由公开 mask 派生。

GT target、local/global descriptions 仅供评测和核验，禁止进入模型 adapter。全部方法原生 planner 只能看到当前公开图像与指令；mask-provided 可看该 mask 的确定性标记图。

### 2.2 八方法输入与冻结参数

| 方法 | mask-free | mask-provided | 冻结参数 |
|---|---|---|---|
| SITEdit / SAMTokEdit | 原文 U1 → Pass1 定位区域码 → S2 | 官方 mask → 原生 SAMTok codec 区域码 → S2，不调用 Pass1 grounder | aa5a414；raw SAMTok TE；40 步；γ=2；负向同句去 token；seed 42 |
| Qwen-Image-2.1 | 原文 + 清图 | 清图 + mask 轮廓标记图 + 固定角色说明 + 原文 | 40 步，CFG 1，1024 分辨率策略，KV cache，原生 CPU offload |
| Qwen-Image-Edit-2511 | 原文 + 清图 | 同上 | 40 步，true CFG 4，guidance 1，negative 单空格 |
| FLUX.3 Klein distilled | `<ref_image_0>` 引用前缀 + 原文 + 清图 | 清图 `<ref_image_0>` + 标记图 `<ref_image_1>`，沿用 IF-Bench 的显式引用角色说明 + 原文 | 16 步，PUP off，boxes=None |
| FLUX.2 Klein-9B distilled | 原文 + 清图 | 清图 + 标记图 + 固定说明 + 原文 | 4 步，guidance 1，文本上限 512 |
| RePlan（Qwen2511） | 原生 planner → editor | planner 看标记图与原文，editor 编辑清图 | 40 步，CFG 4，expand 0，attention switch .5，规划上限 2048；SDPA |
| MIRAGE（Qwen2511） | 原生 parser/locator → 联合编辑 | parser 原文，locator 看标记图 + 对应提示，editor 编辑清图 | 40 步，CFG 4，原生默认 patch ratio .4，padding 10；不沿用 RefEdit 专用 .2 |
| MICE（Klein-4B） | 原文作全局文本 | 原文与公开 mask 作原生区域绑定 | 4 步，guidance 1；保留原生 200-token 检查与注意力默认 |

SITEdit 源码与 `configs/ifbench/main_row.json` 必须一致；Pass1 step 2000 与 S2 adapter_16000 不变。单轮原文作为一个 U1（不外接 LLM 拆分）；单目标使用训练时的裸句格式，区域码插入复用 RefEdit 已固定的纯文本规则，不看输出后改写。无合法预测码时仅按方法既有规则退回原文并计数。给定 mask 直接编码，不先做外部 SAM；codec 属于方法原生表示。mask-provided 单独成表，不与 mask-free 混合排名。

基于 `origin/eval-refedit` 的 `c9f9447` 开新分支：它已有全部八方法原生后端、SITEdit 冻结源码校验、记录与断点续跑，以及单机 ARNOLD 环境归档。新模块为 `src/samtok_benchmark/external_magicbrush/`，不改 `external_refedit`、`external_mira`、其他 worktree 或 IF-Bench 冻结文件。新配置复用其权重／源码版本；MIRAGE 恢复 IF-Bench 的原生默认 .4，并明确不将 .2 描述为 MagicBrush 推荐值。

## 3. 官方指标与本次实现

以固定官方 `evaluation/image_eval.py` 为语义依据，独立实现可审计的逐图结果与汇总，不执行数据包自带代码，不调用 GPT 或其他付费接口。

| 指标 | 官方定义与实现位置 |
|---|---|
| L1 ↓ | `eval_distance`：输出 resize 到 GT 尺寸；RGB 转 [0,1]，逐图所有像素通道的平均绝对误差，再对图取平均 |
| L2 ↓ | 同上，`nn.MSELoss`，是均方误差，不开根号 |
| CLIP-I ↑ | OpenAI **ViT-B/32**，官方预处理；输出与 GT 的图像 embedding 余弦相似度 |
| DINO ↑ | 原版 DINO **ViT-S/16**（`dino_vits16`，不是 DINOv2/B16）；短边 256 BICUBIC、中心裁剪 224、ImageNet mean/std；CLS embedding 余弦 |
| CLIP-T ↑ | 同一个 OpenAI ViT-B/32；输出图像与官方 **local description** 文本 embedding 的余弦，不使用编辑指令或 global caption 代替 |

权重、实现版本、预处理、精度及 SHA 在运行配置／SOURCE 中固定。评分模型只用受信的依赖实现；远程数据和模型目录里的 Python 不会被导入，模型权重使用安全加载。逐图保存五指标与 GT CLIP-T 诊断；失败／缺项记 missing，报告目标分母和实际计分数，不填零或静默删除。完整行才视为完整基准得分。可另报各方法共有成功子集，但不替代主分母。

具体实现使用发布者提供的 HF 权重转换：OpenAI `clip-vit-base-patch32@3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268`、Facebook `dino-vits16@abe3b354cb6a9b6f146096b14a4a9d7eecbcb4bd`，安装环境中的 Transformers，FP32、eager attention、TF32 关闭。预处理及余弦定义保持上述公开 scorer 口径；与旧 OpenAI CLIP CUDA/FP16 实现不宣称逐位相同。已在 CPU 核验相同图像的 L1=L2=0、CLIP-I=DINO=1。

官方 local descriptions 中有三条空字符串：`248403-1`、`411530-1`、`551701-2`。沿用官方代码行为，对原样空字符串编码，保留在分母并显式披露；不改成指令、global caption 或人工补写文本。

DINO 特别核验：HF 转换版的配置遗留 `layer_norm_eps=1e-12`，本实现显式恢复[原始 `vit_small` 的 `1e-6`](https://github.com/facebookresearch/dino/blob/7c446df5b9f45747937fb0d72314eb9f7b66930a/vision_transformer.py#L222-L225)。从官方地址下载原始 tensor checkpoint，仅用 `weights_only=True` 读取；198 个转换后参数张量逐个与原始权重完全一致。以独立实现的原始 Transformer 运算核验两张真实测试图，两组 CLS 特征最大绝对误差均为 0、余弦均为 1。证据在共享包 `METRIC_PARITY.json`；核验脚本为 `scripts/magicbrush_metric_check.py`，未执行下载的 Python 或 TorchScript。

**论文与现行代码的差异必须披露。** 论文 Table 3 将 mask-provided 的 L1/L2/CLIP-T 定义为区域指标，且 L1/L2 数值量级不同；现行官方公开 scorer 对这五项均使用完整图像，没有区域模式。故本次两输入轨道统一采用上述公开代码的整图指标，mask-provided 标为“公开 scorer 下的有 mask 扩展”，不声称复现论文 Table 3 区域指标，也不据此和 GLIDE/Blended Diffusion 排名。必要的局部诊断明确单列，不替换标准五指标。

其他偏差：生成端统一约 1MP、现代模型官方／IF-Bench 参数、单次 seed 42、SITEdit 自由文本适配；这些不是论文基线的原始配置。论文数字仅列为带来源的历史参考，不和本次重跑方法合并排名。mask 标记图是通用模型的一种输入适配，和原生二值 mask 接口分别记录。

## 4. 已发表基线（历史参考，非本次结果）

来源：[论文 Table 2](https://arxiv.org/html/2306.10012v3#S4.T2)，均为 mask-free。

| 设置 | 方法 | L1 ↓ | L2 ↓ | CLIP-I ↑ | DINO ↑ | CLIP-T ↑ |
|---|---|---:|---:|---:|---:|---:|
| single-turn | InstructPix2Pix | 0.1122 | 0.0371 | 0.8524 | 0.7428 | 0.2764 |
| single-turn | InstructPix2Pix + MagicBrush 训练 | 0.0625 | 0.0203 | 0.9332 | 0.8987 | 0.2781 |
| single-turn | HIVE + MagicBrush 训练 | 0.0658 | 0.0224 | 0.9189 | 0.8655 | 0.2812 |
| multi-turn | InstructPix2Pix | 0.1584 | 0.0598 | 0.7924 | 0.6177 | 0.2726 |
| multi-turn | InstructPix2Pix + MagicBrush 训练 | 0.0964 | 0.0353 | 0.8924 | 0.8273 | 0.2754 |
| multi-turn | HIVE + MagicBrush 训练 | 0.0966 | 0.0365 | 0.8785 | 0.7891 | 0.2796 |

不额外添加未冻结的新生成模型，以优先完成用户指定的八方法一致评测。重跑五指标不等于具备编辑意图达成的人工证明，结论区分像素／表征相似度与编辑执行观察。

## 5. 训练重合审计与统计

直接复用 `refedit_overlap_audit_20261104/{TRAINING.json,COCO_TRAINING_USE.json,GRES_FINGERPRINTS.jsonl}` 及其绑定的 646,908 个训练图像指纹，先核验文件哈希。比较每个会话的 COCO id、原始源图字节／RGB 像素哈希、感知哈希（含镜像）。精确匹配或可追溯实际训练 COCO id 为已确认；感知近邻只作待核候选，不能仅靠 pHash 宣称训练重合。

按 **会话** 统一排除：一张 COCO 源图确认重合，则其全部独立轮次与最终连续结果对所有方法同时排除。主补充子集采用保守规则：排除“可追溯实际微调重合”与“已知 SAMTok/gRES 训练语料中相同 COCO id 或精确图像”的并集；两种证据分别计数，后者不等同于证明冻结 SAMTok checkpoint 实际使用过该条数据。源图及全部 GT 编辑图均进行指纹比对，感知近邻本身不触发剔除。报告全量与无已知训练语料重合子集，不把“未发现”写成“保证未训练”。若只经过重编码或缩放，COCO id 来源证据与像素／感知比对联合核实。

五指标按官方逐图均值。补充 95% CI 采用会话为 cluster 的共享 paired bootstrap（seed 20261105、10,000 次）：单轮重采样会话并保留其中所有轮次，多轮每会话一个最终结果。所有方法使用同一排除清单、同一抽样索引；不把图像内多轮当成独立样本。

## 6. 冒烟、时间门槛和运行约束

- 本机仅 GPU 4–7；**2026-11-05 19:00 UTC 后**，`nvidia-smi` 核实只剩约 1.6 GB/卡的既有进程后才可启动。GPU 0–3 永不使用。不停止别人的 run.py、run_candidate.py、torchrun、vLLM 或主线程任务。
- 每方法 2–3 个固定请求，覆盖无 mask、有 mask、以及连续编辑的前序依赖；输入选择只依赖数据和结构，不按输出择优。分别记录端到端状态、加载／推理耗时和 allocated/reserved 峰值。
- 正式开始前，用本次真实 smoke 的各阶段耗时乘正式请求数估算 GPU·h，额外披露冷加载、评分与连续依赖。若在本机可用卡上超过约 8 h，停止本机正式执行，交付**单机 8 卡 ARNOLD** 前台入口；不使用四机集群，不自行提交平台作业。
- 每请求保存不可变输入身份、admission、阶段计划／token、输出 SHA 和终态。已完成且身份一致则复用；已受理无终态需明确基础设施放行记录，不能自动重采样。日志、缓存不覆盖完成记录。只按 PID 结束自己启动的进程。
- 端口只允许 39000–49999；本任务正常单卡 worker 与免费特征评分无需联网服务。

## 7. 路径

| 内容 | 路径 |
|---|---|
| 新 worktree / 分支 | `/opt/tiger/tanyue/if-bench-magicbrush` / `eval-magicbrush` |
| 原始数据、SOURCE、解码 | `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/MagicBrush/`，原始下载隔离在 `raw/` |
| 冒烟、调试、研究缓存 | `/tmp/claude_magicbrush_20261105/` |
| 共享启动包和中间准备材料 | `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/magicbrush_20261105/` |
| 正式实验 | `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_magicbrush/` |
| 用户拼图／预览 | `/opt/tiger/tanyue/visualization_tmp/MagicBrush_20261105/` |

所有读取下载数据的 Python 入口使用 `-I`；只显式加入本仓库与冻结方法的受信源码路径。不提交数据、输出或密钥。仅提交／推送 `eval-magicbrush`；提交使用英文标准格式且无额外贡献者署名。
