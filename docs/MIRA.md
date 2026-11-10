# MIRA 运行手册

本页负责环境、命令与复现操作。**当前 R2@1000 全量结果、权重配置、专用运行及恢复命令见 [MIRA_R2.md](MIRA_R2.md)**；公共协议、五种方法的原生流程及 Judge 见 [MIRA_EVALUATION.md](MIRA_EVALUATION.md)。实际启动与协议核验见 [MIRA_FULL_RUN.md](MIRA_FULL_RUN.md)，早期两例记录见 [MIRA_SMOKE.md](MIRA_SMOKE.md)，独立失败恢复见 [MIRA_REPLAN_FAILURE.md](MIRA_REPLAN_FAILURE.md)。

原五行 200 图评测已完成：999 张输出全部评分，RePlan 154 生成失败。**11-10 新增 R2@1000 的 200/200 张已完成**，单独保存在 `external_mira/r2_20261110`。下面第 1–4 节的 `mira.json` 命令对应原五行（SITEdit v4）；R2 使用专用 [profile](../configs/external/mira_r2_1000.json) 和 [前台协调器](../scripts/run_mira_r2_full.py)，不要把默认 v4 配置当成 R2。

## 1. 环境与固定路径

| 内容 | 路径 |
|---|---|
| 当前代码 | `/opt/tiger/tanyue/if-bench-mira`，branch `eval-mira` |
| 数据 | `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/MIRA-Bench` |
| 已完成正式结果 | `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira` |
| 共享输入、依赖与临时证据 | `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102` |
| 本机临时环境 | `/tmp/ifbench/external_bench_20261102` |
| 当前诊断展示 | `/opt/tiger/tanyue/visualization_tmp/MIRA_branch_review_20261103` |

生成配置为 [mira.json](../configs/external/mira.json)，Judge 配置为 [mira_judge_gpt54.json](../configs/external/mira_judge_gpt54.json)。三套环境分离基线/Judge、SITEdit Pass1 和 S2，避免 Transformers 版本冲突。源码、权重、环境路径与 revision 均在配置内。

```bash
cd /opt/tiger/tanyue/if-bench-mira
/tmp/ifbench/external_bench_20261102/env_v4/bin/python scripts/setup_mira_runtime.py --check-only
```

新节点可运行 `python3 scripts/setup_mira_runtime.py`，从 NAS 上验证的归档恢复基线环境，并按方法仓库锁文件安装 Pass1/S2 环境。需要 Python 3.11、`uv`、共享 NAS 和包源访问；脚本不会启动推理。共享源码或权重不可用时应先恢复原件，不静默替换版本。

基线环境归档 SHA-256 为 `a9defaaec05b3b54fda510f7b6d8978e1633ddb51354be8049235f7770bf636a`。本节点三环境检查已通过；新节点自动恢复分支尚未在第二台机器实测。

## 2. 下载与准备

以下从仓库根目录运行，不依赖旧 IF-Bench `start.sh`：

```bash
export PYTHONPATH="$PWD/src"
MIRA_PY=/tmp/ifbench/fairness-dev20-runtime-20261030/generation/env/bin/python
MIRA_TMP=/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102
MIRA_DATA=/mnt/bn/strategy-mllm-train/user/tanyue/datasets/MIRA-Bench

"$MIRA_PY" -m samtok_benchmark.external_mira download --dataset "$MIRA_DATA"
"$MIRA_PY" -m samtok_benchmark.external_mira prepare \
  --dataset "$MIRA_DATA" --bundle "$MIRA_TMP/mira_bundle"
```

当前完整下载和 200 请求准备已完成。下载/准备均核验内容身份，已有文件仅在一致时复用。bundle 内 `public/` 为模型输入，`private/` 为评分材料；模型适配器不读取后者。共享临时目录含复现必需输入及依赖，不因名字带 tmp 删除。

## 3. 生成入口

单节点前台运行，独立方法按 GPU 分配，各方法自己的规划/编辑阶段顺序执行；每阶段加载一次模型。新 smoke 限定 1–3 个 case，使用新临时目录：

```bash
"$MIRA_PY" -u -m samtok_benchmark.external_mira run \
  --bundle "$MIRA_TMP/mira_bundle" --config configs/external/mira.json \
  --output "$MIRA_TMP/mira_smoke_new" --gpus 0,1,2,3,4 --cases 003 --smoke
```

可加 `--models qwen21 sitedit` 选方法，或 `--gpus 0` 顺序运行。实际早期 smoke 为 001/002；以上 003 命令是新运行示例，未执行。步骤数和其他生成设置仍来自固定配置。

独立的完整生成入口如下；新实验设立新的正式根目录。当前成绩来自已结束的 `external_mira/run_001`，其实际启动命令和监督流程另见 [MIRA_FULL_RUN.md](MIRA_FULL_RUN.md)。

```bash
MIRA_NEW=/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira_new
"$MIRA_PY" -u -m samtok_benchmark.external_mira run \
  --bundle "$MIRA_TMP/mira_bundle" --config configs/external/mira.json \
  --output "$MIRA_NEW/run_001" --gpus 0,1,2,3,4
```

