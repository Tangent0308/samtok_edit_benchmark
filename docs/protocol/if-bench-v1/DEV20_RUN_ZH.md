# 已确认公平方案：20张dev的8卡入口

用户已确认七模型固定输入方案，并将本轮dev从108张减为20张。名单从原108张开发池按K分层比例、seed=20261027及SHA256排序抽取，不读取分数或输出选择。K2/K3/K4/K5分别3/4/11/2张，共72个编辑目标；所有模型共用相同20张。其余88张仍留在开发池，原976张test不变。

## 启动

在能访问同一共享挂载的8卡机器上，直接把下列命令作为Merlin用户脚本：

```bash
bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v2-dev20-20261030/start.sh
```

入口在前台等待整个任务，不加`nohup`或`&`。运行环境需8张H100 80GB、每卡至少70GiB空闲，x86_64 Linux、glibc≥2.36及gcc/g++。入口先验证文件、设备和依赖，再运行；不会清理别人的GPU进程。无需重新下载权重或提供token。

生成与Judge分别使用已打包的原Python3.11/3.12及原依赖，避免跨环境污染。首次启动会在本机`/tmp/ifbench/fairness-dev20-runtime-20261030/`解包约24GB运行环境，请保留足够本地空间。源码、20图公共输入和原生规划器路径也通过已核验的别名安装；已有路径内容冲突时停止，不覆盖旧目录。

只检查启动环境而不运行评测：

```bash
bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v2-dev20-20261030/start.sh --validate-only
```

## 启动阶段与日志解读

新机器先逐项核验固定源码、公共输入与约 16 GB RePlan 权重；随后校验并解包约 10.49 GB 生成环境、约 13.50 GB Judge 环境，分别做 CPU import 检查。共享挂载吞吐会影响这一阶段，初次日志写入前可能较长时间静默；不能仅据空日志判断推理已开始或已失败。

只有出现 `Starting the foreground evaluation coordinator.`、`results/ACTIVE/owner.json` 和新 worker 状态，才确认进入执行。某模型全部命中缓存时可以完成但不加载 GPU 模型；`reused` 必须与新增出图分开统计。Judge 需等全部生成阶段结束。

启动包的 `repo/` 和 `code_manifest.json` 是本轮固定源码快照；远程 Git 更新不会热更新正在运行的包。不要为了使用新 checkout 重新覆盖已发布包、重算其 plan 或删除 started/ACTIVE 记录。

## 会执行什么

- 七模型×十setting×二十图，共1400个逻辑请求。Qwen两版各200个和FLUX3/RePlan各20个S1已有完全一致输出，共440个可精确复用；其余960个计划新生成。
- 逐模型执行，当前模型的请求分到8张卡独立处理；RePlan/MIRAGE先完成原生规划，再进入联合编辑。每个case一次采样、seed42，不增加候选或外接组件。
- 全部生成进程退出后切换到原8卡TP/EP Judge，batch16、4线程证据预取；内部按模型顺序评分。只在canonical指令/GT/输出SHA/Judge配置全部相同时复用旧评分。
- 报告真实失败；规划/生成失败保留分母，Judge失败保留缺分。仅按既有无歧义规则解析恢复，不自动补评、换seed或回退。
- 自动产出UP/JP、95% paired-bootstrap CI、派生指标、K桶、输入/输出图册和调用成本记录。20图只能描述这个小样本；人工κ、正式随机10例抽检与未执行诊断仍如实列待完成。
- 完成后写`REVIEW_REQUIRED.json`，按原约定停在正式freeze/test之前，不自动运行test。

已完成的请求通过绑定和SHA核验后跳过。若作业异常退出且有已提交无返回的请求，入口会拒绝自动重试，并保留ACTIVE、started和错误记录供核对；不要删除这些记录后强行重跑。

## 进度与报告

启动日志路径会打印在控制台；控制器每约30秒输出进度，估计只基于已有实测，不填虚构完成量。

- 共享进度：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v2-dev20-20261030/results/PROGRESS.md`
- 机器进度：同目录`progress.json`及`judge/progress.json`
- 每个worker日志：同目录`executions/<执行时间>/<模型-阶段>/worker-*.log`
- 汇总报告：同目录`report/REPORT.md`，直接插入输入/输出图
- 固定名单、请求与配置：启动包根的`selection.json`、`plan.json`、`requests/`

全部dev产物留在共享临时目录；正式`experiments2/IF-Bench/`仍只接收最终确认并冻结后的正式结果。用户已启动本次入口；入口运行与否、已完成数量及失败情况仍须从实际记录核对，不能把入口交付或缓存命中当作 960 个新生成和 Judge 已完成。

评测细节：[七模型 × 十 setting 的输入/流程/参数/评分](CURRENT_EVALUATION_ZH.md)。协议：[20图dev执行版](PROTOCOL.fairness-v2.dev20.md)。此前两图验证与旧dev候选结果保持原样，不套用为新配置成绩。
