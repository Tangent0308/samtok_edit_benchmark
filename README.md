# SAMTok Edit Benchmark v2

多对象、逐对象混合交互的细粒度图像编辑评测集。当前指令发布版 **2.1.0**：212 张独立源图，540 个编辑单元，add / replace / remove / attribute 各 135 个（各 25%）。每图 2–4 个不同物体，至少两种交互形式；所有单元都必须通过目标选择与完整执行、非目标保持、编辑质量检查。

**唯一 benchmark 主文档：[SAMTok Benchmark v2](docs/BENCHMARK_V2_ZH.md)**。其中集中说明评测目标、源数据、逐图筛选、指令和区域构造、协议、统计、路径、可视化与复现方法。旧版本文档从当前分支移除，历史可从 Git 查询。

- [冻结任务](data/v2/cases.jsonl)、[统计](data/v2/statistics.json)、[指令修订记录](data/v2/instruction_revision.json)
- [来源审计](data/v2/audit/source_audit.json)、[训练排除清单](data/v2/holdout_source_ids.jsonl)
- [模型适配器](examples/v2_editor_adapter.py)、[开发约定](CONTRIBUTING.md)

ref 是文本指代。无 ref 必须有 point / box / mask；纯 ref 没有区域提示。同一物体的多个 mask 碎片仍算一个单元。当前 add 是在已有物体/部件上添加配件或物品，区域指定承载部位，详见主文档。

当前为 assistant 逐图审核的数据与任务发布，未声称独立人工认证，尚无正式 v2 模型成绩。

## 位置与审核包

| 内容 | 位置 |
|---|---|
| 唯一 v2 仓库 | `/opt/tiger/samtok_edit_benchmark_v2branch`，`v2branch` |
| 正式与过程数据 | `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2` |
| 当前审核工具 | `/opt/tiger/samtok_edit_benchmark_v2_review` |
| 审核压缩包 | `/opt/tiger/samtok_edit_benchmark_v2_review_20261010.zip` |

[下载当前审核包](https://huggingface.co/datasets/TTangenty/samtok_edit/resolve/main/samtok_edit_benchmark_v2_review_20261010.zip)；固定远端 revision 与校验值见 [发布记录](data/v2/review_package.json)。本轮替换远端同名文件，下载时应使用当前版本。

解压进入包目录运行：

```bash
python run_review.py
```

浏览器自动打开。左侧选择 case，每个对象显示简短英文指令和中文翻译，可分别切换不显示 / point / box / mask。支持任务类型筛选、缩放、备注、指令建议、保存与导出。服务器仅依赖 Python 3.10+ 标准库。审核记录与冻结任务分开；旧版本审核记录不能直接确认新指令。

## 开发与运行

```bash
python -m pip install -e '.[dev]'
ruff check src tests examples construction
pytest -q
```

正式图片和 mask 在数据根目录 `assets/`；标注在 `benchmark/`，仓库镜像在 `data/v2/`；候选与审核过程在 `construction/`；模型输入/输出在 `evaluation/`。完整运行命令见主文档，迁移目录后需重新生成运行输入。

`samtok-benchmark-v2` 为当前入口；原 v1 执行代码与冻结数据保留兼容，但其旧文档不再混入本分支的当前文档入口。
