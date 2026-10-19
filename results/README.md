# Results and run registry

结果与大图不放进 Git 的正式数据目录；它们保存在：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/benchmark_v2_2.6.0_baselines/
```

## Current runs

- `mask_pilot/`: 12-case paired input experiment，包含 color locator 与 grayscale label-map 的 jobs、配对 summary 和可视化 gallery。
- `recommended_runs/qwen_image_21_mask/`: 1,084/1,084 generated，registry 1,084。
- `recommended_runs/qwen_image_edit_2511_mask/`: 1,084/1,084 generated，registry 1,084。
- `recommended_runs/flux2_klein_4b_mask/`: 1,084/1,084 generated，registry 1,084。
- `recommended_runs/flux3_klein_color/`: 1,084/1,084 generated，registry 1,084。
- `recommended_judge_inputs/`: 四模型完整 judge 输入已准备。
- `recommended_judge/`: Qwen3.8-Flash-Next-FP8 judge 正在按模型顺序生成 records；未全部完成前不发布全量分数。

## Reproduction metadata

- `recommended_run_plan.json`: 四模型与输入模式映射。
- `run_recommended_full.sh`: 顺序生成和 prepare-judge 脚本。
- `recommended_progress.sh`: 生成 registry、judge records 和进程状态。
- `RECOMMENDED_REEVAL_PLAN.md`: 运行命令和目录绑定。

## Interpretation boundary

`mask_pilot/paired_summary.md` 是输入形式诊断，不是 benchmark release score。正式报告应在四个 judge 目录都产生完整 `scores.jsonl` 后，再用 `report` 生成并另存；不要把 partial records 当成全量结果。
