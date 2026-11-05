# MagicBrush 运行手册

协议见 [MAGICBRUSH_EVALUATION.md](MAGICBRUSH_EVALUATION.md)，实际状态见 [MAGICBRUSH_PROGRESS.md](MAGICBRUSH_PROGRESS.md)。本模块不调用任何收费接口，不使用四机集群，不修改其他实验。所有读取数据的 Python 均使用 `-I`；入口只显式添加本仓库与已冻结方法源码。

## 1. 数据、输入与重合审计

以下为已固定路径。原始文件来自官方 `osunlp/MagicBrush` 指定 revision，下载校验后才解码；不运行数据包里的 Python。`SOURCE.json` 保留原 URL、版本、许可与哈希。

```bash
cd /opt/tiger/tanyue/if-bench-magicbrush
MB_PY=/tmp/ifbench/external_bench_20261102/env_v4/bin/python
MB_DATA=/mnt/bn/strategy-mllm-train/user/tanyue/datasets/MagicBrush
MB_PACKAGE=/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/magicbrush_20261105
export CUDA_VISIBLE_DEVICES=''
"$MB_PY" -I scripts/magicbrush.py download --dataset "$MB_DATA"
"$MB_PY" -I scripts/magicbrush.py extract --dataset "$MB_DATA"
"$MB_PY" -I scripts/magicbrush.py prepare --dataset "$MB_DATA" --output "$MB_PACKAGE/bundle"
"$MB_PY" -I scripts/magicbrush.py audit --dataset "$MB_DATA" \
  --training-root /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/refedit_overlap_audit_20261104 \
  --output "$MB_PACKAGE/overlap"
"$MB_PY" -I scripts/magicbrush.py download-metrics --config configs/external/magicbrush.json
```

公共请求为 `bundle/public/<mask-free|mask-provided>/<session>-<turn>/public.json`；图片和 `geometry.json` 同目录。`bundle/private/evaluation.json` 含 GT 与 caption，仅 scorer 可读。`index.json` 固定公共文件和私有评分清单的哈希，但生成 worker 不打开私有清单。多轮模型输入在各自结果的 `public_recurrent/<model>/…` 构造，并绑定本方法前一轮 `output.png` 与记录 SHA。

## 2. CPU 检查与本机冒烟

```bash
CUDA_VISIBLE_DEVICES='' "$MB_PY" -I -m pytest tests/test_external_magicbrush.py -q
```

本机仅允许 **GPU 4–7，2026-11-05 19:00 UTC 后，既有显存不超过约 2.3 GiB 且空闲至少 70,000 MiB**。实际要求是只剩原有约 1.6 GB 的共享进程；应先人工核对 `nvidia-smi`。代码在 launcher 和 worker 两层拒绝其他卡、提前运行或占用超标。绝不结束别人的进程。端口预留 42000–42007，正常原生单卡 worker 不需要分布式服务。

```bash
nvidia-smi --query-gpu=index,name,memory.used,memory.total,uuid --format=csv,noheader
"$MB_PY" -I scripts/magicbrush.py run --bundle "$MB_PACKAGE/bundle" \
  --config /tmp/claude_magicbrush_20261105/local_config.json --output "$MB_PACKAGE/smoke_001" \
  --gpus 4,5,6,7 --attempt smoke001 --smoke --cache-dir /tmp/claude_magicbrush_20261105/cache
CUDA_VISIBLE_DEVICES='' "$MB_PY" -I scripts/magicbrush.py score \
  --output "$MB_PACKAGE/smoke_001" --config /tmp/claude_magicbrush_20261105/local_config.json \
  --cache /tmp/claude_magicbrush_20261105/metric_cache --device cpu
CUDA_VISIBLE_DEVICES='' "$MB_PY" -I scripts/magicbrush.py estimate \
  --output "$MB_PACKAGE/smoke_001" --destination "$MB_PACKAGE/ESTIMATE.json"
```

本机 `local_config.json` 仅将已核验的原生源码与 Python 环境路径换成本机暂存路径；模型配置完全一致，启动时再次校验。

输入由固定 seed/hash 选择，每方法恰好三条：会话 A 首轮无 mask、会话 B 首轮有 mask、会话 A 第 2 轮连续无 mask。连续第 2 轮使用各方法自己的首轮输出。选样不根据得分；不在测试集调 LoRA、提示词或 checkpoint。加载时间独立记录，GPU 峰值明确区分 PyTorch allocated/reserved。估计表使用本次实测逐阶段耗时；冷加载、I/O、评分另计，不能把估计写成正式实测。

