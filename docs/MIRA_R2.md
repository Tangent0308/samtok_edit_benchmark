# MIRA-Bench：R2@1000 全量评测与完整方法对比

本页记录 **2026-11-10 已完成的 200 张 MIRA-Bench 全量评测**，以及与此前五行结果的统一对比。SITEdit R2@1000 已生成并评分 **200/200** 张；四个其他方法和 SITEdit v4 直接读取 11-03 完成的逐图记录，没有重新生成或重新判分。共五种方法、六行配置。完整公共协议和各基线推理细节见 [MIRA_EVALUATION.md](MIRA_EVALUATION.md)，通用运行入口见 [MIRA.md](MIRA.md)。

## 1. 数据与任务

- 使用官方数据 revision `fce5795af4276c5d312d3d68c13879c8d9735f55` 的全部 **200 张源图**，每图 **5 项联合编辑**，共 1,000 个编辑项。统计单位是源图，不是把五项当作独立样本。
- 输入只有同一张约 1MP 公共清图和公开文字指令。所有模型均不接收 GT 多边形、mask、用户标记图或参考答案。
- SITEdit 按公开指令的固定语法分成 U1–U5；Pass1 一次预测五项区域码，S2 一次联合编辑整图。五项可能涉及同一对象或部件，不等于五个独立实例。
- 保存模型 `raw.png`；按公共画布的几何记录去 padding、恢复源图尺寸为 `output.png`，再评分。没有 GT paste-back、背景融合或多次采样选优。
- 本页只报告完整 200 张；早期 30 张诊断及 11-03 的 198 张附加分析是不同统计集合，不混入本表。既有训练重合审计的范围和证据保留在 [公共协议 §7](MIRA_EVALUATION.md#7-训练重合审计与统计方法)；该历史审计不能被解读为已重新覆盖 R2 新增训练数据。

## 2. R2 的实际权重与推理配置

本次按用户指定，仅将原 `external_mira/run_001/CONFIG.json` 中的 **`sitedit.dit_adapter`** 换成 R2 目录，其他生成字段保持一致。这个目录同时提供 **DiT LoRA 和 CodeInjector**，不是只换 LoRA、继续使用 v4 injector。

| 项目 | 本次实际值 |
|---|---|
| 底座 | Qwen-Image-2.1，与 v4 相同的固定权重 |
| 方法源码 | [samtok_edit@aa5a414](https://github.com/Tangent0308/samtok_edit/tree/aa5a414e36c01eba60b37fc46cb9e32f803f8a93)，只读快照 `sitedit-aa5a414` |
| Pass1 | Qwen3-VL-8B-SAMTok + 定位 LoRA step 2000；一次请求输出 U1–U5 区域码 |
| S2 | R2@1000 的 `adapter.safetensors` 和 `code_injector.safetensors` |
| LoRA 强度 | **1.0**；原生 rank=alpha=32，没有强度缩放 |
| 文本编码器 | **raw SAMTok TE**；关闭定位 LoRA，不是原始 Qwen TE |
| Space Token Guidance | **γ=2**，正分支为带区域码的编号指令，负分支为同一指令去掉区域码 |
| 去噪与随机性 | **40 步，seed 42**，每请求一张输出、不重采样 |
| 空间与执行 | 公共约 1MP 画布宽高、KV cache；一次联合 S2 调用，预期 80 次 DiT 前向 |
| 其他 | 不做 latent blending、背景贴回、guidance schedule、off-step 或动态 LoRA |
| Python | Pass1：`env_pass1`（Transformers 5.19.0）；S2：`env_v4`（Transformers 5.12.1） |

完整路径：

```text
方法源码：
/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/deps/sitedit-aa5a414

Pass1：
/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/pass1_localization_lora_formal_20261030_0939/runs/formal/step_2000

R2 DiT LoRA + CodeInjector：
/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/quality_anchor_20261104/runs_v5/v6_full/r2/train/adapter_1000

v4 对照 DiT LoRA + CodeInjector：
/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/qwen21_v3/runs/s2_4n_001/train/adapter_16000

S2 Python：
/tmp/ifbench/external_bench_20261102/env_v4/bin/python
```

R2 配置入口为 [mira_r2_1000.json](../configs/external/mira_r2_1000.json)。实际运行配置保存在结果目录的 `run_001/CONFIG.json`，以该文件及逐图 `call.json/result.json` 为执行证据。

### 权重与流程核验

已逐一复核四个 checkpoint 文件与运行前的 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `adapter.json` | `e6d48b61e37da90d673b7e309aade022ab4e1a450a7280daf858f300b94507a1` |
| `adapter.safetensors` | `c0d15a0c81ca63713c72d8ab0ee23e7f475c4ebe86642601d74b546227e734b8` |
| `code_injector.json` | `c5f3bdf379b56782abacaaade159c57fb890f0097b2b7a49bbed7086a3b23b2b` |
| `code_injector.safetensors` | `205f2c28184e4f2d01018d6f0c9e2252c5c546b697688a29dae5c1af00296fb9` |

元数据中的 `grounding.update=1000` 是实际 checkpoint 步数；`updates=7000` 是训练计划长度，`init_adapter` 是训练初始化来源，二者都不表示本次加载了另一个 checkpoint。

- 全部 200 张的实际参数均为 40 步、seed 42、γ=2、raw TE、一次联合编辑，无 fallback 和 blending。
- 本次重新执行的 Pass1，在全部 200 张上与 v4 的请求、原始回答、解析结果和区域码相同；S2 的输入调用也逐张一致。
- `RESULTS_V5.md` 对应 `tok_r2_1000` 的 30 张诊断中，**30/30 张输出 PNG 与本次对应图逐字节一致**，实际调用及 raw 哈希也一致。
- `RESULTS_V5.md` §16.1–16.3 的小样本对比使用 27 张共同可评分图，不是本页的 200 张；§16.5 的 LoRA 0.75 是另一项实验。本次配置对应 LoRA **1.0**，结果已追加到 **§16.6**。

## 3. Judge 与统计口径

沿用固定 MIRA 官方评分源码 `ff01782a27018ce59f01760e62fe0bcdf518c586` 的提示词、区域证据、换算和聚合，接入 **`gpt-5.4-2026-03-05`**。Judge 配置与 v4 完全一致；运行日期不同，不声称调用确定性。相对上游默认 GPT-5.1 的替换已披露，不直接拼入其他 Judge 的论文数字。

| 指标 | 评分内容 |
|---|---|
| PF | 按五项原文和 GT 区域检查目标编辑是否完成，每图取五项均值 |
| Cons | 同一组目标区域证据中，指令之外的对象/属性变化；每图取五项均值 |
| PQ | 单独输入完整源图与输出，不给编辑指令，评分技术质量和结构伪影 |
| Overall | 先分别求全体源图 PF、Cons、PQ 均值，再计算下式 |

$$\mathrm{Overall}=\sqrt{\min(\overline{\mathrm{PF}},\overline{\mathrm{Cons}})\,\overline{\mathrm{PQ}}}.$$

三项原始 0–25 分除以 2.5，报告为 **0–10，越高越好**。它们不是通过率；Cons 只看 GT 区域内证据，不能当作全图非编辑区保持度。每张图两次 API 请求：一次 PQ，一次五项联合 PF/Cons。源图配对 bootstrap 10,000 次，seed 20261027，percentile 95% CI；每次抽样重算非线性的 Overall。

R2 全部 200 张有效。RePlan 154 的原生零宽度规划框导致生成失败，保留在请求总数中，其展示均值只基于 199 张，不补零；与它的配对比较明确限于共同可评分的 199 张。其余行完整覆盖 200 张。

## 4. 完整结果

数值来自 `r2_20261110/ALL_MODELS_COMPARISON.json`，R2 与 v4 分量差值来自 `r2_20261110/REPORT.json`。表中保留三位小数，统计使用未舍入值。粗体为最高点估计。

| 方法 / 检查点 | 已评分/请求 | PF ↑ | Cons ↑ | PQ ↑ | Overall ↑ | Overall 95% CI |
|---|---:|---:|---:|---:|---:|---|
| Qwen-Image-Edit-2511 | 200/200 | 7.372 | 6.996 | 6.960 | 6.978 | [6.802, 7.145] |
| Qwen-Image-2.1 | 200/200 | 7.443 | 7.760 | **7.276** | **7.359** | [7.175, 7.541] |
| RePlan | 199/200 | 4.593 | 6.442 | 6.923 | 5.639 | N/A（缺 1 张） |
| MIRAGE | 200/200 | 7.730 | 7.182 | 4.336 | 5.580 | [5.390, 5.770] |
| SITEdit v4 / S2@16000 | 200/200 | 7.596 | 7.613 | 6.264 | 6.898 | [6.697, 7.072] |
| **SITEdit R2@1000** | **200/200** | **7.881** | **7.830** | 6.748 | 7.269 | [7.079, 7.440] |

### R2 相对 v4 的变化

| 指标 | R2 − v4 | 配对 95% CI | 图数 |
|---|---:|---|---:|
| PF | +0.285 | [+0.154, +0.414] | 200 |
| Cons | +0.217 | [+0.075, +0.358] | 200 |
| PQ | +0.484 | [+0.298, +0.672] | 200 |
| Overall | +0.371 | [+0.256, +0.494] | 200 |

### R2 相对各方法的 Overall 配对差

| 对照 | R2 − 对照 | 配对 95% CI | 图数 / 范围 |
|---|---:|---|---|
| Qwen-Image-Edit-2511 | +0.291 | [+0.139, +0.432] | 200，全量 |
| Qwen-Image-2.1 | −0.090 | [−0.257, +0.064] | 200，全量 |
| RePlan | +1.632 | [+1.417, +1.834] | 199，共同可评分子集 |
| MIRAGE | +1.688 | [+1.492, +1.874] | 200，全量 |
| SITEdit v4 / S2@16000 | +0.371 | [+0.256, +0.494] | 200，全量 |

- **相对 v4：** 四项分数均提高，配对区间均高于零；PQ 提升 0.484，Overall 从 6.898 增至 7.269。
- **相对其他方法：** R2 的 PF、Cons 点估计最高，Overall 居第二。Qwen2.1 的 PQ 和 Overall 点估计最高；R2 与其 Overall 配对差区间包含零，不能把这两个点估计解释为明确的总体优劣。
- **解释范围：** 本结果支持 R2 完整配置在文本驱动多项编辑中的表现。PF、Cons、PQ 衡量的范围不同，应分别解释；不能从这次完整方法对比单独推出某个训练损失或组件的因果贡献。

## 5. 实际运行、故障与恢复

| 事件 | UTC 时间 / 记录 |
|---|---|
| 启动 | 2026-11-10 19:38:11 |
| 生成完成 | 20:25:46，200/200，无生成失败、无未知 admission |
| 评分完成 | 20:27:37，200/200 |
| 汇总及文档追加完成 | 20:30:05 |
| GPU / Judge 并行 | 本机 GPU 4–7，四条固定分片；20 个十图评分批次，最多四条 API lane |
| API 实际请求 | 404 次，400 个成功响应；4 次资源不足 429，退避后完成 |

原始协调器在 `PROVENANCE.json` 中的 SHA 为 `37345eeb1a4cea879febb0ffa0887ffd4573cae2d592578f94d21e772c915b75`；实际源码副本保存在临时证据目录。后来整理的运行入口增加参数化、恢复检查及持续资源重试，不把维护后的脚本哈希写回历史执行记录。模型、Judge、公开输入和既有结果均未改动。

完成评分后，追加 `RESULTS_V5.md` 时 NAS 的 `flock` 返回 ENOSYS。该问题仅影响文档追加；原始评分和报告已保存。随后改用本机协作锁、写入前字节比对、`O_APPEND` 和追加后完整比对，确认原文前缀保留、§16.6 只追加一次。保留 `STOPPED.json` 等原始异常证据；最终 `STATUS.json` 和 `SUPERVISOR.json` 均为 `complete`。

## 6. 目录与结果文件

以下 `R`、`N`、`T` 仅为文档中的路径简写：

```text
R=/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira
N=/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira/r2_20261110
T=/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/mira_r2_full_20261110
```

| 文件 / 目录 | 内容 |
|---|---|
| `N/ALL_MODELS_COMPARISON.{json,md}` | 当前六行完整方法对比、Overall CI 和配对差值 |
| `N/REPORT.{json,md}` | R2/v4 的逐图分数、四项均值、区间和配对差；主要统计证据 |
| `N/run_001/CONFIG.json`, `RUN.json`, `source_snapshot/` | 实际配置、源图列表、冻结源码摘要及副本 |
| `N/run_001/sitedit/tokens/<case>/` | 每张图的 Pass1 请求、回答、区域码及诊断 mask |
| `N/run_001/sitedit/edit/<case>/` | `call.json`、`result.json`、`raw.png`、`output.png`、admission |
| `N/scores_gpt54/lane{0..3}_batch{00..04}/sitedit/` | `JOB.json`、`JUDGE.json`、逐图分数、请求/回答、尝试记录 |
| `N/PROVENANCE.json`, `VERIFICATION.json`, `PASS1_PARITY.json` | 权重文件哈希、执行来源、统计及 Pass1 一致性核验 |
| `N/STATUS.json`, `SUPERVISOR.json` | 生成、评分和汇总的最终状态 |
| `R/run_001/`, `R/scores_gpt54_001/` | 只读的五行原始生成、规划和评分 |
| `R/audited_report_v2/REPORT.json` | 原五行全量及历史附加子集汇总，未改动 |
| `T/WEIGHT_INFERENCE_AUDIT.json`, `PILOT_PARITY_AUDIT.json` | 正确权重/推理及 30 张 PNG 一致性审计 |
| `T/run_mira_r2_full.snapshot.py`, `supervise_mira_r2_full.snapshot.py` | 实际运行脚本的保留副本 |
| `T/DOCUMENT_APPEND_REPAIR.json`, `CONTROLLER_POST_RUN_FIX.json` | 文档追加故障、修复与保留原文证据 |

主要统计文件 [REPORT.json](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira/r2_20261110/REPORT.json) SHA-256：`a97cdefb8f7d948e6e862690db75d9655cb96a52ba358f6efa4a535a7fc78dcf`。

统一项目汇总：[RESULTS_V5.md §16.6](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/quality_anchor_20261104/RESULTS_V5.md:703)。实际出图初检：[001/004 的 source、v4、R2 对照](/opt/tiger/tanyue/visualization_tmp/MIRA_R2_20261110/initial_generation_check.png)，它是生成期间固定查看的两例，不代表总体样本。

## 7. 代码组织与复现

| 层 | 文件 | 职责 |
|---|---|---|
| 冻结原生实现 | [external_mira/](../src/samtok_benchmark/external_mira/) | 数据、公开输入、五种 adapter、worker、原生评分；14 个被执行身份引用的源文件不变 |
| 配置 | [mira_r2_1000.json](../configs/external/mira_r2_1000.json) | 固定 R2 checkpoint 和参考参数，实际完整配置由原 v4 配置仅替换 adapter 得到 |
| 前台协调 | [run_mira_r2_full.py](../scripts/run_mira_r2_full.py) | 原生 Pass1/S2、固定十图批次评分、断点身份校验、资源不足退避重试、汇总 |
| 评分恢复 | [supervise_mira_r2_full.py](../scripts/supervise_mira_r2_full.py) | 等待原协调器结束后，仅补缺失完整评分；不重采样生成 |
| CPU 统计 | [report_mira_r2.py](../scripts/report_mira_r2.py) | 读取原始 JSONL 和绑定，复算六行对比，核对已发表的报告 |
| CPU 核验 | [audit_mira_r2.py](../scripts/audit_mira_r2.py) | 权重 SHA、源码、逐图推理、Pass1、可选 30 张 pilot 一致性 |
| 回归测试 | [test_mira_r2.py](../tests/test_mira_r2.py) | 配对/聚合、固定分片、失败重试边界、原始记录保留、文档安全追加 |

### 只读复算：不启动 GPU 或 API

从本仓库根目录运行；需要 NumPy 和 Pillow。`--output` 使用新的临时目录，脚本拒绝覆盖已有内容或写入正式结果根。

```bash
MIRA_CPU=/tmp/ifbench/external_pilots_20261107/env_metrics/bin/python
MIRA_CHECK=/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/mira_r2_check_new
"$MIRA_CPU" -B scripts/report_mira_r2.py --verify-images --output "$MIRA_CHECK/tables"
"$MIRA_CPU" -B scripts/audit_mira_r2.py --output "$MIRA_CHECK/inference" \
  --pilot-root /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/quality_anchor_20261104/mira_eval/tok_r2_1000 \
  --pilot-subset /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/quality_anchor_20261104/mira_eval/sub30/SUBSET30.json
```

### 新建同配置评测或继续未完成运行

下面命令是复现入口，不是本次整理中再次执行的实验。使用空闲的本机 GPU 4–7，检查每张已有占用不超过 2.3 GB、可用不少于 70,000 MiB，并获取协作锁；不会使用其他卡或结束其他任务。源码和全部依赖需要与冻结配置匹配。

```bash
MIRA_PY=/tmp/ifbench/fairness-dev20-runtime-20261030/generation/env/bin/python
MIRA_NEW=/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira/r2_reproduction_new
MIRA_SCRATCH=/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/mira_r2_reproduction_new
export MIRA_API_KEY_FILE=/path/to/private/gpt54.key
"$MIRA_PY" -B scripts/run_mira_r2_full.py --root "$MIRA_NEW" --scratch "$MIRA_SCRATCH" --prepare-only
"$MIRA_PY" -B -u scripts/run_mira_r2_full.py --root "$MIRA_NEW" --scratch "$MIRA_SCRATCH"
```

保留同一 `--root/--scratch` 可继续相同运行；仅身份一致的完整结果可跳过，未知 admission 和生成失败不会自动重采样。429、网络和服务端临时故障按 30/60/120/240/300 秒退避继续，已提交完整的图像评分不重判，错误请求及响应保留。鉴权、数据、解析及其他非暂时性错误停下供检查。

若生成已全部完成、主进程退出而仍有缺分，使用 `scripts/supervise_mira_r2_full.py --root "$MIRA_NEW" --scratch "$MIRA_SCRATCH"`，最多两条 API lane。`--report-only` 只汇总已有完整分数。两入口看到完成状态即退出；对完成实验的核验应使用前面的 CPU 入口。`RESULTS_V5.md` 不再作为默认写入副作用；需要时显式传 `--append-results <file>`，相同 §16.6 幂等，不同内容拒绝覆盖。

当前 CPU 统计入口已在全部正式记录上复算通过：原五行、R2/v4 四项区间和六行配对结果一致；推理核验通过 200 张，pilot 输出一致 30/30。开发检查命令见 [运行手册](MIRA.md#5-cpu-分析与验证)。

本次整理的[检查记录](/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/mira_r2_full_20261110/repo_review_20261110T205738Z/DELIVERY_CHECKS.json) 保存于运行根之外：38 项 CPU 测试、Ruff、22 份文档链接及图像检查通过；64 个纳入前后哈希检查的正式文件和 14 个冻结源码文件未变化。整理过程中没有生成图像或调用 Judge。
