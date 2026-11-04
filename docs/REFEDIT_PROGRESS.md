# RefEdit-Bench 进度记录

按时间追加；用于中断后恢复。时间为 UTC。协议与计划见 [REFEDIT_EVALUATION.md](REFEDIT_EVALUATION.md)。

## 2026-11-04

- **19:43** 开始。GPU 6、7 只有他人作业（PID 154280，约 1.6 GB/卡）；GPU 0–5 为主线程作业，不使用。
- **19:50–20:10** 调研：论文、项目页、官方仓库（固定 commit `3b4fb55`）、HF 数据卡。读取官方 `refedit.ipynb`、`sc_score.txt`、`pq_score.txt`、`evalaute_refedit_final.py`（只作文本阅读，未执行）。
- **20:05** **数据访问受阻**：`bpathir1/RefEdit-Bench`（revision `71fc847…`）为 `gated: auto`，无 token 下载 parquet 返回 HTTP 401；本机无 HF token，NAS 上无副本，作者未提供其他官方下载地址。按约束停止下载，已向协调方报告，等待用户提供已接受条款账号的 token 文件路径或手动放置 parquet。未使用第三方镜像。
- **20:20** 训练侧重合线索：`derived` 来源派生自 SAMTok 训练混合集，其 gRES 部分为 RefCOCO 的 COCO_train2014 图像（带文件名）；MIRA 审计已对同一组检查点的 646,908 个训练图像路径计算指纹，可直接复用。
- **20:35** 建立 worktree `/opt/tiger/tanyue/if-bench-refedit`，分支 `eval-refedit`，基于 `origin/eval-mira`（c6a6f6c）。
- **20:50** 外部检索：只有 MIRAGE（arXiv 2604.05180）报告 RefEdit-Bench，协议为 EditScore PF/Cons + GPT-5.1 PQ，合并 200 图；其固定源码 README 规定 RefEdit 用 patch ratio 0.2。
- **21:00** 写定评测计划（本分支 `docs/REFEDIT_EVALUATION.md`），随后开始实现 `external_refedit`。

- **21:00–21:10** 实现 `external_refedit`（数据/bundle、8 方法适配器、worker、launcher、官方 Modified VIEScore 评分、汇总）与 CPU 测试（33 项通过）。提交 `de78476`。
- **21:05** 训练侧重合审计（CPU，59 s）：MIRA 审计绑定的 10 个训练元数据文件 SHA 全部未变，复用其 646,908 个图像指纹；SAMTok 训练混合集中 gRES（RefCOCO）8,337 行 = 7,639 个 COCO train2014 图；经 derived 编辑 → 清洗清单 → 合板 `derived-*` 记录追踪，**3,249 个 COCO id 的 7,473 条记录进入 S2 实际训练行**，其中 819 个 id 也在 Pass1 step 2000 实际训练行；S1 行不含这些记录。产物：`.ifbench-tmp/external_bench_20261102/refedit_overlap_audit_20261104/`（`TRAINING.json`、`GRES_FINGERPRINTS.jsonl`、`COCO_TRAINING_USE.json`）。基准侧比对待数据。
- **21:15–21:57** 工程 dry run（**MIRA 图像各取第一项编辑，不是 RefEdit 数据**），GPU 6–7，8 方法 × 3 例全部生成成功（`/tmp/claude_refedit_20261104/dryrun_run1`）。每例墙钟中位数与峰值显存（allocated/reserved GiB）：

| 方法 | 每例墙钟（s） | 首次加载（s） | 峰值显存 |
|---|---:|---:|---:|
| SITEdit | Pass1 1.3 + S2 49.7 | 20 + 21 | 18.6 / 38.2（reserved 47.1） |
| Qwen-Image-2.1 | 39.3 | 8 | 19.1 |
| Qwen-Image-Edit-2511 | 74.2 | 24 | 57.9 |
| RePlan | 规划 2.3 + 编辑 97.5 | 135 + 934 | 15.9 / 57.9 |
| MIRAGE（patch 0.2） | 规划 5.3 + 编辑 66.5 | 351 + 709 | 18.0 / 57.9 |
| FLUX.3 Klein | 8.8 | 361 | 23.2 |
| MICE | 5.4 | 366 | 17.3 |
| FLUX.2 Klein-9B | 4.1 | 689 | 34.7 |

  加载时间是进程内 `build()` 的实测值，冷加载（NAS 首读、与主线作业共享 NAS）长达 6–16 分钟；同一权重已在页缓存时约 0.5 分钟（如 RePlan/MIRAGE 之后的 Qwen2511）。SITEdit 三例 Pass1 均无 fallback；区码插入规则命中 `attribute_method` 2 例、`replace_with` 1 例。
