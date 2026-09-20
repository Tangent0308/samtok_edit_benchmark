# SAMTok Fine-Grained Interactive Edit Benchmark

656 cases in same-class multi-instance scenes: 532 CompBench, 24 HumanEdit, and 100 MIRAGE. Each case provides text-only, mask, box, and point settings. The frozen protocol sends a clean source image to the editor; an interactive setting also provides an annotated locator image to a model or to RePlan's planner. Reference targets and evaluation masks are reserved for inspection.

- [Benchmark construction and usage](BENCHMARK.md): selection, schema, masks, frozen inputs, and rebuild commands.
- [Model evaluation and results](MODEL_RESULTS.md): official pipeline calls, checkpoints, launch commands, completed runs, visual results, and manual findings for Qwen-Image-Edit-2511, FLUX.2-klein-4B, and RePlan with each editor.

## Repository layout

```text
selection/                 reviewed CompBench, HumanEdit, and MIRAGE selections
benchmark/                 frozen manifest, statistics, and build validation
build_unified_benchmark.py construct the unified data
verify_source_masks.py     compare materialized regions with source annotations
evaluation/common.py       four-setting frozen input protocol and shared checks
evaluation/prepare_inputs.py
evaluation/run_inference.py                Qwen / FLUX.2 DiffSynth adapter
evaluation/launch_baseline_inference.sh    eight-GPU baseline controller
evaluation/replan/                       RePlan adapter, controller, validation, gallery
tests/                      protocol and adapter tests
```

## Quick start

```bash
cd /opt/tiger/tanyue/samtok_edit_benchmark
BASELINE_PY=/opt/tiger/tanyue/samtok_edit_eval_stage2/.venv/bin/python
REPLAN_PY=/opt/tiger/tanyue/RePlan/.venv/bin/python

"$BASELINE_PY" evaluation/prepare_inputs.py --resume
"$BASELINE_PY" evaluation/run_inference.py --model qwen --dry_run > /tmp/samtok_qwen_preflight.json
"$BASELINE_PY" evaluation/run_inference.py --model flux2 --dry_run > /tmp/samtok_flux_preflight.json
"$REPLAN_PY" evaluation/replan/runner.py --model qwen2511 --dry-run
"$REPLAN_PY" evaluation/replan/runner.py --model flux2_klein4b --dry-run
```

Full inference, eight-GPU launch commands, and progress logs are documented in [MODEL_RESULTS.md](MODEL_RESULTS.md). The completed RePlan run has 5,248 structurally validated outputs; bare Qwen and FLUX.2 have a validated 15-case run on the current 656-case prompt protocol, plus an archived 556-case run on an earlier protocol. No quality score or judge has been computed.
