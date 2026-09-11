"""Browser checks: start Vite, then run `python tests/theme_smoke.py`.

Requires Python Playwright and Edge. Set BROWSER_CHANNEL=chromium to use
Playwright's installed Chromium, or BASE_URL to test a production preview.
API responses are mocked; no real account or budget data is changed.
"""
import json
import os

from playwright.sync_api import expect, sync_playwright

URL = os.environ.get("BASE_URL", "http://127.0.0.1:5173/")


def mock_login(route):
    setup = "setup" in route.request.url
    route.fulfill(status=200 if setup else 401, content_type="application/json",
                  body=json.dumps({"required": False} if setup else {"detail": "Login required"}))


def appearance(page, theme):
    expect(page.locator("html")).to_have_attribute("data-theme", theme)
    assert page.evaluate("getComputedStyle(document.documentElement).colorScheme") == theme
    expected = "#0d1916" if theme == "dark" else "#f4f7f6"
    expect(page.locator('meta[name="theme-color"]')).to_have_attribute("content", expected)


with sync_playwright() as playwright:
    channel = os.environ.get("BROWSER_CHANNEL", "msedge")
    browser = playwright.chromium.launch(**({} if channel == "chromium" else {"channel": channel}))
    context = browser.new_context(color_scheme="light")
    context.route("**/api/**", mock_login)
    errors = []
    context.on("weberror", lambda error: errors.append(str(error.error)))
    page = context.new_page()
    page.goto(URL)
    picker = page.get_by_label("Görünüm teması")
    expect(picker).to_have_value("system")
    appearance(page, "light")
    page.emulate_media(color_scheme="dark")
    appearance(page, "dark")
    picker.select_option("light")
    appearance(page, "light")
    page.reload()
    expect(picker).to_have_value("light")
    appearance(page, "light")
    page.emulate_media(color_scheme="light")
    picker.select_option("dark")
    appearance(page, "dark")
    page.reload()
    appearance(page, "dark")

    second = context.new_page()
    second.goto(URL)
    expect(second.get_by_label("Görünüm teması")).to_have_value("dark")
    picker.select_option("system")
    expect(second.get_by_label("Görünüm teması")).to_have_value("system")
    appearance(page, "light")
    page.emulate_media(color_scheme="dark")
    appearance(page, "dark")

    # Settings exposes the same preference as accessible radio controls.
    user = {"id": 1, "display_name": "Deneme", "is_admin": True, "username": "demo", "auth_source": "session"}
    fixtures = {"me": user, "bootstrap": {"today": "2026-09-11", "categories": [], "payment_methods": [], "people": [user]},
                "users": [user], "notifications": {"items": [], "unread": 0},
                "payment-methods": [], "categories": [], "reports/cards": []}
    context.unroute("**/api/**")

    def mock_settings(route):
        key = route.request.url.split("/api/")[-1].split("?")[0]
        route.fulfill(status=200 if key in fixtures else 503, content_type="application/json",
                      body=json.dumps(fixtures.get(key, {"detail": "Test endpoint unavailable"})))

    context.route("**/api/**", mock_settings)
    page.goto(URL + "#/ayarlar")
    page.reload()
    radios = page.get_by_role("radio")
    expect(radios).to_have_count(3)
    for width in (320, 390, 768, 1024, 1440):
        page.set_viewport_size({"width": width, "height": 900})
        for index, theme in ((0, "light"), (1, "dark"), (2, "dark")):
            radios.nth(index).check()
            appearance(page, theme)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Overflow at {width}px"
    radios.nth(0).focus()
    page.keyboard.press("ArrowRight")
    expect(radios.nth(1)).to_be_checked()
    appearance(page, "dark")
    assert not errors, errors
    context.close()

    # Disabled storage must not prevent login or theme changes.
    restricted = browser.new_context(color_scheme="dark")
    restricted.route("**/api/**", mock_login)
    restricted.add_init_script("Object.defineProperty(window, 'localStorage', { get() { throw new Error('disabled'); } });")
    page = restricted.new_page()
    page.goto(URL)
    appearance(page, "dark")
    page.get_by_label("Görünüm teması").select_option("light")
    appearance(page, "light")
    restricted.close()
    browser.close()
    print("PASS: system changes, manual overrides, reload, tab sync, settings, keyboard, responsive layout, disabled storage")
