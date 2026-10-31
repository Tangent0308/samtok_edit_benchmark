# IF-Bench 约1MP全量四机评测

当前配置为 [fairness_v2_2_1mp.json](../configs/evaluation/fairness_v2_2_1mp.json)。一个ARNOLD作业含4个worker，每个8×H100 80GB，共32卡，共享 `/mnt/bn/strategy-mllm-train/user/tanyue/` 挂载。全部 **1,084张图、3,872个编辑单元** 合并为一份总成绩；七模型×十setting共 **75,880条逻辑请求**。

模型输入、公共灰色letterbox画布、坐标变换及输出去padding见 [USAGE.md](USAGE.md)。模型与全部原生planner只读公共约1MP的I/A；Qwen2.1使用output_resolution1024；RePlan/MIRAGE保留原生近1MP网格，不声明显式width/height能约束RePlan结果。Judge仍使用原始源图/GT和逆映射输出。

当前小样本包为 `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/one-mp-probe-20261031`。全量包计划位置为 `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/one-mp-full4-20261031`，正式结果根计划为 `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/IF-Bench/one-mp-full4-20261031`。

**全部1,084图输入与全量READY尚待准备、核验和发布；当前不能把该路径当成已可启动的包。** 发布时以实际READY、plan和SHA回执为准。当前验证和正式结果状态见 [RESULTS.md](RESULTS.md)。构造输入前先提交并保持源码干净；构造完成并核验后，发布命令为：

```bash
PYTHONPATH=src python -m evaluation.protocol_audit.prepare_full4 \
  --bundle /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/one-mp-full4-20261031 \
  --publish
```

## 分片与并行

| worker | 平台编号 | 源图 | 单元 | 逻辑请求 |
|---|---|---:|---:|---:|
| 0 | ARNOLD_ID=0 | 271 | 968 | 18,970 |
| 1 | ARNOLD_ID=1 | 271 | 968 | 18,970 |
| 2 | ARNOLD_ID=2 | 271 | 968 | 18,970 |
| 3 | ARNOLD_ID=3 | 271 | 968 | 18,970 |

一个全局plan固定权重、参数、seed42、公共画布、几何、S4/S5分配和源图所有权。每张图的七模型×十setting在同一台机器，节点间不重复处理。每台按模型依次推进，同一模型的请求分给8个单卡worker；RePlan/MIRAGE先执行原生规划，再联合编辑，不按目标串行改K遍。

四台执行同一条前台命令，从ARNOLD平台变量取编号。启动先核验4×8拓扑、TCP通信、同一READY和共享挂载，再准备固定运行环境；四份完整输入preflight均通过后才允许采样。不同节点随后独立推进，不要求每个模型跨机同步。

本机全部生成结束、generation进程释放后，启动固定TP8/EP、batch16 Judge，并按模型依次完成评分。集群最多同时四组TP8 Judge。worker0验证四份逐图结果后统一汇总；所有前台控制器等待共同完成后退出。全局逐源图paired bootstrap不平均四机百分数或CI。

## 启动

设置平台为4个worker、每worker8卡。以下为READY发布后的共同入口；四台使用相同包路径与attempt：

```bash
export IFBENCH_BUNDLE=/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/one-mp-full4-20261031
test -f "$IFBENCH_BUNDLE/READY.json" || { echo "当前1MP运行包尚未发布READY"; exit 1; }
bash "$IFBENCH_BUNDLE/start.sh" --attempt run001
```

不要追加 `nohup`、`&` 或外套 `torchrun`。入口自行管理每机8卡子进程。`attempt` 在四台必须相同，每次平台提交使用新值；新attempt只隔离日志，不授权重复已admit请求。

无推理检查也由四台运行相同命令：

```bash
# 仅核验控制进程、TCP、共享盘和共同退出。
bash "$IFBENCH_BUNDLE/start.sh" --attempt network001 --coordination-only
# 进一步准备runtime、核验8卡、固定输入/几何/缓存；不调用模型或Judge。
bash "$IFBENCH_BUNDLE/start.sh" --attempt preflight001 --validate-only
```

各机需要x86_64 Linux、glibc≥2.36、gcc/g++及每卡至少70GiB空闲，临时盘应能容纳两个固定runtime、源码和编译缓存。平台提供的端口条目数不等于worker数；拓扑由ARNOLD_WORKER_NUM/ARNOLD_WORKER_GPU校验，共同endpoint取ARNOLD_WORKER_HOSTS首项并支持IPv6。所有运行源码与环境按固定SHA检查，不在执行中升级或下载新权重，不停止其他GPU任务。

## 冻结、失败与恢复

