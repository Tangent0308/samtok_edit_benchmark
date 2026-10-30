# Historical workflows — superseded for current dev20

This document preserves earlier commands and stage-local status. For the active fixed-method dev20 workflow, use [the current README](README.md). Do not launch these historical inference commands as part of dev20.

# IF-Bench tiered evaluation

This package implements the newly approved tiered protocol without changing the historical `v2` input or scoring semantics. Protocol documentation lives in [docs/protocol/if-bench-v1](../../docs/protocol/if-bench-v1/README.md).

The shared-input command implements milestone 1. It performs no image-editing inference or Judge calls. The smoke runners implement milestone 2 for all seven main-table methods, following approval of shared inputs.

```bash
python -m samtok_benchmark.ifbench \
  --manifest data/v2_2.6.0/cases.jsonl \
  --dataset-root /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2 \
  --output /tmp/ifbench/tiered_v1/shared_inputs_20261027 \
  --workers 8
```

The command creates the 108/976 source-family split, shared S4/S5 assignments, public requests for all dev cases and all 10 settings, deterministic annotations and region conversions, exact shared prompts, and a static gallery with 3 dev cases per setting. It reads test metadata only to freeze split membership and assignment tables; it never opens test image or mask assets. Previously viewed audit cases are forced into dev. The five-unit gallery case is selected by a fixed hash among dev cases with a ref-only S5 unit, without observing model outputs.

- `plan.py`: immutable split/assignment files, including their digests and exact hashing recipe.
- `public.py`: strict private-to-public projection. No downstream serializer receives the full annotated case.
- `geometry.py`: half-open pixel boxes, explicit normalized xyxy/yxyx conversions, 5% point boxes and mask conversion provenance.
- `render.py`: fixed font/colors/rounding, complete mask contours, public-geometry-only label placement.
- `inputs.py`: dual-image, single-image, coordinate-text forms and S2-only discard-region form. These are shared forms, not all automatically assigned as candidates to every model. A model's complete candidate configurations remain limited to 4.
- `preview.py`: full-size image links, exact shared prompts and region files. Display thumbnails are not model inputs.

S2 discard-region produces the same text/image input as S1 and is only for a separately reported best-adapted result; paired S2/S3 main results keep the region. S3, S4-noref and S5 cannot use that discard entry. No region is invented for S1 or ref-only S5 units. Source selectors are not output-difference masks; add anchors are not new-object output boxes.

Model-specific formatting, native planner prompts and actual API calls have been checked on the three fixed dev examples. The user revoked per-model smoke pauses. Stop after dev selection scores are reported, before freezing/test. Smoke recommendations are not selected configurations.

All generated artifacts, including dev search and diagnostics, must stay under `/tmp/ifbench/`. Only final frozen formal runs may write to `experiments2/IF-Bench/`. Existing split/assignment/renderer metadata refuses conflicting overwrite. The reviewed inputs are reproducible draft input assets, not a final model configuration freeze.

## Qwen-2511 smoke

```bash
python -m samtok_benchmark.ifbench.qwen2511_smoke prepare
# Run each shard once on its assigned GPU, in the audited Qwen environment.
CUDA_VISIBLE_DEVICES=0 python -m samtok_benchmark.ifbench.qwen2511_smoke worker --shard 0 --shards 4
# After all four workers finish:
python -m samtok_benchmark.ifbench.smoke_report /tmp/ifbench/tiered_v1/smoke/qwen2511
```

Report generation uses the `review` optional dependency group (`markdown-it-py`); model workers use the separately audited inference environment.

The immutable smoke plan uses the three approved dev examples: 30 dual-path setting requests, plus six single-image/coordinate requests on S3-mask. Nine S2 discard-region entries reuse bit-identical S1 inputs; image hashes, prompt, seed and parameters must all match. It records actual transformer/text-encoder calls, condition-image preprocessing, raw outputs, source-resolution outputs and measured runtime. No Judge or quality-based candidate selection occurs. Failed requests are not automatically resampled. The report contains inline comparison images and exact prompts; HTML embeds previews to remain viewable without resolving local image URLs. All artifacts stay in the temporary directory.

## Other main-table smoke runners

