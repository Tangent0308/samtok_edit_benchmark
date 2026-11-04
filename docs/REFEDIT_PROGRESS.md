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

## 待办

1. 数据访问获批后：下载、校验、写 `SOURCE.json`，准备 bundle。
2. 实现与 CPU 测试：数据/bundle、适配器、worker、评分（官方 VIEScore、GPT-5.4、本地 Judge）、报告、重合审计、ARNOLD 入口。
3. smoke：每方法 2–3 case 生成 + 评分（付费请求总数 ≤ 30），记录每 case 墙钟与峰值显存。
4. 用实测时间估算正式运行；≤ 约 3 h 则在 GPU 6–7 直接运行，否则交付 8 GPU ARNOLD 入口并在本机伪造变量做入口 smoke。
