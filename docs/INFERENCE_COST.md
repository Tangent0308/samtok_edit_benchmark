# IF-Bench 推理开销实验

统一后端与 GPU 驻留的独立补测见 [INFERENCE_COST_UNIFIED.md](INFERENCE_COST_UNIFIED.md)。
本页记录已完成的原生实现计时，两类执行配置分别保存与报告。

本分支 `eval-inference-cost` 实现独立的计时实验，复用已冻结的 IF-Bench
fairness-v2.2-1mp 输入与模型接口。所有结果写入新的 NAS 临时目录；不修改
正式评测的输入、模型输出、Judge、分数或运行包。不调用付费 API。

## 实验范围

| 项目 | 固定口径 |
|---|---|
| Benchmark | IF-Bench，约 1MP 公共画布；沿用各模型已确认的输入方式 |
| 方法 | SITEdit R2@1000、Qwen-Image-2.1、RePlan、MIRAGE、MICE |
| Setting | S1 和 S3-mask，分别报告 |
| 样本 | 同一组 20 张源图，K=2、3、4、5 各 5 张 |
| 选择 | seed 20261112，对公开 case ID 做确定性哈希排序；不读取成绩或生成状态选择样本 |
| 重复 | 每个方法 × setting × 源图计时 3 次；生成 seed 始终为 42 |
| 规模 | 200 个方法／请求组合，600 次计时编辑，另有定位／规划及明确记录的预热 |
| 硬件 | 独占单机 8×H100 80GB，每个 GPU 一个 worker、batch size 1 |

20 张图同时用于总体开销和 K 曲线，不另选有利于某种趋势的样本。
同一源图、setting 和重复次数在各方法上分配到同一张卡。
三个阶段的方法分开加载，不要求把整个方法的所有模型同时放入一张卡。

SITEdit 固定使用 `8beaffbd24a773cb7441948df57e65c576e31126` 的原生方法实现：
Pass1 定位 LoRA step 2000，DiT LoRA／CodeInjector 为
`quality_anchor_20261104/runs_v5/v6_full/r2/train/adapter_1000`，LoRA 强度 1.0，
raw SAMTok TE，40 步，token guidance γ=2，负分支是同一句去掉区域 token。
每次编辑前保留原生 `torch._dynamo.reset()`。

| 方法 | 定位／规划阶段 | 编辑阶段 |
|---|---|---|
| Qwen-Image-2.1 | 无额外规划器 | 原生一次联合编辑，40 步、true CFG 1，保留官方主实验使用的 model CPU offload |
| RePlan | 冻结的原生规划器及其区域输入路径 | Qwen-2511，40 步、true CFG 4，原生区域注意力 |
| MIRAGE | 原生指令解析和定位；保留公共空间提示 | Qwen-2511，40 步、true CFG 4，patch ratio 0.4；记录实际规划区域数 R |
| MICE | 无额外规划器；保留原生文本长度校验 | 原生 FLUX.2 Klein 4B、4 步、guidance 1 |
| SITEdit | S1：一次联合 Pass1；S3-mask：逐公开 mask 编码，不调用 Pass1 | 一次联合 S2，40 步，区域 token guidance 2；没有合法 token 时保留原生纯文本回退 |

MIRAGE 的 R 不一定等于数据目标数 K；局部区域分支不表述为 K 次完整图像生成。
详细输入和原生流程见 [USAGE.md](USAGE.md)。

## 测量与统计

- 用 CUDA 同步包围原生阶段调用，记录 `native_seconds`；模型加载时间另外记录。
- 每个 worker 依固定队列预热，直到首次成功或队列耗尽，保留每次预热记录。
  全部 worker 完成加载和预热后通过屏障，同时开始正式计时。
- 公共输入以完全相同的字节预读至 RAM，路径和公开请求不重写。输入校验、权重加载、
  最终 PNG／JSON 写入和与历史输出的字节对照在计时区间外。
- 保留图像／mask 解码、必要的数据准备和 CPU/GPU 传输、原生编码／VAE 解码、
  原生 CPU offload、编译状态重置。原生 wrapper 的少量簿记保留在 RAM 临时目录。
- SITEdit 仅用于可视化的 mask 解码和 MIRAGE 的诊断图片序列化不计入模型工作；
  它们不参与实际生成。不得删除原生区域编码、规划、模型推理或条件构造。
- 单独保存规划／token 阶段和编辑阶段耗时、实际输出尺寸、峰值 allocated／reserved
  GPU 显存、原生调用计数和输出 RGB SHA256。MIRAGE 额外保存 R。
- 各阶段分别驻留模型，**`warm_stage_sum_seconds` 是阶段耗时之和，不是实测端到端延迟**。
  不包括两个独立 Python 环境间的冷启动切换；报告中的端到端字段始终为 null。
