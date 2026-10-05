#!/usr/bin/env python3
"""Run the local SAMTok v1 case review server.

Usage:
    python run_review.py
    python run_review.py --port 8765 --no-browser
"""

from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

RESULTS_LOCK = threading.RLock()


ROOT = Path(__file__).resolve().parent
RESULTS_PATH = ROOT / "review_results.json"
CASES_PATH = ROOT / "cases.json"
REVIEWED_CASES_PATH = ROOT / "reviewed_cases.json"
REVIEWED_BENCHMARK_PATH = ROOT / "benchmark" / "reviewed_benchmark.jsonl"


def migrate_results(value: dict) -> dict:
    """Retain decisions/custom edits; discard only obsolete default overrides."""
    path = ROOT / "benchmark" / "instruction_revision_audit.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            revision = json.loads(line)
            record = value.get("cases", {}).get(revision["id"], {})
            if record.get("instruction_override") == revision["previous_instruction"]:
                record.pop("instruction_override", None)
    return value


def load_results() -> dict:
    if not RESULTS_PATH.exists():
        return {"version": 1, "cases": {}}
    value = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("cases"), dict):
        raise ValueError("Invalid review_results.json; restore a backup before continuing")
    return migrate_results(value)


def save_results(value: dict) -> None:
    cases = {c["id"]: c for c in json.loads(CASES_PATH.read_text(encoding="utf-8"))}
    if set(value["cases"]) - set(cases):
        raise ValueError("unknown case ID in results")
    for record in value["cases"].values():
        if not isinstance(record, dict) or record.get("status", "unreviewed") not in {
            "pass",
            "discard",
            "unreviewed",
        }:
            raise ValueError("invalid review status")
    value = migrate_results(value)
    temporary = RESULTS_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(RESULTS_PATH)
    materialize_reviewed_copy(value)


def materialize_reviewed_copy(value: dict) -> None:
    """Apply human decisions to a separate copy; never mutate cases.json."""
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    for case in cases:
        record = value.get("cases", {}).get(case.get("id"), {})
        case["review_status"] = record.get("status", "unreviewed")
        case["review_note"] = record.get("note", "")
        case["review_updated_at"] = record.get("updated_at")
        case["instruction_needs_recheck"] = bool(
            record
            and case.get("instruction_revision")
            and record.get("instruction_revision") != case["instruction_revision"]
        )
        override = record.get("instruction_override")
        case["reviewed_instruction"] = override if override else case.get("instruction", "")
    temporary = REVIEWED_CASES_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(REVIEWED_CASES_PATH)
    REVIEWED_BENCHMARK_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_jsonl = REVIEWED_BENCHMARK_PATH.with_suffix(".jsonl.tmp")
    with temporary_jsonl.open("w", encoding="utf-8") as stream:
        for case in cases:
            stream.write(json.dumps(case, ensure_ascii=False) + "\n")
    temporary_jsonl.replace(REVIEWED_BENCHMARK_PATH)


class ReviewHandler(SimpleHTTPRequestHandler):
    """Static file server plus a tiny JSON persistence API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/results":
            self._json(load_results())
            return
        if path == "/api/export":
            body = json.dumps(load_results(), ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=review_results.json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        if path != "/api/results":
            self._json({"error": "unknown endpoint"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 10_000_000:
                raise ValueError("invalid request length")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("cases"), dict):
                raise ValueError("payload must contain a cases object")
            payload["version"] = 1
            with RESULTS_LOCK:
                save_results(payload)
            self._json({"ok": True, "path": str(RESULTS_PATH)})
        except Exception as exc:  # keep errors visible to the browser
            self._json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt, *args):
        print("[review] " + (fmt % args))


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the v1 450-case review UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), ReviewHandler)
    url = f"http://{args.host}:{args.port}/index.html"
    print(f"Open {url}")
    print(f"Results are saved to {RESULTS_PATH}")
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping review server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
