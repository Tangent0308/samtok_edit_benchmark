# complexbench_edit 小子集进度

2026-11-08 扩展完成：20 条 / 方法，40/40 输出和全部可运行指标评分完成。结果见 [COMPLEXBENCH_EDIT_PILOT20_RESULTS.md](COMPLEXBENCH_EDIT_PILOT20_RESULTS.md)，方案与恢复记录见 [COMPLEXBENCH_EDIT_PILOT20.md](COMPLEXBENCH_EDIT_PILOT20.md)。原小子集记录保留如下。

更新：2026-11-07T11:31:27.327013+00:00

- 分支：`eval-complexbench-edit`。
- 固定请求：10；bundle digest `9d599e2c80e828acb4a8bd0d2830e209c85e89ddb6da09e10297a7528eaca0da`。
- 结果根：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_complexbench_edit/pilot_20261107`。

| 方法 | 成功生成 | 失败生成 | 客观评分完成 | API 综合评分完成 |
|---|---:|---:|---:|---:|
| sitedit | 10/10 | 0 | 10 | 10 |
| qwen21 | 10/10 | 0 | 10 | 10 |

API 原始答案文件：60；异常文件：0。

全部当前指标已汇总，见 [COMPLEXBENCH_EDIT_RESULTS.md](COMPLEXBENCH_EDIT_RESULTS.md) 和 `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_complexbench_edit/pilot_20261107/report/REPORT.json`。
结果仅适用于生成前固定的小子集；不据此宣布全量排名。逐条输入输出图与评分原文均保留。

恢复时先核对 result/ADMITTED 收据与配置身份。仅使用闲置 GPU 4–7；CPU/API 评分独立进行。未知受理不重试，不猜分，不改官方评分定义。
固定配置：SITEdit aa5a414 / Pass1 step2000 / S2 adapter16000 / raw TE / γ2 / 40步 / seed42；Qwen-Image-2.1 40步 / CFG1 / seed42。
