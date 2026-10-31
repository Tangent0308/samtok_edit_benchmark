# IF-Bench 全量四机评测

本轮将 release 2.6.0 的 **1,084 张源图、3,872 个编辑单元全部纳入同一份总结果**。七模型、十 setting 共 **75,880 条逻辑请求**，每个模型×setting的分母是1,084图/3,872单元；不单列dev/test成绩。

用户已确认使用 **一个 ARNOLD 作业，4 个 worker，每个 8×H100 80GB，共32卡**；节点间可通信，访问同一挂载 `/mnt/bn/strategy-mllm-train/user/tanyue/`。四个worker执行同一条命令，由平台变量识别节点。沿用[已验证的模型与输入方式](USAGE.md)，不重新择优或调参。旧108/976划分和dev20名单作为历史暴露记录保留；总结果包含开发时使用过的图，因此不称为独立未见测试集估计。

## 1. 四机如何分工

| worker | 自动读取的平台编号 | 固定源图 | 编辑单元 | 七模型×十setting请求 |
|---|---|---:|---:|---:|
| 0 | `ARNOLD_ID=0` | 271 | 968 | 18,970 |
| 1 | `ARNOLD_ID=1` | 271 | 968 | 18,970 |
| 2 | `ARNOLD_ID=2` | 271 | 968 | 18,970 |
| 3 | `ARNOLD_ID=3` | 271 | 968 | 18,970 |

- 一个全局冻结plan、同一组权重/参数/seed、同一份S4/S5分配。按K和固定ID哈希均衡分配源图，四片互斥且覆盖完整数据。
- 同一源图的七模型和全部setting固定在同一台；canonical Judge key含源图身份，因此同图重复输出可在本机去重。合并仍会拒绝跨节点重复key或所有权冲突。
- 每台按模型依次生成，当前模型的请求分给8个单卡worker。RePlan/MIRAGE先完成本机原生规划，再联合编辑；不存在逐目标连续改图。
- 四台先完成TCP通信核验，再安装并验证环境。**四份输入preflight全部通过后才允许采样**。正常执行时各source owner独立推进生成/评分阶段，不为每个模型设跨机等待。
- 本机全部生成结束后，释放generation进程，使用原固定TP8/EP、batch16 Judge按模型依次评分。集群同时最多运行四组TP8 Judge；不把Judge改成跨机TP32，也不把一次原生出图拆到32卡。
- 全部节点完成后由 **worker 0** 验证四份逐case结果，生成全局报告；四个前台控制器都等汇总完成才退出。置信区间用全部1,084源图做10,000次paired bootstrap，所有模型/setting共用抽样；**不平均四机分数或CI**。

