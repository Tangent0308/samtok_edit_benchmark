"""Optional real Chromium check of every case in an offline portable gallery."""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

from samtok_benchmark.io import write_json


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto((args.root / "index.html").resolve().as_uri())
        page.wait_for_function('document.querySelectorAll("#main img").length > 0')
        count = page.evaluate(
            'JSON.parse(document.getElementById("payload").textContent).cases.length'
        )
        visited = []
        for i in range(count):
            page.wait_for_function(
                '[...document.querySelectorAll("#main img")].every(i=>i.complete && i.naturalWidth>0)'
            )
            visited.append(page.locator("#main h2").inner_text())
            if i == 0:
                page.screenshot(path=str(args.output.with_suffix(".png")), full_page=True)
            if i + 1 < count:
                page.locator("#next").click()
        page.locator("#source").select_option("PACO-LVIS")
        source_count = int(page.locator("#position").inner_text().split("/")[-1])
        page.locator("#count").select_option("4")
        page.wait_for_function(
            '[...document.querySelectorAll("#main img")].every(i=>i.complete && i.naturalWidth>0)'
        )
        page.locator("#decision").select_option("revise")
        page.locator("#reviewer").fill("BROWSER_SMOKE_ONLY")
        page.locator("#note").fill("Synthetic UI test, not a human data approval.")
        page.locator("#save").click()
        with page.expect_download() as download:
            page.locator("#export").click()
        assert download.value.suggested_filename == "v2_personal_reviews.jsonl"
        page.evaluate("localStorage.clear()")
        page.locator("#source").select_option("")
        page.locator("#count").select_option("")
        page.locator("#search").fill("does-not-exist-test-id")
        assert page.locator(".empty").count() == 1
        page.locator("#search").fill("")
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(args.output.with_name("gallery_mobile.png")), full_page=True)
        if errors:
            raise ValueError(errors)
        browser.close()
    write_json(
        args.output,
        {
            "status": "passed",
            "browser": "Chromium via Playwright",
            "scheme": "file://",
            "cases_checked": len(visited),
            "distinct_case_ids": len(set(visited)),
            "paco_filter_count": source_count,
            "javascript_errors": errors,
            "checks": [
                "every source / public locator / gold review / mask image loaded",
                "source/count/search filters",
                "review localStorage and JSONL export",
                "mobile layout",
            ],
            "human_review_created": False,
        },
    )


if __name__ == "__main__":
    main()