默认全部 200 图、五方法，不带 `--smoke` 或 `--cases`。运行前确认资源空闲；没有跨节点调度。需要生成结束后自动逐方法评分、最多三个并发 Judge 和网络恢复时，使用 [run_mira_full.py](../scripts/run_mira_full.py)，配置与实际用法见正式运行文档。

`RUN.json`、`CONFIG.json` 和 `source_snapshot/` 固定调用身份，每请求先写 `ADMITTED.json`，再保存终态 `result.json`、raw/恢复图及 SHA。只有源码、配置、输入和输出身份均一致才可复用完成结果。已 admission 无终态的请求不能自动重采样，失败终态保留。普通单项规划失败不阻止其他成功计划；致命 CUDA/加载错误停止该方法后续阶段。

只查看现有生成状态：

```bash
"$MIRA_PY" -m samtok_benchmark.external_mira report \
  --output /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira/run_001
```

## 4. GPT-5.4 评分入口

PF、Cons、PQ 均为 `gpt-5.4-2026-03-05`，沿用固定官方评分代码。提示、图像掩码、聚合、重试语义和 Cons/PQ 的解释边界详见 [完整评测文档](MIRA_EVALUATION.md)。`mira.json` 只管理生成，改 Judge 不改变生成配置。

凭据从受限文件或 `OPENAI_API_KEY` 读取，不放入 Git。办公网络需要时另设 endpoint：

```bash
export MIRA_API_KEY_FILE=/path/to/private/gpt54.key
# 仅办公网络需要：
export MIRA_AZURE_ENDPOINT=https://aidp-i18ntt-sg.tiktok-row.net/api/modelhub/online/v2/crawl
```

对上面的新生成目录评分：

```bash
"$MIRA_PY" -u -m samtok_benchmark.external_mira score \
  --bundle "$MIRA_TMP/mira_bundle" --config "$MIRA_NEW/run_001/CONFIG.json" \
  --judge-config configs/external/mira_judge_gpt54.json \
  --run "$MIRA_NEW/run_001" --output "$MIRA_NEW/scores_gpt54_001"
```

`--export-only` 仅核验/导出评分输入，不调用 API；生成只有部分方法时，评分传相同 `--models`。完整逐图评分可断点复用；未提交完整记录的图像可能重发部分请求。原始请求/响应与失败均保留，不按得分选优。自动流水线的有限网络恢复见 `ATTEMPTS.json`。

失败及缺失不填零；`SCORES.json` 显式记录请求、有效输出、已评分分母。官方 Overall 从总体 PF/Cons/PQ 均值计算。冻结的原始汇总器仅在所有方法全覆盖时产生 CI；[report_mira_audited.py](../scripts/report_mira_audited.py) 按已完成重合审计的子集，另报告完整覆盖方法的区间与 RePlan 条件比较。保留所有原始表。

## 5. CPU 分析与验证

当前六行对比由 `scripts/report_mira_r2.py` 直接读取原始逐图分数、验证绑定、复算均值与区间，核对已有完整报告；`scripts/audit_mira_r2.py` 检查 R2 checkpoint、200 张实际调用及可选 30 张 pilot 一致性。两者只写新临时目录，不启动 GPU/API，完整命令见 [R2 复现入口](MIRA_R2.md#7-代码组织与复现)。

原五行的两套总体表由 `scripts/report_mira_audited.py` 复算，输入是已完成的正式 run、评分和重合子集，输出使用新的临时目录：

```bash
python3 scripts/report_mira_audited.py \
  --root /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira \
  --output "$MIRA_TMP/mira_tables_new"
```

分量配对统计、12 例缩略图与三项缓存区域检查的单一入口为 [analyze_mira_results.py](../scripts/analyze_mira_results.py)，固定选例位于 [mira_cases_20261103.json](../configs/analysis/mira_cases_20261103.json)。[完整文档](MIRA_EVALUATION.md) 给出 CPU 复现命令、实际报告路径和来源记录。此入口不加载模型、不调用 Judge，也不重写正式结果。

```bash
PYTHONPATH="$PWD/src:$MIRA_TMP/deps/sitedit-aa5a414/src" \
  python3 -m pytest -q tests/test_external_mira.py tests/test_mira_audited_report.py \
  tests/test_mira_overlap.py tests/test_mira_replan_diagnostic.py tests/test_mira_analysis.py \
  tests/test_mira_r2.py
uv tool run ruff check scripts/run_mira_r2_full.py scripts/supervise_mira_r2_full.py \
  scripts/report_mira_r2.py scripts/audit_mira_r2.py scripts/check_docs.py tests/test_mira_r2.py
python3 scripts/check_docs.py
```

检查覆盖公开信息隔离、原生参数、生成/评分绑定、完整分母聚合、重合证据、独立恢复边界和诊断坐标。IF-Bench 的冻结 canvas/public/Judge 及 MIRA 的正式推理源码保持原样。
