# IF-Bench development instructions

## Current authorized scope

Current evaluation is **fairness-v2.2-1mp**. Read [USAGE.md](docs/USAGE.md), [FULL_RUN.md](docs/FULL_RUN.md), and [fairness_v2_2_1mp.json](configs/evaluation/fairness_v2_2_1mp.json). The user authorized implementation, minimal correctness samples, current documentation cleanup, and commit/push. Whole-release execution uses 1,084 sources / 3,872 units, seven fixed methods and ten settings, reported together rather than as separate dev/test rows. Do not interpret smoke success as completed full evaluation; [RESULTS.md](docs/RESULTS.md) must reflect actual receipts.

- All editors and native planners receive only the shared approximately 1MP clean/annotated canvas. Canonical source/GT assets remain separate and are used for data identity, inverse mapping and Judge evidence.
- Use the fixed centered RGB(128,128,128) letterbox policy in `canvas.py`: target 1024², a 32-pixel grid, 0.995 scale backoff, LANCZOS image resize and NEAREST public masks. Transform only geometry already public in the current setting. Record exact content size/offset/scale; redraw shared annotations on the canvas. Do not create extra region information, enlarge vanished masks or read the private manifest inside model adapters.
- Qwen2.1 uses output_resolution=1024 with the public canvas width/height and native model CPU offload. Qwen2511/FLUX3/FLUX2 use the public width/height; MICE uses public model_size. RePlan and MIRAGE preserve their native approximately 1MP output grids. RePlan's native region flow does not obey an explicit width/height override; do not document one as effective or change its native algorithm to force equal integer output dimensions.
- Preserve native steps, guidance, weights, precision, components, prompts and input counts. No score-driven candidate search, PE/PUP, external SAM/grounder/caption model or K sequential edits. RePlan/MIRAGE keep their own native planners and disclose costs.
- One sample per request, seed 42. No manual plan repair, silent fallback or unknown-admission retries. MICE retains native 200-token segment completeness checks; input/plan/generation failures stay in full denominators. Judge failures are missing, never zero or filtered-out cases.
- Restore every raw output by scaling the recorded content crop to raw dimensions, removing padding and resizing once with LANCZOS to canonical source size. Preserve raw outputs. This is geometric inversion, never GT paste-back or marker cleanup.
- Canonical Judge source/configuration/evidence remain fixed. Cache reuse requires complete scientific input identity and actual output SHA. Matching resolution alone is insufficient. Never transfer scores by model name.
- Final four-node aggregation verifies ownership, generation bindings, admissions/raw/effective provenance and exact complete coverage. Use one global source-paired bootstrap; never average node percentages or CIs. Keep measured stopped/resumed costs and unknown durations distinct.
- GT selector paste-back is a diagnostic, never an upper bound. Human residual rates and κ require real independent human labels. Do not fabricate pending scores, visualizations, throughput or verification claims.

## Artifacts and documentation

Code and current protocol documentation belong in this repository. Smoke outputs, audits, intermediate reports, previews and logs belong under `/tmp/ifbench/` or shared `.ifbench-tmp/`. Only the confirmed frozen full run's formal outputs enter `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/IF-Bench/`. Preserve unrelated experiments, raw evidence and actual compute costs. Never modify a published READY, frozen request, active run snapshot or original score record.

Repository documentation describes only the current evaluation setting. Data release 2.6.0 and its construction provenance are scientific data records, not evaluation-version prose. Preserve [CONSTRUCTION.md](docs/CONSTRUCTION.md), current manifest/patches and necessary authoring/audit/rebuild evidence. Before removing tracked non-current data or docs, inspect links and construction/test dependencies; relocate indispensable provenance and update executable references rather than silently breaking reconstruction. Keep full datasets, weights, credentials and model outputs outside Git. Current aggregate scores and a few actual image previews may be tracked with SHA provenance; insert real images directly in Markdown.

Use the foreground shared launcher; do not add `nohup`, `&` or a second `torchrun`. Never kill unrelated GPU processes. A new attempt ID is a logging identity, not resampling permission. Inspect actual result records before reporting progress: cached output is not new inference, and generated output is not task success.

## Source layout and checks

- `src/samtok_benchmark/ifbench/`: public inputs, canvas geometry, orchestration, workers, Judge integration and statistics.
- `src/evaluation/protocol_audit/`: pinned native helpers and runtime/bundle tools.
- `src/construction/` and `data/provenance/`: dataset construction and reproducibility evidence.
- `tests/test_ifbench_*.py`: CPU contract/regression tests without model downloads or inference.
- `docs/{CONSTRUCTION,USAGE,FULL_RUN,RESULTS}.md`: current user-facing documents.

Run appropriate CPU tests and Ruff on changed Python files; keep development and GPU runtimes separate. Do not change canonical Judge bytes or scoring semantics for a scheduling/packaging change. Use English `<type>: <Imperative subject>` commit messages. Check all current document links, current config references and data reconstruction dependencies before commit/push.

## Collaboration and reporting

CPU subagents may inspect methods, analyze completed outputs, draft reports and prepare thumbnails, with at most three analysis agents concurrently. Keep I/O bounded, artifacts temporary and running inference untouched. Do not select inputs based on incomplete results. Each report states work completed, issues/deviations, blockers and next steps, with real files/receipts. File monitoring alone does not deliver proactive chat updates.
