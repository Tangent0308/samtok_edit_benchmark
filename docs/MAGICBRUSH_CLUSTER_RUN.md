# MagicBrush 四机 32 卡运行

用户于 2026-11-06 将部署调整为四机 32 卡，其余评测内容保持不变。[协议](MAGICBRUSH_EVALUATION.md)与[冒烟报告](MAGICBRUSH_RESULTS.md)继续适用。本次只修改调度、协调和启动封装。run001 在下载源码时停滞，用户已停止四台机器；未产生生成或评分记录。

## 提交方式

一个 ARNOLD 作业：**4 workers，每台 8×H100 80GB，四台均挂载 `/mnt/bn/strategy-mllm-train/user/tanyue/`**。四台执行同一条前台命令，attempt 必须相同：

```bash
MAGICBRUSH_ATTEMPT=run002 bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/magicbrush_4node32_nas_20261106/start.sh
```

平台需提供 `ARNOLD_WORKER_NUM=4`、`ARNOLD_WORKER_GPU=8`、不同的 `ARNOLD_ID=0/1/2/3`。入口拒绝错误拓扑、相同物理主机和原共享开发机。每张卡仍须至少 70,000 MiB 空闲；不会结束已有进程。仅通过 NAS 协调，无 `torchrun`、NCCL 或端口监听；子进程端口变量保留在 42000–42007。

可选的 CPU／空闲检查使用独立 attempt；它会恢复环境、读 `nvidia-smi` 和验证文件，但不运行模型：

```bash
MAGICBRUSH_ATTEMPT=validate002 bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/magicbrush_4node32_nas_20261106/start.sh --validate-only
```

预检退出后，正式运行使用新 attempt。每次恢复也只改 attempt；同一结果目录的完成记录继续复用。

## 调度与信息边界

| 项目 | 当前执行方式 |
|---|---|
| 数据 | 原 535 会话、1,053 编辑轮；八方法、两种 mask 轨道和独立／连续评测保持不变 |
| node 0 | 133 会话，每方法 786 个生成请求 |
| node 1 | 133 会话，每方法 786 个生成请求 |
| node 2 | 135 会话，每方法 786 个生成请求 |
| node 3 | 134 会话，每方法 784 个生成请求 |
| 全量 | 每方法 3,142 次联合编辑，共 25,136 次；Pass1／planner 仍按原生流程另计 |
| 分配规则 | 以会话请求数降序、原始索引顺序打破同权重并列，依次交给累计请求数较少的节点；不参考图像、预测或分数 |
| 多轮依赖 | 完整会话固定归属一台机器；始终使用同方法上一轮真实输出 |
| 本机队列 | 八个单卡槽位，按冻结冒烟耗时排列各方法的任务；GPU 之间无模型张量并行 |
| 评分 | 四台生成均完成后开始；全局分片编号 `node_rank*8+card`，共 32 片；原始评分代码不变 |
| 汇总 | 四台评分均结束后，node 0 统一读全部逐图记录；保持同一完整集／排除重合集和会话 bootstrap，不平均节点分数或区间 |

原生单卡 worker 的冻结门禁要求独立单机环境。因此，外层控制器先严格验证真实 4×8 拓扑，再仅对其子进程设置 `ARNOLD_WORKER_NUM=1`、`WORLD_SIZE=1` 等单机运行变量。真实节点身份仍存于 `MAGICBRUSH_CLUSTER_NODE_ID`、`MAGICBRUSH_CLUSTER_WORKERS`、OWNER/TASKS 记录。这是运行时隔离；不修改原生模型调用、生成代码或科学记录身份。

## 包与结果位置

| 内容 | 路径 |
|---|---|
| 当前入口与 READY | `.ifbench-tmp/magicbrush_4node32_nas_20261106/` |
| 原始冻结输入和冒烟 | `.ifbench-tmp/magicbrush_20261105/`，保留科学资产及其原绝对路径；旧启动文件移除 |
| 发布身份与校验记录 | `.ifbench-tmp/magicbrush_4node32_nas_20261106-handoff.md`，在包外 |
| 正式结果 | `experiments2/SAMTokEdit/external_magicbrush/run_001/` |
| 启动日志 | `experiments2/SAMTokEdit/external_magicbrush/arnold/<attempt>/node-<rank>/entry.log` |
| 心跳／阶段／评分日志 | `run_001/cluster/<attempt>/node-<rank>/` |
| 生成阶段日志 | `run_001/nodes/node-<rank>/attempts/<attempt>/` |
| 原图、输出、逐图评分、报告 | 原 `runs/`、`scores/`、`report/` 布局保持不变 |

