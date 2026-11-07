# CompBench 全量评测

2026-11-07 用户授权全量评测；本方案先于实现和推理记录。分支 `eval-compbench`，保留既有八条 pilot 的输入、代码和结果。小样本结果不能替代本页的全量结果。

## 依据与范围

- [最新版论文 v4](https://arxiv.org/abs/2505.12200v4) 提出 benchmark、数据构建与指令分解策略，没有发布独立的编辑模型。因此没有名为“CompBench”的待评测模型。
- [官方代码](https://github.com/comp-bench/CompBench/tree/ca0ec0dea6ce2ced7d42e26afdedd712034e6b56)，commit `ca0ec0dea6ce2ced7d42e26afdedd712034e6b56`。
- [官方数据](https://huggingface.co/datasets/BohanJia/CompBench/tree/a4c5a4d1854056d24aad43a494772dc90588d426)，revision `a4c5a4d1854056d24aad43a494772dc90588d426`，CC BY 4.0。数据卡的 `train` 是发布分区名，本次不训练任何模型。
- 完整保留 3,481 条编辑请求：2,905 条单轮，以及 288 组两轮编辑（576 条）。不根据输出、评分或图像重复情况筛选请求。

| 发布任务 | 请求数 | 评分 |
|---|---:|---|
| 添加 / 删除 / 替换 | 982 / 1,331 / 152 | 官方五项客观指标 |
| 隐式推理 | 100 | 官方五项客观指标 |
| 多目标添加 / 删除 | 72 / 72 | 官方五项客观指标 |
| 连续两轮添加 / 删除 | 288 / 288 | 每轮分别计算官方五项客观指标 |
| 动作 / 位置 / 视角 | 89 / 73 / 34 | 作者公开 v2 提示词 + GPT-5.4，0–10 分 |

## 固定方法与输入

所有方法仅接收当前源图与原始公开指令。评分 mask、目标图、局部 caption 不进入编辑或原生规划器。沿用 IF-Bench 的约 1MP 画布及输出回源规则；原始图均为 640×640，评分时再使用作者代码的 512×512 预处理。一次请求仅采样一次，seed 42，不做分数驱动的候选搜索、外部指令改写或 GT 回贴。

| 方法 | 固定推理配置 | 原生额外流程 |
|---|---|---|
| SITEdit | aa5a414；Pass1 step 2000；S2 adapter 16000；raw SAMTok TE；40 步；token guidance 2 | 对公开完整指令生成区域码，再联合编辑；负分支为同一句去 token |
| Qwen-Image-2.1 | 40 步、CFG 1、output_resolution 1024、KV cache | 模型原生编码与 CPU offload |
| Qwen-Image-Edit-2511 | 40 步、true CFG 4、guidance 1、空格负提示 | 原生单图编辑 |
| RePlan / Qwen-2511 | 40 步、true CFG 4；expand 0；attention switch 0.5 | 原生规划器，最多 2,048 个生成 token；保存规划与调用数 |
| MIRAGE / Qwen-2511 | 40 步、true CFG 4、patch ratio 0.4、padding 10 | 原生解析与定位；thinking 关闭，贪心；保留 IF-Bench 配置，不使用 RefEdit 特定的 0.2 |
| MICE / Klein-4B | 4 步、guidance 1；原生注意力参数和 200-token 完整性检查 | 原始文本作为 global instruction，无外部框或 mask |
| FLUX.3 Klein distilled | 16 步；PUP 关闭；原生单图引用前缀 | 不填虚构目标框 |
| FLUX.2 Klein-9B distilled | 4 步、guidance 1、max sequence length 512 | 原生单图编辑 |

各方法的源码、权重 revision 与参数写入 `configs/external/compbench_full.json`。复用已经验证的 `external_refedit.adapters`；不改 adapter 或冻结模块。SITEdit 继续使用 pilot 的完整公开指令作为单个复合 U1，不读取评分 caption 拆解目标。

**两轮协议：**同一 `(task, image_path 去掉 turn 前缀)` 的两条记录组成一条链。第一轮使用发布源图；第二轮只使用本方法第一轮恢复至源图尺寸的输出和第二轮原始指令。每轮仍只调用一次编辑流程。第二轮的原生 Pass1 / planner 重新查看实际输入。第一轮失败或未完成时，第二轮记录依赖失败或等待，不拿 GT 中间图代替。评分继续使用官方每一轮的 canonical source、mask、caption 和 target，因此第二轮分数包含累积编辑误差。

## 评分与汇总

3,285 条请求直接使用官方 `eval_all.py` 的 `CompBenchEvaluator.preprocess_images` 和 `calculate_metrics`：LC-T ↑、LC-I ↑、背景 PSNR ↑、SSIM ↑、LPIPS ↓。CLIP 为 OpenAI ViT-L/14 revision `32bd64288804d66eefd0ccbe215aa642df71cc41`，LPIPS 为 squeeze。CPU FP32，保持 pilot 的软件环境。多目标 caption 按官方规则分别评分后平均，不改变 bbox / mask 边界或预处理。

这些分数不是成功率：LC-T 衡量目标区域与目标文字描述的匹配；LC-I 衡量该区域与目标图的 CLIP 相似度；后三项衡量背景保留，PSNR 的单位为 dB，LPIPS 越小越好。

按官方代码先计算子任务均值；Local Editing 对添加、删除、替换三个子任务做等权平均；Multi-object 对添加、删除等权平均；Multi-turn 按轮次分别对添加、删除等权平均。同时提供每个子任务、每轮的完整样本数、成功数、失败数、缺分数。不同指标不合成一个未经定义的总分。保留原始精度，并给出复现官方脚本三位小数中间舍入的对照字段。

动作、位置、视角的官方代码未发布 VLM 入口。v4 §4.1 使用 GPT-4o、Qwen2.5-VL-72B 与人工评分；公开可定位的完整提示词在 [v2 Fig.6 / Appendix D](https://arxiv.org/html/2505.12200v2#A4)。**用户已确认**采用该公开提示词、单次 temperature 0、指定的 `gpt-5.4-2026-03-05`，最多 196×8=1,568 次正式请求；Qwen / Human / 三者平均标 N/A，不与作者不同 Judge 的数值混排。提示词逐段对照原图转录，仅合并排版换行；示意图片和示例指令不作为额外示例发送。每请求发送原始源图、回源后的模型输出、该请求原始指令；不发送 GT、mask、模型名称。max_tokens 8192、关闭 SDK 自动重试；原始响应、受理记录与解析结果分开保存。未受理和已受理未作答严格区分，后者不自动重判。

提示词及原图证据：`.ifbench-tmp/compbench_full_20261107/prompts/`；`paper_v2_prompts.json` SHA256 为 `788e7d7a4eefd5bd7af1244eef5439a9d39ba815746c8b7055aea9c02cc48242`。该 Judge 使用此前已验证的 GPT-5.4 服务接口；本轮八方法冒烟运行官方五项客观指标，VLM 请求格式与解析做 CPU 验证，不新增付费冒烟调用。三类实际 VLM 评分由正式运行完成，不能把 CPU 验证称为已完成 VLM 评分。

生成失败、依赖失败、评分失败与已受理未作答分别记录；不得丢弃请求或擅自填零。有效值均值须同时报告覆盖率，不宣称是不含缺分的全量均值。基础设施中断只能经过记录的放行操作重跑，不能因效果不好重采样。

## 路径与运行安排

- 现有原始 Parquet：`/mnt/bn/strategy-mllm-train/user/tanyue/datasets/CompBench/`，只读。
- 新的解码资产与来源清单：`/mnt/bn/strategy-mllm-train/user/tanyue/datasets/CompBench-Full-20261107/`。
- 输入包、代码快照和运行准备：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/compbench_full_20261107/`。
- 冒烟及 CPU 测试：`/tmp/ifbench/compbench_full_20261107/`。
- 正式结果预定：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/full_20261107/`。
- 展示拼图：`/opt/tiger/tanyue/visualization_tmp/CompBench_Full_20261107/`。

先完成每方法少量冒烟和官方评分，实测单请求耗时后计算 GPU 小时。若在本机可用卡上的预计正式时间超过八小时，则按既有约束发布单机八卡前台 ARNOLD 入口，由用户提交。不中断其他任务，不自动启动多机作业。

## 当前进度

3,481 条全量输入和 288 组完整两轮链已经构建、核验；八方法冒烟、官方客观评分和续跑验证已经结束。当前准备发布全量运行包，尚无全量正式分数。下面保留本轮准备过程的实测记录。

- 12:17 UTC：10 项 CPU 合同测试通过，覆盖两轮输出依赖、禁止 GT 替代、父结果篡改 / 跨模型隔离、子任务等权平均、完整分母以及冻结 SITEdit 配置。评分环境已归档并成功进行 CPU 解包 / 导入验证；修复了旧 Python 不支持 tarfile `filter=` 的兼容问题，保留路径及链接检查。
- 冒烟清单在推理前固定为第一条多目标添加与第一组两轮添加，共 3 条 / 方法。清单：`/tmp/ifbench/compbench_full_20261107/SMOKE_SELECTION.json`。正式 run 不复用冒烟结果。
- 12:22 UTC：全量输入完成，digest `3ada41250a3d42e6c1ad4a82f240c04977ed801c78f87ab154691e80e05fe586`。288 组链的第一轮 GT 与第二轮 canonical source 的文件字节和 RGB 像素全部一致；全部原图为 640×640；196 条无 mask 请求恰为 action/location/view；288 条第二轮公开记录均不含 GT 输入路径。已在当时空闲的 GPU 4、5 启动三条 / 方法冒烟。
- 冒烟观察：SITEdit、Qwen-Image-2.1 各 3/3 生成及客观评分完成。MIRAGE 在多目标添加的原生解析中出现 `Refer_object` 与 `New_edit_instruction` 列表长度不一致，官方 `mirage/vlm.py:470` 的严格 `zip` 抛错，编辑阶段记为依赖失败。未重采样或补写规划；其他样例与方法继续运行。这是原生规划失败，不能解释为硬件故障，也不能把缺失指标填为零。

## 冒烟完成与预算

固定三条 / 方法已完成：23/24 出图并得到五项客观评分；MIRAGE 的一条原生规划失败保留，未调用编辑器，没有数值填补。所有已产生输出都恢复到 640×640 后评分；已完成两轮链均绑定本方法实际前一轮输出。Qwen-Image-2.1 的三条结果跨 GPU 续跑验证全部复用，新增推理为零，raw/output SHA256 均通过校验。

| 方法 | 成功 / 应测 | 完整请求平均秒数 | 峰值 reserved GiB | 全量生成 GPU 小时估算 |
|---|---:|---:|---:|---:|
| SITEdit | 3 / 3 | 54.12 | 44.18 | 52.33 |
| Qwen-Image-2.1 | 3 / 3 | 44.30 | 20.21 | 42.84 |
| Qwen-Image-Edit-2511 | 3 / 3 | 75.01 | 58.72 | 72.53 |
| RePlan | 3 / 3 | 98.72 | 58.58 | 95.46 |
| MIRAGE | 2 / 3 | 80.98 | 59.15 | 78.31 |
| FLUX.3 Klein | 3 / 3 | 9.12 | 27.64 | 8.82 |
| MICE | 3 / 3 | 5.50 | 18.71 | 5.32 |
| FLUX.2 Klein-9B | 3 / 3 | 4.18 | 36.08 | 4.05 |

平均秒数包含成功请求的原生 Pass1 / planner 与编辑，不含权重加载和进程切换；MIRAGE 只用两条成功请求估算正常路径耗时，失败及其耗时仍保留。每方法仅三条，这些是资源规划估算，不是全量实测。总计约 **359.65 GPU 小时**，八卡理想生成约 **44.96 小时**。正式单机八卡建议预留 **约 48–60 小时**，实际受任务复杂度、NAS、加载和服务延迟影响。此范围为调度余量，非已测完成时间。

客观评分本轮平均 2.52 秒 / 输出；3,285×8 输出在八个 CPU worker 上单独执行约需 2.30 小时。入口在某方法的八个生成 shard 都结束后，立即并行启动该方法的客观评分与 GPT 评分，同时 GPU 继续下一方法，因而无需把这部分全部加在生成尾部。GPT 本轮尚无实际服务耗时，不能给精确 ETA。其最多 1,568 次请求使用四路并发和独立受理记录。

原始冒烟：`/tmp/ifbench/compbench_full_20261107/smoke/`。真实输入输出拼图与实测成本：`/opt/tiger/tanyue/visualization_tmp/CompBench_Full_20261107/smoke-final/SMOKE.md`。完整性 / 续跑证明：`/tmp/ifbench/compbench_full_20261107/RESUME_PROOF.json`。发布前会将上述证据复制到 NAS 的运行准备目录，不放入正式结果根。

## 单机八卡运行入口

正式运行需要一台八卡 H100 80GB ARNOLD worker，挂载相同 NAS。每卡独立一份模型，按序列分片；无 NCCL / 跨机通信，不占用 29xxx 端口。模型按固定顺序执行，保留原生步数和精度，不使用会改变采样流程的加速替代实现。

运行包通过 `scripts/compbench_publish.py` 从已推送的干净 `eval-compbench` commit 导出；启动不访问 GitHub。代码、配置、完整输入索引、评分提示词和环境归档都有 SHA256。启动前确认 GPU 每卡空闲至少 70,000 MiB。

```bash
export COMPBENCH_API_KEY_FILE=/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/secrets/gpt54.key
COMPBENCH_ATTEMPT=run001 bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/compbench_full_20261107/package-v1/start.sh
```

入口保持前台；正式根是 `experiments2/SAMTokEdit/external_compbench/full_20261107/`，生成在 `run/`，客观 / VLM 原始响应及分数在 `scores/`，报告在 `reports/<attempt>/`，启动日志在 `launches/<attempt>/`。逐卡阶段进度位于 `run/attempts/<attempt>/*.progress.json`，按新增日志增量计数；不逐批全量扫描输出。每方法每卡的完成标记用于触发并行评分。

续跑仅需换新 attempt（例如 `run002`），保持同一输入包和结果根。已完成结果先核验再跳过，绝不覆盖。模型原生失败保留；受理后没有终态的请求不会自动重跑，必须检查基础设施中断证据后另行记录放行。付费评分只允许使用这一个正式根，未作答的已受理 key 不自动再次发送。所有请求保留在预定完整分母内。

目前**全量正式实验尚未启动**：按先前约定，本机预计超过八小时的正式实验交由用户提交 ARNOLD 作业。本轮没有占用 GPU 0–3，也没有停止其他任务。
