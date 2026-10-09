"""Record explicit visual decisions supplied by the reviewer; never infer admission."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    pool = [json.loads(x) for x in (root / "candidate_pool.jsonl").read_text().splitlines()]
    path = root / "visual_decisions.jsonl"
    previous = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    seen = {r["candidate_id"] for r in previous}
    decisions = json.load(sys.stdin)
    for decision in decisions:
        record = pool[decision["index"]]
        cid = record["candidate_id"]
        if cid in seen:
            raise ValueError(
                f"already reviewed {cid}; append a separate documented revision instead"
            )
        assert decision["decision"] in {"accept", "reject"}
        assert decision.get("evidence")
        if decision["decision"] == "accept":
            assert 2 <= len(decision["units"]) <= 4
            selected = [u["candidate_unit"] for u in decision["units"]]
            assert len(selected) == len(set(selected)) and all(
                1 <= u <= len(record["units"]) for u in selected
            )
            assert all(u.get("ref") and u.get("value") for u in decision["units"])
            assert decision.get("mechanisms") and decision.get("protect")
        card = root / "review_cards" / f"{decision['index']:04d}_{cid}.jpg"
        decision.update(
            candidate_id=cid,
            kind="ai_direct_visual",
            reviewer="assistant",
            reviewed_at=datetime.now(timezone.utc).isoformat(),
            review_card=str(card.relative_to(root)),
            review_card_sha256=hashlib.sha256(card.read_bytes()).hexdigest(),
        )
        previous.append(decision)
        seen.add(cid)
    path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in previous))
    accepted = sum(d["decision"] == "accept" for d in previous)
    print(
        f"Visual decisions {len(previous)}; accepted {accepted}; rejected {len(previous) - accepted}"
    )


if __name__ == "__main__":
    main()
