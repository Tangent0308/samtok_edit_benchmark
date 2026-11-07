# omni_iie 小子集进度

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
