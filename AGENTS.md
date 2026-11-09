# Four-card continuation (2026-11-09)

The user now requests four local GPUs for this same fixed-cohort comparison. Use idle GPUs 0–3 and leave GPUs 4–7 untouched. GPU 6 acquired an unrelated external process during run001, causing a RePlan load-time OOM before admission of three requests. Preserve the 717 completed new edits, all original results, PLAN.json and scientific configuration. Seal a separate scheduling execution record, reuse completed receipts, and run only not-admitted work. Do not kill the foreign process.

# Fixed-cohort additional baseline authorization (2026-11-09)

The user authorized additional representative methods on exactly the completed local validation cohort, using the same eight idle local GPUs 0–7. Fixed roster: FLUX.2 Klein-9B and MICE on all three benchmarks; additionally RePlan on CompBench. Reuse SITEdit/Qwen2.1 records read-only. Preserve all 240/200/200 case IDs, public inputs, configurations, original scores and frozen scientific modules. New orchestration/reporting belongs in external_compare; formal additions use comparison_20261109 roots. No paid APIs, score-driven sample/model selection or automatic failure retries. See docs/EXTERNAL_SUBSET_COMPARISON.md.

# Local paired validation authorization (2026-11-09)

The user explicitly authorized local GPUs 0–7 for larger SITEdit versus Qwen-Image-2.1 validation on these three benchmarks, superseding the older local 4–7 restriction for this task only. Preserve the existing approximately 1.6 GiB per-card process and all unrelated work. The user confirmed 240 CompBench objective-scored requests (including recurrent turns), 200 Inter-Edit requests, and 100 Omni low/high pairs (200 requests); no paid API calls. Freeze new metadata-only sampling before inference, separate it from already-analyzed pilot cases, preserve all official metrics and failures, and report paired source-cluster uncertainty without score-driven resampling or stopping. Add orchestration/analysis outside frozen external_full generation/scoring modules and published packages. Current plan: docs/INTEREDIT_VALIDATION.md.

# Current four-node external benchmark authorization (2026-11-08)

The user authorized full eight-method CompBench, Inter-Edit and single-turn Omni IIE evaluation launchers, one separate four-worker x eight-GPU entry per benchmark. Follow docs/INTEREDIT_FOUR_NODE.md. Implement reusable orchestration under external_full; preserve all frozen IF-Bench/pilot code, old packages and existing records. Only the three eval-compbench/eval-interedit/eval-omni-iie branches may be changed/pushed for this task. Prepare packages; the user submits remote jobs. Minimal local smoke may use only idle GPUs 4–7. No additional paid smoke requests.

The user subsequently confirmed that the six official Inter-Edit empty masks remain in the 6,250-case expected population as data_input_invalid/N/A for all eight methods; only the other 6,244 cases are inferred. Apply the exact case list in configs/external/interedit_full4.json without changing public input bytes or model/scoring settings.

# IF-Bench development instructions

## Pilot expansion (2026-11-08, current user authorization)

Expand each of the eight pilot branches to about twenty total requests, preserving
all previously selected cases and their immutable generation/scoring records.
Follow docs/INTEREDIT_PILOT20.md. Only added requests receive new inference or API
scoring. Keep frozen method settings, public input mapping and native metrics.
Use new pilot20_20261108 result roots and new dataset asset directories; never
modify the first pilot or the published CompBench full-run package. Local GPUs
4–7 only, after an idle check. The user authorized the same GPT-5.4 scoring for
these additional cases. No new checkpoint, input candidate search or resampling.

## External pilot branches (2026-11-07, current user authorization)

