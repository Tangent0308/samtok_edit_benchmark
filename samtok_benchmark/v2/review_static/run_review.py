#!/usr/bin/env python3
"""Standalone Python-standard-library server; run from any working directory."""

from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
LOCK = threading.RLock()
RESULTS = ROOT / "reviews/review_results.json"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_reviews():
    meta = load_json(ROOT / "package_metadata.json")
    if not RESULTS.exists():
        return {"schema_version": "2.0", "manifest_sha256": meta["manifest_sha256"], "cases": {}}
    value = load_json(RESULTS)
    if value.get("manifest_sha256") != meta["manifest_sha256"] or not isinstance(
        value.get("cases"), dict
    ):
        raise ValueError("Review results belong to a different manifest or are invalid")
    return value


def save_record(payload):
    metadata = load_json(ROOT / "package_metadata.json")
    if payload.get("manifest_sha256") != metadata["manifest_sha256"]:
        raise ValueError("Manifest mismatch; reload the review application")
    known = {c["id"] for c in load_json(ROOT / "cases.json")}
    cid = payload.get("case_id")
    if cid not in known:
        raise ValueError("Unknown case ID")
    case = load_json(ROOT / "cases" / f"{cid}.json")
    units = {u["id"] for u in case["units"]}
    if payload.get("decision") not in {"pending", "accept", "revise", "reject"}:
        raise ValueError("Invalid review decision")
    if not isinstance(payload.get("reviewer"), str) or (
        payload["decision"] != "pending" and not payload["reviewer"].strip()
    ):
        raise ValueError("填写实际复核人姓名 / ID 后再保存审核决定")
    if not isinstance(payload.get("note", ""), str):
        raise ValueError("Note must be text")
    for name in ["unit_notes", "instruction_suggestions"]:
        rows = payload.get(name, {})
        if (
            not isinstance(rows, dict)
            or set(rows) - units
            or any(not isinstance(v, str) for v in rows.values())
        ):
            raise ValueError("Invalid per-unit review fields")
    modes = payload.get("view_modes", {})
    if (
        not isinstance(modes, dict)
        or set(modes) - units
        or any(v not in {"none", "point", "box", "mask"} for v in modes.values())
    ):
        raise ValueError("Invalid annotation viewing mode")
    flags = payload.get("overlay_flags", {})
    if not isinstance(flags, dict) or set(flags) - units:
        raise ValueError("Invalid overlay units")
    for layers in flags.values():
        if (
            not isinstance(layers, dict)
            or set(layers) - {"point", "box", "mask", "ref", "none"}
            or any(type(v) is not bool for v in layers.values())
        ):
            raise ValueError("Invalid overlay flags")
    # Identity is entered by the user, not independently authenticated by this tool.
    record = {
        k: payload.get(k, {})
        for k in ["unit_notes", "instruction_suggestions", "view_modes", "overlay_flags"]
    }
    record.update(
        case_id=cid,
        decision=payload["decision"],
        reviewer=payload["reviewer"].strip(),
        note=payload.get("note", ""),
        review_kind="user_entered_unverified_identity",
        reviewed_at=datetime.now(timezone.utc).isoformat(),
        manifest_sha256=metadata["manifest_sha256"],
    )
    with LOCK:
        value = load_reviews()
        value["cases"][cid] = record
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        temporary = RESULTS.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(RESULTS)
    return record


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def json_response(self, value, status=200, download=False):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if download:
            self.send_header("Content-Disposition", "attachment; filename=v2_review_results.json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/api/reviews", "/api/export"}:
            try:
                with LOCK:
                    self.json_response(load_reviews(), download=path == "/api/export")
            except Exception as exc:
                self.json_response({"error": str(exc)}, 400)
        else:
            super().do_GET()

    def do_POST(self):  # noqa: N802
        if urlparse(self.path).path != "/api/review":
            self.json_response({"error": "unknown endpoint"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1_000_000:
                raise ValueError("Invalid payload length")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Expected a review object")
            self.json_response({"ok": True, "record": save_record(payload)})
        except Exception as exc:
            self.json_response({"ok": False, "error": str(exc)}, 400)


def main():
    p = argparse.ArgumentParser(description="SAMTok v2 多对象标注审核")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{server.server_address[1]}/"
    print(f"Open {url}", flush=True)
    print(f"Reviews: {RESULTS}", flush=True)
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