## 3. 单机 8 卡 ARNOLD 正式入口

正式运行必须先有八方法成功冒烟与 `ESTIMATE.json`。本机估计超过 8 h 时，launcher 拒绝正式执行。用户提交 **一个 worker、8×H100 80GB、同 NAS** 的作业；入口始终留在前台，先恢复受校验的 RefEdit 环境归档，再生成、免费标准评分、汇总。

正式入口将在烟测通过、提交推送并发布 `READY.json` 后，把精确 commit、READY SHA、启动命令写入进度文档与 NAS handoff。**尚未发布 READY 时不要启动正式入口。** 发布工具只允许干净的 `eval-magicbrush` 工作区，核验所有输入／GT／评分模型文件都在 NAS 且哈希一致。

```bash
# 发布完成后，使用 handoff 中固定的完整 commit：
export MAGICBRUSH_ATTEMPT=run001
export MAGICBRUSH_COMMIT=<handoff中的40位commit>
bash /path/to/published/magicbrush_bootstrap.sh
```

结果根固定为 `experiments2/SAMTokEdit/external_magicbrush/run_001/`。每次恢复只改 attempt，例如 `run002`，不改结果根、配置或生成代码。入口先验证 READY，运行完才退出。已有完成请求按身份验证复用；新 attempt 不是重采样授权。纯编辑方法在一个 worker 中按轮次保留后端；含 planner/Pass1 的方法按依赖波次运行，所有跨模型任务按 GPU 队列分配。各进程在临时 cache 根下使用独立工作目录，避免 MICE 原生调试图片相互覆盖，也不把这些调试文件写入正式结果。

## 4. 记录、恢复与评分

- `RUN.json`、`CONFIG.json`、`source_snapshot/`：冻结协议、源码与请求范围；同目录不能混入变更后的方案。
- `runs/<model>/<tokens|plan|edit>/<track>/<independent|iterative>/<case>/`：`ADMITTED.json`、原生调用／计划、`result.json`；编辑阶段额外保存 `raw.png`、`output.png`。终态与输出不覆盖。
- `attempts/<id>/`：各阶段日志、自己的 PID、历史和退出记录。`SIGUSR1` 发给该 attempt 的 launcher，可在当前请求完成后停止；不要对整个机器 `pkill`。
- 已受理但无终态：明确列为未知，不自动重采样。先确认进程已退出，查明基础设施原因，再人工隔离该 key 并保留原因；不得覆盖证据。模型自身失败不按基础设施失败重新抽样。
- `scores/<model>/<track>/<mode>/<case>/score.json`：五指标、输出／GT／caption／评分权重与代码的绑定。评分失败保留失败记录，缺分不填零。
- `report/REPORT.{json,md}`：全量与统一去重合子集；完整行列均值、95% 会话 bootstrap 区间和逐图记录；不完整行明确计分覆盖。

所有机器共用同一份 NAS 输入；连续轮次的标记字体也从 NAS 加载固定字节，不依赖新容器的字体版本。单轮评价全部独立轮次；多轮只取每会话最终连续图，单轮会话复用首轮。第一轮不生成两次。五项分数不需要 Judge/GPT。报告末端以 16 线程验证独立输出哈希，避免串行读取大量 NAS 图像；评分逐请求保存，不每批扫描全目录。

## 5. 报告与对比拼图

```bash
CUDA_VISIBLE_DEVICES='' "$MB_PY" -I scripts/magicbrush.py report \
  --output <运行结果目录> --overlap "$MB_PACKAGE/overlap/OVERLAP.json" --destination <报告目录>
CUDA_VISIBLE_DEVICES='' "$MB_PY" -I scripts/magicbrush.py preview \
  --output <运行结果目录> --destination /opt/tiger/tanyue/visualization_tmp/MagicBrush_20261105
```

拼图直接使用真实图像，附 SHA 来源。连续编辑输入是方法各自上一轮输出，因此分别显示。默认使用预先选定的两个会话，避免按最终成绩挑选；GT 标注为仅评分／展示。正式远程作业先写 NAS 的 `report/previews/`，再复制到用户指定的本地可视化目录。
