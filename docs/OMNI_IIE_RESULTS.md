# Omni IIE Bench 小子集结果

固定 8 条请求，两方法使用相同输入，每条 seed 42，仅生成一次。本页用于快速验证，不代表全量 benchmark 的排名。

| 方法 | 成功出图 | LPIPS ↓ | PSNR ↑ | SSIM ↑ | CLIP-I ↑ | FG LPIPS ↓ | FG CLIP-I ↑ | BG LPIPS ↓ | BG CLIP-I ↑ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SITEdit | 8/8 | 0.3236 | 17.7153 | 0.5446 | 0.9092 | 0.0962 | 0.9046 | 0.2495 | 0.9061 |
| Qwen-Image-2.1 | 8/8 | 0.3637 | 17.8766 | 0.5246 | 0.9366 | 0.0908 | 0.9294 | 0.2890 | 0.9358 |

| 方法 / 尺度 | LPIPS ↓ | PSNR ↑ | SSIM ↑ | CLIP-I ↑ | FG LPIPS ↓ | FG CLIP-I ↑ | BG LPIPS ↓ | BG CLIP-I ↑ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| sitedit / low | 0.3015 | 18.4468 | 0.5560 | 0.9489 | 0.0999 | 0.9271 | 0.2189 | 0.9484 |
| sitedit / high | 0.3456 | 16.9838 | 0.5332 | 0.8695 | 0.0901 | 0.8821 | 0.2776 | 0.8673 |
| qwen21 / low | 0.3339 | 18.8559 | 0.5377 | 0.9393 | 0.0859 | 0.9482 | 0.2616 | 0.9376 |
| qwen21 / high | 0.3936 | 16.8973 | 0.5116 | 0.9339 | 0.0987 | 0.9107 | 0.3140 | 0.9341 |

- 四个完整 high/low 配对，共 8 请求；区域 mask 与目标图均仅用于评分。
- 官方固定 768×768 评分，LPIPS-vgg、CLIP ViT-B/32。BG LPIPS/CLIP 和 FG LPIPS 按原生区域面积权重聚合，其余逐例平均。
- 官方 BG_CLIP_I 仅把背景 mask 写入 alpha，CLIPProcessor 转 RGB 后忽略 alpha；逐例与全图 CLIP-I 相同，汇总使用背景面积权重。保留原实现，不将它解释为独立的纯背景指标。
- QA 和 Overall 均 N/A：发布数据及官方可执行入口缺少 QA，用户已确认；不自行造题。

评分缺失不填零；若某项未覆盖全部请求，上表会标有效数/总数。生成成功只表示正常出图，不表示正确完成指令。

| 方法 | 平均编辑调用（秒） | 峰值 allocated（GiB） |
|---|---:|---:|
| sitedit | 48.68 | 38.23 |
| qwen21 | 41.57 | 19.13 |

编辑用时不含加载；SITEdit 的额外定位/codec 阶段与实际 API 用量在 REPORT.json 中逐项保留。

- 原始结果、输入、评分与报告：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_omni_iie/pilot_20261107`。
- 全部输入输出对比图：`/opt/tiger/tanyue/visualization_tmp/OmniIIEBench_20261107`。


## 观察与解释

- SITEdit 在 LPIPS、SSIM 和 BG LPIPS 上更好；base 在 PSNR、全图/前景 CLIP 等指标上更好。保持这组分项结果，不合成自定义总分。
- high/low 是四张相同源图的成对条件；每组只有四条，不能视为八个独立来源。
- QA 与 Overall 缺失意味着本轮只能评价与目标图的视觉一致性，不能把客观指标的改善直接等同于隐含意图理解正确率。
- BG_CLIP-I 的逐例遮罩无效已核验并披露；它与全图 CLIP-I 共用逐例值，仅汇总权重不同。