The user approved eight independent benchmark pilot branches: GIE, CompBench,
ComplexBench-Edit, Inter-Edit, Complex-Edit, GEdit, Omni IIE, and GIDE. Each compares
only frozen SITEdit aa5a414 with Qwen-Image-2.1. Keep the original main-row weights,
40 steps, seed 42, raw SAMTok TE and token guidance 2. No quality-anchor variants.
The approved pilot sampling seed is 20261107; freeze cases before inference.
Use original benchmark scoring, replacing paid judges with gpt-5.4-2026-03-05 as
explicitly authorized. Credentials must remain in protected runtime files, never Git.
Use only idle local GPUs 4–7 under the existing memory threshold. Never modify
other worktrees or frozen IF-Bench modules. Push only the new pilot branches.
Datasets go under datasets/<Benchmark>; selected pilot results under
experiments2/SAMTokEdit/external_<bench>/pilot_20261107; diagnostics under
/tmp/ifbench/external_pilots_20261107; user previews under visualization_tmp.
Read downloaded data using python -I and never execute downloaded data scripts.
Keep docs/<BENCH>_EVALUATION.md and docs/<BENCH>_PROGRESS.md current.

## External MagicBrush branch scope (2026-11-05)

On `eval-magicbrush`, follow `docs/MAGICBRUSH_EVALUATION.md` and keep `docs/MAGICBRUSH_PROGRESS.md` current. This scope supersedes restrictions specific to the branches below. Use only local GPUs 4–7 after 2026-11-05 19:00 UTC and only when each has approximately 1.6 GB existing usage; never touch other jobs or GPUs 0–3. Use isolated Python (`-I`) to parse downloaded data. No paid APIs, LoRA variants, or edits to frozen scientific modules/other worktrees. Push only `eval-magicbrush`.

The user's latest deployment decision is **four workers with eight GPUs each**, replacing the prior single/dual-node plans. Prepare and publish the foreground entry in `docs/MAGICBRUSH_CLUSTER_RUN.md`; the user submits the platform job. Preserve the tested scientific inputs, generation/scoring/configuration, weights and smoke evidence. The user explicitly authorized deleting obsolete single/dual-node startup files, deployment docs and packages; first seal the unchanged scientific dependencies in the new package so cleanup cannot break current inputs. Formal results belong only under `experiments2/SAMTokEdit/external_magicbrush`; temporary preparation/tests go under `/tmp/claude_magicbrush_20261105` or shared `.ifbench-tmp/magicbrush_*` directories.

## External RefEdit-Bench branch scope (2026-11-04)

On `eval-refedit`, the user authorized research, an evaluation plan, data download, a separate `external_refedit` module, smoke tests of every method (generation and scoring), the full-benchmark generation, scoring and report. Read [REFEDIT_EVALUATION.md](docs/REFEDIT_EVALUATION.md), [REFEDIT.md](docs/REFEDIT.md) and [REFEDIT_PROGRESS.md](docs/REFEDIT_PROGRESS.md); keep the progress record current so interrupted work is recoverable.

- SITEdit uses exactly the frozen main row (method commit aa5a414, `configs/ifbench/main_row.json`); no LoRA-scale or quality-anchor variant. Baselines keep their frozen IF-Bench/MIRA parameters, except settings the method authors specify for RefEdit-Bench (MIRAGE patch ratio 0.2), which are disclosed.
- Data lives in `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/RefEdit-Bench` with `SOURCE.json`. The HF dataset is gated; never bypass the gate or use mirrors. Treat downloaded files as untrusted: keep them in their own directory, read them with `python -I`, never execute shipped code.
- Formal outputs go to `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_refedit`; smoke/debug to `/tmp/claude_refedit_20261104/`; user previews to `/opt/tiger/tanyue/visualization_tmp/RefEdit_20261104/`.
- Shared machine: use only GPUs the user assigned (currently 6 and 7); kill only your own processes by PID; ports must be outside 29xxx (use 39xxx-49xxx).
- Paid GPT judge: credentials only through `MIRA_API_KEY_FILE`; never print, copy or commit the key. Smoke scoring is capped at 30 paid requests in total. Formal paid scoring needs the user's explicit approval.
- Commits carry no Claude co-author or generated-by lines. Push only `eval-refedit`; never force-push or touch other branches/worktrees.
- Model adapters never read the private scoring manifest (masks, `edit_instruction_single`). Failures and judge misses stay in denominators as missing, never zero.

