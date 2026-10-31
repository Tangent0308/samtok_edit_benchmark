# IF-Bench 全量四机评测

本轮将 release 2.6.0 的 **1,084 张源图、3,872 个编辑单元全部纳入同一份总结果**。七模型、十 setting 共 **75,880 条逻辑请求**，每个模型×setting的分母是1,084图/3,872单元；不单列dev/test成绩。

用户已确认使用四台机器，每台 **8×H100 80GB**，访问同一挂载 `/mnt/bn/strategy-mllm-train/user/tanyue/`。沿用[已验证的模型与输入方式](USAGE.md)，不重新择优或调参。旧108/976划分和dev20名单作为历史暴露记录保留；总结果包含开发时使用过的图，因此不称为独立未见测试集估计。

## 1. 四机如何分工

| 机器 | 参数 | 固定源图 | 编辑单元 | 七模型×十setting请求 |
|---|---|---:|---:|---:|
| 机器1 | `--node 0` | 271 | 968 | 18,970 |
| 机器2 | `--node 1` | 271 | 968 | 18,970 |
| 机器3 | `--node 2` | 271 | 968 | 18,970 |
| 机器4 | `--node 3` | 271 | 968 | 18,970 |

- 一个全局冻结plan、同一组权重/参数/seed、同一份S4/S5分配。按K和固定ID哈希均衡分配源图，四片互斥且覆盖完整数据。
- 同一源图的七模型和全部setting固定在同一台；canonical Judge key含源图身份，因此同图重复输出可在本机去重。合并仍会拒绝跨节点重复key或所有权冲突。
- 每台按模型依次生成，当前模型的请求分给8个单卡worker。RePlan/MIRAGE先完成本机原生规划，再联合编辑；不存在逐目标连续改图。
- 本机全部生成结束后，释放generation进程，使用原固定TP8/EP、batch16 Judge按模型依次评分。四台互不等待生成/评分阶段；不建立跨机NCCL通信。
- 最后一台完成后自动验证四份逐case结果，并生成全局报告。置信区间用全部1,084源图做10,000次paired bootstrap，所有模型/setting共用抽样；**不平均四机分数或CI**。

## 2. 冻结输入与已知问题

采样seed固定42；Qwen2.1采用原生model CPU offload、2K/40步/CFG1/KV cache。其他模型原生默认、输入路由、内部planner和外部组件关闭边界与[USAGE.md](USAGE.md)一致。Judge仍只看canonical ref指令、GT source selector及输出，统一回到源图分辨率，不知道editor拿到哪种输入形式。

旧dev20的1,400条终态是精确复用来源，含1,399个生成输出和1个既有MIRAGE原生规划失败；实际复用需逐条核验。新任务保留旧请求和公开资产的原引用，不重写路径来绕过相等检查。评分从最新已完成的effective记录导出全部有效key及raw/overlay证据，不能只复制其继承索引。缓存不计新增推理，原始成本和修复经过继续保留。

全量CPU tokenizer检查发现 **MICE有19条S2-point请求的global段超过原生200-token限制**，均为K=5，请求长度201–215；四片分别7/3/7/2条。按已确认的规则，保存完整输入及超限证据，worker在采样前记录`failed/input_preflight`、`attempt_admitted=false`和零模型调用，并保留分母。不会删任务、截断、缩短已冻结prompt或扩大原生token预算。FLUX2 Klein9B全部公开prompt通过512-token检查。

当前入口覆盖70条主结果、S2丢弃区域的精确S1复用补充、语言/区域/形式/混合派生指标、K分桶、逐请求调用账本，以及每模型×setting固定10例的人工抽检材料。人工残留率/κ、GT selector paste-back诊断和额外协议消融仍需独立实施，不能由主表脚本编造数值。

## 3. 四台机器的入口

