"""Trusted isolated entrypoint; downloaded data never supplies executable modules."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from samtok_benchmark.external_gie.data import download, bundle

parser = argparse.ArgumentParser()
parser.add_argument("command", choices=["download", "prepare"])
parser.add_argument("--dataset", required=True)
parser.add_argument("--upstream")
parser.add_argument("--output")
args = parser.parse_args()
if args.command == "download":
    result = download(args.dataset, args.upstream)
    print(json.dumps({"images": len(result["images"]), "revision": result["revision"]}))
else:
    result = bundle(args.dataset, args.output)
    print(json.dumps({"cases": len(result["cases"]), "digest": result["digest"]}))
