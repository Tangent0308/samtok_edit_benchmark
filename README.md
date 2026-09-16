# SAMTok Fine-Grained Interactive Edit Benchmark

A 656-case benchmark for referential, fine-grained editing in same-class
multi-instance scenes: 532 CompBench, 24 HumanEdit, and 100 MIRAGE cases.
Each case contains one or two selected regions and supports text-only, mask,
box, and point inputs. ReShapeBench is not included.

For Qwen-Image-Edit-2511 and FLUX.2-klein-4B, an interactive setting uses the
models' supported multi-reference interface:

```text
[clean source image, source image with a temporary locator]
```

Target references and evaluation masks are evaluator-only and never enter the
model input. MIRAGE has no edited target reference, so its
`target.reference_image` is `null`.

## Data

```text
Unified benchmark: /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark/
CompBench raw:     /mnt/bn/strategy-mllm-train/user/tanyue/datasets/CompBench/
HumanEdit raw:     /mnt/bn/strategy-mllm-train/user/tanyue/datasets/HumanEdit/
MIRAGE raw:        /mnt/bn/strategy-mllm-train/user/tanyue/datasets/MIRAGE/benchmark/
Prepared inputs:   /mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/referential_finegrained_edit_benchmark_656_two_image_locator/
15-case results:   /mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/referential_finegrained_edit_benchmark_656_prompt_v2_smoke15/
```

## Usage

```bash
cd /opt/tiger/tanyue/finegrained_edit_benchmark_selection

# Recreate the reviewed MIRAGE five-to-one/two selection, then build and verify.
python selection/build_mirage_selection.py
CUDA_VISIBLE_DEVICES=0 python build_unified_benchmark.py
python verify_source_masks.py

# Render and freeze all four baseline settings for 656 cases.
/opt/tiger/tanyue/samtok_edit/.venv/bin/python \
  evaluation/prepare_inputs.py --resume

# Optional: run both baselines on eight GPUs.
tmux new-session -d -s samtok_baselines_656 \
  -c /opt/tiger/tanyue/finegrained_edit_benchmark_selection \
  'bash evaluation/launch_baseline_inference.sh'

python evaluation/report_baseline_progress.py
python evaluation/validate_baseline_outputs.py
```

The preparation and inference commands do not compute metrics or call a judge.
See [BENCHMARK.md](BENCHMARK.md) for the Chinese construction record, schema,
exact prompt-v2 input protocol, archived 556-case results, and the current
656-case 15-sample DiffSynth smoke test with visual comparisons.
