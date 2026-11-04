# RefEdit-Bench 运行手册

本页只写命令和路径。协议、偏差与计划见 [REFEDIT_EVALUATION.md](REFEDIT_EVALUATION.md)，实际执行与结果见 [REFEDIT_PROGRESS.md](REFEDIT_PROGRESS.md)。

## 1. 路径

| 内容 | 路径 |
|---|---|
| 代码 | `/opt/tiger/tanyue/if-bench-refedit`，branch `eval-refedit` |
| 数据 | `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/RefEdit-Bench`（`SOURCE.json`、`raw/`、`extracted/`） |
| 正式 bundle | `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_refedit/bundle` |
| 正式生成 | `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_refedit/run_001` |
| ARNOLD 入口日志 | `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_refedit/arnold/<run id>/` |
| smoke/调试 | `/tmp/claude_refedit_20261104/` |
| 展示 | `/opt/tiger/tanyue/visualization_tmp/RefEdit_20261104/` |
| 远端环境归档 | `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/refedit_runtimes/`（`env_v4.tar`、`env_pass1.tar` 及描述符） |
| 训练重合审计 | `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/refedit_overlap_audit_20261104/` |

本机环境沿用 MIRA：基线 `/tmp/ifbench/fairness-dev20-runtime-20261030/generation/env/bin/python`，SITEdit Pass1 `/tmp/ifbench/external_bench_20261102/env_pass1`，S2 `/tmp/ifbench/external_bench_20261102/env_v4`；本地 Judge 的 vLLM 运行时为 `/tmp/ifbench/fairness-dev20-runtime-20261030/judge/python`。

## 2. 数据（gated）

数据集需要已在 HF 接受条款的账号 token。token 放在权限 600 的文件里，脚本只读取、不打印、不保存。下载内容视为不可信，只用 `python -I` 解析，不执行任何随数据发布的代码。

```bash
cd /opt/tiger/tanyue/if-bench-refedit
DATA=/mnt/bn/strategy-mllm-train/user/tanyue/datasets/RefEdit-Bench
PY=/tmp/ifbench/external_bench_20261102/env_v4/bin/python   # 需要 pyarrow
$PY -I scripts/refedit_data.py download --dataset $DATA --token-file /path/to/hf_read_token
$PY -I scripts/refedit_data.py extract --dataset $DATA
$PY -I scripts/refedit_data.py prepare --dataset $DATA \
  --bundle /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_refedit/bundle
```

`download` 固定 revision `71fc847382cf4fd8da03de18b6138d383ad6eb00`，核对文件大小与上游 LFS SHA-256，写 `SOURCE.json`（URL、revision、license 说明、SHA）。`extract` 将 parquet 中的图像按官方行号存为 `extracted/images/000…199`，并写 `annotations.jsonl` 与 `EXTRACT.json`（核对 `category` 与官方“前 100 为 Easy”规则）。`prepare` 生成公共约 1MP 画布与 `public.json`（只有清图和原文指令），评分字段只在 `private/evaluation.json`。

## 3. 本机生成（smoke 或 GPU 足够时）

```bash
cd /opt/tiger/tanyue/if-bench-refedit
export PYTHONPATH="$PWD/src"
GEN=/tmp/ifbench/fairness-dev20-runtime-20261030/generation/env/bin/python
B=/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_refedit/bundle
$GEN -u -m samtok_benchmark.external_refedit run --bundle $B --config configs/external/refedit.json \
  --output /tmp/claude_refedit_20261104/smoke_refedit --gpus 6,7 --cases 000 100 --smoke \
  --attempt smoke1 --cache-dir /tmp/claude_refedit_20261104/cache
$GEN -m samtok_benchmark.external_refedit report --output /tmp/claude_refedit_20261104/smoke_refedit
```

- 不带 `--smoke/--cases` 即为 200 例正式运行，`--output` 应为正式目录 `run_001`。
- launcher 按方法和 case 分片，按估计时长从长到短分配给空闲 GPU；每个 GPU 上一次只跑一个任务。任务开始前检查该卡已用显存不超过 `--max-used-gib`（默认 8 GiB，本机他人作业约 1.6 GiB），否则等待最多 30 分钟。
- 已有终态的请求核对输入、配置、源码身份和输出 SHA 后复用，绝不覆盖；有 admission 无终态的请求记为 `unknown`，不自动重采样。确认是进程被杀等基础设施原因后，用 `release` 手动移走并留痕：

```bash
$GEN -m samtok_benchmark.external_refedit release --output <run dir> --model <m> --stage <s> --case <id> \
  --reason "worker killed by preemption at <time>"
```

## 4. ARNOLD 单机 8 卡入口（正式生成）

入口只做生成，不做任何 Judge 或付费请求。启动命令（ARNOLD：1 个 worker，8 GPU）：

```bash
export REFEDIT_RUN_ID=gen_arnold_001            # 每次尝试一个新 ID；用过的 ID 会被拒绝
export REFEDIT_COMMIT=<eval-refedit 的完整 commit SHA，见进度记录>
curl -fsSL https://raw.githubusercontent.com/Tangent0308/samtok_edit_benchmark/$REFEDIT_COMMIT/scripts/arnold/refedit_bootstrap.sh -o /tmp/refedit_bootstrap.sh
bash /tmp/refedit_bootstrap.sh
```

也可以把 [refedit_bootstrap.sh](../scripts/arnold/refedit_bootstrap.sh) 的全文粘贴为启动命令，并在前面设置这两个变量。入口依次：

