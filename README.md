# SAMTok Edit Benchmark v2

多对象、逐对象混合交互的细粒度图像编辑评测集。当前 `v2branch` 冻结 **212 张新源图、540 个不同物体目标**：每条 2–4 个对象，分别使用 point / box / mask / 文本 ref 的不同组合；正确完整编辑、非目标保持和编辑质量必须对所有目标同时成立。

| 构成 | 数量 |
|---|---:|
| PACO-LVIS / ADE20K-Part-234 | 119 / 93 条 |
| 2 / 3 / 4 对象 | 115 / 78 / 19 条 |
| 颜色 / 材质 / 移除 / 替换 | 420 / 40 / 40 / 40 个单元 |
| 实际逐图查看 / 最终保留 | 288 / 212 张 |

每条使用至少两种交互形式。ref 指文本 referring expression。无 ref 的单元必须给点、框或 mask；纯 ref 单元不获得任何几何提示。一个物体的多个可见碎片仍计为一个对象。

- [中文构建结果、难点分布、审阅过程与使用说明](docs/V2_REPORT_ZH.md)
- [数据格式、公开模型输入与严格计分契约](docs/V2_SCHEMA.md)
- [冻结任务](data/v2/cases.jsonl)、[统计](data/v2/statistics.json)、[来源审计](data/v2/audit/source_audit.json)
- [训练扩充排除清单](data/v2/holdout_source_ids.jsonl)
- [模型适配器入口](examples/v2_editor_adapter.py)、[开发约定](CONTRIBUTING.md)

本轮是 assistant 逐图源数据审核，已保留原始及二次筛选记录；未声称独立人工审核，也未运行 v2 正式模型对比实验。测试中的 identity 输出只验证管线。

## 本机产物

全部本轮产物位于 `/opt/tiger/SAMTok_Benchmark_v2/`，其中 `code/` 为本仓库，`dataset/index.html` 为全部 case 的离线查看页，`construction_workspace/` 保留候选及筛选证据。完整图片在仓库外，Git 保存代码、文档、冻结元数据和少量代表性图片。

浏览远程产物时，下载 `SAMTok_Benchmark_v2_浏览包.zip`，解压后用浏览器打开 `dataset/index.html`。保留完整目录，图片使用相对路径；不需要 VS Code 的 HTML 预览插件。

## 安装与验证

```bash
python -m pip install -e '.[dev]'
BENCH_DATA=/opt/tiger/SAMTok_Benchmark_v2/dataset
samtok-benchmark-v2 validate --manifest "$BENCH_DATA/cases.jsonl" \
  --dataset-root "$BENCH_DATA" --minimum-cases 200 --output outputs/v2_validation.json
samtok-benchmark-v2 prepare --manifest "$BENCH_DATA/cases.jsonl" \
  --dataset-root "$BENCH_DATA" --protocol visual_locator_v2 --output outputs/v2_inputs
ruff check src tests examples construction
pytest -q
```

数据复制到新路径后重新生成 inputs。`native_regions_v2` 使用原生逐单元区域；与视觉标记协议分别评测。运行模型、准备逐目标评审和汇总严格成功率的完整命令见中文报告。

## 冻结的 v1

v1 原始数据、执行入口和结果保持可复现；`samtok-benchmark` 仍为 v1，`samtok-benchmark-v2` 为 v2。本轮没有从 v1 的 450 条正式任务或 433 条扩充任务重组源图。

- [v1 报告与已有实验](docs/V1_REPORT.md)
- [v1 原 README](docs/V1_LEGACY_README.md)
- [v1 数据协议](docs/DATASET.md)及[评估协议](docs/EVALUATION.md)
