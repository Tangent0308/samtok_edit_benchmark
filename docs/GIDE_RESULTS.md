# GIDE-Bench 小子集结果

固定 8 条请求，两方法使用相同输入，每条 seed 42，仅生成一次。本页用于快速验证，不代表全量 benchmark 的排名。

| 方法 | 成功出图 | 指令遵循 ↑ | 视觉自然度 ↑ |
|---|---:|---:|---:|
| SITEdit | 8/8 | 3.5000 | 3.1875 |
| Qwen-Image-2.1 | 8/8 | 4.0000 | 3.2500 |

- 公开 polygon 2、xywh box 2、text 4，共 8 条，覆盖六种编辑组合。
- SITEdit 通过原生 codec/box locator/文字定位处理公开区域；一次联合 Pass1、一次联合 S2。
- Judge 保留官方 evaluation 指令和两编辑评分规则，GPT-5.4 替代 GPT-5.1；两项范围均为 1–5。
- 原始 RGBA 另行保留；RGB 评分中的部分紫色背景来自原生预测的透明区域，没有回贴源图或补背景。该现象需与指令遵循得分一起分析。

评分缺失不填零；若某项未覆盖全部请求，上表会标有效数/总数。生成成功只表示正常出图，不表示正确完成指令。

| 方法 | 平均编辑调用（秒） | 峰值 allocated（GiB） |
|---|---:|---:|
| sitedit | 48.35 | 38.39 |
| qwen21 | 41.30 | 19.13 |

编辑用时不含加载；SITEdit 的额外定位/codec 阶段与实际 API 用量在 REPORT.json 中逐项保留。

- 原始结果、输入、评分与报告：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_gide/pilot_20261107`。
- 全部输入输出对比图：`/opt/tiger/tanyue/visualization_tmp/GIDE-Bench_20261107`。


## 按公开输入形式分组

| 输入 | 数量/方法 | 方法 | 指令遵循 ↑ | 视觉自然度 ↑ |
|---|---:|---|---:|---:|
| polygon | 2 | sitedit | 2.7500 | 2.2500 |
| polygon | 2 | qwen21 | 2.5000 | 1.7500 |
| box | 2 | sitedit | 3.5000 | 3.2500 |
| box | 2 | qwen21 | 4.0000 | 2.5000 |
| text | 4 | sitedit | 3.8750 | 3.6250 |
| text | 4 | qwen21 | 4.7500 | 4.3750 |

总体两项均为 base 较高；每个分组只有 2–4 个请求，不能据此得出稳定的形式排名。原始 RGBA 诊断显示 base 在四个 polygon/box 请求中预测了大面积透明区域，RGB 评分原样保留，SITEdit 在这些请求中未出现该现象；这与整体任务得分是不同层面的观察。

透明诊断：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_pilots_20261107/ALPHA_AUDIT.json`；标准为回源后超过 1% 像素的 alpha < 128。
