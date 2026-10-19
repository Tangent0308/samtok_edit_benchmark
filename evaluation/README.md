# Evaluation

当前版本的模型生成、输入准备和 judge 代码集中在这里；结果不写回 `data/`。

## Layout

- `diffsynth/`: Qwen-Image-2.1、Qwen-Image-Edit-2511、FLUX.2-klein-4B 的 DiffSynth adapters，以及 FLUX.3 官方 reference adapter。
- `inputs/`: 三种区域输入的准备器；`inputs/pilots/` 只保存小批量对照实验脚本。
- `../samtok_benchmark/v2/`: 公共 job schema、prepare-judge、rubric、judge 和 report。
- `../results/`: 运行索引；大图、registry 和 judge records 保存在外部实验根目录。

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

# To run an already prepared input package:
SAMTOK_INPUTS=/path/to/grayscale_label_map_mixed \
  bash evaluation/diffsynth/run_all.sh gen qwen_image_21 0,1,2,3,4,5,6,7

bash evaluation/diffsynth/run_all.sh judge qwen_image_21 qwen_image_edit_2511 flux2_klein_4b flux3_klein
bash evaluation/diffsynth/run_all.sh report qwen_image_21
```

Use separate `SAMTOK_EXP` roots when comparing input modes. A model output generated with one
input digest must not be mixed into another mode's judge directory.
