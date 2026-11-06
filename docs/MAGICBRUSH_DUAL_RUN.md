# MagicBrush 双机 16 卡运行

用户于 2026-11-06 将部署调整为双机 16 卡，其余评测内容保持不变。[协议](MAGICBRUSH_EVALUATION.md)与[冒烟报告](MAGICBRUSH_RESULTS.md)继续适用。本次只修改调度、协调和启动封装；未启动正式实验。

## 提交方式

一个 ARNOLD 作业：**2 workers，每台 8×H100 80GB，两台均挂载 `/mnt/bn/strategy-mllm-train/user/tanyue/`**。两台执行同一条前台命令，attempt 必须相同：

```bash
MAGICBRUSH_ATTEMPT=run001 bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/magicbrush_2node16_20261106/start.sh
```

平台需提供 `ARNOLD_WORKER_NUM=2`、`ARNOLD_WORKER_GPU=8`、不同的 `ARNOLD_ID=0/1`。入口拒绝错误拓扑、相同物理主机和原共享开发机。每张卡仍须至少 70,000 MiB 空闲；不会结束已有进程。仅通过 NAS 协调，无 `torchrun`、NCCL 或端口监听；子进程端口变量保留在 42000–42007。

可选的 CPU／空闲检查使用独立 attempt；它会恢复环境、读 `nvidia-smi` 和验证文件，但不运行模型：

```bash
MAGICBRUSH_ATTEMPT=validate001 bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/magicbrush_2node16_20261106/start.sh --validate-only
```

预检退出后，正式运行使用新 attempt。每次恢复也只改 attempt；同一结果目录的完成记录继续复用。

## 调度与信息边界

| 项目 | 当前执行方式 |
|---|---|
| 数据 | 原 535 会话、1,053 编辑轮；八方法、两种 mask 轨道和独立／连续评测保持不变 |
| node 0 | 268 会话，每方法 1,572 个生成请求 |
| node 1 | 267 会话，每方法 1,570 个生成请求 |
| 全量 | 每方法 3,142 次联合编辑，共 25,136 次；Pass1／planner 仍按原生流程另计 |
| 分配规则 | 以会话请求数降序、原始索引顺序打破同权重并列，依次交给累计请求数较少的节点；不参考图像、预测或分数 |
| 多轮依赖 | 完整会话固定归属一台机器；始终使用同方法上一轮真实输出 |
| 本机队列 | 八个单卡槽位，按冻结冒烟耗时排列各方法的任务；GPU 之间无模型张量并行 |
| 评分 | 两台生成均完成后开始；全局分片编号 `node_rank*8+card`，共 16 片；原始评分代码不变 |
| 汇总 | 两台评分均结束后，node 0 统一读全部逐图记录；保持同一完整集／排除重合集和会话 bootstrap，不平均节点分数或区间 |

原生单卡 worker 的冻结门禁要求独立单机环境。因此，外层控制器先严格验证真实 2×8 拓扑，再仅对其子进程设置 `ARNOLD_WORKER_NUM=1`、`WORLD_SIZE=1` 等单机运行变量。真实节点身份仍存于 `MAGICBRUSH_CLUSTER_NODE_ID`、`MAGICBRUSH_CLUSTER_WORKERS`、OWNER/TASKS 记录。这是运行时隔离；不修改原生模型调用、生成代码或科学记录身份。

## 包与结果位置

| 内容 | 路径 |
|---|---|
| 当前入口与 READY | `.ifbench-tmp/magicbrush_2node16_20261106/` |
| 原始冻结输入和冒烟 | `.ifbench-tmp/magicbrush_20261105/`，保留原状；新 READY 引用原绝对路径 |
| 发布身份与校验记录 | `.ifbench-tmp/magicbrush_2node16_20261106-handoff.md`，在包外 |
| 正式结果 | `experiments2/SAMTokEdit/external_magicbrush/run_001/` |
| 启动日志 | `experiments2/SAMTokEdit/external_magicbrush/arnold/<attempt>/node-<rank>/entry.log` |
| 心跳／阶段／评分日志 | `run_001/cluster/<attempt>/node-<rank>/` |
| 生成阶段日志 | `run_001/nodes/node-<rank>/attempts/<attempt>/` |
| 原图、输出、逐图评分、报告 | 原 `runs/`、`scores/`、`report/` 布局保持不变 |

