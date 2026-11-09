# CompBench 小子集进度

2026-11-08 扩展完成：20 条 / 方法，40/40 输出和全部可运行指标评分完成。结果见 [COMPBENCH_PILOT20_RESULTS.md](COMPBENCH_PILOT20_RESULTS.md)，方案与恢复记录见 [COMPBENCH_PILOT20.md](COMPBENCH_PILOT20.md)。原小子集记录保留如下。

当前正在准备的 3,481 条全量评测见 [COMPBENCH_FULL_RUN.md](COMPBENCH_FULL_RUN.md)。以下仅为已完成的八条 pilot 记录。

2026-11-07：8 条 × 2 方法已全部生成和评分，16/16 成功。前两条完成端到端冒烟后复用，剩余六条各仅生成一次。CPU 合同测试通过，新增 Python 通过 Ruff；全部案例对照已经生成。

- 结果：[COMPBENCH_RESULTS.md](COMPBENCH_RESULTS.md)。
- 原始根：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/pilot_20261107`。
- 含全部图片的报告：`/opt/tiger/tanyue/visualization_tmp/CompBench_20261107/REPORT.md`。
- 用户确认：缺少官方可评分接口的 action/location/view 不纳入本轮，六类八条。
- 工程问题：评分依赖与本地 CLIP 权重路径已修复，无模型或指标变更，无失败请求重采样，无付费 API。


## 2026-11-08：八方法四机全量入口

当前部署见 [COMPBENCH_FOUR_NODE.md](COMPBENCH_FOUR_NODE.md)。新增统一 external_full 模块与独立四机脚本；原始 pilot、冻结主协议及正式记录均未修改。完成全量源数据核验、原生评分对照与八方法最小验证；本轮正式作业未启动。

## 2026-11-09 独立扩大样本验证

用户确认本机八卡，仅 SITEdit 与 Qwen-Image-2.1，采用官方客观指标。已冻结新样本并与旧 pilot 按源图分离，详见 [COMPBENCH_VALIDATION.md](COMPBENCH_VALIDATION.md)。不改四机包及已有结果。

## 2026-11-09 扩大样本验证完成

本轮固定新样本的两方法生成、官方客观评分、源图配对 bootstrap/置换检验及 53 项主比较 Holm 校正全部完成，生成/评分失败为 0，API 调用为 0。结果表、分析、数据路径、SHA256 和全部样例图入口见 [COMPBENCH_VALIDATION.md](COMPBENCH_VALIDATION.md)。三组 GPU 任务均已退出；未改四机包与此前结果。


## 2026-11-09：固定子集多方法比较完成

新增 FLUX.2 Klein-9B、MICE（全部三个子集）和 RePlan（CompBench），复用同一批 SITEdit/Base 输出。全部 2,800 张方法输出已有效计分，失败为 0；原结果、公开输入、配置与 native scorer 均未修改。按用户最新要求，剩余任务最多四卡续跑，CPU 评分并行。表格、分析、恢复记录与文件位置见 [EXTERNAL_SUBSET_RESULTS.md](EXTERNAL_SUBSET_RESULTS.md)；当前没有启动四机全量评测。
