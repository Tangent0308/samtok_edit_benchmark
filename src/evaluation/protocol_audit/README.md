# Audited method and bundle tools

See [USAGE.md](../../../docs/USAGE.md) for the current scientific configuration and [CONTRIBUTING.md](../../../CONTRIBUTING.md) for development. This historical directory name is retained to preserve Python imports; actual source files now live under `src/`.

| Tool | Role |
|---|---|
| `prepare_full4.py`, `bootstrap_full4.py`, `start_full4.sh` | CPU construction/publication and foreground launch of the authorized four-node full-release run; see [FULL_RUN.md](../../../docs/FULL_RUN.md) |
| `prepare_fairness_dev20_recovery.py` | Build the approved native Qwen2.1 offload recovery from its exact parent, preserving terminal evidence |
| `prepare_fairness_dev20_revision.py` | Prepare the approved 2K/MICE revision, verify parent provenance and snapshot/publish source |
| `package_fairness_dev20_assets.py` | Package public assets/upstream snapshots with verified aliases |
| `bootstrap_fairness_dev20.py`, `start_fairness_dev20.sh` | Verify resources, isolate pinned runtimes and stay in foreground; support `src/` and old flat snapshots |
| `fairness_flux3_replan.py` | Native FLUX3 dual-input/no-box and RePlan planning→joint-edit helpers |
| `fairness_mirage_mice_probe.py` | Public MIRAGE/MICE adapters, also used by the earlier fixed probe |
| `fairness_qwen_flux2_smoke.py`, `fairness_validation_runner.py` | Audited native Qwen/FLUX2 helpers and trace accounting |

The coordinator/worker/Judge/report modules are in [samtok_benchmark.ifbench](../../samtok_benchmark/ifbench/README.md). A recovery builder is specific to its approved parent and failed requests; it is not a general test-set launcher. Preparation/publishing must never update an already-published bundle. Publication requires a clean committed checkout, exact file hashes and the corresponding authorization.

Use `if-bench inspect-run --bundle PATH` for read-only metadata and `if-bench run-dev --bundle PATH` for the bundle's own foreground entry. `--validate-only` prepares/verifies the frozen environment and GPU admission without inference; it can write preflight receipts. The new full-release authorization is separate: use `if-bench run-full --node N --bundle PATH` with its published four-node plan. Old dev packages and retry permissions remain unchanged.

Older source audits, smoke probes, second-node Judge packaging, candidate selection and one-off report scripts are historical evidence. Run those workflows in their original flat snapshots; [LEGACY_AUDIT.md](LEGACY_AUDIT.md) records their original scope. Do not apply old retry permission or overwrite old reports from a new checkout.
