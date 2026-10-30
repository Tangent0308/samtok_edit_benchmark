# Evaluation

当前 IF-Bench fairness v2 / dev20：

- [各模型 × setting 的实际输入、原生流程和评分](../docs/protocol/if-bench-v1/CURRENT_EVALUATION_ZH.md)
- [8 卡前台启动与进度](../docs/protocol/if-bench-v1/DEV20_RUN_ZH.md)
- [运行模块](../samtok_benchmark/ifbench/README.md) · [审计/打包工具](protocol_audit/README.md)

以下为**历史 2.6.0 评测流程**，不作为 fairness v2 的默认入口。

历史 release 的模型生成、输入准备和 judge 代码集中在这里；结果不写回 `data/`。

## Layout

- `diffsynth/`: Qwen-Image-2.1、Qwen-Image-Edit-2511、FLUX.2-klein-4B、HiDream-O1-Image、Step1X-Edit 的 DiffSynth adapters；HunyuanImage-3.0-Instruct-Distil 和 LongCat-Image-Edit 使用各自官方本地推理 pipeline；FLUX.3 使用官方 reference adapter。
- `inputs/`: 三种区域输入的准备器；`inputs/pilots/` 只保存小批量对照实验脚本。
- `../samtok_benchmark/v2/`: 公共 job schema、prepare-judge、rubric、judge 和 report。
- `../results/`: 运行索引；大图、registry 和 judge records 保存在外部实验根目录。
- `analyze_results.py`: 从七个完整 report JSON 生成统计 CSV、英文坐标图和案例研究素材；发布报告位于 `../docs/reports/2.6.0/`。

## Input modes

默认 `visual_locator_v2/mixed`。要使用其他模式，先生成对应 jobs，再把 `SAMTOK_INPUTS` 指向该目录：

```bash
# Official visual locator: point/box/mask markers in a second image
PYTHONPATH=. /opt/tiger/envs/gen/bin/python -m samtok_benchmark.v2.cli prepare \
  --manifest data/v2_2.6.0/cases.jsonl \
  --dataset-root /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2 \
  --protocol visual_locator_v2 --variants mixed \
  --output /path/to/visual_locator_v2_mixed

# Native point/box/mask fields
PYTHONPATH=. /opt/tiger/envs/gen/bin/python -m samtok_benchmark.v2.cli prepare \
  --manifest data/v2_2.6.0/cases.jsonl \
  --dataset-root /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2 \
  --protocol native_regions_v2 --variants mixed \
  --output /path/to/native_regions_v2_mixed

# Full grayscale label-map ablation
PYTHONPATH=. /opt/tiger/envs/gen/bin/python evaluation/inputs/build_mask_label_map.py \
  --source-jobs /path/to/visual_locator_v2_mixed/jobs.jsonl \
  --manifest data/v2_2.6.0/cases.jsonl \
  --dataset-root /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2 \
  --output /path/to/grayscale_label_map_mixed
```

## Generation, judge and report

```bash
# Default setting; use eight visible GPUs.
bash evaluation/diffsynth/run_all.sh gen qwen_image_21 0,1,2,3,4,5,6,7
bash evaluation/diffsynth/run_all.sh gen qwen_image_edit_2511 0,1,2,3,4,5,6,7
bash evaluation/diffsynth/run_all.sh gen flux2_klein_4b 0,1,2,3,4,5,6,7
bash evaluation/diffsynth/run_all.sh gen flux3_klein 0,1,2,3,4,5,6,7
bash evaluation/diffsynth/run_all.sh gen hunyuan_image_30_instruct 0,1,2,3,4,5,6,7
bash evaluation/diffsynth/run_all.sh gen hidream_o1_image 0,1,2,3,4,5,6,7
bash evaluation/diffsynth/run_all.sh gen step1x_edit 0,1,2,3,4,5,6,7
bash evaluation/diffsynth/run_all.sh gen longcat_image_edit 0,1,2,3,4,5,6,7

# To run an already prepared input package:
SAMTOK_INPUTS=/path/to/grayscale_label_map_mixed \
  bash evaluation/diffsynth/run_all.sh gen qwen_image_21 0,1,2,3,4,5,6,7

bash evaluation/diffsynth/run_all.sh judge qwen_image_21 qwen_image_edit_2511 flux2_klein_4b flux3_klein \
  hunyuan_image_30_instruct hidream_o1_image step1x_edit longcat_image_edit
bash evaluation/diffsynth/run_all.sh report qwen_image_21
```

Use separate `SAMTOK_EXP` roots when comparing input modes. A model output generated with one
input digest must not be mixed into another mode's judge directory.

## Newly added model adapters

