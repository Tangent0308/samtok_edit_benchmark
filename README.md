# SAMTok Fine-Grained Interactive Edit Benchmark

A 556-case benchmark for referential, fine-grained image editing in
same-class multi-instance scenes. It contains 532 CompBench cases and 24
HumanEdit cases covering add, remove, and replace operations. ReShapeBench is
not included.

The benchmark compares text-only editing with mask-, box-, and point-guided
editing. For Qwen-Image-Edit-2511 and FLUX.2-klein-4B, each interactive setting
uses an ordered two-reference input:

```text
[clean source image, source image with a temporary locator]
```

The target reference and evaluation mask are evaluator-only and are never
passed to either model.

## Data

```text
Benchmark: /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark/
CompBench: /mnt/bn/strategy-mllm-train/user/tanyue/datasets/CompBench/
HumanEdit: /mnt/bn/strategy-mllm-train/user/tanyue/datasets/HumanEdit/
Results:   /mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/referential_finegrained_edit_benchmark_two_image_locator/
```

## Usage

```bash
cd /opt/tiger/tanyue/finegrained_edit_benchmark_selection

# Rebuild and validate the benchmark data.
CUDA_VISIBLE_DEVICES=0 python build_unified_benchmark.py
python verify_source_masks.py

# Render and freeze the baseline inputs.
/opt/tiger/tanyue/samtok_edit/.venv/bin/python \
  evaluation/prepare_inputs.py --resume

# Run Qwen and FLUX.2 on eight GPUs in the background.
tmux new-session -d -s samtok_baselines_two_image_556 \
  -c /opt/tiger/tanyue/finegrained_edit_benchmark_selection \
  'bash evaluation/launch_baseline_inference.sh'

# Show current progress or validate completed outputs.
python evaluation/report_baseline_progress.py
python evaluation/validate_baseline_outputs.py
```

No metric or judge is run by these commands. See [BENCHMARK.md](BENCHMARK.md)
for the complete Chinese construction and evaluation record.
