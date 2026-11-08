# interedit 小子集进度

2026-11-08 扩展完成：20 条 / 方法，40/40 输出和全部可运行指标评分完成。结果见 [INTEREDIT_PILOT20_RESULTS.md](INTEREDIT_PILOT20_RESULTS.md)，方案与恢复记录见 [INTEREDIT_PILOT20.md](INTEREDIT_PILOT20.md)。原小子集记录保留如下。

更新：2026-11-07T11:31:28.864821+00:00

- 分支：`eval-interedit`。
- 固定请求：8；bundle digest `f84fef3d3cda4770facba20631897c6300db49a47eb2f6c73ebd22ad3146660a`。
- 结果根：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_interedit/pilot_20261107`。

| 方法 | 成功生成 | 失败生成 | 客观评分完成 | API 综合评分完成 |
|---|---:|---:|---:|---:|
| sitedit | 8/8 | 0 | 8 | 0 |
| qwen21 | 8/8 | 0 | 8 | 0 |

API 原始答案文件：0；异常文件：0。

全部当前指标已汇总，见 [INTEREDIT_RESULTS.md](INTEREDIT_RESULTS.md) 和 `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_interedit/pilot_20261107/report/REPORT.json`。
结果仅适用于生成前固定的小子集；不据此宣布全量排名。逐条输入输出图与评分原文均保留。

恢复时先核对 result/ADMITTED 收据与配置身份。仅使用闲置 GPU 4–7；CPU/API 评分独立进行。未知受理不重试，不猜分，不改官方评分定义。
固定配置：SITEdit aa5a414 / Pass1 step2000 / S2 adapter16000 / raw TE / γ2 / 40步 / seed42；Qwen-Image-2.1 40步 / CFG1 / seed42。


## 2026-11-08：八方法四机全量入口

当前部署见 [INTEREDIT_FOUR_NODE.md](INTEREDIT_FOUR_NODE.md)。新增统一 external_full 模块与独立四机脚本；原始 pilot、冻结主协议及正式记录均未修改。完成全量源数据核验、原生评分对照与八方法最小验证；本轮正式作业未启动。6 个官方空 mask 的处理已获用户确认，保留为 data_input_invalid/N/A，见当前四机文档。


## 2026-11-08：确认空 mask 策略并发布

用户确认六个官方空 mask 对全部八方法一致记为 data_input_invalid/N/A。配置固定完整 6,250 条应评清单及 6,244 条推理请求，公开输入字节、模型设置和评分实现均不变。本轮仅执行 CPU 核验与 READY 发布，不启动正式作业。
