"""Browser tests (Playwright) against a running ColorMuse in local mode.

Start the app first (see docs/TESTING.md), then:
    COLORMUSE_E2E_URL=http://localhost:8599 pytest tests/e2e -m e2e
Screenshots are written to tests/_artifacts/screens/.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

URL = os.environ.get("COLORMUSE_E2E_URL")
EMAIL = os.environ.get("COLORMUSE_E2E_EMAIL", "zidi@example.com")
PASSWORD = os.environ.get("COLORMUSE_E2E_PASSWORD", "demo-pass")
SHOTS = Path(__file__).resolve().parents[1] / "_artifacts" / "screens"

PAGES = [
    ("home", "Home", "Recent outfits"),
    ("matcher", "Color Matcher", "Harmony palettes"),
    ("wardrobe", "My Wardrobe", "pieces"),
    ("studio", "Outfit Studio", "Flat-lay"),
    ("occasions", "Occasions", "Occasion Planner"),
    ("looks", "Saved Looks", "look"),
    ("settings", "Settings", "Style profile"),
]

VIEWPORTS = {"desktop": {"width": 1366, "height": 900}, "mobile": {"width": 390, "height": 844}}

if not URL:
    pytest.skip("COLORMUSE_E2E_URL not set (start the app in local mode first)", allow_module_level=True)

sync_api = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _assert_no_exception(page) -> None:
    errors = page.locator("[data-testid='stException']")
    assert errors.count() == 0, errors.first.inner_text()[:800]


def _login(page) -> None:
    page.goto(URL)
    page.get_by_role("textbox", name="Email").fill(EMAIL)
    page.get_by_role("textbox", name="Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.get_by_text(re.compile("Hello,")).first.wait_for(timeout=30000)


def _open(page, title: str, viewport: str) -> None:
    top = page.locator("[data-testid='stTopNavLink']").filter(has_text=title)
    if top.count() and top.first.is_visible():
        top.first.click()
        return
    # narrow screens: the navigation collapses into the sidebar menu
    side = page.locator("[data-testid='stSidebarNavLink']").filter(has_text=title).first
    expand = page.locator("[data-testid='stExpandSidebarButton']")
    if expand.count() and expand.first.is_visible():
        expand.first.click()
        page.wait_for_timeout(500)
    side.click()
    # close the drawer again so it doesn't cover the page
    close = page.locator("[data-testid='stSidebarCollapseButton'] button, [data-testid='stSidebarCollapseButton']")
    page.wait_for_timeout(400)
    if close.count() and close.first.is_visible():
        close.first.click()


@pytest.mark.parametrize("viewport", list(VIEWPORTS))
def test_all_pages_render(browser, viewport):
    SHOTS.mkdir(parents=True, exist_ok=True)
    ctx = browser.new_context(viewport=VIEWPORTS[viewport], device_scale_factor=1)
    page = ctx.new_page()
    _login(page)
    for slug, title, marker in PAGES:
        _open(page, title, viewport)
        page.get_by_text(marker).first.wait_for(timeout=30000)
        page.wait_for_timeout(1200)
        _assert_no_exception(page)
        page.screenshot(path=str(SHOTS / f"{viewport}-{slug}.png"), full_page=True)
    ctx.close()


def test_login_rejects_wrong_password(browser):
    page = browser.new_page()
    page.goto(URL)
    page.get_by_role("textbox", name="Email").fill(EMAIL)
    page.get_by_role("textbox", name="Password").fill("wrong-password")
    page.get_by_role("button", name="Sign in").click()
    page.get_by_text("Incorrect email or password").wait_for(timeout=15000)
    page.close()


def test_studio_shows_mannequin_svg(browser):
    page = browser.new_page(viewport=VIEWPORTS["desktop"])
    _login(page)
    _open(page, "Outfit Studio", "desktop")
    page.get_by_role("tab", name="Mannequin").click()
    page.locator(".cm-mannequin svg").first.wait_for(timeout=20000)
    assert page.locator(".cm-mannequin svg [data-layer='body']").count() >= 1
    _assert_no_exception(page)
    page.close()


def _jpeg(path: Path) -> Path:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (600, 800), (238, 238, 236))
    d = ImageDraw.Draw(img)
    d.rectangle((150, 160, 450, 640), fill=(163, 177, 138))  # sage garment
    img.save(path, "JPEG")
    return path


def test_add_piece_with_photo_and_color_extraction(browser, tmp_path):
    page = browser.new_page(viewport=VIEWPORTS["desktop"])
    _login(page)
    _open(page, "My Wardrobe", "desktop")
    page.get_by_role("button", name="Add a piece").click()
    page.get_by_text("Add a piece").first.wait_for()
    page.locator("input[type='file']").first.set_input_files(str(_jpeg(tmp_path / "sage.jpg")))
    page.get_by_text("Detected colors").first.wait_for(timeout=60000)
    assert page.get_by_text("Sage").first.is_visible() or page.get_by_text("Eucalyptus").first.is_visible()
    page.get_by_role("textbox", name="Name").fill("Sage linen shirt")
    page.get_by_role("button", name="Save piece").click()
    page.get_by_text("Sage linen shirt").first.wait_for(timeout=60000)
    _assert_no_exception(page)
    page.screenshot(path=str(SHOTS / "flow-photo-saved.png"), full_page=True)
    page.close()


def test_matcher_to_studio_save_and_export(browser):
    page = browser.new_page(viewport=VIEWPORTS["desktop"])
    _login(page)
    _open(page, "Color Matcher", "desktop")
    page.get_by_role("button", name=re.compile("Build an outfit")).click()
    page.get_by_text("Outfit Studio").first.wait_for(timeout=30000)
    page.get_by_role("button", name=re.compile("Save$")).first.click()
    page.get_by_text("Look saved").first.wait_for(timeout=30000)
    page.get_by_role("button", name="Export images").click()
    with page.expect_download(timeout=60000) as dl:
        page.get_by_role("button", name="Mannequin PNG").click()
    assert dl.value.suggested_filename.endswith("-mannequin.png")
    page.get_by_role("tab", name="Mannequin").click()
    page.wait_for_timeout(800)
    page.screenshot(path=str(SHOTS / "flow-studio-mannequin.png"), full_page=True)
    _assert_no_exception(page)
    page.close()
