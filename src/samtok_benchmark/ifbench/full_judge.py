"""Canonical TP8 Judge for one source-owned node of the full release."""

import argparse
from pathlib import Path
from .fairness_dev_judge import run


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--node", type=int, required=True)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    run(a.plan, node_id=a.node, dry_run=a.dry_run)
