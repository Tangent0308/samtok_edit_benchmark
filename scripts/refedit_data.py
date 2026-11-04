#!/usr/bin/env python3
"""Download, extract and prepare RefEdit-Bench. Run with ``python -I`` (downloaded bytes are untrusted).

Isolated mode ignores PYTHONPATH and does not put the current or script directory on sys.path, so nothing in the
download directory can shadow a module; this script adds only the repository's own ``src`` explicitly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from samtok_benchmark.external_refedit import data  # noqa: E402


def main():
    if not sys.flags.isolated:
        raise SystemExit("Run this script with python -I")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("download")
    p.add_argument("--dataset", required=True)
    p.add_argument("--token-file", required=True, help="file holding an HF read token; never printed")
    p = sub.add_parser("extract")
    p.add_argument("--dataset", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--dataset", required=True)
    p.add_argument("--bundle", required=True)
    args = parser.parse_args()
    if args.command == "download":
        receipt = data.download(args.dataset, args.token_file)
        print(json.dumps({k: receipt[k] for k in ("dataset", "revision", "files")}, indent=2))
    elif args.command == "extract":
        print(json.dumps(data.extract(args.dataset), indent=2))
    else:
        index = data.prepare(args.dataset, args.bundle)
        print(json.dumps({"cases": len(index["cases"]), "digest": index["digest"]}, indent=2))


if __name__ == "__main__":
    main()
