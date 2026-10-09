# Development

This branch develops v2 while preserving the frozen v1 release and its commands. v2 uses an independent `samtok_benchmark.v2` module and `samtok-benchmark-v2` entrypoint. Keep model weights, source-image downloads, full generated-output collections and interactive human decisions outside Git. Small documented result figures and frozen AI-review evidence snapshots may live under `docs/assets/` and `docs/results/`. Do not alter released tasks or masks as a side effect of evaluation.

```bash
python -m pip install -e '.[dev]'
ruff check src tests examples construction
pytest -q
```

Tests use temporary synthetic images and no model weights/GPU. Full asset validation uses the actual data root and `data/v1/asset_manifest.jsonl`:

```bash
samtok-benchmark validate --dataset-root /path/to/v1 --output outputs/validation.json
```

Use `src/samtok_benchmark/` for reusable code, `examples/` for integration contracts, `docs/` for protocol documentation, `data/v1/` for frozen release metadata, and `tests/` for behavior/invariants. UI assets must be included in package data so installed distributions can generate portable review tools.

v2 metadata lives in `data/v2/`; construction scripts live in `construction/`. The portable asset bundle is external to Git. The Chinese construction and protocol report is `docs/V2_REPORT_ZH.md`. v2 images must be new source families relative to v1 and the known task-training inventory. Count physical parent objects, never disconnected mask components. The editor receives only explicitly public interactions. All per-unit E/P/Q and global P/Q must pass for a case to pass. Synthetic smoke outputs must never be presented as benchmark model scores.

A dataset change needs a new instruction/manifest identity and provenance, regenerated inputs, and new model/judge results. Preserve source IDs and original mask hashes. Do not mix old scores into the new version. Update statistical summaries and representative figures together with metadata.

Record reviewer identity and concrete reasons in separate audit files. AI review, human data approval and human output scoring are distinct provenance categories. Use human result files only when the corresponding people actually reviewed them.

Commit messages follow [MaiXiaochai/CommitMessageGuidelines](https://github.com/MaiXiaochai/CommitMessageGuidelines): `<type>: <subject>`, with an optional body explaining behavior and validation. Use `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build` or `ci` as appropriate. For example:

```text
refactor: organize the v1 benchmark release and evaluation workflow

Replace legacy entrypoints with the frozen 450-case release, portable review,
and a version-checked model-independent evaluation pipeline.
```

Run relevant checks before committing. Push this work only to `v2branch`; do not update `v1branch`, `dev` or `main`. Never force-push unrelated work.

The current implementation checks and their scope are recorded in [`data/v1/audits/repository_validation.json`](data/v1/audits/repository_validation.json). The UI and protocol smoke checks use synthetic/unchanged outputs; they are not benchmark model scores or human annotations.
