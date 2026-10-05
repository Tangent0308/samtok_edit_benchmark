# Development

This branch maintains the current v1 release only. Keep model weights, source-image downloads, generated outputs and human decisions outside Git. Do not alter released tasks or masks as a side effect of evaluation.

```bash
python -m pip install -e '.[dev]'
ruff check src tests examples
pytest -q
```

Tests use temporary synthetic images and no model weights/GPU. Full asset validation uses the actual data root and `data/v1/asset_manifest.jsonl`:

```bash
samtok-benchmark validate --dataset-root /path/to/v1 --output outputs/validation.json
```

Use `src/samtok_benchmark/` for reusable code, `examples/` for integration contracts, `docs/` for protocol documentation, `data/v1/` for frozen release metadata, and `tests/` for behavior/invariants. UI assets must be included in package data so installed distributions can generate portable review tools.

A dataset change needs a new instruction/manifest identity and provenance, regenerated inputs, and new model/judge results. Preserve source IDs and original mask hashes. Do not mix old scores into the new version. Update statistical summaries and representative figures together with metadata.

Record reviewer identity and concrete reasons in separate audit files. AI review, human data approval and human output scoring are distinct provenance categories. Use human result files only when the corresponding people actually reviewed them.

Commit messages follow [MaiXiaochai/CommitMessageGuidelines](https://github.com/MaiXiaochai/CommitMessageGuidelines): `<type>: <subject>`, with an optional body explaining behavior and validation. Use `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build` or `ci` as appropriate. For example:

```text
refactor: organize the v1 benchmark release and evaluation workflow

Replace legacy entrypoints with the frozen 450-case release, portable review,
and a version-checked model-independent evaluation pipeline.
```

Run relevant checks before committing. A push of `v1branch` must not update `dev` or `main`. Never force-push unrelated work.

The current implementation checks and their scope are recorded in [`data/v1/audits/repository_validation.json`](data/v1/audits/repository_validation.json). The UI and protocol smoke checks use synthetic/unchanged outputs; they are not benchmark model scores or human annotations.