启动方式参考用户指定的 [SAMTokEdit 四机指南](https://github.com/Tangent0308/samtok_edit/blob/4443f60b557cfbc12ecb6b22ea938cd2b0b0a89c/docs/05_SAMTokEdit_Qwen21_%E5%9B%9B%E6%9C%BA%E5%AE%9E%E9%AA%8C%E8%BF%90%E8%A1%8C%E6%8C%87%E5%8D%97.md) 第7节，并核对了其代码：

| 参考实现中的机制 | IF-Bench采用方式与差异 |
|---|---|
| [bootstrap的ARNOLD变量校验、本地源码、失败记录](https://github.com/Tangent0308/samtok_edit/blob/4443f60b557cfbc12ecb6b22ea938cd2b0b0a89c/scripts/round2/bootstrap_arnold.sh#L40-L132) | 校验4×8和节点编号；将固定commit对应、逐文件SHA验证的代码快照复制到各机`/tmp`后执行，避免依赖每台在线clone。上游模型源码也复制到本机原约定路径；输入、权重、证据仍从共享盘读取。 |
| [公共endpoint与IPv6解析](https://github.com/Tangent0308/samtok_edit/blob/4443f60b557cfbc12ecb6b22ea938cd2b0b0a89c/scripts/round2/run_arnold.sh#L30-L41) | 取`ARNOLD_WORKER_HOSTS`第一项的host和port，支持`[IPv6]:port`；忽略各机可能不同的`PORT`。先做真实TCP握手，后用共享状态和心跳协调。 |
| [评测代码每GPU加载pipeline、按rank划分样本](https://github.com/Tangent0308/samtok_edit/blob/4443f60b557cfbc12ecb6b22ea938cd2b0b0a89c/src/samtok_edit21/evaluation/round2_eval.py#L261-L300) | 同样按样本并行，但保留已冻结的source owner划分，使用32个原生单卡worker。没有训练梯度同步需求，无需启动跨机NCCL模型组。 |
| [原评测捕获异常后跳过样本](https://github.com/Tangent0308/samtok_edit/blob/4443f60b557cfbc12ecb6b22ea938cd2b0b0a89c/src/samtok_edit21/evaluation/round2_eval.py#L278-L298) | **不采用跳过分母的做法**。原生规划/输入/生成失败保留全量分母；节点或基础设施故障传播到其他控制器，停止本作业拥有的子进程，不自动重采样。 |

参考仓库核查commit为`4443f60b557cfbc12ecb6b22ea938cd2b0b0a89c`。指南当前示例锁定`50ffa0ce3d1a1b9db88ffc4fb633b684f1e4df2a`；两者涉及的启动参数和评测分片逻辑一致。指南记录的C2正式四机运行是训练阶段，不能作为IF-Bench四机评测已实测通过的证据。

## 2. 冻结输入与已知问题

采样seed固定42；Qwen2.1采用原生model CPU offload、2K/40步/CFG1/KV cache。其他模型原生默认、输入路由、内部planner和外部组件关闭边界与[USAGE.md](USAGE.md)一致。Judge仍只看canonical ref指令、GT source selector及输出，统一回到源图分辨率，不知道editor拿到哪种输入形式。

旧dev20的1,400条终态是精确复用来源，含1,399个生成输出和1个既有MIRAGE原生规划失败；实际复用需逐条核验。新任务保留旧请求和公开资产的原引用，不重写路径来绕过相等检查。评分从最新已完成的effective记录导出全部有效key及raw/overlay证据，不能只复制其继承索引。缓存不计新增推理，原始成本和修复经过继续保留。

全量CPU tokenizer检查发现 **MICE有19条S2-point请求的global段超过原生200-token限制**，均为K=5，请求长度201–215；四片分别7/3/7/2条。按已确认的规则，保存完整输入及超限证据，worker在采样前记录`failed/input_preflight`、`attempt_admitted=false`和零模型调用，并保留分母。不会删任务、截断、缩短已冻结prompt或扩大原生token预算。FLUX2 Klein9B全部公开prompt通过512-token检查。

当前入口覆盖70条主结果、S2丢弃区域的精确S1复用补充、语言/区域/形式/混合派生指标、K分桶、逐请求调用账本，以及每模型×setting固定10例的人工抽检材料。人工残留率/κ、GT selector paste-back诊断和额外协议消融仍需独立实施，不能由主表脚本编造数值。

## 3. 一个四机作业的共同入口

共享运行包：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/full4-arnold-v21-1084-20261031
```

只有存在`READY.json`的冻结包可以启动。平台配置4个worker、每worker8卡，**四个worker都执行下面同一条命令**，不手工指定`--node`。**不要加`nohup`或`&`**，不要再在外面套一层`torchrun`：入口已经管理每机的8卡原生worker，重复启动会争抢GPU和请求。

```bash
bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/full4-arnold-v21-1084-20261031/start.sh --attempt run001
```

默认正式入口已包含TCP通信检查和完整preflight，无需额外采样冒烟。可选的两个无推理检查也要求四个worker运行相同命令，使用不同attempt：

```bash
# 只检查4个控制进程、真实TCP通信、共享盘、共同退出；不准备GPU环境。
bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/full4-arnold-v21-1084-20261031/start.sh --attempt network001 --coordination-only
# 在上述基础上准备runtime、检查8卡和全部输入/缓存；不调用模型或Judge。
bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/full4-arnold-v21-1084-20261031/start.sh --attempt preflight001 --validate-only
```

`attempt`四机必须相同，每次平台提交使用新值；已使用的节点claim不会自动删除。新attempt仅避免覆盖日志，**不提供重采样授权**。旧`full4-v21-1084-20261031`包保留为输入来源与历史启动实现，本作业使用上面的ARNOLD包。底层`run-full --node`仍用于独立节点工具链，不是此平台入口。

每台需x86_64 Linux、glibc≥2.36、gcc/g++和每卡至少70GiB空闲。两个固定runtime归档分别约10.49GB、13.50GB，启动时按各自SHA核验并展开到本机`/tmp/ifbench/arnold-runtime/<commit>`；源码位于`/tmp/ifbench/arnold-code/<manifest-sha>/repo`，编译缓存也在本机。保证临时盘足够容纳归档解压及缓存。输入、权重、历史证据必须能通过共享挂载访问。入口不会下载新权重、升级固定环境或停止其他GPU进程。需要全新的worker容器，或原源码别名已经是通过SHA校验的本地目录；已有指向共享盘的源码别名会明确拒绝，不自动改写正在被其他任务使用的路径。

## 4. 进度、故障与恢复

控制器心跳约15秒更新一次，位于启动包`launches/<attempt>/nodes/<rank>/heartbeat.json`；注册后心跳超过300秒未更新会报故障，启动等待上限2小时。生成/评分的`nodes/node-N/progress.json`约30秒更新一次，含模型/阶段、完成数、失败、Judge状态和基于实际调用的当前阶段ETA；没有足够观测时ETA为空。

任一能访问挂载的主机可查看四台状态：

```bash
bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/full4-arnold-v21-1084-20261031/start.sh --status
```

安装本仓库后可使用只读入口：

```bash
if-bench inspect-full --bundle /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/full4-arnold-v21-1084-20261031
```

- 同一attempt同一rank的重复启动由永久claim拒绝；同一主机也有runtime锁，避免两份任务争同一组8卡。四台必须注册同一份READY、代码、拓扑和运行模式。
- 正常终态不会重采样，重启跳过已完成请求；模型原生失败保持失败。
- 存在`started.json`但没有终态时，禁止自动重新采样。已注册节点的基础设施错误、非零退出或心跳丢失会传播给其他控制器，停止其自行启动的进程，保留原始证据。原生case失败本身仍按既定策略留在分母中，不等同于整机故障。
- 强杀后残留`ACTIVE`不能直接删后重跑：先确认旧进程已退出、检查其已admit请求。控制器正常捕获退出时仅终止自己启动的子进程，保留原执行回执。
- Judge失败保留原回答和固定确定性解析结果，缺分明确报告；没有通用重试授权。四台尚未齐全时不会把局部结果当成全量成绩。

根据旧运行的非缓存实际计时，初始规划约 **4–6天**；这是相同硬件/吞吐下的宽松时间窗口，启动后按实际进度更新，不是完成保证。初始化、共享盘I/O和长尾会影响墙钟。

## 5. 文件位置与最终报告

正式运行结果：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/IF-Bench/full4-arnold-v21-1084-20261031
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

输入构造、代码快照、preflight和启动日志留在共享`.ifbench-tmp`运行包。`launches/<attempt>/SUCCESS.json`仅在四机共同完成时写出；若是无推理检查，明确记录其模式和零模型调用，不能当成全量成绩。正式目录只接收该已冻结全量运行的正式产物。旧dev包与结果保持不可变。总报告记录源代码commit、权重revision、冻结请求、seed、额外推理调用及逐节点计时；节点执行回执的墙钟×8是控制器执行阶段的GPU预留时间，**不含外层环境准备和等其他节点/报告的时间**。平台全程预留需另用全局启动/完成时间统计，不能冒称GPU内核活跃时间；强杀造成的未知时长保留缺失。

## 6. 开发与重新准备

实现：[全量范围校验](../src/samtok_benchmark/ifbench/full_plan.py)、[CPU构造/发布](../src/evaluation/protocol_audit/prepare_full4.py)、[共同前台入口](../src/evaluation/protocol_audit/start_arnold_full4.sh)、[ARNOLD调度](../src/evaluation/protocol_audit/run_arnold_full4.py)、[通信与同步](../src/samtok_benchmark/ifbench/arnold.py)、[原生节点控制器](../src/samtok_benchmark/ifbench/full_run.py)、[统一统计](../src/samtok_benchmark/ifbench/full_report.py)。

若维护者为同一冻结协议准备另一份运行包，必须使用新的空目录及结果路径；不能覆盖已发布的READY、请求、计划或结果。CPU输入构造可多进程执行；已完成的dev20复用链继续按原输入和SHA核验。发布需要干净已提交源码，不会自动启动GPU：

```bash
python -m evaluation.protocol_audit.prepare_full4 --bundle /path/to/new-bundle --results /path/to/new-formal-results --workers 16
python -m evaluation.protocol_audit.prepare_full4 --bundle /path/to/new-bundle --publish
```

为已构造但尚未启动的全量输入适配ARNOLD时，使用新路径，无需重建输入：

```bash
python -m evaluation.protocol_audit.prepare_full4 --bundle /path/to/new-arnold-bundle --results /path/to/new-formal-results --reuse-full-inputs /path/to/unstarted-full-bundle
python -m evaluation.protocol_audit.prepare_full4 --bundle /path/to/new-arnold-bundle --publish
```

迁移逐条比较75,880个任务的所有非输出字段，验证request/公开信息/缓存身份保持一致，并对复制的Judge证据逐文件复核SHA；只改变调度代码和正式输出位置。原全量目录一旦出现产物就拒绝此迁移，必须先审查已admit请求。这不是创建新候选、改变推理协议或自动重跑失败的授权。旧dev20的严格20图校验保留，全量使用独立schema和本次授权记录。

验证边界：仓库包含真实TCP连接的本机四进程CPU测试，覆盖共同端口/IPv6解析、节点冲突、跨进程等待、故障传播、心跳超时和只清理自有子进程。**它不等于四台H100上的实测通过**；实际平台互联、环境和完整输入检查在正式入口采样前执行，失败即停。本次入口修订没有运行任何新模型样本或Judge。
