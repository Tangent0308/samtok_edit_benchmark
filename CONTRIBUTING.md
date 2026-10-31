# Development

Use a checkout and a separate CPU environment for repository development. GPU generation and Judge runtimes are pinned in published bundles; installing this package does not provision models, data or GPU dependencies.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
if-bench --help
python -m pytest -q
```

Install `.[construction]` for data authoring/release tools. Reproduce documentation plots with `scripts/results_plot_requirements.txt` in a separate environment; see [the results guide](docs/RESULTS.md). The project distribution/CLI is `if-bench`; existing `samtok_benchmark`, `evaluation` and `construction` import namespaces are preserved for compatibility. The historical `samtok-benchmark` CLI remains a data/review compatibility interface, not the current tiered evaluation runner.

## Layout

| Directory | Purpose |
|---|---|
| `src/samtok_benchmark/ifbench/` | Public inputs, fixed dev/full-release orchestration, native workers, canonical scoring and reports |
| `src/samtok_benchmark/v2/` | Release validation, instruction contracts and shared evaluation primitives |
| `src/evaluation/` | Native method helpers and audited bundle/bootstrap utilities |
| `src/construction/` | Candidate selection, annotation, audit and release-building tools |
| `configs/evaluation/` | Human-readable reference for the completed dev configuration; no formal freeze implied |
| `data/v2_2.6.0/` | Current release manifests, validation receipts and reviewed mask patches |
| `data/provenance/construction/` | Historical annotation/revision decisions, recipes and audit records |
| `data/legacy/`, other `data/v2*/` | Earlier schema/releases, retained for provenance |
| `docs/` | Current guides and the four-node runbook and curated documentation figures |
| `docs/archive/previous/` | Earlier documents and evidence; not current execution instructions |
| `scripts/` | Lightweight maintenance and documentation entry points |
| `tests/` | CPU regression tests; no model downloads or inference |
| `examples/`, `results/` | Small interface examples and an external-results index |

Raw source images, full generated outputs, checkpoints, runtime archives and full experiment reports stay outside Git. The requested small documentation previews, provenance and aggregate tables live under `docs/assets/`. Temporary outputs belong under `/tmp/ifbench/` or the shared `.ifbench-tmp/`; `experiments2/IF-Bench/` is reserved for confirmed formal results.

## Preserve experimental identity

A published bundle owns its `repo/` snapshot, requests, plan and SHA manifests. Run it with `if-bench run-dev --bundle /path/to/published-bundle` or its own foreground `start.sh`; never replace its code with a newer checkout, change SHA fields, weaken cache checks or reuse an output with different inputs. `if-bench inspect-run` is read-only. `--validate-only` on a run checks the frozen runtime/GPU admission and can write preflight receipts; it does not generate or judge images.

The new checkout uses `src/`; published older bundles use their original flat layout. Current bootstraps support both without modifying the old manifests. Historical standalone modules (`dev_judge`, `dev_judge_stream`, `dev_rejudge13`, `judge_repair`, early smoke/analysis/packaging tools) are evidence for previous run workflows and should be replayed in their original frozen snapshots. They are not public entry points for a new run. The canonical `ifbench/dev_judge.py`, deterministic score repair and `v2/judge.py` are retained byte-for-byte so scoring identities remain auditable; current orchestration resolves data from the plan.

The user has authorized the full 1,084-image release with the same fixed seven configurations on four shared-mount 8×H100 hosts. [FULL_RUN.md](docs/FULL_RUN.md) documents the dedicated full-plan schema, foreground `run-full --node 0..3` and read-only `inspect-full`. Preserve the old 108/976 split and dev20 subset as exposure provenance; report one total, without claiming unseen held-out performance. This does not authorize candidate search, retries or changes to native model defaults.

## Checks and contributions

Run CPU tests and Ruff on changed Python files. Path/launcher changes need coverage of both `src/` and frozen flat layouts, including foreground lifetime, exit status and hash rejection. A model adapter change must not alter public information, scoring, retry policy or native defaults silently. Record proposed protocol changes before inference.

```bash
python -m pytest -q
python -m ruff check src/samtok_benchmark/paths.py src/samtok_benchmark/ifbench/cli.py tests/test_repository_layout.py
python -m build --wheel --outdir /tmp/ifbench/dist
python scripts/check_docs.py
```

Use English commits in the format `<type>: <imperative subject>`, following [CommitMessageGuidelines](https://github.com/MaiXiaochai/CommitMessageGuidelines). Keep credentials out of code, configs and reports. Source datasets, third-party model implementations and weights retain their respective terms; this repository does not grant rights to those external assets.
