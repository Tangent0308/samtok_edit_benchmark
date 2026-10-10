"""Exercise real v2 cases in an isolated copy without creating human review records."""

import argparse
import importlib.util
import json
import shutil
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

from samtok_benchmark.io import write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    errors = []
    with tempfile.TemporaryDirectory(prefix="v2_review_check_") as temp:
        root = Path(temp)
        for name in [
            "index.html",
            "app.js",
            "style.css",
            "run_review.py",
            "cases.json",
            "package_metadata.json",
        ]:
            shutil.copyfile(args.root / name, root / name)
        for name in ["assets", "formal_inputs", "cases", "benchmark"]:
            (root / name).symlink_to((args.root / name).resolve(), target_is_directory=True)
        spec = importlib.util.spec_from_file_location("isolated_server", root / "run_review.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                page = browser.new_page(
                    viewport={"width": 1500, "height": 1100}, device_scale_factor=1
                )
                page.on("pageerror", lambda error: errors.append(str(error)))
                requests = []
                page.on("request", lambda request: requests.append(request.url))
                page.goto(f"http://127.0.0.1:{server.server_address[1]}/")
                page.wait_for_function('document.querySelector("#viewer").dataset.modes')
                cases = json.loads((args.root / "cases.json").read_text())
                first = cases[0]["id"]
                initial_images = [u for u in requests if u.endswith((".jpg", ".png"))]
                assert len(initial_images) == 1, initial_images
                assert page.locator(".case-row").count() == len(cases)
                visited = []
                mode_checks = 0
                for row in cases:
                    cid = row["id"]
                    page.locator(f'[data-case="{cid}"]').click()
                    page.wait_for_function(
                        '(id)=>document.querySelector("#case-title").textContent===id', arg=cid
                    )
                    page.wait_for_function(
                        '()=>Object.values(JSON.parse(document.querySelector("#viewer").dataset.modes)).every(m=>m==="none")'
                    )
                    for mode in ["point", "box", "mask"]:
                        page.locator(f'[data-all="{mode}"]').click()
                        page.wait_for_function(
                            '(m)=>Object.values(JSON.parse(document.querySelector("#viewer").dataset.modes)).every(v=>v===m)',
                            arg=mode,
                        )
                        mode_checks += row["objects"]
                    page.locator("#clear").click()
                    page.wait_for_function(
                        '()=>Object.values(JSON.parse(document.querySelector("#viewer").dataset.modes)).every(v=>v==="none")'
                    )
                    visited.append(cid)
                page.locator(f'[data-case="{first}"]').click()
                page.wait_for_function(
                    '(id)=>document.querySelector("#case-title").textContent===id', arg=first
                )
                page.locator('[data-mode="U1"]').select_option("point")
                page.locator('[data-mode="U2"]').select_option("mask")
                page.locator('[data-mode="U3"]').select_option("box")
                page.wait_for_function(
                    '()=>{const m=JSON.parse(document.querySelector("#viewer").dataset.modes);return m.U1==="point"&&m.U2==="mask"&&m.U3==="box"}'
                )
                page.screenshot(path=str(args.output.with_suffix(".png")), full_page=True)
                page.locator("#reviewer").fill("BROWSER_SMOKE_ONLY")
                page.locator("#decision").select_option("revise")
                page.locator("#note").fill("Synthetic interaction check; not a human review.")
                page.locator("#unit-U1 details").last.evaluate("el=>el.open=true")
                page.locator('[data-suggestion="U1"]').fill("Synthetic instruction suggestion.")
                page.locator("#save").click()
                page.wait_for_function(
                    'document.querySelector("#save-state").textContent.includes("已保存")'
                )
                page.reload()
                page.wait_for_function('document.querySelector("#viewer").dataset.modes')
                assert page.locator("#note").input_value().startswith("Synthetic interaction check")
                assert page.locator("#decision").input_value() == "revise"
                with page.expect_download() as download:
                    page.locator("header a").click()
                assert download.value.suggested_filename == "v2_review_results.json"
                page.locator("#dataset").select_option("PACO-LVIS")
                assert page.locator(".case-row").count() == 119
                page.locator("#count").select_option("4")
                assert page.locator(".case-row").count() > 0
                page.locator("#dataset").select_option("")
                page.locator("#count").select_option("")
                page.set_viewport_size({"width": 390, "height": 844})
                page.screenshot(
                    path=str(args.output.with_name("review_mobile.png")), full_page=True
                )
                if errors:
                    raise ValueError(errors)
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    write_json(
        args.output,
        {
            "status": "passed",
            "browser": "Chromium via Playwright",
            "server": "standalone Python standard library HTTP",
            "cases": len(visited),
            "distinct_cases": len(set(visited)),
            "object_mode_render_checks": mode_checks,
            "initial_image_requests": len(initial_images),
            "javascript_errors": errors,
            "checks": [
                "lazy images: initial clean source only",
                "every object point/box/mask/none",
                "mixed per-object display",
                "case list and source/count filters",
                "persistent notes and instruction suggestions",
                "export",
                "mobile layout",
            ],
            "isolated_test_copy": True,
            "actual_human_records_created": 0,
        },
    )


if __name__ == "__main__":
    main()
