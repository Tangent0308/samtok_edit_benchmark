# Development

Use a separate CPU development environment. Model and Judge runtimes are pinned independently; installing this repository does not download weights or dataset images.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/check_docs.py
```

| Directory | Purpose |
|---|---|
| `src/samtok_benchmark/ifbench/` | Public inputs, 1MP geometry, native adapters, orchestration, Judge and reporting |
| `src/samtok_benchmark/v2/` | Dataset contracts and canonical scoring primitives |
| `src/evaluation/` | Native method helpers and runtime bootstrap utilities |
| `src/construction/` | Source selection, annotation, auditing and dataset construction |
| `configs/evaluation/fairness_v2_2_1mp.json` | Current model, resolution and Judge specification |
| `data/v2_2.6.0/` | Current evaluation release |
| `data/provenance/` | Immutable construction inputs and audit evidence |
| `docs/` | Current construction, usage, results and four-node guides |
| `tests/` | CPU regression tests without neural inference |

Read [AGENTS.md](AGENTS.md), [USAGE.md](docs/USAGE.md) and [FULL_RUN.md](docs/FULL_RUN.md) before changing scientific behavior. Public information, fixed seeds, native method workflows and canonical scoring must remain explicit. Preserve original canonical masks and manifest hashes when changing model canvases. Never overwrite a published run snapshot, resample an unresolved admitted request, or reuse outputs with different inputs.

Run pytest and Ruff on changed Python files. Geometry changes need tests for public-information isolation, coordinate transformations and restoration to canonical dimensions. Keep GPU smoke checks small and separate from quality evaluation.

Use English `<type>: <imperative subject>` commits following [CommitMessageGuidelines](https://github.com/MaiXiaochai/CommitMessageGuidelines). Keep credentials, weights, full datasets and generated experiment outputs out of Git. Temporary checks belong under `/tmp/ifbench/` or shared `.ifbench-tmp/`; only confirmed formal results belong under `experiments2/IF-Bench/`. Curated current documentation images may live under `docs/assets/` with provenance.
