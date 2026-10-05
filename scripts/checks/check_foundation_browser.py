"""Optional Playwright check of the foundation screen; run against Compose."""
from datetime import datetime, timezone
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[2] / "docs/implementation/mvp/phase2/evidence"
OUT.mkdir(parents=True, exist_ok=True)
checks, errors = [], []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        for width in [390, 768, 1440]:
            page.set_viewport_size({"width": width, "height": 950})
            page.goto("http://127.0.0.1:3000", wait_until="networkidle")
            page.get_by_role("status").filter(has_text="Đã kết nối cơ sở dữ liệu").wait_for()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(OUT / f"foundation-{width}.png"), full_page=True)
            checks.append({"width": width, "no_horizontal_overflow": True, "live_readiness_visible": True})
        page.reload(wait_until="networkidle")
        page.get_by_role("status").filter(has_text="Đã kết nối cơ sở dữ liệu").wait_for()
        assert not errors, errors
    finally:
        browser.close()
report = {
    "checked_at": datetime.now(timezone.utc).isoformat(),
    "viewports": checks,
    "reload": "pass",
    "browser_errors": errors,
}
(OUT / "browser-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("PASS: 3 viewport checks, reload, no browser runtime errors")