`smoke_suite` supports `qwen21`, `flux3`, `replan`, `mirage`, `mice`, and `maskflow`. Its plans bind the reviewed three dev examples and refuse conflicting inputs. RePlan/MIRAGE S1 and missing-region S5 requests use cached native plans from `smoke_planners`; MIRAGE public ref extraction requires the recorded user decision. MaskFlow S1/S5 are explicit N/A. Failed generations are recorded, not quality-retried.

```bash
python -m samtok_benchmark.ifbench.smoke_suite prepare qwen21
# Choose shard count and available GPU for a new run; existing outputs are retained.
CUDA_VISIBLE_DEVICES=0 python -m samtok_benchmark.ifbench.smoke_suite worker qwen21 --shard 0 --shards 1
python -m samtok_benchmark.ifbench.validate_suite qwen21
python -m samtok_benchmark.ifbench.suite_report qwen21
# Only after every main-table plan is complete and validated:
python -m samtok_benchmark.ifbench.smoke_summary
```

The prepared runtime paths and snapshot sources are recorded in `smoke_suite.py` and each worker's environment JSON. These are smoke tools for this audited machine, not yet a portable frozen formal runner. Qwen/RePlan/MIRAGE/MICE/FLUX use the audited Python 3.11 environment; MaskFlow uses the separate Python 3.12 environment. Avoid rerunning completed generations as a quality retry. `suite_report` and `smoke_summary` only read existing inference outputs and write reports under `/tmp/ifbench/`.

All main-table smoke tests are complete; see `/tmp/ifbench/tiered_v1/smoke/SUMMARY_REPORT.html`. MaskFlow serial-chain validation checks every unit and pixel equality of each previous output to the next source. The consolidated report verifies one inference start per generated request, displays all method recommendations and embeds comparison images directly in HTML. No Judge score, candidate freeze or test inference has been produced.

## Registered dev selection

The user approved proceeding after the consolidated smoke report. `dev_plan.py` registers complete candidates (including S2 discard and official PE/PUP supplements within each four-slot budget), the dev-only case list, primary selection settings and tie order. This is candidate preregistration, not the final selected-configuration freeze.

`dev_runner.py` consumes only the approved public requests. It verifies identical smoke calls before reusing their outputs, uses file locks to distribute requests across workers, and leaves interrupted inference as a recorded failure rather than sampling again. Runtime/protocol errors pause the affected model. MaskFlow S1/S5 remain N/A. `dev_components.py` caches official PE/PUP with their native sampling defaults. `ref_extract.py` extends the public referring-phrase grammar; unknown grammar is not filled from private annotations.

`dev_judge.py` builds an independent canonical view: source, source-size output, canonical ref instructions, source selector masks and private edit contracts. It exposes no model, candidate, setting, actual editor instruction or locator metadata. It does not reuse historical scores. Deterministic parsing may repair JSON structure but cannot invent scores; unparsed responses block selection.

`dev_orchestrator.py` schedules prerequisite planners/components and generation on eight GPUs, then runs the common Judge and writes a pre-freeze review marker. It never runs test or writes a freeze file. `dev_report.py` publishes live completeness and, only when complete, candidate scores and proposed selections. All artifacts are under `/tmp/ifbench/tiered_v1/dev_selection/`.

```bash
python -m samtok_benchmark.ifbench.dev_plan
# Validate the canonical Judge on the fixed smoke outputs using its separate runtime:
/tmp/ifbench-judge-runtime/bin/python -m samtok_benchmark.ifbench.dev_judge --probe
# Only one controller at a time; it holds controller.lock.
python -m samtok_benchmark.ifbench.dev_orchestrator
```

The Judge requires its supported Qwen4Exp runtime. The historical working package versions were recovered from prior run metadata, and CUDA 12.9 builds match this host's driver. Installation evidence remains in the dev temporary directory; [vLLM's GPU installation guide](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/) documents choosing the matching CUDA build. These engineering dependencies do not change the pinned Judge weights or scoring rubric.


Dynamic dev GPU handoffs are enabled only by a plan-bound `engineering/balanced_queue/enabled.json` in the temporary dev root. Existing workers are unaffected. New `dev_runner` invocations dispatch independent `--exact-model` children in each model's original environment. Assignment and completion records identify the actual model/GPU; outer orchestration labels remain the original launch requests. No active inference is preempted, and candidate selection remains unchanged.
