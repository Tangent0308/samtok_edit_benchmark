"""Read only new-pilot receipts; report real generation/scoring coverage."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

BASE = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
BENCHES = ("gie", "compbench", "complexbench_edit", "interedit", "complex_edit", "gedit", "omni_iie", "gide")


def main():
    rows = []
    for bench in BENCHES:
        root = BASE / "experiments2/SAMTokEdit" / ("external_"+bench) / "pilot20_20261108"
        selection = json.loads((root/"SELECTION.json").read_text())
        item = {"benchmark": bench, "additional_per_model": selection["additional"], "total_per_model": selection["total"]}
        for model in ("sitedit", "qwen21"):
            results = [json.loads(p.read_text()) for p in (root/"additional/run"/model/"edit").glob("*/result.json")]
            scores = root/"additional/scores"/model
            item[model] = {"generation": dict(Counter(r["status"] for r in results)),
                           "local": len(list(scores.glob("*/local.json"))),
                           "judge": len(list(scores.glob("*/judge/score.json"))),
                           "api_responses": len(list(scores.glob("**/response.json"))),
                           "api_errors": len(list(scores.glob("**/error.json")))}
            failures = [(r["identity"]["case_id"], r.get("error")) for r in results if r["status"] != "completed"]
            if failures:
                item[model]["failures"] = failures
        item["combined_report"] = (root/"report/REPORT.json").exists()
        rows.append(item)
    payload = {"utc": datetime.now(timezone.utc).isoformat(), "rows": rows}
    destination = BASE / ".ifbench-tmp/external_pilot20_20261108/STATUS.json"
    temporary = destination.with_suffix(".partial")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n")
    temporary.replace(destination)
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