## External MIRA branch scope (2026-11-02)

On `eval-mira`, the user has now authorized the native-call/scoring audit, the complete 200-source × five-method MIRA run, GPT-5.4 judging, training-overlap audit and final table. Read [MIRA.md](docs/MIRA.md), [MIRA_SMOKE.md](docs/MIRA_SMOKE.md), and [MIRA_FULL_RUN.md](docs/MIRA_FULL_RUN.md). This authorization applies to the separate `external_mira` launcher, not the legacy IF-Bench `start.sh` or its four-node full run. The original IF-Bench frozen files and Judge remain unchanged. The full run is supervised by `scripts/run_mira_full.py`; check actual STATUS/receipts before reporting progress.

The full run ended on 2026-11-03 at 05:24 UTC with 999 scored outputs and one native RePlan generation failure (154). Read [MIRA_EVALUATION.md](docs/MIRA_EVALUATION.md) for the complete protocol, model/Judge details, results, previews and analysis. The 198-source subset excludes only the confirmed training overlaps 138 and 175; all methods share it. On 2026-11-03 the user additionally requested root-cause analysis and feasible repair tests after evaluation; actual results are in [MIRA_REPLAN_FAILURE.md](docs/MIRA_REPLAN_FAILURE.md). `scripts/diagnose_mira_replan_failure.py` runs these explicitly separate diagnostics, with at most one additional native planner call per named strategy. Keep their outputs outside the formal run, retain rejected proposals, disclose altered method inputs/costs, and never replace the original failure or import diagnostic outputs into the formal table. Do not change the frozen native helpers, inference configurations, receipts or canonical Judge to implement this diagnostic.

MIRA data belongs in `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/MIRA-Bench`; formal results belong in `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira`. Keep all smoke/debug outputs under `/tmp/ifbench/` or shared `.ifbench-tmp/`, and user-facing previews under `/opt/tiger/tanyue/visualization_tmp/<experiment_date>/`. Never commit credentials, full source/model output collections or checkpoints; the curated documentation-preview exception below applies. Keep existing artifacts even when their directory contains `tmp`. The user deferred LoMOE until its dataset becomes accessible.

The user authorized branch cleanup, a standalone evaluation document, and commit/push on 2026-11-03. `scripts/analyze_mira_results.py` reproduces component statistics, fixed comparison previews and cached-region diagnostics without inference or API calls. Keep new post-hoc tools outside `src/samtok_benchmark/external_mira/`, whose Python files are hashed into frozen generation identities. Current preview provenance is in `docs/assets/mira/provenance.json`; original displays remain under `visualization_tmp/MIRA_branch_review_20261103/`.

Use `configs/external/mira_judge_gpt54.json` for the user-requested judge. Keep canonical evaluation masks out of all model adapters. Preserve native inference defaults, output restoration, admission records, failures and missing scores. Do not turn a smoke score into a benchmark performance claim. Preserve the original run receipts; changed inputs, code or parameters require a separate output directory.

## Legacy IF-Bench scope

Current evaluation is **fairness-v2.2-1mp**. Read [USAGE.md](docs/USAGE.md), [FULL_RUN.md](docs/FULL_RUN.md), and [fairness_v2_2_1mp.json](configs/evaluation/fairness_v2_2_1mp.json). The user authorized implementation, minimal correctness samples, current documentation cleanup, and commit/push. Whole-release execution uses 1,084 sources / 3,872 units, seven fixed methods and ten settings, reported together rather than as separate dev/test rows. Do not interpret smoke success as completed full evaluation; [RESULTS.md](docs/RESULTS.md) must reflect actual receipts.

