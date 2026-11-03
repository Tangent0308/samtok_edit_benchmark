# MIRA 外部泛化评测

本分支从 `v2branch@d04c1a7` 增加独立的 `samtok_benchmark.external_mira` 模块，比较 SITEdit、Qwen-Image-2.1、Qwen-Image-Edit-2511、RePlan 和 MIRAGE。完整 200 图 × 五方法评测已于 **2026-11-03 05:24 UTC** 结束：999 张有效输出全部完成 GPT-5.4 评分，RePlan 的 154 号请求生成失败。实际成绩、覆盖率和训练重合子集见 [MIRA_RESULTS.md](MIRA_RESULTS.md)；运行与审计见 [MIRA_FULL_RUN.md](MIRA_FULL_RUN.md)，早期小样本证据见 [MIRA_SMOKE.md](MIRA_SMOKE.md)。下文保留各阶段独立命令，不用于覆盖已结束的正式实验。

## 1. 固定的数据与方法

- 数据：[MIRAGE 官方数据仓库](https://huggingface.co/datasets/ziqiangoodgood/MIRAGE/tree/fce5795af4276c5d312d3d68c13879c8d9735f55/benchmark)，revision `fce5795af4276c5d312d3d68c13879c8d9735f55`。当前版本含 **200 张源图、每图 5 个编辑项，共 1,000 项**。不要与旧的 100 图版本混用。
- 下载器验证上游 Git blob / LFS 内容标识，落盘 SHA-256 记录于 `DOWNLOAD.json`。`prepare` 再核验文件并生成共享公开输入和独立评分标注。
- SITEdit：[方法仓库](https://github.com/Tangent0308/samtok_edit/tree/aa5a414e36c01eba60b37fc46cb9e32f803f8a93)，commit `aa5a414e36c01eba60b37fc46cb9e32f803f8a93`。Pass1 使用 `pass1_localization_lora_formal_20261030_0939/runs/formal/step_2000`；S2 使用 `qwen21_v3/runs/s2_4n_001/train/adapter_16000`。
- 官方评分代码：[MIRAGE metrics](https://github.com/ZiqianLiu666/MIRAGE/tree/ff01782a27018ce59f01760e62fe0bcdf518c586/metrics)，commit `ff01782a27018ce59f01760e62fe0bcdf518c586`。保留其评分提示、区域构造、分数换算与汇总规则，只通过官方 `request_fn` 接入用户指定的 GPT-5.4。
- 原生 MIRAGE **生成代码**固定为 `234a31968df307879a55675873a54258d6c0eae4`，与当前采用的评分代码版本分别记录。其余原生代码与权重 revision 见 [mira.json](../configs/external/mira.json)。未重新训练或按 MIRA 分数调参。

| 方法 ID | 实际流程 | 固定生成设置 |
|---|---|---|
| `qwen2511` | 原图 + 完整原始复合指令 → Qwen-Image-Edit-2511 | 40 steps，CFG 4，seed 42 |
| `qwen21` | 原图 + 完整原始复合指令 → Qwen-Image-2.1 | 40 steps，CFG 1，KV cache，原生 CPU offload，seed 42 |
| `replan` | 原生 RePlan-Qwen2.5-VL-7B 规划 → Qwen2511 区域编辑 | 40 steps，CFG 4，原生 planner 上限 2,048 tokens，seed 42 |
| `mirage` | 原生 Qwen3.5-9B parser / locator → 局部与全局联合去噪 | 40 steps，CFG 4，patch ratio 0.4，padding 10，seed 42 |
| `sitedit` | Pass1 从公开文本预测 5 个区域码 → S2 一次联合编辑 | 40 steps，token guidance 2，Pass1 上限 512 tokens，seed 42 |

RePlan / MIRAGE 的规划成本和原生多分支计算属于方法本身。比较成本时应包含规划、模型加载和编辑；`inference_seconds` 只对应当前阶段，不能直接当成完整请求延时。SITEdit 的掩码解码仅为诊断，另有计时，不输入生成器。

## 2. 输入与公平性

所有模型只接收公开源图和文本。统一使用已有 IF-Bench 的约 1MP 画布：32 像素网格、居中灰色 padding、0.995 backoff，沿用冻结的 `canvas.py`。不改变原生步骤、引导强度或算法；RePlan / MIRAGE 保留自己的原生输出网格。保存 `raw.png`，用记录的几何变换去除 padding、恢复到原图尺寸后保存 `output.png`，在原图坐标下评分。

原始复合指令通过固定标点语法拆为 5 个公开子句，保留字符位置。拆分仅读取文本；计数和顺序不从 GT mask 推断。SITEdit 将各子句绑定到区域码，沿用方法仓库的 `place_token` 与 `multi_edit_prompt`。无有效区域码时保留该项原文，并记录 `fallback_units`。MIRAGE 接收完整复合指令，由它自己的 parser 决定拆分；RePlan 同样使用自己的原生规划。

GT 多边形、canonical 图像元数据和评分用子句映射保存在 `private/evaluation.json`，模型适配器不读取它。各模型评分统一使用官方标注顺序与同一套 5 项文本，避免把某个方法自己的解析结果当成该方法的评测标准。Free-space addition 等 MIRA 原生任务全部保留，不按 SITEdit 是否容易处理过滤；MIRA 的五个编辑项也不自动等价于 IF-Bench 的五个独立目标。

本实验衡量“公开文本驱动的多项联合编辑泛化”，不能替代本论文交互输入、细粒度目标绑定或按 K 分组的主实验。声明范围内的训练与开发图像重合审计已完成：646,908 个路径均成功读取，确认源图 138、175 与实际 S2 训练记录重合。正式结果同时保留官方 200 图和五方法共用的排除已确认重合后的 198 图子集；该审计不涵盖基础模型预训练和任意图像变换。

## 3. 文件与环境

| 内容 | 路径 |
|---|---|
| 当前代码 | `/opt/tiger/tanyue/if-bench-mira`，branch `eval-mira` |
| 原始数据 | `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/MIRA-Bench` |
| 正式结果根目录 | `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira` |
| 当前共享输入、依赖与 smoke | `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102` |
| 本机临时环境 | `/tmp/ifbench/external_bench_20261102` |
| 展示拼图 | `/opt/tiger/tanyue/visualization_tmp/MIRA_smoke_20261102` |

三个独立环境避免 Pass1 与 v4 的 Transformers 版本冲突。基线生成 / Judge 使用已有 generation 环境（Torch 2.8、Transformers 5.19）；Pass1 使用方法仓库锁定的 Transformers 5.19；S2 使用该仓库锁定的 Transformers 5.12.1。配置里包含实际路径。

当前节点已经可用，可执行纯 CPU 检查：

```bash
cd /opt/tiger/tanyue/if-bench-mira
/tmp/ifbench/external_bench_20261102/env_v4/bin/python scripts/setup_mira_runtime.py --check-only
```

新节点可在这个代码目录运行 `python3 scripts/setup_mira_runtime.py`，从 NAS 上已验证的基线运行环境归档恢复 generation 环境，并按方法仓库锁文件安装另两个环境。脚本需要 Python 3.11、`uv`、共享 NAS 和包源访问，**不会启动推理**。依赖源码及权重已在配置中的 NAS 路径；若这些共享路径不可用，应先恢复它们。不得用另一套权重或代码静默替代。

基线环境归档 SHA-256 为 `a9defaaec05b3b54fda510f7b6d8978e1633ddb51354be8049235f7770bf636a`。本次安装后的三环境检查已通过；新节点自动恢复分支尚未在第二台机器实测。

## 4. 下载与准备

下面命令从仓库根目录运行。指定分支中路径后不依赖旧 IF-Bench `start.sh`。

```bash
export PYTHONPATH="$PWD/src"
MIRA_PY=/tmp/ifbench/fairness-dev20-runtime-20261030/generation/env/bin/python
MIRA_TMP=/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102
MIRA_DATA=/mnt/bn/strategy-mllm-train/user/tanyue/datasets/MIRA-Bench

"$MIRA_PY" -m samtok_benchmark.external_mira download --dataset "$MIRA_DATA"
"$MIRA_PY" -m samtok_benchmark.external_mira prepare \
  --dataset "$MIRA_DATA" --bundle "$MIRA_TMP/mira_bundle"
```

当前完整下载和 200 请求准备已完成。已有文件仅在内容一致时复用，不覆盖不同内容。正式运行前保留该 NAS bundle 和依赖目录，不因名字带 `tmp` 删除它们。

## 5. 运行

新的 smoke 使用新的输出目录；已有 smoke 目录是证据。一次限定 1–3 个明确 case ID，禁止写入正式结果根目录。下面会运行五个方法，独立模型按 GPU 分配，规划与编辑阶段顺序执行：

```bash
"$MIRA_PY" -u -m samtok_benchmark.external_mira run \
  --bundle "$MIRA_TMP/mira_bundle" --config configs/external/mira.json \
  --output "$MIRA_TMP/mira_smoke_new" --gpus 0,1,2,3,4 --cases 003 --smoke
```

可用 `--models qwen21 sitedit` 选方法，或 `--gpus 0` 顺序运行。早期 smoke 实际使用 `001` 与 `002`；上面的独立 `003` smoke 命令未执行。随后正式实验覆盖了全部 200 图。

正式评测的独立生成命令如下。本次生成已由自动流水线完成；默认包含全部 200 源图、五个方法和每项一次生成，不带 `--smoke` 或 `--cases`。已结束的正式目录保留原始终态：

```bash
MIRA_FORMAL=/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira
"$MIRA_PY" -u -m samtok_benchmark.external_mira run \
  --bundle "$MIRA_TMP/mira_bundle" --config configs/external/mira.json \
  --output "$MIRA_FORMAL/run_001" --gpus 0,1,2,3,4
```

正式运行前应确认资源空闲。当前 launcher 是单节点前台入口；没有实现跨节点调度。模型一次加载后处理该阶段的全部源图，规划与编辑分阶段释放显存。

`RUN.json`、`CONFIG.json` 与 `source_snapshot/` 固定本次配置和调用代码；每项写入 `ADMITTED.json`、终态 `result.json`、实际输出 SHA 和耗时。相同代码 / 配置 / 输入下重复同一命令可复用完成结果；输入或输出被改动会拒绝。已 admission 而无终态的请求必须检查原因，不能自动重采样；失败终态同样保留。正常单项规划失败不阻止其余成功规划进入编辑；致命 CUDA / 模型加载错误停止该方法后续阶段。

生成状态：

```bash
"$MIRA_PY" -m samtok_benchmark.external_mira report --output "$MIRA_FORMAL/run_001"
```

## 6. GPT-5.4 评分

默认配置为 [mira_judge_gpt54.json](../configs/external/mira_judge_gpt54.json)，PF / Cons / PQ 全部使用 **`gpt-5.4-2026-03-05`**。统一 Judge 重评全部方法，因此不能与论文中使用其他 Judge 的分数直接拼表。`mira.json` 只管理生成，修改 Judge 不改变生成配置。

密钥从 `MIRA_API_KEY_FILE` 指向的本地受限文件读取，也支持 `OPENAI_API_KEY` 环境变量。文件不要纳入 Git。默认使用用户提供的服务器 endpoint；办公网络按用户要求设置：

```bash
export MIRA_API_KEY_FILE=/path/to/private/gpt54.key
# 仅在办公网络需要时设置：
export MIRA_AZURE_ENDPOINT=https://aidp-i18ntt-sg.tiktok-row.net/api/modelhub/online/v2/crawl
```

独立评分入口如下。本次实际由自动流水线逐方法调用同一评分模块完成，见 `ATTEMPTS.json`；不要把此命令当成重新评分或覆盖现有结果的步骤：

```bash
"$MIRA_PY" -u -m samtok_benchmark.external_mira score \
  --bundle "$MIRA_TMP/mira_bundle" --config "$MIRA_FORMAL/run_001/CONFIG.json" \
  --judge-config configs/external/mira_judge_gpt54.json \
  --run "$MIRA_FORMAL/run_001" --output "$MIRA_FORMAL/scores_gpt54_001"
```

加 `--export-only` 只核验并导出评分输入；它不调用 API。`score` 默认包含五个方法；若生成时只运行部分方法，需传相同的 `--models`。每张图通常有两次请求：一批 5 项的 PF / Cons，以及整图 PQ。保留 `JOB.json`、`JUDGE.json`、输入哈希、请求 logid 和真实返回。已完成的整图分数可断点复用；单图内未提交完整记录的 API 失败可能在再次执行评分时重发，保留前次请求记录。SDK 自动重试关闭。

输出 `SCORES.json` 报告 `total`、`valid_outputs`、`scored`、PF、Cons、PQ 和 Overall。官方 0–25 Judge 输出除以 2.5，报告 0–10 分；先求全体图像 PF / Cons / PQ 的均值，再算：

```text
Overall = sqrt(min(mean(PF), mean(Cons)) * mean(PQ))
```

生成失败、评分失败和未知状态不能删除；Judge 缺失是 missing，不设为 0。存在缺失时展示覆盖率与已评分分母，不能当成完整 200 图成绩。冻结的原始汇总器仅在所有方法全覆盖时生成区间，因此本次原始 `SCORES.json` 没有区间。独立的 `scripts/report_mira_audited.py` 保留原始聚合不变，为完整覆盖的方法计算源图 bootstrap 区间，并把 RePlan 的共同可评分比较明确标为条件诊断，详见 [MIRA_RESULTS.md](MIRA_RESULTS.md)。两套子集均为 10,000 次相同索引的配对 bootstrap；早期两个独立单图 smoke 不生成总体 CI。

## 7. CPU 验证

```bash
PYTHONPATH="$PWD/src:$MIRA_TMP/deps/sitedit-aa5a414/src" \
  /tmp/ifbench/external_bench_20261102/env_v4/bin/python \
  -m pytest -q tests/test_external_mira.py
uv tool run ruff check src/samtok_benchmark/external_mira \
  tests/test_external_mira.py scripts/setup_mira_runtime.py
```

回归覆盖公开文本拆分、禁止 GT 字段混入、SITEdit 逐项绑定和文本回退、原生模型参数、输入与评分哈希、失败状态及 Overall 汇总公式。没有修改 IF-Bench 冻结的 canvas / public / Judge 文件。
