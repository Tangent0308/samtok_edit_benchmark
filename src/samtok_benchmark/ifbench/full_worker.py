"""Run the existing native worker on one frozen full-release source partition."""

import argparse
from pathlib import Path
from . import full_plan
from .fairness_dev_worker import run_worker


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", required=True, type=Path)
    p.add_argument("--node", required=True, type=int)
    p.add_argument("--model", required=True)
    p.add_argument("--stage", required=True, choices=["planner", "edit"])
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=8)
    a = p.parse_args()
    return run_worker(
        a.plan, a.model, a.stage, a.shard, a.shards, plan_api=full_plan, node_id=a.node
    )


if __name__ == "__main__":
    main()