- 输入冻结包含原始case身份、公共I/A和公开mask的SHA、精确画布几何、完整最终prompt、模型参数与源码身份。输入不得偷偷切回高分辨率原图。
- 每请求只采样一次。模型原生规划、输入超限与生成失败留在完整分母；低分不重采样。MICE各global/local段保留原生200-token完整性门，FLUX2保留512-token完整性检查，不截断任务。
- 有 `started.json` 或Judge admission但缺终态时，可能已经采样，禁止自动重试。正常终态重启时按相同绑定核验后跳过，不删除失败记录。
- 同一attempt/rank的重复启动被claim拒绝；基础设施故障传播到其他控制器，仅停止本作业启动的子进程。强杀遗留claim须先查清进程和已admit请求，不能直接删除后重跑。
- 精确生成复用要求输入像素、prompt、几何、权重、参数、seed和原生实现均一致；只有最终输出尺寸相近不构成相等。Judge缓存另核完整canonical身份和输出SHA，新增调用记0，实际成本分别披露。
- 新Judge raw与admission集合双向一致，逐条绑定key、源图、输出、canonical prompt与attempt=1。确定性JSON恢复单独保存overlay，不产生额外推理。
- 未齐四台完整终态时不发布全量分数。Judge缺分保留为缺失，不能补0或只报可评分子集。

## CPU构造入口

当前实现使用独立空目录构造公共输入和模型请求，不运行GPU。以下命令在仓库根目录执行，`python` 必须来自已核验的 generation runtime（Transformers 5.19.0、Pillow 12.3.0；完整身份见运行包 `bootstrap.json`）。CPU构造也需真实 MICE tokenizer 做长度检查，基础开发环境不包含全部这些依赖。构造和发布均设置 `PYTHONPATH=src`，避免误用其他 checkout 的已安装包。完整1,084图的构造命令为：

```bash
PYTHONPATH=src python -m samtok_benchmark.ifbench.prepare_one_mp \
  --scope full \
  --bundle /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/one-mp-full4-20261031 \
  --results /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/IF-Bench/one-mp-full4-20261031
```

构造输出不是READY发布完成的证明。已有请求/结果目录不能覆盖；维护者需核对配置、CPU验证、最小GPU验证和源码SHA后再发布固定启动身份。当前小样本采用2图×3setting×7模型的42条生成请求；另以3图×10setting×7模型核验210条CPU请求。实际完成状态分别记录，不将少量GPU样本扩大宣称为70组合均已实测。

## 进度与文件

```bash
bash "$IFBENCH_BUNDLE/start.sh" --status
if-bench inspect-full --bundle "$IFBENCH_BUNDLE"
```

启动心跳位于包内 `launches/<attempt>/nodes/<rank>/heartbeat.json`；模型/Judge状态位于正式结果根的 `nodes/node-N/progress.json`。ETA仅从当前方案真实已完成调用估计；样本不足时留空，不套用其他分辨率的运行时长。

| 位置 | 内容 |
|---|---|
| 包内 `READY.json`、`plan.json`、代码manifest | 发布身份、权重/参数、分片、当前配置与源码SHA |
| 包内公共资产、请求与几何记录 | 约1MP清图/标注/公开区域及精确逆映射契约 |
| `runs/<model>/outputs/<setting>/<case>/` | 实际call、raw输出、回源输出、终态、尺寸和SHA |
| `runs/<model>/planners/<setting>/<case>/` | 原生规划输入、响应、trace、调用数 |
| `nodes/node-N/workers/` | 环境、加载、worker状态与真实API/forward计数 |
| `nodes/node-N/judge/` | canonical raw/effective/admission与执行回执 |
| `report/REPORT.md`、`REPORT.json` | 70条主行、UP/JP及CI、112派生项、K桶、真实内嵌图 |
| `report/CALLS.json` | 编辑/规划/Judge调用与加载、缓存、耗时来源 |
| `report/AUDIT_GALLERY.md` | 每模型×setting固定随机10图，共700组输入/输出/最终prompt |
| `report/COMPLETED.json` | 汇总状态、plan/report SHA和缺分情况 |

正式结果位置由plan的 `results_root` 指定，位于共享 `experiments2/IF-Bench/` 的独立目录；准备、短测、审查、预览留在 `/tmp/ifbench/` 或共享 `.ifbench-tmp/`。完整输出不入Git，结果页仅同步当前聚合记录和少量真实图像。

成本统计保留全部停止/恢复执行的实测墙钟，不把最终成功回执当全部成本。控制器墙钟×8是该阶段GPU预留时间，不是GPU内核活跃时间；平台排队、环境准备和节点等待另列，强杀造成的未知时长保持缺失。

人工残留率、κ、GT selector paste-back诊断和额外消融需要单独完成；主表执行器不生成这些未观测数值。全量报告包含开发过程接触过的数据，不称为独立未见测试集估计。

实现：[当前CPU输入构造](../src/samtok_benchmark/ifbench/prepare_one_mp.py) · [小样本worker](../src/samtok_benchmark/ifbench/one_mp_probe.py) · [范围与身份校验](../src/samtok_benchmark/ifbench/full_plan.py) · [公共画布](../src/samtok_benchmark/ifbench/canvas.py) · [前台入口](../src/evaluation/protocol_audit/start_arnold_full4.sh) · [ARNOLD调度](../src/evaluation/protocol_audit/run_arnold_full4.py) · [节点控制器](../src/samtok_benchmark/ifbench/full_run.py) · [合并统计](../src/samtok_benchmark/ifbench/full_report.py)。
