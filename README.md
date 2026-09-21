# SAMTok Fine-Grained Interactive Edit Benchmark

656 cases in same-class multi-instance scenes: 532 CompBench, 24 HumanEdit, and 100 MIRAGE. Each case provides text, mask, box, and point settings. Evaluation covers Qwen-Image-Edit-2511, FLUX.2-klein-4B, Qwen-Image-2.1, and RePlan with the first two editors. Qwen3.8-27B scores edit completion, preservation, and visual quality from two outlined images.

- [Benchmark](BENCHMARK.md): construction, data schema, official model adapters, scoring rubric, environments, launch commands, and progress logs.
- [Experiments](MODEL_RESULTS.md): generation and scoring status, judge calibration, visual comparisons, and case studies.

## Repository layout

```text
selection/                 source selections and selection tools
benchmark/                 frozen manifest, statistics, validation, examples
build_unified_benchmark.py dataset construction
verify_source_masks.py     source mask verification
render_unified_examples.py dataset visualization
evaluation/                frozen model inputs, baseline inference, validation
evaluation/replan/         RePlan adapter, compatibility patch, case review
evaluation/metrics/        two-image judge, scheduling, statistics, publication
docs/assets/               figures used by the experiment record
docs/data/                 environment, progress, and calibration records
tests/                     data protocol, adapters, and scoring checks
```

Large datasets, model weights, and outputs live outside Git; their exact locations and use are documented in [BENCHMARK.md](BENCHMARK.md).
