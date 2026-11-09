# omni_iie 小子集进度

2026-11-08 扩展完成：20 条 / 方法，40/40 输出和全部可运行指标评分完成。结果见 [OMNI_IIE_PILOT20_RESULTS.md](OMNI_IIE_PILOT20_RESULTS.md)，方案与恢复记录见 [OMNI_IIE_PILOT20.md](OMNI_IIE_PILOT20.md)。原小子集记录保留如下。

更新：2026-11-07T11:31:44.284669+00:00

- 分支：`eval-omni-iie`。
- 固定请求：8；bundle digest `19013aecff152d88f21158e9bdb60df01e2339af18711d53c4bc17556866e468`。
- 结果根：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_omni_iie/pilot_20261107`。

| 方法 | 成功生成 | 失败生成 | 客观评分完成 | API 综合评分完成 |
|---|---:|---:|---:|---:|
| sitedit | 8/8 | 0 | 8 | 0 |
| qwen21 | 8/8 | 0 | 8 | 0 |

API 原始答案文件：0；异常文件：0。

全部当前指标已汇总，见 [OMNI_IIE_RESULTS.md](OMNI_IIE_RESULTS.md) 和 `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_omni_iie/pilot_20261107/report/REPORT.json`。
结果仅适用于生成前固定的小子集；不据此宣布全量排名。逐条输入输出图与评分原文均保留。

恢复时先核对 result/ADMITTED 收据与配置身份。仅使用闲置 GPU 4–7；CPU/API 评分独立进行。未知受理不重试，不猜分，不改官方评分定义。
固定配置：SITEdit aa5a414 / Pass1 step2000 / S2 adapter16000 / raw TE / γ2 / 40步 / seed42；Qwen-Image-2.1 40步 / CFG1 / seed42。


## 2026-11-08：八方法四机全量入口

当前部署见 [OMNI_IIE_FOUR_NODE.md](OMNI_IIE_FOUR_NODE.md)。新增统一 external_full 模块与独立四机脚本；原始 pilot、冻结主协议及正式记录均未修改。完成全量源数据核验、原生评分对照与八方法最小验证；本轮正式作业未启动。

## 2026-11-09 独立扩大样本验证

用户确认本机八卡，仅 SITEdit 与 Qwen-Image-2.1，采用官方客观指标。已冻结新样本并与旧 pilot 按源图分离，详见 [OMNI_IIE_VALIDATION.md](OMNI_IIE_VALIDATION.md)。不改四机包及已有结果。

## 2026-11-09 扩大样本验证完成

本轮固定新样本的两方法生成、官方客观评分、源图配对 bootstrap/置换检验及 53 项主比较 Holm 校正全部完成，生成/评分失败为 0，API 调用为 0。结果表、分析、数据路径、SHA256 和全部样例图入口见 [OMNI_IIE_VALIDATION.md](OMNI_IIE_VALIDATION.md)。三组 GPU 任务均已退出；未改四机包与此前结果。
