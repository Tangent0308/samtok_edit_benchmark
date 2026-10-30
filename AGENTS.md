# IF-Bench development instructions

## Current scope

The active protocol is [fairness v2.1 / fixed dev20](docs/protocol/if-bench-v1/PROTOCOL.fairness-v2.1.dev20.md).
Read the [evaluation reference](docs/protocol/if-bench-v1/CURRENT_EVALUATION_ZH.md) before changing inputs, parameters or scoring.

- The user approved seven fixed configurations, twenty shared dev images and canonical judging. No new candidate search.
- The approved v2.1 corrections are Qwen2.1 at 2K and MICE's fixed short annotation preamble plus native 200-token completeness checks. Preserve native algorithms/defaults otherwise. Reuse exact terminal results including the historical MIRAGE failure; never reuse 1K outputs for 2K requests.
- Preserve the original 108-image dev pool and 976-image test split; the other 88 dev images do not become test.
- Stop after dev scores, failures and proposed formal configuration. Formal freeze/test requires the next user confirmation.
- MaskFlow and other methods without verified joint multi-target editing are excluded. Do not add K sequential edits.
- Only public text/geometry may reach editors. No external SAM, grounder, caption rewriter, PE or PUP. RePlan/MIRAGE retain their own named methods' planners and disclose actual calls.
- One sample per request, seed 42. No manual plan repair, unknown-attempt retry, output-driven prompt changes or silent fallback. Generation failures stay in the denominator; Judge failures remain missing. The old 13-key rejudge authorization is not a general retry policy.
- Paste-back is a **GT selector paste-back diagnostic**, never an upper bound. AI inspection does not replace independent human residual-rate or κ checks.

## Artifact placement and active runs

Code and protocol Markdown belong in this repository. Audit snapshots, smoke/dev outputs, logs, previews, reports and validation receipts belong under `/tmp/ifbench/` or `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/`. Only confirmed, frozen formal artifacts may enter `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/IF-Bench/`. This overrides the parent's visualization location for temporary IF-Bench material. Preserve unrelated experiments and historical records/costs.

The shared bundles `fairness-v2-dev20-20261030` (completed parent) and `fairness-v21-dev20-20261030` (approved correction) have immutable `repo/` snapshots, manifests and requests. Repository cleanup must not change published bundles or imply that a running experiment has adopted new checkout code. Use the foreground launcher in [DEV20_RUN_ZH.md](docs/protocol/if-bench-v1/DEV20_RUN_ZH.md), without `nohup` or `&`. Never kill unrelated GPU processes.

Inspect actual records before reporting progress. Cached output is not new inference; generation success is not task success. Keep credentials, weights, datasets and generated artifacts out of Git.

## Code and checks

- `samtok_benchmark/ifbench/`: public inputs, orchestration, workers, Judge integration and reports.
- `evaluation/protocol_audit/`: audited native helpers, bundle/bootstrap tools and historical analysis.
- `tests/test_ifbench_*.py`: CPU regression tests, without model downloads/inference.
- `docs/protocol/if-bench-v1/`: current reference plus clearly labeled historical evidence; keep original protocols intact.

Run `python -m pytest -q` and Ruff on changed Python files. Keep GPU runtimes separate from the development environment. Do not change historical `samtok_benchmark/v2/judge.py` or scoring semantics as a scheduling fix.
Use English `<type>: <imperative subject>` commits as requested, following [CommitMessageGuidelines](https://github.com/MaiXiaochai/CommitMessageGuidelines).

## Collaboration and reporting

The user authorized CPU subagents for per-model inspection, analysis, summaries and thumbnails (at most three analysis agents concurrently), and a dedicated read-only dev20 monitor. Bound their I/O, keep outputs temporary, and do not let them change scores, select from incomplete results or interfere with GPU jobs. File monitoring alone does not deliver chat notifications; report observed changes and uncertainty explicitly.

Report completed work, problems/deviations, blockers and next steps. Use measured progress/ETA and Markdown with inline images for galleries. [Historical session notes](docs/protocol/if-bench-v1/archive/SESSION_HISTORY.md) preserve chronological evidence, not current permission state.
