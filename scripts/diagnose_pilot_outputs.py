"""Read-only transparency diagnostics; never repair or rescore generated images."""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

SLUGS = ("gie", "compbench", "complexbench_edit", "interedit", "complex_edit", "gedit", "omni_iie", "gide")


def diagnose(results):
    rows = []
    for slug in SLUGS:
        for model in ("sitedit", "qwen21"):
            root = results/("external_"+slug)/"pilot_20261107/run"/model/"edit"
            for path in sorted(root.glob("*/result.json")):
                result = json.loads(path.read_text())
                if result["status"] != "completed":
                    continue
                with Image.open(result["raw_image"]) as image:
                    fraction = 0.0
                    if "A" in image.getbands():
                        transform = result["identity"]["geometry"]
                        cw, ch = transform["canvas_size"]
                        box = tuple(v*(image.width/cw if i % 2 == 0 else image.height/ch)
                                    for i, v in enumerate(transform["content_box"]))
                        alpha = image.getchannel("A").resize(tuple(transform["source_size"]), Image.Resampling.LANCZOS, box=box)
                        fraction = float((np.asarray(alpha) < 128).mean())
                    rows.append({"benchmark": slug, "model": model, "case_id": path.parent.name,
                                 "raw_image": result["raw_image"], "raw_sha256": result["raw_sha256"],
                                 "raw_mode": image.mode, "restored_alpha_below_128_fraction": fraction})
    return {"diagnostic_only": True, "criterion": "more than 1% of restored content has native alpha < 128",
            "rows": rows, "substantial_transparency": [r for r in rows if r["restored_alpha_below_128_fraction"] > 0.01]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = diagnose(args.results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2)+"\n")
    print(json.dumps({"count": len(payload["rows"]), "substantial_transparency": [
        [r["benchmark"], r["model"], r["case_id"], r["restored_alpha_below_128_fraction"]]
        for r in payload["substantial_transparency"]]}, indent=2))