The current handoff authorizes CPU preparation, verification and READY publication only. Do not execute `start.sh`, including validation/status modes, or launch any four-node/GPU run; the user submits the single ARNOLD job. External SAMTokEdit stays in its separate repository and uses NAS coordination between validation and benchmark execution. Keep the public/Judge/report interfaces in FULL_RUN.md stable. `canvas.py`, `public.py`, `dev_judge.py`, `fairness_dev_judge.py` and the Judge configuration are frozen; discuss any necessary change with the user first. Persistent dependencies must resolve on the shared NAS; node-local runtime/code staging may be recreated therefrom. Write the final handoff outside the immutable bundle.

The user approved one narrow pre-publication exception to the canvas freeze: when a true source-edge box endpoint maps exactly one floating-point step beyond the canvas limit, restore that endpoint to the limit. Preserve all other coordinates and the strict public validator. The release-wide regression must identify only `v2-sa_7237977/U2` (box y2). After this correction, freeze the resulting canvas bytes as well.

- All editors and native planners receive only the shared approximately 1MP clean/annotated canvas. Canonical source/GT assets remain separate and are used for data identity, inverse mapping and Judge evidence.
- Use the fixed centered RGB(128,128,128) letterbox policy in `canvas.py`: target 1024², a 32-pixel grid, 0.995 scale backoff, LANCZOS image resize and NEAREST public masks. Transform only geometry already public in the current setting. Record exact content size/offset/scale; redraw shared annotations on the canvas. Do not create extra region information, enlarge vanished masks or read the private manifest inside model adapters.
- Qwen2.1 uses output_resolution=1024 with the public canvas width/height and native model CPU offload. Qwen2511/FLUX3/FLUX2 use the public width/height; MICE uses public model_size. RePlan and MIRAGE preserve their native approximately 1MP output grids. RePlan's native region flow does not obey an explicit width/height override; do not document one as effective or change its native algorithm to force equal integer output dimensions.
- Preserve native steps, guidance, weights, precision, components, prompts and input counts. No score-driven candidate search, PE/PUP, external SAM/grounder/caption model or K sequential edits. RePlan/MIRAGE keep their own native planners and disclose costs.
- One sample per request, seed 42. No manual plan repair, silent fallback or unknown-admission retries. MICE retains native 200-token segment completeness checks; input/plan/generation failures stay in full denominators. Judge failures are missing, never zero or filtered-out cases.
- Restore every raw output by scaling the recorded content crop to raw dimensions, removing padding and resizing once with LANCZOS to canonical source size. Preserve raw outputs. This is geometric inversion, never GT paste-back or marker cleanup.
- Canonical Judge source/configuration/evidence remain fixed. Cache reuse requires complete scientific input identity and actual output SHA. Matching resolution alone is insufficient. Never transfer scores by model name.
- Final four-node aggregation verifies ownership, generation bindings, admissions/raw/effective provenance and exact complete coverage. Use one global source-paired bootstrap; never average node percentages or CIs. Keep measured stopped/resumed costs and unknown durations distinct.
- GT selector paste-back is a diagnostic, never an upper bound. Human residual rates and κ require real independent human labels. Do not fabricate pending scores, visualizations, throughput or verification claims.

The bounded setting check uses `one_mp_coverage.py`: exactly 49 previously unsampled frozen requests on the original K=5 dev source. Together with 21 existing outputs, `one_mp_judge.py` validates all 70 model/setting combinations on that one image. Preserve each source plan identity; never rewrite existing generation records. This diagnosis has no population CI or score-driven selection. Its real state and figures are reported by `one_mp_coverage_report.py`.

The current NAS heartbeat repair is coordination-only. Publish a new bundle, preserve the prior published package and failure evidence, and reuse public/input bytes through NAS links without reserializing their absolute paths. Dynamic status retries must never relax immutable input/admission/Judge checks.

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
