# CompBench 评测进度

2026-11-08 扩展完成：20 条 / 方法，40/40 输出和全部可运行指标评分完成。结果见 [COMPBENCH_PILOT20_RESULTS.md](COMPBENCH_PILOT20_RESULTS.md)，方案与恢复记录见 [COMPBENCH_PILOT20.md](COMPBENCH_PILOT20.md)。原小子集记录保留如下。

3,481 条全量五方法结果见 [COMPBENCH_FULL_RESULTS.md](COMPBENCH_FULL_RESULTS.md)。以下保留此前 pilot 和部署记录。

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


## 2026-11-09：五方法全量四机入口

沿用 240 条子集的 SITEdit、Qwen-Image-2.1、RePlan、MICE、FLUX.2 Klein-9B，准备 4 worker × 8 H100 的完整 3,481 条评测。新入口、预算和续跑方式见 [COMPBENCH_FOUR_NODE.md](COMPBENCH_FOUR_NODE.md)。16 项 CPU 测试通过，四个分片的全量 CPU 资产预检全部通过（871/870/870/870 条）；21 个冻结生成源码文件与子集相同。本次不启动 start.sh、GPU 或付费 API；用户提交正式作业。新包、结果根、代码发布 SHA 见 NAS 包外交接。旧包和全部原结果保留。

## 2026-11-10：五方法全量与 GPT 补判完成

四机 run001 于 11-09 21:39 UTC 完成，实际墙钟 5 小时 12 分钟。五方法各 3,481 张，17,405/17,405 生成成功；16,425/16,425 客观评分完成。原始 980 次 GPT 请求中 53 次被资源池以 429/-4302 拒绝，均没有答案文件。

用户于 11-10 明确授权补齐。独立补判层串行追加 59 次请求（53 个正常答案、6 次资源池拒绝），于 03:10 UTC 补齐 53/53；消息哈希与原 admission 完全一致。所有 17,352 条原有效逐图记录和 25 行客观分组结果保持不变，原始报告 SHA 未变化。合并复算、原始响应解析与身份绑定检查全部通过。

最终五方法表格、协议、完整覆盖率、分析、耗时、数据路径及复现信息见 [COMPBENCH_FULL_RESULTS.md](COMPBENCH_FULL_RESULTS.md)。正式补判与合并根为 `experiments2/SAMTokEdit/external_compbench/full5_20261109_vlm_rejudge_20261110`；原始运行包及正式记录保留，不重发 READY。