1. 检查 `ARNOLD_WORKER_HOSTS`、`ARNOLD_WORKER_NUM=1`、`ARNOLD_WORKER_GPU=8`、`ARNOLD_ID=0`、run ID 格式、bundle 存在和 NAS 可写；用原子 `mkdir arnold/<run id>` 认领 run ID，已用则退出。
2. 将 `eval-refedit` 克隆到 `/tmp/refedit-code-<run id>` 并 checkout 固定 SHA，核对 HEAD。
3. [refedit_worker.sh](../scripts/arnold/refedit_worker.sh) 在 `/tmp/refedit-runtime/v1` 准备：SITEdit 源码（GitHub 克隆并 checkout `aa5a414`，核对干净）、原生方法源码（逐文件对照 [清单](../configs/external/refedit_native_sources.json) 的 SHA）、基线运行时（IF-Bench 全量运行用的归档，核对 SHA、payload 清单与导入）、SITEdit 两个环境（NAS 归档，核对描述符 SHA 和归档 SHA，并证明 `samtok_edit21/diffsynth/samtok` 从核对过的克隆导入）。
4. 生成节点本地配置（模板 [refedit_arnold.template.json](../configs/external/refedit_arnold.template.json)，除路径外与 [refedit.json](../configs/external/refedit.json) 相同；已有文件必须逐字节一致），检查每张卡至少 70 GB 空闲。
5. 前台运行上面的 launcher，输出写入 NAS 正式目录 `run_001`，任务日志在 `run_001/logs/`，入口日志在 `arnold/<run id>/entry.log`，结束写 `DONE.json`（失败另写 `FAILED.json`）。

中断后用新的 run ID 重新提交即可续跑：已完成请求复用，未完成请求照常生成，`unknown` 请求需按上一节手动 `release` 后才会重新生成。端口：入口本身不开端口。

## 5. 评分

### 5.1 导出

```bash
$GEN -m samtok_benchmark.external_refedit score-export --bundle <bundle> --run <run dir> --output <scores dir>
```

按官方 notebook 生成每个 case 的 `source_initial.png`、`edited.png`、`source_masked.jpg`、`edited_masked.jpg`（第一个多边形、15×15 膨胀），并在 `JOB.json` 绑定输出与 result SHA。

### 5.2 本地 Judge（免费，GPU 6–7）

```bash
JPY=/tmp/ifbench/fairness-dev20-runtime-20261030/judge/python
CUDA_VISIBLE_DEVICES=6,7 $JPY -m vllm.entrypoints.openai.api_server \
  --model /mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/Qwen3.8-27B \
  --served-model-name Qwen3.8-27B --tensor-parallel-size 2 --port 39611 --host 127.0.0.1 \
  --max-model-len 16384 --limit-mm-per-prompt '{"image": 2}'
$GEN -m samtok_benchmark.external_refedit judge --job <scores dir>/<method>/JOB.json \
  --judge-config configs/external/refedit_judge_local_qwen38.json --output <scores dir>/<method>
```

### 5.3 GPT-5.4（付费，需要用户批准正式评分）

```bash
export MIRA_API_KEY_FILE=/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/secrets/gpt54.key
$GEN -m samtok_benchmark.external_refedit judge --job <scores dir>/<method>/JOB.json \
  --judge-config configs/external/refedit_judge_gpt54.json --output <scores dir>/<method> \
  --ledger <scores root>/PAID_LEDGER.jsonl --max-paid-requests <cap>
```

每次 API 调用尝试先写入共享 ledger，超过上限即拒绝发送；每个请求、响应和解析结果分别保存。已解析的答案续跑时复用；返回了但不是官方 JSON 的答案记为缺失，不会再次询问（除非显式 `--retry-unparsable`）。

### 5.4 汇总

```bash
$GEN -m samtok_benchmark.external_refedit aggregate --scores <scores dir> --models sitedit qwen21 ...
```

输出 Easy/Hard/All 的 s1、s2、SC、PQ、O（官方逐图 O 的平均）、有效分母和 SITEdit − 各基线的源图配对 bootstrap（10,000 次，seed 20261027）。

## 6. 训练重合审计

```bash
PY=/tmp/ifbench/external_bench_20261102/env_v4/bin/python
A=/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/refedit_overlap_audit_20261104
$PY -I scripts/audit_refedit_overlap.py --stage training --output $A        # 已完成
$PY -I scripts/audit_refedit_overlap.py --stage benchmark --output $A \
  --dataset /mnt/bn/strategy-mllm-train/user/tanyue/datasets/RefEdit-Bench   # 数据到位后
```

## 7. 工程 dry run（非 RefEdit 数据）

数据未到位时，用 MIRA-Bench 图像各取第一项编辑构造同格式 bundle，检验全部适配器、launcher、计时与评分导出。bundle 标记 `dryrun`，launcher/worker 拒绝把它写入正式目录，结果不是 RefEdit-Bench 成绩：

```bash
$PY scripts/refedit_dryrun_bundle.py --output /tmp/claude_refedit_20261104/dryrun_bundle
```

## 8. CPU 检查

```bash
M=/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/deps/sitedit-aa5a414
PYTHONPATH="$PWD/src:$M/src" /tmp/ifbench/external_bench_20261102/env_v4/bin/python -m pytest -q tests/test_external_refedit.py
uv tool run ruff check src/samtok_benchmark/external_refedit scripts/refedit_*.py scripts/audit_refedit_overlap.py tests/test_external_refedit.py
```
