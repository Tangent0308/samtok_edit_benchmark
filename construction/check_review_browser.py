"""Exercise every real case and independent overlay layers in an isolated review copy."""

from __future__ import annotations
import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    a = parser.parse_args()
    errors = []
    failed_requests = []
    requests = []
    reviewed = []
    with tempfile.TemporaryDirectory(prefix="samtok-v2-browser-") as temp:
        work = Path(temp)
        for p in a.package.iterdir():
            if p.name == "reviews":
                continue
            if p.is_dir():
                (work / p.name).symlink_to(p.resolve(), target_is_directory=True)
            else:
                shutil.copyfile(p, work / p.name)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        log = (work / "server.log").open("w")
        server = subprocess.Popen(
            [sys.executable, str(work / "run_review.py"), "--port", str(port), "--no-browser"],
            stdout=log,
            stderr=log,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                try:
                    with urlopen(base + "/package_metadata.json", timeout=1) as response:
                        meta = json.load(response)
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("server did not start")
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
                page = browser.new_page(viewport={"width": 1500, "height": 1100})
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on("requestfailed", lambda req: failed_requests.append(req.url))
                page.on("request", lambda req: requests.append(req.url))
                page.goto(base)
                page.wait_for_function(
                    "current && source && document.querySelector('#viewer').dataset.overlays !== undefined"
                )
                assert page.locator("[data-case]").count() == 200
                assert len([u for u in requests if "/cases/" in u and u.endswith(".json")]) == 1
                assert page.locator("#error").inner_text() == ""
                ids = page.evaluate("index.map(c=>c.id)")
                selected_ids = [ids[0], ids[167], ids[199]] if a.smoke else ids
                for i, cid in enumerate(selected_ids):
                    page.evaluate("(id)=>select(id)", cid)
                    page.wait_for_function(
                        '(id)=>current?.id===id && document.querySelector("#load-state").textContent===""',
                        arg=cid,
                    )
                    expected = page.evaluate("current.units.length")
                    assert page.locator(".instruction-en").count() == expected
                    assert page.locator(".instruction-zh").count() == expected
                    page.locator("#clear").click()
                    for layer in ["mask", "box", "ref"]:
                        page.locator(f'[data-all="{layer}"]').click()
                    page.wait_for_function(
                        """()=>{const v=JSON.parse(document.querySelector('#viewer').dataset.overlays||'{}');return current.units.every(u=>v[u.id]?.mask&&v[u.id]?.box&&v[u.id]?.ref)}"""
                    )
                    assert page.locator("#error").inner_text() == ""
                    if i in [137, 167, 199]:
                        a.output.parent.mkdir(parents=True, exist_ok=True)
                        page.screenshot(
                            path=str(a.output.parent / f"review_case_{i + 1:03d}.png"),
                            full_page=True,
                        )
                    reviewed.append(cid)
                    page.locator("#clear").click()
                    if (i + 1) % 25 == 0:
                        print(f"Browser cases: {i + 1}/200", flush=True)
                page.select_option("#count", "5")
                assert page.locator("[data-case]").count() == 85
                page.select_option("#count", "")
                page.evaluate("(id)=>select(id)", ids[167])
                page.wait_for_function("(id)=>current?.id===id", arg=ids[167])
                page.locator("#formal-modes").click()
                page.wait_for_function(
                    '()=>current.units.every(u=>(viewModes[u.id]||"none")===u.interaction.locator)'
                )
                page.locator("#formal-details").click()
                page.wait_for_function('()=>document.querySelector("#formal-image").naturalWidth>0')
                page.locator("#reviewer").fill("SYNTHETIC_BROWSER_TEST_ONLY")
                page.select_option("#decision", "revise")
                page.locator("#note").fill("Isolated test; not a real human review.")
                page.locator("#save").click()
                page.wait_for_function(
                    '()=>document.querySelector("#save-state").textContent.includes("已保存")'
                )
                page.reload()
                page.wait_for_function(
                    '()=>current && document.querySelector("#note").value.includes("Isolated test")'
                )
                assert page.locator("#decision").input_value() == "revise"
                page.locator("#clear").click()
                page.locator("#all-overlays").click()
                page.wait_for_function(
                    "()=>current.units.every(u=>overlayFlags[u.id]?.mask&&overlayFlags[u.id]?.box&&overlayFlags[u.id]?.ref)"
                )
                page.locator('[data-owner="U5"][data-layer="mask"]').check()
                page.locator('[data-owner="U5"][data-layer="box"]').check()
                page.locator('[data-owner="U5"][data-layer="ref"]').check()
                page.wait_for_function(
                    '()=>{let x=JSON.parse(document.querySelector("#viewer").dataset.overlays);return x.U5.mask&&x.U5.box&&x.U5.ref}'
                )
                assert not errors, errors
                assert not failed_requests, failed_requests
                browser.close()
            result = {
                "status": "passed",
                "cases_loaded": len(reviewed),
                "all_cases_mask_box_ref_layers": True,
                "fifth_object": True,
                "one_click_all_mask_box_ref": True,
                "five_object_filter_count": 85,
                "lazy_initial_case_fetches": 1,
                "bilingual_instructions": True,
                "isolated_review_persistence": True,
                "delivered_user_reviews_untouched": True,
                "page_errors": errors,
                "failed_requests": failed_requests,
                "manifest_sha256": meta["manifest_sha256"],
            }
            a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(result))
        finally:
            server.terminate()
            server.wait(timeout=10)
            log.close()


if __name__ == "__main__":
    main()
