# IF-Bench development instructions

## Current scope

As of 2026-10-31 the user explicitly authorized the full 1,084-image release, seven confirmed methods and ten settings, reporting one total without separate dev/test score tables. The user confirmed four machines, each with eight H100 80GB GPUs and the same shared mount. This supersedes the previous stop-before-freeze/test gate for this fixed full-release run.

Read [USAGE.md](docs/USAGE.md), [FULL_RUN.md](docs/FULL_RUN.md) and the [approved configuration reference](configs/evaluation/fairness_v2_1.json) before changing inputs, parameters or scoring.

- Freeze the latest seven native configurations: Qwen2.1 2K/40 steps/CFG1/KV cache/native model CPU offload; MICE fixed short preamble and complete native 200-token segments. No new candidate search, score-driven changes or external components.
- Retain the original 108/976 split and dev20 membership only as exposure provenance. The full report includes all 1,084 sources and does not claim an unseen held-out test estimate.
- Use one ARNOLD job with four workers × eight GPUs and the same foreground entry on every worker. Read ARNOLD_ID and the common endpoint from ARNOLD_WORKER_HOSTS, never the worker-local generic PORT. Stage pinned benchmark and upstream source bytes in node-local /tmp. The supervisor owns TCP rendezvous, readiness/exit barriers and fatal-error propagation; node 0 alone aggregates, and all controllers wait for it.
- Four fixed, disjoint source owners, each 271 images and 968 units. A source's complete seven-model × ten-setting group stays on one node; each node has eight single-GPU generation workers and its own unchanged TP8 Judge. Cross-host control communication does not change inference to TP32 or add a multi-node NCCL model group.
- Reuse the completed repaired dev20 only after exact request/public/configuration/output and Judge-key verification. Preserve terminal native failures and historical costs; do not resample old failures or revive the old 177-repair authorization.
- Only public text/geometry reaches editors. No external SAM, grounder, caption rewrite, PE or PUP. Named methods RePlan/MIRAGE retain their own native planners; record actual calls. No K sequential edits.
- One sample per request, seed42. No unknown-admission retries, manual plan repair or silent fallback. Generation/planning/input-limit failures retain full denominators; Judge missing scores remain missing. MICE's 19 whole-release S2-point overflows follow the existing zero-sampling failure policy, not truncation or extra prompt revision.
- Final aggregation verifies all four owners and every unique canonical key, then computes one global source-paired bootstrap. Do not average node percentages/intervals or choose among duplicate scores.
- Paste-back remains a GT selector paste-back diagnostic, never an upper bound. Human residual-rate and κ require actual independent human review.

## Artifact placement and active runs

Code and protocol Markdown belong in this repository. Audit snapshots, smoke/dev outputs, logs, previews, reports and validation receipts belong under `/tmp/ifbench/` or `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/`. Only confirmed, frozen formal artifacts may enter `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/IF-Bench/`. This overrides the parent's visualization location for temporary IF-Bench material. Preserve unrelated experiments and historical records/costs.

The shared bundles `fairness-v2-dev20-20261030` (completed parent), `fairness-v21-dev20-20261030` (approved correction), and `full4-v21-1084-20261031` (superseded independent-node launcher) have immutable snapshots, manifests and requests. Use `full4-arnold-v21-1084-20261031-r2` for the common ARNOLD entry in [FULL_RUN.md](docs/FULL_RUN.md); its scientific requests reuse the previous full-input bundle exactly. Never rewrite old READY files or imply a running experiment adopted new checkout code. Keep the platform entry in the foreground, without `nohup` or `&`. Never kill unrelated GPU processes. A new attempt ID alone does not authorize repeating admitted requests.

Inspect actual records before reporting progress. Cached output is not new inference; generation success is not task success. Keep credentials, weights, full source datasets and raw experiment outputs out of Git. The user explicitly requested inline documentation examples: selected previews, their provenance and aggregate scores may be tracked under `docs/assets/`.

## Code and checks

- `src/samtok_benchmark/ifbench/`: public inputs, orchestration, workers, Judge integration and reports.
- `src/evaluation/protocol_audit/`: audited native helpers, bundle/bootstrap tools and historical analysis.
- `tests/test_ifbench_*.py`: CPU regression tests, without model downloads/inference.
- `docs/{CONSTRUCTION,USAGE,RESULTS}.md`: current guides; `docs/archive/previous/`: historical evidence; keep original protocols intact.

Run `python -m pytest -q` and Ruff on changed Python files. Keep GPU runtimes separate from the development environment. Do not change historical `src/samtok_benchmark/v2/judge.py` or scoring semantics as a scheduling fix.
Use English `<type>: <imperative subject>` commits as requested, following [CommitMessageGuidelines](https://github.com/MaiXiaochai/CommitMessageGuidelines).

## Collaboration and reporting

The user authorized CPU subagents for per-model inspection, analysis, summaries and thumbnails (at most three analysis agents concurrently), and a dedicated read-only dev20 monitor. Bound their I/O, keep outputs temporary, and do not let them change scores, select from incomplete results or interfere with GPU jobs. File monitoring alone does not deliver chat notifications; report observed changes and uncertainty explicitly.

Report completed work, problems/deviations, blockers and next steps. Use measured progress/ETA and Markdown with inline images for galleries. [Historical session notes](docs/archive/previous/protocol/if-bench-v1/archive/SESSION_HISTORY.md) preserve chronological evidence, not current permission state.
