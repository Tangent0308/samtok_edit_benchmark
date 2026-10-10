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

## 规范目录与审核包

唯一的本地 v2 Git 仓库：`/opt/tiger/samtok_edit_benchmark_v2branch`。
数据根目录：`/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2`。

| 位置 | 内容 |
|---|---|
| 本仓库 `data/v2/` | 冻结标注、来源、统计、审阅决定及检查摘要 |
| 数据根目录 `assets/` | 正式源图与原始 mask；不进入 Git |
| 数据根目录 `benchmark/` | 正式标注副本及完整审计 |
| 数据根目录 `construction/` | 候选池、逐图筛选、中间结果及日志 |
| 数据根目录 `evaluation/` | 两种协议的运行输入与验证产物 |
| `/opt/tiger/samtok_edit_benchmark_v2_review/` | 独立可下载审核工具，无 `.git` |

审核包已上传至 [Hugging Face 数据集 TTangenty/samtok_edit](https://huggingface.co/datasets/TTangenty/samtok_edit/resolve/e1179b57548c48e1e2090990a446c70b1717b9ca/samtok_edit_benchmark_v2_review_20261010.zip)，文件名 `samtok_edit_benchmark_v2_review_20261010.zip`，完整下载链接及 SHA256 见[构建报告](docs/V2_REPORT_ZH.md)。解压进入包目录，运行：

```bash
python run_review.py
```

浏览器自动打开。左侧选择 case 后加载对应图片，每个 object 可单独切换不显示、point、box、mask；支持多对象混合显示、恢复正式输入、缩放、审核决定、对象备注及指令修改建议。记录保存在包内 `reviews/review_results.json`，导出不修改冻结标注。只需 Python 标准库和现代浏览器。

## 安装与验证

```bash
python -m pip install -e '.[dev]'
BENCH_DATA=/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2
samtok-benchmark-v2 validate --manifest "$BENCH_DATA/benchmark/cases.jsonl" \
  --dataset-root "$BENCH_DATA" --minimum-cases 200 --output outputs/v2_validation.json
samtok-benchmark-v2 prepare --manifest "$BENCH_DATA/benchmark/cases.jsonl" \
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