- 每个源图先对三次重复取中位数，再在源图之间统计均值／中位数。三次都成功才进入
  成功耗时统计；失败、依赖阻塞、未完成保留状态和已消耗时间，绝不填零伪造低耗时。
  同时输出所有方法共同完成样本的配对统计，保留原始样本覆盖情况。
- 去噪前向次数不是 FLOPs，也不能直接推出时间加速倍数。基线沿用原 wrapper 的
  forward hook；SITEdit 沿用冻结循环的预期计数（有 token 为 80，无 token 为 40），
  明确记录计数来源，不额外安装可能改变 Dynamo 行为的 hook。
- 正式质量分数来自全量评测，开销来自此固定子集，论文中应分清两者的分母。
  此实验不产生新的质量分数，也不通过重复生成选择更好的输出。

## 一个前台入口完成实验

提交**一个 worker、8 张 H100 80GB**。所有必需代码和环境均来自 NAS，不需要 GitHub
下载、不使用 ARNOLD 分布式端口、不启动 NCCL 或跨机通信。

```bash
bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/ifbench_cost_8gpu_20261112/package-v1/start.sh --attempt run001
```

入口在前台运行，直到 5 个方法的全部阶段和报告完成。不要追加 `&` 或 `nohup`。
启动会拒绝已有 GPU compute 进程、非空闲 GPU 或非 8×H100 配置；不会终止其他任务。
`/tmp` 至少需要 50 GiB 空闲空间；三套环境与代码在独立的 attempt 目录中恢复。
NAS 环境归档只读取一次并同时校验哈希，解包在本地完成。

默认命令已经包含预热、正式计时和报告，通常无需额外命令：

```bash
# 可选：只恢复环境并做前置检查，不调用模型
bash <package>/start.sh --attempt check001 --validate-only
# 可选：每卡、每阶段只测一个固定任务，另写 results/smoke
bash <package>/start.sh --attempt smoke001 --smoke-only
# 中断后的新 attempt：跳过已有终态，不覆盖记录
bash <package>/start.sh --attempt run002
```

若请求已写 ADMITTED 但没有终态，入口会停止并指出具体路径，禁止悄悄重采样。
SIGUSR1／SIGTERM 会要求自有 worker 完成当前测量后退出；不停止其他用户的进程。
硬件故障或平台强杀后须先审查未终态记录，再决定是否放行。

## NAS 交接与监控

运行包：
`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/ifbench_cost_8gpu_20261112/package-v1/`

输出根：
`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/ifbench_cost_8gpu_20261112/results/`

| 文件 | 用途 |
|---|---|
| 包内 `PLAN.json` | 固定样本、输入 SHA、方法配置、分工、重复和计时定义 |
| 包内 `READY.json` | 代码 commit、plan digest、运行环境与代码归档哈希、依赖指纹 |
| `STARTUP.json` | 当前启动阶段、机器和 attempt |
| `bootstrap/<attempt>/{STATUS,HEARTBEAT,RUNTIME}.json` | 启动心跳、环境验证和实际解释器路径 |
| `bootstrap/<attempt>/bootstrap.log` | 环境恢复及控制器的前台日志副本 |
| `PROGRESS.json` | 当前方法／setting／阶段、8 卡状态、阶段内完成数量和粗略剩余时间 |
| `attempts/<attempt>/` | GPU 初始状态、逐阶段日志、屏障、预热记录和 GPU 采样 |
| `records/<model>/<setting>/<stage>/<case>/repeat-N/` | 不覆盖的受理／终态记录，repeat-0 的原始图片 |
| `REPORT.json`／`REPORT.md` | 总表、阶段拆分、K 分桶、逐次证据、失败与缺失状态 |
| `REPORT.json` 的 `diagnostics`／`worker_accounting` | 输出／token 一致性待检查项，加载及 worker 占用时长 |
| `COST_VS_K.svg` | 自动生成的 K—耗时曲线 |

包目录外的 `../handoff.md` 包含精确启动命令、READY SHA、commit、plan digest、输出位置
和验证状态，本会话及其他机器上的会话可直接从 NAS 读取。正式执行前不声称 GPU 冒烟
或计时已经通过；远端日志会给出真实结果。

## 开发验证

代码位于 `src/samtok_benchmark/inference_cost/`；入口在 `scripts/inference_cost*.py`，
发布工具为 `scripts/publish_inference_cost.py`。冻结的生成适配器、canvas、public 和 Judge
源文件没有修改。发布器核对关键生成接口与正式包逐字节一致。

```bash
IFBENCH_COST_METHOD_TEST=<pinned-method-source> python -m pytest -q tests/test_inference_cost.py
ruff check src/samtok_benchmark/inference_cost scripts/inference_cost*.py scripts/publish_inference_cost.py tests/test_inference_cost.py
```

当前发布前验证仅在 CPU 执行；本机现有 CompBench MIRAGE 任务保持运行。运行环境归档
通过哈希和禁用 CUDA 的实际 import 检查，GPU 加载／预热由用户提交的独占机器完成。