上述路径均以 `/mnt/bn/strategy-mllm-train/user/tanyue/` 为根。新 READY 逐项保留原 12,660 个资产校验项；19 个生成源文件、评分与统计实现、模型配置、环境 staging 文件均与原发布 commit 相同。运行时代码和环境从 NAS/GitHub 恢复到各容器 `/tmp`，不依赖开发机的本地目录。

## 恢复与故障处理

- **重复启动保护**：node 0 原子创建 NAS 的 `CLUSTER.lock/` 并写入 attempt/token；只有旧 attempt 两个节点均写入 RELEASED，才允许归档旧锁目录并交给新 attempt。每个 rank 的 OWNER 仅创建一次，复用 attempt 会拒绝。NAS 实测不支持 `flock`，因此跨机准入不依赖它；节点生成锁和 staging 锁只位于本地 `/tmp`。支持 `flock` 的挂载还会保留与旧单机入口的排他兼容。
- **心跳**：15 秒写一次；读取遇到文件短暂缺失或 JSON 未完整可见会重试。连续未观测到新序号超过 600 秒才判失联；短暂读取失败保留最近一次成功时间，不回退到 OWNER 创建时间。新节点入场最多等待 60 分钟。
- **正常停止**：分别向两台机器 `cluster/<attempt>/node-<rank>/OWNER.json` 中的本机 PID 发 `SIGUSR1`。控制器让自己启动的生成／评分进程完成当前请求，再退出；不会向其他作业发信号。
- **节点故障**：同伴记录 FAILED 或心跳超时后，另一节点停止发新任务并等待自己当前请求结束。强制平台终止仍可能留下未知 admission；遵循原规则核查和隔离，不自动重采样。
- **续跑**：正常／优雅退出写入 RELEASED 后，用新 attempt 在两台执行相同入口。全部终态的阶段跳过，已有评分验证身份后复用。模型失败、评分缺失仍按原协议保留，不改写结果。

如果平台强制杀死容器、没有 RELEASED，则先在平台确认**两台旧 worker 都已退出**，再手工放行协调锁（不放行未知 admission）：

```bash
/usr/bin/python3 -I /opt/tiger/tanyue/if-bench-magicbrush/scripts/magicbrush_dual.py release \
  --package /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/magicbrush_2node16_20261106 \
  --attempt <已停止的旧attempt> --confirm-both-workers-stopped \
  --reason '平台已确认两个旧 worker 均退出；填写实际中断原因'
```

该 CPU 命令也可使用新节点上的同一提交源码。它只新增 `cluster/<旧attempt>/FORCED_RELEASE.json`，保留原锁和所有生成／评分证据；不可在旧 worker 尚存活时执行。未知 admission 仍按原规则单独处理。

## 耗时与验证

八方法冒烟外推总生成量为 **342.77 GPU·h**。16 卡完全均衡下约 **21.42 h**；当前固定会话分配与本地任务队列的模拟最长节点约 **22.67 h**。实际另加环境恢复、冷加载、NAS I/O、标准指标和报告；这些数字不是正式实测或完成时间承诺。

本次验证使用 CPU：双进程阶段屏障、同伴失败、剩余节点锁保护、并发心跳覆盖／暂时不可读、优雅停止、完整会话依赖、16 个评分分片无重漏、共享 RUN 与源码快照复用。原八方法真实 GPU 冒烟结果继续适用，不为调度变更重新采样。发布工具从已推送的干净 `eval-magicbrush` 提交构造新包，并核验全部 NAS 资产。
