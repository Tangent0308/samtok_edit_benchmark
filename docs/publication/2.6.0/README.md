# Benchmark 2.6.0 发布文档

- `SAMTOK_BENCHMARK_2_6_0_ZH.md`：完整介绍、设置、结果及案例；HiDream 已更新为约 4 MP 配置的 1,084 例完整重评，飞书同步状态见 `publication_status.json`。
- `../../reports/2.6.0/RESULT_ANALYSIS_2_6_0_ZH.md`：独立结果报告，直接嵌入全部图表和案例。
- `case_study_notes.json`：逐模型选例、可观察的失败原因和审查说明。
- `model_case_studies.json`：选例关联的原始输出路径、摘要和评分。
- `actual_input_evidence.json` / `actual_adapter_prompts.json`：单图输入尺寸与适配器 prompt 示例；FLUX.3 内部扩写文本未存档。
- `report_audit.json`：七模型的覆盖率及 job / output / score 摘要绑定核对。
- `publication_status.json` / `lark_image_blocks.json`：同步状态、远程 block 和图片 token。

## 重绘

从仓库根目录执行，Python 环境需包含 Pillow、NumPy、Matplotlib：

```bash
/opt/tiger/envs/gen/bin/python evaluation/analyze_results.py --tables-only
/opt/tiger/envs/gen/bin/python evaluation/render_model_case_studies.py
/opt/tiger/envs/gen/bin/python evaluation/render_current_report.py
```

在本机隔离绘图依赖位于 `/tmp/samtok_doc_deps` 时，可给上述命令设置 `PYTHONPATH=/tmp/samtok_doc_deps`。渲染只读取冻结生成结果和评分，不运行模型，也不改分数。完整运行 `analyze_results.py` 会按顺序调用两个渲染脚本。

`render_current_report.py` 同时生成供飞书局部替换的 `.seven-report.xml` 和 Markdown 片段；飞书写入、回读与本地全文同步单独执行，以保留用户在线修改。HunyuanImage 尚未纳入；HiDream 的当前结果使用官方约 4 MP 分桶，完整生成和评分均已完成。
