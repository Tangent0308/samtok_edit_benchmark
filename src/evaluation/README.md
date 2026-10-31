# Evaluation helpers

The current seven-model, ten-setting workflow is documented in [USAGE.md](../../docs/USAGE.md); its latest dev20 statistics are in [RESULTS.md](../../docs/RESULTS.md). Start with the public `if-bench` CLI after installing this checkout.

- [protocol_audit/](protocol_audit/README.md): audited native helpers and immutable dev-bundle/bootstrap utilities.
- [inputs/](inputs/README.md): earlier shared-input export tools and their historical boundary.
- `diffsynth/`: shared method helper code referenced by recorded runs.
- Other top-level analysis/editor scripts: preserved legacy release workflows. Use their original snapshots to reproduce old runs; they are not the current ten-setting launcher or result definition.

Current orchestration lives in [samtok_benchmark/ifbench](../samtok_benchmark/ifbench/README.md). All raw outputs, checkpoints and runtime packages remain external. See [CONTRIBUTING.md](../../CONTRIBUTING.md) for directories, CPU checks and artifact policy.
