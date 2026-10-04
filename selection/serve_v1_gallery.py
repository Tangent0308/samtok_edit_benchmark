#!/usr/bin/env python3
"""Serve the v1 lazy gallery and local assets with Python's standard library."""

from __future__ import annotations

import argparse
import functools
import http.server
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--html", default="case_gallery.html", help="HTML filename under --root")
    args = parser.parse_args()
    root = args.root.resolve()
    html_name = args.html
    if not (root / html_name).is_file() and html_name == "case_gallery.html" and (root / "v1_case_gallery.html").is_file():
        html_name = "v1_case_gallery.html"
    if not (root / html_name).is_file():
        raise FileNotFoundError(root / html_name)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Open http://{args.host}:{args.port}/{html_name}", flush=True)
    print("Press Ctrl-C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
