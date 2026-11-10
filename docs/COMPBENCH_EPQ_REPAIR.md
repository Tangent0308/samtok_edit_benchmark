# CompBench 补充 E/P/Q：原答案格式恢复

2026-11-10 用户授权在本机修复失败项。本操作独立于冻结 Judge，不改变其输入、提示词、
模型、采样或已有记录，不重新调用 Judge，不重新生成编辑图片。

失败答案正常结束（`finish_reason=stop`），均已给出完整 E/P/Q。统一支持三种无损恢复：

1. 根对象结尾无值的空键 `,""` 或只有开引号的 `,"`：仅删除该无值语法。
   位置必须在根层级、字符串之外，并紧邻最后一个闭括号。
2. 完整 E/P/Q 对象之后再次出现标量摘要（例如 `"E":2`）：只在摘要与相应对象的
   `score` 严格同值、同为整数时去重；保留原完整对象及全部 evidence。
3. 额外 `E_note` / `P_note` / `Q_note` 字符串：保留到审计记录的辅助说明字段，
   标准评分对象仍逐字取自原答案；不据说明改分。

恢复后必须严格满足原 schema。相互冲突或多个完整评分对象、缺失评分、非整数、截断、
其他非白名单额外字段或歧义均拒绝恢复。所有方法应用同一规则，不按方法名或分数筛选；
证据文字、分数和原始答案均保持不变。

新增代码在 `src/samtok_benchmark/external_compbench/epq_repair/`。冻结的 `vlm_judge/`
代码、运行包 READY、官方 CompBench 客观结果和本轮原始 Judge 结果全部保留。
独立 overlay 记录每个原 admission/raw/effective 文件 SHA256、原失败原因、精确删除位置、
修复前后文本 digest、同值摘要和辅助说明、恢复得到的原有评分，以及解析器指纹。

正式运行完成后，以原始逐条记录重算原报告，要求所有原结果均可复现；再应用恢复层重算
全部 15 行、原场景聚类配对区间与方法差值。未受影响的行和共享抽样索引必须完全一致。
若仍有无法无歧义恢复的答案，保持缺分并报告，不自动补零或重判。

运行命令：

```bash
python -I scripts/compbench_epq_repair.py \
  --bundle /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/compbench_epq_20261110 \
  --original-root /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/supplementary_epq_20261110 \
  --source-report /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/supplementary_epq_20261110/reports/run001/REPORT.json \
  --output /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/supplementary_epq_20261110_repair1
```

CPU 环境需 NumPy 和 Pillow；不需要 CUDA。本次使用与正式 Judge 相同的独立 Python 运行时，
设置 `CUDA_VISIBLE_DEVICES=`，只执行解析、校验及 NumPy 统计。

## 完成结果

全量运行已完成 720 次调用。原结果为 713 条有效评分、7 条格式失败；本机离线恢复
7/7 成功，修复后 **720/720 有效、15/15 统计行完整**。没有新增 Judge 调用或 GPU 推理。

| 方法 | 恢复条数 | 修复后有效/总数 |
|---|---:|---:|
| SITEdit | 0 | 144/144 |
| Qwen-Image-2.1 | 6 | 144/144 |
| RePlan | 1 | 144/144 |
| MICE | 0 | 144/144 |
| FLUX.2 Klein-9B | 0 | 144/144 |

其中 5 条删除结尾无值空键（含 1 条仅有开引号），1 条去掉与完整评分对象同值的冗余
标量摘要，1 条把额外说明保留在审计字段。所有原有评分与证据未改写。

校验包括：原报告全部逐条记录及统计可精确复算；713 条原有效记录和 11 行未受影响
的统计完全一致；所有共享 bootstrap 索引一致；2,160 个原 admission/raw/effective 文件
逐个 SHA256 校验未变化。新增与既有补充 Judge 的 15 项合同测试通过，Ruff 通过。

- 修复后中文表格：`experiments2/SAMTokEdit/external_compbench/supplementary_epq_20261110_repair1/MERGED_REPORT.md`。
- 论文/分析读取的结构化补充结果：同目录 `MERGED_REPORT.json`。
- 独立恢复层：同目录 `OVERLAY.json`、`repairs/`。
- 原文件校验：同目录 `SOURCE_RECORDS.json`、`VERIFICATION.json`。
- 路径均相对于 `/mnt/bn/strategy-mllm-train/user/tanyue/`。

| 文件 | SHA256 |
|---|---|
| 修复后 MERGED_REPORT.json | `e018ce6735eb53d5ed688e02337b5a0d25159ee6cbb5ae9b79c064bd703ece0a` |
| 原始 REPORT.json（未修改） | `37b0c7a2f94a89b79ead82437eab70e4eef35fb876ebf6c6216c9113c8c77b7a` |
| 原 READY.json（未修改） | `a657ad9d522ddc2d55b695eb71c699248a25a3416de883efb50866f3afeb008e` |

该结果仍是补充自动诊断。格式恢复不纠正 Judge 的语义误判，也不替代 CompBench 官方客观指标。
