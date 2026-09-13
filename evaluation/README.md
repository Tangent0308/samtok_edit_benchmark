# Benchmark inference

This directory implements the frozen 500-case inference protocol for
Qwen-Image-Edit-2511, FLUX.2-klein-4B, and the refined four-node SAMTokEdit
checkpoint. Both base models are loaded through the vendored DiffSynth library
in `/opt/tiger/tanyue/samtok_edit/DiffSynth-Studio`.

## Output root

All materialized inputs, run configurations, per-image sidecars, generated
images, and logs live under:

```text
/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/finegrained_edit_benchmark/
```

The full generated benchmark outputs are intentionally kept outside Git. The
repository contains only a small representative all-setting gallery under
`docs/assets/benchmark_evaluation/` for documentation.

## Frozen settings

Qwen and FLUX each have five result rows: text-only, mask annotation, box
annotation, point annotation, and mask-annotation paste-back. A single target
uses an unnumbered red marker; multi-target inputs use red/green markers labeled
R1/R2 in benchmark region order. The paste-back
row is deterministically composited from the exact mask-annotation sample, so
it does not perform a second stochastic generation.

SAMTokEdit has five rows: online CoT with the original instruction, mask-token
UMT, box-to-SAM2-to-token UMT, point-to-SAM2-to-token UMT, and explicit
mask-token MT with the original instruction. Multi-region spans retain the
order of the benchmark `regions` array.

For add edits, the requested object is absent from the source image. A box or
point prompt can therefore make SAM2 select background rather than the future
placement extent. This is an intrinsic limitation of the protocol stated in
the benchmark plan, not corrected with a hidden GT fallback. The preparation
report records SAM2/input-mask IoU by edit type and every within-case token
collision so this effect can be reported separately.

All stochastic generations use the constant `seed = 0`. Qwen and SAMTokEdit
use 40 steps, CFG 4, `zero_cond_t=True`, and the Qwen 2511 DiffSynth edit path.
FLUX.2-klein-4B uses the official distilled DiffSynth path with 4 steps, CFG 1,
and embedded guidance 4. All models generate near one megapixel at the source
aspect ratio; saved results are resized back to the exact source dimensions.

`target.*` fields are evaluator-only and are never consumed by a model. The
evaluation mask is likewise hidden during generation, except in the explicitly
named oracle paste-back post-processing row.

## Model identities

```text
Qwen:
  /mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/Qwen-Image-Edit-2511

FLUX:
  black-forest-labs/FLUX.2-klein-4B@e7b7dc27f91deacad38e78976d1f2b499d76a294
  /mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/FLUX.2-klein-4B

SAMTokEdit Stage-1 TE LoRA:
  /mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/crispedit_refined_4node/crispedit-refined-4node-20260910-run2/stage1_te_lora/step-2648.safetensors

SAMTokEdit Stage-2 DiT LoRA:
  /mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/crispedit_refined_4node/crispedit-refined-4node-20260910-run2/stage2_dit_lora/step-5296.safetensors
```

`FLUX.2-dev` was the first choice, but its gated repository rejected the
configured Hugging Face account. The benchmark design allows either dev or
Klein, so the accessible official distilled edit checkpoint is pinned above.

## Run

Prepare all visual inputs, interactive SAM2 masks, and SAMTok spans:

```bash
cd /opt/tiger/tanyue/finegrained_edit_benchmark_selection
CUDA_VISIBLE_DEVICES=0 \
  /opt/tiger/tanyue/samtok_edit/.venv/bin/python \
  evaluation/prepare_inputs.py --resume
```

Validate a model configuration without loading weights:

```bash
/opt/tiger/tanyue/samtok_edit/.venv/bin/python \
  evaluation/run_inference.py --model qwen --dry_run
```

Run a one-case end-to-end smoke test before a large launch (replace `qwen` by
`flux2` or `samtok_edit` as needed):

```bash
CUDA_VISIBLE_DEVICES=0 \
  /opt/tiger/tanyue/samtok_edit/.venv/bin/python \
  evaluation/run_inference.py \
  --model qwen --settings all --max_samples 1 \
  --experiment_root \
  /mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/finegrained_edit_benchmark/smoke/qwen
```

Launch all three models over eight GPUs with resumable per-image outputs:

```bash
tmux new-session -d -s samtok_finegrained_benchmark \
  "cd /opt/tiger/tanyue/finegrained_edit_benchmark_selection && \
  bash evaluation/launch_full_evaluation.sh > \
  /mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/finegrained_edit_benchmark/logs/controller.log 2>&1"
```

Monitor the detached run with:

```bash
cat /mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/finegrained_edit_benchmark/controller.status
tail -f /mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/finegrained_edit_benchmark/logs/controller.log
```

Each setting contains `0000.png`/`0000.json` pairs and a final
`results.jsonl`. Each model directory contains an immutable `run_config.json`
and a completion `report.json`. The controller status is recorded in
`controller.status`. After all models finish, `validate_outputs.py` verifies all
7,500 result image/sidecar pairs and writes
`reports/full_inference_report.json`.

Re-run the non-metric completeness and inference-protocol audits with:

```bash
/opt/tiger/tanyue/samtok_edit/.venv/bin/python \
  evaluation/validate_outputs.py

/opt/tiger/tanyue/samtok_edit/.venv/bin/python \
  evaluation/audit_inference_protocol.py
```

The completed run has 7,500/7,500 validated outputs. The protocol audit checks
the exact prompts, setting/input mapping, seed/rank provenance, checkpoint
hashes, SAMTok telemetry, and all 1,000 paste-back images pixel by pixel. It does
not compute a quality metric or call a judge. See
[`../BENCHMARK_CONSTRUCTION_AND_EVALUATION.md`](../BENCHMARK_CONSTRUCTION_AND_EVALUATION.md)
for the full construction, annotation, implementation audit, result paths, and
representative comparisons.
