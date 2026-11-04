#!/usr/bin/env python3
"""Text-only review of SITEdit's region-token placement on the public RefEdit-Bench instructions.

Run once after the data is prepared and BEFORE any generation: it shows, for every case, the placement rule that the
frozen adapter applies and the instruction with a placeholder token. It reads only public.json files (no images,
masks, scoring fields or model outputs), so any rule revision it prompts is made without seeing results; after the
review the rules are frozen and the review file is kept as evidence.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
TOKEN = "<|mt_start|><|mt_0000|><|mt_0256|><|mt_end|>"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--method-source", required=True, help="SITEdit checkout (for the method's selector rule)")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(args.method_source) / "src"))
    from samtok_benchmark.external_refedit.placement import place

    index = json.loads((Path(args.bundle) / "index.json").read_text())
    rows, rules = [], Counter()
    for case in index["cases"]:
        public = json.loads(Path(case["public"]).read_text())
        placed, info = place(public["instruction"], TOKEN)
        rules[info["rule"]] += 1
        rows.append({"case_id": case["case_id"], "instruction": public["instruction"],
                     "placed": placed.replace(TOKEN, "<TOKEN>"), **info})
    output = Path(args.output)
    output.write_text(json.dumps({"rules": dict(rules), "cases": rows}, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(dict(rules), indent=1))


if __name__ == "__main__":
    main()
