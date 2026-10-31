# IF-Bench evaluation code

Read the current [usage guide](../../../docs/USAGE.md), [configuration reference](../../../configs/evaluation/fairness_v2_1.json) and [development rules](../../../CONTRIBUTING.md). The completed fixed dev20 has seven models, ten settings and twenty shared images. Formal freeze/test is pending.

| Modules | Responsibility |
|---|---|
| `cli` | Public `if-bench` data/config/run entry point |
| `plan`, `public`, `render`, `inputs` | Split, shared assignments, public projection, deterministic annotations and prompts |
| `fairness_dev_plan` | Fixed dev20 identity, assets, scope and exact cache verification |
| `fairness_dev_revision`, `fairness_dev_recovery` | Approved 2K/MICE changes and native Qwen2.1 CPU-offload recovery |
| `fairness_dev_cache` | Exact terminal reuse, including failures, with original provenance/costs |
| `fairness_dev_worker`, `fairness_dev_run` | Native joint editing, eight-GPU foreground orchestration and lifecycle barriers |
| `fairness_dev_judge` | Canonical blind evidence, exact score reuse and model-serial TP8 Judge |
| `fairness_dev_report` | Complete-denominator UP/JP, paired bootstrap, derived metrics and review gate |

Model helpers are in [evaluation/protocol_audit](../../evaluation/protocol_audit/README.md). A current public point never becomes an inferred hard box/mask, and no private target text reaches an editor. One request produces one joint sample. Started requests without terminal records are not automatically retried. Generation failures remain in denominators; missing Judge scores remain missing.

The new checkout uses `src/`; an existing bundle always uses its own immutable `repo/`, manifest and foreground `start.sh`. Canonical scoring modules retain original bytes. Historical candidate/smoke/rejudge CLI workflows must run in their original frozen snapshots; see [LEGACY_WORKFLOWS.md](LEGACY_WORKFLOWS.md) for provenance, not new-run instructions.

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check src/samtok_benchmark/ifbench src/evaluation/protocol_audit tests/test_ifbench_*.py
bash -n src/evaluation/protocol_audit/start_fairness_dev20.sh
```