- **21:58 正式生成估算**：按上表中位数 × 200 例，纯生成 19.9 GPU·h；按 launcher 分片（目标 3,000 s/片，26 个加载、每次按 3 分钟计）约 22 GPU·h。GPU 6–7：约 10.5 h 墙钟；若 GPU 2–7 可用：约 3.7 h；单机 8 卡：约 2.9–3.3 h（冷加载更慢时偏上限）。超过“约 3 小时”阈值，**不在本机启动正式生成**，改为交付 ARNOLD 单机 8 卡入口（`scripts/arnold/`）。SITEdit 两个环境已打包到 NAS（`refedit_runtimes/env_v4.tar` 7.64 GB、`env_pass1.tar` 7.66 GB，描述符 SHA 写入 worker 脚本）。

- **22:02** 推送 `eval-refedit`。修正：MICE 原生注意力代码把调试图 `HARD_MASK_smoothpl.png` 写到当前目录，曾误入提交（推送前已删除）；launcher 现为每个任务设独立 scratch 工作目录。
- **22:05** ARNOLD 入口 smoke `entry_smoke_001`（伪造 `ARNOLD_*`，GPU 6–7）在 env_v4 解包时失败：安全检查沿已解出的绝对解释器链接解析了 `bin/python3 -> python`。改为纯词法检查（`e677c28`），失败尝试的日志与 `FAILED.json` 保留。
- **22:09** GPT-5.4 传输核验：dry run 的 SITEdit/005 发送 SC、PQ 各 1 次（付费请求累计 **2/30**），`temperature=0` 被接受，返回模型 `gpt-5.4-2026-03-05`、`finish_reason=stop`、官方 JSON（`[9, 9]`、`8`）。记录：`/tmp/claude_refedit_20261104/dryrun_scores_gpt54/`，ledger `/tmp/claude_refedit_20261104/PAID_LEDGER.jsonl`。
- **22:17–22:24** 入口 smoke `entry_smoke_002`（commit `e677c28`，从 GitHub 拉取固定 SHA 的 bootstrap）：run ID 认领 → 克隆并核对 HEAD → SITEdit 克隆 `aa5a414` → 212 个原生源码文件逐一核对 → 基线运行时归档核对与导入 → env_v4/env_pass1 从 NAS 归档解包，三个包均从核对过的克隆导入 → 节点本地配置 → GPU 显存检查 → 8 方法 × 1 例生成，**全部成功，退出码 0，约 7 分钟**。8 个方法的 raw 输出与本机运行时 dry run 的同一 case **逐字节相同**（SHA-256）。已用 run ID、`ARNOLD_WORKER_NUM=2`、缺 `ARNOLD_ID` 均在克隆前被拒绝。产物：`/tmp/claude_refedit_20261104/entry_root/`。
- **22:25** 向协调方报告速度估算、入口命令与阻塞，等待回复；数据未到位前正式生成无法启动。

## 待办

1. 数据访问获批后：下载、校验、写 `SOURCE.json`，准备 bundle。
2. 实现与 CPU 测试：数据/bundle、适配器、worker、评分（官方 VIEScore、GPT-5.4、本地 Judge）、报告、重合审计、ARNOLD 入口。
3. smoke：每方法 2–3 case 生成 + 评分（付费请求总数 ≤ 30），记录每 case 墙钟与峰值显存。
4. 用实测时间估算正式运行；≤ 约 3 h 则在 GPU 6–7 直接运行，否则交付 8 GPU ARNOLD 入口并在本机伪造变量做入口 smoke。