上述路径均以 `/mnt/bn/strategy-mllm-train/user/tanyue/` 为根。新 READY 保留全部 12,659 个共同科学资产校验项，并将基线校验封存到新包 `BASELINE.json`，不再依赖旧启动文件或旧 READY；19 个生成源文件、评分与统计实现、模型配置、环境 staging 文件均与原发布 commit 相同。benchmark 与 SITEdit aa5a414 源码均使用包内 `sources/*.bundle`，先校验 SHA256，再仅允许 Git 本地文件协议恢复固定提交；环境和原生依赖也从 NAS 恢复到各容器 `/tmp`。启动不再访问 GitHub，也不依赖开发机的本地目录。`bootstrap.phase` 和 `bootstrap_failure.json` 在入口日志同目录记录阶段与失败；控制器启动后沿用原心跳。

## 恢复与故障处理

- **重复启动保护**：node 0 原子创建 NAS 的 `CLUSTER.lock/` 并写入 attempt/token；只有旧 attempt 四个节点均写入 RELEASED，才允许归档旧锁目录并交给新 attempt。每个 rank 的 OWNER 仅创建一次，复用 attempt 会拒绝。NAS 实测不支持 `flock`，因此跨机准入不依赖它；节点生成锁和 staging 锁只位于本地 `/tmp`。
- **心跳**：15 秒写一次；读取遇到文件短暂缺失或 JSON 未完整可见会重试。连续未观测到新序号超过 600 秒才判失联；短暂读取失败保留最近一次成功时间，不回退到 OWNER 创建时间。新节点入场最多等待 60 分钟。
- **正常停止**：分别向四台机器 `cluster/<attempt>/node-<rank>/OWNER.json` 中的本机 PID 发 `SIGUSR1`。控制器让自己启动的生成／评分进程完成当前请求，再退出；不会向其他作业发信号。
- **节点故障**：同伴记录 FAILED 或心跳超时后，其余节点停止发新任务并等待自己当前请求结束。强制平台终止仍可能留下未知 admission；遵循原规则核查和隔离，不自动重采样。
- **续跑**：正常／优雅退出写入 RELEASED 后，用新 attempt 在四台执行相同入口。全部终态的阶段跳过，已有评分验证身份后复用。模型失败、评分缺失仍按原协议保留，不改写结果。

如果平台强制杀死容器、没有 RELEASED，则先在平台确认**四台旧 worker 都已退出**，再手工放行协调锁（不放行未知 admission）：

```bash
/usr/bin/python3 -I /opt/tiger/tanyue/if-bench-magicbrush/scripts/magicbrush_cluster.py release \
  --package /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/magicbrush_4node32_nas_20261106 \
  --attempt <已停止的旧attempt> --confirm-all-workers-stopped \
  --reason '平台已确认四个旧 worker 均退出；填写实际中断原因'
```

该 CPU 命令也可使用新节点上的同一提交源码。它只新增 `cluster/<旧attempt>/FORCED_RELEASE.json`，保留原锁和所有生成／评分证据；不可在旧 worker 尚存活时执行。未知 admission 仍按原规则单独处理。

## 耗时与验证

八方法冒烟外推总生成量为 **342.77 GPU·h**。32 卡完全均衡下约 **10.71 h**；当前固定会话分配与本地任务队列的模拟最长节点约 **11.36 h**。实际另加环境恢复、冷加载、NAS I/O、标准指标和报告；这些数字不是正式实测或完成时间承诺。

本次验证使用 CPU：四进程阶段屏障、同伴失败、剩余节点锁保护、并发心跳覆盖／暂时不可读、优雅停止、完整会话依赖、32 个评分分片无重漏、共享 RUN 与源码快照复用。增加离线 Git bundle 恢复测试，覆盖命名分支、detached HEAD、网络协议禁用和错误 commit 拒绝。原八方法真实 GPU 冒烟结果继续适用，不为调度变更重新采样。发布工具从已推送的干净 `eval-magicbrush` 提交构造新包，并核验全部 NAS 资产。

## 文件清理

当前仓库只保留 `magicbrush_cluster.py`、`magicbrush_publish.py`、`magicbrush_cluster_bootstrap.sh`、`magicbrush_stage.sh` 这一套正式入口及本文档。单机／双机专用入口、旧 READY、启动包与交接文档已退出使用并清理；具体清单写在新包外的交接记录。共享输入、冒烟输出、重合审计和原生环境归档继续用于当前评测，未删除。Git 历史仍可追溯代码改动。

## run001 启动故障与修复

2026-11-06 03:08 UTC 四台启动，node 0 的 GitHub clone 长时间未完成，checkout 没有 HEAD。证据为 `.ifbench-tmp/magicbrush_monitor_20261106/diagnostic-node-0-1793936143.json`。用户确认四台均停止；正式结果根为空，尚未建立协调锁或 admission，因此直接使用新包和 `run002`，不需要放行未知请求。旧四机包和 run001 日志保留。新包仅替换源码传输方式并增加启动诊断，不变更评测输入、原生模型调用、权重、配置或评分。