共享运行包：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/full4-v21-1084-20261031
```

只有存在`READY.json`的冻结包可以启动。每台机器仅启动对应的一条，**不要加`nohup`或`&`**；平台用户脚本必须一直等待前台命令结束。

机器1：

```bash
bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/full4-v21-1084-20261031/start.sh --node 0
```

机器2：

```bash
bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/full4-v21-1084-20261031/start.sh --node 1
```

机器3：

```bash
bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/full4-v21-1084-20261031/start.sh --node 2
```

机器4：

```bash
bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/full4-v21-1084-20261031/start.sh --node 3
```

想先做单机环境检查，可在该命令末尾加`--validate-only`。它会校验源码/资产/缓存、准备两套隔离runtime并检查GPU，但不进行模型采样或Judge。已有本地repo可用等价入口：

```bash
if-bench run-full --bundle /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/full4-v21-1084-20261031 --node 0
```

每台需x86_64 Linux、glibc≥2.36、gcc/g++和每卡至少70GiB空闲。两个固定runtime归档分别约10.49GB、13.50GB，启动时按各自SHA核验并展开到本机`/tmp/ifbench/full4-runtime-20261031`；保证本机临时盘足够容纳归档解压及缓存。输入、权重、历史证据必须能通过共享挂载访问。入口不会下载新权重、升级固定环境或停止其他GPU进程。

## 4. 进度、故障与恢复

每台前台日志及`nodes/node-N/progress.json`约30秒更新一次。进度含当前模型/阶段、完成数、失败、Judge状态和基于已完成调用的当前阶段ETA；没有足够观测时ETA为空，不填写猜测。

任一能访问挂载的主机可查看四台状态：

```bash
bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/full4-v21-1084-20261031/start.sh --status
```

安装本仓库后可使用只读入口：

```bash
if-bench inspect-full --bundle /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/full4-v21-1084-20261031
```

- 同一node的重复启动由共享目录claim拒绝；同一主机也有runtime锁，避免两份任务争同一组8卡。
- 正常终态不会重采样，重启跳过已完成请求；模型原生失败保持失败。
- 存在`started.json`但没有终态时，禁止自动重新采样。GPU异常会记录错误并停止该节点，其他节点可以继续。
- 强杀后残留`ACTIVE`不能直接删后重跑：先确认旧进程已退出、检查其已admit请求。控制器正常捕获退出时仅终止自己启动的子进程，保留原执行回执。
- Judge失败保留原回答和固定确定性解析结果，缺分明确报告；没有通用重试授权。四台尚未齐全时不会把局部结果当成全量成绩。

根据旧运行的非缓存实际计时，初始规划约 **4–6天**；这是相同硬件/吞吐下的宽松时间窗口，启动后按实际进度更新，不是完成保证。初始化、共享盘I/O和长尾会影响墙钟。

## 5. 文件位置与最终报告

正式运行结果：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/IF-Bench/full4-v21-1084-20261031
```

| 相对位置 | 内容 |
|---|---|
| `runs/<model>/outputs/<setting>/<case>/` | 真实调用、原生输出、源分辨率输出、终态与SHA |
| `runs/<model>/planners/<setting>/<case>/` | RePlan/MIRAGE原生规划证据 |
| `nodes/node-N/workers/` | 本节点8卡worker环境、状态与实际调用计数 |
| `nodes/node-N/judge/` | 本节点canonical raw、effective、admission和运行回执 |
| `nodes/node-N/progress.json` / `COMPLETED.json` / `ERROR.json` | 节点状态与终结记录 |
| `report/REPORT.md` / `REPORT.json` | 全量70行、95% CI、派生量、K桶与内嵌对照图 |
| `report/CALLS.json` | 新调用、planner、加载和历史成本来源 |
| `report/AUDIT_GALLERY.md` | 每模型×setting相同10图，共700组输入/输出/最终prompt |
| `report/COMPLETED.json` | 汇总完成状态、plan/report SHA；有缺分会明确标识 |

输入构造、代码快照、preflight和启动日志留在共享`.ifbench-tmp`运行包。正式目录只接收该已冻结全量运行的正式产物。旧dev包与结果保持不可变。总报告记录源代码commit、权重revision、冻结请求、seed、额外推理调用及逐节点计时；所有有终结回执的节点执行（含停止后续跑）的墙钟×8属于有范围说明的GPU预留时间；强杀导致时长未知的执行单独列为缺失，，不能冒称GPU内核活跃时间或包含平台排队的总费用。

## 6. 开发与重新准备

实现：[全量范围校验](../src/samtok_benchmark/ifbench/full_plan.py)、[CPU构造/发布](../src/evaluation/protocol_audit/prepare_full4.py)、[节点控制器](../src/samtok_benchmark/ifbench/full_run.py)、[统一统计](../src/samtok_benchmark/ifbench/full_report.py)。

若维护者为同一冻结协议准备另一份运行包，必须使用新的空目录及结果路径；不能覆盖已发布的READY、请求、计划或结果。CPU输入构造可多进程执行；已完成的dev20复用链继续按原输入和SHA核验。发布需要干净已提交源码，不会自动启动GPU：

```bash
python -m evaluation.protocol_audit.prepare_full4 --bundle /path/to/new-bundle --results /path/to/new-formal-results --workers 16
python -m evaluation.protocol_audit.prepare_full4 --bundle /path/to/new-bundle --publish
```

这不是创建新候选、改变推理协议或自动重跑失败的授权。旧dev20的严格20图校验保留，全量使用独立schema和本次授权记录。
