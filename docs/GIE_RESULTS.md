# GIE-Bench 小子集结果

固定 seed 20261107，每类 1 条，共 9 条；两模型同一子集，每条 seed 42，仅生成一次。Judge 为 GPT-5.4，保留官方题目、提示和精确匹配规则。这是快速验证，不代表全量表现。

| 方法 | 生成 | 问答正确率 ↑ | 区域外 CLIP ↑ | 区域外 SSIM ↑ | 官方脚本 MSE ↓ | 官方脚本 PSNR ↑ |
|---|---:|---:|---:|---:|---:|---:|
| SITEdit | 9/9 | 4/9 (44.44%) | 0.9868 | 0.9817 | 774.7253 | 20.3889 |
| Qwen-Image-2.1 | 9/9 | 5/9 (55.56%) | 0.9835 | 0.9404 | 1155.0131 | 18.8291 |

注意：官方数据 mask 为 0/1，但 MSE/PSNR 发布代码使用 `<128` 判区域外，因此其结果实际是配准后的全图误差。上表原样保留官方代码，不将这两列解释为背景保持。CLIP/SSIM 按正确的 0/1 mask 计算。各指标有效分母见 REPORT.json。

| 方法 | 平均编辑调用用时（秒） | 峰值 allocated 显存（GiB） |
|---|---:|---:|
| sitedit | 48.73 | 38.23 |
| qwen21 | 41.01 | 19.14 |

用时为真实记录的编辑调用时间，不含模型加载。SITEdit 的额外 Pass1 调用和完整阶段记录保留在 run/sitedit/tokens/。

## 逐例结果

| Case | 编辑类别 | SITEdit | 底座 |
|---|---|---:|---:|
| 0626 | Add Object | 1 | 1 |
| 0832 | Attribute Change | 0 | 1 |
| 0485 | Color Change | 1 | 1 |
| 0531 | Layout Modification | 0 | 0 |
| 0959 | Object Replacement | 1 | 1 |
| 0060 | Remove Object | 1 | 1 |
| 0344 | Scene/Background Change | 0 | 0 |
| 0749 | Size Change | 0 | 0 |
| 0732 | Textual Edit | 0 | 0 |

1 表示 GPT-5.4 选择的选项与官方答案完全相同；0 表示不同。不能将两个模型均生成成功等同于正确完成编辑。

## 文件与复现

- 原始结果与报告：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_gie/pilot_20261107`。
- 全部对比图：`/opt/tiger/tanyue/visualization_tmp/GIE-Bench_20261107`。
- 数据、代码、权重与输入配置详见 GIE_EVALUATION.md；分支 eval-gie。