The default visual-locator protocol remains unchanged. Models with an official multi-image
editing interface receive the clean source image first and the locator image second:

- `hunyuan_image_30_instruct`
- `hidream_o1_image`

Models whose official editor accepts one image receive the locator image itself when a locator
exists; the prompt explicitly says that markers are spatial selectors and must not be copied:

- `step1x_edit`
- `longcat_image_edit`

This is recorded in each run's `config.json` and must not be mixed across input protocols. The
Hunyuan adapter uses `tencent/HunyuanImage-3.0-Instruct-Distil` (the full
`HunyuanImage-3.0-Instruct` checkpoint can be selected with the model-root override), the HiDream adapter uses
`HiDream-ai/HiDream-O1-Image`, Step1X uses the official DiffSynth `FluxImagePipeline` path, and
LongCat uses the official `LongCatImageEditPipeline`. Put local model directories under
`SAMTOK_MODEL_ROOT` using the names in `evaluation/diffsynth/adapters.py`, or edit the path
through a separate run configuration before starting generation.
For a model stored outside the shared model root, set a model-specific override such as
`SAMTOK_LONGCAT_IMAGE_EDIT_ROOT=/tmp/LongCat-Image-Edit`.

HunyuanImage-3.0-Instruct-Distil is an 80B MoE model. Its official `device_map="auto"` loader needs
all visible GPUs in one process; `run_sharded.py` therefore creates one multi-GPU worker for this
model instead of launching one worker per GPU. The other three selected models use independent
workers and can be sharded across the eight GPUs.

### Actual input setting and integration status

For `visual_locator_v2/mixed`, point, box and mask retain their original
per-unit forms. They are not converted to masks.

| Models | Images actually passed to the editor |
|---|---|
| Qwen-Image-2.1, Qwen-Image-Edit-2511, FLUX.2, FLUX.3, HiDream-O1, HunyuanImage | Clean source first; source with colored point/box/mask and U labels second |
| Step1X-Edit, LongCat-Image-Edit | Only the source with colored point/box/mask and U labels |

The single-image adapters consume the second image of the public job as their
sole image argument. The public job still lists both images for traceability;
that list is not evidence that both reached the model. Report this as a
single-image setting, separately from the two-image setting.

As of 2026-10-22, LongCat, Step1X and corrected HiDream have complete
1084-case generation and judging, alongside the four existing models.
Hunyuan Distil only completed a quick check with a **64-token reasoning cap**.
This is not a validated full-evaluation configuration. Its default reasoning
budget has been restored to 2048; full generation awaits validation with that
budget. The adapter currently uses an explicit aspect-preserving HxW target
instead of automatic ratio-token generation. Both deviations and the exact
checkpoint must be recorded when interpreting its quick-check outputs.

During generation, `shards/*/images/*.png` provides an approximate live
completion count. Each shard's registry is written when the worker exits;
only complete, successful registries establish generation completion.
The queued generation/judge workflow and its logs are stored in the experiment
root under `launch/selected_models_20261020/`.


### HiDream resolution correction (2026-10-21)

The original 1 MP HiDream run suffers severe generation degradation. Three
controlled cases reproduced the frozen PNGs byte for byte; changing only the
generation resolution to the original HiDream repository's approximately 4 MP
buckets removed the severe noise. The default adapter now uses
`resolution_policy=hidream_official_2k_buckets_v1`. Inputs remain clean source +
mixed point/box/mask locator image. Legacy configs without this field retain
the old behavior for reproducibility. Use a **new run directory** for corrected
generation and a new judge run; the historical scores are not corrected scores.
See [diagnosis and before/after images](../docs/reports/2.6.0/HIDREAM_NOISE_DIAGNOSIS_2_6_0_ZH.md).

The corrected 1084-case generation and judge run completed on 2026-10-21
at 16:30:45 UTC using GPUs 0–7. All 1084 scores are valid; JointPass is
13/1084 (1.20%). The canonical `runs/hidream_o1_image/` and
`judge/hidream_o1_image/Qwen3.8-Flash-Next-FP8/` now contain these corrected
results. Read recorded progress from the repository root with:

```bash
/opt/tiger/envs/gen/bin/python evaluation/hidream_progress.py
```

`evaluation/rerun_hidream_2k.py` resumes generation, prepares fresh judge
evidence, retries missing judge records, then requires a complete report.
The cleanup audit, live status, logs and retired metadata live under the
experiment root's `launch/hidream_2k_20261021/` directory.

Environment snapshots, temporary input recovery, exact model revisions and storage locations:
[recovery handoff](../docs/RECOVERY_HANDOFF_2_6_0_ZH.md).
