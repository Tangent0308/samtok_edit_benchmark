# IF-Bench evaluation package

The current workflow is **fairness v2.1 / fixed dev20**: seven models, ten settings,
twenty shared development images, one configuration and one sample per request.
Read the [method reference](../../docs/protocol/if-bench-v1/CURRENT_EVALUATION_ZH.md)
and [launcher guide](../../docs/protocol/if-bench-v1/DEV20_RUN_ZH.md).
Historical `v2` Judge and release semantics remain unchanged.

## Current execution path

| Module | Responsibility |
|---|---|
| `plan`, `public`, `render`, `inputs` | Split/assignments, public projection, deterministic annotations and prompt forms |
| `fairness_dev_plan` | Fixed dev20 scope, scientific identity, assets and exact cache provenance |
| `fairness_dev_revision` | Approved Qwen2.1 2K and MICE fixed preamble changes; native 200-token completeness preflight |
| `fairness_dev_cache` | Completed-parent terminal reuse, including native failures, after exact request/specification and evidence checks |
| `fairness_dev_worker` | One GPU/shard, native planning or joint editing, durable attempts/results and actual calls |
| `fairness_dev_run` | Foreground lifecycle, eight workers per model, planner/editor barriers and Judge handoff |
| `fairness_dev_judge` | Canonical blind evidence, exact score reuse, eight-GPU model-serial scoring and parse records |
| `fairness_dev_report` | Complete-denominator UP/JP, paired bootstrap, derived metrics, K bins, inline-image Markdown and review gate |

Audited model helpers remain in [evaluation/protocol_audit](../../evaluation/protocol_audit/README.md)
and are included in the bundle source manifest. Old `geometry.small_box` and
`native.json` conversion assets remain for historical reproduction; current
fairness requests do **not** turn points into hard boxes or masks.

The shared bundle has its own fixed `repo/` snapshot. Use its foreground `start.sh`;
do not point an existing plan at newly formatted checkout files. Source hashes
remain part of reproducibility even for formatting-only changes. The current
checkout rehashes bytes instead of trusting size/mtime/ctime, which can collide
on shared filesystems; this integrity fix does not retrofit a published bundle.

## Durability and accounting

Tasks bind plan, public input, model configuration, seed and file digests. Exact
cache hits record zero **new** calls and retain original cost/provenance. Started
requests without terminal records cannot be automatically resampled. Generation
failures retain the denominator; missing Judge scores never become zeros. The
coordinator performs no fallback, candidate search, formal freezing or test.

Generation workers all exit before the separate TP/EP Judge starts. Judge batches
contain one model, models are scored serially, and raw responses are retained.
The final `REVIEW_REQUIRED.json` gates formal evaluation on the next user decision.

## Development

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check samtok_benchmark/ifbench evaluation/protocol_audit tests/test_ifbench_*.py
bash -n evaluation/protocol_audit/start_fairness_dev20.sh
```

Run from the repository root. CPU tests use synthetic fixtures and mock model
boundaries, without downloads or inference. Bootstrap lifecycle tests are in
`tests/test_ifbench_fairness_dev_bootstrap.py`.

Earlier smoke, `dev_*` candidate search, second-node Judge and 13-key rejudge
workflows are retained in [LEGACY_WORKFLOWS.md](LEGACY_WORKFLOWS.md) for provenance.
They are not the current launcher, and old retry authorizations do not extend to dev20.
